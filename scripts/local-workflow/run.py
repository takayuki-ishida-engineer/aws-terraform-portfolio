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
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402

PLAN_FILE = "dev-local.tfplan"


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
    parser.add_argument("command", choices=["plan", "apply", "destroy", "migrate-state"])
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
