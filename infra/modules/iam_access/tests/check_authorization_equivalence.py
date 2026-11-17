#!/usr/bin/env python3
"""Compare actual split policy plans with the approved synthetic Phase 3-3 plans.

This is a structural action/compatible-resource/condition regression, not an IAM
simulator. The managed policy intentionally narrows Secrets Manager authority to
its owning account. No AWS API, credential lookup or Terraform command is used.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import check_authorization_reference as reference


APPROVED_COMMIT = "325ead5fb9031be8f2cbab1689e36b408465e274"
BASELINE_SHA256 = "eac48255db9f590f73c7fe89fb84ce86a4a731c3214f4918078cb12f6fb949f1"
FIXTURE = Path(__file__).parent / "fixtures" / "phase_3_3_policies.json"
# Owner-approved tag key rename (docs/deployment-configuration.md section 5,
# 2026-11-16). The frozen Phase 3-3 baseline stays byte-identical and hash-pinned;
# only its aws:RequestTag/<key>, aws:ResourceTag/<key> condition keys and
# aws:TagKeys values are projected through this exact mapping before comparison.
# Every action, resource, operator and condition value stays frozen. An unknown
# tag key fails closed with KeyError.
TAG_KEY_RENAME = {"Environment": "env", "ManagedBy": "managed", "Name": "Name", "Project": "project", "Service": "service"}
SECRET_ACTIONS = {
  "secretsmanager:CreateSecret", "secretsmanager:DescribeSecret",
  "secretsmanager:GetResourcePolicy", "secretsmanager:TagResource",
  "secretsmanager:UntagResource", "secretsmanager:DeleteSecret",
}


def require(condition, message):
  if not condition:
    raise ValueError(message)


def canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"))


def baseline():
  fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
  provenance = fixture["provenance"]
  policies = fixture["policies"]
  require(fixture["schema_version"] == 1 and
      provenance["approved_repository_commit"] == APPROVED_COMMIT,
      "unexpected approved baseline identity")
  digest = hashlib.sha256(canonical(policies).encode()).hexdigest()
  require(digest == BASELINE_SHA256 == provenance["aggregate_policy_sha256"],
      "approved generated-policy baseline hash changed")
  for name, policy in policies.items():
    require(hashlib.sha256(canonical(policy).encode()).hexdigest() ==
        provenance["policy_sha256"][name], "baseline document hash mismatch")
  require(provenance["native_test_summary"] == {
    "status": "pass", "passed": 34, "failed": 0, "errored": 0, "skipped": 0,
  }, "baseline lacks its passing native-plan provenance")
  return policies


def renamed_tag_keys(policies):
  """Project the approved baseline through TAG_KEY_RENAME, changing nothing else."""
  result = copy.deepcopy(policies)
  for policy in result.values():
    for statement in policy["Statement"]:
      for operator, keys in statement.get("Condition", {}).items():
        renamed = {}
        for key, value in keys.items():
          match = re.fullmatch(r"aws:(RequestTag|ResourceTag)/(.+)", key)
          if match:
            key = "aws:" + match[1] + "/" + TAG_KEY_RENAME[match[2]]
          elif key == "aws:TagKeys" and operator != "Null":
            # Null only tests presence ("true"/"false"); its value is not a tag key.
            value = sorted(TAG_KEY_RENAME[item] for item in reference.strings(value))
          require(key not in renamed, "tag key rename collision")
          renamed[key] = value
        statement["Condition"][operator] = renamed
  return result


def normalized_condition(condition, principal_account=None):
  """Normalize scalar/list alternatives; narrow only the old principal list."""
  result = {}
  for operator, keys in condition.items():
    result[operator] = {}
    for key, value in keys.items():
      values = value if isinstance(value, list) else [value]
      if principal_account is not None and key.lower() == "aws:principalaccount":
        require(operator == "StringEquals" and principal_account in values,
            "owning account is outside the approved original principal scope")
        values = [principal_account]
      result[operator][key] = sorted(values)
  return canonical(result)


def projection(policy, references, service, owning_account=None):
  """Keep only resource types AWS documents as compatible with each action.

  For the old Secrets Manager document, owning_account projects the old approved
  multi-account grant onto one target. Every other condition stays exact.
  """
  result = set()
  for statement in policy["Statement"]:
    resources = reference.strings(statement["Resource"])
    for action in reference.strings(statement["Action"]):
      prefix, name = action.split(":", 1)
      if prefix != service:
        continue
      entry = references[prefix][0][name]
      types = {item["Name"] for item in entry.get("Resources", [])}
      for arn in resources:
        if owning_account is not None:
          require(arn != "*", "Secrets Manager baseline must use scoped ARNs")
          if arn.split(":", 5)[4] != owning_account:
            continue
        compatible = arn == "*" and not types
        if arn != "*":
          compatible = any(re.fullmatch(reference.pattern(template), arn)
            for kind in types for template in references[prefix][1][kind])
        if compatible:
          result.add((action, arn, normalized_condition(
            statement.get("Condition", {}), owning_account)))
  return result


def check_equivalence(current, managed, previous, references):
  require(set(current) == {"access_admin", "developer", "operator"},
      "unexpected inline profiles")
  for policy in [*current.values(), managed]:
    reference.check_policy(policy, references)
  require(current["access_admin"] == previous["access_admin"],
      "Access Admin policy changed")
  require(current["operator"] == previous["operator"],
      "Operator policy changed")
  require(all(action.startswith("ec2:") for statement in current["developer"]["Statement"]
      for action in reference.strings(statement["Action"])),
      "Developer inline contains an unexpected service")
  managed_actions = {action for statement in managed["Statement"]
      for action in reference.strings(statement["Action"])}
  require(managed_actions == SECRET_ACTIONS, "managed policy action contract changed")
  accounts = {arn.split(":", 5)[4] for statement in managed["Statement"]
      for arn in reference.strings(statement["Resource"]) if arn != "*"}
  require(len(accounts) == 1 and all(re.fullmatch(r"[0-9]{12}", a) for a in accounts),
      "managed policy must have exactly one explicit owning account")
  account = next(iter(accounts))
  for statement in managed["Statement"]:
    principal = statement.get("Condition", {}).get("StringEquals", {}).get("aws:PrincipalAccount")
    require(principal == account or principal == [account],
        "managed policy principal is not narrowed to its owning account")
  old_ec2 = projection(previous["developer"], references, "ec2")
  new_ec2 = projection(current["developer"], references, "ec2")
  require(old_ec2 == new_ec2, "EC2 action/resource/condition projection changed")
  old_secret = projection(previous["developer"], references, "secretsmanager", account)
  new_secret = projection(managed, references, "secretsmanager")
  require(old_secret == new_secret,
      "Secrets Manager action/resource/condition contract changed beyond owning-account tightening")
  return {"ec2_tuples": len(new_ec2), "secret_tuples": len(new_secret),
      "owning_account_count": len(accounts)}


def self_test(current, managed, previous, references):
  def statement(policy, sid):
    return next(item for item in policy["Statement"] if item["Sid"] == sid)

  def extra_ec2(c, m):
    c["developer"]["Statement"].append({
      "Sid": "UnreviewedMetadata", "Effect": "Allow", "Action": ["ec2:DescribeTags"],
      "Resource": ["*"], "Condition": copy.deepcopy(c["developer"]["Statement"][0]["Condition"]),
    })

  mutations = {
    "new EC2 grant": extra_ec2,
    "EC2 region change": lambda c, m: c["developer"]["Statement"][0]["Condition"]["StringEquals"].update({"aws:RequestedRegion": "us-east-1"}),
    "managed project change": lambda c, m: statement(m, "ReadProjectSecretMetadata")["Condition"]["StringEquals"].update({"aws:ResourceTag/project": "other-project"}),
    "missing adoption guard": lambda c, m: statement(m, "TagProjectSecretIdentity")["Condition"]["StringEquals"].pop("aws:ResourceTag/project"),
    "pre-rename managed tag key": lambda c, m: statement(m, "ReadProjectSecretMetadata")["Condition"]["StringEquals"].update(
        {"aws:ResourceTag/Project": statement(m, "ReadProjectSecretMetadata")["Condition"]["StringEquals"].pop("aws:ResourceTag/project")}),
    "pre-rename creation tag keys": lambda c, m: statement(m, "CreateProjectSecret")["Condition"]["ForAllValues:StringEquals"].update(
        {"aws:TagKeys": ["Environment", "ManagedBy", "Name", "Project", "Service"]}),
    "extra creation tag key": lambda c, m: statement(m, "CreateProjectSecret")["Condition"]["ForAllValues:StringEquals"]["aws:TagKeys"].append("owner"),
    "force deletion enabled": lambda c, m: statement(m, "ScheduleProjectSecretDeletion")["Condition"]["BoolIfExists"].update({"secretsmanager:ForceDeleteWithoutRecovery": "true"}),
    "zero-day recovery": lambda c, m: statement(m, "ScheduleProjectSecretDeletion")["Condition"]["NumericGreaterThanEquals"].update({"secretsmanager:RecoveryWindowInDays": "0"}),
    "forbidden UpdateSecret": lambda c, m: statement(m, "ReadProjectSecretMetadata")["Action"].append("secretsmanager:UpdateSecret"),
    "Operator value read": lambda c, m: statement(c["operator"], "ReadProjectSecretMetadata")["Action"].append("secretsmanager:GetSecretValue"),
    "Access Admin broadening": lambda c, m: c["access_admin"]["Statement"][0].update(Resource=["*"]),
    "managed cross-account grant": lambda c, m: m["Statement"][0]["Resource"].append("arn:aws:secretsmanager:ca-central-1:000000000001:secret:*"),
    "missing allowed create": lambda c, m: m["Statement"].remove(statement(m, "CreateProjectSecret")),
    "removed parent VPC authorization": lambda c, m: c["developer"]["Statement"].remove(statement(c["developer"], "UseExistingProjectVpc")),
  }
  check_equivalence(current, managed, previous, references)
  for label, mutate in mutations.items():
    candidate, customer_policy = copy.deepcopy(current), copy.deepcopy(managed)
    mutate(candidate, customer_policy)
    try:
      check_equivalence(candidate, customer_policy, previous, references)
    except ValueError:
      continue
    raise ValueError("equivalence self-test failed to reject " + label)
  print(f"PASS: {len(mutations)} authorization regression mutations rejected.")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--iam-test-events", required=True)
  parser.add_argument("--account-test-events", required=True)
  parser.add_argument("--ec2-reference", required=True)
  parser.add_argument("--sso-reference", required=True)
  parser.add_argument("--secretsmanager-reference", required=True)
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()
  references = {}
  for service, path in (("ec2", args.ec2_reference), ("sso", args.sso_reference),
      ("secretsmanager", args.secretsmanager_reference)):
    references[service] = reference.index_reference(json.loads(Path(path).read_text()), service)
  previous = renamed_tag_keys(baseline())
  current = reference.read_test_events(args.iam_test_events)
  managed = reference.read_account_test_events(args.account_test_events)
  counts = check_equivalence(current, managed, previous, references)
  print("PASS: approved EC2 projection and Access Admin/Operator documents unchanged after the approved tag key rename; "
      "Secrets Manager union preserves exact reviewed boundaries within one owning account.")
  print("Actual projection counts:", canonical(counts))
  print("Intentional tightening: the managed policy cannot authorize another approved workload account. "
      "This is offline structural verification, not live IAM authorization.")
  if args.self_test:
    self_test(current, managed, previous, references)


if __name__ == "__main__":
  try:
    main()
  except (ValueError, KeyError, TypeError, OSError) as error:
    print(f"FAIL: {error}", file=sys.stderr)
    sys.exit(1)
