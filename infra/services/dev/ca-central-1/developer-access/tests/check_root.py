#!/usr/bin/env python3
"""Verify the DEV developer-access root from actual mock plans, offline.

1. Native events: every expected run passes; each positive plan contains only
   the six developer_access module resources with the module's hardening
   (checked by the module checker) bound to the selected subnet, the VPC and the
   resolved AL2023 AMI, and the root output exposes the Session Manager target.
2. Required inputs: omitting project, aws_account_id, network_reference or
   subnet_key fails before any plan, in a copy without the committed values.
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
sys.path.insert(0, str(ROOT.parents[3] / "modules/developer_access/tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts/terraform-testing"))
from check_developer_access import check_plan, require  # noqa: E402
from isolated_root import tfvars_free_copy  # noqa: E402

PREFIX = "module.developer_access."
NETWORK = {"interface_version": 1, "scope": {"environment": "dev", "partition": "aws", "region": "ca-central-1", "account_id": "000000000000"},
           "vpc_id": "vpc-0123456789abcdef0", "vpc_cidr": "10.40.0.0/16",
           "private_subnet_ids": {"private1": "subnet-0123456789abcdef0", "private2": "subnet-0fedcba9876543210"}}
AMI = "ami-0123456789abcdef0"
POSITIVE = {
    "access_host": {"subnet": "private1", "instance_type": "t3.micro", "tags": {}},
    "alternate_subnet_and_type": {"subnet": "private2", "instance_type": "t3.small", "tags": {"owner": "platform"}},
}
NEGATIVE = {
    "rejects_foreign_account_scope": "network_reference must be interface version 1",
    "rejects_other_region_scope": "network_reference must be interface version 1",
    "rejects_interface_version_2": "network_reference must be interface version 1",
    "rejects_unknown_subnet_key": "subnet_key must be a key",
    "rejects_invalid_project": "project must be 1-10 lowercase",
    "rejects_invalid_account": "aws_account_id must be exactly 12 decimal digits",
    "rejects_reserved_tag": "tags must not set project, env, service, managed or Name",
}
OUTPUT = {"instance_id": "i-0123456789abcdef0", "private_ip": "10.40.1.10", "security_group_id": "sg-0123456789abcdef0",
          "role_arn": "arn:aws:iam::000000000000:role/test-dev-role-bastion", "region": "ca-central-1"}
REQUIRED = ("project", "aws_account_id", "network_reference", "subnet_key")


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
        inputs = {"vpc_id": NETWORK["vpc_id"], "vpc_cidr": NETWORK["vpc_cidr"],
                  "subnet_id": NETWORK["private_subnet_ids"][expected["subnet"]], "ami_id": AMI}
        check_plan(run, plan, expected, inputs)
        require((plan.get("output_changes") or {}).get("developer_access", {}).get("after") == OUTPUT, "root_output:" + run)
    for run, fragment in NEGATIVE.items():
        errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("@testrun") == run
                  and e.get("diagnostic", {}).get("severity") == "error"]
        require(errors and all(d.get("summary") == "Invalid value for variable" for d in errors)
                and any(fragment in d.get("detail", "") for d in errors), "negative:" + run)
    require(not [e for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"
                 and e.get("@testrun") not in NEGATIVE], "unexpected_error_diagnostic")
    source = (ROOT / "main.tf").read_text(encoding="utf-8")
    require('name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"' in source
            and "ami_id        = data.aws_ssm_parameter.al2023.insecure_value" in source, "al2023_public_parameter")
    return {"status": "passed", "evidence_type": "actual_mock_plan_verification", "aws_api_calls": 0,
            "native_tests": len(expected_runs), "positive_plans": len(POSITIVE), "negative_cases": len(NEGATIVE)}


def required_inputs(terraform):
    header = (ROOT / "tests/developer_access.tftest.hcl").read_text(encoding="utf-8").split('\nrun "', 1)[0]
    require("variables {" not in header and "override_data" in header, "required_fixture_header")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TF_VAR_", "TF_CLI_ARGS"))}
    env.update(TF_INPUT="0", TF_IN_AUTOMATION="1", AWS_EC2_METADATA_DISABLED="true",
               AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null")
    values = {"project": "test", "aws_account_id": "000000000000", "network_reference": NETWORK, "subnet_key": "private1"}
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
                    and any(d.get("summary") == "No value for required variable" and missing in d.get("detail", "") for d in errors)
                    and not any(e.get("type") == "test_plan" for e in events), "required_input:" + missing)
            results.append(missing)
    return results


def change(events, run, address):
    plan = next(e for e in events if e.get("type") == "test_plan" and e.get("@testrun") == run)["test_plan"]
    return next(r for r in plan["resource_changes"] if r["address"] == PREFIX + address)


def mutations():
    run = "access_host"
    yield "semantic", "other_subnet", lambda e: change(e, run, "aws_instance.this")["change"]["after"].update(subnet_id="subnet-0fedcba9876543210")
    yield "semantic", "unresolved_ami", lambda e: change(e, run, "aws_instance.this")["change"]["after"].update(ami="ami-0aaaaaaaaaaaaaaaa")
    yield "semantic", "other_vpc", lambda e: change(e, run, "aws_security_group.this")["change"]["after"].update(vpc_id="vpc-0aaaaaaaaaaaaaaaa")
    yield "semantic", "egress_outside_vpc", lambda e: change(e, run, "aws_vpc_security_group_egress_rule.vpc_https")["change"]["after"].update(cidr_ipv4="10.0.0.0/8")
    yield "semantic", "public_ip", lambda e: change(e, run, "aws_instance.this")["change"]["after"].update(associate_public_ip_address=True)
    yield "semantic", "output_target", lambda e: next(x for x in e if x.get("type") == "test_plan" and x.get("@testrun") == run)["test_plan"][
        "output_changes"]["developer_access"]["after"].update(instance_id="i-0aaaaaaaaaaaaaaaa")
    yield "capture", "resource_outside_module", lambda e: change(e, run, "aws_instance.this").update(address="aws_instance.this")
    yield "capture", "no_summary", lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != "test_summary"])
    yield "capture", "no_plans", lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != "test_plan"])
    yield "capture", "negative_diagnostic_lost", lambda e: e.__setitem__(slice(None), [
        x for x in e if not (x.get("type") == "diagnostic" and x.get("@testrun") == "rejects_unknown_subnet_key")])


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
        print("developer-access root verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
