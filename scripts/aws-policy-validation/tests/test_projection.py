"""Exact-action projection certificates and synthetic capture regressions."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import policy_validation as toolkit
import simulation_projection as projection
from test_toolkit import ToolkitFixture


def statement(action, effect="Allow"):
  return {"Sid": "SyntheticStructure", "Effect": effect, "Action": action,
      "Resource": ["arn:aws:ec2:ca-central-1:000000000000:vpc/*"],
      "Condition": {"StringEquals": {"aws:ResourceTag/project": "test-portfolio"}}}


def documents(*statements):
  return {"synthetic": {"Version": "2012-10-17", "Id": "synthetic-certificate",
      "Statement": list(statements)}}


class ProjectionStructureTests(unittest.TestCase):
  def test_exact_action_is_case_insensitive_and_statement_stays_whole(self):
    sources = documents(statement(["EC2:deletevpc", "ec2:ModifyVpcAttribute"]))
    result = projection.project_policies(sources, "ec2:DeleteVpc")
    self.assertEqual(result, sources)
    self.assertEqual(projection.verify_projection(sources, "ec2:DeleteVpc", result)["retained_statement_count"], 1)

  def test_matching_deny_is_retained_without_condition_or_resource_rewrite(self):
    sources = documents(statement("ec2:DeleteVpc", "Deny"), statement("secretsmanager:DeleteSecret"))
    result = projection.project_policies(sources, "ec2:DeleteVpc")
    self.assertEqual(result["synthetic"]["Statement"], [sources["synthetic"]["Statement"][0]])
    proof = projection.verify_projection(sources, "ec2:DeleteVpc", result)
    self.assertEqual((proof["retained_statement_count"], proof["omitted_statement_count"]), (1, 1))

  def test_nonmatching_deny_can_be_omitted_by_exact_action_only(self):
    sources = documents(statement("secretsmanager:DeleteSecret", "Deny"))
    self.assertEqual(projection.project_policies(sources, "ec2:DeleteVpc"), {})
    self.assertEqual(projection.verify_projection(sources, "ec2:DeleteVpc", {})["omitted_statement_count"], 1)

  def test_unknown_selectors_never_establish_an_absent_action_proof(self):
    for selector in ("ec2:*", "s3:Get?bject", [], None, ["s3:GetObject", "ec2:*"]):
      with self.subTest(selector=selector):
        sources = documents(statement(selector))
        result = projection.project_policies(sources, "ec2:DeleteVpc")
        self.assertEqual(result, sources)
        projection.verify_projection(sources, "ec2:DeleteVpc", result)

  def test_not_action_is_retained_conservatively(self):
    original = statement("ec2:DeleteVpc", "Deny")
    original["NotAction"] = original.pop("Action")
    sources = documents(original)
    self.assertEqual(projection.project_policies(sources, "ec2:DeleteVpc"), sources)
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", {})

  def test_resource_mismatch_does_not_authorize_removing_a_matching_action(self):
    original = statement("ec2:DeleteVpc")
    original["Resource"] = ["arn:aws:ec2:us-east-1:000000000001:vpc/*"]
    sources = documents(original)
    self.assertEqual(projection.project_policies(sources, "ec2:DeleteVpc"), sources)

  def test_verifier_is_independent_of_projector(self):
    sources = documents(statement("ec2:DeleteVpc"))
    result = copy.deepcopy(sources)
    with mock.patch.object(projection, "project_policies", side_effect=AssertionError("must not be called")):
      proof = projection.verify_projection(sources, "ec2:DeleteVpc", result)
    self.assertEqual(proof["method"], projection.METHOD)

  def test_dropping_matching_allow_is_rejected(self):
    with self.assertRaises(ValueError):
      projection.verify_projection(documents(statement("ec2:DeleteVpc")), "ec2:DeleteVpc", {})

  def test_dropping_matching_deny_is_rejected(self):
    with self.assertRaises(ValueError):
      projection.verify_projection(documents(statement("ec2:DeleteVpc", "Deny")), "ec2:DeleteVpc", {})

  def test_adding_or_duplicating_a_statement_is_rejected(self):
    sources = documents(statement("ec2:DeleteVpc"))
    result = copy.deepcopy(sources)
    result["synthetic"]["Statement"].append(copy.deepcopy(result["synthetic"]["Statement"][0]))
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", result)

  def test_projected_policy_metadata_cannot_change(self):
    sources = documents(statement("ec2:DeleteVpc"))
    result = copy.deepcopy(sources)
    result["synthetic"]["Id"] = "unreviewed"
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", result)

  def test_empty_projected_document_is_not_an_aws_request(self):
    sources = documents(statement("s3:GetObject"))
    result = copy.deepcopy(sources)
    result["synthetic"]["Statement"] = []
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", result)

  def test_statement_order_is_auditable_and_preserved(self):
    sources = documents(statement("ec2:DeleteVpc"), statement(["ec2:DeleteVpc", "ec2:ModifyVpcAttribute"], "Deny"))
    result = copy.deepcopy(sources)
    result["synthetic"]["Statement"].reverse()
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", result)

  def test_source_hashes_include_omitted_documents(self):
    sources = documents(statement("ec2:DeleteVpc"))
    sources["other"] = {"Version": "2012-10-17", "Statement": [statement("s3:GetObject")]}
    result = projection.project_policies(sources, "ec2:DeleteVpc")
    proof = projection.verify_projection(sources, "ec2:DeleteVpc", result)
    self.assertEqual(set(proof["source_sha256"]), {"synthetic", "other"})
    self.assertEqual(set(proof["projected_sha256"]), {"synthetic"})

  def test_json_hash_does_not_depend_on_dictionary_key_order(self):
    self.assertEqual(projection.content_sha256({"a": 1, "b": 2}), projection.content_sha256({"b": 2, "a": 1}))
    self.assertNotEqual(projection.content_sha256({"a": True}), projection.content_sha256({"a": 1}))

  def test_projection_does_not_mutate_originals(self):
    sources = documents(statement("ec2:DeleteVpc"))
    original = copy.deepcopy(sources)
    result = projection.project_policies(sources, "ec2:DeleteVpc")
    result["synthetic"]["Statement"][0]["Condition"]["StringEquals"].clear()
    self.assertEqual(sources, original)
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", result)


class ActualPolicyProjectionTests(ToolkitFixture):
  def setUp(self):
    super().setUp()
    _, (self.manifest, self.policies, self.cases) = self.bundle()

  def current(self, identifier):
    return next(case for case in self.cases if case["id"] == identifier)

  def capture(self, case, decision="allowed", missing=None, legacy=False):
    result = {"EvalActionName": case["action"], "EvalDecision": decision}
    if missing is not None:
      result["MissingContextValues"] = missing
    record = {"api": "iam:SimulateCustomPolicy", "subject": case["id"],
        "pages": [{"EvaluationResults": [result], "IsTruncated": False}]}
    capture = {"format_version": 1 if legacy else toolkit.CAPTURE_VERSION,
        "bundle_sha256": toolkit.bundle_identity(self.manifest), "complete": False, "calls": [record]}
    if not legacy:
      capture["simulation_mode"] = projection.METHOD
      record["evidence"] = toolkit.simulation_plan(case, self.policies)["evidence"]
    return capture

  def assert_condition_mutation_rejected(self, action, sid, operator, key):
    sources = {name: self.policies[name] for name in toolkit.PROFILE_POLICIES["developer"]}
    result = projection.project_policies(sources, action)
    selected = next(statement for doc in result.values() for statement in doc["Statement"] if statement["Sid"] == sid)
    del selected["Condition"][operator][key]
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, action, result)

  def test_account_restriction_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("ec2:DeleteVpc", "ManageExistingProjectNetwork", "StringEquals", "aws:PrincipalAccount")

  def test_region_restriction_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("ec2:DeleteVpc", "ManageExistingProjectNetwork", "StringEquals", "aws:RequestedRegion")

  def test_resource_project_restriction_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("ec2:DeleteVpc", "ManageExistingProjectNetwork", "StringEquals", "aws:ResourceTag/project")

  def test_request_project_restriction_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:CreateSecret", "CreateProjectSecret", "StringEquals", "aws:RequestTag/project")

  def test_tag_adoption_guard_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:TagResource", "TagProjectSecretIdentity", "StringEquals", "aws:ResourceTag/project")

  def test_tag_key_protection_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:UntagResource", "EditProjectSecretTags", "ForAllValues:StringNotEqualsIgnoreCase", "aws:TagKeys")

  def test_recovery_lower_bound_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:DeleteSecret", "ScheduleProjectSecretDeletion", "NumericGreaterThanEquals", "secretsmanager:RecoveryWindowInDays")

  def test_recovery_upper_bound_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:DeleteSecret", "ScheduleProjectSecretDeletion", "NumericLessThanEquals", "secretsmanager:RecoveryWindowInDays")

  def test_force_deletion_guard_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:DeleteSecret", "ScheduleProjectSecretDeletion", "BoolIfExists", "secretsmanager:ForceDeleteWithoutRecovery")

  def test_replica_absence_guard_removal_cannot_pass_certificate(self):
    self.assert_condition_mutation_rejected("secretsmanager:CreateSecret", "CreateProjectSecret", "Null", "secretsmanager:AddReplicaRegions")

  def test_resource_broadening_cannot_pass_certificate(self):
    sources = {name: self.policies[name] for name in toolkit.PROFILE_POLICIES["developer"]}
    result = projection.project_policies(sources, "ec2:DeleteVpc")
    result["developer_inline"]["Statement"][0]["Resource"] = ["*"]
    with self.assertRaises(ValueError):
      projection.verify_projection(sources, "ec2:DeleteVpc", result)

  def test_cross_service_conditions_are_not_sent_for_ec2_request(self):
    case = self.current("developer-vpc-unapproved-region")
    plan = toolkit.simulation_plan(case, self.policies)
    self.assertEqual(plan["kind"], "aws_simulation")
    self.assertEqual(plan["request"]["ContextEntries"], case["context"])
    self.assertNotIn("secretsmanager:", json.dumps(plan["request"]["PolicyInputList"]))
    self.assertEqual(set(plan["evidence"]["source_sha256"]), {"developer_inline", "developer_secrets_manager"})
    self.assertEqual(set(plan["evidence"]["projected_sha256"]), {"developer_inline"})

  def test_legacy_cross_service_missing_context_is_not_relabelled_as_new_success(self):
    case = self.current("developer-vpc-unapproved-region")
    capture = self.capture(case, "implicitDeny", ["secretsmanager:AddReplicaRegions", "secretsmanager:RecoveryWindowInDays"], legacy=True)
    report = toolkit.parse_capture(self.manifest, self.policies, self.cases, capture)
    self.assertEqual(report["simulation_mode"], "legacy_full_policy_set")
    self.assertEqual(report["simulations"][case["id"]]["reason"], "missing_context")
    self.assertFalse(report["static_checks"])

  def test_new_projected_response_with_missing_context_is_still_inconclusive(self):
    case = self.current("developer-vpc-unapproved-region")
    capture = self.capture(case, "implicitDeny", ["aws:ResourceTag/project"])
    result = toolkit.parse_capture(self.manifest, self.policies, self.cases, capture)["simulations"][case["id"]]
    self.assertEqual((result["status"], result["reason"]), ("inconclusive", "missing_context"))

  def test_unexpected_allow_with_matching_projection_still_fails(self):
    case = self.current("developer-vpc-unapproved-region")
    capture = self.capture(case, "allowed", ["aws:ResourceTag/project"])
    result = toolkit.parse_capture(self.manifest, self.policies, self.cases, capture)["simulations"][case["id"]]
    self.assertEqual((result["status"], result["reason"]), ("failed", "unexpected_allow"))

  def test_legacy_ungranted_action_unexpected_allow_is_not_hidden_by_inventory(self):
    case = self.current("developer-secret-forbidden-get-value")
    capture = self.capture(case, "allowed", legacy=True)
    report = toolkit.parse_capture(self.manifest, self.policies, self.cases, capture)
    self.assertEqual(report["simulations"][case["id"]]["reason"], "unexpected_allow")

  def test_new_capture_cannot_sneak_an_api_allow_for_a_static_case(self):
    case = self.current("developer-secret-forbidden-get-value")
    with self.assertRaisesRegex(ValueError, "extra API subjects"):
      toolkit.parse_capture(self.manifest, self.policies, self.cases, self.capture(case, "allowed"))

  def test_request_hash_tampering_never_yields_a_passing_simulation(self):
    case = self.current("developer-vpc-delete")
    capture = self.capture(case)
    capture["calls"][0]["evidence"]["request_sha256"] = "untrusted-request"
    result = toolkit.parse_capture(self.manifest, self.policies, self.cases, capture)["simulations"][case["id"]]
    self.assertEqual(result["reason"], "request_projection_mismatch")

  def test_changed_case_context_does_not_reuse_old_projected_evidence(self):
    original = self.current("developer-vpc-delete")
    capture = self.capture(original)
    cases = copy.deepcopy(self.cases)
    changed = next(case for case in cases if case["id"] == original["id"])
    changed["context"].append({"ContextKeyName": "synthetic:Changed", "ContextKeyValues": ["changed"], "ContextKeyType": "string"})
    result = toolkit.parse_capture(self.manifest, self.policies, cases, capture)["simulations"][original["id"]]
    self.assertEqual(result["reason"], "request_projection_mismatch")

  def test_changed_source_condition_does_not_reuse_old_projected_evidence(self):
    case = self.current("developer-vpc-delete")
    capture = self.capture(case)
    policies = copy.deepcopy(self.policies)
    selected = next(s for s in policies["developer_inline"]["Statement"] if s["Sid"] == "ManageExistingProjectNetwork")
    del selected["Condition"]["StringEquals"]["aws:PrincipalAccount"]
    result = toolkit.parse_capture(self.manifest, policies, self.cases, capture)["simulations"][case["id"]]
    self.assertEqual(result["reason"], "request_projection_mismatch")

  def test_positive_action_missing_from_policy_is_failed_static_evidence(self):
    case = copy.deepcopy(self.current("developer-iam-administration"))
    case["expected"] = "allowed"
    plan = toolkit.simulation_plan(case, self.policies)
    result = toolkit.static_inventory_result(case, plan)
    self.assertEqual((result["status"], result["reason"]), ("failed", "expected_allow_without_action"))
    self.assertFalse(result["aws_simulated"])

  def test_negative_ungranted_action_has_static_not_simulated_evidence(self):
    case = self.current("developer-secret-forbidden-get-value")
    plan = toolkit.simulation_plan(case, self.policies)
    result = toolkit.static_inventory_result(case, plan)
    self.assertEqual(result["status"], "passed")
    self.assertEqual(result["evidence_type"], "static_action_inventory")
    self.assertFalse(result["aws_simulated"])

  def test_null_and_ifexists_absence_context_is_never_filled(self):
    for identifier in ("developer-secret-create", "developer-secret-delete-30-days"):
      with self.subTest(identifier=identifier):
        case = self.current(identifier)
        plan = toolkit.simulation_plan(case, self.policies)
        self.assertEqual(plan["request"]["ContextEntries"], case["context"])
        projected = [json.loads(text) for text in plan["request"]["PolicyInputList"]]
        operators = {operator for policy in projected for statement in policy["Statement"] for operator in statement.get("Condition", {})}
        self.assertTrue(operators & {"Null", "BoolIfExists"})

  def test_case_plan_partition_and_four_unsupported_cases_are_unchanged(self):
    counts = {kind: sum(toolkit.simulation_plan(case, self.policies)["kind"] == kind for case in self.cases)
      for kind in ("aws_simulation", "static_action_inventory", "unsupported")}
    self.assertEqual(counts, {"aws_simulation": 35, "static_action_inventory": 15, "unsupported": 4})
    for case in self.cases:
      if not case["supported"]:
        self.assertEqual(toolkit.simulation_plan(case, self.policies)["kind"], "unsupported")
        self.assertEqual(toolkit.simulation_result(case, [])["status"], "inconclusive")


if __name__ == "__main__":
  unittest.main()
