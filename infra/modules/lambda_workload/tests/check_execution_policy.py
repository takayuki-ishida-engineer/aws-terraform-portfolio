#!/usr/bin/env python3
"""Narrow, credential-free verification of actual native mock-plan IAM policies.

This is static policy-set evidence, not an IAM Simulator or a deployed-session
authorization proof. No Terraform process, AWS CLI, SDK, credential lookup or
network client is invoked. Expected scope comes from the input-derived output,
never from the policy being checked. Semantic mutations use actual rendered JSON.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from check_r1_migration import verify_structure, structure_mutations


# Reviewed case-by-case migration, not a replacement with a historical total.
MANIFEST = json.loads((Path(__file__).with_name("coverage.json")).read_text())
EXPECTED_TESTS = len(MANIFEST)
EXPECTED_NEGATIVES = sum(case["expect_failure"] for case in MANIFEST)
POSITIVE_RUNS = {case["new_run"] for case in MANIFEST if not case["expect_failure"]}
EXPECTED_RUNS = {(case["new_file"], case["new_run"]) for case in MANIFEST}
REJECTED_SHAPES = json.loads((Path(__file__).with_name("rejected_shapes.json")).read_text())
INVENTORY = {"aws_lambda_function", "aws_iam_role", "aws_iam_role_policy", "aws_cloudwatch_log_group"}
POLICY_NAME = "LambdaWorkloadAccess"
LOG_ACTIONS = {"logs:CreateLogStream", "logs:PutLogEvents"}
SECRET_ACTIONS = {"secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"}
SERVICE_NAMES = {"logs": "CloudWatch Logs", "secretsmanager": "Secrets Manager", "kms": "KMS"}
REQUIRED_TYPES = {**{action: "log-stream" for action in LOG_ACTIONS},
    **{action: "Secret" for action in SECRET_ACTIONS}, "kms:Decrypt": "key"}
# The machine SAR v1.5 omits HTML's required-resource asterisks. These five
# required types were verified against the official Logs/Secrets Manager/KMS
# service-authorization tables; no action here requires Resource="*".
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_logs.html
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_kms.html
REQUIRED_TYPES_CASEFOLD = {action.casefold(): kind for action, kind in REQUIRED_TYPES.items()}
SCOPE_KEYS = {"role_name", "partition", "account_id", "region", "log_group_arn",
    "enable_secret_read", "secret_arn", "secret_kms_key_arn"}
LIMITATIONS = [
  "Static reviewed-policy-set evidence only; no AWS Simulator or deployed-role authorization was executed.",
  "Expected account and reference consistency do not configure or verify the root provider account; allowed_account_ids and provider selection remain root responsibilities.",
  "ARN syntax and generated-suffix shape do not prove resource existence or provenance; callers must supply the actual existing resource outputs.",
  "Trust propagation, other identity/resource policies, SCPs, boundaries, KMS key policy, service-supplied context and runtime connectivity remain unverified.",
  "This role has no VPC ENI permissions; VPC-enabled Lambda requires a separately reviewed extension.",
]


def require(condition, code):
  if not condition:
    raise ValueError(code)


def canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256(value):
  return hashlib.sha256(canonical(value).encode()).hexdigest()


def unique_object(pairs):
  result = {}
  for key, value in pairs:
    require(key not in result, "json_duplicate_key")
    result[key] = value
  return result


def reject_constant(value):
  raise ValueError("json_nonfinite_number")


def parse_json(text):
  return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


def strings(value):
  values = [value] if isinstance(value, str) else value
  require(isinstance(values, list) and values and all(isinstance(item, str) and item for item in values), "string_list_shape")
  require(len(set(values)) == len(values), "duplicate_value")
  return values


def json_document(value):
  require(isinstance(value, str), "policy_json_type")
  try:
    result = parse_json(value)
  except json.JSONDecodeError as error:
    raise ValueError("policy_json_malformed") from error
  require(isinstance(result, dict) and set(result) == {"Version", "Statement"}
      and result["Version"] == "2012-10-17", "policy_document_shape")
  require(isinstance(result["Statement"], list) and result["Statement"], "policy_statements_shape")
  return result


def validate_scope(scope):
  require(isinstance(scope, dict) and set(scope) == SCOPE_KEYS, "scope_shape")
  require(isinstance(scope["role_name"], str) and re.fullmatch(r"[A-Za-z0-9_+=,.@-]{1,64}", scope["role_name"]), "scope_role_name")
  require(scope["partition"] in {"aws", "aws-us-gov"}, "scope_partition")
  require(isinstance(scope["account_id"], str) and re.fullmatch(r"[0-9]{12}", scope["account_id"]), "scope_account")
  region = scope["region"]
  require(isinstance(region, str) and len(region) <= 63 and re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]+)+-[0-9]+", region), "scope_region")
  require((region.startswith("us-gov-")) == (scope["partition"] == "aws-us-gov")
      and not region.startswith(("cn-", "us-iso", "eu-iso")), "scope_partition_region")
  prefix = f"arn:{scope['partition']}:logs:{region}:{scope['account_id']}:log-group:"
  group = scope["log_group_arn"]
  require(isinstance(group, str) and group.startswith(prefix), "scope_log_group_account_region_partition")
  name = group[len(prefix):]
  require(re.fullmatch(r"[A-Za-z0-9_./#-]{1,512}", name) and not name.startswith("aws/"), "scope_log_group_bare_name")
  require(type(scope["enable_secret_read"]) is bool, "scope_secret_flag")
  secret, key = scope["secret_arn"], scope["secret_kms_key_arn"]
  if not scope["enable_secret_read"]:
    require(secret is None and key is None, "scope_disabled_secret_inputs")
  else:
    secret_prefix = f"arn:{scope['partition']}:secretsmanager:{region}:{scope['account_id']}:secret:"
    require(isinstance(secret, str) and len(secret) <= 2048 and secret.startswith(secret_prefix), "scope_secret_account_region_partition")
    require(re.fullmatch(r"[A-Za-z0-9/_+=.@-]{1,512}-[A-Za-z0-9]{6}", secret[len(secret_prefix):]), "scope_secret_full_suffix")
    if key is not None:
      key_prefix = f"arn:{scope['partition']}:kms:{region}:{scope['account_id']}:key/"
      require(isinstance(key, str) and len(key) <= 256 and key.startswith(key_prefix), "scope_kms_account_region_partition")
      require(re.fullmatch(r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})", key[len(key_prefix):]), "scope_kms_key_id")
  return scope


def expected_kms_conditions(scope):
  # AWS KMS explicitly documents amazonaws.com for ViaService in all partitions.
  # This is a condition value, not inference from a service's DNS endpoint.
  return {"StringEquals": {
    "kms:CallerAccount": scope["account_id"],
    "kms:ViaService": f"secretsmanager.{scope['region']}.amazonaws.com",
    "kms:EncryptionContext:SecretARN": scope["secret_arn"],
  }}


def normalized_condition(condition):
  require(isinstance(condition, dict) and not set(condition) - {"StringEquals"}, "condition_operator")
  normalized = {}
  for operator, entries in condition.items():
    require(isinstance(entries, dict) and entries, "condition_shape")
    keys = {}
    for key, value in entries.items():
      require(isinstance(key, str) and key.casefold() not in keys, "condition_key_collision")
      keys[key.casefold()] = sorted(strings(value))
    normalized[operator] = keys
  return canonical(normalized)


def expected_records(scope):
  records = {(action.casefold(), scope["log_group_arn"] + ":log-stream:*", normalized_condition({})) for action in LOG_ACTIONS}
  if scope["enable_secret_read"]:
    records |= {(action.casefold(), scope["secret_arn"], normalized_condition({})) for action in SECRET_ACTIONS}
  if scope["secret_kms_key_arn"] is not None:
    records.add(("kms:decrypt", scope["secret_kms_key_arn"], normalized_condition(expected_kms_conditions(scope))))
  return records


def verify_trust(trust):
  require(len(trust["Statement"]) == 1, "trust_statement_count")
  statement = trust["Statement"][0]
  require(isinstance(statement, dict) and not set(statement) - {"Sid", "Effect", "Action", "Principal"}, "trust_elements")
  require("Sid" not in statement or isinstance(statement["Sid"], str)
      and re.fullmatch(r"[A-Za-z0-9]+", statement["Sid"]), "trust_statement_identity")
  require(statement.get("Effect") == "Allow" and {action.casefold() for action in strings(statement.get("Action"))} == {"sts:assumerole"}, "trust_action_effect")
  principal = statement.get("Principal")
  require(isinstance(principal, dict) and set(principal) == {"Service"}
      and strings(principal["Service"]) == ["lambda.amazonaws.com"], "trust_principal")


def verify_identity(policy, scope):
  records, identifiers = set(), set()
  for statement in policy["Statement"]:
    require(isinstance(statement, dict) and not set(statement) - {"Sid", "Effect", "Action", "Resource", "Condition"}, "identity_elements")
    require(statement.get("Effect") == "Allow", "identity_effect")
    if "Sid" in statement:
      sid = statement["Sid"]
      require(isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9]+", sid) and sid not in identifiers, "statement_identity")
      identifiers.add(sid)
    actions, resources = strings(statement.get("Action")), strings(statement.get("Resource"))
    require(all(re.fullmatch(r"[a-z0-9-]+:[A-Za-z0-9]+", action, re.I) for action in actions), "action_selector")
    require(len({action.casefold() for action in actions}) == len(actions), "action_collision")
    condition = normalized_condition(statement.get("Condition", {}))
    for action in actions:
      for resource in resources:
        current = (action.casefold(), resource, condition)
        require(current not in records, "duplicate_grant")
        records.add(current)
  require(records == expected_records(scope), "permission_boundary")


def reference_pattern(template):
  return "".join("[^:]+" if value.startswith("${") else re.escape(value)
      for value in re.split(r"(\$\{[^}]+\})", template))


def references_index(documents):
  indexed = {}
  for service, document in documents.items():
    require(isinstance(document, dict) and document.get("ServiceName") == SERVICE_NAMES[service]
        and document.get("Version") == "v1.5", "reference_schema")
    actions, resources = document.get("Actions"), document.get("Resources")
    require(isinstance(actions, list) and isinstance(resources, list), "reference_collections")
    action_index, resource_index = {}, {}
    for action in actions:
      require(isinstance(action, dict) and isinstance(action.get("Name"), str)
          and action["Name"] not in action_index, "reference_action_identity")
      action_index[action["Name"]] = action
    require(len({name.casefold() for name in action_index}) == len(action_index), "reference_action_case_collision")
    for resource in resources:
      require(isinstance(resource, dict) and isinstance(resource.get("Name"), str)
          and resource["Name"] not in resource_index and isinstance(resource.get("ARNFormats"), list), "reference_resource_identity")
      resource_index[resource["Name"]] = resource
    require(len({name.casefold() for name in resource_index}) == len(resource_index), "reference_resource_case_collision")
    indexed[service] = (action_index, resource_index)
  require(set(indexed) == set(SERVICE_NAMES), "reference_service_set")
  return indexed


def verify_reference(policy, references):
  for statement in policy["Statement"]:
    for action in strings(statement["Action"]):
      service, _, name = action.partition(":")
      service = service.casefold()
      allowed_action = next((value for value in REQUIRED_TYPES if value.casefold() == action.casefold()), None)
      name = next((value for value in references.get(service, ({}, {}))[0] if value.casefold() == name.casefold()), None)
      require(service in references and name is not None and allowed_action is not None, "reference_action")
      entry = references[service][0][name]
      kinds = {item["Name"]: item for item in entry.get("Resources", [])}
      kind = REQUIRED_TYPES[allowed_action]
      require(kind in kinds and kind in references[service][1], "reference_required_resource")
      resource = references[service][1][kind]
      for arn in strings(statement["Resource"]):
        require(any(re.fullmatch(reference_pattern(template), arn) for template in resource["ARNFormats"]), "reference_arn_compatibility")
      allowed = set(entry.get("ActionConditionKeys", [])) | set(kinds[kind].get("ConditionKeys", [])) | set(resource.get("ConditionKeys", []))
      for entries in statement.get("Condition", {}).values():
        for key in entries:
          require(any(re.fullmatch(reference_pattern(template), key, re.I) for template in allowed), "reference_condition_key")


def glob_matches(pattern, value, casefold=False):
  if casefold:
    pattern, value = pattern.casefold(), value.casefold()
  expression = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
  return re.fullmatch(expression, value) is not None


def identity_decision(policy, action, resource, context):
  """Only StringEquals/IfExists plus simple selectors, for these witnesses.

  Wildcards are understood here solely to expose unsafe mutations. The structural
  verifier above never permits them except the reviewed terminal stream wildcard.
  Unknown operators/elements are rejected, never treated as a passing denial.
  """
  normalized_context = {key.casefold(): value for key, value in context.items()}
  require(len(normalized_context) == len(context), "matrix_context_collision")
  effects = []
  for statement in policy["Statement"]:
    require(not set(statement) - {"Sid", "Effect", "Action", "Resource", "Condition"}, "matrix_elements")
    require(statement.get("Effect") in {"Allow", "Deny"}, "matrix_effect")
    condition = statement.get("Condition", {})
    require(isinstance(condition, dict) and not set(condition) - {"StringEquals", "StringEqualsIfExists"}, "matrix_condition_operator")
    matches = True
    for operator, entries in condition.items():
      require(isinstance(entries, dict), "matrix_condition_shape")
      keys = {key.casefold(): value for key, value in entries.items()}
      require(len(keys) == len(entries), "matrix_condition_collision")
      for key, value in keys.items():
        actual = normalized_context.get(key)
        matches = matches and ((actual is None and operator == "StringEqualsIfExists") or actual in strings(value))
    if matches and any(glob_matches(pattern, action, True) for pattern in strings(statement["Action"])) and any(glob_matches(pattern, resource) for pattern in strings(statement["Resource"])):
      effects.append(statement["Effect"])
  return "explicit_deny" if "Deny" in effects else "allowed" if "Allow" in effects else "not_granted"


def trust_decision(trust, principal_type, principal, action):
  effects = []
  for statement in trust["Statement"]:
    require(not set(statement) - {"Sid", "Effect", "Action", "Principal"}, "trust_matrix_elements")
    current = statement.get("Principal")
    matches = current == "*" or (isinstance(current, dict) and principal_type in current
        and any(glob_matches(value, principal) for value in strings(current[principal_type])))
    if matches and any(glob_matches(value, action, True) for value in strings(statement["Action"])):
      effects.append(statement["Effect"])
  return "explicit_deny" if "Deny" in effects else "allowed" if "Allow" in effects else "not_granted"


def matrix_cases(scope):
  partition, account, region = (scope[key] for key in ("partition", "account_id", "region"))
  other_account = "000000000099" if account != "000000000099" else "000000000098"
  other_region = "us-gov-east-1" if partition == "aws-us-gov" and region != "us-gov-east-1" else "us-gov-west-1" if partition == "aws-us-gov" else "us-west-2" if region != "us-west-2" else "us-east-2"
  group = scope["log_group_arn"]
  stream = group + ":log-stream:synthetic-stream"
  secret = scope["secret_arn"] or f"arn:{partition}:secretsmanager:{region}:{account}:secret:portfolio/test/reference-ABC123"
  key = scope["secret_kms_key_arn"] or f"arn:{partition}:kms:{region}:{account}:key/00000000-0000-0000-0000-000000000000"
  other_secret = secret + "-unrelated-XYZ987"
  other_key = key.rsplit("/", 1)[0] + "/11111111-1111-1111-1111-111111111111"
  if other_key == key:
    other_key = key.rsplit("/", 1)[0] + "/22222222-2222-2222-2222-222222222222"
  context = {"kms:CallerAccount": account, "kms:ViaService": f"secretsmanager.{region}.amazonaws.com", "kms:EncryptionContext:SecretARN": secret}
  cases = []

  def add(identifier, action, resource, allowed=False, supplied=None):
    cases.append({"id": identifier, "action": action, "resource": resource,
      "context": {} if supplied is None else supplied, "expected": "allowed" if allowed else "not_granted"})

  for action in sorted(LOG_ACTIONS):
    add("logs-" + action.split(":")[1], action, stream, True)
  add("logs-other-group", "logs:PutLogEvents", group + "-unrelated:log-stream:synthetic-stream")
  add("logs-other-account", "logs:PutLogEvents", stream.replace(":" + account + ":", ":" + other_account + ":", 1))
  add("logs-other-region", "logs:PutLogEvents", stream.replace(":" + region + ":", ":" + other_region + ":", 1))
  for action in ("CreateLogGroup", "DeleteLogGroup", "PutRetentionPolicy", "PutLogGroupDeletionProtection"):
    add("forbidden-logs-" + action, "logs:" + action, group)
  add("forbidden-logs-DeleteLogStream", "logs:DeleteLogStream", stream)
  add("forbidden-logs-PutResourcePolicy", "logs:PutResourcePolicy", "*")
  for action in ("iam:CreateRole", "iam:PassRole", "sts:AssumeRole"):
    add("forbidden-" + action.replace(":", "-"), action, f"arn:{partition}:iam::{account}:role/SyntheticOtherRole")
  add("forbidden-vpc-eni", "ec2:CreateNetworkInterface", "*")
  for action in sorted(SECRET_ACTIONS):
    add("secret-" + action.split(":")[1], action, secret, scope["enable_secret_read"])
  add("secret-other-reference", "secretsmanager:GetSecretValue", other_secret)
  add("secret-other-account", "secretsmanager:GetSecretValue", secret.replace(":" + account + ":", ":" + other_account + ":", 1))
  add("secret-other-region", "secretsmanager:GetSecretValue", secret.replace(":" + region + ":", ":" + other_region + ":", 1))
  for action in ("CreateSecret", "PutSecretValue", "UpdateSecret", "DeleteSecret", "TagResource", "UntagResource", "PutResourcePolicy", "ReplicateSecretToRegions"):
    add("forbidden-secret-" + action, "secretsmanager:" + action, secret)
  for action in ("ListSecrets", "BatchGetSecretValue"):
    add("forbidden-secret-" + action, "secretsmanager:" + action, "*")
  add("kms-approved", "kms:Decrypt", key, scope["secret_kms_key_arn"] is not None, context)
  add("kms-other-key", "kms:Decrypt", other_key, supplied=context)
  add("kms-other-secret-context", "kms:Decrypt", key, supplied={**context, "kms:EncryptionContext:SecretARN": other_secret})
  add("kms-other-service", "kms:Decrypt", key, supplied={**context, "kms:ViaService": f"ec2.{region}.amazonaws.com"})
  add("kms-missing-service", "kms:Decrypt", key, supplied={name: value for name, value in context.items() if name != "kms:ViaService"})
  add("kms-other-caller", "kms:Decrypt", key, supplied={**context, "kms:CallerAccount": other_account})
  add("kms-missing-caller", "kms:Decrypt", key, supplied={name: value for name, value in context.items() if name != "kms:CallerAccount"})
  for action in ("GenerateDataKey", "CreateGrant", "Encrypt"):
    add("forbidden-kms-" + action, "kms:" + action, key, supplied=context)
  return cases


def run_matrix(trust, policy, scope):
  identity = []
  for case in matrix_cases(scope):
    actual = identity_decision(policy, case["action"], case["resource"], case["context"])
    require(actual == case["expected"], "authorization_matrix_mismatch:" + case["id"])
    identity.append({"id": case["id"], "action": case["action"], "expected": case["expected"], "actual": actual})
  trusted = [("lambda-assumption", "Service", "lambda.amazonaws.com", "sts:AssumeRole", "allowed"),
    ("other-service", "Service", "ec2.amazonaws.com", "sts:AssumeRole", "not_granted"),
    ("account-principal", "AWS", f"arn:{scope['partition']}:iam::{scope['account_id']}:root", "sts:AssumeRole", "not_granted"),
    ("extra-trust-action", "Service", "lambda.amazonaws.com", "sts:TagSession", "not_granted"),
    ("web-identity", "Federated", "synthetic-oidc", "sts:AssumeRoleWithWebIdentity", "not_granted")]
  for identifier, kind, principal, action, expected in trusted:
    actual = trust_decision(trust, kind, principal, action)
    require(actual == expected, "trust_matrix_mismatch:" + identifier)
    identity.append({"id": identifier, "action": action, "expected": expected, "actual": actual})
  return identity


def verify_plan(plan, references, run=None):
  resources = plan.get("resource_changes")
  require(isinstance(resources, list) and Counter(resource.get("type") for resource in resources) == {kind: 1 for kind in INVENTORY}, "resource_inventory")
  require(all(resource.get("name") == "this" and resource.get("address") == resource.get("type") + ".this"
      and "index" not in resource and resource.get("mode") == "managed" and resource.get("change", {}).get("actions") == ["create"] for resource in resources), "resource_lifecycle_identity")
  required = {
    "aws_iam_role": {"name", "arn", "path", "max_session_duration", "assume_role_policy", "tags"},
    "aws_iam_role_policy": {"name", "role", "policy"},
    "aws_cloudwatch_log_group": {"name", "arn", "retention_in_days", "deletion_protection_enabled", "log_group_class", "skip_destroy", "kms_key_id", "tags"},
    "aws_lambda_function": {"function_name", "arn", "invoke_arn", "role", "s3_bucket", "s3_key", "s3_object_version", "runtime", "handler", "package_type", "publish", "memory_size", "timeout", "architectures", "ephemeral_storage", "logging_config", "tracing_config", "environment", "vpc_config", "layers", "reserved_concurrent_executions", "tags"},
  }
  for resource in resources:
    change = resource["change"]
    require(resource.get("provider_name") == "registry.terraform.io/hashicorp/aws" and change.get("before") is None
        and isinstance(change.get("after"), dict) and isinstance(change.get("after_unknown"), dict), "resource_change_metadata")
    for name in required[resource["type"]]:
      require(name in change["after"] and not any_unknown(change["after_unknown"].get(name, False)), "required_resource_field:" + name)
  values = {resource["type"]: resource["change"]["after"] for resource in resources}
  outputs = plan.get("output_changes", {})
  require(isinstance(outputs, dict) and "permission_scope" in outputs, "scope_output_missing")
  require(not any_unknown(outputs["permission_scope"].get("after_unknown", False)), "scope_output_unknown")
  scope = validate_scope(outputs["permission_scope"].get("after"))
  role, inline = values["aws_iam_role"], values["aws_iam_role_policy"]
  require(role.get("name") == scope["role_name"] and role.get("path") == "/" and role.get("max_session_duration") == 3600, "role_identity_configuration")
  require(role.get("arn") == f"arn:{scope['partition']}:iam::{scope['account_id']}:role/{scope['role_name']}", "role_arn_scope")
  require(not role.get("managed_policy_arns") and not role.get("inline_policy"), "unreviewed_role_grants")
  require(inline.get("name") == POLICY_NAME and inline.get("role") == role["name"], "inline_policy_binding")
  trust, policy = json_document(role.get("assume_role_policy")), json_document(inline.get("policy"))
  require(len("".join(role["assume_role_policy"].split())) <= 2048 and len("".join(inline["policy"].split())) <= 10240, "policy_size_quota")
  verify_trust(trust)
  verify_identity(policy, scope)
  verify_reference(policy, references)
  for name, expected in {"execution_role_arn": role["arn"], "execution_role_name": role["name"],
      "inline_policy_name": inline["name"], "log_group_arn": scope["log_group_arn"],
      "secret_read_enabled": scope["enable_secret_read"]}.items():
    require(name in outputs and not any_unknown(outputs[name].get("after_unknown", False))
        and canonical(outputs[name].get("after")) == canonical(expected), "resource_output_binding:" + name)
  verify_workload(values, outputs, scope, run)
  matrix = run_matrix(trust, policy, scope)
  grant_matrix = [{"action": action, "resource_type": REQUIRED_TYPES_CASEFOLD[action.casefold()],
    "resource_sha256": sha256(resource), "condition_keys": sorted(key for entries in statement.get("Condition", {}).values() for key in entries)}
    for statement in policy["Statement"] for action in strings(statement["Action"]) for resource in strings(statement["Resource"])]
  return {"scope": scope, "trust": trust, "policy": policy, "matrix": matrix, "grant_matrix": grant_matrix,
    "trust_sha256": sha256(trust), "policy_sha256": sha256(policy),
    "policy_size": len("".join(inline["policy"].split()))}


def verify_workload(values, outputs, scope, run):
  """Inspect the actual complete four-resource workload, not a filtered IAM plan."""
  role, group, function = (values[kind] for kind in ("aws_iam_role", "aws_cloudwatch_log_group", "aws_lambda_function"))
  require(group.get("arn") == scope["log_group_arn"] and group["arn"] ==
      f"arn:{scope['partition']}:logs:{scope['region']}:{scope['account_id']}:log-group:{group.get('name')}", "owned_log_identity")
  verify_log_configuration(group)
  expected_retention = {"logging_minimum_finite_retention": 1, "logging_weekly_retention": 7,
      "logging_supported_400_day_retention": 400, "logging_supported_731_day_retention": 731,
      "logging_maximum_supported_retention": 3653}.get(run, 30)
  require(group["retention_in_days"] == expected_retention and group["deletion_protection_enabled"] is
      (run != "logging_explicit_disposable_development_override"), "owned_log_effective_lifecycle")
  expected_key = None
  if run in {"logging_existing_symmetric_key_reference", "logging_existing_multi_region_key_reference", "logging_govcloud_partition_key_syntax"}:
    identifier = "mrk-00000000000000000000000000000000" if run == "logging_existing_multi_region_key_reference" else "00000000-0000-0000-0000-000000000000"
    expected_key = f"arn:{scope['partition']}:kms:{scope['region']}:{scope['account_id']}:key/{identifier}"
  require(group.get("kms_key_id") == expected_key, "owned_log_effective_key")
  key = group.get("kms_key_id")
  require(key is None or isinstance(key, str) and key.startswith(
      f"arn:{scope['partition']}:kms:{scope['region']}:{scope['account_id']}:key/"), "log_key_scope")
  require(function.get("role") == role["arn"], "function_owned_role_binding")
  logging = function.get("logging_config")
  require(isinstance(logging, list) and len(logging) == 1 and logging[0].get("log_group") == group["name"]
      and logging[0].get("log_format") == "Text", "function_owned_log_binding")
  require(function.get("arn") == f"arn:{scope['partition']}:lambda:{scope['region']}:{scope['account_id']}:function:{function.get('function_name')}"
      and function.get("invoke_arn") == f"arn:{scope['partition']}:apigateway:{scope['region']}:lambda:path/2015-03-31/functions/{function['arn']}/invocations", "function_identity_scope")
  require(function.get("package_type") == "Zip" and function.get("publish") is False
      and function.get("s3_bucket") == "portfolio-test-artifacts" and function.get("s3_key") == "lambda/test/function.zip"
      and function.get("s3_object_version") == "synthetic-version-001", "function_versioned_artifact")
  require(not function.get("filename") and not function.get("image_uri") and function.get("kms_key_arn") is None,
      "function_no_unreviewed_delivery")
  require(function.get("runtime") in {"python3.13", "nodejs22.x", "java21"} and function.get("architectures") in (["x86_64"], ["arm64"])
      and type(function.get("memory_size")) is int and 128 <= function["memory_size"] <= 10240
      and type(function.get("timeout")) is int and 1 <= function["timeout"] <= 900
      and function.get("tracing_config") == [{"mode": "PassThrough"}], "function_compute_tracing")
  require(isinstance(function.get("ephemeral_storage"), list) and len(function["ephemeral_storage"]) == 1
      and 512 <= function["ephemeral_storage"][0].get("size", 0) <= 10240, "function_storage")
  defaults = {"memory_size": 128, "timeout": 10, "architectures": ["x86_64"], "ephemeral_storage": [{"size": 512}], "runtime": "python3.13", "handler": "app.handler"}
  overrides = {
    "lambda_node_runtime_and_compute_overrides": {"memory_size": 512, "timeout": 30, "ephemeral_storage": [{"size": 1024}], "runtime": "nodejs22.x", "handler": "index.handler"},
    "lambda_java_runtime_on_arm64": {"memory_size": 1024, "architectures": ["arm64"], "runtime": "java21", "handler": "org.example.Handler::handleRequest"},
    "lambda_maximum_compute_boundaries": {"memory_size": 10240, "timeout": 900, "ephemeral_storage": [{"size": 10240}]},
    "lambda_minimum_timeout_and_name_description_boundaries": {"timeout": 1},
  }
  defaults.update(overrides.get(run, {}))
  require(all(function.get(name) == value for name, value in defaults.items()), "function_effective_configuration")
  expected_env = {}
  if run == "lambda_nonsecret_configuration_and_secret_reference":
    expected_env = {"APP_MODE": "test", "SECRET_ARN": "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/metadata-ABC123"}
  elif run == "lambda_environment_byte_boundary":
    expected_env = {"APP_MODE": " " * 4087 + "x"}
  env = function.get("environment") or []
  require((env[0].get("variables") if len(env) == 1 else {} if not env else None) == expected_env, "function_nonsecret_environment")
  require(function.get("reserved_concurrent_executions") == {"lambda_existing_versioned_layers_and_concurrency": 20,
      "lambda_maximum_layer_count_and_zero_concurrency": 0}.get(run), "function_concurrency_contract")
  require(not function.get("layers") or run in {"lambda_existing_versioned_layers_and_concurrency", "lambda_maximum_layer_count_and_zero_concurrency"}, "function_layer_contract")
  require(not function.get("vpc_config") or run in {"lambda_existing_vpc_references", "lambda_maximum_vpc_reference_counts"}, "function_no_unreviewed_vpc")
  # Native cases cover every optional input boundary; these check actual structure.
  vpc = function.get("vpc_config") or []
  require(not vpc or len(vpc) == 1 and vpc[0].get("subnet_ids") and vpc[0].get("security_group_ids"), "function_vpc_contract")
  expected = {"function_arn": function["arn"], "function_name": function["function_name"],
      "invoke_arn": function["invoke_arn"], "version": function["version"], "runtime": function["runtime"],
      "architecture": function["architectures"][0], "log_group_name": group["name"],
      "log_retention_in_days": group["retention_in_days"], "log_deletion_protection_enabled": group["deletion_protection_enabled"],
      "log_group_class": group["log_group_class"], "log_kms_key_arn": key,
      "vpc_configuration": {"subnet_ids": sorted(vpc[0]["subnet_ids"]) if vpc else [],
          "security_group_ids": sorted(vpc[0]["security_group_ids"]) if vpc else []}}
  for name, value in expected.items():
    require(name in outputs and outputs[name].get("after_sensitive") is False
        and not any_unknown(outputs[name].get("after_unknown", False))
        and canonical(outputs[name].get("after")) == canonical(value), "workload_output_binding:" + name)
  require(set(outputs) == set(expected) | {"execution_role_arn", "execution_role_name", "inline_policy_name",
      "log_group_arn", "secret_read_enabled", "permission_scope"}, "workload_output_inventory")


def verify_log_configuration(group):
  require(isinstance(group, dict) and isinstance(group.get("name"), str)
      and re.fullmatch(r"[A-Za-z0-9_./#-]{1,512}", group["name"]) and not group["name"].startswith("aws/"), "owned_log_name")
  require(type(group.get("retention_in_days")) is int and group["retention_in_days"] in
      {1,3,5,7,14,30,60,90,120,150,180,365,400,545,731,1096,1827,2192,2557,2922,3288,3653}
      and type(group.get("deletion_protection_enabled")) is bool and group.get("log_group_class") == "STANDARD"
      and group.get("skip_destroy") is False and "kms_key_id" in group, "owned_log_lifecycle")


def compact_events(path):
  """Discard repeated provider schemas, retaining the actual security evidence."""
  for line in Path(path).open(encoding="utf-8"):
    event = parse_json(line)
    require(isinstance(event, dict), "capture_event_shape")
    if event.get("type") == "test_plan":
      actual = event["test_plan"]
      event["test_plan"] = {"resource_changes": actual.get("resource_changes", []), "output_changes": actual.get("output_changes", {})}
    yield event


def any_unknown(value):
  if isinstance(value, dict):
    return any(any_unknown(item) for item in value.values())
  if isinstance(value, list):
    return any(any_unknown(item) for item in value)
  require(type(value) is bool, "unknown_metadata_shape")
  return value


def verify_rejected_plan(plan, run):
  """Validate every resource in a deliberately rejected partial workload plan.

  Invalid inputs may leave logs, a safe role, or the safe log/role/policy subset.
  Never count these as complete positive workloads or silently discard grants.
  Exact reviewed per-case shapes are pinned from the successful native capture.
  """
  resources = plan["resource_changes"]
  kinds = sorted(resource.get("type", "") for resource in resources)
  require(kinds == REJECTED_SHAPES.get(run) and "aws_lambda_function" not in kinds
      and len(set(kinds)) == len(kinds) and set(kinds) <= INVENTORY, "rejected_input_resource_changes")
  values = {}
  for resource in resources:
    kind = resource["type"]
    require(resource.get("address") == kind + ".this" and resource.get("name") == "this"
        and "index" not in resource and resource.get("mode") == "managed"
        and resource.get("provider_name") == "registry.terraform.io/hashicorp/aws"
        and resource.get("change", {}).get("actions") == ["create"]
        and resource["change"].get("before") is None
        and isinstance(resource["change"].get("after_unknown"), dict), "rejected_input_resource_changes")
    value = resource["change"].get("after")
    require(isinstance(value, dict), "rejected_resource_configuration")
    values[kind] = value
    if kind == "aws_iam_role":
      require(value.get("path") == "/" and value.get("max_session_duration") == 3600
          and isinstance(value.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_+=,.@-]{1,64}", value["name"]), "rejected_role_configuration")
      require(not value.get("managed_policy_arns") and not value.get("inline_policy"), "rejected_role_grants")
      verify_trust(json_document(value.get("assume_role_policy")))
      tags = value.get("tags")
      require(isinstance(tags, dict) and len(tags) <= 50 and all(isinstance(key, str) and 1 <= len(key) <= 128
          and not key.casefold().startswith("aws:") and isinstance(item, str) and len(item) <= 256
          for key, item in tags.items()), "rejected_role_tags")
    if kind == "aws_cloudwatch_log_group":
      verify_log_configuration(value)
  if "aws_iam_role_policy" in values:
    require(set(values) == {"aws_cloudwatch_log_group", "aws_iam_role", "aws_iam_role_policy"}, "rejected_grant_dependencies")
    output = plan.get("output_changes", {}).get("permission_scope", {})
    require(not any_unknown(output.get("after_unknown", False)), "rejected_scope_unknown")
    scope = validate_scope(output.get("after"))
    group, role, inline = (values[kind] for kind in ("aws_cloudwatch_log_group", "aws_iam_role", "aws_iam_role_policy"))
    require(scope["log_group_arn"] == group["arn"] and scope["role_name"] == role["name"]
        and inline.get("role") == role["name"] and inline.get("name") == POLICY_NAME, "rejected_grant_binding")
    require(role.get("arn") == f"arn:{scope['partition']}:iam::{scope['account_id']}:role/{scope['role_name']}"
        and group.get("arn") == f"arn:{scope['partition']}:logs:{scope['region']}:{scope['account_id']}:log-group:{group['name']}", "rejected_grant_scope")
    verify_identity(json_document(inline.get("policy")), scope)
  return "+".join(kinds) or "empty"


def verify_capture(events, references, terraform_exit_code=0):
  require(terraform_exit_code == 0, "terraform_process_failure")
  passed, errors, seen_plans, terminal, summaries = set(), set(), set(), set(), []
  plans, negative, negative_shapes = {}, set(), Counter()
  declared, files, late = [], [], []
  for event in events:
    require(isinstance(event, dict), "capture_event_shape")
    if summaries:
      late.append(event)
    require(event.get("type") in {"version", "test_abstract", "test_run", "test_plan", "test_file", "diagnostic", "test_summary", "log"}, "capture_event_type")
    if event.get("type") == "test_abstract":
      declared.append(event.get("test_abstract"))
    if event.get("type") == "test_file" and "status" in event.get("test_file", {}):
      files.append((event["test_file"].get("path"), event["test_file"]["status"]))
    key = (event.get("@testfile"), event.get("@testrun"))
    if event.get("@level") == "error":
      errors.add(key)
    if event.get("type") == "test_run":
      status = event["test_run"].get("status")
      if status in {"pass", "fail", "error", "skip"}:
        require(key not in terminal, "duplicate_terminal_run")
        terminal.add(key)
        require(status == "pass", "nonpassing_native_run")
        passed.add(key)
    if event.get("type") == "test_plan":
      require(key in passed and key not in seen_plans, "plan_order_or_duplicate")
      seen_plans.add(key)
      plan = event["test_plan"]
      require(isinstance(plan, dict) and isinstance(plan.get("resource_changes"), list), "capture_plan_shape")
      if key[1] in POSITIVE_RUNS:
        require(key[1] not in plans, "duplicate_positive_name")
        plans[key[1]] = verify_plan(plan, references, key[1])
      else:
        negative_shapes[verify_rejected_plan(plan, key[1])] += 1
        negative.add(key)
    if event.get("type") == "test_summary":
      summaries.append(event["test_summary"])
  require(len(summaries) == 1 and isinstance(summaries[0], dict), "capture_unique_summary")
  expected = {"status": "pass", "passed": EXPECTED_TESTS, "failed": 0, "errored": 0, "skipped": 0}
  require(all(type(summaries[0].get(name)) is int for name in ("passed", "failed", "errored", "skipped"))
      and all(summaries[0].get(name) == value for name, value in expected.items()), "capture_summary_counts")
  require(passed == EXPECTED_RUNS and EXPECTED_TESTS > 0 and len(passed) == EXPECTED_TESTS and seen_plans == passed and terminal == passed
      and errors <= passed, "capture_run_completeness")
  require(set(plans) == POSITIVE_RUNS and len(negative) == EXPECTED_NEGATIVES, "capture_coverage")
  require(errors == negative, "capture_validation_error_coverage")
  require(negative_shapes == Counter("+".join(kinds) or "empty" for kinds in REJECTED_SHAPES.values()), "capture_rejected_plan_shapes")
  require(any(not plan["scope"]["enable_secret_read"] for plan in plans.values())
      and any(plan["scope"]["secret_kms_key_arn"] is not None for plan in plans.values()), "capture_optional_coverage")
  manifest = {}
  for case in MANIFEST:
    manifest.setdefault(case["new_file"], set()).add(case["new_run"])
  require(len(declared) == 1 and isinstance(declared[0], dict)
      and {file: set(names) for file, names in declared[0].items()} == manifest
      and sum(len(names) for names in declared[0].values()) == EXPECTED_TESTS, "capture_declared_manifest")
  require(len(files) == len(manifest) and set(files) == {(file, "pass") for file in manifest}, "capture_file_completeness")
  require(not late, "capture_after_summary")
  return plans


def semantic_mutations(plans, references):
  """Expose unauthorized Allows by mutating actual documents, not checksums."""
  disabled = next(plan for plan in plans.values() if not plan["scope"]["enable_secret_read"])
  enabled = next(plan for plan in plans.values() if plan["scope"]["secret_kms_key_arn"] is not None)
  results = []

  def identity_mutation(identifier, baseline, case_id, change):
    policy = copy.deepcopy(baseline["policy"])
    case = next(case for case in matrix_cases(baseline["scope"]) if case["id"] == case_id)
    before = identity_decision(policy, case["action"], case["resource"], case["context"])
    change(policy, case)
    after = identity_decision(policy, case["action"], case["resource"], case["context"])
    require(before == "not_granted" and after == "allowed", "mutation_witness_not_exposed:" + identifier)
    try:
      verify_identity(policy, baseline["scope"])
    except ValueError:
      pass
    else:
      raise ValueError("mutation_not_detected:" + identifier)
    approved_context = expected_kms_conditions(baseline["scope"])["StringEquals"]
    relations = {key: "absent" if key not in case["context"] else
        "approved" if case["context"][key] == value else "other"
        for key, value in approved_context.items()}
    results.append({"id": identifier, "evidence": "static_unauthorized_allow_witness", "before": before,
      "after": after, "detected": True, "case_id": case["id"], "action": case["action"],
      "resource_sha256": sha256(case["resource"]), "context_sha256": sha256(case["context"]),
      "context_relations": relations,
      "baseline_sha256": baseline["policy_sha256"], "mutated_sha256": sha256(policy)})

  def add_grant(policy, case):
    statement = copy.deepcopy(policy["Statement"][0])
    statement.update(Sid="SyntheticUnsafeAddition", Action=[case["action"]], Resource=[case["resource"]])
    statement.pop("Condition", None)
    policy["Statement"].append(statement)

  identity_mutation("logs-create-group", disabled, "forbidden-logs-CreateLogGroup", add_grant)
  identity_mutation("logs-wildcard-resource", disabled, "logs-other-group", lambda policy, case: policy["Statement"][0].update(Resource=["*"]))
  identity_mutation("disabled-secret-grant", disabled, "secret-GetSecretValue", add_grant)
  identity_mutation("unrelated-secret-reference", enabled, "secret-other-reference", lambda policy, case: next(statement for statement in policy["Statement"] if "secretsmanager:GetSecretValue" in strings(statement["Action"])).update(Resource=[case["resource"]]))
  identity_mutation("unrelated-kms-key", enabled, "kms-other-key", lambda policy, case: next(statement for statement in policy["Statement"] if "kms:Decrypt" in strings(statement["Action"])).update(Resource=[case["resource"]]))

  def remove_condition(key):
    def mutate(policy, case):
      entries = next(statement for statement in policy["Statement"] if "kms:Decrypt" in strings(statement["Action"]))["Condition"]["StringEquals"]
      del entries[next(name for name in entries if name.casefold() == key.casefold())]
    return mutate

  for identifier, case_id, key in (("kms-remove-secret-context", "kms-other-secret-context", "kms:EncryptionContext:SecretARN"),
      ("kms-remove-via-service", "kms-other-service", "kms:ViaService"),
      ("kms-missing-via-service", "kms-missing-service", "kms:ViaService"),
      ("kms-remove-caller-account", "kms-other-caller", "kms:CallerAccount")):
    identity_mutation(identifier, enabled, case_id, remove_condition(key))
  identity_mutation("iam-administration", disabled, "forbidden-iam-CreateRole", add_grant)
  identity_mutation("sts-lateral-assumption", disabled, "forbidden-sts-AssumeRole", add_grant)
  identity_mutation("pass-role", disabled, "forbidden-iam-PassRole", add_grant)
  identity_mutation("vpc-eni-grant", disabled, "forbidden-vpc-eni", add_grant)
  trust = copy.deepcopy(disabled["trust"])
  before = trust_decision(trust, "Service", "ec2.amazonaws.com", "sts:AssumeRole")
  trust["Statement"][0]["Principal"]["Service"] = ["lambda.amazonaws.com", "ec2.amazonaws.com"]
  after = trust_decision(trust, "Service", "ec2.amazonaws.com", "sts:AssumeRole")
  require(before == "not_granted" and after == "allowed", "trust_mutation_witness")
  try:
    verify_trust(trust)
  except ValueError:
    pass
  else:
    raise ValueError("trust_mutation_not_detected")
  results.append({"id": "trust-additional-service", "evidence": "static_unauthorized_trust_witness",
    "before": before, "after": after, "detected": True, "baseline_sha256": disabled["trust_sha256"], "mutated_sha256": sha256(trust)})
  return results


def capture_self_tests(events, references):
  cases = []
  summary = next(event for event in events if event.get("type") == "test_summary")
  cases.append(("missing_summary", [event for event in copy.deepcopy(events) if event.get("type") != "test_summary"], 0, "capture_unique_summary"))
  cases.append(("duplicate_summary", copy.deepcopy(events) + [copy.deepcopy(summary)], 0, "capture_unique_summary"))
  for field, value in (("passed", EXPECTED_TESTS - 1), ("skipped", 1), ("errored", 1), ("failed", 1)):
    changed = copy.deepcopy(events)
    next(event for event in changed if event.get("type") == "test_summary")["test_summary"][field] = value
    cases.append(("summary_" + field, changed, 0, "capture_summary_counts"))
  for field, value in (("passed", float(EXPECTED_TESTS)), ("skipped", False)):
    changed = copy.deepcopy(events)
    next(event for event in changed if event.get("type") == "test_summary")["test_summary"][field] = value
    cases.append(("summary_type_" + field, changed, 0, "capture_summary_counts"))
  cases.append(("process_error", copy.deepcopy(events), 1, "terraform_process_failure"))
  for field, value in (("type", "aws_iam_policy"), ("name", "unexpected"), ("mode", "data")):
    changed = copy.deepcopy(events)
    first = next(event for event in changed if event.get("type") == "test_plan")
    first["test_plan"]["resource_changes"][0][field] = value
    cases.append(("resource_" + field, changed, 0, "resource_inventory" if field == "type" else "resource_lifecycle_identity"))
  changed = copy.deepcopy(events)
  first = next(event for event in changed if event.get("type") == "test_plan")
  first["test_plan"]["resource_changes"].append(copy.deepcopy(first["test_plan"]["resource_changes"][0]))
  cases.append(("extra_resource", changed, 0, "resource_inventory"))
  changed = copy.deepcopy(events)
  first = next(event for event in changed if event.get("type") == "test_plan")
  first["test_plan"]["resource_changes"] = []
  cases.append(("empty_positive_plan", changed, 0, "resource_inventory"))
  changed = copy.deepcopy(events)
  first = next(event for event in changed if event.get("type") == "test_plan")
  negative = next(event for event in changed if event.get("type") == "test_plan" and not event["test_plan"]["resource_changes"])
  negative["test_plan"]["resource_changes"] = copy.deepcopy(first["test_plan"]["resource_changes"])
  cases.append(("resource_in_rejected_plan", changed, 0, "rejected_input_resource_changes"))
  for label in ("missing_plan", "duplicate_plan", "plan_before_pass"):
    changed = copy.deepcopy(events)
    first = next(event for event in changed if event.get("type") == "test_plan")
    if label == "missing_plan":
      changed.remove(first)
      reason = "capture_run_completeness"
    elif label == "duplicate_plan":
      changed.append(copy.deepcopy(first))
      reason = "plan_order_or_duplicate"
    else:
      changed.remove(first)
      changed.insert(0, first)
      reason = "plan_order_or_duplicate"
    cases.append((label, changed, 0, reason))
  changed = copy.deepcopy(events)
  changed.append({"type": "diagnostic", "@level": "error", "@testfile": "outside", "@testrun": "outside"})
  cases.append(("unaccounted_error", changed, 0, "capture_run_completeness"))
  changed = copy.deepcopy(events)
  positive = next(event for event in changed if event.get("type") == "test_plan")
  changed.append({"type": "diagnostic", "@level": "error", "@testfile": positive["@testfile"], "@testrun": positive["@testrun"]})
  cases.append(("error_in_positive_run", changed, 0, "capture_validation_error_coverage"))
  negative_error = next(event for event in events if event.get("@level") == "error")
  changed = [event for event in copy.deepcopy(events) if not (event.get("@level") == "error"
    and event.get("@testfile") == negative_error.get("@testfile") and event.get("@testrun") == negative_error.get("@testrun"))]
  cases.append(("missing_expected_validation_error", changed, 0, "capture_validation_error_coverage"))

  def add_plan_fault(identifier, change, reason):
    changed = copy.deepcopy(events)
    first = next(event for event in changed if event.get("type") == "test_plan")
    change(first["test_plan"])
    cases.append((identifier, changed, 0, reason))

  def role_of(plan):
    return next(resource["change"]["after"] for resource in plan["resource_changes"] if resource["type"] == "aws_iam_role")

  def inline_of(plan):
    return next(resource["change"]["after"] for resource in plan["resource_changes"] if resource["type"] == "aws_iam_role_policy")

  def change_document(plan, trust, mutate):
    source = role_of(plan) if trust else inline_of(plan)
    field = "assume_role_policy" if trust else "policy"
    document = json_document(source[field])
    mutate(document)
    source[field] = canonical(document)

  add_plan_fault("unexpected_trust_action", lambda plan: change_document(plan, True,
    lambda document: document["Statement"][0].update(Action=["sts:AssumeRole", "sts:TagSession"])), "trust_action_effect")
  add_plan_fault("malformed_trust_sid", lambda plan: change_document(plan, True,
    lambda document: document["Statement"][0].update(Sid={"unexpected": "object"})), "trust_statement_identity")
  add_plan_fault("unexpected_account_trust", lambda plan: change_document(plan, True,
    lambda document: document["Statement"][0].update(Principal={"AWS": "*"})), "trust_principal")
  add_plan_fault("unsupported_trust_condition", lambda plan: change_document(plan, True,
    lambda document: document["Statement"][0].update(Condition={"StringEquals": {"aws:SourceAccount": "000000000000"}})), "trust_elements")
  add_plan_fault("administrative_action_selector", lambda plan: change_document(plan, False,
    lambda document: document["Statement"][0].update(Action=["iam:*"])), "action_selector")
  add_plan_fault("wildcard_identity_resource", lambda plan: change_document(plan, False,
    lambda document: document["Statement"][0].update(Resource=["*"])), "permission_boundary")
  add_plan_fault("wrong_inline_role", lambda plan: inline_of(plan).update(role="UnreviewedRole"), "inline_policy_binding")
  add_plan_fault("wrong_actual_role_account", lambda plan: role_of(plan).update(arn="arn:aws:iam::000000000099:role/UnreviewedRole"), "role_arn_scope")
  add_plan_fault("scope_suffix_wildcard", lambda plan: plan["output_changes"]["permission_scope"]["after"].update(
    log_group_arn=plan["output_changes"]["permission_scope"]["after"]["log_group_arn"] + ":*"), "scope_log_group_bare_name")
  add_plan_fault("unknown_scope_output", lambda plan: plan["output_changes"]["permission_scope"].update(after_unknown=True), "scope_output_unknown")
  add_plan_fault("missing_scope_output", lambda plan: plan["output_changes"].pop("permission_scope"), "scope_output_missing")
  add_plan_fault("wrong_role_output", lambda plan: plan["output_changes"]["execution_role_arn"].update(after="unverified"), "resource_output_binding")
  add_plan_fault("hidden_embedded_policy", lambda plan: role_of(plan).update(inline_policy=[{"name": "Extra", "policy": "unreviewed"}]), "unreviewed_role_grants")
  add_plan_fault("hidden_managed_policy", lambda plan: role_of(plan).update(managed_policy_arns=["arn:aws:iam::aws:policy/AdministratorAccess"]), "unreviewed_role_grants")
  add_plan_fault("malformed_policy_json", lambda plan: inline_of(plan).update(policy="{"), "policy_json_malformed")
  add_plan_fault("duplicate_policy_key", lambda plan: inline_of(plan).update(policy='{"Statement":[],' + inline_of(plan)["policy"].lstrip()[1:]), "json_duplicate_key")
  changed = copy.deepcopy(events)
  negative = next(event for event in changed if event.get("type") == "test_plan" and event.get("@testrun") not in POSITIVE_RUNS and any(resource["type"] == "aws_iam_role" for resource in event["test_plan"]["resource_changes"]))
  change_document(negative["test_plan"], True, lambda document: document["Statement"][0].update(Principal="*"))
  cases.append(("unsafe_partial_role_trust", changed, 0, "trust_principal"))
  changed = copy.deepcopy(events)
  terminal = next(event for event in changed if event.get("type") == "test_run" and event["test_run"].get("status") == "pass")
  terminal["test_run"]["status"] = "skip"
  cases.append(("skipped_native_run", changed, 0, "nonpassing_native_run"))
  changed = copy.deepcopy(events)
  terminal = next(event for event in changed if event.get("type") == "test_run" and event["test_run"].get("status") == "pass")
  changed.insert(changed.index(terminal) + 1, copy.deepcopy(terminal))
  cases.append(("duplicate_pass_record", changed, 0, "duplicate_terminal_run"))
  for label, changed, status, reason in cases:
    try:
      verify_capture(changed, references, status)
    except ValueError as error:
      require(reason in str(error), "self_test_wrong_failure:" + label)
    else:
      raise ValueError("self_test_accepted_fault:" + label)
  try:
    list(compact_events_from_lines(['{"type":"test_summary"']))
  except json.JSONDecodeError:
    pass
  else:
    raise ValueError("self_test_accepted_truncated_json")
  for text, reason in (('{"type":"test_run","type":"test_summary"}', "json_duplicate_key"),
      ('{"value":NaN}', "json_nonfinite_number"),
      ('{"value":Infinity}', "json_nonfinite_number")):
    try:
      list(compact_events_from_lines([text]))
    except ValueError as error:
      require(reason in str(error), "self_test_wrong_json_failure")
    else:
      raise ValueError("self_test_accepted_ambiguous_json")
  return len(cases) + 4


def workload_plan_mutations(events, references):
  original = next(event["test_plan"] for event in events if event.get("type") == "test_plan"
      and event.get("@testrun") == "lambda_default_function_configuration")
  cases = []
  def add(name, kind, transform):
    plan = copy.deepcopy(original)
    resource = next(item for item in plan["resource_changes"] if item["type"] == kind)
    transform(resource["change"]["after"])
    try:
      verify_plan(plan, references, "lambda_default_function_configuration")
    except (ValueError, KeyError, TypeError):
      cases.append({"id": name, "detected": True, "evidence": "actual_four_resource_plan_mutation"})
      return
    raise ValueError("workload_mutation_accepted:" + name)
  add("function-unrelated-role", "aws_lambda_function", lambda v: v.update(role="arn:aws:iam::000000000000:role/Other"))
  add("function-unrelated-log", "aws_lambda_function", lambda v: v["logging_config"][0].update(log_group="/unrelated"))
  add("log-wrong-owner-arn", "aws_cloudwatch_log_group", lambda v: v.update(arn=v["arn"].replace("000000000000", "000000000099")))
  add("log-infinite-retention", "aws_cloudwatch_log_group", lambda v: v.update(retention_in_days=0))
  add("log-disable-default-protection", "aws_cloudwatch_log_group", lambda v: v.update(deletion_protection_enabled=False))
  add("log-skip-destroy", "aws_cloudwatch_log_group", lambda v: v.update(skip_destroy=True))
  add("log-unreviewed-kms", "aws_cloudwatch_log_group", lambda v: v.update(kms_key_id="arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000"))
  add("artifact-unrelated-bucket", "aws_lambda_function", lambda v: v.update(s3_bucket="unrelated-artifacts"))
  add("artifact-unrelated-key", "aws_lambda_function", lambda v: v.update(s3_key="other.zip"))
  add("artifact-null-version", "aws_lambda_function", lambda v: v.update(s3_object_version="null"))
  add("function-plaintext-environment", "aws_lambda_function", lambda v: v.update(environment=[{"variables": {"PASSWORD": "synthetic-negative-value"}}]))
  add("function-unreviewed-vpc", "aws_lambda_function", lambda v: v.update(vpc_config=[{"subnet_ids": ["subnet-00000000"], "security_group_ids": ["sg-00000000"]}]))
  add("function-publish-version", "aws_lambda_function", lambda v: v.update(publish=True))
  add("function-unreviewed-runtime", "aws_lambda_function", lambda v: v.update(runtime="nodejs20.x"))
  add("function-wrong-account", "aws_lambda_function", lambda v: v.update(arn=v["arn"].replace("000000000000", "000000000099")))
  return cases


def workload_capture_faults(events, references):
  cases = []
  def reject(name, mutate):
    changed = copy.deepcopy(events)
    mutate(changed)
    try:
      verify_capture(changed, references)
    except (ValueError, KeyError, TypeError):
      cases.append(name)
      return
    raise ValueError("workload_capture_fault_accepted:" + name)
  def first_plan(e):
    return next(x["test_plan"] for x in e if x.get("type") == "test_plan")
  reject("missing-terminal-file", lambda e: e.remove(next(x for x in e if x.get("type") == "test_file" and "status" in x["test_file"])))
  reject("missing-declared-manifest", lambda e: e.remove(next(x for x in e if x.get("type") == "test_abstract")))
  reject("late-capture-record", lambda e: e.append({"type": "log"}))
  reject("unknown-log-name", lambda e: first_plan(e)["resource_changes"][0]["change"]["after_unknown"].update(name=True))
  reject("missing-log-kms-null", lambda e: first_plan(e)["resource_changes"][0]["change"]["after"].pop("kms_key_id"))
  reject("missing-change-metadata", lambda e: first_plan(e)["resource_changes"][0]["change"].pop("after_unknown"))
  reject("wrong-resource-address", lambda e: first_plan(e)["resource_changes"][0].update(address="aws_cloudwatch_log_group.other"))
  return len(cases)


def reference_self_tests(references, plans):
  policy = next(plan["policy"] for plan in plans.values() if plan["scope"]["secret_kms_key_arn"] is not None)
  probes = []
  changed = copy.deepcopy(references)
  del changed["logs"][0]["CreateLogStream"]
  probes.append((changed, "reference_action"))
  changed = copy.deepcopy(references)
  changed["logs"][0]["CreateLogStream"]["Resources"] = [{"Name": "log-group"}]
  probes.append((changed, "reference_required_resource"))
  changed = copy.deepcopy(references)
  changed["logs"][1]["log-stream"]["ARNFormats"] = ["arn:invalid-format"]
  probes.append((changed, "reference_arn_compatibility"))
  changed = copy.deepcopy(references)
  changed["kms"][0]["Decrypt"]["ActionConditionKeys"] = [key for key in changed["kms"][0]["Decrypt"]["ActionConditionKeys"] if key != "kms:CallerAccount"]
  probes.append((changed, "reference_condition_key"))
  for changed, reason in probes:
    try:
      verify_reference(policy, changed)
    except ValueError as error:
      require(reason in str(error), "self_test_wrong_reference_failure")
    else:
      raise ValueError("self_test_accepted_bad_reference")
  try:
    parse_json('{"ServiceName":"CloudWatch Logs","ServiceName":"KMS"}')
  except ValueError as error:
    require("json_duplicate_key" in str(error), "self_test_wrong_duplicate_reference_failure")
  else:
    raise ValueError("self_test_accepted_duplicate_reference")
  return len(probes) + 1


def compact_events_from_lines(lines):
  for line in lines:
    yield parse_json(line)


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--test-events", required=True)
  parser.add_argument("--logs-reference", required=True)
  parser.add_argument("--secretsmanager-reference", required=True)
  parser.add_argument("--kms-reference", required=True)
  parser.add_argument("--terraform-exit-code", type=int, required=True)
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args(argv)
  references = references_index({service: parse_json(Path(path).read_text()) for service, path in (
    ("logs", args.logs_reference), ("secretsmanager", args.secretsmanager_reference), ("kms", args.kms_reference))})
  events = list(compact_events(args.test_events))
  plans = verify_capture(events, references, args.terraform_exit_code)
  mutations = semantic_mutations(plans, references) if args.self_test else []
  ownership_mutations = workload_plan_mutations(events, references) if args.self_test else []
  source_contract = verify_structure()
  source_mutations = structure_mutations() if args.self_test else 0
  failures = capture_self_tests(events, references) if args.self_test else 0
  extra_failures = workload_capture_faults(events, references) if args.self_test else 0
  reference_failures = reference_self_tests(references, plans) if args.self_test else 0
  negative_shapes = Counter("+".join(sorted(resource["type"] for resource in event["test_plan"]["resource_changes"])) or "empty"
      for event in events if event.get("type") == "test_plan" and event.get("@testrun") not in POSITIVE_RUNS)
  report = {"status": "passed", "evidence_type": "static_actual_workload_policy_verification", "aws_api_calls": 0,
    "native_tests": EXPECTED_TESTS, "positive_plans": len(plans), "negative_plans": EXPECTED_NEGATIVES,
    "negative_plan_shapes": dict(negative_shapes),
    "matrix_cases": sum(len(plan["matrix"]) for plan in plans.values()),
    "plan_evidence": {name: {"trust_sha256": plan["trust_sha256"], "policy_sha256": plan["policy_sha256"],
      "inline_policy_non_whitespace_characters": plan["policy_size"], "secret_read_enabled": plan["scope"]["enable_secret_read"],
      "customer_key_configured": plan["scope"]["secret_kms_key_arn"] is not None, "grant_matrix": plan["grant_matrix"],
      "authorization_matrix": plan["matrix"]} for name, plan in plans.items()},
    "semantic_mutations": mutations, "semantic_mutation_count": len(mutations),
    "capture_failure_injections": failures, "workload_capture_failure_injections": extra_failures,
    "workload_semantic_mutations": ownership_mutations, "workload_semantic_mutation_count": len(ownership_mutations),
    "source_contract": source_contract, "source_dependency_mutations": source_mutations, "reference_failure_injections": reference_failures, "limitations": LIMITATIONS}
  print(json.dumps(report, indent=2))
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except (ValueError, TypeError, KeyError, OSError, StopIteration) as error:
    # Only fixed diagnostic codes and case IDs are emitted; no raw IAM/ARN data.
    print("Execution-policy verification failed:", str(error), file=sys.stderr)
    raise SystemExit(1)
