"""Deterministic exporter, CLI and transport tests; no AWS account is used."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import policy_validation as toolkit


def document(action, resources, condition):
  return {"Version": "2012-10-17", "Statement": [{"Sid": "RenderedMockFixture",
    "Effect": "Allow", "Action": action, "Resource": resources, "Condition": condition}]}


def fixture_plans():
  account, admin, region, project = "000000000000", "000000000002", "ca-central-1", "test-portfolio"
  instance = "arn:aws:sso:::instance/ssoins-0000000000000000"
  profiles = {name: {"name": identity, "instance_arn": instance,
    "arn": f"arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-{index:016d}"}
    for index, (name, identity) in enumerate((("access_admin", "Portfolio-Access-Admin"),
      ("developer", "Portfolio-Developer"), ("operator", "Portfolio-Operator")), 1)}
  regional = {"StringEquals": {"aws:PrincipalAccount": [account, "000000000001"], "aws:RequestedRegion": region}}
  secret = f"arn:aws:secretsmanager:{region}:{account}:secret:*"
  creation = {"StringEquals": {"aws:PrincipalAccount": account, "aws:RequestedRegion": region, "aws:RequestTag/Project": project}}
  policies = {
    "access_admin": document(["sso:ListAccountAssignments"], [instance, profiles["developer"]["arn"],
      f"arn:aws:sso:::account/{account}"], {"StringEquals": {"aws:PrincipalAccount": admin}}),
    "developer": document(["ec2:DescribeVpcs"], ["*"], regional),
    "operator": document(["ec2:DescribeVpcs"], ["*"], regional),
  }
  managed = document(["secretsmanager:CreateSecret"], [secret], creation)
  managed["Statement"].append({"Sid": "OtherRenderedMockActions", "Effect": "Allow",
    "Action": sorted(toolkit.SM_ACTIONS - {"secretsmanager:CreateSecret"}), "Resource": [secret],
    "Condition": {"StringEquals": {"aws:PrincipalAccount": account, "aws:RequestedRegion": region, "aws:ResourceTag/Project": project}}})

  def resource(kind, name, after):
    return {"type": kind, "name": name, "mode": "managed", "change": {"actions": ["create"], "after": after}}

  iam = [resource("aws_ssoadmin_permission_set", name, after) for name, after in profiles.items()]
  iam += [resource("aws_ssoadmin_permission_set_inline_policy", name, {"inline_policy": toolkit.compact(policy),
    "permission_set_arn": profiles[name]["arn"], "instance_arn": instance}) for name, policy in policies.items()]
  iam += [resource("aws_ssoadmin_customer_managed_policy_attachment", "developer", {
    "permission_set_arn": profiles["developer"]["arn"], "instance_arn": instance,
    "customer_managed_policy_reference": [{"name": toolkit.CMP_NAME, "path": "/"}]})]
  account_plan = [resource("aws_iam_policy", "developer_secrets_manager", {
    "name": toolkit.CMP_NAME, "path": "/", "policy": toolkit.compact(managed)})]
  return {"resource_changes": iam}, {"resource_changes": account_plan}


def events(plan, summary=None):
  identity = {"@testfile": "tests/synthetic.tftest.hcl", "@testrun": "rendered_mock"}
  return [
    {"type": "test_run", "test_run": {"status": "pass"}, **identity},
    {"type": "test_plan", "test_plan": plan, **identity},
    {"type": "test_summary", "test_summary": summary or {
      "status": "pass", "passed": 1, "failed": 0, "errored": 0, "skipped": 0}},
  ]


class ToolkitFixture(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix="policy-toolkit-test-")
    self.addCleanup(self.temp.cleanup)
    self.directory = Path(self.temp.name)
    self.iam_plan, self.account_plan = fixture_plans()
    self.iam_file, self.account_file = self.directory / "iam.jsonl", self.directory / "account.jsonl"
    self.write_events(self.iam_file, events(self.iam_plan))
    self.write_events(self.account_file, events(self.account_plan))

  def write_events(self, filename, rows):
    filename.write_text("".join(json.dumps(row) + "\n" for row in rows))

  def bundle(self):
    directory = self.directory / "bundle"
    toolkit.export_bundle(self.iam_file, self.account_file, directory)
    return directory, toolkit.load_bundle(directory)


class ExportTests(ToolkitFixture):
  def test_actual_rendered_documents_and_manifest(self):
    directory, (manifest, policies, cases) = self.bundle()
    self.assertEqual(set(policies), toolkit.POLICY_IDS)
    self.assertEqual(policies["developer_inline"], json.loads(self.iam_plan["resource_changes"][4]["change"]["after"]["inline_policy"]))
    self.assertEqual(policies["developer_secrets_manager"], json.loads(self.account_plan["resource_changes"][0]["change"]["after"]["policy"]))
    self.assertEqual(manifest["attachment"]["count"], 1)
    self.assertGreater(len(cases), 40)
    self.assertEqual(manifest["policies"]["developer_secrets_manager"]["limit"], 6144)
    self.assertEqual(manifest["policies"]["developer_inline"]["limit"], 10240)
    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
    self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir()))

  def test_failed_native_summary_rejected(self):
    summary = {"status": "fail", "passed": 0, "failed": 1, "errored": 0, "skipped": 0}
    self.write_events(self.iam_file, events(self.iam_plan, summary))
    with self.assertRaises(ValueError):
      self.bundle()

  def test_skipped_native_summary_rejected(self):
    summary = {"status": "pass", "passed": 1, "failed": 0, "errored": 0, "skipped": 1}
    self.write_events(self.iam_file, events(self.iam_plan, summary))
    with self.assertRaises(ValueError):
      self.bundle()

  def test_native_summary_cannot_omit_skip_or_error_counts(self):
    summary = {"status": "pass", "passed": 1, "failed": 0}
    self.write_events(self.iam_file, events(self.iam_plan, summary))
    with self.assertRaises(ValueError):
      self.bundle()

  def test_incomplete_native_stream_rejected(self):
    self.write_events(self.iam_file, events(self.iam_plan)[:-1])
    with self.assertRaises(ValueError):
      self.bundle()

  def test_unmatched_native_error_rejected(self):
    rows = events(self.iam_plan)
    rows.insert(0, {"@level": "error", "@testrun": "unmatched"})
    self.write_events(self.iam_file, rows)
    with self.assertRaises(ValueError):
      self.bundle()

  def test_unexpected_resource_rejected(self):
    self.account_plan["resource_changes"].append({"type": "aws_iam_user"})
    self.write_events(self.account_file, events(self.account_plan))
    with self.assertRaises(ValueError):
      self.bundle()

  def test_attachment_name_path_mismatch_rejected(self):
    self.iam_plan["resource_changes"][-1]["change"]["after"]["customer_managed_policy_reference"][0]["path"] = "/unapproved/"
    self.write_events(self.iam_file, events(self.iam_plan))
    with self.assertRaises(ValueError):
      self.bundle()

  def test_attachment_to_operator_rejected(self):
    self.iam_plan["resource_changes"][-1]["change"]["after"]["permission_set_arn"] = self.iam_plan["resource_changes"][2]["change"]["after"]["arn"]
    self.write_events(self.iam_file, events(self.iam_plan))
    with self.assertRaises(ValueError):
      self.bundle()

  def test_swapped_inline_permission_set_binding_rejected(self):
    self.iam_plan["resource_changes"][4]["change"]["after"]["permission_set_arn"] = self.iam_plan["resource_changes"][2]["change"]["after"]["arn"]
    self.write_events(self.iam_file, events(self.iam_plan))
    with self.assertRaisesRegex(ValueError, "bound"):
      self.bundle()

  def test_tampered_policy_rejected(self):
    directory, _ = self.bundle()
    (directory / "operator.json").write_text("{}")
    with self.assertRaises(ValueError):
      toolkit.load_bundle(directory)

  def test_tampered_case_rejected(self):
    directory, _ = self.bundle()
    (directory / "cases.json").write_text("[]")
    with self.assertRaises(ValueError):
      toolkit.load_bundle(directory)

  def test_managed_policy_cannot_be_reclassified_to_larger_inline_quota(self):
    directory, _ = self.bundle()
    manifest = toolkit.read_json(directory / "manifest.json")
    entry = manifest["policies"]["developer_secrets_manager"]
    entry["kind"] = "inline"
    entry.update(toolkit.policy_sizes((directory / entry["file"]).read_text().rstrip("\n"), "inline"))
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with self.assertRaisesRegex(ValueError, "kind"):
      toolkit.load_bundle(directory)

  def test_path_traversal_rejected(self):
    directory, _ = self.bundle()
    manifest = toolkit.read_json(directory / "manifest.json")
    manifest["policies"]["operator"]["file"] = "../operator.json"
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with self.assertRaises(ValueError):
      toolkit.load_bundle(directory)

  def test_policy_quotas_are_separate(self):
    self.assertEqual(toolkit.policy_sizes("{}", "inline")["headroom"], 10238)
    with self.assertRaises(ValueError):
      toolkit.policy_sizes("x" * 6145, "managed")
    with self.assertRaises(ValueError):
      toolkit.policy_sizes("x" * 10241, "inline")

  def test_non_synthetic_identifier_and_payload_field_rejected(self):
    with self.assertRaises(ValueError):
      toolkit.synthetic_only("arn:aws:iam::" + "1" * 12 + ":role/RejectedNonFixtureIdentifier")
    with self.assertRaises(ValueError):
      toolkit.synthetic_only('{"SecretString": null}')

  def test_git_output_forbidden(self):
    checkout = self.directory / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (checkout / ".git" / "objects").mkdir()
    with self.assertRaises(ValueError):
      toolkit.private_directory(checkout / "generated")

  def test_existing_nonempty_output_not_overwritten(self):
    self.bundle()
    with self.assertRaises(ValueError):
      self.bundle()


class TransportAndCliTests(ToolkitFixture):
  def test_quoted_json_credential_key_is_redacted(self):
    value = toolkit.redact('{"aws_session_token": "synthetic-redaction-fixture"}')
    self.assertNotIn("synthetic-redaction-fixture", value)
    self.assertIn("<redacted>", value)

  def test_unexpected_complete_allow_fails_even_with_missing_context(self):
    case = {"supported": True, "action": "ec2:DeleteVpc", "resources": ["arn:aws:ec2:ca-central-1:000000000000:vpc/vpc-00000000000000000"], "expected": "deny"}
    pages = [{"EvaluationResults": [{"EvalActionName": case["action"], "EvalDecision": "allowed", "MissingContextValues": ["aws:ResourceTag/Project"]}]}]
    result = toolkit.simulation_result(case, pages)
    self.assertEqual(result["status"], "failed")
    self.assertEqual(result["reason"], "unexpected_allow")

  def test_negative_multi_resource_allow_requires_complete_resource_coverage(self):
    case = {"supported": True, "action": "ec2:AttachInternetGateway", "resources": ["synthetic-gateway", "synthetic-vpc"], "expected": "deny"}
    result = {"EvalActionName": case["action"], "EvalDecision": "allowed", "MissingContextValues": ["aws:ResourceTag/Project"],
      "ResourceSpecificResults": [{"EvalResourceName": "synthetic-gateway", "EvalResourceDecision": "allowed"}]}
    self.assertEqual(toolkit.simulation_result(case, [{"EvaluationResults": [result]}])["status"], "inconclusive")
    result["ResourceSpecificResults"].append({"EvalResourceName": "synthetic-vpc", "EvalResourceDecision": "allowed"})
    self.assertEqual(toolkit.simulation_result(case, [{"EvaluationResults": [result]}])["status"], "failed")

  def test_validate_policy_pagination(self):
    calls = []
    def transport(api, request):
      calls.append(copy.deepcopy(request))
      return {"findings": [], "nextToken": "page-two"} if len(calls) == 1 else {"findings": []}
    pages = toolkit.collect_pages(transport, "access-analyzer:ValidatePolicy", {"policyType": "IDENTITY_POLICY"})
    self.assertEqual(len(pages), 2)
    self.assertEqual(calls[1]["nextToken"], "page-two")
    self.assertEqual(toolkit.validate_findings(toolkit.complete_pages("access-analyzer:ValidatePolicy", pages))["status"], "passed")

  def test_iam_marker_pagination(self):
    calls = []
    def transport(api, request):
      calls.append(copy.deepcopy(request))
      return {"EvaluationResults": [], "IsTruncated": True, "Marker": "next"} if len(calls) == 1 else {"EvaluationResults": [], "IsTruncated": False}
    pages = toolkit.collect_pages(transport, "iam:SimulateCustomPolicy", {"ActionNames": ["ec2:DescribeVpcs"]})
    self.assertEqual(calls[1]["Marker"], "next")
    self.assertEqual(len(toolkit.complete_pages("iam:SimulateCustomPolicy", pages)), 2)

  def test_repeated_pagination_token_rejected(self):
    with self.assertRaises(ValueError):
      toolkit.collect_pages(lambda api, request: {"findings": [], "nextToken": "same"}, "access-analyzer:ValidatePolicy", {})

  def test_missing_iam_marker_rejected(self):
    with self.assertRaises(ValueError):
      toolkit.collect_pages(lambda api, request: {"EvaluationResults": [], "IsTruncated": True}, "iam:SimulateCustomPolicy", {})

  def test_recorded_truncated_pages_rejected(self):
    with self.assertRaises(ValueError):
      toolkit.complete_pages("iam:SimulateCustomPolicy", [{"IsTruncated": True, "Marker": "not-finished"}])
    with self.assertRaises(ValueError):
      toolkit.complete_pages("access-analyzer:ValidatePolicy", [{"findings": [], "nextToken": "not-finished"}])

  def test_missing_pagination_completeness_rejected(self):
    with self.assertRaises(ValueError):
      toolkit.collect_pages(lambda api, request: {"EvaluationResults": []}, "iam:SimulateCustomPolicy", {})

  def test_default_run_and_offline_check_make_no_aws_calls(self):
    directory, _ = self.bundle()
    with mock.patch.object(toolkit.subprocess, "run") as process, mock.patch.object(toolkit, "AwsCli") as aws, contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(toolkit.main(["offline-check", "--bundle", str(directory)]), 0)
      result_dir = self.directory / "offline-result"
      self.assertEqual(toolkit.main(["run", "--bundle", str(directory), "--output-dir", str(result_dir)]), 0)
    process.assert_not_called()
    aws.assert_not_called()
    report = toolkit.read_json(result_dir / "results.json")
    self.assertEqual(report["aws_api_calls"], 0)
    self.assertEqual(report["mode"], "offline")
    self.assertIn("Authenticated validation has not been run", (result_dir / "summary.md").read_text())

  def test_execute_flag_forbidden_in_ci(self):
    directory, _ = self.bundle()
    with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), mock.patch.object(toolkit, "AwsCli") as aws:
      with self.assertRaisesRegex(ValueError, "forbidden"):
        toolkit.main(["run", "--execute-aws", "--bundle", str(directory), "--output-dir", str(self.directory / "must-not-exist")])
    aws.assert_not_called()
    self.assertFalse((self.directory / "must-not-exist").exists())

  def test_aws_cli_transport_allowlist_and_request_shape_with_mocked_subprocess(self):
    # Only this deterministic fake subprocess is used; no AWS CLI is executed.
    with mock.patch.object(toolkit, "live_execution_allowed"), mock.patch.object(toolkit.subprocess, "run", return_value=mock.Mock(returncode=0, stdout='{"findings": []}', stderr="")) as process:
      transport = toolkit.AwsCli(self.directory, "ca-central-1")
      response = transport("access-analyzer:ValidatePolicy", {"policyDocument": "{}", "policyType": "IDENTITY_POLICY"})
      self.assertEqual(response, {"findings": []})
      command = process.call_args.args[0]
      self.assertEqual(command[:3], ["aws", "accessanalyzer", "validate-policy"])
      self.assertIn("--no-paginate", command)
      self.assertIn("--cli-input-json", command)
      self.assertFalse(process.call_args.kwargs.get("shell", False))
      with self.assertRaises(ValueError):
        transport("sts:GetCallerIdentity", {})
      self.assertEqual(process.call_count, 1)

  def test_api_permission_error_is_sanitized_and_incomplete(self):
    _, (manifest, policies, cases) = self.bundle()
    def denied(api, request):
      raise toolkit.CliFailure("AccessDenied for arn:aws:sts::" + "1" * 12 + ":assumed-role/PrivateRole/PrivateSession")
    capture = toolkit.execute_bundle(manifest, policies, cases, denied)
    self.assertFalse(capture["complete"])
    self.assertEqual(len(capture["calls"]), 1)
    report = toolkit.parse_capture(manifest, policies, cases, capture)
    self.assertEqual(report["status"], "review_required")
    self.assertNotIn("PrivateRole", json.dumps(report))
    self.assertNotIn("1" * 12, json.dumps(report))

  def test_complete_mocked_responses_preserve_explicit_unverified_cases(self):
    _, (manifest, policies, cases) = self.bundle()
    supported = [case for case in cases if case["supported"]]
    def transport(api, request):
      if api == "access-analyzer:ValidatePolicy":
        return {"findings": []}
      if api == "iam:GetContextKeysForCustomPolicy":
        return {"ContextKeyNames": ["aws:PrincipalAccount", "secretsmanager:AddReplicaRegions"]}
      matches = [case for case in supported if [case["action"]] == request["ActionNames"] and case["resources"] == request["ResourceArns"] and case["context"] == request["ContextEntries"] and toolkit.policy_inputs(case["profile"], policies) == request["PolicyInputList"]]
      self.assertTrue(matches)
      decision = "allowed" if matches[0]["expected"] == "allowed" else "implicitDeny"
      result = {"EvalActionName": request["ActionNames"][0], "EvalDecision": decision, "MissingContextValues": []}
      if len(request["ResourceArns"]) > 1:
        result["ResourceSpecificResults"] = [{"EvalResourceName": arn, "EvalResourceDecision": decision, "MissingContextValues": []} for arn in request["ResourceArns"]]
      return {"EvaluationResults": [result], "IsTruncated": False}
    capture = toolkit.execute_bundle(manifest, policies, cases, transport)
    self.assertTrue(capture["complete"])
    report = toolkit.parse_capture(manifest, policies, cases, capture)
    self.assertEqual(report["status"], "review_required")
    self.assertFalse(any(result["status"] == "failed" for group in ("validations", "contexts", "simulations") for result in report[group].values()))
    self.assertEqual(report["counts"]["inconclusive"], sum(not case["supported"] for case in cases))

  def test_interrupted_result_set_never_fabricates_pass(self):
    _, (manifest, policies, cases) = self.bundle()
    capture = {"format_version": 1, "bundle_sha256": toolkit.bundle_identity(manifest), "complete": False, "calls": []}
    report = toolkit.parse_capture(manifest, policies, cases, capture)
    self.assertEqual(report["status"], "review_required")
    self.assertEqual(set(result["status"] for result in report["validations"].values()), {"inconclusive"})

  def test_unexpected_allow_is_an_actionable_finding_in_both_outputs(self):
    _, (manifest, policies, cases) = self.bundle()
    case = next(case for case in cases if case["supported"] and case["expected"] == "deny" and len(case["resources"]) == 1)
    capture = {"format_version": 1, "bundle_sha256": toolkit.bundle_identity(manifest), "complete": False,
      "calls": [{"api": "iam:SimulateCustomPolicy", "subject": case["id"], "pages": [{"IsTruncated": False,
        "EvaluationResults": [{"EvalActionName": case["action"], "EvalDecision": "allowed"}]}]}]}
    report = toolkit.parse_capture(manifest, policies, cases, capture)
    self.assertEqual(report["status"], "failed")
    self.assertTrue(any(item["type"] == "AUTHORIZATION_MISMATCH" and item["case"] == case["id"] for item in report["findings_requiring_changes"]))
    self.assertIn(case["id"], toolkit.markdown_report(report))
    self.assertIn("unexpected_allow", toolkit.markdown_report(report))

  def test_result_bundle_identity_mismatch_rejected(self):
    _, (manifest, policies, cases) = self.bundle()
    with self.assertRaises(ValueError):
      toolkit.parse_capture(manifest, policies, cases, {"format_version": 1, "bundle_sha256": "wrong", "complete": True, "calls": []})


if __name__ == "__main__":
  unittest.main()
