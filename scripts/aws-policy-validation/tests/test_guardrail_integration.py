"""Keep independent static proofs separate from AWS response evidence."""

import contextlib
import io
import json
from pathlib import Path
import sys
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import policy_validation as toolkit
from test_toolkit import ToolkitFixture


class GuardrailIntegrationTests(ToolkitFixture):
  def setUp(self):
    super().setUp()
    self.bundle_dir, (self.manifest, self.policies, self.cases) = self.bundle()

  def capture(self):
    records = []
    for identifier, key in (("developer-vpc-project-tag-change", "ec2:CreateAction"),
        ("developer-secret-replica-overwrite", "secretsmanager:AddReplicaRegions")):
      case = next(case for case in self.cases if case["id"] == identifier)
      records.append({"api": "iam:SimulateCustomPolicy", "subject": identifier,
          "evidence": toolkit.simulation_plan(case, self.policies)["evidence"],
          "pages": [{"EvaluationResults": [{"EvalActionName": case["action"],
            "EvalDecision": "implicitDeny", "MissingContextValues": [key]}], "IsTruncated": False}]})
    return {"format_version": toolkit.CAPTURE_VERSION, "simulation_mode": toolkit.METHOD,
        "bundle_sha256": toolkit.bundle_identity(self.manifest), "complete": False, "calls": records}

  def test_offline_proofs_are_separate_from_unchanged_inventory(self):
    report = toolkit.offline_report(self.manifest, self.cases, self.policies)
    self.assertEqual(report["guardrail_proofs"]["status"], "passed")
    self.assertFalse(report["guardrail_proofs"]["aws_simulated"])
    self.assertEqual(report["simulation_plan_counts"],
        {"aws_simulation": 35, "static_action_inventory": 15, "unsupported": 4})
    self.assertEqual(len(report["static_checks"]), 15)
    self.assertEqual(report["simulation_case_count"], 54)
    self.assertEqual(report["guardrail_proofs"]["source_export_sha256"], {
      identifier: self.manifest["policies"][identifier]["sha256"]
      for identifier in ("developer_inline", "developer_secrets_manager")})

  def test_independent_success_does_not_upgrade_two_missing_context_responses(self):
    report = toolkit.parse_capture(self.manifest, self.policies, self.cases, self.capture())
    self.assertEqual(report["guardrail_proofs"]["status"], "passed")
    for identifier in ("developer-vpc-project-tag-change", "developer-secret-replica-overwrite"):
      result = report["simulations"][identifier]
      self.assertEqual((result["status"], result["reason"]), ("inconclusive", "missing_context"))
      self.assertNotIn(identifier, report["static_checks"])
    self.assertEqual(report["status"], "review_required")

  def test_default_run_adds_proofs_without_aws_process_or_credentials(self):
    output = self.directory / "offline-results"
    with mock.patch.object(toolkit.subprocess, "run", side_effect=AssertionError("No AWS process")), contextlib.redirect_stdout(io.StringIO()):
      status = toolkit.main(["run", "--bundle", str(self.bundle_dir), "--output-dir", str(output)])
    report = json.loads((output / "results.json").read_text())
    self.assertEqual(status, 0)
    self.assertEqual(report["aws_api_calls"], 0)
    self.assertEqual(report["guardrail_proofs"]["status"], "passed")
    self.assertIn("Independent static guardrail proofs", (output / "summary.md").read_text())

  def test_failed_proof_fails_cli_and_cannot_be_hidden_by_existing_checks(self):
    with mock.patch.object(toolkit, "verify_guardrails", return_value={"status": "failed", "aws_simulated": False}), contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(toolkit.main(["offline-check", "--bundle", str(self.bundle_dir)]), 1)
      report = toolkit.parse_capture(self.manifest, self.policies, self.cases, self.capture())
    self.assertEqual(report["status"], "failed")
    self.assertTrue(any(value["type"] == "INDEPENDENT_GUARDRAIL_MISMATCH"
        for value in report["findings_requiring_changes"]))

  def test_unsupported_proof_fails_closed_with_nonzero_cli_status(self):
    for value in ({"status": "inconclusive", "aws_simulated": False}, {"status": "unexpected"}):
      with self.subTest(value=value), mock.patch.object(toolkit, "verify_guardrails", return_value=value), contextlib.redirect_stdout(io.StringIO()):
        self.assertEqual(toolkit.main(["offline-check", "--bundle", str(self.bundle_dir)]), 2)

  def test_unknown_source_exception_cannot_create_successful_evidence(self):
    with mock.patch.object(toolkit, "verify_guardrails", side_effect=ValueError("Unsupported operator")):
      report = toolkit.offline_report(self.manifest, self.cases, self.policies)
    self.assertEqual(report["status"], "review_required")
    self.assertEqual(report["guardrail_proofs"]["status"], "inconclusive")
    self.assertFalse(report["guardrail_proofs"]["aws_simulated"])

  def test_markdown_identifies_proof_and_retains_missing_context_rows(self):
    report = toolkit.parse_capture(self.manifest, self.policies, self.cases, self.capture())
    markdown = toolkit.markdown_report(report)
    self.assertIn("not an AWS Simulator result or deployed-role authorization proof", markdown)
    self.assertIn("Negative mutation", markdown)
    self.assertIn("developer-vpc-project-tag-change | inconclusive | aws_simulation", markdown)
    self.assertIn("developer-secret-replica-overwrite | inconclusive | aws_simulation", markdown)

  def test_unsupported_protections_remain_inconclusive_despite_successful_proof(self):
    report = toolkit.parse_capture(self.manifest, self.policies, self.cases, self.capture())
    unsupported = [case["id"] for case in self.cases if not case["supported"]]
    self.assertEqual(len(unsupported), 4)
    for identifier in unsupported:
      self.assertEqual(report["simulations"][identifier]["status"], "inconclusive")
      self.assertEqual(report["simulations"][identifier]["evidence_type"], "unsupported_by_design")
