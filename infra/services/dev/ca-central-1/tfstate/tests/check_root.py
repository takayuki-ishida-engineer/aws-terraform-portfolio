#!/usr/bin/env python3
"""Verify the DEV tfstate bootstrap root from actual mock plans, offline.

1. Native events: every expected run passes; the two positive plans contain only
   the seven tfstate_bucket module resources, with the module's fixed protections
   (checked by the module checker) and the expected tags, and backend_settings
   gives one State key per root.
2. Required inputs: omitting project or aws_account_id fails before any plan,
   in a copy without the committed terraform.tfvars.
3. --self-test: semantic mutations and capture failures must be rejected.
No AWS API is called.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[3] / "modules/tfstate_bucket/tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts/terraform-testing"))
from check_tfstate_bucket import BUCKET, check_plan, require  # noqa: E402
from isolated_root import tfvars_free_copy  # noqa: E402

PREFIX = "module.state_bucket."
POSITIVE = {
    "bootstrap_state_bucket": {"retention": 90, "tags": {"Name": BUCKET, "service": "s3"}},
    "caller_tags_pass_through": {"retention": 90, "tags": {"owner": "platform", "Name": BUCKET, "service": "s3"}},
}
NEGATIVE = {
    "rejects_invalid_project": "project must be 1-10 lowercase",
    "rejects_long_project": "project must be 1-10 lowercase",
    "rejects_invalid_account": "aws_account_id must be exactly 12 decimal digits",
    "rejects_reserved_tag": "tags must not set project, env, service, managed or Name",
}
BACKEND_SETTINGS = {
    "bucket": BUCKET, "region": "ca-central-1", "use_lockfile": True, "encrypt": True,
    "keys": {root: f"test/dev/ca-central-1/{root}/terraform.tfstate" for root in ("network", "platform", "serverless-api", "api")},
}
REQUIRED = ("project", "aws_account_id")


def verify(events, exit_code):
    require(exit_code == 0, "terraform_exit")
    require([e.get("terraform") for e in events if e.get("type") == "version"] == ["1.17.0"], "version")
    expected_runs = set(POSITIVE) | set(NEGATIVE)
    abstracts = [e.get("test_abstract") for e in events if e.get("type") == "test_abstract"]
    require(len(abstracts) == 1 and len(abstracts[0]) == 1 and set(next(iter(abstracts[0].values()))) == expected_runs, "manifest")
    terminals = [(e["test_run"].get("run"), e["test_run"].get("status")) for e in events
                 if e.get("type") == "test_run" and "status" in e.get("test_run", {})]
    require(sorted(terminals) == sorted((run, "pass") for run in expected_runs), "run_terminals")
    require([e.get("test_summary") for e in events if e.get("type") == "test_summary"]
            == [{"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}], "summary")
    plans = {}
    for event in events:
        if event.get("type") == "test_plan":
            require(event.get("@testrun") not in plans, "duplicate_plan")
            plans[event.get("@testrun")] = event.get("test_plan") or {}
    for run, expected in POSITIVE.items():
        plan = copy.deepcopy(plans.get(run))
        require(plan, "missing_plan:" + run)
        for change in plan.get("resource_changes") or []:
            require(change.get("address", "").startswith(PREFIX), "resource_outside_module:" + run)
            change["address"] = change["address"][len(PREFIX):]
        check_plan(run, plan, expected)
        outputs = plan.get("output_changes") or {}
        require(outputs.get("backend_settings", {}).get("after") == BACKEND_SETTINGS, "backend_settings:" + run)
        require(outputs.get("bucket_name", {}).get("after") == BUCKET, "bucket_output:" + run)
    for run, fragment in NEGATIVE.items():
        errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("@testrun") == run
                  and e.get("diagnostic", {}).get("severity") == "error"]
        require(errors and all(d.get("summary") == "Invalid value for variable" for d in errors)
                and any(fragment in d.get("detail", "") for d in errors), "negative:" + run)
    require(not [e for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"
                 and e.get("@testrun") not in NEGATIVE], "unexpected_error_diagnostic")
    return {"status": "passed", "evidence_type": "actual_mock_plan_verification", "aws_api_calls": 0,
            "native_tests": len(expected_runs), "positive_plans": len(POSITIVE), "negative_cases": len(NEGATIVE)}


def required_inputs(terraform):
    header = (ROOT / "tests/tfstate.tftest.hcl").read_text(encoding="utf-8").split('\nrun "', 1)[0]
    header, count = re.subn(r"(?m)^variables \{[^}]*\}\n", "", header)
    require(count == 1, "required_fixture_header")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TF_VAR_", "TF_CLI_ARGS"))}
    env.update(TF_INPUT="0", TF_IN_AUTOMATION="1", AWS_EC2_METADATA_DISABLED="true",
               AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null")
    values = {"project": "test", "aws_account_id": "000000000000"}
    results = []
    with tfvars_free_copy(ROOT) as (workspace, isolation):
        env.update(isolation)
        for missing in REQUIRED:
            folder = workspace / "tests" / missing
            folder.mkdir()
            supplied = "\n".join(f"  {k} = {json.dumps(v)}" for k, v in values.items() if k != missing)
            (folder / "missing.tftest.hcl").write_text(header + "\nvariables {\n" + supplied + '\n}\nrun "missing_input" {\n  command = plan\n}\n')
            process = subprocess.run([terraform, "test", "-json", "-no-color", "-test-directory=" + str(folder.relative_to(workspace))],
                                     cwd=workspace, env=env, capture_output=True, text=True, check=False)
            events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith("{")]
            errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e["diagnostic"].get("severity") == "error"]
            require(process.returncode == 1 and not process.stderr.strip() and errors
                    and all(d.get("summary") == "No value for required variable" for d in errors)
                    and any(missing in d.get("detail", "") for d in errors)
                    and not any(e.get("type") == "test_plan" for e in events), "required_input:" + missing)
            results.append(missing)
    return results


def plan_change(events, run, address):
    for event in events:
        if event.get("type") == "test_plan" and event.get("@testrun") == run:
            for item in event["test_plan"]["resource_changes"]:
                if item["address"] == PREFIX + address:
                    return item
    raise KeyError(address)


def output(events, run, name):
    return next(e for e in events if e.get("type") == "test_plan" and e.get("@testrun") == run)["test_plan"]["output_changes"][name]


def mutations():
    run = "bootstrap_state_bucket"
    yield "semantic", "state_key", lambda e: output(e, run, "backend_settings")["after"]["keys"].update(network="test/dev/network.tfstate")
    yield "semantic", "lockfile_off", lambda e: output(e, run, "backend_settings")["after"].update(use_lockfile=False)
    yield "semantic", "unencrypted_backend", lambda e: output(e, run, "backend_settings")["after"].update(encrypt=False)
    yield "semantic", "other_region", lambda e: output(e, run, "backend_settings")["after"].update(region="us-east-1")
    yield "semantic", "bucket_name", lambda e: plan_change(e, run, "aws_s3_bucket.this")["change"]["after"].update(bucket="test-s3-tfstate")
    yield "semantic", "caller_tags_lost", lambda e: plan_change(e, "caller_tags_pass_through", "aws_s3_bucket.this")["change"]["after"]["tags"].pop("owner")
    yield "semantic", "versioning_suspended", lambda e: plan_change(e, run, "aws_s3_bucket_versioning.this")["change"]["after"][
        "versioning_configuration"][0].update(status="Suspended")
    yield "semantic", "force_destroy", lambda e: plan_change(e, run, "aws_s3_bucket.this")["change"]["after"].update(force_destroy=True)
    yield "capture", "resource_outside_module", lambda e: plan_change(e, run, "aws_s3_bucket.this").update(address="aws_s3_bucket.this")
    yield "capture", "no_summary", lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != "test_summary"])
    yield "capture", "no_plans", lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != "test_plan"])
    yield "capture", "negative_diagnostic_lost", lambda e: e.__setitem__(slice(None), [
        x for x in e if not (x.get("type") == "diagnostic" and x.get("@testrun") == "rejects_invalid_account")])


def self_test(events):
    counts = {"semantic_mutations": 0, "capture_failure_injections": 0}
    for kind, name, mutate in mutations():
        mutated = copy.deepcopy(events)
        mutate(mutated)
        try:
            verify(mutated, 0)
        except (ValueError, KeyError, TypeError, StopIteration):
            counts["semantic_mutations" if kind == "semantic" else "capture_failure_injections"] += 1
            continue
        raise ValueError("mutation_not_detected:" + name)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-events", required=True)
    parser.add_argument("--terraform-exit-code", type=int, required=True)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        with open(args.test_events, encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        report = verify(events, args.terraform_exit_code)
        report["required_input_rejections"] = len(required_inputs(args.terraform))
        if args.self_test:
            report.update(self_test(events))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print("tfstate root verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
