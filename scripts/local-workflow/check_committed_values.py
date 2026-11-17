#!/usr/bin/env python3
"""CI validation of the committed DEV values and the local workflow preflight.

For each DEV root, offline and credential-free:

1. Mock plan with the committed values. The root's own native test header
   (mock provider and computed-attribute overrides) is reused without its
   ``variables`` blocks, so every input comes from the committed
   ``terraform.tfvars`` and ``features.auto.tfvars``. This proves the committed
   values satisfy every variable validation and plan under mocks.
2. Preflight refusal. In a temporary sibling copy (committed files only,
   initialized with the local backend and the committed lock), the offline
   preflight must report exactly a missing ``local.auto.tfvars`` and a
   placeholder for every environment-specific input.
3. Preflight acceptance. A synthetic, non-placeholder ``local.auto.tfvars`` is
   added to the copy; the preflight must pass and Terraform must report the
   local values as effective, proving the override order.

The live preflight is never run here. No AWS API is called; the synthetic
account and identifiers are not real.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402

ACCOUNT = "444455556666"
HEADERS = {
    "network": "network.tftest.hcl",
    "platform": "platform.tftest.hcl",
    "serverless-api": "root_integration.tftest.hcl",
    "api": "auth.tftest.hcl",
}
NETWORK_REFERENCE = """{
  interface_version = 1
  scope             = { environment = "dev", partition = "aws", region = "ca-central-1", account_id = "%s" }
  routing_mode      = "per_az"
  vpc_id            = "vpc-0a1b2c3d4e5f60718"
  vpc_cidr          = "10.40.0.0/16"
  private_subnet_ids = { private1 = "subnet-0a1b2c3d4e5f60711", private2 = "subnet-0a1b2c3d4e5f60712" }
  public_subnet_ids  = { public1 = "subnet-0a1b2c3d4e5f60713", public2 = "subnet-0a1b2c3d4e5f60714" }
  subnet_azs         = { private = { private1 = "ca-central-1a", private2 = "ca-central-1b" } }
  private_route_table_ids_by_subnet = { private1 = "rtb-0a1b2c3d4e5f60711", private2 = "rtb-0a1b2c3d4e5f60712" }
  public_route_table_id = "rtb-0a1b2c3d4e5f60713"
  nat_gateway_ids_by_az = { "ca-central-1a" = "nat-0a1b2c3d4e5f60711" }
}""" % ACCOUNT
SYNTHETIC_LOCAL = {
    "network": {},
    "platform": {"bootstrap_admin_role_arn": f'"arn:aws:iam::{ACCOUNT}:role/ci-eks-admin"', "network_reference": NETWORK_REFERENCE},
    "serverless-api": {"artifact_object_version": '"Ci3HL4kqtJlcpXroDTDmJrmSpXd3dIbrHY"'},
    "api": {"callback_urls": '["https://app.ci-check.dev/callback"]', "logout_urls": '["https://app.ci-check.dev/logout"]',
            "default_redirect_uri": '"https://app.ci-check.dev/callback"'},
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def clean_environment(extra=None):
    env = {key: val for key, val in os.environ.items() if not key.startswith(("AWS_", "TF_VAR_", "TF_CLI_ARGS", "TF_DATA_DIR"))}
    env.update(TF_INPUT="0", TF_IN_AUTOMATION="1", AWS_EC2_METADATA_DISABLED="true",
               AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null")
    env.update(extra or {})
    return env


def committed_plan(name, root, terraform):
    """Mock plan of the root with only the committed values as inputs."""
    header = (root / "tests" / HEADERS[name]).read_text(encoding="utf-8").split('\nrun "', 1)[0]
    header, removed = re.subn(r"(?m)^variables \{[^}]*\}\n", "", header)
    require("mock_provider" in header and "variables {" not in header, "committed_header:" + name)
    # The native headers give computed attributes the synthetic test identity
    # (account 000000000000, project "test"). Re-key them to the committed
    # placeholder identity so the root's identity postconditions see one account.
    committed = (root / "terraform.tfvars").read_text(encoding="utf-8")
    project = re.search(r'(?m)^project\s*=\s*"([a-z0-9]+)"', committed)
    account = re.search(r'(?m)^aws_account_id\s*=\s*"([0-9]{12})"', committed)
    require(project and account, "committed_identity:" + name)
    for old, new in (("000000000000", account.group(1)), ("test-dev", project.group(1) + "-dev"),
                     ("/test/dev/", "/" + project.group(1) + "/dev/"), ('project = "test"', 'project = "' + project.group(1) + '"')):
        header = header.replace(old, new)
    with tempfile.TemporaryDirectory(prefix=".committed-values-", dir=root / "tests") as temporary:
        folder = Path(temporary)
        (folder / "committed.tftest.hcl").write_text(header + '\nrun "committed_values" {\n  command = plan\n}\n', encoding="utf-8")
        process = subprocess.run([terraform, "test", "-json", "-no-color", "-test-directory=" + str(folder.relative_to(root))],
                                 cwd=root, env=clean_environment(), capture_output=True, text=True, check=False)
    events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith("{")]
    summaries = [event["test_summary"] for event in events if event.get("type") == "test_summary"]
    runs = [event["test_run"] for event in events if event.get("type") == "test_run" and "status" in event.get("test_run", {})]
    errors = [event["diagnostic"].get("summary", "") + ": " + event["diagnostic"].get("detail", "")[:300]
              for event in events if event.get("type") == "diagnostic" and event["diagnostic"].get("severity") == "error"]
    require(process.returncode == 0 and not process.stderr.strip()
            and summaries == [{"status": "pass", "passed": 1, "failed": 0, "errored": 0, "skipped": 0}]
            and [(run["run"], run["status"]) for run in runs] == [("committed_values", "pass")],
            "committed_plan_failed:" + name + ":" + "; ".join(errors or [process.stderr.strip()[:300]]))
    return {"mock_plan": "pass", "header_variable_blocks_removed": removed}


def preflight_copy(name, root, terraform):
    """Run the offline preflight against a committed-files copy, then with local values."""
    with tempfile.TemporaryDirectory(prefix="." + name + "-committed-", dir=root.parent) as temporary:
        copy = Path(temporary)
        for source in list(root.glob("*.tf")) + [root / "terraform.tfvars", root / "features.auto.tfvars", root / ".terraform.lock.hcl"]:
            if source.is_file():
                shutil.copy2(source, copy / source.name)
        env = clean_environment({"TF_DATA_DIR": str(copy / ".terraform")})
        init = subprocess.run([terraform, "init", "-input=false", "-lockfile=readonly", "-no-color"], cwd=copy, env=env,
                              capture_output=True, text=True, check=False)
        require(init.returncode == 0, "copy_init_failed:" + name + ":" + init.stderr.strip()[:300])
        refused = preflight.preflight(name, terraform, live=False, env=env, root=copy)
        expected = ["local_tfvars_missing"] + ["placeholder:" + key for key in preflight.ENVIRONMENT_INPUTS[name]]
        require(refused["status"] == "failed" and refused["findings"] == expected,
                "committed_values_not_refused:" + name + ":" + ",".join(refused["findings"]))
        local = {"project": '"ciproj"', "aws_account_id": f'"{ACCOUNT}"', **SYNTHETIC_LOCAL[name]}
        require(set(local) == set(preflight.ENVIRONMENT_INPUTS[name]), "synthetic_coverage:" + name)
        (copy / preflight.LOCAL_FILE).write_text("".join(f"{key} = {value}\n" for key, value in local.items()), encoding="utf-8")
        accepted = preflight.preflight(name, terraform, live=False, env=env, root=copy)
        require(accepted["status"] == "passed" and accepted["findings"] == [],
                "synthetic_values_refused:" + name + ":" + ",".join(accepted["findings"]))
        values = preflight.effective_values(copy, terraform, env)
        require(values["project"] == "ciproj" and values["aws_account_id"] == ACCOUNT, "local_override_not_effective:" + name)
    return {"committed_values_refused": expected, "synthetic_local_values": "passed", "local_override_effective": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("roots", nargs="*", choices=list(HEADERS), help="default: all DEV roots")
    args = parser.parse_args()
    reports = []
    try:
        for name in args.roots or list(HEADERS):
            root = preflight.root_directory(name)
            require((root / ".terraform").is_dir(), "root_not_initialized:" + name)
            require(not (root / preflight.LOCAL_FILE).exists(), "unexpected_local_tfvars_in_checkout:" + name)
            reports.append({"root": name, **committed_plan(name, root, args.terraform), **preflight_copy(name, root, args.terraform)})
    except (ValueError, KeyError, OSError, preflight.PreflightError) as error:
        print("Committed-values validation failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "aws_api_calls": 0, "roots": reports,
                      "limitations": ["Mock plans and placeholder checks only; real values, real AWS reachability "
                                      "and the live preflight are verified on the operator workstation."]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
