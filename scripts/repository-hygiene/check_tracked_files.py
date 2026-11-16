#!/usr/bin/env python3
"""Fail closed when files that must stay on the operator workstation are tracked.

Real environment-specific values, backend settings that name a real state bucket,
State, saved plans and Terraform working directories belong only on the local
operator workstation. Only committed placeholders (terraform.tfvars), feature
flags (features.auto.tfvars) and *.example templates may be tracked.

This checks tracked paths only. It never reads file contents, prints no values
and makes no AWS call.
"""

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import PurePosixPath

ALLOWED_TFVARS = frozenset({"terraform.tfvars", "features.auto.tfvars"})
FORBIDDEN = (
    ("local-values", ("local.auto.tfvars", "local.auto.tfvars.json", "*.local.tfvars", "*.local.tfvars.json")),
    ("backend-settings", ("*.tfbackend", "backend_override.tf", "backend_override.tf.json")),
    ("override-files", ("override.tf", "override.tf.json", "*_override.tf", "*_override.tf.json")),
    ("state", ("*.tfstate", "*.tfstate.*", ".terraform.tfstate.lock.info")),
    ("saved-plans", ("*.tfplan", "*.tfplan.*", "tfplan", "tfplan.*", "planout", "planout.*", "plan.out")),
)


def violations(paths):
    """Return sorted (rule, path) pairs for tracked paths that must stay local."""
    found = set()
    for raw in paths:
        path = PurePosixPath(raw)
        name = path.name
        if ".terraform" in path.parts[:-1]:
            found.add(("terraform-working-directory", raw))
        for rule, patterns in FORBIDDEN:
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
                found.add((rule, raw))
        if (name.endswith(".tfvars") or name.endswith(".tfvars.json")) and name not in ALLOWED_TFVARS:
            found.add(("tfvars-not-allowed", raw))
    return sorted(found)


def tracked_paths():
    output = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def self_test():
    allowed = [
        "infra/services/dev/ca-central-1/network/terraform.tfvars",
        "infra/services/dev/ca-central-1/serverless-api/features.auto.tfvars",
        "infra/services/dev/ca-central-1/network/local.auto.tfvars.example",
        "infra/services/dev/ca-central-1/network/backend.s3.tfbackend.example",
        "infra/services/dev/ca-central-1/network/backend_override.tf.example",
        "infra/services/dev/ca-central-1/network/.terraform.lock.hcl",
        "docs/terraform-plan-review.md",
    ]
    assert violations(allowed) == [], violations(allowed)
    cases = {
        "infra/x/local.auto.tfvars": "local-values",
        "infra/x/local.auto.tfvars.json": "local-values",
        "infra/x/dev.local.tfvars": "local-values",
        "infra/x/backend.s3.tfbackend": "backend-settings",
        "infra/x/backend_override.tf": "backend-settings",
        "infra/x/override.tf": "override-files",
        "infra/x/provider_override.tf.json": "override-files",
        "infra/x/terraform.tfstate": "state",
        "infra/x/terraform.tfstate.backup": "state",
        "infra/x/.terraform.tfstate.lock.info": "state",
        "infra/x/create.tfplan": "saved-plans",
        "infra/x/tfplan": "saved-plans",
        "infra/x/plan.out": "saved-plans",
        "infra/x/.terraform/providers/registry.terraform.io/hashicorp/aws/terraform-provider-aws": "terraform-working-directory",
        "infra/x/secrets.tfvars": "tfvars-not-allowed",
        "infra/x/prod.tfvars.json": "tfvars-not-allowed",
    }
    for path, rule in cases.items():
        result = violations([path])
        assert (rule, path) in result, (path, result)
    # Every forbidden rule must be exercised, so a removed pattern cannot pass silently.
    exercised = {rule for rule in cases.values()}
    expected = {rule for rule, _ in FORBIDDEN} | {"terraform-working-directory", "tfvars-not-allowed"}
    assert exercised == expected, (exercised, expected)
    return len(cases) + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="exercise positive and negative cases only")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps({"status": "passed", "mode": "self-test", "cases": self_test()}))
        return 0
    found = violations(tracked_paths())
    if found:
        print(json.dumps({"status": "failed", "violations": [{"rule": rule, "path": path} for rule, path in found]}))
        return 1
    print(json.dumps({"status": "passed", "mode": "repository", "aws_api_calls": 0}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
