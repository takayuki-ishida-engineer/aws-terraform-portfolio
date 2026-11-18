#!/usr/bin/env python3
"""Delete every object version from a DEV artifact or State bucket before teardown.

Workstation only, like run.py; refused in CI and cloud sessions. The DEV buckets
keep force_destroy = false and versioning on, so terraform destroy fails while
any object version or delete marker remains. This script accepts only the
project's own buckets (``<project>-dev-s3-artifact`` or
``<project>-dev-s3-tfstate``, with project and account taken from the root's
local.auto.tfvars), checks the caller account, shows the count and asks for the
bucket name before deleting, in batches of at most 1000.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402

ROOT_BY_PURPOSE = {"artifact": "serverless-api", "tfstate": "tfstate"}


def aws_json(aws, arguments, env):
    process = subprocess.run([aws] + arguments + ["--region", preflight.REGION, "--output", "json"], env=env,
                             capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise preflight.PreflightError("aws_failed:" + " ".join(arguments[:2]))
    return json.loads(process.stdout) if process.stdout.strip() else {}


def object_versions(aws, bucket, env):
    """All (Key, VersionId) pairs of object versions and delete markers."""
    items, arguments = [], ["s3api", "list-object-versions", "--bucket", bucket]
    while True:
        page = aws_json(aws, arguments, env)
        for field in ("Versions", "DeleteMarkers"):
            items += [{"Key": item["Key"], "VersionId": item["VersionId"]} for item in page.get(field) or []]
        if not page.get("IsTruncated"):
            return items
        arguments = ["s3api", "list-object-versions", "--bucket", bucket,
                     "--key-marker", page["NextKeyMarker"], "--version-id-marker", page["NextVersionIdMarker"]]


def empty_bucket(bucket, aws="aws", services=preflight.SERVICES, env=None, confirm=input, out=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out("Refused (" + refusal + "): run teardown only on the operator's workstation.")
        return 1
    match = re.fullmatch(r"([a-z]([a-z0-9-]{0,8}[a-z0-9])?)-dev-s3-(artifact|tfstate)", bucket)
    if not match:
        out("Refused: only <project>-dev-s3-artifact or <project>-dev-s3-tfstate buckets are emptied.")
        return 1
    root = Path(services) / ROOT_BY_PURPOSE[match.group(3)]
    project, account = preflight.local_value(root, "project"), preflight.local_value(root, "aws_account_id")
    if project != match.group(1) or project in preflight.PLACEHOLDER_PROJECTS:
        out("Refused: the bucket does not belong to the project in " + str(root / preflight.LOCAL_FILE))
        return 1
    caller = preflight.caller_findings(account, aws, environment)
    if caller:
        out("Refused: " + ", ".join(caller))
        return 1
    items = object_versions(aws, bucket, environment)
    if not items:
        out(bucket + " is already empty.")
        return 0
    answer = confirm(f"Type {bucket} to permanently delete {len(items)} object versions and delete markers: ")
    if answer.strip() != bucket:
        out("Not confirmed; nothing was deleted.")
        return 1
    for start in range(0, len(items), 1000):
        batch = {"Objects": items[start:start + 1000], "Quiet": True}
        result = aws_json(aws, ["s3api", "delete-objects", "--bucket", bucket, "--delete", json.dumps(batch)], environment)
        if result.get("Errors"):
            out("Some deletions failed; rerun after checking: " + json.dumps(result["Errors"][:3]))
            return 1
    out(f"Deleted {len(items)} object versions and delete markers from {bucket}.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bucket")
    parser.add_argument("--aws", default="aws")
    args = parser.parse_args(argv)
    try:
        return empty_bucket(args.bucket, args.aws)
    except (preflight.PreflightError, KeyError, json.JSONDecodeError, OSError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
