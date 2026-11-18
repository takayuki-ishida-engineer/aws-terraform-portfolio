#!/usr/bin/env python3
"""Prove each required DEV network input fails before a successful mock plan."""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[3] / "modules/vpc/tests"))
from check_network_configuration import parse, require  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts/terraform-testing"))
from isolated_root import tfvars_free_copy  # noqa: E402

REQUIRED = ("aws_account_id", "project", "vpc_cidr", "private_subnets",
            "public_subnets", "active_workload_az", "nat")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args()
    try:
        cases = parse((ROOT.parents[3] / "modules/vpc/tests/network_cases.json").read_text())
        inputs = cases["root_positive"]["dev_network"]
        environment = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TF_VAR_", "TF_CLI_ARGS"))}
        environment.update(TF_INPUT="0", TF_IN_AUTOMATION="1", AWS_EC2_METADATA_DISABLED="true",
                           AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null")
        results = []
        header = (ROOT / "tests/network.tftest.hcl").read_text().split('\nrun "', 1)[0]
        # Each fixture supplies its own complete variable block; drop the native-suite
        # file-level defaults so missing inputs really are missing.
        header, defaults = re.subn(r"(?m)^variables \{[^}]*\}\n", "", header)
        require(defaults == 1, "native_header_defaults")
        # Committed terraform.tfvars would satisfy the omitted inputs; run in a tfvars-free copy.
        with tfvars_free_copy(ROOT) as (workspace, isolation):
            environment.update(isolation)
            temporary = workspace / "tests"
            for missing in REQUIRED:
                folder = Path(temporary) / missing
                folder.mkdir()
                variables = "\n".join(f"  {k} = {json.dumps(v)}" for k, v in inputs.items() if k != missing)
                source = header + '\nvariables {\n' + variables + '\n}\nrun "missing_input" {\n  command = plan\n}\n'
                (folder / "missing.tftest.hcl").write_text(source)
                process = subprocess.run([args.terraform, "test", "-json", "-verbose", "-no-color",
                    "-test-directory=" + str(folder.relative_to(workspace))], cwd=workspace, env=environment,
                    capture_output=True, text=True, check=False)
                require(process.returncode == 1 and not process.stderr.strip(), "expected_failed_process:" + missing)
                events = [parse(line) for line in process.stdout.splitlines()]
                errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"]
                require(errors and all(e.get("summary") == "No value for required variable" for e in errors)
                    and any(missing in e.get("detail", "") for e in errors), "missing_input_diagnostic:" + missing)
                require(not any(e.get("type") == "test_plan" for e in events), "no_successful_plan:" + missing)
                terminals = [e["test_run"]["status"] for e in events if e.get("type") == "test_run" and "status" in e["test_run"]]
                summaries = [e["test_summary"] for e in events if e.get("type") == "test_summary"]
                require(len(terminals) == 1 and terminals[0] in {"fail", "error"}, "failed_terminal:" + missing)
                require(len(summaries) == 1 and summaries[0].get("status") in {"fail", "error"}
                    and summaries[0].get("passed") == summaries[0].get("skipped") == 0
                    and summaries[0].get("failed", 0) + summaries[0].get("errored", 0) == 1, "failed_summary:" + missing)
                results.append({"missing_input": missing, "rejected": True, "terraform_exit": 1, "successful_plans": 0})
            security = []
            wrong_public = copy.deepcopy(inputs)
            wrong_public["nat"]["public_subnet_key_by_nat_az"]["ca-central-1a"] = "public2"
            wrong_region = copy.deepcopy(inputs)
            wrong_region["private_subnets"]["private2"]["availability_zone"] = "us-east-1b"
            unsafe_policy = copy.deepcopy(cases["root_positive"]["dev_network_s3"])
            policy = parse(unsafe_policy["gateway_endpoints"]["s3"]["policy_json"])
            policy["Statement"][0]["Action"] = ["s3:*"]
            unsafe_policy["gateway_endpoints"]["s3"]["policy_json"] = json.dumps(policy)
            unconditioned = copy.deepcopy(cases["root_positive"]["dev_network_s3"])
            legacy_principal = copy.deepcopy(unconditioned)
            foreign_role = copy.deepcopy(unconditioned)
            ifexists = copy.deepcopy(unconditioned)
            policy = parse(unconditioned["gateway_endpoints"]["s3"]["policy_json"])
            policy["Statement"][0].pop("Condition")
            unconditioned["gateway_endpoints"]["s3"]["policy_json"] = json.dumps(policy)
            policy = parse(legacy_principal["gateway_endpoints"]["s3"]["policy_json"])
            policy["Statement"][0]["Principal"] = {"AWS": "arn:aws:iam::000000000000:role/test-network-reader"}
            legacy_principal["gateway_endpoints"]["s3"]["policy_json"] = json.dumps(policy)
            policy = parse(foreign_role["gateway_endpoints"]["s3"]["policy_json"])
            policy["Statement"][0]["Condition"]["ArnEquals"]["aws:PrincipalArn"] = "arn:aws:iam::111111111111:role/test-network-reader"
            foreign_role["gateway_endpoints"]["s3"]["policy_json"] = json.dumps(policy)
            policy = parse(ifexists["gateway_endpoints"]["s3"]["policy_json"])
            policy["Statement"][0]["Condition"] = {"ArnEqualsIfExists": policy["Statement"][0]["Condition"]["ArnEquals"]}
            ifexists["gateway_endpoints"]["s3"]["policy_json"] = json.dumps(policy)
            for name, supplied, summary, reason in [
                ("child_wrong_nat_public_az", wrong_public, "Resource precondition failed", "same-AZ public subnet"),
                ("child_wrong_region", wrong_region, "Resource precondition failed", "AZ must match"),
                ("child_unsafe_endpoint_policy", unsafe_policy, "Invalid value for variable", "Endpoint policy must use"),
                ("child_unconditioned_wildcard", unconditioned, "Invalid value for variable", "Endpoint policy must use"),
                ("child_legacy_principal_object", legacy_principal, "Invalid value for variable", "Endpoint policy must use"),
                ("child_foreign_role_condition", foreign_role, "Resource precondition failed", "explicit expected account"),
                ("child_ifexists_role_condition", ifexists, "Invalid value for variable", "Endpoint policy must use"),
            ]:
                folder = Path(temporary) / name
                folder.mkdir()
                variables = "\n".join(f"  {k} = {json.dumps(v)}" for k, v in supplied.items())
                (folder / "rejected.tftest.hcl").write_text(header + '\nvariables {\n' + variables + '\n}\nrun "rejected_input" {\n  command = plan\n}\n')
                process = subprocess.run([args.terraform, "test", "-json", "-verbose", "-no-color",
                    "-test-directory=" + str(folder.relative_to(workspace))], cwd=workspace, env=environment,
                    capture_output=True, text=True, check=False)
                events = [parse(line) for line in process.stdout.splitlines()]
                errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"]
                terminals = [e["test_run"]["status"] for e in events if e.get("type") == "test_run" and "status" in e["test_run"]]
                summaries = [e["test_summary"] for e in events if e.get("type") == "test_summary"]
                require(process.returncode == 1 and not process.stderr.strip() and errors
                    and all(e.get("summary") == summary for e in errors)
                    and any(reason in e.get("detail", "") for e in errors), "child_security_rejection:" + name)
                require(not any(e.get("type") == "test_plan" for e in events) and len(terminals) == 1
                    and terminals[0] in {"fail", "error"}, "child_rejected_plan:" + name)
                require(len(summaries) == 1 and summaries[0].get("status") in {"fail", "error"}
                    and summaries[0].get("passed") == summaries[0].get("skipped") == 0
                    and summaries[0].get("failed", 0) + summaries[0].get("errored", 0) == 1, "child_failed_summary:" + name)
                security.append({"case": name, "rejected": True, "terraform_exit": 1, "successful_plans": 0})
        print(json.dumps({"status": "passed", "aws_api_calls": 0, "required_input_rejections": len(results),
            "security_input_rejections": len(security), "cases": results, "security_cases": security}, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("Required network input verification failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
