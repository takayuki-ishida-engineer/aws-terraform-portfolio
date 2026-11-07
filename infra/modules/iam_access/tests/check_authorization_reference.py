#!/usr/bin/env python3
"""Offline checks of rendered policies against supplied official AWS SAR JSON.

Run Terraform separately and preserve its exit status before invoking this script.
This checker requires a passing native test summary; it does not run Terraform,
contact AWS, simulate IAM, or prove request-dependent resource/condition values.
"""

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict


# AWS SAR machine JSON v1.5 omits the HTML tables' required-resource asterisks.
# Explicit overlay for actions used here, reviewed against these HTML tables:
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam-identity-center.html
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html
# Other resource types in an action's JSON entry remain request-dependent/optional.
REQUIRED = {
  "ec2:CreateVpc": {"vpc"},
  "ec2:CreateSubnet": {"vpc", "subnet"},
  "ec2:CreateInternetGateway": {"internet-gateway"},
  "ec2:CreateRouteTable": {"vpc", "route-table"},
  "ec2:DeleteVpc": {"vpc"},
  "ec2:DeleteSubnet": {"subnet"},
  "ec2:DeleteInternetGateway": {"internet-gateway"},
  "ec2:DeleteRouteTable": {"route-table"},
  "ec2:CreateRoute": {"route-table"},
  "ec2:ReplaceRoute": {"route-table"},
  "ec2:DeleteRoute": {"route-table"},
  "ec2:DescribeVpcAttribute": {"vpc"},
  "ec2:AttachInternetGateway": {"vpc", "internet-gateway"},
  "ec2:DetachInternetGateway": {"vpc", "internet-gateway"},
  "ec2:ModifyVpcAttribute": {"vpc"},
  "ec2:ModifySubnetAttribute": {"subnet"},
  "ec2:AssociateRouteTable": {"route-table"},
  "ec2:ReplaceRouteTableAssociation": {"route-table"},
  "sso:CreateAccountAssignment": {"Account", "Instance", "PermissionSet"},
  "sso:DeleteAccountAssignment": {"Account", "Instance", "PermissionSet"},
  "sso:ListAccountAssignments": {"Account", "Instance", "PermissionSet"},
  "sso:DescribePermissionSet": {"Instance", "PermissionSet"},
  "sso:DescribeAccountAssignmentCreationStatus": {"Instance"},
  "sso:DescribeAccountAssignmentDeletionStatus": {"Instance"},
  "secretsmanager:CreateSecret": {"Secret"},
  "secretsmanager:DescribeSecret": {"Secret"},
  "secretsmanager:GetResourcePolicy": {"Secret"},
  "secretsmanager:TagResource": {"Secret"},
  "secretsmanager:UntagResource": {"Secret"},
  "secretsmanager:DeleteSecret": {"Secret"},
}
# Only these universal, single-valued global keys are exceptions to SAR entries:
# https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html
GLOBAL_KEYS = {"aws:PrincipalAccount", "aws:RequestedRegion"}
PROFILES = {"access_admin", "developer", "operator"}


def require(condition, message):
  if not condition:
    raise ValueError(message)


def strings(value):
  result = [value] if isinstance(value, str) else value
  require(isinstance(result, list) and result and
      all(isinstance(item, str) and item for item in result), "expected nonempty strings")
  return result


def pattern(template):
  """Escape literals; only AWS-documented ${...} placeholders are variable."""
  # Secrets Manager names may contain '/', unlike ARN account/region segments.
  # Limit this exception to its documented terminal SecretId placeholder.
  secret_path = template.startswith("arn:") and ":secretsmanager:" in template and template.endswith(":secret:${SecretId}")
  return "".join("[^:]+" if secret_path and part == "${SecretId}" else
         "[^:/]+" if part.startswith("${") else re.escape(part)
         for part in re.split(r"(\$\{[^}]+\})", template))


def condition_matches(key, allowed):
  return any(re.fullmatch(pattern(candidate).replace("[^:/]+", ".+"), key, re.I)
       for candidate in allowed)


def index_reference(document, service):
  require(document.get("ServiceName") == {
    "ec2": "EC2", "sso": "IAM Identity Center", "secretsmanager": "Secrets Manager"}[service]
      and document.get("Version") == "v1.5",
      f"expected official {service} SAR schema v1.5")
  return ({action["Name"]: action for action in document["Actions"]},
      {resource["Name"]: resource["ARNFormats"] for resource in document["Resources"]})


def check_policy(policy, references):
  require(policy.get("Version") == "2012-10-17", "unexpected policy version")
  statements = policy.get("Statement")
  require(isinstance(statements, list) and statements, "missing statements")
  coverage = defaultdict(set)
  for statement in statements:
    require(not ({"NotAction", "NotResource", "Principal", "NotPrincipal"} & statement.keys()),
        "negative action/resource or principal elements are forbidden")
    require(statement.get("Effect") == "Allow", "expected explicit Allow statement")
    actions, resources = strings(statement.get("Action")), strings(statement.get("Resource"))
    conditions = statement.get("Condition", {})
    require(isinstance(conditions, dict) and all(isinstance(v, dict) for v in conditions.values()),
        "malformed Condition")
    keys = {key for group in conditions.values() for key in group}
    covered = set()
    for action in actions:
      require(not any(char in action for char in "*?"), f"action wildcard: {action}")
      service, separator, name = action.partition(":")
      require(separator and service in references and name in references[service][0],
          f"unknown action: {action}")
      entry = references[service][0][name]
      types = {item["Name"]: item for item in entry.get("Resources", [])}
      common = set(entry.get("ActionConditionKeys", [])) | GLOBAL_KEYS
      if not types:
        require(resources == ["*"], f"{action} requires wildcard Resource")
        require(all(condition_matches(key, common) for key in keys),
            f"unsupported condition key for {action}")
        covered.add(0)
        coverage[action].add("*")
        continue
      require("*" not in resources, f"wildcard Resource for scoped action {action}")
      applicable = False
      for i, arn in enumerate(resources):
        fields = arn.split(":", 5)
        require(len(fields) == 6 and not any(c in ":".join(fields[:5]) for c in "*?"),
            f"invalid or unscoped ARN: {arn}")
        matching = [kind for kind in types if any(
          re.fullmatch(pattern(fmt), arn)
          for fmt in references[service][1].get(kind, []))]
        for kind in matching:
          allowed = common | set(types[kind].get("ConditionKeys", []))
          require(all(condition_matches(key, allowed) for key in keys),
              f"unsupported condition key for {action}/{kind}: {sorted(keys)}")
          coverage[action].add(kind)
          covered.add(i)
          applicable = True
      require(applicable, f"no supported Resource for {action}")
    require(covered == set(range(len(resources))), "Resource unsupported by all statement actions")
  for action, actual in coverage.items():
    require(REQUIRED.get(action, set()) <= actual,
        f"missing required resource types for {action}: {sorted(REQUIRED.get(action, set()) - actual)}")


def policies_from_plan(plan):
  resources = plan.get("resource_changes", [])
  expected = Counter({"aws_ssoadmin_permission_set": 3,
            "aws_ssoadmin_permission_set_inline_policy": 3,
            "aws_ssoadmin_customer_managed_policy_attachment": 1})
  require(Counter(r.get("type") for r in resources) == expected,
      "positive plan must contain exactly three Permission Sets, three inline policies and one customer-managed reference")
  for kind in ("aws_ssoadmin_permission_set", "aws_ssoadmin_permission_set_inline_policy"):
    require({r.get("name") for r in resources if r.get("type") == kind} == PROFILES,
        f"unexpected profiles for {kind}")
  profiles = {r["name"]: r["change"]["after"] for r in resources
        if r["type"] == "aws_ssoadmin_permission_set"}
  instances = {profile["instance_arn"] for profile in profiles.values()}
  require(len(instances) == 1, "Permission Sets must share the reviewed instance")
  policies = {}
  for resource in resources:
    require(resource.get("mode") == "managed" and resource["change"]["actions"] == ["create"],
        "positive plan must contain managed creates only")
    after = resource["change"]["after"]
    if resource["type"] == "aws_ssoadmin_permission_set_inline_policy":
      require(after["permission_set_arn"] == profiles[resource["name"]]["arn"]
          and after["instance_arn"] in instances, "inline policy bound to wrong profile/instance")
      policies[resource["name"]] = json.loads(after["inline_policy"])
    if resource["type"] == "aws_ssoadmin_customer_managed_policy_attachment":
      require(resource["name"] == "developer" and resource.get("index") == "secrets_manager"
          and after["permission_set_arn"] == profiles["developer"]["arn"]
          and after["instance_arn"] in instances, "managed reference must target only Developer in the reviewed instance")
      require(after["customer_managed_policy_reference"] == [
        {"name": "Portfolio-Developer-SecretsManager", "path": "/"}],
        "unexpected customer-managed policy identity")
  return policies


def account_policy_from_plan(plan):
  resources = plan.get("resource_changes", [])
  require(len(resources) == 1, "account plan must contain exactly one managed policy")
  resource = resources[0]
  require(resource.get("type") == "aws_iam_policy" and resource.get("name") == "developer_secrets_manager"
      and resource.get("mode") == "managed" and resource["change"]["actions"] == ["create"],
      "unexpected account policy resource or lifecycle")
  after = resource["change"]["after"]
  require(after["name"] == "Portfolio-Developer-SecretsManager" and after["path"] == "/",
      "account policy name/path does not match the Identity Center reference")
  return json.loads(after["policy"])


def read_test_events(path, plan_reader=policies_from_plan):
  # Stream JSONL: retain only the first successful plan's reviewed resources,
  # not the repeated provider schemas. Still inspect later errors and summary.
  passed, errors, policies, summary = set(), set(), None, None
  with open(path, encoding="utf-8") as events:
    for line in events:
      event = json.loads(line)
      if event.get("@level") == "error":
        errors.add((event.get("@testfile"), event.get("@testrun")))
      if event.get("type") == "test_run" and event["test_run"].get("status") == "pass":
        passed.add((event.get("@testfile"), event.get("@testrun")))
      if event.get("type") == "test_plan" and policies is None:
        require((event.get("@testfile"), event.get("@testrun")) in passed,
            "first rendered plan did not follow a passing test")
        policies = plan_reader(event["test_plan"])
      if event.get("type") == "test_summary":
        summary = event["test_summary"]
  # Expected-failure validation runs legitimately emit error diagnostics; only
  # accept them when Terraform explicitly marks that same test run as passing.
  require(errors <= passed, "Terraform emitted errors outside a passing test run")
  require(policies is not None, "no rendered successful test plan found")
  require(summary and summary.get("status") == "pass" and summary.get("passed", 0) > 0
      and summary.get("failed", 0) == 0 and summary.get("errored", 0) == 0
      and summary.get("skipped", 0) == 0,
      "missing or unsuccessful Terraform test summary")
  return policies


def read_account_test_events(path):
  return read_test_events(path, account_policy_from_plan)


def inventory_self_test():
  instance = "arn:aws:sso:::instance/ssoins-0000000000000000"
  resources = []
  for i, profile in enumerate(sorted(PROFILES)):
    arn = f"arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-{i:016d}"
    resources.extend([
      {"type": "aws_ssoadmin_permission_set", "name": profile, "mode": "managed",
       "change": {"actions": ["create"], "after": {"arn": arn, "instance_arn": instance}}},
      {"type": "aws_ssoadmin_permission_set_inline_policy", "name": profile, "mode": "managed",
       "change": {"actions": ["create"], "after": {"permission_set_arn": arn, "instance_arn": instance,
         "inline_policy": json.dumps({"Version": "2012-10-17", "Statement": []})}}}])
  resources.append({"type": "aws_ssoadmin_customer_managed_policy_attachment", "name": "developer",
    "index": "secrets_manager", "mode": "managed", "change": {"actions": ["create"], "after": {
      "permission_set_arn": resources[2]["change"]["after"]["arn"], "instance_arn": instance,
      "customer_managed_policy_reference": [{"name": "Portfolio-Developer-SecretsManager", "path": "/"}]}}})
  iam = {"resource_changes": resources}
  account = {"resource_changes": [{"type": "aws_iam_policy", "name": "developer_secrets_manager",
    "mode": "managed", "change": {"actions": ["create"], "after": {
      "name": "Portfolio-Developer-SecretsManager", "path": "/",
      "policy": json.dumps({"Version": "2012-10-17", "Statement": []})}}}]}
  policies_from_plan(iam)
  account_policy_from_plan(account)
  cases = []
  for field, value in (("permission_set_arn", resources[0]["change"]["after"]["arn"]),
      ("name", "Unreviewed"), ("path", "/unreviewed/")):
    plan = copy.deepcopy(iam)
    after = plan["resource_changes"][-1]["change"]["after"]
    if field == "permission_set_arn":
      after[field] = value
    else:
      after["customer_managed_policy_reference"][0][field] = value
    cases.append((policies_from_plan, plan))
  plan = copy.deepcopy(iam)
  plan["resource_changes"].append({"type": "aws_iam_role"})
  cases.append((policies_from_plan, plan))
  for field, value in (("name", "Unreviewed"), ("path", "/unreviewed/")):
    plan = copy.deepcopy(account)
    plan["resource_changes"][0]["change"]["after"][field] = value
    cases.append((account_policy_from_plan, plan))
  plan = copy.deepcopy(account)
  plan["resource_changes"].append({"type": "aws_iam_role"})
  cases.append((account_policy_from_plan, plan))
  for reader, plan in cases:
    try:
      reader(plan)
    except ValueError:
      continue
    raise ValueError("inventory self-test accepted unreviewed identity/resource")
  print(f"Inventory self-tests passed: {len(cases)} incorrect profile/identity/resource mutations rejected.")


def self_test():
  fixture = {"ServiceName": "EC2", "Version": "v1.5", "Actions": [{
    "Name": "CreateSubnet", "ActionConditionKeys": ["ec2:Region"], "Resources": [
      {"Name": "subnet", "ConditionKeys": ["aws:RequestTag/${TagKey}"]},
      {"Name": "vpc", "ConditionKeys": ["aws:ResourceTag/${TagKey}"]}]}],
    "Resources": [{"Name": kind, "ARNFormats": [
      "arn:${Partition}:ec2:${Region}:${Account}:" + kind + "/${Id}"]}
      for kind in ("vpc", "subnet")]}
  fixture["Actions"].append({"Name": "CreateVpc", "Resources": [
    {"Name": "vpc", "ConditionKeys": []},
    {"Name": "ipam-pool", "ConditionKeys": []}]})
  fixture["Resources"].append({"Name": "ipam-pool", "ARNFormats": [
    "arn:${Partition}:ec2::${Account}:ipam-pool/${IpamPoolId}"]})
  refs = {"ec2": index_reference(fixture, "ec2")}
  base = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Action": ["ec2:CreateSubnet"],
    "Resource": ["arn:aws:ec2:ca-central-1:000000000000:" + kind + "/*"],
    "Condition": {"StringEquals": {key: "test"}}}
    for kind, key in (("subnet", "aws:RequestTag/Project"), ("vpc", "aws:ResourceTag/Project"))]}
  check_policy(base, refs)
  mutations = {
    "unknown action": lambda p: p["Statement"][0].update(Action=["ec2:Typo"]),
    "wildcard action": lambda p: p["Statement"][0].update(Action=["ec2:Create*"]),
    "wildcard write resource": lambda p: p["Statement"][0].update(Resource=["*"]),
    "unsupported resource": lambda p: p["Statement"][0].update(Resource=["arn:aws:ec2:ca-central-1:000000000000:security-group/*"]),
    "unsupported condition": lambda p: p["Statement"][0].update(Condition={"Bool": {"ec2:IsMain": "false"}}),
    "wrong resource condition": lambda p: p["Statement"][0].update(Condition={"StringEquals": {"aws:ResourceTag/Project": "test"}}),
    "missing required parent": lambda p: p["Statement"].pop(),
    "optional resource without required VPC": lambda p: p.update(Statement=[{
      "Effect": "Allow", "Action": ["ec2:CreateVpc"],
      "Resource": ["arn:aws:ec2::000000000000:ipam-pool/ipam-pool-00000000000000000"]}]),
    "negative action": lambda p: p["Statement"][0].update(NotAction=["ec2:DeleteVpc"]),
  }
  for label, mutate in mutations.items():
    candidate = copy.deepcopy(base)
    mutate(candidate)
    try:
      check_policy(candidate, refs)
    except ValueError:
      continue
    raise ValueError(f"self-test failed to reject {label}")
  secret_count = secretsmanager_self_test()
  print(f"Self-test passed: valid parameterized keys and secret paths accepted; {len(mutations) + secret_count} unsafe mutations rejected ({len(mutations)} original, {secret_count} Secrets Manager).")


def secretsmanager_self_test():
  # Minimal official v1.5 action/key subsets; no secret payload is supplied.
  tags = ["aws:ResourceTag/${TagKey}", "aws:TagKeys"]
  definitions = {
    "CreateSecret": ["aws:RequestTag/${TagKey}", "aws:TagKeys"],
    "DescribeSecret": ["aws:ResourceTag/${TagKey}"],
    "GetResourcePolicy": ["aws:ResourceTag/${TagKey}"],
    "TagResource": tags + ["aws:RequestTag/${TagKey}"],
    "UntagResource": tags,
    "DeleteSecret": ["aws:ResourceTag/${TagKey}",
      "secretsmanager:ForceDeleteWithoutRecovery", "secretsmanager:RecoveryWindowInDays"],
  }
  fixture = {"ServiceName": "Secrets Manager", "Version": "v1.5",
    "Actions": [{"Name": name, "ActionConditionKeys": keys,
      "Resources": [{"Name": "Secret"}]} for name, keys in definitions.items()],
    "Resources": [{"Name": "Secret", "ARNFormats": [
      "arn:${Partition}:secretsmanager:${Region}:${Account}:secret:${SecretId}"]}]}
  refs = {"secretsmanager": index_reference(fixture, "secretsmanager")}
  arn = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/dev/database-000000"
  base = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Allow", "Action": ["secretsmanager:DescribeSecret"], "Resource": [arn],
    "Condition": {"StringEquals": {"aws:ResourceTag/Project": "test"}}}]}
  check_policy(base, refs)
  # Also exercise the deletion and tag-integrity keys used by generated policies.
  deletion = copy.deepcopy(base)
  deletion["Statement"][0].update(Action=["secretsmanager:DeleteSecret"])
  deletion["Statement"][0]["Condition"].update({
    "BoolIfExists": {"secretsmanager:ForceDeleteWithoutRecovery": "false"},
    "NumericGreaterThanEquals": {"secretsmanager:RecoveryWindowInDays": "7"},
    "NumericLessThanEquals": {"secretsmanager:RecoveryWindowInDays": "30"}})
  check_policy(deletion, refs)
  tag = copy.deepcopy(base)
  tag["Statement"][0].update(Action=["secretsmanager:TagResource"])
  tag["Statement"][0]["Condition"]["StringEquals"]["aws:RequestTag/Project"] = "test"
  tag["Statement"][0]["Condition"]["ForAllValues:StringEquals"] = {"aws:TagKeys": ["Name", "Project"]}
  check_policy(tag, refs)
  mutations = {
    "unknown secret action": lambda p: p["Statement"][0].update(Action=["secretsmanager:Typo"]),
    "secret action wildcard": lambda p: p["Statement"][0].update(Action=["secretsmanager:Describe*"]),
    "unscoped secret resource": lambda p: p["Statement"][0].update(Resource=["*"]),
    "unsupported secret resource": lambda p: p["Statement"][0].update(Resource=["arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000"]),
    "fabricated payload-absence condition": lambda p: p["Statement"][0].update(Action=["secretsmanager:CreateSecret"], Condition={"Null": {"secretsmanager:SecretString": "true", "secretsmanager:SecretBinary": "true"}}),
    "unsupported untag request-tag condition": lambda p: p["Statement"][0].update(Action=["secretsmanager:UntagResource"], Condition={"StringEquals": {"aws:RequestTag/Project": "test"}}),
    "wildcard secret account": lambda p: p["Statement"][0].update(Resource=[arn.replace("000000000000", "*")]),
    "colon inside secret identifier": lambda p: p["Statement"][0].update(Resource=[arn.replace("portfolio/dev", "portfolio:dev")]),
  }
  for label, mutate in mutations.items():
    candidate = copy.deepcopy(base)
    mutate(candidate)
    try:
      check_policy(candidate, refs)
    except ValueError:
      continue
    raise ValueError(f"self-test failed to reject {label}")
  return len(mutations)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ec2-reference")
  parser.add_argument("--sso-reference")
  parser.add_argument("--secretsmanager-reference")
  parser.add_argument("--test-events")
  parser.add_argument("--account-test-events")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()
  if args.self_test:
    self_test()
    inventory_self_test()
  paths = (args.ec2_reference, args.sso_reference, args.secretsmanager_reference, args.test_events, args.account_test_events)
  if not any(paths):
    require(args.self_test, "supply all five input paths or --self-test")
    return
  require(all(paths), "all five input paths are required")
  references = {}
  for service, path in zip(("ec2", "sso", "secretsmanager"), paths[:3]):
    with open(path, encoding="utf-8") as source:
      references[service] = index_reference(json.load(source), service)
  policies = read_test_events(args.test_events)
  policies["developer_secrets_manager"] = read_account_test_events(args.account_test_events)
  for profile, policy in policies.items():
    try:
      check_policy(policy, references)
      compact = json.dumps(policy, separators=(",", ":"), ensure_ascii=False)
      limit = 6144 if profile == "developer_secrets_manager" else 10240
      actual = len(compact) if profile == "developer_secrets_manager" else len(compact.encode("utf-8"))
      require(actual <= limit, f"policy quota exceeded: {actual} > {limit}")
      print(f"{profile}: {actual}/{limit}; remaining {limit - actual}")
    except ValueError as error:
      raise ValueError(f"{profile}: {error}") from error
  print("PASS: four rendered policies, reviewed 7+1 resource inventories, quotas, scoped action/resource/condition compatibility and required-resource overlay; passing test summaries.")
  print("Static checks only: no IAM simulation, request-dependent authorization, parameter-value or main-route-table exclusion proof.")


if __name__ == "__main__":
  try:
    main()
  except (ValueError, KeyError, TypeError, OSError) as error:
    print(f"FAIL: {error}", file=sys.stderr)
    sys.exit(1)
