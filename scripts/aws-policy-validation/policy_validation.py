#!/usr/bin/env python3
"""Export Terraform mock policies and prepare optional, manual AWS validation.

Default execution is offline. The authenticated mode is intentionally forbidden
in Codex Cloud and GitHub Actions and is limited to three read-only validation APIs.
"""

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from policy_cases import build_cases


FORMAT_VERSION = 1
POLICY_IDS = {"access_admin", "developer_inline", "operator", "developer_secrets_manager"}
PROFILE_POLICIES = {
  "developer": ["developer_inline", "developer_secrets_manager"],
  "operator": ["operator"],
  "access_admin": ["access_admin"],
}
CMP_NAME = "Portfolio-Developer-SecretsManager"
CMP_PATH = "/"
INLINE_LIMIT = 10240
INLINE_TOTAL_LIMIT = 32768
MANAGED_LIMIT = 6144
ATTACHMENT_LIMIT = 25
PORTFOLIO_ATTACHMENT_BUDGET = 10
SM_ACTIONS = {"secretsmanager:" + name for name in (
  "CreateSecret", "DescribeSecret", "GetResourcePolicy", "TagResource", "UntagResource", "DeleteSecret"
)}
API_COMMANDS = {
  "access-analyzer:ValidatePolicy": ("accessanalyzer", "validate-policy"),
  "iam:GetContextKeysForCustomPolicy": ("iam", "get-context-keys-for-custom-policy"),
  "iam:SimulateCustomPolicy": ("iam", "simulate-custom-policy"),
}
LIMITATIONS = [
  "Synthetic policy context is not an assumed role or actual session.",
  "Simulation does not prove effective SCP/resource-policy/KMS authorization or live service calls.",
  "Multi-resource operations require every requested resource; an isolated Allow is insufficient.",
  "Identity Center propagation, recipient/self-assignment, main-route-table exclusion and attribute-value prevention remain unverified.",
  "CreateSecret can initialize values; no secret payload is used by this toolkit.",
  "CloudShell/validation permissions and existing session authorization must be verified externally.",
]


def require(condition, message):
  if not condition:
    raise ValueError(message)


def compact(document):
  return json.dumps(document, separators=(",", ":"), ensure_ascii=True)


def digest(data):
  return hashlib.sha256(data).hexdigest()


def read_json(path):
  with Path(path).open(encoding="utf-8") as source:
    return json.load(source)


def private_directory(path):
  directory = Path(path).expanduser().resolve()
  def checkout_marker(parent):
    marker = parent / ".git"
    if marker.is_file():
      return marker.read_text(encoding="utf-8").startswith("gitdir:")
    # Codex mounts empty protected .git placeholders at writable roots. They
    # are not repositories; require real repository metadata before rejecting.
    return (marker / "HEAD").is_file() and ((marker / "objects").is_dir() or (marker / "commondir").is_file())
  require(not any(checkout_marker(parent) for parent in (directory, *directory.parents)),
      "Output must be outside every Git checkout; use a fresh private /tmp directory.")
  if directory.exists():
    require(directory.is_dir() and not any(directory.iterdir()), "Output directory must be empty.")
  else:
    directory.mkdir(parents=True, mode=0o700)
  directory.chmod(0o700)
  return directory


def private_write(path, value):
  text = json.dumps(value, indent=2, ensure_ascii=True) + "\n" if not isinstance(value, str) else value
  descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
  with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    output.write(text)


def read_plan(path):
  """Read a complete successful native JSONL stream without retaining schemas."""
  passed, errors, first_plan, summaries = set(), set(), None, []
  with Path(path).open(encoding="utf-8") as events:
    for line in events:
      event = json.loads(line)
      key = (event.get("@testfile"), event.get("@testrun"))
      if event.get("@level") == "error":
        errors.add(key)
      if event.get("type") == "test_run" and event["test_run"].get("status") == "pass":
        passed.add(key)
      if event.get("type") == "test_plan" and first_plan is None:
        require(key in passed, "Rendered plan did not follow a passing native test.")
        first_plan = event["test_plan"]
      if event.get("type") == "test_summary":
        summaries.append(event["test_summary"])
  require(errors <= passed, "Errors occurred outside expected-failure passing native tests.")
  require(first_plan is not None and len(summaries) == 1, "Missing plan or unique complete test summary.")
  summary = summaries[0]
  require(summary.get("status") == "pass" and summary.get("passed", 0) > 0 and
      all(summary.get(key) == 0 for key in ("failed", "errored", "skipped")),
      "Native tests failed, errored, skipped or did not finish.")
  return first_plan, summary


def inventory(plan, expected):
  resources = plan.get("resource_changes", [])
  require(collections.Counter(resource.get("type") for resource in resources) == expected,
      "Unexpected managed-resource inventory in rendered mock plan.")
  require(all(resource.get("mode") == "managed" and resource.get("change", {}).get("actions") == ["create"]
      for resource in resources), "Only reviewed managed creates may be exported.")
  return resources


def actions(policy):
  result = set()
  require(policy.get("Version") == "2012-10-17", "Unexpected IAM policy language version.")
  statements = policy.get("Statement")
  require(isinstance(statements, list) and statements, "Policy has no statements.")
  for statement in statements:
    require(statement.get("Effect") == "Allow" and not
        ({"NotAction", "NotResource", "Principal", "NotPrincipal"} & statement.keys()),
        "Only reviewed positive identity-policy Allow statements are supported.")
    current = statement.get("Action")
    current = [current] if isinstance(current, str) else current
    require(isinstance(current, list) and current and all(isinstance(value, str) and
        re.fullmatch(r"[a-z0-9-]+:[A-Za-z0-9]+", value) for value in current),
        "Missing, wildcard or malformed action.")
    resources = statement.get("Resource")
    require(isinstance(resources, list) and resources and all(isinstance(value, str) for value in resources),
        "Resource arrays are required for reviewed policies.")
    result.update(current)
  return result


def policy_sizes(text, kind):
  non_whitespace = "".join(text.split())
  count = len(non_whitespace.encode("utf-8")) if kind == "inline" else len(non_whitespace)
  limit = INLINE_LIMIT if kind == "inline" else MANAGED_LIMIT
  require(count <= limit, "Rendered policy exceeds its non-whitespace quota.")
  if kind == "inline":
    require(len(text.encode("utf-8")) <= INLINE_TOTAL_LIMIT, "Rendered inline policy exceeds total-byte quota.")
  return {"non_whitespace_size": count, "limit": limit, "headroom": limit - count,
      "unit": "bytes" if kind == "inline" else "characters", "total_bytes": len(text.encode("utf-8"))}


def synthetic_only(text):
  account_ids = re.findall(r"(?<![0-9])[0-9]{12}(?![0-9])", text)
  require(all(value.startswith("000000000") for value in account_ids),
      "Only format-valid synthetic account identifiers may enter this fixture bundle.")
  require(not re.search(r"(?:AKIA|ASIA)[A-Z0-9]{16}|-----BEGIN .*PRIVATE KEY-----", text),
      "Credential-like material is forbidden.")
  require(not re.search(r'"(?:SecretString|SecretBinary|secret_string|secret_binary)"\s*:', text),
      "Secret payload fields are forbidden.")


def scope_from_policies(policies, permission_sets):
  secret_statement = policies["developer_secrets_manager"]["Statement"][0]
  secret_arns = secret_statement["Resource"]
  require(len(secret_arns) == 1, "Per-account managed policy must contain one account-specific ARN pattern.")
  match = re.fullmatch(r"arn:(aws|aws-us-gov|aws-cn):secretsmanager:([^:]+):([0-9]{12}):secret:\*", secret_arns[0])
  require(match, "Managed policy Secret ARN is not account/region scoped.")
  equals = secret_statement["Condition"]["StringEquals"]
  account, region = match[3], match[2]
  require(equals.get("aws:PrincipalAccount") in (account, [account]) and equals.get("aws:RequestedRegion") == region,
      "Managed policy caller account/region does not match its resource ARN.")
  project = equals.get("aws:RequestTag/Project")
  require(isinstance(project, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,62}", project), "Missing reviewed Project identity.")
  inline_equals = policies["developer_inline"]["Statement"][0]["Condition"]["StringEquals"]
  targets = inline_equals.get("aws:PrincipalAccount")
  targets = [targets] if isinstance(targets, str) else targets
  require(isinstance(targets, list) and account in targets, "Managed policy account is not an approved inline target.")
  require(inline_equals.get("aws:RequestedRegion") == region, "Inline and managed regions differ.")
  admin = policies["access_admin"]["Statement"][0]["Condition"]["StringEquals"]["aws:PrincipalAccount"]
  return {"account_id": account, "target_account_ids": sorted(targets), "region": region,
      "project_tag": project, "administration_account_id": admin,
      "instance_arn": permission_sets["developer"]["instance_arn"],
      "developer_permission_set_arn": permission_sets["developer"]["arn"],
      "operator_permission_set_arn": permission_sets["operator"]["arn"]}


def export_bundle(iam_events, account_events, output_dir, fixture_version="terraform-mock-v1"):
  require(re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", fixture_version), "Invalid fixture version label.")
  iam, iam_summary = read_plan(iam_events)
  account, account_summary = read_plan(account_events)
  expected_iam = collections.Counter({"aws_ssoadmin_permission_set": 3,
      "aws_ssoadmin_permission_set_inline_policy": 3,
      "aws_ssoadmin_customer_managed_policy_attachment": 1})
  iam_resources = inventory(iam, expected_iam)
  account_resources = inventory(account, collections.Counter({"aws_iam_policy": 1}))
  permission_sets, policy_texts, inline_bindings = {}, {}, {}
  attachment = None
  for resource in iam_resources:
    after = resource["change"]["after"]
    if resource["type"] == "aws_ssoadmin_permission_set":
      permission_sets[resource["name"]] = after
    elif resource["type"] == "aws_ssoadmin_permission_set_inline_policy":
      inline_bindings[resource["name"]] = after
      name = "developer_inline" if resource["name"] == "developer" else resource["name"]
      policy_texts[name] = after["inline_policy"]
    else:
      attachment = after
  require(set(permission_sets) == {"access_admin", "developer", "operator"}, "Permission Set identities changed.")
  for profile, name in (("access_admin", "Portfolio-Access-Admin"), ("developer", "Portfolio-Developer"), ("operator", "Portfolio-Operator")):
    require(permission_sets[profile].get("name") == name, "Fixed Permission Set name changed.")
  require(set(inline_bindings) == set(permission_sets), "Each profile must own exactly one inline policy.")
  for profile, binding in inline_bindings.items():
    require(binding.get("permission_set_arn") == permission_sets[profile]["arn"] and
        binding.get("instance_arn") == permission_sets[profile]["instance_arn"],
        "Inline policy is bound to the wrong Permission Set or instance.")
  managed = account_resources[0]["change"]["after"]
  require(managed.get("name") == CMP_NAME and managed.get("path") == CMP_PATH, "Managed policy name/path contract changed.")
  require(attachment and attachment.get("permission_set_arn") == permission_sets["developer"]["arn"] and
      attachment.get("instance_arn") == permission_sets["developer"]["instance_arn"], "Attachment is not Developer-only.")
  reference = attachment.get("customer_managed_policy_reference")
  require(isinstance(reference, list) and len(reference) == 1 and reference[0] == {"name": CMP_NAME, "path": CMP_PATH},
      "Attachment and per-account policy name/path do not match.")
  policy_texts["developer_secrets_manager"] = managed["policy"]
  require(set(policy_texts) == POLICY_IDS, "Unexpected exported policy identities.")
  policies = {key: json.loads(value) for key, value in policy_texts.items()}
  require(actions(policies["developer_secrets_manager"]) == SM_ACTIONS, "Managed policy action set changed.")
  require(all(action.startswith("ec2:") for action in actions(policies["developer_inline"])), "Developer inline must remain EC2-only.")
  scope = scope_from_policies(policies, permission_sets)
  directory = private_directory(output_dir)
  manifest = {"format_version": FORMAT_VERSION, "fixture_version": fixture_version,
      "synthetic": True, "source": "actual successful native Terraform mock plans",
      "scope": scope, "policies": {}, "native_results": {"iam_access": iam_summary, "iam_account_policies": account_summary},
      "inventories": {"iam_access": dict(expected_iam), "iam_account_policies": {"aws_iam_policy": 1}},
      "attachment": {"profile": "developer", "name": CMP_NAME, "path": CMP_PATH, "count": 1,
        "portfolio_budget": PORTFOLIO_ATTACHMENT_BUDGET, "identity_center_limit": ATTACHMENT_LIMIT},
      "limitations": LIMITATIONS}
  for identifier, text in sorted(policy_texts.items()):
    synthetic_only(text)
    kind = "managed" if identifier == "developer_secrets_manager" else "inline"
    stats = policy_sizes(text, kind)
    filename = identifier + ".json"
    data = (text + "\n").encode("utf-8")
    private_write(directory / filename, data.decode("utf-8"))
    manifest["policies"][identifier] = {"file": filename, "sha256": digest(data), "kind": kind, **stats}
  cases = build_cases(scope)
  case_text = json.dumps(cases, indent=2, ensure_ascii=True) + "\n"
  synthetic_only(case_text)
  private_write(directory / "cases.json", case_text)
  manifest["cases"] = {"file": "cases.json", "sha256": digest(case_text.encode()), "count": len(cases)}
  private_write(directory / "manifest.json", manifest)
  load_bundle(directory)
  return manifest


def load_bundle(path):
  directory = Path(path).resolve()
  manifest = read_json(directory / "manifest.json")
  require(manifest.get("format_version") == FORMAT_VERSION and manifest.get("synthetic") is True,
      "Unsupported or non-synthetic bundle manifest.")
  require(set(manifest.get("policies", {})) == POLICY_IDS, "Manifest policy identity set changed.")
  policies = {}
  for identifier, entry in manifest["policies"].items():
    expected_kind = "managed" if identifier == "developer_secrets_manager" else "inline"
    require(entry.get("kind") == expected_kind, "Policy kind must match its reviewed quota identity.")
    require(entry.get("file") == identifier + ".json", "Policy path must be a reviewed bundle basename.")
    filename = directory / entry["file"]
    require(filename.resolve().parent == directory, "Policy file escapes bundle directory.")
    data = filename.read_bytes()
    require(digest(data) == entry.get("sha256"), "Policy content checksum does not match manifest.")
    text = data.decode("utf-8")
    synthetic_only(text)
    policy = json.loads(text)
    actions(policy)
    sizes = policy_sizes(text.rstrip("\n"), entry["kind"])
    require(all(entry.get(key) == value for key, value in sizes.items()), "Policy size/headroom metadata is stale.")
    policies[identifier] = policy
  require(actions(policies["developer_secrets_manager"]) == SM_ACTIONS, "Managed action allowlist changed.")
  require(all(action.startswith("ec2:") for action in actions(policies["developer_inline"])), "Developer inline is not EC2-only.")
  require(manifest.get("attachment") == {"profile": "developer", "name": CMP_NAME, "path": CMP_PATH, "count": 1,
      "portfolio_budget": PORTFOLIO_ATTACHMENT_BUDGET, "identity_center_limit": ATTACHMENT_LIMIT}, "Attachment contract changed.")
  cases_path = directory / "cases.json"
  require(manifest.get("cases", {}).get("file") == "cases.json" and cases_path.resolve().parent == directory and
      digest(cases_path.read_bytes()) == manifest["cases"].get("sha256"), "Cases path/checksum mismatch.")
  cases = read_json(cases_path)
  require(cases == build_cases(manifest["scope"]) and manifest["cases"].get("count") == len(cases),
      "Simulation cases do not match the reviewed deterministic generation contract.")
  return manifest, policies, cases


def bundle_identity(manifest):
  return digest(compact(manifest).encode())


def redact(value):
  value = str(value)
  value = re.sub(r"\barn:[A-Za-z0-9-]+:[^\s\"'<>]+", "<redacted-arn>", value)
  value = re.sub(r"(?<![0-9])[0-9]{12}(?![0-9])", "<redacted-account>", value)
  value = re.sub(r"\b(?:AIDA|AROA|AKIA|ASIA)[A-Z0-9]{12,}\b", "<redacted-identity>", value)
  value = re.sub(r"(?i)\bauthorization\s*[:=][^\r\n]*", "authorization=<redacted>", value)
  value = re.sub(r"(?i)[\"']?\b((?:aws_)?(?:token|access_key_id|secret_access_key|session_token|security_token))[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|\S+)", r"\1=<redacted>", value)
  return value[:2000]


def validate_findings(pages):
  findings = []
  require(pages, "No ValidatePolicy result pages.")
  for page in pages:
    require(isinstance(page, dict) and isinstance(page.get("findings"), list), "Malformed ValidatePolicy response.")
    for finding in page["findings"]:
      require(isinstance(finding, dict) and finding.get("findingType") in
          {"ERROR", "SECURITY_WARNING", "WARNING", "SUGGESTION"} and
          isinstance(finding.get("findingDetails"), str) and isinstance(finding.get("issueCode"), str),
          "Malformed or unknown policy finding.")
      findings.append({"type": finding["findingType"], "issue_code": redact(finding["issueCode"]),
          "details": redact(finding["findingDetails"])})
  counts = {kind: sum(f["type"] == kind for f in findings) for kind in ("ERROR", "SECURITY_WARNING", "WARNING", "SUGGESTION")}
  status = "failed" if counts["ERROR"] else "review_required" if findings else "passed"
  return {"status": status, "findings": findings, "counts": counts}


def simulation_result(case, pages):
  if not case.get("supported", True):
    return {"status": "inconclusive", "reason": "unsupported_by_design", "details": redact(case["notes"])}
  results = []
  require(pages, "No simulation response pages.")
  for page in pages:
    require(isinstance(page, dict) and isinstance(page.get("EvaluationResults"), list), "Malformed simulation response.")
    results.extend(page["EvaluationResults"])
  require(len(results) == 1 and isinstance(results[0], dict) and results[0].get("EvalActionName") == case["action"],
      "Missing, duplicate or mismatched per-action simulation result.")
  result = results[0]
  decisions = {"allowed", "implicitDeny", "explicitDeny"}
  require(result.get("EvalDecision") in decisions, "Unsupported simulation decision.")
  missing = result.get("MissingContextValues", [])
  require(isinstance(missing, list) and all(isinstance(key, str) for key in missing), "Malformed missing-context result.")
  missing = list(missing)
  specific = result.get("ResourceSpecificResults", [])
  require(isinstance(specific, list), "Malformed resource-specific simulation results.")
  resource_decisions = []
  if specific:
    names = []
    for resource in specific:
      require(isinstance(resource, dict) and resource.get("EvalResourceDecision") in decisions and
          isinstance(resource.get("EvalResourceName"), str), "Malformed resource-specific decision.")
      names.append(resource["EvalResourceName"])
      resource_decisions.append(resource["EvalResourceDecision"])
      context = resource.get("MissingContextValues", [])
      require(isinstance(context, list) and all(isinstance(key, str) for key in context), "Malformed resource missing context.")
      missing.extend(context)
    require(len(names) == len(set(names)), "Duplicate resource-specific simulation result.")
    if set(names) != set(case["resources"]):
      return {"status": "inconclusive", "reason": "incomplete_resource_coverage"}
  elif len(case["resources"]) > 1:
    return {"status": "inconclusive", "reason": "multi_resource_details_missing"}
  actual = result["EvalDecision"]
  if resource_decisions:
    aggregate = "explicitDeny" if "explicitDeny" in resource_decisions else "implicitDeny" if "implicitDeny" in resource_decisions else "allowed"
    require(actual == aggregate, "Aggregate and per-resource decisions disagree.")
  if case["expected"] == "deny" and actual == "allowed":
    # Full resource coverage was checked above. An unexpected aggregate Allow
    # must never be softened to an inconclusive result by missing context.
    return {"status": "failed", "decision": actual, "expected": "deny",
        "resource_decisions": resource_decisions, "reason": "unexpected_allow",
        "missing_context": sorted(set(redact(key) for key in missing))}
  if missing:
    return {"status": "inconclusive", "reason": "missing_context", "keys": sorted(set(redact(key) for key in missing))}
  matched = actual == "allowed" if case["expected"] == "allowed" else actual in {"implicitDeny", "explicitDeny"}
  return {"status": "passed" if matched else "failed", "decision": actual,
      "expected": case["expected"], "resource_decisions": resource_decisions,
      "reason": "matched" if matched else "unexpected_allow" if actual == "allowed" else "unexpected_deny"}


class CliFailure(Exception):
  pass


class AwsCli:
  def __init__(self, directory, region):
    live_execution_allowed()
    self.directory, self.region, self.counter = Path(directory), region, 0

  def __call__(self, api, request):
    require(api in API_COMMANDS, "AWS operation is not in the read-only validation allowlist.")
    self.counter += 1
    path = self.directory / f"request-{self.counter}.private.json"
    private_write(path, request)
    environment = os.environ.copy()
    environment.update(AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")
    command = ["aws", *API_COMMANDS[api], "--cli-input-json", "file://" + str(path),
        "--no-paginate", "--output", "json", "--no-cli-pager", "--region", self.region]
    try:
      result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=180)
    except (OSError, subprocess.SubprocessError) as error:
      raise CliFailure(redact(error)) from error
    if result.returncode:
      raise CliFailure(redact(result.stderr or f"AWS CLI exited {result.returncode}"))
    try:
      document = json.loads(result.stdout)
    except ValueError as error:
      raise CliFailure("AWS CLI returned malformed JSON.") from error
    require(isinstance(document, dict), "AWS CLI response is not an object.")
    return document


def collect_pages(transport, api, request):
  """Use native service pagination fields, never CLI-generated starting tokens."""
  pages, seen, current = [], set(), dict(request)
  for _ in range(100):
    page = transport(api, current)
    require(isinstance(page, dict), "Malformed AWS response object.")
    pages.append(page)
    if api == "access-analyzer:ValidatePolicy":
      token = page.get("nextToken")
      if token is None:
        return pages
      field = "nextToken"
    elif api == "iam:SimulateCustomPolicy":
      require(isinstance(page.get("IsTruncated"), bool), "Missing IAM pagination completeness flag.")
      if not page["IsTruncated"]:
        return pages
      token, field = page.get("Marker"), "Marker"
    else:
      return pages
    require(isinstance(token, str) and token and token not in seen, "Missing or repeated AWS pagination token.")
    seen.add(token)
    current = dict(request, **{field: token})
  raise ValueError("AWS pagination exceeded the bounded page limit.")


def complete_pages(api, pages):
  """Recheck recorded native pagination so a truncated capture cannot pass."""
  require(isinstance(pages, list) and pages, "Missing API response pages.")
  seen = set()
  for index, page in enumerate(pages):
    require(isinstance(page, dict), "Malformed response page.")
    last = index == len(pages) - 1
    if api == "access-analyzer:ValidatePolicy":
      token = page.get("nextToken")
      require((token is None) == last, "Incomplete or inconsistent ValidatePolicy page sequence.")
    elif api == "iam:SimulateCustomPolicy":
      require(isinstance(page.get("IsTruncated"), bool), "Missing IAM completeness flag.")
      require(page["IsTruncated"] != last, "Incomplete or inconsistent simulation page sequence.")
      token = page.get("Marker") if page["IsTruncated"] else None
    else:
      require(len(pages) == 1, "Context-key discovery is not paginated.")
      token = None
    if not last:
      require(isinstance(token, str) and token, "Missing recorded pagination token.")
    if token is not None:
      require(isinstance(token, str) and token and token not in seen, "Missing or repeated recorded page token.")
      seen.add(token)
  return pages


def policy_inputs(profile, policies):
  return [compact(policies[identifier]) for identifier in PROFILE_POLICIES[profile]]


def execute_bundle(manifest, policies, cases, transport):
  """Transport injection supports offline tests; CLI main is the live-mode gate."""
  capture = {"format_version": FORMAT_VERSION, "bundle_sha256": bundle_identity(manifest), "complete": False, "calls": []}
  requests = []
  for identifier in sorted(policies):
    requests.append(("access-analyzer:ValidatePolicy", identifier,
        {"policyDocument": compact(policies[identifier]), "policyType": "IDENTITY_POLICY", "locale": "EN", "maxResults": 100}))
  for profile in sorted(PROFILE_POLICIES):
    requests.append(("iam:GetContextKeysForCustomPolicy", profile, {"PolicyInputList": policy_inputs(profile, policies)}))
  for case in cases:
    if case.get("supported", True):
      requests.append(("iam:SimulateCustomPolicy", case["id"], {"PolicyInputList": policy_inputs(case["profile"], policies),
          "ActionNames": [case["action"]], "ResourceArns": case["resources"], "ContextEntries": case["context"], "MaxItems": 100}))
  for api, subject, request in requests:
    record = {"api": api, "subject": subject}
    try:
      record["pages"] = collect_pages(transport, api, request)
    except (ValueError, CliFailure) as error:
      record["error"] = {"category": "api_or_response_error", "message": redact(error)}
      capture["calls"].append(record)
      return capture
    capture["calls"].append(record)
  capture["complete"] = True
  return capture


def parse_capture(manifest, policies, cases, capture):
  require(capture.get("format_version") == FORMAT_VERSION and capture.get("bundle_sha256") == bundle_identity(manifest),
      "Results do not match this exact policy fixture/version.")
  require(isinstance(capture.get("calls"), list) and isinstance(capture.get("complete"), bool), "Malformed result capture.")
  calls = {}
  for record in capture["calls"]:
    require(isinstance(record, dict) and record.get("api") in API_COMMANDS and isinstance(record.get("subject"), str), "Unexpected API record.")
    key = (record["api"], record["subject"])
    require(key not in calls, "Duplicate API result record.")
    calls[key] = record
  report = {"format_version": FORMAT_VERSION, "mode": "aws_response_analysis", "fixture_version": manifest["fixture_version"],
      "bundle_sha256": bundle_identity(manifest), "policy_identities": {key: entry["sha256"] for key, entry in manifest["policies"].items()},
      "apis": sorted({record["api"] for record in capture["calls"]}), "reviewed_api_allowlist": list(API_COMMANDS),
      "validations": {}, "contexts": {}, "simulations": {}, "limitations": LIMITATIONS,
      "findings_requiring_changes": []}

  def result(api, subject, parser):
    record = calls.pop((api, subject), None)
    if record is None:
      return {"status": "inconclusive", "reason": "result_missing"}
    if "error" in record:
      return {"status": "inconclusive", "reason": "api_or_response_error", "details": redact(record["error"].get("message", "API error"))}
    try:
      return parser(complete_pages(api, record.get("pages", [])))
    except (ValueError, TypeError, KeyError) as error:
      return {"status": "inconclusive", "reason": "malformed_or_unsupported_response", "details": redact(error)}

  for identifier in sorted(policies):
    validation = result("access-analyzer:ValidatePolicy", identifier, validate_findings)
    report["validations"][identifier] = validation
    for finding in validation.get("findings", []):
      if finding["type"] in {"ERROR", "SECURITY_WARNING", "WARNING", "SUGGESTION"}:
        report["findings_requiring_changes"].append({"policy": identifier, **finding})
  for profile in sorted(PROFILE_POLICIES):
    def contexts(pages):
      require(len(pages) == 1 and isinstance(pages[0].get("ContextKeyNames"), list) and
          all(isinstance(key, str) for key in pages[0]["ContextKeyNames"]), "Malformed context-key response.")
      return {"status": "passed", "keys": sorted(set(redact(key) for key in pages[0]["ContextKeyNames"])),
          "note": "Discovery only; Null/IfExists keys can intentionally be absent."}
    report["contexts"][profile] = result("iam:GetContextKeysForCustomPolicy", profile, contexts)
  for case in cases:
    if not case.get("supported", True):
      report["simulations"][case["id"]] = simulation_result(case, [])
    else:
      report["simulations"][case["id"]] = result("iam:SimulateCustomPolicy", case["id"], lambda pages: simulation_result(case, pages))
    evaluation = report["simulations"][case["id"]]
    if evaluation["status"] == "failed":
      report["findings_requiring_changes"].append({"type": "AUTHORIZATION_MISMATCH",
          "policy": case["profile"], "case": case["id"], "issue_code": evaluation["reason"],
          "details": f"Case {case['id']} expected {case['expected']} but received {evaluation['decision']}."})
  require(not calls, "Capture contains unreviewed or unsupported extra API subjects.")
  statuses = [value["status"] for group in ("validations", "contexts", "simulations") for value in report[group].values()]
  report["status"] = "failed" if "failed" in statuses else "review_required" if not capture["complete"] or any(status != "passed" for status in statuses) else "passed"
  report["capture_complete"] = capture["complete"]
  report["counts"] = dict(collections.Counter(statuses))
  report["aws_validation_executed_by_this_parse"] = False
  return report


def markdown_report(report):
  lines = ["# AWS policy validation report", "", f"Status: **{report['status']}**", "",
      f"Mode: `{report['mode']}`", f"Fixture: `{redact(report['fixture_version'])}`",
      f"Bundle SHA-256: `{report['bundle_sha256']}`", "", "Only sanitized metadata is shown; keep raw responses private.", ""]
  if report["mode"] == "offline":
    lines.extend(["AWS API calls: **0**. Authenticated validation has not been run.", "",
        f"Reviewed simulation cases: {report['simulation_case_count']}", ""])
  else:
    lines.extend(["| Check | Subject | Status |", "| --- | --- | --- |"])
    for group in ("validations", "contexts", "simulations"):
      for subject, value in report[group].items():
        lines.append(f"| {group} | {subject} | {value['status']} |")
    lines.extend(["", "## Findings requiring review", ""])
    findings = report["findings_requiring_changes"]
    for finding in findings:
      lines.append(f"- {finding['type']} / {finding['policy']} / {finding['issue_code']}: {redact(finding['details']).replace(chr(10), ' ')}")
    if not findings:
      lines.append("No policy findings returned in the available responses; missing/inconclusive results remain distinct.")
  lines.extend(["", "## Limitations", "", *["- " + value for value in LIMITATIONS], ""])
  return "\n".join(lines)


def offline_report(manifest, cases):
  return {"format_version": FORMAT_VERSION, "mode": "offline", "status": "offline_ready", "aws_api_calls": 0,
      "fixture_version": manifest["fixture_version"], "bundle_sha256": bundle_identity(manifest),
      "policy_sizes": {key: {name: value for name, value in entry.items() if name not in {"file", "sha256"}}
        for key, entry in manifest["policies"].items()}, "simulation_case_count": len(cases),
      "unsupported_cases": [case["id"] for case in cases if not case.get("supported", True)], "limitations": LIMITATIONS}


def live_execution_allowed():
  require(not os.environ.get("GITHUB_ACTIONS") and not Path("/etc/codex/network-policy.json").exists() and
      not any(key.startswith("CODEX_") for key in os.environ),
      "Authenticated validation is forbidden in Codex Cloud and GitHub Actions; use the owner's separately authorized CloudShell session.")


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  subparsers = parser.add_subparsers(dest="command", required=True)
  exporter = subparsers.add_parser("export", help="Export only actual rendered synthetic Terraform policies.")
  exporter.add_argument("--iam-test-events", required=True)
  exporter.add_argument("--account-test-events", required=True)
  exporter.add_argument("--output-dir", required=True)
  exporter.add_argument("--fixture-version", default="terraform-mock-v1")
  offline = subparsers.add_parser("offline-check", help="Verify bundle/checksums/cases without invoking AWS CLI.")
  offline.add_argument("--bundle", required=True)
  runner = subparsers.add_parser("run", help="Offline by default; manual --execute-aws only outside Codex/CI.")
  runner.add_argument("--bundle", required=True)
  runner.add_argument("--output-dir", required=True)
  runner.add_argument("--execute-aws", action="store_true")
  replay = subparsers.add_parser("parse", help="Parse private recorded responses offline; never invokes AWS.")
  replay.add_argument("--bundle", required=True)
  replay.add_argument("--responses", required=True)
  replay.add_argument("--output-dir", required=True)
  args = parser.parse_args(argv)
  if args.command == "export":
    manifest = export_bundle(args.iam_test_events, args.account_test_events, args.output_dir, args.fixture_version)
    print(json.dumps({"status": "exported_synthetic", "policies": manifest["policies"], "cases": manifest["cases"]["count"]}, indent=2))
    return 0
  manifest, policies, cases = load_bundle(args.bundle)
  if args.command == "offline-check":
    print(json.dumps(offline_report(manifest, cases), indent=2))
    return 0
  if args.command == "run" and args.execute_aws:
    live_execution_allowed()
  directory = private_directory(args.output_dir)
  if args.command == "parse":
    report = parse_capture(manifest, policies, cases, read_json(args.responses))
  elif args.execute_aws:
    capture = execute_bundle(manifest, policies, cases, AwsCli(directory, manifest["scope"]["region"]))
    private_write(directory / "responses.private.json", capture)
    report = parse_capture(manifest, policies, cases, capture)
    report["aws_validation_executed_by_this_parse"] = True
  else:
    report = offline_report(manifest, cases)
  private_write(directory / "results.json", report)
  private_write(directory / "summary.md", markdown_report(report))
  print(json.dumps({"status": report["status"], "mode": report["mode"], "output": str(directory)}, indent=2))
  return 1 if report["status"] == "failed" else 2 if report["status"] == "review_required" else 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except (ValueError, TypeError, KeyError, OSError) as error:
    print("Validation toolkit error:", redact(error), file=sys.stderr)
    raise SystemExit(1)
