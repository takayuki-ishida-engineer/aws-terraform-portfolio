"""Deterministic response interpretation tests; no AWS CLI or network calls."""

import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_validation import redact, simulation_result, validate_findings


VPC = "arn:aws:ec2:ca-central-1:000000000000:vpc/vpc-00000000000000000"
IGW = "arn:aws:ec2:ca-central-1:000000000000:internet-gateway/igw-00000000000000000"


def case(expected="allowed", resources=None):
  arns = resources or [VPC]
  action = "ec2:AttachInternetGateway" if len(arns) > 1 else "ec2:DeleteVpc"
  return {"id": "synthetic-case", "profile": "developer", "action": action,
      "resources": arns, "expected": expected, "supported": True}


def pages_for(current, decision="allowed", specific=None, missing=None):
  result = {"EvalActionName": current["action"], "EvalDecision": decision,
      # The aggregate template is deliberately not the concrete resource ARN.
      "EvalResourceName": "arn:aws:ec2:ca-central-1:000000000000:vpc/*"}
  if specific is not None:
    result["ResourceSpecificResults"] = specific
  if missing is not None:
    result["MissingContextValues"] = missing
  return [{"EvaluationResults": [result], "IsTruncated": False}]


def resource(arn, decision="allowed", missing=None):
  result = {"EvalResourceName": arn, "EvalResourceDecision": decision}
  if missing is not None:
    result["MissingContextValues"] = missing
  return result


class SimulationDecisionTests(unittest.TestCase):
  def test_expected_allow_from_single_resource_aggregate(self):
    current = case()
    result = simulation_result(current, pages_for(current))
    self.assertEqual((result["status"], result["decision"], result["reason"]),
        ("passed", "allowed", "matched"))

  def test_expected_implicit_deny_remains_distinct(self):
    current = case("deny")
    result = simulation_result(current, pages_for(current, "implicitDeny"))
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["decision"], "implicitDeny")

  def test_expected_explicit_deny_remains_distinct(self):
    current = case("deny")
    result = simulation_result(current, pages_for(current, "explicitDeny"))
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["decision"], "explicitDeny")

  def test_unexpected_allow_fails(self):
    current = case("deny")
    result = simulation_result(current, pages_for(current))
    self.assertEqual((result["status"], result["reason"]), ("failed", "unexpected_allow"))

  def test_unexpected_deny_fails_supported_positive(self):
    current = case()
    result = simulation_result(current, pages_for(current, "implicitDeny"))
    self.assertEqual((result["status"], result["reason"]), ("failed", "unexpected_deny"))

  def test_missing_aggregate_context_is_inconclusive(self):
    current = case()
    result = simulation_result(current, pages_for(current, missing=["aws:ResourceTag/Project"]))
    self.assertEqual((result["status"], result["reason"]), ("inconclusive", "missing_context"))
    self.assertEqual(result["keys"], ["aws:ResourceTag/Project"])

  def test_missing_resource_context_is_inconclusive(self):
    current = case()
    result = simulation_result(current, pages_for(current,
        specific=[resource(VPC, missing=["aws:RequestedRegion"])]))
    self.assertEqual((result["status"], result["reason"]), ("inconclusive", "missing_context"))
    self.assertEqual(result["keys"], ["aws:RequestedRegion"])

  def test_duplicate_context_names_are_reported_once(self):
    current = case(resources=[VPC, IGW])
    specific = [resource(VPC, missing=["aws:RequestedRegion"]),
        resource(IGW, missing=["aws:RequestedRegion"])]
    result = simulation_result(current, pages_for(current, specific=specific))
    self.assertEqual(result["keys"], ["aws:RequestedRegion"])

  def test_parser_does_not_mutate_recorded_response(self):
    current = case()
    pages = pages_for(current, specific=[resource(VPC, missing=["aws:RequestedRegion"])], missing=[])
    original = copy.deepcopy(pages)
    simulation_result(current, pages)
    self.assertEqual(pages, original)

  def test_multi_resource_allows_require_all_resources(self):
    current = case(resources=[VPC, IGW])
    result = simulation_result(current, pages_for(current, specific=[resource(VPC), resource(IGW)]))
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["resource_decisions"], ["allowed", "allowed"])

  def test_one_allow_and_one_deny_can_match_negative_api_case(self):
    current = case("deny", [VPC, IGW])
    result = simulation_result(current, pages_for(current, "implicitDeny",
        [resource(VPC), resource(IGW, "implicitDeny")]))
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["decision"], "implicitDeny")

  def test_explicit_deny_has_aggregate_precedence(self):
    current = case("deny", [VPC, IGW])
    result = simulation_result(current, pages_for(current, "explicitDeny",
        [resource(VPC, "implicitDeny"), resource(IGW, "explicitDeny")]))
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["decision"], "explicitDeny")

  def test_incomplete_multi_resource_details_are_inconclusive(self):
    current = case(resources=[VPC, IGW])
    result = simulation_result(current, pages_for(current, specific=[resource(VPC)]))
    self.assertEqual((result["status"], result["reason"]),
        ("inconclusive", "incomplete_resource_coverage"))

  def test_missing_multi_resource_details_are_inconclusive(self):
    current = case(resources=[VPC, IGW])
    result = simulation_result(current, pages_for(current))
    self.assertEqual((result["status"], result["reason"]),
        ("inconclusive", "multi_resource_details_missing"))

  def test_wrong_single_resource_details_are_inconclusive(self):
    current = case()
    result = simulation_result(current, pages_for(current, specific=[resource(IGW)]))
    self.assertEqual(result["reason"], "incomplete_resource_coverage")

  def test_inconsistent_aggregate_is_rejected(self):
    current = case(resources=[VPC, IGW])
    with self.assertRaisesRegex(ValueError, "Aggregate and per-resource"):
      simulation_result(current, pages_for(current, "allowed",
          [resource(VPC), resource(IGW, "implicitDeny")]))

  def test_declared_unsupported_protection_never_becomes_passing_deny(self):
    current = case("deny") | {"supported": False, "notes": "Recipient comparison is unsupported."}
    result = simulation_result(current, [])
    self.assertEqual((result["status"], result["reason"]),
        ("inconclusive", "unsupported_by_design"))

  def test_malformed_response_is_rejected(self):
    with self.assertRaises(ValueError):
      simulation_result(case(), [{"unexpected": []}])

  def test_unknown_decision_is_rejected(self):
    current = case()
    with self.assertRaisesRegex(ValueError, "Unsupported simulation decision"):
      simulation_result(current, pages_for(current, "unknown"))

  def test_missing_result_is_rejected(self):
    with self.assertRaises(ValueError):
      simulation_result(case(), [{"EvaluationResults": [], "IsTruncated": False}])

  def test_duplicate_action_result_is_rejected(self):
    current = case()
    with self.assertRaisesRegex(ValueError, "duplicate"):
      simulation_result(current, pages_for(current) + pages_for(current))

  def test_mismatched_action_result_is_rejected(self):
    current = case()
    pages = pages_for(current)
    pages[0]["EvaluationResults"][0]["EvalActionName"] = "ec2:DeleteSubnet"
    with self.assertRaisesRegex(ValueError, "mismatched"):
      simulation_result(current, pages)

  def test_duplicate_resource_result_is_rejected(self):
    current = case()
    with self.assertRaisesRegex(ValueError, "Duplicate resource"):
      simulation_result(current, pages_for(current, specific=[resource(VPC), resource(VPC)]))

  def test_malformed_missing_context_is_rejected(self):
    current = case()
    with self.assertRaisesRegex(ValueError, "Malformed missing-context"):
      simulation_result(current, pages_for(current, missing="aws:RequestedRegion"))


class PolicyFindingTests(unittest.TestCase):
  @staticmethod
  def finding(kind):
    return {"findingType": kind, "issueCode": "SYNTHETIC_FIXTURE",
        "findingDetails": "Synthetic finding; no real account information."}

  def test_empty_findings_pass_only_when_response_exists(self):
    result = validate_findings([{"findings": []}])
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["counts"],
        {"ERROR": 0, "SECURITY_WARNING": 0, "WARNING": 0, "SUGGESTION": 0})
    with self.assertRaises(ValueError):
      validate_findings([])

  def test_each_severity_keeps_its_distinct_count_and_review_status(self):
    for kind in ("ERROR", "SECURITY_WARNING", "WARNING", "SUGGESTION"):
      with self.subTest(kind=kind):
        result = validate_findings([{"findings": [self.finding(kind)]}])
        self.assertEqual(result["counts"][kind], 1)
        self.assertEqual(sum(result["counts"].values()), 1)
        self.assertEqual(result["status"], "failed" if kind == "ERROR" else "review_required")

  def test_multiple_pages_retain_all_finding_severities(self):
    result = validate_findings([
      {"findings": [self.finding("ERROR"), self.finding("SECURITY_WARNING")]},
      {"findings": [self.finding("WARNING"), self.finding("SUGGESTION")]},
    ])
    self.assertEqual(result["status"], "failed")
    self.assertEqual(result["counts"],
        {"ERROR": 1, "SECURITY_WARNING": 1, "WARNING": 1, "SUGGESTION": 1})

  def test_unknown_severity_is_rejected(self):
    with self.assertRaises(ValueError):
      validate_findings([{"findings": [self.finding("UNKNOWN")]}])

  def test_missing_finding_details_are_rejected(self):
    with self.assertRaises(ValueError):
      validate_findings([{"findings": [{"findingType": "ERROR", "issueCode": "FIXTURE"}]}])

  def test_malformed_finding_page_is_rejected(self):
    with self.assertRaises(ValueError):
      validate_findings([{"findings": {}}])


class RedactionTests(unittest.TestCase):
  def test_arn_is_removed_from_shareable_details(self):
    result = redact("Synthetic reference " + VPC)
    self.assertIn("<redacted-arn>", result)
    self.assertNotIn(VPC, result)

  def test_account_identifier_is_removed(self):
    result = redact("Synthetic account 000000000000 is not an actual session.")
    self.assertIn("<redacted-account>", result)
    self.assertNotIn("000000000000", result)

  def test_token_assignment_is_removed(self):
    result = redact("token=synthetic-redaction-fixture")
    self.assertNotIn("synthetic-redaction-fixture", result)
    self.assertIn("<redacted>", result)

  def test_bearer_authorization_payload_is_removed(self):
    result = redact("Authorization: Bearer synthetic-redaction-fixture")
    self.assertNotIn("synthetic-redaction-fixture", result)
    self.assertIn("<redacted>", result)

  def test_findings_are_sanitized_before_reporting(self):
    finding = {"findingType": "WARNING", "issueCode": "SYNTHETIC_FIXTURE",
        "findingDetails": f"Synthetic {VPC} and account 000000000000; token=synthetic-redaction-fixture"}
    result = validate_findings([{"findings": [finding]}])
    detail = result["findings"][0]["details"]
    self.assertNotIn(VPC, detail)
    self.assertNotIn("000000000000", detail)
    self.assertNotIn("synthetic-redaction-fixture", detail)


if __name__ == "__main__":
  unittest.main()
