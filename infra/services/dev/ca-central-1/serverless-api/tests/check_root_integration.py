#!/usr/bin/env python3
"""Verify complete offline root mock plans and their actual cross-module bindings.

This is planned configuration evidence, never proof of AWS identity, artifact
existence, effective authorization, propagation, execution or log delivery.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = "tests/root_integration.tftest.hcl"
PROJECT = "test"
PREFIX = PROJECT + "-dev"
PATH_PREFIX = "/" + PROJECT + "/dev"
ACCOUNT = "000000000000"
REGION = "ca-central-1"
POSITIVE_RUNS = {"default_secret_read_disabled", "enabled_exact_secret_read", "node_runtime", "java_runtime", "teardown_log_protection_off"}
NEGATIVE_RUNS = {"invalid_account_id"}
MODULE_TYPES = {
    "artifact_bucket": {"aws_s3_bucket", "aws_s3_bucket_versioning", "aws_s3_bucket_public_access_block",
        "aws_s3_bucket_ownership_controls", "aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_policy"},
    "secret_metadata": {"aws_secretsmanager_secret"},
    "lambda_workload": {"aws_lambda_function", "aws_iam_role", "aws_iam_role_policy", "aws_cloudwatch_log_group"},
    "http_api": {"aws_cloudwatch_log_group", "aws_apigatewayv2_api", "aws_apigatewayv2_integration", "aws_apigatewayv2_route", "aws_apigatewayv2_stage", "aws_lambda_permission"},
}
INVENTORY = {f"module.{module}.{kind}.this" for module, kinds in MODULE_TYPES.items() for kind in kinds}
LOG_FORMAT = {key: "$context." + key for key in (
    "requestId", "routeKey", "httpMethod", "status", "responseLatency", "integrationLatency", "responseLength")}
DEFAULT_TAGS = {"project": PROJECT, "env": "dev", "managed": "terraform"}
# Module-owned Name and service tags (docs/deployment-configuration.md sections 4 and 5).
OWNED_TAGS = {
    ("artifact_bucket", "aws_s3_bucket"): (PREFIX + "-s3-artifact", "s3"),
    ("secret_metadata", "aws_secretsmanager_secret"): (PATH_PREFIX + "/secret/app", "secret"),
    ("lambda_workload", "aws_lambda_function"): (PREFIX + "-lambda", "lambda"),
    ("lambda_workload", "aws_iam_role"): (PREFIX + "-role-lambda", "role"),
    ("lambda_workload", "aws_cloudwatch_log_group"): ("/aws/lambda/" + PREFIX + "-lambda", "lambda"),
    ("http_api", "aws_apigatewayv2_api"): (PREFIX + "-apigw-http", "apigw"),
    ("http_api", "aws_apigatewayv2_stage"): (PREFIX + "-apigw-http-default", "apigw"),
    ("http_api", "aws_cloudwatch_log_group"): (PATH_PREFIX + "/apigw/http", "apigw"),
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "json_duplicate_key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("json_nonfinite_number")


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


def any_unknown(value):
    if isinstance(value, dict):
        return any(any_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(any_unknown(item) for item in value)
    require(type(value) is bool, "unknown_metadata_shape")
    return value


def unknown_at(value, path):
    for part in path:
        if type(value) is bool:
            return value
        value = value.get(part, False) if isinstance(value, dict) else value[part] if isinstance(value, list) and isinstance(part, int) and part < len(value) else False
    return any_unknown(value)


def block(value, code):
    require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict), code)
    return value[0]


def resources_of(plan, complete=True):
    require(isinstance(plan, dict), "plan_shape")
    changes = plan.get("resource_changes", [] if not complete else None)
    require(isinstance(changes, list), "plan_resource_changes")
    resources = {}
    for item in changes:
        address, change = item.get("address"), item.get("change")
        require(address in INVENTORY and address not in resources, "resource_inventory")
        require(item.get("mode") == "managed" and item.get("name") == "this" and "index" not in item
            and item.get("provider_name") == "registry.terraform.io/hashicorp/aws"
            and address == item.get("module_address", "") + "." + item.get("type", "") + ".this", "resource_identity")
        require(isinstance(change, dict) and change.get("actions") == ["create"] and "before" in change
            and change["before"] is None and isinstance(change.get("after"), dict)
            and isinstance(change.get("after_unknown"), dict), "resource_create_metadata")
        any_unknown(change["after_unknown"])
        resources[address] = change
    require(not complete or set(resources) == INVENTORY, "complete_resource_inventory")
    return resources


def verify_plan(plan, enabled, runtime="python3.13", handler="app.handler", log_protection=True):
    resources = resources_of(plan)

    def value(module, kind):
        change = resources[f"module.{module}.{kind}.this"]
        return change["after"], change["after_unknown"]

    def read(module, kind, *keys):
        after, unknown = value(module, kind)
        for key in keys:
            require(key in after, "missing_configuration_field:" + key)
            paths = {
                "versioning_configuration": [(0, "status")],
                "rule": [(0, "object_ownership")] if kind == "aws_s3_bucket_ownership_controls" else [(0, "apply_server_side_encryption_by_default", 0, "sse_algorithm")],
                "logging_config": [(0, "log_group"), (0, "log_format")],
                "default_route_settings": [(0, "throttling_rate_limit"), (0, "throttling_burst_limit"), (0, "logging_level"), (0, "data_trace_enabled")],
            }.get(key, [()])
            require(not any(unknown_at(unknown, (key, *path)) for path in paths), "required_configuration_unknown:" + key)
        return after

    bucket = read("artifact_bucket", "aws_s3_bucket", "bucket", "id", "arn", "bucket_namespace", "force_destroy", "tags_all")
    require(bucket.get("bucket") == PREFIX + "-s3-artifact" and bucket.get("id") == bucket["bucket"]
        and bucket.get("arn") == "arn:aws:s3:::" + bucket["bucket"], "artifact_bucket_identity")
    require(bucket.get("force_destroy") is False and bucket.get("bucket_namespace") == "global", "bucket_safety")
    require(all(not bucket.get(key) for key in ("acl", "grant", "policy", "replication_configuration", "website",
        "cors_rule", "lifecycle_rule", "versioning", "server_side_encryption_configuration")), "bucket_no_embedded_bypass")
    for kind in MODULE_TYPES["artifact_bucket"] - {"aws_s3_bucket"}:
        item = read("artifact_bucket", kind, "bucket")
        require(item.get("bucket") == bucket["id"], "s3_security_bucket_binding")
    versioning = read("artifact_bucket", "aws_s3_bucket_versioning", "versioning_configuration")
    require(block(versioning.get("versioning_configuration"), "versioning_block").get("status") == "Enabled", "bucket_versioning")
    public = read("artifact_bucket", "aws_s3_bucket_public_access_block", "block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")
    require(all(public.get(key) is True for key in ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")), "bucket_public_access")
    ownership = read("artifact_bucket", "aws_s3_bucket_ownership_controls", "rule")
    require(block(ownership.get("rule"), "ownership_rule") == {"object_ownership": "BucketOwnerEnforced"}, "bucket_ownership")
    encryption = read("artifact_bucket", "aws_s3_bucket_server_side_encryption_configuration", "rule")
    rule = block(encryption.get("rule"), "encryption_rule")
    default = block(rule.get("apply_server_side_encryption_by_default"), "encryption_default")
    require(default.get("sse_algorithm") == "AES256" and not default.get("kms_master_key_id")
        and rule.get("bucket_key_enabled") in (None, False), "bucket_encryption")
    policy = read("artifact_bucket", "aws_s3_bucket_policy", "policy")
    require(parse_json(policy.get("policy")) == {"Version": "2012-10-17", "Statement": [{
        "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
        "Resource": [bucket["arn"], bucket["arn"] + "/*"], "Condition": {"Bool": {
            "aws:SecureTransport": "false", "aws:PrincipalIsAWSService": "false"}}}]}, "bucket_transport_policy")

    for (module, kind), (name, service) in OWNED_TAGS.items():
        tags = read(module, kind, "tags").get("tags")
        require(isinstance(tags, dict) and tags.get("Name") == name and tags.get("service") == service, "owned_name_service_tags:" + module + "." + kind)
    logs = {}
    for module, name in (("lambda_workload", "/aws/lambda/" + PREFIX + "-lambda"), ("http_api", PATH_PREFIX + "/apigw/http")):
        log = read(module, "aws_cloudwatch_log_group", "name", "arn", "retention_in_days", "deletion_protection_enabled", "log_group_class", "kms_key_id", "skip_destroy")
        require(log.get("name") == name and log.get("arn") == f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{name}", "log_identity:" + module)
        require(log.get("retention_in_days") == 30 and log.get("deletion_protection_enabled") is log_protection
            and log.get("log_group_class") == "STANDARD" and log.get("kms_key_id") is None
            and log.get("skip_destroy") is False, "log_safety:" + module)
        logs[module] = log
    require(logs["lambda_workload"]["arn"] != logs["http_api"]["arn"], "separate_log_groups")
    secret = read("secret_metadata", "aws_secretsmanager_secret", "name", "arn", "kms_key_id", "recovery_window_in_days", "tags", "tags_all")
    require(secret.get("name") == PATH_PREFIX + "/secret/app" and isinstance(secret.get("arn"), str)
        and re.fullmatch(f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:" + re.escape(secret["name"]) + r"-[A-Za-z0-9]{6}", secret["arn"]), "secret_metadata_identity")
    require(secret.get("kms_key_id") is None and secret.get("recovery_window_in_days") == 7
        and secret.get("tags", {}).get("project") == DEFAULT_TAGS["project"], "secret_metadata_safety")
    role = read("lambda_workload", "aws_iam_role", "name", "arn", "path", "max_session_duration", "assume_role_policy")
    require(role.get("name") == PREFIX + "-role-lambda" and role.get("arn") == f"arn:aws:iam::{ACCOUNT}:role/" + role["name"]
        and role.get("path") == "/" and role.get("max_session_duration") == 3600, "execution_role_identity")
    require(parse_json(role.get("assume_role_policy")) == {"Version": "2012-10-17", "Statement": [{
        "Sid": "LambdaServiceAssumeRole", "Effect": "Allow", "Action": ["sts:AssumeRole"], "Principal": {"Service": "lambda.amazonaws.com"}}]}, "lambda_only_role_trust")
    inline = read("lambda_workload", "aws_iam_role_policy", "name", "role", "policy")
    require(inline.get("name") == PREFIX + "-policy-lambda" and inline.get("role") == role["name"], "workload_policy_role_binding")
    statements = [{"Sid": "WriteExistingLogStreams", "Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": [logs["lambda_workload"]["arn"] + ":log-stream:*"]}]
    if enabled:
        statements.append({"Sid": "ReadAuthorizedSecret", "Effect": "Allow", "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"], "Resource": [secret["arn"]]})
    require(parse_json(inline.get("policy")) == {"Version": "2012-10-17", "Statement": statements}, "exact_workload_permissions")
    function = read("lambda_workload", "aws_lambda_function", "function_name", "arn", "invoke_arn", "role", "s3_bucket", "s3_key", "s3_object_version", "runtime", "handler", "environment", "logging_config", "vpc_config", "layers", "kms_key_arn", "publish", "architectures", "memory_size", "timeout", "ephemeral_storage", "tracing_config")
    require(function.get("function_name") == PREFIX + "-lambda" and function.get("arn") == f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:" + function["function_name"], "lambda_identity")
    require(function.get("invoke_arn") == f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/" + function["arn"] + "/invocations", "lambda_invoke_identity")
    require(function.get("role") == role["arn"], "lambda_execution_role_binding")
    require(function.get("s3_bucket") == bucket["bucket"] and function.get("s3_key") == "lambda/test/function.zip"
        and function.get("s3_object_version") == "synthetic-version-001", "lambda_artifact_binding")
    require(function.get("runtime") == runtime and function.get("handler") == handler, "lambda_runtime_handler")
    require(block(function.get("logging_config"), "lambda_logging").get("log_group") == logs["lambda_workload"]["name"]
        and function["logging_config"][0].get("log_format") == "Text", "lambda_log_binding")
    expected_env = {"SECRET_ARN": secret["arn"]} if enabled else {}
    env = function.get("environment") or []
    require((block(env, "lambda_environment").get("variables") if env else {}) == expected_env, "lambda_secret_reference_only")
    require(not function.get("vpc_config") and not function.get("layers") and function.get("kms_key_arn") is None
        and function.get("publish") is False and function.get("architectures") == ["x86_64"]
        and function.get("memory_size") == 128 and function.get("timeout") == 10
        and block(function.get("ephemeral_storage"), "lambda_storage").get("size") == 512
        and block(function.get("tracing_config"), "lambda_tracing").get("mode") == "PassThrough", "lambda_safe_defaults")

    api = read("http_api", "aws_apigatewayv2_api", "id", "name", "execution_arn", "protocol_type", "disable_execute_api_endpoint", "cors_configuration", "body", "target", "route_key", "credentials_arn")
    require(api.get("name") == PREFIX + "-apigw-http" and isinstance(api.get("id"), str) and re.fullmatch(r"[a-z0-9]+", api["id"])
        and api.get("execution_arn") == f"arn:aws:execute-api:{REGION}:{ACCOUNT}:" + api["id"], "api_identity")
    require(api.get("protocol_type") == "HTTP" and api.get("disable_execute_api_endpoint") is False
        and all(not api.get(key) for key in ("cors_configuration", "body", "target", "route_key", "credentials_arn")), "http_api_safety")
    integration = read("http_api", "aws_apigatewayv2_integration", "id", "api_id", "integration_uri", "integration_type", "integration_method", "payload_format_version", "credentials_arn", "connection_type")
    require(integration.get("api_id") == api["id"] and integration.get("integration_uri") == function["invoke_arn"], "api_lambda_binding")
    require(integration.get("integration_type") == "AWS_PROXY" and integration.get("integration_method") == "POST"
        and integration.get("payload_format_version") == "2.0" and integration.get("connection_type") == "INTERNET"
        and not integration.get("credentials_arn"), "lambda_proxy_contract")
    route = read("http_api", "aws_apigatewayv2_route", "api_id", "route_key", "authorization_type", "target", "authorizer_id", "api_key_required")
    require(route.get("api_id") == api["id"] and route.get("target") == "integrations/" + integration["id"], "route_integration_binding")
    require(route.get("route_key") == "$default" and route.get("authorization_type") == "AWS_IAM"
        and not route.get("authorizer_id") and route.get("api_key_required") in (None, False), "iam_authorized_default_route")
    permission = read("http_api", "aws_lambda_permission", "function_name", "action", "principal", "source_arn", "statement_id", "qualifier", "statement_id_prefix")
    require(permission.get("function_name") == function["arn"] and permission.get("action") == "lambda:InvokeFunction"
        and permission.get("principal") == "apigateway.amazonaws.com" and permission.get("source_arn") == api["execution_arn"] + "/$default/$default"
        and permission.get("statement_id") == "AllowHttpApi" + hashlib.sha256(api["id"].encode()).hexdigest()
        and not permission.get("qualifier") and not permission.get("statement_id_prefix"), "exact_api_lambda_permission")
    stage = read("http_api", "aws_apigatewayv2_stage", "api_id", "name", "auto_deploy", "invoke_url", "access_log_settings", "default_route_settings", "route_settings", "stage_variables")
    require(stage.get("api_id") == api["id"] and stage.get("name") == "$default" and stage.get("auto_deploy") is True, "default_stage_binding")
    access = block(stage.get("access_log_settings"), "api_access_logging")
    require(access.get("destination_arn") == logs["http_api"]["arn"] and parse_json(access.get("format")) == LOG_FORMAT, "api_separate_metadata_logging")
    settings = block(stage.get("default_route_settings"), "api_route_settings")
    require(settings.get("throttling_rate_limit") == 10 and settings.get("throttling_burst_limit") == 20
        and settings.get("data_trace_enabled") in (None, False) and settings.get("logging_level") in (None, "OFF")
        and not stage.get("route_settings") and not stage.get("stage_variables"), "api_throttling_and_logging")
    require(stage.get("invoke_url") == f"https://{api['id']}.execute-api.{REGION}.amazonaws.com/", "api_invoke_url")
    # Most SDK Region/tags_all attributes are provider-computed. Mock providers
    # do not authenticate or propagate real provider configuration into them.
    # The actual cross-module ARNs above establish synthetic reference scope;
    # the separate static provider inspection establishes the configured guard.

    expected = {"api_invoke_url": stage["invoke_url"], "api_id": api["id"], "lambda_function_name": function["function_name"],
        "lambda_function_arn": function["arn"], "artifact_bucket_name": bucket["bucket"], "secret_metadata_arn": secret["arn"],
        "lambda_log_group_name": logs["lambda_workload"]["name"], "api_access_log_group_name": logs["http_api"]["name"]}
    outputs = plan.get("output_changes")
    require(isinstance(outputs, dict) and set(outputs) == set(expected), "output_inventory")
    for name, val in expected.items():
        output = outputs[name]
        require(output.get("actions") == ["create"] and output.get("after_sensitive") is False
            and not any_unknown(output.get("after_unknown", False)) and output.get("after") == val, "output_binding:" + name)
    return resources


def verify_function_package():
    """The committed function.zip must equal a reproducible rebuild of function/src."""
    import importlib.util
    import tempfile
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("function_build", ROOT / "function" / "build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    committed = (ROOT / "function" / "function.zip").read_bytes()
    with tempfile.TemporaryDirectory() as temporary:
        rebuilt = builder.build(Path(temporary) / "function.zip").read_bytes()
    require(committed == rebuilt, "function_zip_matches_source")
    source = (ROOT / "function" / "src" / "main.py").read_text(encoding="utf-8")
    require(re.search(r"^def handler\(event, context\):", source, re.M) is not None, "function_handler_present")


def verify_provider_contract():
    """Static guard only: a mock never authenticates these identity restrictions."""
    provider = (ROOT / "providers.tf").read_text(encoding="utf-8")
    require(re.search(r'provider\s+"aws"\s*\{', provider) is not None
        and re.search(r'region\s*=\s*local\.region\b', provider) is not None
        and re.search(r'allowed_account_ids\s*=\s*\[var\.aws_account_id\]', provider) is not None
        and not re.search(r'\b(alias|access_key|secret_key|token|profile)\s*=', provider), "root_provider_account_guard")
    for key, source in (("project", "var.project"), ("env", "local.environment"), ("managed", '"terraform"')):
        require(re.search(r"\b" + key + r"\s*=\s*" + re.escape(source), provider) is not None, "root_provider_default_tags:" + key)
    main = (ROOT / "main.tf").read_text(encoding="utf-8")
    for name, val in (("environment", "dev"), ("region", REGION)):
        require(re.search(r'\b' + name + r'\s*=\s*"' + re.escape(val) + '"', main) is not None, "root_fixed_identity:" + name)
    require(set(re.findall(r'module\s+"([^"]+)"\s*\{', main)) == set(MODULE_TYPES)
        and not re.search(r'\b(resource|data)\s+"', main), "root_composition_contract")


def read_events(path):
    for line in Path(path).open(encoding="utf-8"):
        event = parse_json(line)
        require(isinstance(event, dict), "capture_event_shape")
        if event.get("type") == "test_plan":
            plan = event.get("test_plan")
            require(isinstance(plan, dict), "plan_shape")
            # Stream one event at a time and discard very large provider schemas.
            event["test_plan"] = {key: plan[key] for key in ("resource_changes", "output_changes") if key in plan}
        yield event


def verify_capture(events, exit_code=0):
    require(type(exit_code) is int and exit_code == 0, "terraform_process_failure")
    expected = POSITIVE_RUNS | NEGATIVE_RUNS
    declared, summaries, terminal, plans, errors, files = None, [], set(), {}, set(), set()
    for event in events:
        require(isinstance(event, dict) and isinstance(event.get("type"), str), "capture_event_shape")
        require(not summaries, "capture_after_summary")
        kind = event["type"]
        require(kind in {"version", "test_abstract", "test_run", "test_plan", "test_file", "diagnostic", "test_summary", "log"}, "capture_event_type")
        if kind == "test_abstract":
            abstract = event.get("test_abstract")
            require(declared is None and isinstance(abstract, dict) and set(abstract) == {TEST_FILE}
                and isinstance(abstract[TEST_FILE], list) and len(abstract[TEST_FILE]) == len(expected)
                and set(abstract[TEST_FILE]) == expected, "capture_declared_coverage")
            declared = abstract
        if kind == "diagnostic":
            diagnostic = event.get("diagnostic")
            require(isinstance(diagnostic, dict) and diagnostic.get("severity") in {"error", "warning"}
                and event.get("@level") == {"error": "error", "warning": "warn"}[diagnostic["severity"]], "capture_diagnostic_level")
        if kind in {"test_run", "test_plan"} or event.get("@level") == "error":
            name = event.get("@testrun")
            require(event.get("@testfile") == TEST_FILE and name in expected, "capture_unexpected_run")
            if event.get("@level") == "error":
                require(kind == "diagnostic" and name in NEGATIVE_RUNS
                    and event["diagnostic"].get("summary") == "Invalid value for variable", "capture_unexpected_error")
                errors.add(name)
            if kind == "test_run":
                run = event.get("test_run")
                require(isinstance(run, dict) and run.get("run") == name and run.get("path") == TEST_FILE, "capture_run_identity")
                if "status" in run:
                    require(run["status"] == "pass" and name not in terminal, "capture_nonpassing_or_duplicate_run")
                    terminal.add(name)
            if kind == "test_plan":
                require(name in terminal and name not in plans, "capture_plan_order_or_duplicate")
                if name in POSITIVE_RUNS:
                    verify_plan(event["test_plan"], name == "enabled_exact_secret_read",
                        *{"node_runtime": ("nodejs22.x", "index.handler"), "java_runtime": ("java21", "com.example.Handler::handleRequest")}.get(name, ("python3.13", "app.handler")),
                        log_protection=name != "teardown_log_protection_off")
                else:
                    require(not resources_of(event["test_plan"], False), "rejected_account_plan")
                plans[name] = event["test_plan"]
        if kind == "test_file" and "status" in event.get("test_file", {}):
            require(event["test_file"]["status"] == "pass" and event.get("@testfile") == TEST_FILE
                and TEST_FILE not in files, "capture_nonpassing_or_duplicate_file")
            files.add(TEST_FILE)
        if kind == "test_summary":
            summaries.append(event.get("test_summary"))
    summary = {"status": "pass", "passed": len(expected), "failed": 0, "errored": 0, "skipped": 0}
    require(declared is not None and len(summaries) == 1 and isinstance(summaries[0], dict)
        and all(type(summaries[0].get(key)) is int for key in ("passed", "failed", "errored", "skipped"))
        and summaries[0] == summary, "capture_summary_counts")
    require(terminal == expected and set(plans) == expected and errors == NEGATIVE_RUNS and files == {TEST_FILE}, "capture_complete_runs")
    return plans


def expect_rejection(operation, identifier):
    try:
        operation()
    except (ValueError, KeyError, TypeError) as error:
        return {"id": identifier, "detected": True, "reason": str(error)}
    raise ValueError("unsafe_input_accepted:" + identifier)


def semantic_mutations(plan, enabled=False):
    results = []

    def mutate(identifier, module, kind, transform):
        changed = copy.deepcopy(plan)
        item = next(item for item in changed["resource_changes"] if item["address"] == f"module.{module}.{kind}.this")
        transform(item["change"]["after"])
        # A mutation that changes nothing would pass silently; require an actual change.
        require(changed != plan, "mutation_noop:" + identifier)
        results.append(expect_rejection(lambda: verify_plan(changed, enabled), identifier))

    mutate("unrelated-execution-role", "lambda_workload", "aws_lambda_function", lambda v: v.update(role=f"arn:aws:iam::{ACCOUNT}:role/other"))
    mutate("unversioned-artifact", "lambda_workload", "aws_lambda_function", lambda v: v.update(s3_object_version="null"))
    mutate("unrelated-artifact-bucket", "lambda_workload", "aws_lambda_function", lambda v: v.update(s3_bucket="other-artifacts"))
    mutate("unrelated-artifact-key", "lambda_workload", "aws_lambda_function", lambda v: v.update(s3_key="other.zip"))
    mutate("unrelated-lambda-log-group", "lambda_workload", "aws_lambda_function", lambda v: v["logging_config"][0].update(log_group="/other"))
    mutate("plaintext-environment", "lambda_workload", "aws_lambda_function", lambda v: v.update(environment=[{"variables": {"PASSWORD": "synthetic-value"}}]))
    mutate("anonymous-route", "http_api", "aws_apigatewayv2_route", lambda v: v.update(authorization_type="NONE"))
    mutate("unrelated-integration", "http_api", "aws_apigatewayv2_integration", lambda v: v.update(integration_uri=v["integration_uri"].replace(PREFIX + "-lambda", PREFIX + "-other")))
    mutate("broad-invoke-source", "http_api", "aws_lambda_permission", lambda v: v.update(source_arn=v["source_arn"].replace("/$default/$default", "/*/*")))
    mutate("wildcard-invoke-principal", "http_api", "aws_lambda_permission", lambda v: v.update(principal="*"))
    mutate("reuse-lambda-access-log", "http_api", "aws_apigatewayv2_stage", lambda v: v["access_log_settings"][0].update(destination_arn=f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/lambda/{PREFIX}-lambda"))
    mutate("sensitive-access-log", "http_api", "aws_apigatewayv2_stage", lambda v: v["access_log_settings"][0].update(format=json.dumps({**LOG_FORMAT, "authorization": "$request.header.Authorization"})))
    mutate("disable-public-block", "artifact_bucket", "aws_s3_bucket_public_access_block", lambda v: v.update(block_public_policy=False))
    mutate("suspend-versioning", "artifact_bucket", "aws_s3_bucket_versioning", lambda v: v["versioning_configuration"][0].update(status="Suspended"))
    mutate("force-destroy", "artifact_bucket", "aws_s3_bucket", lambda v: v.update(force_destroy=True))

    def escalate(v):
        policy = parse_json(v["policy"])
        policy["Statement"].append({"Effect": "Allow", "Action": ["iam:PassRole"], "Resource": ["*"]})
        v["policy"] = json.dumps(policy)

    mutate("unrestricted-pass-role", "lambda_workload", "aws_iam_role_policy", escalate)
    if enabled:
        def add_kms(v):
            policy = parse_json(v["policy"])
            policy["Statement"].append({"Effect": "Allow", "Action": ["kms:Decrypt"], "Resource": ["*"]})
            v["policy"] = json.dumps(policy)
        mutate("enabled-secret-kms-escalation", "lambda_workload", "aws_iam_role_policy", add_kms)
        def broaden_secret(v):
            policy = parse_json(v["policy"])
            policy["Statement"][1]["Resource"] = ["*"]
            v["policy"] = json.dumps(policy)
        mutate("wildcard-secret-resource", "lambda_workload", "aws_iam_role_policy", broaden_secret)
    else:
        def add_secret(v):
            policy = parse_json(v["policy"])
            policy["Statement"].append({"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue", "kms:Decrypt"], "Resource": ["*"]})
            v["policy"] = json.dumps(policy)
        mutate("disabled-secret-kms-escalation", "lambda_workload", "aws_iam_role_policy", add_secret)
    return results


def capture_faults(events):
    results = [expect_rejection(lambda: verify_capture(events, 1), "nonzero-process-status")]

    def first(items, kind):
        return next(i for i, item in enumerate(items) if item["type"] == kind)

    def inject(identifier, transform):
        changed = copy.deepcopy(events)
        transform(changed)
        results.append(expect_rejection(lambda: verify_capture(changed), identifier))

    inject("missing-plan", lambda e: e.pop(first(e, "test_plan")))
    inject("duplicate-plan", lambda e: e.insert(first(e, "test_plan"), copy.deepcopy(e[first(e, "test_plan")])))
    inject("missing-file-terminal", lambda e: e.pop(next(i for i, v in enumerate(e) if v["type"] == "test_file" and "status" in v.get("test_file", {}))))
    inject("missing-summary", lambda e: e.pop(first(e, "test_summary")))
    inject("duplicate-summary", lambda e: e.append(copy.deepcopy(e[first(e, "test_summary")])))
    inject("skipped-summary", lambda e: e[first(e, "test_summary")]["test_summary"].update(skipped=1))
    inject("boolean-summary-count", lambda e: e[first(e, "test_summary")]["test_summary"].update(failed=False))
    inject("failed-run", lambda e: next(v["test_run"] for v in e if v["type"] == "test_run" and v["test_run"].get("status")).update(status="fail"))
    inject("missing-run", lambda e: e.pop(next(i for i, v in enumerate(e) if v["type"] == "test_run" and v["test_run"].get("status"))))
    inject("unexpected-run", lambda e: e[first(e, "test_plan")].update({"@testrun": "unreviewed"}))
    inject("missing-resource", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"].pop())
    inject("additional-resource", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"].append(copy.deepcopy(e[first(e, "test_plan")]["test_plan"]["resource_changes"][0])))
    inject("aws-data-source", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0].update(mode="data"))
    inject("non-create-action", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].update(actions=["delete", "create"]))
    inject("unknown-output", lambda e: e[first(e, "test_plan")]["test_plan"]["output_changes"]["api_invoke_url"].update(after_unknown=True))
    inject("unknown-security-field", lambda e: next(r for r in e[first(e, "test_plan")]["test_plan"]["resource_changes"] if r["address"] == "module.http_api.aws_cloudwatch_log_group.this")["change"]["after_unknown"].update(name=True))
    inject("missing-known-null-security-field", lambda e: next(v for v in e[first(e, "test_plan")]["test_plan"]["resource_changes"] if v["type"] == "aws_lambda_function")["change"]["after"].pop("kms_key_arn"))
    inject("missing-change-metadata", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].pop("after_unknown"))
    for identifier, raw in (("malformed-jsonl", "{"), ("duplicate-json-key", '{"type":"test_summary","type":"test_plan"}'), ("nonfinite-json", '{"count":NaN}')):
        results.append(expect_rejection(lambda text=raw: parse_json(text), identifier))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-events", required=True, type=Path)
    parser.add_argument("--terraform-exit-code", required=True, type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        verify_provider_contract()
        verify_function_package()
        events = list(read_events(args.test_events))
        plans = verify_capture(events, args.terraform_exit_code)
        mutations = []
        if args.self_test:
            for name in ("default_secret_read_disabled", "enabled_exact_secret_read"):
                mutations.extend({"profile": name, **result} for result in semantic_mutations(plans[name], name == "enabled_exact_secret_read"))
        faults = capture_faults(events) if args.self_test else []
        print(json.dumps({"status": "passed", "aws_api_calls": 0, "evidence_type": "static_actual_root_mock_plan",
            "native_tests": len(POSITIVE_RUNS | NEGATIVE_RUNS), "positive_plans": len(POSITIVE_RUNS), "negative_plans": len(NEGATIVE_RUNS),
            "module_instances": len(MODULE_TYPES), "managed_resources_per_positive_plan": len(INVENTORY),
            "resource_inventory": dict(Counter(address.split(".")[2] for address in INVENTORY)),
            "semantic_mutation_count": len(mutations), "semantic_mutations": mutations,
            "capture_failure_injections": len(faults), "capture_faults": faults,
            "provider_identity": "static account guard and fixed Region inspected; mock execution does not authenticate an AWS account",
            "limitations": ["No deployment, artifact, initialized secret, real authorization, propagation, invocation or logging delivery was tested."]}, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("Root integration verification failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
