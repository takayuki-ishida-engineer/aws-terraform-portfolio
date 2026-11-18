#!/usr/bin/env python3
"""Run a local DEV plan, apply or destroy for one root behind the preflight.

Workstation only (docs/deployment-configuration.md section 2): never in CI,
Codex Cloud, a Claude Code cloud session or any other automation; it refuses
to start there. The operator's own AWS CLI credentials are used by Terraform
and the read-only preflight; this script never reads them.

Sequence: terraform init (committed lock, read-only) -> offline and live
preflight -> saved plan -> typed confirmation (apply/destroy) -> apply of that
exact saved plan. The saved plan is written inside the root under an ignored
name and deleted afterwards, because a plan can contain sensitive values.

`publish-artifact` (serverless-api, finding F2) creates the artifact bucket with
a targeted plan, uploads the committed function/function.zip and writes the
returned object version into local.auto.tfvars; then run `apply`.

With the optional S3 backend (an untracked backend_override.tf and
backend.s3.tfbackend in the root), init passes the backend settings, and
`migrate-state` moves the root's existing local State into the bucket after
the same checks (Terraform asks before copying).

Apply roots in this order: tfstate (only for the S3 backend), network,
platform, developer-access, then serverless-api and api. Destroy in the
reverse order.
Cross-root hand-off is still manual (platform needs the network output in its
local.auto.tfvars).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff  # noqa: E402
import preflight  # noqa: E402

PLAN_FILE = "dev-local.tfplan"
ARTIFACT_FILE = "function/function.zip"
# Findings expected before the first upload: the version does not exist yet.
ARTIFACT_PENDING = {"placeholder:artifact_object_version", "local_value_missing:artifact_object_version"}


def terraform_step(terraform, root, arguments, env):
    process = subprocess.run([terraform, "-chdir=" + str(root)] + arguments, env=env, check=False)
    if process.returncode != 0:
        raise preflight.PreflightError("terraform_failed:" + arguments[0])


def migrate_state(root_name, root, terraform, aws, environment, out):
    """Move the root's local State into the S3 backend after the checks pass."""
    if not (root / preflight.BACKEND_OVERRIDE).is_file():
        out("Refused: copy backend_override.tf.example and backend.s3.tfbackend.example first (see the README).")
        return 1
    findings = preflight.migration_findings(root_name, root, aws, environment)
    if findings:
        out("Migration checks failed for " + root_name + ": " + ", ".join(findings))
        return 1
    terraform_step(terraform, root, ["init", "-lockfile=readonly", "-backend-config=" + preflight.BACKEND_CONFIG,
                                     "-migrate-state"], environment)
    report = preflight.preflight(root_name, terraform, aws, live=True, services=root.parent, env=environment, root=root)
    out(("Migrated; preflight passed for " if report["status"] == "passed" else "Migrated; preflight failed for ")
        + root_name + ": " + ", ".join(report["findings"]))
    return 0 if report["status"] == "passed" else 1


def publish_artifact(root, terraform, aws, environment, confirm, out):
    """Finding F2: create the artifact bucket first, upload the Lambda ZIP, record its version."""
    report = preflight.preflight("serverless-api", terraform, aws, live=False, services=root.parent, env=environment, root=root)
    blocking = [f for f in report["findings"] if f not in ARTIFACT_PENDING]
    if blocking:
        out("Preflight failed for serverless-api: " + ", ".join(blocking))
        return 1
    values = preflight.effective_values(root, terraform, environment)
    caller = preflight.caller_findings(values["aws_account_id"], aws, environment)
    if caller:
        out("Refused: " + ", ".join(caller))
        return 1
    plan = root / PLAN_FILE
    try:
        process = subprocess.run([terraform, "-chdir=" + str(root), "plan", "-input=false", "-detailed-exitcode",
                                  "-target=module.artifact_bucket", "-out=" + PLAN_FILE], env=environment, check=False)
        if process.returncode not in (0, 2):
            raise preflight.PreflightError("terraform_failed:plan")
        if process.returncode == 2:
            answer = confirm("Type serverless-api to create the artifact bucket with exactly this targeted plan: ")
            if answer.strip() != "serverless-api":
                out("Not confirmed; nothing was changed.")
                return 1
            terraform_step(terraform, root, ["apply", "-input=false", PLAN_FILE], environment)
    finally:
        plan.unlink(missing_ok=True)
    bucket = values["project"] + "-dev-s3-artifact"
    upload = subprocess.run([aws, "s3api", "put-object", "--bucket", bucket, "--key", values["artifact_key"],
                             "--body", str(root / ARTIFACT_FILE), "--region", preflight.REGION, "--output", "json"],
                            env=environment, capture_output=True, text=True, check=False)
    version = json.loads(upload.stdout).get("VersionId") if upload.returncode == 0 and upload.stdout.strip() else None
    if not version or version == "null":
        out("Upload failed or the bucket is not versioned; nothing was recorded.")
        return 1
    handoff.write_assignment(root / preflight.LOCAL_FILE, "artifact_object_version", version)
    out("Uploaded " + ARTIFACT_FILE + " as version " + version + "; now run: python3 scripts/local-workflow/run.py serverless-api apply")
    return 0


def run(root_name, command, terraform="terraform", aws="aws", services=preflight.SERVICES, env=None,
        confirm=input, out=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out("Refused (" + refusal + "): real AWS operations run only from the operator's workstation.")
        return 1
    root = preflight.root_directory(root_name, services)
    if command == "migrate-state":
        return migrate_state(root_name, root, terraform, aws, environment, out)
    if command == "publish-artifact":
        if root_name != "serverless-api":
            out("Refused: publish-artifact applies only to serverless-api.")
            return 1
        backend = ["-backend-config=" + preflight.BACKEND_CONFIG] if (root / preflight.BACKEND_OVERRIDE).exists() else []
        terraform_step(terraform, root, ["init", "-input=false", "-lockfile=readonly"] + backend, environment)
        return publish_artifact(root, terraform, aws, environment, confirm, out)
    plan = root / PLAN_FILE
    work_tree = preflight.git_work_tree(root)
    if subprocess.run(["git", "-C", str(work_tree), "check-ignore", "-q", "--", os.path.relpath(plan, work_tree)],
                      capture_output=True, check=False).returncode != 0:
        out("Refused: the saved plan path is not ignored by Git: " + str(plan))
        return 1
    backend = ["-backend-config=" + preflight.BACKEND_CONFIG] if (root / preflight.BACKEND_OVERRIDE).exists() else []
    terraform_step(terraform, root, ["init", "-input=false", "-lockfile=readonly"] + backend, environment)
    report = preflight.preflight(root_name, terraform, aws, live=True, services=services, env=environment)
    if report["status"] != "passed":
        out("Preflight failed for " + root_name + ": " + ", ".join(report["findings"]))
        return 1
    out("Preflight passed for " + root_name + ".")
    try:
        terraform_step(terraform, root, ["plan", "-input=false", "-out=" + PLAN_FILE]
                       + (["-destroy"] if command == "destroy" else []), environment)
        if command == "plan":
            return 0
        answer = confirm("Type the root name (" + root_name + ") to " + command + " exactly this plan: ")
        if answer.strip() != root_name:
            out("Not confirmed; nothing was changed.")
            return 1
        terraform_step(terraform, root, ["apply", "-input=false", PLAN_FILE], environment)
        return 0
    finally:
        plan.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", choices=sorted(preflight.ENVIRONMENT_INPUTS))
    parser.add_argument("command", choices=["plan", "apply", "destroy", "migrate-state", "publish-artifact"])
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--aws", default="aws")
    args = parser.parse_args(argv)
    try:
        return run(args.root, args.command, args.terraform, args.aws)
    except preflight.PreflightError as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
