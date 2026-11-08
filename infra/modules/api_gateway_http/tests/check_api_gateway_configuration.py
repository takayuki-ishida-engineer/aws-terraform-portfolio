#!/usr/bin/env python3
"""Verify actual offline HTTP API plans, not a deployed Lambda IAM policy.

Only the reviewed five-resource configuration and complete successful native
capture are accepted. No credentials, Terraform subprocesses or AWS APIs are used.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


TEST_FILE = "tests/api_gateway_http.tftest.hcl"
POSITIVE_RUNS = {
    "default_http_api_configuration", "resource_attribute_outputs", "govcloud_reference_scope",
    "minimum_api_name", "maximum_api_name", "caller_owned_tags", "maximum_tag_limits",
    "effective_provider_default_tags",
}
NEGATIVE_RUNS = {
    "empty_api_name", "invalid_api_name", "overlong_api_name", "null_lambda_function_arn",
    "malformed_lambda_function_arn", "lambda_alias_arn", "lambda_version_arn", "wildcard_lambda_function_arn",
    "unsupported_lambda_partition", "unsupported_lambda_region", "overlong_lambda_function_arn",
    "unsupported_numeric_region_shape", "null_lambda_invoke_arn",
    "malformed_lambda_invoke_arn", "mismatched_lambda_invoke_function", "mismatched_lambda_invoke_account",
    "mismatched_lambda_invoke_region", "mismatched_lambda_invoke_partition", "null_access_log_group_arn",
    "malformed_access_log_group_arn", "wildcard_access_log_group_arn", "log_stream_instead_of_group",
    "log_group_api_suffix", "mismatched_log_account", "mismatched_log_region", "mismatched_log_partition",
    "empty_tag_key", "reserved_tag_prefix", "null_tag_value", "overlong_tag_key", "overlong_tag_value",
    "too_many_tags", "invalid_tag_key_character", "invalid_tag_value_character", "actual_api_wrong_account",
    "actual_api_wrong_region", "actual_api_wrong_partition", "effective_api_tags_exceed_limit",
    "effective_stage_tags_exceed_limit",
}
TYPES = {"aws_apigatewayv2_api", "aws_apigatewayv2_integration", "aws_apigatewayv2_route",
    "aws_apigatewayv2_stage", "aws_lambda_permission"}
LOG_FORMAT = {key: "$context." + key for key in (
    "requestId", "routeKey", "httpMethod", "status", "responseLatency", "integrationLatency", "responseLength")}
REGION_PATTERN = r"[a-z]{2}(?:-[a-z]+){1,2}-[1-9]"
FUNCTION_PATTERN = rf"arn:(aws|aws-us-gov):lambda:({REGION_PATTERN}):([0-9]{{12}}):function:([A-Za-z0-9_-]{{1,64}})"
LOG_PATTERN = rf"arn:(aws|aws-us-gov):logs:({REGION_PATTERN}):([0-9]{{12}}):log-group:([A-Za-z0-9_./#-]{{1,512}})"
KNOWN_FIELDS = {
    "aws_apigatewayv2_api": ("id", "name", "protocol_type", "disable_execute_api_endpoint", "execution_arn", "api_endpoint", "tags", "tags_all", "body", "target", "credentials_arn", "route_key", "cors_configuration"),
    "aws_apigatewayv2_integration": ("id", "api_id", "integration_type", "integration_method", "integration_uri", "payload_format_version", "credentials_arn", "connection_id", "connection_type", "request_parameters", "request_templates", "response_parameters", "tls_config"),
    "aws_apigatewayv2_route": ("api_id", "route_key", "authorization_type", "target", "authorizer_id", "authorization_scopes", "api_key_required", "request_models", "request_parameter"),
    "aws_apigatewayv2_stage": ("api_id", "name", "auto_deploy", "invoke_url", "tags", "tags_all", "access_log_settings", "default_route_settings", "route_settings", "stage_variables", "client_certificate_id"),
    "aws_lambda_permission": ("action", "principal", "function_name", "source_arn", "statement_id", "statement_id_prefix", "qualifier", "source_account", "principal_org_id", "function_url_auth_type", "invoked_via_function_url", "event_source_token"),
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


def one_block(value, code):
    require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict), code)
    return value[0]


def valid_region(partition, region):
    return len(region) <= 63 and (region in {"us-gov-west-1", "us-gov-east-1"}
        if partition == "aws-us-gov" else not region.startswith(("cn-", "us-gov-", "us-iso", "eu-iso")))


def function_scope(arn):
    match = re.fullmatch(FUNCTION_PATTERN, arn) if isinstance(arn, str) else None
    # The pinned provider's function-name validator still limits full ARNs to 140.
    require(match is not None and len(arn) <= 140 and valid_region(*match.groups()[:2]), "lambda_function_reference")
    return match.groups()[:3]


def invocation_arn(function):
    partition, region, _account = function_scope(function)
    return f"arn:{partition}:apigateway:{region}:lambda:path/2015-03-31/functions/{function}/invocations"


def valid_tags(tags):
    def characters(text):
        return all(unicodedata.category(char)[0] in "LZN" or char in "_.:/=+@-" for char in text)
    return isinstance(tags, dict) and len(tags) <= 50 and all(
        isinstance(key, str) and 1 <= len(key) <= 128 and not key.lower().startswith("aws:")
        and characters(key) and isinstance(value, str) and len(value) <= 256 and characters(value)
        for key, value in tags.items())


def resources_of(plan, complete):
    require(isinstance(plan, dict), "plan_shape")
    changes = plan.get("resource_changes")
    if not complete and changes is None:
        changes = []
    require(isinstance(changes, list), "plan_resource_changes")
    resources = {}
    for resource in changes:
        require(isinstance(resource, dict), "resource_shape")
        kind, change = resource.get("type"), resource.get("change")
        require(kind in TYPES and kind not in resources, "resource_inventory")
        require(resource.get("mode") == "managed" and resource.get("name") == "this"
            and resource.get("address") == kind + ".this" and "index" not in resource
            and resource.get("provider_name") == "registry.terraform.io/hashicorp/aws", "resource_identity")
        require(isinstance(change, dict) and "before" in change and change["before"] is None
            and change.get("actions") == ["create"] and "after_unknown" in change, "resource_create_metadata")
        unknown = change["after_unknown"]
        any_unknown(unknown)
        require(isinstance(unknown, dict) and not any(any_unknown(unknown.get(key, False))
            for key in (*KNOWN_FIELDS[kind], "region")), "required_configuration_unknown")
        require(isinstance(change.get("after"), dict), "resource_after")
        resources[kind] = change["after"]
    if complete:
        require(set(resources) == TYPES, "complete_resource_inventory")
    return resources


def verify_fixed(resources):
    api = resources.get("aws_apigatewayv2_api")
    if api is not None:
        require(api.get("protocol_type") == "HTTP" and api.get("disable_execute_api_endpoint") is False, "http_api_endpoint")
        require(all(not api.get(key) for key in ("body", "target", "credentials_arn", "route_key", "cors_configuration")), "api_no_quick_create_or_cors")
        require(isinstance(api.get("id"), str) and re.fullmatch(r"[a-z0-9]+", api["id"]), "api_id")
        require(isinstance(api.get("execution_arn"), str) and re.fullmatch(
            rf"arn:(aws|aws-us-gov):execute-api:{REGION_PATTERN}:[0-9]{{12}}:" + re.escape(api["id"]), api["execution_arn"]), "api_execution_identity")
    integration = resources.get("aws_apigatewayv2_integration")
    if integration is not None:
        require(integration.get("integration_type") == "AWS_PROXY" and integration.get("integration_method") == "POST", "lambda_proxy_integration")
        require(integration.get("payload_format_version") == "2.0", "payload_version")
        require(integration.get("connection_type") in (None, "INTERNET") and all(not integration.get(key) for key in (
            "credentials_arn", "connection_id", "integration_subtype", "request_parameters", "request_templates", "response_parameters", "tls_config")), "integration_no_credentials_or_transforms")
    route = resources.get("aws_apigatewayv2_route")
    if route is not None:
        require(route.get("route_key") == "$default" and route.get("authorization_type") == "AWS_IAM", "default_route_iam")
        require(route.get("api_key_required") in (None, False) and all(not route.get(key) for key in (
            "authorizer_id", "authorization_scopes", "request_models", "request_parameter")), "route_no_alternate_authorization")
    stage = resources.get("aws_apigatewayv2_stage")
    if stage is not None:
        require(stage.get("name") == "$default" and stage.get("auto_deploy") is True, "default_stage_deployment")
        logging = one_block(stage.get("access_log_settings"), "mandatory_access_logging")
        require(isinstance(logging.get("format"), str) and parse_json(logging["format"]) == LOG_FORMAT, "access_log_format")
        settings = one_block(stage.get("default_route_settings"), "default_route_settings")
        require(settings.get("throttling_rate_limit") == 10 and settings.get("throttling_burst_limit") == 20, "default_throttling")
        require(settings.get("data_trace_enabled") in (None, False) and settings.get("logging_level") in (None, "OFF")
            and all(not stage.get(key) for key in ("route_settings", "stage_variables", "client_certificate_id")), "stage_no_payload_logging_or_overrides")
    permission = resources.get("aws_lambda_permission")
    if permission is not None:
        require(permission.get("action") == "lambda:InvokeFunction" and permission.get("principal") == "apigateway.amazonaws.com", "lambda_invoke_boundary")
        function_scope(permission.get("function_name"))
        require(all(not permission.get(key) for key in ("qualifier", "source_account", "principal_org_id", "function_url_auth_type",
            "invoked_via_function_url", "event_source_token", "statement_id_prefix")), "permission_no_unreviewed_conditions")


def verify_bindings(resources):
    api = resources.get("aws_apigatewayv2_api")
    require(api is not None or not resources, "dependent_resources_require_api")
    if api is None:
        return
    require(all(value.get("region") == api["execution_arn"].split(":")[3] for value in resources.values()), "resource_region_binding")
    integration, route, stage, permission = (resources.get(key) for key in (
        "aws_apigatewayv2_integration", "aws_apigatewayv2_route", "aws_apigatewayv2_stage", "aws_lambda_permission"))
    for value in (integration, route, stage):
        if value is not None:
            require(value.get("api_id") == api["id"], "api_resource_binding")
    if permission is not None:
        function = permission["function_name"]
        scope = function_scope(function)
        require(api["execution_arn"] == "arn:%s:execute-api:%s:%s:%s" % (*scope, api["id"]), "api_function_scope")
        require(permission.get("source_arn") == api["execution_arn"] + "/$default/$default", "permission_source_scope")
        require(permission.get("statement_id") == "AllowHttpApi" + hashlib.sha256(api["id"].encode()).hexdigest(), "permission_statement_identity")
        if integration is not None:
            require(integration.get("integration_uri") == invocation_arn(function), "integration_function_binding")
        if stage is not None:
            arn = one_block(stage["access_log_settings"], "mandatory_access_logging").get("destination_arn")
            match = re.fullmatch(LOG_PATTERN, arn) if isinstance(arn, str) else None
            require(match is not None and match.groups()[:3] == scope and not match[4].startswith("aws/"), "access_log_scope")
    if route is not None:
        require(integration is not None and route.get("target") == "integrations/" + integration["id"], "route_integration_binding")
    if stage is not None:
        require(permission is not None and route is not None, "stage_requires_route_and_permission")


def verify_plan(plan, complete=True):
    resources = resources_of(plan, complete)
    verify_fixed(resources)
    verify_bindings(resources)
    if not complete:
        return resources
    api, stage = resources["aws_apigatewayv2_api"], resources["aws_apigatewayv2_stage"]
    require(isinstance(api.get("name"), str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", api["name"]), "api_name")
    for value in (api, stage):
        require(valid_tags(value.get("tags")) and valid_tags(value.get("tags_all")), "effective_tags")
        require(all(value["tags_all"].get(key) == item for key, item in value["tags"].items()), "caller_tag_precedence")
    require(isinstance(stage.get("invoke_url"), str) and re.fullmatch(r"https://[^\s?#]+/", stage["invoke_url"]), "stage_invoke_url")
    outputs = plan.get("output_changes")
    expected = {"api_id": api["id"], "execution_arn": api["execution_arn"], "invoke_url": stage["invoke_url"]}
    require(isinstance(outputs, dict) and set(outputs) == set(expected), "output_inventory")
    for name, value in expected.items():
        output = outputs[name]
        require(output.get("actions") == ["create"] and output.get("after_sensitive") is False
            and not any_unknown(output.get("after_unknown", False)) and output.get("after") == value, "output_binding:" + name)
    return resources


def verify_fixture(name, resources):
    """Bind actual plans independently to the reviewed synthetic native inputs."""
    api = resources["aws_apigatewayv2_api"]
    expected_name = {"minimum_api_name": "a", "maximum_api_name": "a" * 128}.get(name, "test-http-api")
    require(api["name"] == expected_name, "reviewed_api_name")
    partition, region, account = ("aws-us-gov", "us-gov-west-1", "222222222222") if name == "govcloud_reference_scope" else ("aws", "ca-central-1", "111111111111")
    function = f"arn:{partition}:lambda:{region}:{account}:function:test-api-handler"
    require(resources["aws_lambda_permission"]["function_name"] == function, "reviewed_lambda_input")
    require(one_block(resources["aws_apigatewayv2_stage"]["access_log_settings"], "mandatory_access_logging")["destination_arn"]
        == f"arn:{partition}:logs:{region}:{account}:log-group:/test/api-access", "reviewed_log_input")
    expected_tags = {}
    if name == "caller_owned_tags":
        expected_tags = {"Owner": "Root-Owned", "Purpose": "HTTP access", "Empty": ""}
    if name == "maximum_tag_limits":
        expected_tags = {"K" * 128: "v" * 256, **{f"tag-{i:02}": "" for i in range(49)}}
    if name == "effective_provider_default_tags":
        expected_tags = {"Owner": "Root-Owned"}
    expected_all = {**expected_tags, **({"CostCentre": "test-default"} if name == "effective_provider_default_tags" else {})}
    require(all(resources[kind]["tags"] == expected_tags and resources[kind]["tags_all"] == expected_all
        for kind in ("aws_apigatewayv2_api", "aws_apigatewayv2_stage")), "reviewed_tag_inputs")


def read_events(path):
    for line in Path(path).open(encoding="utf-8"):
        event = parse_json(line)
        require(isinstance(event, dict), "capture_event_shape")
        if event.get("type") == "test_plan":
            plan = event["test_plan"]
            require(isinstance(plan, dict), "plan_shape")
            event["test_plan"] = {key: plan[key] for key in ("resource_changes", "output_changes") if key in plan}
        yield event


def negative_inventory(name):
    if "lambda_invoke" in name:
        return {"aws_apigatewayv2_api", "aws_lambda_permission"}
    if name in {"null_access_log_group_arn", "malformed_access_log_group_arn", "wildcard_access_log_group_arn",
        "log_stream_instead_of_group", "log_group_api_suffix", "mismatched_log_account", "mismatched_log_region", "mismatched_log_partition"}:
        return TYPES - {"aws_apigatewayv2_stage"}
    if name.startswith("actual_api_") or name == "effective_api_tags_exceed_limit":
        return {"aws_apigatewayv2_api"}
    return TYPES if name == "effective_stage_tags_exceed_limit" else set()


def verify_capture(events, exit_code=0):
    require(type(exit_code) is int and exit_code == 0, "terraform_process_failure")
    expected_runs = POSITIVE_RUNS | NEGATIVE_RUNS
    terminal, plans, errors, summaries = set(), {}, set(), []
    declared = None
    for event in events:
        require(isinstance(event, dict) and isinstance(event.get("type"), str), "capture_event_shape")
        require(not summaries, "capture_after_summary")
        kind = event["type"]
        require(kind in {"version", "test_abstract", "test_run", "test_plan", "test_file", "diagnostic", "test_summary", "log"}, "capture_event_type")
        if kind == "test_abstract":
            abstract = event["test_abstract"]
            require(declared is None and isinstance(abstract, dict) and set(abstract) == {TEST_FILE}
                and isinstance(abstract[TEST_FILE], list), "capture_test_files")
            declared = abstract[TEST_FILE]
            require(len(declared) == len(expected_runs) and set(declared) == expected_runs, "capture_declared_coverage")
        if kind == "diagnostic":
            diagnostic = event.get("diagnostic")
            require(isinstance(diagnostic, dict) and diagnostic.get("severity") in {"error", "warning"}, "diagnostic_shape")
            require(event.get("@level") == {"error": "error", "warning": "warn"}[diagnostic["severity"]], "diagnostic_error_level")
        if kind in {"test_run", "test_plan"} or event.get("@level") == "error":
            name = event.get("@testrun")
            require(event.get("@testfile") == TEST_FILE and name in expected_runs, "capture_unexpected_run")
            if event.get("@level") == "error":
                require(name in NEGATIVE_RUNS and kind == "diagnostic", "capture_unexpected_error")
                expected_error = "Resource postcondition failed" if name.startswith(("actual_api_", "effective_api_", "effective_stage_")) else "Invalid value for variable"
                require(event["diagnostic"].get("summary") == expected_error, "unexpected_validation_error")
                errors.add(name)
            if kind == "test_run":
                run = event["test_run"]
                require(run.get("run") == name and run.get("path") == TEST_FILE, "capture_run_identity")
                if "status" in run:
                    require(run["status"] == "pass" and name not in terminal, "capture_nonpassing_or_duplicate_run")
                    terminal.add(name)
            if kind == "test_plan":
                require(name in terminal and name not in plans, "capture_plan_order_or_duplicate")
                resources = verify_plan(event["test_plan"], name in POSITIVE_RUNS)
                if name in POSITIVE_RUNS:
                    verify_fixture(name, resources)
                else:
                    require(set(resources) == negative_inventory(name), "rejected_plan_shape")
                    if name.startswith("actual_api_"):
                        api = resources["aws_apigatewayv2_api"]
                        require(api["execution_arn"] != "arn:aws:execute-api:ca-central-1:111111111111:" + api["id"], "rejected_api_scope_evidence")
                    if name.startswith(("effective_api_", "effective_stage_")):
                        kind = "aws_apigatewayv2_api" if name.startswith("effective_api_") else "aws_apigatewayv2_stage"
                        require(valid_tags(resources[kind]["tags"]) and not valid_tags(resources[kind]["tags_all"]), "rejected_effective_tags_evidence")
                plans[name] = event["test_plan"]
        if kind == "test_file" and "status" in event["test_file"]:
            require(event["test_file"]["status"] == "pass", "capture_nonpassing_file")
        if kind == "test_summary":
            summaries.append(event["test_summary"])
    expected = {"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}
    require(declared is not None and len(summaries) == 1 and isinstance(summaries[0], dict)
        and all(type(summaries[0].get(key)) is int for key in ("passed", "failed", "errored", "skipped"))
        and summaries[0] == expected, "capture_summary_counts")
    require(terminal == expected_runs and set(plans) == expected_runs and errors == NEGATIVE_RUNS, "capture_complete_runs")
    return plans


def expect_rejection(operation, identifier, expected_code=None):
    try:
        operation()
    except (ValueError, KeyError, TypeError) as error:
        require(expected_code is None or str(error) == expected_code, "wrong_rejection:" + identifier)
        return {"id": identifier, "detected": True, "reason": str(error)}
    raise ValueError("unsafe_input_accepted:" + identifier)


def semantic_mutations(plan):
    results = []

    def mutate(identifier, code, transform):
        changed = copy.deepcopy(plan)
        values = {r["type"]: r["change"]["after"] for r in changed["resource_changes"]}
        transform(values)
        def check():
            verify_fixture("default_http_api_configuration", verify_plan(changed))
        results.append(expect_rejection(check, identifier, code))

    mutate("anonymous-route", "default_route_iam", lambda r: r["aws_apigatewayv2_route"].update(authorization_type="NONE"))
    mutate("broad-lambda-source", "permission_source_scope", lambda r: r["aws_lambda_permission"].update(source_arn=r["aws_apigatewayv2_api"]["execution_arn"] + "/*/*"))
    mutate("wildcard-lambda-principal", "lambda_invoke_boundary", lambda r: r["aws_lambda_permission"].update(principal="*"))
    def other_function(resources):
        function = resources["aws_lambda_permission"]["function_name"] + "-other"
        resources["aws_lambda_permission"]["function_name"] = function
        resources["aws_apigatewayv2_integration"]["integration_uri"] = invocation_arn(function)
    mutate("unrelated-function-and-integration", "reviewed_lambda_input", other_function)
    mutate("nonunique-statement-id", "permission_statement_identity", lambda r: r["aws_lambda_permission"].update(statement_id="AllowHttpApi"))
    mutate("remove-access-logs", "mandatory_access_logging", lambda r: r["aws_apigatewayv2_stage"].update(access_log_settings=[]))
    mutate("unrelated-log-destination", "reviewed_log_input", lambda r: r["aws_apigatewayv2_stage"]["access_log_settings"][0].update(destination_arn=r["aws_apigatewayv2_stage"]["access_log_settings"][0]["destination_arn"] + "-other"))
    mutate("log-sensitive-header", "access_log_format", lambda r: r["aws_apigatewayv2_stage"]["access_log_settings"][0].update(format=json.dumps({**LOG_FORMAT, "authorization": "$request.header.Authorization"})))
    mutate("wrong-payload-version", "payload_version", lambda r: r["aws_apigatewayv2_integration"].update(payload_format_version="1.0"))
    mutate("disable-throttling", "default_throttling", lambda r: r["aws_apigatewayv2_stage"]["default_route_settings"][0].update(throttling_rate_limit=0, throttling_burst_limit=0))
    mutate("unexpected-route-target", "route_integration_binding", lambda r: r["aws_apigatewayv2_route"].update(target="integrations/unreviewed"))
    mutate("disable-auto-deployment", "default_stage_deployment", lambda r: r["aws_apigatewayv2_stage"].update(auto_deploy=False))
    mutate("integration-execution-role", "integration_no_credentials_or_transforms", lambda r: r["aws_apigatewayv2_integration"].update(credentials_arn="arn:aws:iam::111111111111:role/test-unreviewed"))
    mutate("permissive-cors", "api_no_quick_create_or_cors", lambda r: r["aws_apigatewayv2_api"].update(cors_configuration=[{"allow_origins": ["*"]}]))
    mutate("qualified-lambda-permission", "permission_no_unreviewed_conditions", lambda r: r["aws_lambda_permission"].update(qualifier="live"))
    mutate("cross-account-permission", "api_function_scope", lambda r: r["aws_lambda_permission"].update(function_name=r["aws_lambda_permission"]["function_name"].replace("111111111111", "222222222222")))
    changed = copy.deepcopy(plan)
    changed["resource_changes"].append(copy.deepcopy(next(r for r in changed["resource_changes"] if r["type"] == "aws_apigatewayv2_route")))
    results.append(expect_rejection(lambda: verify_plan(changed), "additional-route-resource", "resource_inventory"))
    return results


def capture_faults(events):
    results = [expect_rejection(lambda: verify_capture(events, 1), "nonzero-process-status", "terraform_process_failure")]

    def first(items, kind):
        return next(i for i, event in enumerate(items) if event["type"] == kind)

    def inject(identifier, transform):
        changed = copy.deepcopy(events)
        transform(changed)
        results.append(expect_rejection(lambda: verify_capture(changed), identifier))

    inject("missing-plan", lambda e: e.pop(first(e, "test_plan")))
    inject("duplicate-plan", lambda e: e.insert(first(e, "test_plan"), copy.deepcopy(e[first(e, "test_plan")])))
    inject("missing-summary", lambda e: e.pop(first(e, "test_summary")))
    inject("duplicate-summary", lambda e: e.append(copy.deepcopy(e[first(e, "test_summary")])))
    inject("skipped-summary", lambda e: e[first(e, "test_summary")]["test_summary"].update(skipped=1))
    inject("boolean-summary-count", lambda e: e[first(e, "test_summary")]["test_summary"].update(failed=False))
    inject("failed-run", lambda e: next(v["test_run"] for v in e if v["type"] == "test_run" and v["test_run"].get("status")).update(status="fail"))
    inject("missing-run", lambda e: e.pop(next(i for i, v in enumerate(e) if v["type"] == "test_run" and v["test_run"].get("status"))))
    inject("unexpected-run", lambda e: e[first(e, "test_plan")].update({"@testrun": "unreviewed-run"}))
    inject("missing-resource", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"].pop())
    inject("non-create-action", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].update(actions=["delete", "create"]))
    inject("unknown-output", lambda e: e[first(e, "test_plan")]["test_plan"]["output_changes"]["invoke_url"].update(after_unknown=True))
    inject("unknown-security-value", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].update(after_unknown=True))
    inject("missing-change-metadata", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].pop("after_unknown"))
    inject("contradictory-error-level", lambda e: next(v for v in e if v["type"] == "diagnostic" and v.get("@level") == "error").update({"@level": "info"}))
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
        events = list(read_events(args.test_events))
        plans = verify_capture(events, args.terraform_exit_code)
        mutations = semantic_mutations(plans["default_http_api_configuration"]) if args.self_test else []
        faults = capture_faults(events) if args.self_test else []
        shapes = Counter("empty" if not plan.get("resource_changes") else "+".join(sorted(r["type"] for r in plan["resource_changes"]))
            for name, plan in plans.items() if name in NEGATIVE_RUNS)
        print(json.dumps({
            "status": "passed", "evidence_type": "static_actual_plan_verification", "aws_api_calls": 0,
            "native_tests": len(POSITIVE_RUNS | NEGATIVE_RUNS), "positive_plans": len(POSITIVE_RUNS), "negative_plans": len(NEGATIVE_RUNS),
            "negative_plan_shapes": dict(shapes), "resource_inventory": {kind: 1 for kind in sorted(TYPES)},
            "semantic_mutations": mutations, "semantic_mutation_count": len(mutations),
            "capture_faults": faults, "capture_failure_injections": len(faults),
            "limitations": ["Mock/static planned permission fields are not a deployed Lambda IAM policy or real authorization, ownership, execution or log-delivery proof."],
        }, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("HTTP API actual-plan verification failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
