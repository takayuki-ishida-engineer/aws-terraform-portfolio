#!/usr/bin/env python3
"""Run a local DEV plan, apply or destroy for one root behind the preflight.

Workstation only (docs/deployment-configuration.md section 2): never in CI,
Codex Cloud or any other automation. The operator's own AWS CLI credentials are
used by Terraform and the read-only preflight; this script never reads them.

Sequence: terraform init (committed lock, read-only) -> offline and live
preflight -> saved plan -> typed confirmation (apply/destroy) -> apply of that
exact saved plan. The saved plan is written inside the root under an ignored
name and deleted afterwards, because a plan can contain sensitive values.

Apply roots in this order: network, platform, then serverless-api and api.
Destroy in the reverse order. Cross-root hand-off is still manual
(platform needs the network output in its local.auto.tfvars).
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


def run(root_name, command, terraform="terraform", aws="aws", services=preflight.SERVICES, env=None,
        confirm=input, out=print):
    environment = dict(os.environ if env is None else env)
    if environment.get("CI") or environment.get("GITHUB_ACTIONS"):
        out("Refused: real AWS operations run only from the operator's workstation, never in CI.")
        return 1
    root = preflight.root_directory(root_name, services)
    plan = root / PLAN_FILE
    work_tree = preflight.git_work_tree(root)
    if subprocess.run(["git", "-C", str(work_tree), "check-ignore", "-q", "--", os.path.relpath(plan, work_tree)],
                      capture_output=True, check=False).returncode != 0:
        out("Refused: the saved plan path is not ignored by Git: " + str(plan))
        return 1
    terraform_step(terraform, root, ["init", "-input=false", "-lockfile=readonly"], environment)
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
    parser.add_argument("command", choices=["plan", "apply", "destroy"])
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
