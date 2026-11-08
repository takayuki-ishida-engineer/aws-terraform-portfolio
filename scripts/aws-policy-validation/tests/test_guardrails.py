"""Independent semantic guardrail regressions using actual rendered policy fixtures."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guardrail_verification as oracle
from test_toolkit import ToolkitFixture


class GuardrailTests(ToolkitFixture):
  def setUp(self):
    super().setUp()
    _, (self.manifest, self.policies, _) = self.bundle()
    self.scope = self.manifest["scope"]

  def report(self, policies=None, scope=None):
    return oracle.verify_guardrails(self.policies if policies is None else policies,
                                    self.scope if scope is None else scope)

  def changed(self, sid, change, policy="developer_inline"):
    policies = copy.deepcopy(self.policies)
    statement = next(row for row in policies[policy]["Statement"] if row["Sid"] == sid)
    change(statement)
    return self.report(policies)

  def scenario(self, report, suffix):
    return next(row for row in report["scenarios"] if row["id"].endswith(suffix))

  def test_actual_exported_baseline_proves_all_reviewed_guards(self):
    report = self.report()
    self.assertEqual(report["status"], "passed")
    self.assertEqual(len(report["structural_checks"]), 6)
    self.assertEqual(len(report["scenarios"]), 181)
    self.assertEqual(len(report["negative_mutations"]), 36)
    self.assertFalse(report["aws_simulated"])

  def test_input_documents_and_scope_are_never_modified(self):
    originals = copy.deepcopy((self.policies, self.scope))
    self.report()
    self.assertEqual((self.policies, self.scope), originals)

  def test_source_hashes_are_canonical_and_identity_bound(self):
    report = self.report()
    self.assertEqual(set(report["source_sha256"]), {"developer_inline", "developer_secrets_manager"})
    for identity, digest in report["source_sha256"].items():
      expected = hashlib.sha256(json.dumps(self.policies[identity], sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
      self.assertEqual(digest, expected)
    self.assertTrue(any("not raw exported" in line for line in report["limitations"]))

  def test_oracle_does_not_import_exporter_projection_or_capture_parser(self):
    tree = ast.parse(Path(oracle.__file__).read_text())
    names = {item.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names}
    names.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    self.assertEqual(names, {"copy", "hashlib", "json", "re"})

  def test_direct_tagging_never_fabricates_create_action(self):
    rows = [row for row in self.report()["scenarios"] if row["action"] == "ec2:CreateTags" and "-create-" not in row["id"]]
    self.assertTrue(rows)
    self.assertTrue(all("ec2:CreateAction" not in row["context"] for row in rows))

  def test_all_project_key_capitalizations_and_mixed_keys_are_blocked(self):
    rows = [row for row in self.report()["scenarios"] if "overwrite-" in row["id"] and row["action"] == "ec2:CreateTags" or row["id"].endswith("mixed-protected-keys")]
    self.assertEqual(len(rows), 32)
    self.assertEqual({tuple(row["context"]["aws:TagKeys"]) for row in rows},
                     {("Project",), ("project",), ("pRoJeCt",), ("Name", "pRoJeCt")})
    self.assertTrue(all(row["actual"] == "implicit_deny" for row in rows))

  def test_ordinary_edits_and_four_creation_types_remain_eligible(self):
    rows = [row for row in self.report()["scenarios"] if row["id"].endswith(("ordinary-edit", "create-tagging"))]
    self.assertEqual(len(rows), 16)
    self.assertEqual({row["resource_type"] for row in rows}, set(oracle.CREATE))
    self.assertTrue(all(row["actual"] == "allowed" for row in rows))

  def test_create_action_mutations_expose_direct_foreign_project_adoption(self):
    rows = [row for row in self.report()["negative_mutations"] if "create-action" in row["id"]]
    self.assertEqual(len(rows), 8)
    for row in rows:
      self.assertNotIn("ec2:CreateAction", row["context"])
      self.assertEqual(row["context"]["aws:ResourceTag/Project"], "another-project")
      self.assertEqual(row["context"]["aws:RequestTag/Project"], self.scope["project_tag"])
      self.assertEqual(row["context"]["aws:TagKeys"], ["Project"])
      self.assertEqual(row["baseline"]["actual"], "implicit_deny")
      self.assertEqual(row["mutated"]["actual"], "allowed")
      self.assertTrue(row["regression_exposed"])

  def test_creation_path_account_region_and_resource_mutations_expose_allows(self):
    report = self.report()
    rows = [row for row in report["negative_mutations"] if "-create-" in row["id"] and "create-action" not in row["id"]]
    self.assertEqual(len(rows), 16)
    self.assertEqual({row["resource_type"] for row in rows}, set(oracle.CREATE))
    for row in rows:
      self.assertIn("ec2:CreateAction", row["context"])
      self.assertNotIn("aws:ResourceTag/Project", row["context"])
      self.assertEqual(row["context"]["aws:RequestTag/Project"], self.scope["project_tag"])
      self.assertEqual(row["baseline"]["actual"], "implicit_deny")
      self.assertEqual(row["mutated"]["actual"], "allowed")

  def test_wrong_create_action_is_denied_for_each_approved_resource_type(self):
    rows = [row for row in self.report()["scenarios"] if row["id"].endswith("create-wrong-action")]
    self.assertEqual(len(rows), 8)
    self.assertTrue(all(row["actual"] == "implicit_deny" for row in rows))

  def test_foreign_project_context_is_distinct_from_authorized_project(self):
    original_project = self.scope["project_tag"]
    policies = json.loads(json.dumps(self.policies).replace(original_project, "another-project"))
    scope = {**self.scope, "project_tag": "another-project"}
    report = self.report(policies, scope)
    self.assertEqual(report["status"], "passed")
    self.assertEqual(self.scenario(report, "ec2-0-vpc-direct-adoption")["context"]["aws:ResourceTag/Project"], "different-project")

  def test_secret_guards_have_separate_and_combined_truth_scenarios(self):
    report = self.report()
    for suffix in ("secret-no-replica-overwrite-absent", "secret-no-replica-overwrite-false"):
      self.assertEqual(self.scenario(report, suffix)["actual"], "allowed")
    for suffix in ("secret-replica-only", "secret-overwrite-only", "secret-both"):
      self.assertEqual(self.scenario(report, suffix)["actual"], "implicit_deny")
    absent = self.scenario(report, "secret-no-replica-overwrite-absent")["context"]
    self.assertNotIn("secretsmanager:AddReplicaRegions", absent)
    self.assertNotIn("secretsmanager:ForceOverwriteReplicaSecret", absent)

  def test_replica_mutations_satisfy_the_overwrite_guard(self):
    rows = [row for row in self.report()["negative_mutations"] if "replica-null" in row["id"]]
    self.assertEqual(len(rows), 2)
    for row in rows:
      self.assertFalse(row["context"]["secretsmanager:ForceOverwriteReplicaSecret"])
      self.assertTrue(row["context"]["secretsmanager:AddReplicaRegions"])
      self.assertEqual(row["mutated"]["actual"], "allowed")
      conditions = row["mutated"]["statements"][-1]["conditions"]
      self.assertTrue(next(item["satisfied"] for item in conditions if item["operator"] == "BoolIfExists"))

  def test_overwrite_mutations_satisfy_the_replica_guard(self):
    rows = [row for row in self.report()["negative_mutations"] if "overwrite-guard" in row["id"]]
    self.assertEqual(len(rows), 2)
    for row in rows:
      self.assertTrue(row["context"]["secretsmanager:ForceOverwriteReplicaSecret"])
      self.assertNotIn("secretsmanager:AddReplicaRegions", row["context"])
      self.assertEqual(row["mutated"]["actual"], "allowed")
      conditions = row["mutated"]["statements"][-1]["conditions"]
      self.assertTrue(next(item["satisfied"] for item in conditions if item["operator"] == "Null"))

  def test_resource_account_region_and_project_mutations_expose_actual_allows(self):
    rows = [row for row in self.report()["negative_mutations"] if "-create-" not in row["id"] and any(label in row["id"] for label in (
      "remove-existing-project", "remove-principal-account", "remove-requested-region", "unbounded-resource"))]
    self.assertEqual(len(rows), 5)
    self.assertTrue(all(row["baseline"]["actual"] == "implicit_deny" and row["mutated"]["actual"] == "allowed" for row in rows))
    self.assertTrue(all(row["source_sha256"] != row["mutated_sha256"] for row in rows))

  def test_empty_and_absent_tag_keys_fail_the_nonnull_guard(self):
    rows = [row for row in self.report()["scenarios"] if row["id"].endswith(("empty-tag-keys", "missing-TagKeys"))]
    self.assertEqual(len(rows), 16)
    for row in rows:
      edit = next(item for item in row["statements"] if item["sid"] == "EditNonAuthorizationTags")
      self.assertFalse(next(item["satisfied"] for item in edit["conditions"] if item["operator"] == "Null"))
      self.assertTrue(next(item["satisfied"] for item in edit["conditions"] if item["operator"].startswith("ForAll")))
      self.assertEqual(row["actual"], "implicit_deny")

  def test_condition_diagnostics_cover_even_resource_nonmatching_statements(self):
    row = self.scenario(self.report(), "ec2-0-vpc-ordinary-edit")
    self.assertEqual(len(row["statements"]), 5)
    subnet = next(item for item in row["statements"] if item["sid"] == "TagDuringCreateSubnet")
    self.assertFalse(subnet["resource_match"])
    self.assertTrue(subnet["conditions"])
    self.assertTrue(all({"operator", "key", "satisfied", "present"} <= set(item) for item in subnet["conditions"]))

  def test_extra_allow_outside_sampled_resource_scope_cannot_obtain_proof(self):
    policies = copy.deepcopy(self.policies)
    extra = copy.deepcopy(policies["developer_inline"]["Statement"][0])
    extra.update(Sid="UnreviewedNarrowAllow", Effect="Allow", Action="ec2:CreateTags",
      Resource="arn:aws:ec2:ca-central-1:000000000099:vpc/*", Condition={})
    policies["developer_inline"]["Statement"].append(extra)
    report = self.report(policies)
    self.assertEqual(report["status"], "failed")
    check = next(item for item in report["structural_checks"] if item["sid"] == "UnreviewedNarrowAllow")
    self.assertEqual(check["status"], "failed")
    self.assertFalse(check["blocking_form"])

  def test_extra_secret_allow_missing_either_guard_is_rejected_universally(self):
    for operator in ("Null", "BoolIfExists"):
      with self.subTest(operator=operator):
        policies = copy.deepcopy(self.policies)
        extra = copy.deepcopy(next(row for row in policies["developer_secrets_manager"]["Statement"] if row["Sid"] == "CreateProjectSecret"))
        extra["Sid"] = "UnreviewedSecretAllow"
        del extra["Condition"][operator]
        # Make the sample scenario inapplicable while preserving a potential grant.
        extra["Condition"]["StringEquals"]["aws:RequestTag/Project"] = "another-project"
        policies["developer_inline"]["Statement"].append(extra)
        report = self.report(policies)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(next(row["status"] for row in report["structural_checks"] if row["sid"] == extra["Sid"]), "failed")

  def test_matching_deny_is_enumerated_and_takes_precedence(self):
    policies = copy.deepcopy(self.policies)
    policies["developer_secrets_manager"]["Statement"].append({"Sid": "ExplicitTagDeny", "Effect": "Deny",
      "Action": "EC2:CREATETAGS", "Resource": "*"})
    report = self.report(policies)
    self.assertEqual(report["status"], "failed")
    self.assertEqual(self.scenario(report, "ec2-0-vpc-ordinary-edit")["actual"], "explicit_deny")
    records = report["actions"]["ec2:CreateTags"]["applicable_statements"]
    self.assertTrue(any(row["policy"] == "developer_secrets_manager" and row["sid"] == "ExplicitTagDeny" for row in records))

  def test_action_case_is_insensitive_without_changing_condition_value_case(self):
    policies = copy.deepcopy(self.policies)
    for document in policies.values():
      for statement in document["Statement"]:
        statement["Action"] = [action.upper() for action in statement["Action"]]
    self.assertEqual(self.report(policies)["status"], "passed")
    report = self.changed("EditNonAuthorizationTags", lambda s: s["Condition"]["StringEquals"].update({"aws:ResourceTag/Project": self.scope["project_tag"].upper()}))
    self.assertEqual(report["status"], "failed")

  def test_condition_key_case_is_insensitive(self):
    policies = copy.deepcopy(self.policies)
    for identity in oracle.POLICIES:
      for statement in policies[identity]["Statement"]:
        statement["Condition"] = {operator: {key.upper(): value for key, value in entries.items()}
          for operator, entries in statement.get("Condition", {}).items()}
    # Evaluation/structural proof is insensitive; mutation construction also must preserve this.
    self.assertEqual(self.report(policies)["status"], "passed")

  def test_condition_key_casefold_collision_is_inconclusive(self):
    report = self.changed("EditNonAuthorizationTags", lambda s: s["Condition"]["StringEquals"].update({"AWS:REQUESTEDREGION": self.scope["region"]}))
    self.assertEqual(report["status"], "inconclusive")

  def test_duplicate_statement_identity_is_inconclusive(self):
    policies = copy.deepcopy(self.policies)
    policies["developer_inline"]["Statement"].append(copy.deepcopy(policies["developer_inline"]["Statement"][0]))
    self.assertEqual(self.report(policies)["status"], "inconclusive")

  def test_wildcard_action_and_notaction_are_inconclusive(self):
    for action in ("ec2:*", "*", "ec2:Create?ags"):
      with self.subTest(action=action):
        self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s.update(Action=action))["status"], "inconclusive")
    self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s.update(NotAction="ec2:DescribeVpcs"))["status"], "inconclusive")

  def test_notresource_and_unknown_resource_patterns_are_inconclusive(self):
    self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s.update(NotResource="*"))["status"], "inconclusive")
    self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s.update(Resource="arn:aws:ec2:*:*:vpc/*"))["status"], "inconclusive")
    self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s.update(Resource="${aws:PrincipalArn}"))["status"], "inconclusive")

  def test_unsupported_condition_operators_and_keys_are_inconclusive(self):
    self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s["Condition"].update(StringLike={"aws:TagKeys": "*"}))["status"], "inconclusive")
    self.assertEqual(self.changed("EditNonAuthorizationTags", lambda s: s["Condition"]["StringEquals"].update({"aws:UnreviewedKey": "value"}))["status"], "inconclusive")

  def test_unsupported_deny_cannot_be_silently_skipped(self):
    policies = copy.deepcopy(self.policies)
    policies["developer_inline"]["Statement"].append({"Sid": "UnsupportedDeny", "Effect": "Deny",
      "Action": "ec2:CreateTags", "Resource": "*", "Condition": {"StringLike": {"aws:TagKeys": "Project"}}})
    self.assertEqual(self.report(policies)["status"], "inconclusive")

  def test_missing_sources_and_malformed_scope_are_inconclusive(self):
    policies = copy.deepcopy(self.policies)
    del policies["developer_inline"]
    self.assertEqual(self.report(policies)["status"], "inconclusive")
    for change in ({"target_account_ids": []}, {"instance_arn": "bad"}, {"region": "*"}, {"project_tag": ""}):
      with self.subTest(change=change):
        self.assertEqual(self.report(scope={**self.scope, **change})["status"], "inconclusive")

  def test_widened_resources_fail_scope_certificate_and_negative_scenario(self):
    report = self.changed("EditNonAuthorizationTags", lambda s: s.update(Resource="*"))
    self.assertEqual(report["status"], "failed")
    self.assertEqual(self.scenario(report, "ec2-0-vpc-wrong-resource-account")["actual"], "allowed")
    self.assertFalse(next(row for row in report["structural_checks"] if row["sid"] == "EditNonAuthorizationTags")["resource_account_region_boundaries"])

  def test_removing_account_or_region_is_an_authorization_regression(self):
    for key, suffix in (("aws:PrincipalAccount", "wrong-principal"), ("aws:RequestedRegion", "wrong-requested-region")):
      with self.subTest(key=key):
        report = self.changed("EditNonAuthorizationTags", lambda s: s["Condition"]["StringEquals"].pop(key))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(self.scenario(report, "ec2-0-vpc-" + suffix)["actual"], "allowed")

  def test_removing_protected_key_guard_is_an_authorization_regression(self):
    report = self.changed("EditNonAuthorizationTags", lambda s: s["Condition"].pop("ForAllValues:StringNotEqualsIgnoreCase"))
    self.assertEqual(report["status"], "failed")
    self.assertEqual(self.scenario(report, "ec2-0-vpc-overwrite-pRoJeCt")["actual"], "allowed")

  def test_weakened_creation_guard_fails_even_with_original_edit_guard_intact(self):
    def weaken(statement):
      value = statement["Condition"]["StringEquals"].pop("ec2:CreateAction")
      statement["Condition"]["StringEqualsIfExists"] = {"ec2:CreateAction": value}
    report = self.changed("TagDuringCreateVpc", weaken)
    self.assertEqual(report["status"], "failed")
    self.assertEqual(self.scenario(report, "ec2-0-vpc-direct-adoption")["actual"], "allowed")

  def test_secret_guard_removal_exposes_each_independent_regression(self):
    for operator, suffix in (("Null", "secret-replica-only"), ("BoolIfExists", "secret-overwrite-only")):
      with self.subTest(operator=operator):
        report = self.changed("CreateProjectSecret", lambda s: s["Condition"].pop(operator), "developer_secrets_manager")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(self.scenario(report, suffix)["actual"], "allowed")

  def test_shareable_report_redacts_accounts_but_preserves_diagnostics(self):
    report = self.report()
    text = json.dumps(report)
    for account in self.scope["target_account_ids"]:
      self.assertNotIn(account, text)
    self.assertIn("<account>", text)
    self.assertIn("ForAllValues:StringNotEqualsIgnoreCase", text)
    self.assertIn("authorization_regression_exposed", text)
    self.assertTrue(all("source_sha256" in row and "mutated_sha256" in row for row in report["negative_mutations"]))


if __name__ == "__main__":
  unittest.main()
