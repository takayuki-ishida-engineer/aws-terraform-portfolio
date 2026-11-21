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
import eks_tunnel  # noqa: E402
import empty_bucket  # noqa: E402
import handoff  # noqa: E402
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
    elif arguments[0] == "output":
        chdir = [a for a in sys.argv[1:] if a.startswith("-chdir=")][0].split("=", 1)[1]
        outputs = json.load(open(os.environ["FAKE_OUTPUTS"])).get(os.path.basename(chdir), {})
        if arguments[-1] not in outputs:
            sys.exit(1)
        print(json.dumps(outputs[arguments[-1]]))
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
    "node_https_egress_prefix_list_ids": ["pl-7da54014"],
}
AWS_OK = {
    "sts get-caller-identity": {"Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/operator/session", "UserId": "AROAEXAMPLE:session"},
    "eks describe-addon-versions vpc-cni": {"addons": [{"addonName": "vpc-cni", "addonVersions": [{"addonVersion": "v1.23.1-eksbuild.1", "compatibilities": [{"clusterVersion": "1.35"}]}]}]},
    "eks describe-addon-versions coredns": {"addons": [{"addonName": "coredns", "addonVersions": [{"addonVersion": "v1.14.3-eksbuild.16", "compatibilities": [{"clusterVersion": "1.35"}]}]}]},
    "eks describe-addon-versions kube-proxy": {"addons": [{"addonName": "kube-proxy", "addonVersions": [{"addonVersion": "v1.35.3-eksbuild.25", "compatibilities": [{"clusterVersion": "1.35"}]}]}]},
    "ssm get-parameter": {"Parameter": {"Value": "ami-0123abcd4567ef890"}},
    "s3api get-bucket-versioning": {"Status": "Enabled"},
    "ec2 describe-managed-prefix-lists": {"PrefixLists": [{"PrefixListId": "pl-7da54014", "PrefixListName": "com.amazonaws.ca-central-1.s3"}]},
    "s3api get-public-access-block": {"PublicAccessBlockConfiguration": {
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True}},
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
        (base / "repo/.gitignore").write_text("*.tfvars\n*.tfplan\n!terraform.tfvars\n*_override.tf\n*.tfbackend\n")
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

    def use_backend(self, project="acme", root_name="platform", override=None, config=None):
        """Install the repository's backend example files with the project filled in."""
        example = preflight.SERVICES / "network"
        (self.root / preflight.BACKEND_OVERRIDE).write_text(
            override if override is not None else (example / "backend_override.tf.example").read_text())
        text = (example / "backend.s3.tfbackend.example").read_text()
        text = text.replace('"project-dev-s3-tfstate"', f'"{project}-dev-s3-tfstate"').replace(
            '"project/dev/ca-central-1/network/', f'"{project}/dev/ca-central-1/{root_name}/')
        (self.root / preflight.BACKEND_CONFIG).write_text(config if config is not None else text)

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
            (dict(AWS_OK, **{"ec2 describe-managed-prefix-lists": {"PrefixLists": [{"PrefixListId": "pl-0123abcd"}]}}), ["s3_prefix_list_mismatch"]),
            ({k: v for k, v in AWS_OK.items() if k != "ec2 describe-managed-prefix-lists"}, ["s3_prefix_list_mismatch"]),
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


class BackendTests(unittest.TestCase):
    def check(self, workspace, live=False, env=None):
        return preflight.preflight("platform", workspace.terraform, workspace.aws, live=live,
                                   services=workspace.services, env=env or workspace.env)["findings"]

    def test_repository_examples_pass_once_filled_in(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend()
        self.assertEqual(self.check(workspace), [])
        self.assertEqual(self.check(workspace, live=True), [])
        buckets = [call for call in workspace.calls() if call[1:2] == ["s3api"]]
        self.assertEqual({tuple(call[1:3]) for call in buckets}, {("s3api", "get-bucket-versioning"), ("s3api", "get-public-access-block")})
        self.assertTrue(all("acme-dev-s3-tfstate" in call for call in buckets))

    def test_unedited_examples_are_refused(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend(project="project")
        self.assertEqual(self.check(workspace), ["backend_bucket_mismatch", "backend_key_mismatch"])
        placeholder = Workspace(values=dict(PLATFORM, project="project"))
        self.addCleanup(placeholder.close)
        placeholder.use_backend(project="project")
        self.assertEqual(self.check(placeholder), ["placeholder:project", "placeholder:backend"])

    def test_backend_setting_findings(self):
        good = 'bucket = "acme-dev-s3-tfstate"\nkey = "acme/dev/ca-central-1/platform/terraform.tfstate"\nregion = "ca-central-1"\nuse_lockfile = true\nencrypt = true\n'
        cases = {
            good.replace("platform/", "network/"): ["backend_key_mismatch"],
            good.replace('"acme-dev-s3-tfstate"', '"other-dev-s3-tfstate"'): ["backend_bucket_mismatch"],
            good.replace('region = "ca-central-1"', 'region = "us-east-1"'): ["backend_region_mismatch"],
            good.replace("use_lockfile = true", "use_lockfile = false"): ["backend_lockfile_disabled"],
            good.replace("encrypt = true", "encrypt = false"): ["backend_encryption_disabled"],
            good + 'profile = "admin"\n': ["backend_config_settings"],
            good.replace("use_lockfile = true\n", ""): ["backend_config_settings"],
            good + "role_arn = arn\n": ["backend_config_unparsable"],
            good + 'bucket = "acme-dev-s3-tfstate"\n': ["backend_config_unparsable"],
        }
        for config, expected in cases.items():
            workspace = Workspace()
            self.addCleanup(workspace.close)
            workspace.use_backend(config=config)
            self.assertEqual(self.check(workspace), expected, config)

    def test_override_must_stay_empty(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend(override='terraform {\n  backend "s3" {\n    bucket = "x"\n  }\n}\n')
        self.assertEqual(self.check(workspace), ["backend_override_unexpected_content"])

    def test_incomplete_backend_files(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend()
        (workspace.root / preflight.BACKEND_CONFIG).unlink()
        self.assertEqual(self.check(workspace), ["backend_config_missing"])
        workspace.use_backend()
        (workspace.root / preflight.BACKEND_OVERRIDE).unlink()
        self.assertEqual(self.check(workspace), ["backend_config_without_override"])

    def test_tracked_backend_files_are_refused(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend()
        subprocess.run(["git", "-C", str(workspace.root), "add", "-f", preflight.BACKEND_CONFIG, preflight.BACKEND_OVERRIDE], check=True)
        self.assertEqual(sorted(self.check(workspace)), ["backend_config_tracked", "backend_override_tracked"])

    def test_bootstrap_root_stays_local(self):
        values = {"project": "acme", "aws_account_id": ACCOUNT, "tags": {}}
        workspace = Workspace(root_name="tfstate", values=values, local=f'project = "acme"\naws_account_id = "{ACCOUNT}"\n')
        self.addCleanup(workspace.close)
        self.assertEqual(preflight.preflight("tfstate", workspace.terraform, services=workspace.services, env=workspace.env)["findings"], [])
        workspace.use_backend(root_name="tfstate")
        self.assertEqual(preflight.preflight("tfstate", workspace.terraform, services=workspace.services, env=workspace.env)["findings"],
                         ["bootstrap_backend_must_stay_local"])

    def test_live_state_bucket_findings(self):
        scenarios = [
            (dict(AWS_OK, **{"s3api get-bucket-versioning": {"Status": "Suspended"}}), ["state_bucket_versioning_not_enabled"]),
            (dict(AWS_OK, **{"s3api get-bucket-versioning": {}}), ["state_bucket_versioning_not_enabled"]),
            ({k: v for k, v in AWS_OK.items() if k != "s3api get-bucket-versioning"}, ["state_bucket_unavailable"]),
            (dict(AWS_OK, **{"s3api get-public-access-block": {"PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": False, "RestrictPublicBuckets": True}}}),
             ["state_bucket_public_access_not_blocked"]),
        ]
        for responses, expected in scenarios:
            workspace = Workspace(aws=responses)
            self.addCleanup(workspace.close)
            workspace.use_backend()
            self.assertEqual(self.check(workspace, live=True), expected)

    def test_local_value_reads_plain_strings_only(self):
        workspace = Workspace(local='project = "acme" # mine\naws_account_id = var.x\n')
        self.addCleanup(workspace.close)
        self.assertEqual(preflight.local_value(workspace.root, "project"), "acme")
        self.assertIsNone(preflight.local_value(workspace.root, "aws_account_id"))


class AutomationRefusalTests(unittest.TestCase):
    def test_refusal_codes(self):
        self.assertEqual(preflight.automation_refusal({}), None)
        self.assertEqual(preflight.automation_refusal({"GITHUB_ACTIONS": "true"}), "live_refused_in_ci")
        self.assertEqual(preflight.automation_refusal({"CLAUDE_CODE_REMOTE": "true"}), "live_refused_in_cloud_session")
        self.assertEqual(preflight.automation_refusal({"CODEX_SANDBOX": "seatbelt"}), "live_refused_in_cloud_session")
        for variable in preflight.CREDENTIAL_VARIABLES:
            self.assertEqual(preflight.automation_refusal({variable: "proxy-injected"}), "live_refused_placeholder_credentials")
        self.assertEqual(preflight.automation_refusal({"AWS_ENDPOINT_URL": "https://localhost"}), "live_refused_endpoint_override")

    def test_live_preflight_refused_in_cloud_session_without_aws_calls(self):
        for extra in ({"CLAUDE_CODE_REMOTE": "true"}, {"AWS_ACCESS_KEY_ID": "proxy-injected", "AWS_SECRET_ACCESS_KEY": "proxy-injected"}):
            workspace = Workspace()
            self.addCleanup(workspace.close)
            report = preflight.preflight("platform", workspace.terraform, workspace.aws, live=True, services=workspace.services,
                                         env=dict(workspace.env, **extra))
            self.assertEqual(len(report["findings"]), 1)
            self.assertTrue(report["findings"][0].startswith("live_refused_"))
            self.assertFalse([call for call in workspace.calls() if call[0] == "aws"])


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

    def test_cloud_session_is_refused_before_any_tool(self):
        for extra in ({"CLAUDE_CODE_REMOTE": "true"}, {"AWS_ACCESS_KEY_ID": "proxy-injected"}):
            workspace = Workspace()
            self.addCleanup(workspace.close)
            code, steps, _, messages = self.operate(workspace, "apply", env=dict(workspace.env, **extra))
            self.assertEqual((code, steps, workspace.calls()), (1, [], []))
            self.assertTrue(messages[0].startswith("Refused (live_refused_"))

    def test_every_root_is_refused_in_ci_and_cloud_before_any_tool(self):
        self.assertIn("registry", preflight.ENVIRONMENT_INPUTS)
        for root_name in sorted(preflight.ENVIRONMENT_INPUTS):
            for extra, code_name in (({"GITHUB_ACTIONS": "true"}, "live_refused_in_ci"),
                                     ({"CLAUDE_CODE_REMOTE": "true"}, "live_refused_in_cloud_session")):
                workspace = Workspace(root_name=root_name)
                self.addCleanup(workspace.close)
                messages = []
                code = run.run(root_name, "apply", workspace.terraform, workspace.aws, services=workspace.services,
                               env=dict(workspace.env, **extra), confirm=lambda _prompt, name=root_name: name,
                               out=messages.append)
                self.assertEqual((root_name, code, workspace.calls()), (root_name, 1, []))
                self.assertTrue(messages[0].startswith("Refused (" + code_name + ")"))

    def test_s3_backend_init_passes_backend_settings(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend()
        code, steps, calls, _ = self.operate(workspace, "plan")
        self.assertEqual((code, steps), (0, ["init", "console", "plan"]))
        self.assertIn("-backend-config=" + preflight.BACKEND_CONFIG, calls[0])

    def test_migrate_state_checks_before_moving_state(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        workspace.use_backend()
        code, steps, calls, messages = self.operate(workspace, "migrate-state")
        self.assertEqual((code, steps), (0, ["init", "console"]))
        self.assertEqual(calls[0], ["init", "-lockfile=readonly", "-backend-config=" + preflight.BACKEND_CONFIG, "-migrate-state"])
        order = [call[1] if call[0] == "aws" else "terraform" for call in workspace.calls()]
        self.assertEqual(order[:4], ["sts", "s3api", "s3api", "terraform"])
        self.assertTrue(messages[-1].startswith("Migrated; preflight passed"))

    def test_migrate_state_refusals_change_nothing(self):
        scenarios = [
            ("no_override", None, AWS_OK, "Refused: copy backend_override.tf.example"),
            ("versioning_off", "acme", dict(AWS_OK, **{"s3api get-bucket-versioning": {"Status": "Suspended"}}), "state_bucket_versioning_not_enabled"),
            ("wrong_account", "acme", dict(AWS_OK, **{"sts get-caller-identity": {"Account": "999988887777"}}), "caller_account_mismatch"),
            ("placeholder_project", "project", AWS_OK, "placeholder:backend"),
        ]
        for name, project, responses, message in scenarios:
            local = LOCAL_PLATFORM.replace('"acme"', f'"{project}"') if project else LOCAL_PLATFORM
            workspace = Workspace(local=local, aws=responses)
            self.addCleanup(workspace.close)
            if project:
                workspace.use_backend(project=project)
            code, steps, _, messages = self.operate(workspace, "migrate-state")
            self.assertEqual((code, steps), (1, []), name)
            self.assertIn(message, messages[-1], name)

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


PLATFORM_OUTPUT = {"cluster_name": "acme-dev-eks", "endpoint": "https://ABCDEF0123.gr7.ca-central-1.eks.amazonaws.com",
                   "certificate_authority_data": "Q0EtREFUQQ=="}


class Services:
    """A temporary Git repository with several roots and fake tools for the hand-off scripts."""

    def __init__(self, outputs, locals_by_root, aws=AWS_OK):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.repo = base / "repo"
        self.services = self.repo / "infra/services/dev/ca-central-1"
        for name in ("network", "platform", "developer-access", "serverless-api"):
            (self.services / name).mkdir(parents=True)
        (self.repo / ".gitignore").write_text("*.tfvars\n*.tfplan\n!terraform.tfvars\n*_override.tf\n*.tfbackend\n")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        for name, text in locals_by_root.items():
            (self.services / name / "local.auto.tfvars").write_text(text)
        self.log = base / "calls.jsonl"
        self.log.touch()
        (base / "outputs.json").write_text(json.dumps(outputs))
        (base / "aws.json").write_text(json.dumps(aws))
        self.terraform = Workspace.tool(base / "terraform", FAKE_TERRAFORM)
        self.aws = Workspace.tool(base / "aws", FAKE_AWS)
        self.home = base / "home"
        self.env = {"PATH": os.environ["PATH"], "FAKE_LOG": str(self.log), "FAKE_OUTPUTS": str(base / "outputs.json"),
                    "FAKE_AWS": str(base / "aws.json")}

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def close(self):
        self.temporary.cleanup()


class HandoffTests(unittest.TestCase):
    LOCAL = f'project = "acme"\naws_account_id = "{ACCOUNT}"\nnetwork_reference = {{\n  vpc_id = "vpc-..."\n  nested = {{ a = "}}" }}\n}}\ninstance_type = "t3.micro"\n'

    def test_network_output_replaces_reference_in_both_roots(self):
        services = Services({"network": {"network": NETWORK_REFERENCE}}, {"platform": self.LOCAL, "developer-access": self.LOCAL})
        self.addCleanup(services.close)
        messages = []
        self.assertEqual(handoff.handoff_network(services.terraform, services.services, services.env, messages.append), 0)
        for name in ("platform", "developer-access"):
            text = (services.services / name / "local.auto.tfvars").read_text()
            self.assertIn('"vpc_id": "vpc-0a1b2c3d4e5f60718"', text)
            self.assertNotIn("vpc-...", text)
            self.assertTrue(text.startswith('project = "acme"') and text.rstrip().endswith('instance_type = "t3.micro"'))
            self.assertEqual(text.count("network_reference ="), 1)

    def test_reference_is_appended_when_absent(self):
        local = f'project = "acme"\naws_account_id = "{ACCOUNT}"\n'
        services = Services({"network": {"network": NETWORK_REFERENCE}}, {"platform": local, "developer-access": local})
        self.addCleanup(services.close)
        self.assertEqual(handoff.handoff_network(services.terraform, services.services, services.env, lambda _m: None), 0)
        self.assertIn("network_reference = {", (services.services / "platform/local.auto.tfvars").read_text())

    def test_other_account_and_missing_files_are_refused(self):
        other = self.LOCAL.replace(ACCOUNT, "999988887777")
        for locals_by_root in ({"platform": other, "developer-access": self.LOCAL}, {"platform": self.LOCAL}):
            services = Services({"network": {"network": NETWORK_REFERENCE}}, locals_by_root)
            self.addCleanup(services.close)
            before = {n: (services.services / n / "local.auto.tfvars").read_text() for n in locals_by_root}
            self.assertEqual(handoff.handoff_network(services.terraform, services.services, services.env, lambda _m: None), 1)
            self.assertEqual(before["platform"], (services.services / "platform/local.auto.tfvars").read_text())

    def test_unapplied_network_stops(self):
        services = Services({}, {"platform": self.LOCAL, "developer-access": self.LOCAL})
        self.addCleanup(services.close)
        with self.assertRaises(preflight.PreflightError):
            handoff.handoff_network(services.terraform, services.services, services.env, lambda _m: None)

    def test_refused_in_cloud_session(self):
        services = Services({"network": {"network": NETWORK_REFERENCE}}, {"platform": self.LOCAL, "developer-access": self.LOCAL})
        self.addCleanup(services.close)
        self.assertEqual(handoff.handoff_network(services.terraform, services.services, dict(services.env, CLAUDE_CODE_REMOTE="true"), lambda _m: None), 1)
        self.assertEqual(services.calls(), [])


class TunnelTests(unittest.TestCase):
    OUTPUTS = {"platform": {"platform": PLATFORM_OUTPUT}, "developer-access": {"developer_access": {"instance_id": "i-0123456789abcdef0", "region": "ca-central-1"}}}

    def test_kubeconfig_keeps_tls_verification_and_stores_no_token(self):
        services = Services(self.OUTPUTS, {})
        self.addCleanup(services.close)
        path = services.home / "kube.json"
        self.assertEqual(eks_tunnel.write_kubeconfig(services.terraform, str(path), 9443, "arn:aws:iam::444455556666:role/eks-admin",
                                                     services.services, services.env, lambda _m: None), 0)
        config = json.loads(path.read_text())
        cluster = config["clusters"][0]["cluster"]
        self.assertEqual(cluster["server"], "https://127.0.0.1:9443")
        self.assertEqual(cluster["tls-server-name"], "ABCDEF0123.gr7.ca-central-1.eks.amazonaws.com".lower())
        self.assertNotIn("insecure-skip-tls-verify", json.dumps(config))
        exec_args = config["users"][0]["user"]["exec"]["args"]
        self.assertEqual(exec_args[:4], ["eks", "get-token", "--cluster-name", "acme-dev-eks"])
        self.assertIn("--role-arn", exec_args)
        self.assertNotIn("token", json.dumps(config["users"][0]["user"]).replace("get-token", ""))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_kubeconfig_refuses_repository_path_and_bad_endpoint(self):
        services = Services(self.OUTPUTS, {})
        self.addCleanup(services.close)
        inside = preflight.REPOSITORY / "kubeconfig.json"
        self.assertEqual(eks_tunnel.write_kubeconfig(services.terraform, str(inside), 8443, None, services.services, services.env, lambda _m: None), 1)
        self.assertFalse(inside.exists())
        with self.assertRaises(preflight.PreflightError):
            eks_tunnel.endpoint_host({"endpoint": "https://evil.example.com"})

    def test_start_forwards_to_the_endpoint_through_the_host(self):
        services = Services(self.OUTPUTS, {})
        self.addCleanup(services.close)
        self.assertEqual(eks_tunnel.start_tunnel(services.terraform, services.aws, 8443, services.services, services.env, lambda _m: None), 254)
        call = [c for c in services.calls() if c[0] == "aws"][0]
        self.assertEqual(call[1:3], ["ssm", "start-session"])
        self.assertIn("AWS-StartPortForwardingSessionToRemoteHost", call)
        self.assertIn("host=abcdef0123.gr7.ca-central-1.eks.amazonaws.com,portNumber=443,localPortNumber=8443", call)
        self.assertIn("i-0123456789abcdef0", call)

    def test_tunnel_refused_in_ci(self):
        services = Services(self.OUTPUTS, {})
        self.addCleanup(services.close)
        self.assertEqual(eks_tunnel.start_tunnel(services.terraform, services.aws, 8443, services.services, dict(services.env, GITHUB_ACTIONS="true"), lambda _m: None), 1)
        self.assertEqual(services.calls(), [])


class PublishArtifactTests(unittest.TestCase):
    VALUES = {"project": "acme", "aws_account_id": ACCOUNT, "artifact_key": "lambda/function.zip", "artifact_object_version": "placeholder-object-version"}
    LOCAL = f'project = "acme"\naws_account_id = "{ACCOUNT}"\nartifact_object_version = "your-uploaded-object-version-id"\n'

    def workspace(self, aws=None):
        responses = dict(AWS_OK, **{"s3api put-object": {"VersionId": "3HL4kqtJlcpXroDTDmJ.rmSpXd3dIbrHY"}}) if aws is None else aws
        workspace = Workspace(root_name="serverless-api", values=self.VALUES, local=self.LOCAL, aws=responses)
        self.addCleanup(workspace.close)
        (workspace.root / "function").mkdir()
        (workspace.root / "function/function.zip").write_bytes(b"PK")
        return workspace

    def publish(self, workspace, answer="serverless-api", env=None):
        messages = []
        code = run.run("serverless-api", "publish-artifact", workspace.terraform, workspace.aws, services=workspace.services,
                       env=env or workspace.env, confirm=lambda _p: answer, out=messages.append)
        return code, messages

    def test_creates_bucket_uploads_and_records_version(self):
        workspace = self.workspace()
        code, _ = self.publish(workspace, env=dict(workspace.env, FAKE_TF_EXIT_PLAN="2"))
        self.assertEqual(code, 0)
        steps = [c[2] if c[1].startswith("-chdir=") else c[1] for c in workspace.calls() if c[0] == "terraform"]
        self.assertEqual(steps, ["init", "console", "console", "plan", "apply"])
        plan = [c for c in workspace.calls() if c[0] == "terraform" and "plan" in c][0]
        self.assertIn("-target=module.artifact_bucket", plan)
        upload = [c for c in workspace.calls() if c[1:3] == ["s3api", "put-object"]][0]
        self.assertEqual(upload[upload.index("--bucket") + 1], "acme-dev-s3-artifact")
        self.assertEqual(upload[upload.index("--key") + 1], "lambda/function.zip")
        local = (workspace.root / "local.auto.tfvars").read_text()
        self.assertIn('artifact_object_version = "3HL4kqtJlcpXroDTDmJ.rmSpXd3dIbrHY"', local)
        self.assertEqual(local.count("artifact_object_version"), 1)
        self.assertFalse((workspace.root / run.PLAN_FILE).exists())

    def test_existing_bucket_skips_apply(self):
        workspace = self.workspace()
        code, _ = self.publish(workspace)
        self.assertEqual(code, 0)
        self.assertNotIn("apply", [c[2] for c in workspace.calls() if c[0] == "terraform" and len(c) > 2])

    def test_refusals_change_nothing(self):
        workspace = self.workspace()
        code, messages = self.publish(workspace, answer="yes", env=dict(workspace.env, FAKE_TF_EXIT_PLAN="2"))
        self.assertEqual((code, messages[-1]), (1, "Not confirmed; nothing was changed."))
        self.assertFalse([c for c in workspace.calls() if c[1:3] == ["s3api", "put-object"]])
        wrong = self.workspace(dict(AWS_OK, **{"sts get-caller-identity": {"Account": "999988887777"}}))
        self.assertEqual(self.publish(wrong)[0], 1)
        self.assertFalse([c for c in wrong.calls() if c[1:3] == ["s3api", "put-object"]])
        unversioned = self.workspace(dict(AWS_OK, **{"s3api put-object": {"ETag": "x"}}))
        self.assertEqual(self.publish(unversioned)[0], 1)
        self.assertIn("your-uploaded-object-version-id", (unversioned.root / "local.auto.tfvars").read_text())

    def test_only_serverless_api(self):
        workspace = Workspace()
        self.addCleanup(workspace.close)
        messages = []
        self.assertEqual(run.run("platform", "publish-artifact", workspace.terraform, workspace.aws, services=workspace.services,
                                 env=workspace.env, confirm=lambda _p: "x", out=messages.append), 1)
        self.assertEqual(workspace.calls(), [])


class EmptyBucketTests(unittest.TestCase):
    VERSIONS = {"Versions": [{"Key": "lambda/function.zip", "VersionId": "v1"}, {"Key": "lambda/function.zip", "VersionId": "v2"}],
                "DeleteMarkers": [{"Key": "old.zip", "VersionId": "m1"}], "IsTruncated": False}
    LOCAL = f'project = "acme"\naws_account_id = "{ACCOUNT}"\n'

    def services(self, aws_extra=None):
        responses = dict(AWS_OK, **{"s3api list-object-versions": self.VERSIONS, "s3api delete-objects": {}})
        responses.update(aws_extra or {})
        services = Services({}, {"serverless-api": self.LOCAL}, aws=responses)
        self.addCleanup(services.close)
        return services

    def empty(self, services, bucket="acme-dev-s3-artifact", answer="acme-dev-s3-artifact", env=None):
        messages = []
        code = empty_bucket.empty_bucket(bucket, services.aws, services.services, env or services.env, lambda _p: answer, messages.append)
        return code, messages

    def test_deletes_every_version_and_marker_after_confirmation(self):
        services = self.services()
        code, messages = self.empty(services)
        self.assertEqual(code, 0)
        delete = [c for c in services.calls() if c[1:3] == ["s3api", "delete-objects"]][0]
        batch = json.loads(delete[delete.index("--delete") + 1])
        self.assertEqual(sorted(o["VersionId"] for o in batch["Objects"]), ["m1", "v1", "v2"])
        self.assertIn("Deleted 3", messages[-1])

    def test_refusals_delete_nothing(self):
        for bucket, answer, env_extra in [("other-bucket", "other-bucket", {}), ("other-dev-s3-artifact", "other-dev-s3-artifact", {}),
                                          ("acme-dev-s3-artifact", "yes", {}), ("acme-dev-s3-artifact", "acme-dev-s3-artifact", {"CLAUDE_CODE_REMOTE": "true"})]:
            services = self.services()
            code, _ = self.empty(services, bucket, answer, dict(services.env, **env_extra))
            self.assertEqual(code, 1, bucket + answer)
            self.assertFalse([c for c in services.calls() if c[1:3] == ["s3api", "delete-objects"]])

    def test_wrong_account_and_failed_deletes(self):
        wrong = self.services({"sts get-caller-identity": {"Account": "999988887777"}})
        self.assertEqual(self.empty(wrong)[0], 1)
        self.assertFalse([c for c in wrong.calls() if c[1:3] == ["s3api", "list-object-versions"]])
        failing = self.services({"s3api delete-objects": {"Errors": [{"Key": "x", "Code": "AccessDenied"}]}})
        code, messages = self.empty(failing)
        self.assertEqual(code, 1)
        self.assertIn("AccessDenied", messages[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
