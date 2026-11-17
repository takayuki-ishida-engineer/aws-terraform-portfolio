"""Independent, deliberately narrow static guardrail proof; never an AWS simulator.

Only exact action selectors, terminal resource-prefix patterns and the reviewed
condition operators below are understood. Every relevant Allow needs a structural
blocking certificate; finite synthetic examples alone are not a universal proof.
Canonical source hashes bind JSON content, not exported file bytes.
"""

import copy
import hashlib
import json
import re

POLICIES = ("developer_inline", "developer_secrets_manager")
ACTIONS = ("ec2:CreateTags", "secretsmanager:CreateSecret")
CREATE = {"vpc": "CreateVpc", "subnet": "CreateSubnet",
          "internet-gateway": "CreateInternetGateway", "route-table": "CreateRouteTable"}
# Exactly the approved tag keys (docs/deployment-configuration.md section 5).
TAGS = {"Name", "env", "managed", "project", "service"}
OPERATORS = {"StringEquals", "StringEqualsIfExists", "ForAllValues:StringEquals",
             "ForAllValues:StringNotEqualsIgnoreCase", "ForAnyValue:StringNotEqualsIgnoreCase",
             "Null", "BoolIfExists", "NumericGreaterThanEquals", "NumericLessThanEquals"}
KEYS = {"aws:principalaccount", "aws:requestedregion", "aws:resourcetag/project",
        "aws:requesttag/project", "aws:tagkeys", "ec2:createaction",
        "secretsmanager:addreplicaregions", "secretsmanager:forceoverwritereplicasecret",
        "secretsmanager:forcedeletewithoutrecovery", "secretsmanager:recoverywindowindays"}
LIMITATIONS = [
    "Independent static evidence only; not an AWS simulation or deployed-role authorization proof.",
    "Only two exact actions and the reviewed condition/resource forms are understood; unsupported input is inconclusive.",
    "All relevant Allow/Deny statements in both exported Developer documents are considered; other policies, SCPs, boundaries, sessions and service behavior are outside this proof.",
    "Synthetic contexts preserve absent keys; no context is added to an AWS request and no missing-context AWS result is upgraded.",
    "Empty arrays are treated as null datasets; API request validity and tag-key population by AWS are not proved.",
    "Source SHA256 uses canonical JSON (sorted keys, compact separators, ASCII), not raw exported manifest bytes."
]


class Unsupported(ValueError):
  """A fixed, sanitized reason why the narrow proof cannot be completed."""


def _hash(value):
  return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _list(value):
  result = value if isinstance(value, list) else [value]
  if not result or any(not isinstance(item, str) or not item for item in result):
    raise Unsupported("unsupported string/list shape")
  if len(set(result)) != len(result):
    raise Unsupported("duplicate policy value")
  return result


def _safe(value):
  if isinstance(value, dict):
    return {key: _safe(item) for key, item in value.items()}
  if isinstance(value, list):
    return [_safe(item) for item in value]
  if isinstance(value, str):
    return re.sub(r"\d{12}", "<account>", value)
  return value


def _conditions(statement):
  result = {}
  conditions = statement.get("Condition", {})
  if not isinstance(conditions, dict):
    raise Unsupported("unsupported condition structure")
  for operator, entries in conditions.items():
    if operator not in OPERATORS or not isinstance(entries, dict) or not entries:
      raise Unsupported("unsupported condition operator or structure")
    lowered = {}
    for key, raw in entries.items():
      if not isinstance(key, str) or key.casefold() not in KEYS or key.casefold() in lowered:
        raise Unsupported("unsupported or duplicate condition key")
      values = _list(raw)
      if any("${" in item for item in values):
        raise Unsupported("policy variables are unsupported")
      if operator.startswith("For") and key.casefold() != "aws:tagkeys":
        raise Unsupported("set operator on an unreviewed multivalue key")
      if operator in {"Null", "BoolIfExists"} and (len(values) != 1 or values[0] not in {"true", "false"}):
        raise Unsupported("unsupported boolean condition")
      if operator.startswith("Numeric") and (len(values) != 1 or not re.fullmatch(r"\d+", values[0])):
        raise Unsupported("unsupported numeric condition")
      lowered[key.casefold()] = values
    result[operator] = lowered
  return result


def _scope(scope):
  if not isinstance(scope, dict):
    raise Unsupported("missing scope")
  account, region, project = (scope.get(key) for key in ("account_id", "region", "project_tag"))
  accounts = scope.get("target_account_ids")
  if not isinstance(account, str) or not re.fullmatch(r"\d{12}", account):
    raise Unsupported("unsupported account scope")
  if not isinstance(accounts, list) or not accounts or account not in accounts or len(set(accounts)) != len(accounts):
    raise Unsupported("unsupported target account scope")
  if any(not isinstance(item, str) or not re.fullmatch(r"\d{12}", item) for item in accounts):
    raise Unsupported("unsupported target account scope")
  if not isinstance(region, str) or not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region):
    raise Unsupported("unsupported region scope")
  if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", project):
    raise Unsupported("unsupported project scope")
  match = re.fullmatch(r"arn:(aws|aws-us-gov|aws-cn):sso:::instance/ssoins-[a-zA-Z0-9]{16}", scope.get("instance_arn", ""))
  if not match:
    raise Unsupported("unsupported partition scope")
  return {"account": account, "accounts": accounts, "region": region, "project": project,
          "partition": match.group(1)}


def _statements(policies):
  result = []
  for policy in POLICIES:
    document = policies.get(policy)
    if not isinstance(document, dict) or set(document) - {"Version", "Statement"} or document.get("Version") != "2012-10-17":
      raise Unsupported("missing or unsupported Developer source document")
    statements = document.get("Statement")
    if not isinstance(statements, list) or not statements:
      raise Unsupported("unsupported statement collection")
    seen = set()
    for index, statement in enumerate(statements):
      if not isinstance(statement, dict) or set(statement) - {"Sid", "Effect", "Action", "Resource", "Condition"}:
        raise Unsupported("unsupported selector or statement structure")
      sid = statement.get("Sid")
      if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,127}", sid) or sid in seen:
        raise Unsupported("missing or ambiguous statement identity")
      seen.add(sid)
      if statement.get("Effect") not in {"Allow", "Deny"}:
        raise Unsupported("unsupported statement effect")
      actions = _list(statement.get("Action"))
      if any(not re.fullmatch(r"[A-Za-z0-9-]+:[A-Za-z0-9]+", item) for item in actions):
        raise Unsupported("wildcard or unsupported action selector")
      if len({item.casefold() for item in actions}) != len(actions):
        raise Unsupported("duplicate action selector")
      resources = _list(statement.get("Resource"))
      if any("${" in item for item in resources):
        raise Unsupported("policy variables are unsupported")
      conditions = _conditions(statement)
      if any(action.casefold() in {item.casefold() for item in actions} for action in ACTIONS):
        for resource in resources:
          _resource_parts(resource)
        result.append({"policy": policy, "index": index, "sid": sid, "statement": statement,
                       "actions": {item.casefold() for item in actions}, "conditions": conditions})
  return result


def _resource_parts(resource):
  if resource == "*":
    return None
  match = re.fullmatch(r"arn:(aws|aws-us-gov|aws-cn):(ec2|secretsmanager):([a-z0-9-]+):(\d{12}):(vpc/\*|subnet/\*|internet-gateway/\*|route-table/\*|secret:\*)", resource)
  if not match or (match[2] == "secretsmanager") != (match[5] == "secret:*"):
    raise Unsupported("unsupported relevant resource pattern")
  return {"partition": match[1], "service": match[2], "region": match[3], "account": match[4],
          "type": match[5].split("/", 1)[0].split(":", 1)[0]}


def _has(item, operator, key, values, subset=False):
  actual = item["conditions"].get(operator, {}).get(key.casefold())
  return actual is not None and (bool(actual) and set(actual) <= set(values) if subset else set(actual) == set(values))


def _structural(item, action, scope):
  """Reviewed sufficient blocking forms per Allow; no scenario sampling here."""
  if item["statement"]["Effect"] == "Deny":
    return {"policy": item["policy"], "sid": item["sid"], "action": action,
            "status": "passed", "certificate": "explicit_deny_included_in_scenario_evaluation"}
  secret = action == ACTIONS[1]
  approved_accounts = [scope["account"]] if secret else scope["accounts"]
  resources = [_resource_parts(raw) for raw in _list(item["statement"]["Resource"])]
  bounded = all(part is not None and part["partition"] == scope["partition"] and
    part["service"] == ("secretsmanager" if secret else "ec2") and
    part["region"] == scope["region"] and part["account"] in approved_accounts for part in resources)
  base = bounded and _has(item, "StringEquals", "aws:PrincipalAccount", approved_accounts, subset=True) and _has(item, "StringEquals", "aws:RequestedRegion", [scope["region"]])
  if secret:
    form = (_has(item, "StringEquals", "aws:RequestTag/project", [scope["project"]]) and
      _has(item, "ForAllValues:StringEquals", "aws:TagKeys", TAGS) and
      _has(item, "Null", "secretsmanager:AddReplicaRegions", ["true"]) and
      _has(item, "BoolIfExists", "secretsmanager:ForceOverwriteReplicaSecret", ["false"]))
    certificate = "independent_replica_absence_and_overwrite_false_or_absent"
  else:
    protected = (any(value.casefold() == "project" for value in item["conditions"].get("ForAllValues:StringNotEqualsIgnoreCase", {}).get("aws:tagkeys", [])) and
      _has(item, "Null", "aws:TagKeys", ["false"]) and
      _has(item, "StringEquals", "aws:ResourceTag/project", [scope["project"]]))
    create = item["conditions"].get("StringEquals", {}).get("ec2:createaction", [])
    creation = (len(create) == 1 and create[0] in CREATE.values() and
      all(part is not None and CREATE.get(part["type"]) == create[0] for part in resources) and
      _has(item, "StringEquals", "aws:RequestTag/project", [scope["project"]]) and
      _has(item, "ForAllValues:StringEquals", "aws:TagKeys", TAGS))
    form = protected or creation
    certificate = "case_insensitive_protected_key_exclusion_and_existing_project" if protected else "required_create_action_and_canonical_request_tags"
  return {"policy": item["policy"], "sid": item["sid"], "action": action,
          "status": "passed" if base and form else "failed", "certificate": certificate,
          "resource_account_region_boundaries": bool(base), "blocking_form": bool(form)}


def _condition_truth(operator, expected, actual):
  absent = actual is None or actual == []
  if operator == "Null":
    return absent == (expected == ["true"])
  if operator == "BoolIfExists":
    if absent:
      return True
    if type(actual) is not bool:
      raise Unsupported("unsupported boolean context")
    return actual == (expected == ["true"])
  if operator.startswith("For"):
    if not absent and (not isinstance(actual, list) or any(not isinstance(value, str) for value in actual)):
      raise Unsupported("unsupported multivalue context")
    values = [] if absent else actual
    if operator == "ForAllValues:StringEquals":
      return all(value in expected for value in values)
    comparison = [all(value.casefold() != target.casefold() for target in expected) for value in values]
    return all(comparison) if operator.startswith("ForAll") else any(comparison)
  if absent:
    return operator == "StringEqualsIfExists"
  if isinstance(actual, list) or type(actual) not in {str, int}:
    raise Unsupported("unsupported single-value context")
  if operator.startswith("Numeric"):
    if not re.fullmatch(r"\d+", str(actual)):
      raise Unsupported("unsupported numeric context")
    return int(actual) >= int(expected[0]) if operator == "NumericGreaterThanEquals" else int(actual) <= int(expected[0])
  return str(actual) in expected


def _decision(items, action, resource, context):
  normalized = {key.casefold(): value for key, value in context.items()}
  if len(normalized) != len(context):
    raise Unsupported("duplicate context key")
  diagnostics, allows, denies = [], [], []
  for item in items:
    if action.casefold() not in item["actions"]:
      continue
    statement = item["statement"]
    resource_match = any(pattern == "*" or resource.startswith(pattern[:-1]) for pattern in _list(statement["Resource"]))
    truth = [{"operator": operator, "key": key, "satisfied": _condition_truth(operator, expected, normalized.get(key)),
              "present": key in normalized} for operator, entries in item["conditions"].items() for key, expected in entries.items()]
    applicable = resource_match and all(row["satisfied"] for row in truth)
    identity = item["policy"] + ":" + item["sid"]
    if applicable:
      (allows if statement["Effect"] == "Allow" else denies).append(identity)
    diagnostics.append({"policy": item["policy"], "sid": item["sid"], "effect": statement["Effect"],
                        "resource_match": resource_match, "conditions": truth, "applicable": applicable})
  actual = "explicit_deny" if denies else "allowed" if allows else "implicit_deny"
  return {"actual": actual, "allow_sids": allows, "deny_sids": denies, "statements": diagnostics}


def _arn(scope, service, kind, account=None, region=None):
  suffix = "secret:guardrail-fixture" if kind == "secret" else kind + "/guardrail-fixture"
  return f'arn:{scope["partition"]}:{service}:{region or scope["region"]}:{account or scope["account"]}:{suffix}'


def _scenarios(scope):
  result = []
  outside = next(str(index).zfill(12) for index in range(len(scope["accounts"]) + 1) if str(index).zfill(12) not in scope["accounts"])
  other_region = "eu-west-1" if scope["region"] != "eu-west-1" else "us-east-2"
  foreign_project = "another-project" if scope["project"] != "another-project" else "different-project"

  def add(identity, action, kind, resource, context, allowed):
    result.append({"id": identity, "action": action, "resource_type": kind, "resource": resource,
                   "context": context, "expected": "allowed" if allowed else "not_allowed"})

  for index, account in enumerate(scope["accounts"]):
    for kind, create in CREATE.items():
      resource = _arn(scope, "ec2", kind, account)
      base = {"aws:PrincipalAccount": account, "aws:RequestedRegion": scope["region"],
              "aws:ResourceTag/project": scope["project"], "aws:TagKeys": ["Name"]}
      prefix = f"ec2-{index}-{kind}-"
      add(prefix + "ordinary-edit", ACTIONS[0], kind, resource, base, True)
      for variant in ("Project", "project", "pRoJeCt"):
        context = {**base, "aws:TagKeys": [variant], "aws:RequestTag/project": scope["project"]}
        add(prefix + "overwrite-" + variant, ACTIONS[0], kind, resource, context, False)
      add(prefix + "mixed-protected-keys", ACTIONS[0], kind, resource,
          {**base, "aws:TagKeys": ["Name", "pRoJeCt"], "aws:RequestTag/project": scope["project"]}, False)
      add(prefix + "direct-adoption", ACTIONS[0], kind, resource,
          {**base, "aws:ResourceTag/project": foreign_project, "aws:RequestTag/project": scope["project"], "aws:TagKeys": ["project"]}, False)
      creation = {"aws:PrincipalAccount": account, "aws:RequestedRegion": scope["region"],
                  "aws:RequestTag/project": scope["project"], "aws:TagKeys": sorted(TAGS), "ec2:CreateAction": create}
      add(prefix + "create-tagging", ACTIONS[0], kind, resource, creation, True)
      wrong_action = "CreateSubnet" if create == "CreateVpc" else "CreateVpc"
      for label, change in (("create-wrong-action", {"ec2:CreateAction": wrong_action}),
                            ("create-wrong-principal", {"aws:PrincipalAccount": outside}),
                            ("create-wrong-requested-region", {"aws:RequestedRegion": other_region})):
        add(prefix + label, ACTIONS[0], kind, resource, {**creation, **change}, False)
      add(prefix + "create-wrong-resource-account", ACTIONS[0], kind, _arn(scope, "ec2", kind, outside), creation, False)
      add(prefix + "create-wrong-resource-region", ACTIONS[0], kind, _arn(scope, "ec2", kind, account, other_region), creation, False)
      for label, change in (("wrong-principal", {"aws:PrincipalAccount": outside}),
                            ("wrong-requested-region", {"aws:RequestedRegion": other_region}),
                            ("foreign-project-edit", {"aws:ResourceTag/project": foreign_project}),
                            ("empty-tag-keys", {"aws:TagKeys": []})):
        add(prefix + label, ACTIONS[0], kind, resource, {**base, **change}, False)
      for key in ("aws:PrincipalAccount", "aws:RequestedRegion", "aws:TagKeys"):
        context = {key2: value for key2, value in base.items() if key2 != key}
        add(prefix + "missing-" + key.split(":")[-1], ACTIONS[0], kind, resource, context, False)
      add(prefix + "wrong-resource-account", ACTIONS[0], kind, _arn(scope, "ec2", kind, outside), base, False)
      add(prefix + "wrong-resource-region", ACTIONS[0], kind, _arn(scope, "ec2", kind, account, other_region), base, False)
  base = {"aws:PrincipalAccount": scope["account"], "aws:RequestedRegion": scope["region"],
          "aws:RequestTag/project": scope["project"], "aws:TagKeys": sorted(TAGS)}
  resource = _arn(scope, "secretsmanager", "secret")
  add("secret-no-replica-overwrite-absent", ACTIONS[1], "secret", resource, base, True)
  add("secret-no-replica-overwrite-false", ACTIONS[1], "secret", resource,
      {**base, "secretsmanager:ForceOverwriteReplicaSecret": False}, True)
  for label, replica, overwrite in (("replica-only", True, False), ("overwrite-only", False, True), ("both", True, True)):
    context = {**base, "secretsmanager:ForceOverwriteReplicaSecret": overwrite}
    if replica:
      context["secretsmanager:AddReplicaRegions"] = [other_region]
    add("secret-" + label, ACTIONS[1], "secret", resource, context, False)
  for label, change in (("wrong-principal", {"aws:PrincipalAccount": outside}),
                        ("wrong-requested-region", {"aws:RequestedRegion": other_region}),
                        ("foreign-project", {"aws:RequestTag/project": foreign_project})):
    add("secret-" + label, ACTIONS[1], "secret", resource, {**base, **change}, False)
  for key in ("aws:PrincipalAccount", "aws:RequestedRegion", "aws:RequestTag/project"):
    add("secret-missing-" + key.split(":")[-1], ACTIONS[1], "secret", resource,
        {key2: value for key2, value in base.items() if key2 != key}, False)
  add("secret-wrong-resource-account", ACTIONS[1], "secret", _arn(scope, "secretsmanager", "secret", outside), base, False)
  add("secret-wrong-resource-region", ACTIONS[1], "secret", _arn(scope, "secretsmanager", "secret", region=other_region), base, False)
  return result


def _mutations(policies, items, scope, scenarios):
  result = []

  def run(item, label, scenario_suffix, change):
    candidates = [row for row in scenarios if row["id"].endswith(scenario_suffix) and
      (scenario_suffix.startswith(("create-", "secret-")) or "-create-" not in row["id"])]
    # The correct resource type matters: a different creation statement must not mask this mutation.
    resources = [_resource_parts(raw) for raw in _list(item["statement"]["Resource"])]
    kinds = {part["type"] for part in resources if part is not None}
    candidate = next((row for row in candidates if row["resource_type"] in kinds), None)
    if candidate is None:
      raise Unsupported("missing independently targeted mutation scenario")
    mutated = copy.deepcopy(policies)
    statement = mutated[item["policy"]]["Statement"][item["index"]]
    change(statement)
    mutated_items = _statements(mutated)
    before = _decision(items, candidate["action"], candidate["resource"], candidate["context"])
    after = _decision(mutated_items, candidate["action"], candidate["resource"], candidate["context"])
    exposed = before["actual"] != "allowed" and after["actual"] == "allowed"
    result.append({"id": item["sid"] + "-" + label, "policy": item["policy"], "sid": item["sid"],
      "scenario_id": candidate["id"], "resource_type": candidate["resource_type"], "context": _safe(candidate["context"]),
      "expected": "authorization_regression_exposed", "baseline": before, "mutated": after,
      "source_sha256": _hash(policies[item["policy"]]), "mutated_sha256": _hash(mutated[item["policy"]]),
      "regression_exposed": exposed, "detected": exposed, "status": "passed" if exposed else "failed"})

  def remove(operator, key):
    def change(statement):
      entries = statement["Condition"][operator]
      actual_key = next(name for name in entries if name.casefold() == key.casefold())
      del entries[actual_key]
      if not entries:
        del statement["Condition"][operator]
    return change

  for item in items:
    if item["statement"]["Effect"] != "Allow":
      continue
    if ACTIONS[0].casefold() in item["actions"]:
      conditions = item["conditions"]
      if "ec2:createaction" in conditions.get("StringEquals", {}):
        run(item, "remove-create-action", "direct-adoption", remove("StringEquals", "ec2:CreateAction"))
        def weaken(statement):
          values = statement["Condition"]["StringEquals"]
          key = next(name for name in values if name.casefold() == "ec2:createaction")
          statement["Condition"].setdefault("StringEqualsIfExists", {})[key] = values.pop(key)
        run(item, "create-action-if-exists", "direct-adoption", weaken)
        run(item, "create-remove-principal-account", "create-wrong-principal", remove("StringEquals", "aws:PrincipalAccount"))
        run(item, "create-remove-requested-region", "create-wrong-requested-region", remove("StringEquals", "aws:RequestedRegion"))
        run(item, "create-unbounded-resource-account", "create-wrong-resource-account", lambda statement: statement.update(Resource="*"))
        run(item, "create-unbounded-resource-region", "create-wrong-resource-region", lambda statement: statement.update(Resource="*"))
      else:
        run(item, "remove-project-key-exclusion", "overwrite-Project", remove("ForAllValues:StringNotEqualsIgnoreCase", "aws:TagKeys"))
        def weaken_keys(statement):
          entries = statement["Condition"].pop("ForAllValues:StringNotEqualsIgnoreCase")
          statement["Condition"]["ForAnyValue:StringNotEqualsIgnoreCase"] = entries
        run(item, "any-instead-of-all-keys", "mixed-protected-keys", weaken_keys)
        run(item, "remove-existing-project", "foreign-project-edit", remove("StringEquals", "aws:ResourceTag/project"))
        run(item, "remove-nonnull-tag-keys", "missing-TagKeys", remove("Null", "aws:TagKeys"))
        run(item, "remove-principal-account", "wrong-principal", remove("StringEquals", "aws:PrincipalAccount"))
        run(item, "remove-requested-region", "wrong-requested-region", remove("StringEquals", "aws:RequestedRegion"))
        run(item, "unbounded-resource-account", "wrong-resource-account", lambda statement: statement.update(Resource="*"))
        run(item, "unbounded-resource-region", "wrong-resource-region", lambda statement: statement.update(Resource="*"))
    if ACTIONS[1].casefold() in item["actions"]:
      run(item, "remove-replica-null", "secret-replica-only", remove("Null", "secretsmanager:AddReplicaRegions"))
      def weaken_null(statement):
        entries = statement["Condition"]["Null"]
        key = next(name for name in entries if name.casefold() == "secretsmanager:addreplicaregions")
        entries[key] = "false"
      run(item, "invert-replica-null", "secret-replica-only", weaken_null)
      run(item, "remove-overwrite-guard", "secret-overwrite-only", remove("BoolIfExists", "secretsmanager:ForceOverwriteReplicaSecret"))
      def weaken_bool(statement):
        entries = statement["Condition"]["BoolIfExists"]
        key = next(name for name in entries if name.casefold() == "secretsmanager:forceoverwritereplicasecret")
        entries[key] = "true"
      run(item, "invert-overwrite-guard", "secret-overwrite-only", weaken_bool)
  return result


def verify_guardrails(policies, scope):
  """Return sanitized static evidence, fail closed on unsupported/ambiguous input.

  Inputs are never modified. Exact Allow/Deny statements from both Developer
  documents are enumerated independently of exporter/projection/response code.
  """
  report = {"status": "inconclusive", "evidence_type": "independent_static_guardrail_verification",
    "aws_simulated": False, "source_sha256": {}, "actions": {}, "structural_checks": [],
    "scenarios": [], "negative_mutations": [], "limitations": LIMITATIONS.copy()}
  try:
    if not isinstance(policies, dict):
      raise Unsupported("missing policy documents")
    for policy in POLICIES:
      if policy not in policies:
        raise Unsupported("missing Developer source document")
      report["source_sha256"][policy] = _hash(policies[policy])
    checked_scope = _scope(scope)
    items = _statements(policies)
    for action in ACTIONS:
      relevant = [item for item in items if action.casefold() in item["actions"]]
      report["actions"][action] = {"applicable_statements": [{"policy": item["policy"], "sid": item["sid"],
        "effect": item["statement"]["Effect"], "resource_patterns": _safe(_list(item["statement"]["Resource"])),
        "resource_sha256": _hash(item["statement"]["Resource"]), "conditions": _safe(item["statement"].get("Condition", {}))} for item in relevant]}
      report["structural_checks"].extend(_structural(item, action, checked_scope) for item in relevant)
    scenarios = _scenarios(checked_scope)
    for row in scenarios:
      actual = _decision(items, row["action"], row["resource"], row["context"])
      passed = (actual["actual"] == "allowed") == (row["expected"] == "allowed")
      report["scenarios"].append({**_safe(row), **actual, "status": "passed" if passed else "failed"})
    if all(row["status"] == "passed" for row in report["structural_checks"] + report["scenarios"]):
      report["negative_mutations"] = _mutations(policies, items, checked_scope, scenarios)
    report["status"] = "passed" if all(row["status"] == "passed" for row in report["structural_checks"] + report["scenarios"] + report["negative_mutations"]) else "failed"
  except (Unsupported, TypeError, ValueError, KeyError, OverflowError):
    report["status"] = "inconclusive"
    report["reason"] = "unsupported_or_ambiguous_input"
  return report
