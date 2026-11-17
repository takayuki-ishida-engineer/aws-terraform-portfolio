#!/usr/bin/env python3
"""Offline self-tests for the local workflow preflight and run wrapper.

Fake terraform and aws executables stand in for the real tools, so these tests
make no AWS call and need no credentials. A temporary Git repository supplies
the ignore and tracking checks.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402
import run  # noqa: E402

FAKE_TERRAFORM = textwrap.dedent("""\
    #!/usr/bin/env python3
    import base64, json, os, sys
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps(["terraform"] + sys.argv[1:]) + "\\n")
    arguments = [a for a in sys.argv[1:] if not a.startswith("-chdir=")]
    if arguments[0] == "console":
        sys.stdin.read()
        values = open(os.environ["FAKE_VALUES"]).read().encode()
        print('"' + base64.b64encode(values).decode() + '"')
    elif arguments[0] == "plan":
        chdir = [a for a in sys.argv[1:] if a.startswith("-chdir=")][0].split("=", 1)[1]
        out = [a for a in arguments if a.startswith("-out=")][0].split("=", 1)[1]
        open(os.path.join(chdir, out), "w").write("fake plan")
    sys.exit(int(os.environ.get("FAKE_TF_EXIT_" + arguments[0].upper(), "0")))
    """)

FAKE_AWS = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps(["aws"] + sys.argv[1:]) + "\\n")
    responses = json.load(open(os.environ["FAKE_AWS"]))
    key = " ".join(sys.argv[1:3])
    if sys.argv[1:3] == ["eks", "describe-addon-versions"]:
        key += " " + sys.argv[sys.argv.index("--addon-name") + 1]
    if key not in responses:
        sys.exit(254)
    print(json.dumps(responses[key]))
    """)

ACCOUNT = "444455556666"
NETWORK_REFERENCE = {
    "interface_version": 1, "routing_mode": "per_az", "vpc_id": "vpc-0a1b2c3d4e5f60718", "vpc_cidr": "10.40.0.0/16",
    "scope": {"environment": "dev", "partition": "aws", "region": "ca-central-1", "account_id": ACCOUNT},
    "private_subnet_ids": {"private1": "subnet-0a1b2c3d4e5f60711", "private2": "subnet-0a1b2c3d4e5f60712"},
    "public_subnet_ids": {"public1": "subnet-0a1b2c3d4e5f60713", "public2": "subnet-0a1b2c3d4e5f60714"},
    "subnet_azs": {"private": {"private1": "ca-central-1a", "private2": "ca-central-1b"}},
    "private_route_table_ids_by_subnet": {"private1": "rtb-0a1b2c3d4e5f60711", "private2": "rtb-0a1b2c3d4e5f60712"},
    "public_route_table_id": "rtb-0a1b2c3d4e5f60713", "nat_gateway_ids_by_az": {"ca-central-1a": "nat-0a1b2c3d4e5f60711"},
}
PLATFORM = {
    "project": "acme", "aws_account_id": ACCOUNT, "bootstrap_admin_role_arn": f"arn:aws:iam::{ACCOUNT}:role/eks-admin",
    "network_reference": NETWORK_REFERENCE, "kubernetes_version": "1.35",
    "addon_versions": {"vpc_cni": "v1.23.1-eksbuild.1", "coredns": "v1.14.3-eksbuild.16", "kube_proxy": "v1.35.3-eksbuild.25"},
    "node_group": {"ami_type": "AL2023_x86_64_STANDARD", "release_version": "1.35.9-20261112"},
}
AWS_OK = {
    "sts get-caller-identity": {"Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/operator/session", "UserId": "AROAEXAMPLE:session"},
    "eks describe-addon-versions vpc-cni": {"addons": [{"addonName": "vpc-cni", "addonVersions": [{"addonVersion": "v1.23.1-eksbuild.1", "compatibilities": [{"clusterVersion": "1.35"}]}]}]},
    "eks describe-addon-versions coredns": {"addons": [{"addonName": "coredns", "addonVersions": [{"addonVersion": "v1.14.3-eksbuild.16", "compatibilities": [{"clusterVersion": "1.35"}]}]}]},
    "eks describe-addon-versions kube-proxy": {"addons": [{"addonName": "kube-proxy", "addonVersions": [{"addonVersion": "v1.35.3-eksbuild.25", "compatibilities": [{"clusterVersion": "1.35"}]}]}]},
    "ssm get-parameter": {"Parameter": {"Value": "ami-0123abcd4567ef890"}},
}
LOCAL_PLATFORM = textwrap.dedent(f"""\
    project                  = "acme"
    aws_account_id           = "{ACCOUNT}"
    bootstrap_admin_role_arn = "arn:aws:iam::{ACCOUNT}:role/eks-admin"
    network_reference        = {{}}
    """)


class Workspace:
    """A temporary Git repository with one fake root and fake tool executables."""

    def __init__(self, root_name="platform", values=PLATFORM, local=LOCAL_PLATFORM, aws=AWS_OK):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.services = base / "repo/infra/services/dev/ca-central-1"
        self.root = self.services / root_name
        self.root.mkdir(parents=True)
        (base / "repo/.gitignore").write_text("*.tfvars\n*.tfplan\n!terraform.tfvars\n")
        (self.root / "variables.tf").write_text("".join(f'variable "{name}" {{}}\n' for name in values))
        subprocess.run(["git", "init", "-q", str(base / "repo")], check=True)
        if local is not None:
            (self.root / "local.auto.tfvars").write_text(local)
        self.log = base / "calls.jsonl"
        self.log.touch()
        (base / "values.json").write_text(json.dumps(values))
        (base / "aws.json").write_text(json.dumps(aws))
        self.terraform = self.tool(base / "terraform", FAKE_TERRAFORM)
        self.aws = self.tool(base / "aws", FAKE_AWS)
        self.env = {"PATH": os.environ["PATH"], "FAKE_LOG": str(self.log), "FAKE_VALUES": str(base / "values.json"),
                    "FAKE_AWS": str(base / "aws.json")}

    @staticmethod
    def tool(path, source):
        path.write_text(source)
        path.chmod(0o755)
        return str(path)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def close(self):
        self.temporary.cleanup()


class PreflightTests(unittest.TestCase):
    def check(self, workspace, root_name="platform", live=False, env=None):
        return preflight.preflight(root_name, workspace.terraform, workspace.aws, live=live,
                                   services=workspace.services, env=env or workspace.env)

    def test_effective_values_round_trip(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        self.assertEqual(preflight.effective_values(workspace.root, workspace.terraform, workspace.env), PLATFORM)

    def test_ready_root_passes_offline_and_live(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        self.assertEqual(self.check(workspace)["findings"], [])
        report = self.check(workspace, live=True)
        self.assertEqual((report["status"], report["findings"]), ("passed", []))
        aws_calls = [call[1:3] for call in workspace.calls() if call[0] == "aws"]
        self.assertTrue(aws_calls and all(tuple(call) in preflight.READ_ONLY_AWS for call in aws_calls))
        parameter = [call for call in workspace.calls() if call[1:3] == ["ssm", "get-parameter"]][0]
        self.assertIn("/aws/service/eks/optimized-ami/1.35/amazon-linux-2023/x86_64/standard/"
                      "amazon-eks-node-al2023-x86_64-standard-1.35-v20261112/image_id", parameter)

    def test_missing_local_file_is_refused(self):
        workspace = Workspace(local=None)
        self.addCleanup(workspace.close)
        self.assertIn("local_tfvars_missing", self.check(workspace)["findings"])

    def test_tracked_local_file_is_refused(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        subprocess.run(["git", "-C", str(workspace.root), "add", "-f", "local.auto.tfvars"], check=True)
        self.assertIn("local_tfvars_tracked", self.check(workspace)["findings"])

    def test_unignored_local_file_is_refused(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        (workspace.services.parents[3] / ".gitignore").write_text("")
        self.assertIn("local_tfvars_not_ignored", self.check(workspace)["findings"])

    def test_every_environment_input_must_be_set_locally(self):
        workspace = Workspace(local='project = "acme"\n')
        self.addCleanup(workspace.close)
        findings = self.check(workspace)["findings"]
        for key in ("aws_account_id", "bootstrap_admin_role_arn", "network_reference"):
            self.assertIn("local_value_missing:" + key, findings)

    def test_committed_placeholders_are_refused(self):
        committed = dict(PLATFORM, project="project", aws_account_id="123456789012",
                         bootstrap_admin_role_arn="arn:aws:iam::123456789012:role/example-role",
                         network_reference=dict(NETWORK_REFERENCE, vpc_id="vpc-0123456789abcdef0",
                                                scope=dict(NETWORK_REFERENCE["scope"], account_id="123456789012")))
        workspace = Workspace(values=committed)
        self.addCleanup(workspace.close)
        self.assertEqual(sorted(self.check(workspace)["findings"]), sorted(
            ["placeholder:project", "placeholder:aws_account_id", "placeholder:bootstrap_admin_role_arn",
             "placeholder:network_reference"]))

    def test_unedited_example_values_are_refused(self):
        example = dict(PLATFORM, project="myproj", aws_account_id="111122223333",
                       bootstrap_admin_role_arn="arn:aws:iam::111122223333:role/your-eks-admin-role",
                       network_reference=dict(NETWORK_REFERENCE, vpc_id="vpc-..."))
        workspace = Workspace(values=example)
        self.addCleanup(workspace.close)
        findings = self.check(workspace)["findings"]
        self.assertTrue({"placeholder:project", "placeholder:aws_account_id", "placeholder:bootstrap_admin_role_arn",
                         "placeholder:network_reference"} <= set(findings))

    def test_placeholder_patterns_per_root(self):
        cases = {
            "api": {"callback_urls": ["https://app.example.com/callback"], "logout_urls": ["https://app.your-domain.test/logout"],
                    "default_redirect_uri": "https://app.example.org/callback"},
            "serverless-api": {"artifact_object_version": "placeholder-object-version"},
        }
        for root_name, values in cases.items():
            findings = preflight.value_findings(root_name, dict(values, project="acme", aws_account_id=ACCOUNT))
            self.assertEqual(sorted(findings), sorted("placeholder:" + key for key in values), root_name)
        clean = {"project": "acme", "aws_account_id": ACCOUNT, "callback_urls": ["https://app.acme.dev/callback"],
                 "logout_urls": ["https://app.acme.dev/logout"], "default_redirect_uri": "https://app.acme.dev/callback"}
        self.assertEqual(preflight.value_findings("api", clean), [])
        self.assertEqual(preflight.value_findings("serverless-api", {"project": "acme", "aws_account_id": ACCOUNT,
                         "artifact_object_version": "3HL4kqtJlcpXroDTDmJ.rmSp123456789012"}), [])

    def test_other_account_in_reference_is_refused(self):
        foreign = dict(PLATFORM, bootstrap_admin_role_arn="arn:aws:iam::999988887777:role/eks-admin")
        self.assertEqual(preflight.value_findings("platform", foreign), ["account_mismatch:bootstrap_admin_role_arn"])

    def test_live_refusals(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        self.assertEqual(self.check(workspace, live=True, env=dict(workspace.env, GITHUB_ACTIONS="true"))["findings"], ["live_refused_in_ci"])
        self.assertEqual(self.check(workspace, live=True, env=dict(workspace.env, CI="true"))["findings"], ["live_refused_in_ci"])
        self.assertEqual(self.check(workspace, live=True, env=dict(workspace.env, AWS_ENDPOINT_URL_STS="https://localhost:4566"))["findings"],
                         ["live_refused_endpoint_override"])
        self.assertFalse([call for call in workspace.calls() if call[0] == "aws"])

    def test_live_account_and_catalog_failures(self):
        scenarios = [
            (dict(AWS_OK, **{"sts get-caller-identity": {"Account": "999988887777"}}), ["caller_account_mismatch"]),
            (dict(AWS_OK, **{"sts get-caller-identity": {"Account": "000000000000"}}), ["caller_account_synthetic"]),
            ({k: v for k, v in AWS_OK.items() if k != "sts get-caller-identity"}, ["caller_identity_unavailable"]),
            (dict(AWS_OK, **{"eks describe-addon-versions coredns": {"addons": [{"addonName": "coredns", "addonVersions": [
                {"addonVersion": "v1.14.3-eksbuild.16", "compatibilities": [{"clusterVersion": "1.36"}]}]}]}}), ["addon_version_unavailable:coredns"]),
            ({k: v for k, v in AWS_OK.items() if k != "ssm get-parameter"}, ["node_release_unavailable"]),
        ]
        for responses, expected in scenarios:
            workspace = Workspace(aws=responses)
            self.addCleanup(workspace.close)
            self.assertEqual(self.check(workspace, live=True)["findings"], expected)

    def test_live_is_skipped_after_offline_findings(self):
        workspace = Workspace(local=None)
        self.addCleanup(workspace.close)
        self.assertIn("live_skipped_offline_findings", self.check(workspace, live=True)["findings"])
        self.assertFalse([call for call in workspace.calls() if call[0] == "aws"])

    def test_only_read_only_aws_commands_are_allowed(self):
        with self.assertRaises(preflight.PreflightError):
            preflight.run_aws("aws", ["eks", "delete-cluster", "--name", "x"], {})

    def test_console_failure_stops(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        with self.assertRaises(preflight.PreflightError):
            self.check(workspace, env=dict(workspace.env, FAKE_TF_EXIT_CONSOLE="1", FAKE_VALUES="/nonexistent"))


class RunTests(unittest.TestCase):
    def operate(self, workspace, command, answer="platform", env=None):
        messages = []
        code = run.run("platform", command, workspace.terraform, workspace.aws, services=workspace.services,
                       env=env or workspace.env, confirm=lambda _prompt: answer, out=messages.append)
        terraform = [[a for a in call[1:] if not a.startswith("-chdir=")] for call in workspace.calls() if call[0] == "terraform"]
        return code, [call[0] for call in terraform], terraform, messages

    def test_apply_runs_exact_saved_plan_after_confirmation(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        code, steps, calls, _ = self.operate(workspace, "apply")
        self.assertEqual((code, steps), (0, ["init", "console", "plan", "apply"]))
        self.assertIn("-lockfile=readonly", calls[0])
        self.assertEqual(calls[3], ["apply", "-input=false", run.PLAN_FILE])
        self.assertFalse((workspace.root / run.PLAN_FILE).exists())

    def test_destroy_plans_destroy(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        code, steps, calls, _ = self.operate(workspace, "destroy")
        self.assertEqual((code, steps), (0, ["init", "console", "plan", "apply"]))
        self.assertIn("-destroy", calls[2])

    def test_plan_never_applies(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        code, steps, _, _ = self.operate(workspace, "plan")
        self.assertEqual((code, steps), (0, ["init", "console", "plan"]))
        self.assertFalse((workspace.root / run.PLAN_FILE).exists())

    def test_wrong_confirmation_changes_nothing(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        code, steps, _, messages = self.operate(workspace, "apply", answer="yes")
        self.assertEqual((code, steps), (1, ["init", "console", "plan"]))
        self.assertIn("Not confirmed; nothing was changed.", messages)
        self.assertFalse((workspace.root / run.PLAN_FILE).exists())

    def test_failed_preflight_stops_before_plan(self):
        workspace = Workspace(local=None)
        self.addCleanup(workspace.close)
        code, steps, _, _ = self.operate(workspace, "apply")
        self.assertEqual((code, steps), (1, ["init", "console"]))

    def test_ci_is_refused_before_any_tool(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        code, steps, _, _ = self.operate(workspace, "apply", env=dict(workspace.env, GITHUB_ACTIONS="true"))
        self.assertEqual((code, steps), (1, []))
        self.assertEqual(workspace.calls(), [])

    def test_unignored_plan_path_is_refused(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        (workspace.services.parents[3] / ".gitignore").write_text("*.tfvars\n")
        code, steps, _, _ = self.operate(workspace, "plan")
        self.assertEqual((code, steps), (1, []))

    def test_failed_plan_removes_partial_plan_and_stops(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        with self.assertRaises(preflight.PreflightError):
            self.operate(workspace, "apply", env=dict(workspace.env, FAKE_TF_EXIT_PLAN="1"))
        self.assertFalse((workspace.root / run.PLAN_FILE).exists())
        self.assertNotIn("apply", [call[1] for call in workspace.calls() if call[0] == "terraform" and len(call) > 1
                                   and not call[1].startswith("-chdir=")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
