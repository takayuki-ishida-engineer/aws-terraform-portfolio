#!/usr/bin/env python3
"""Verify actual offline HTTP API plans, not a deployed Lambda IAM policy.

Only the reviewed six-resource configuration and complete successful native
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
from check_r2_migration import verify_structure, source_mutations


TEST_FILE = "tests/api_gateway_http.tftest.hcl"
MANIFEST = json.loads((Path(__file__).parent / 'coverage.json').read_text())
POSITIVE_RUNS = {case['new_run'] for case in MANIFEST if not case['negative']}
NEGATIVE_RUNS = {case['new_run'] for case in MANIFEST if case['negative']}
REJECTED_SHAPES = json.loads((Path(__file__).parent / 'rejected_shapes.json').read_text())
TYPES = {"aws_apigatewayv2_api", "aws_apigatewayv2_integration", "aws_apigatewayv2_route",
    "aws_apigatewayv2_stage", "aws_lambda_permission", "aws_cloudwatch_log_group"}
LOG_FORMAT = {key: "$context." + key for key in (
    "requestId", "routeKey", "httpMethod", "status", "responseLatency", "integrationLatency", "responseLength")}
REGION_PATTERN = r"[a-z]{2}(?:-[a-z]+){1,2}-[1-9]"
FUNCTION_PATTERN = rf"arn:(aws|aws-us-gov):lambda:({REGION_PATTERN}):([0-9]{{12}}):function:([A-Za-z0-9_-]{{1,64}})"
LOG_PATTERN = rf"arn:(aws|aws-us-gov):logs:({REGION_PATTERN}):([0-9]{{12}}):log-group:([A-Za-z0-9_./#-]{{1,512}})"
KNOWN_FIELDS = {
    "aws_cloudwatch_log_group": ("name", "arn", "retention_in_days", "deletion_protection_enabled", "log_group_class", "kms_key_id", "skip_destroy", "tags", "tags_all"),
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
        require(all(key in change["after"] for key in KNOWN_FIELDS[kind]), "required_configuration_missing")
        resources[kind] = change["after"]
    if complete:
        require(set(resources) == TYPES, "complete_resource_inventory")
    return resources


def verify_fixed(resources):
    log = resources.get("aws_cloudwatch_log_group")
    if log is not None:
        require(isinstance(log.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_./#-]{1,512}", log["name"])
            and not log["name"].startswith("aws/"), "owned_log_name")
        require(type(log.get("retention_in_days")) is int and log["retention_in_days"] in
            {1,3,5,7,14,30,60,90,120,150,180,365,400,545,731,1096,1827,2192,2557,2922,3288,3653}
            and type(log.get("deletion_protection_enabled")) is bool and log.get("log_group_class") == "STANDARD"
            and log.get("skip_destroy") is False, "owned_log_lifecycle")
        key = log.get("kms_key_id")
        require(key is None or isinstance(key,str) and len(key) <= 256 and re.fullmatch(
            r"arn:(aws|aws-us-gov|aws-cn):kms:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:key/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})", key), "owned_log_key")
        require(valid_tags(log.get("tags")) and valid_tags(log.get("tags_all")), "owned_log_tags")

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
    require(api is not None or set(resources) <= {"aws_cloudwatch_log_group"}, "dependent_resources_require_api")
    if api is None:
        return
    require(all(value.get("region") == api["execution_arn"].split(":")[3] for kind, value in resources.items() if kind != "aws_cloudwatch_log_group"), "resource_region_binding")
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
            log = resources.get("aws_cloudwatch_log_group")
            require(log is not None, "stage_owned_log_required")
            arn = one_block(stage["access_log_settings"], "mandatory_access_logging").get("destination_arn")
            match = re.fullmatch(LOG_PATTERN, arn) if isinstance(arn, str) else None
            require(match is not None and match.groups()[:3] == scope and not match[4].startswith("aws/"), "access_log_scope")
            require(arn == log["arn"] and match[4] == log["name"], "stage_owned_log_binding")
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
    log = resources["aws_cloudwatch_log_group"]
    expected.update({"access_log_" + output: log[attr] for output, attr in {
        "group_name":"name", "group_arn":"arn", "retention_in_days":"retention_in_days",
        "deletion_protection_enabled":"deletion_protection_enabled", "group_class":"log_group_class", "kms_key_arn":"kms_key_id"}.items()})
    require(isinstance(outputs, dict) and set(outputs) == set(expected), "output_inventory")
    for name, value in expected.items():
        output = outputs[name]
        require(isinstance(output, dict) and all(key in output for key in ("actions", "before", "after", "after_sensitive", "after_unknown")) and output["before"] is None, "output_change_metadata:" + name)
        require(output.get("actions") == (["no-op"] if value is None else ["create"]) and output.get("after_sensitive") is False
            and not any_unknown(output.get("after_unknown", False)) and output.get("after") == value, "output_binding:" + name)
    return resources


def reviewed_log_name(name):
    return {"logging_lambda_log_group_name":"/aws/lambda/portfolio-api-handler", "logging_workload_log_group_name":"/portfolio/dev/serverless-api",
        "logging_maximum_name_length":"x"*512, "logging_supported_name_characters":"/portfolio/test/log_group-1.#"}.get(name, "/test/api-access")


def verify_log_fixture(name, log, partition, region, account):
    require(log["name"] == reviewed_log_name(name) and log["arn"] ==
        f"arn:{partition}:logs:{region}:{account}:log-group:{log['name']}", "reviewed_owned_log_identity")
    retention = {"logging_minimum_finite_retention":1, "logging_weekly_retention":7, "logging_supported_400_day_retention":400,
        "logging_supported_731_day_retention":731, "logging_maximum_supported_retention":3653}.get(name,30)
    require(log["retention_in_days"] == retention and log["deletion_protection_enabled"] is
        (name != "logging_explicit_disposable_development_override"), "reviewed_log_lifecycle")
    key = None
    if name in {"logging_existing_symmetric_key_reference", "logging_existing_multi_region_key_reference", "logging_govcloud_partition_key_syntax", "logging_china_partition_key_syntax"}:
        p, r = {"logging_govcloud_partition_key_syntax":("aws-us-gov","us-gov-west-1"),
            "logging_china_partition_key_syntax":("aws-cn","cn-north-1")}.get(name,(partition,region))
        identifier = "mrk-"+"1"*24+"0"*8 if name == "logging_existing_multi_region_key_reference" else "00000000-0000-0000-0000-111111111111"
        key = f"arn:{p}:kms:{r}:111111111111:key/{identifier}"
    require(log["kms_key_id"] == key, "reviewed_log_key")
    tags = {}
    if name == "logging_caller_owned_unicode_tags":tags = {"Project":"Root-Owned", "運用:部門":"本番 構成 +:@/=", "Environment":"test"}
    if name == "logging_maximum_tag_count_and_lengths":tags = {"K"*128:"v"*256, **{f"tag-{i:02}":"" for i in range(49)}}
    require(log["tags"] == tags, "reviewed_log_tag_inputs")


def verify_fixture(name, resources):
    """Bind actual plans independently to the reviewed synthetic native inputs."""
    api = resources["aws_apigatewayv2_api"]
    expected_name = {"minimum_api_name": "a", "maximum_api_name": "a" * 128}.get(name, "test-http-api")
    require(api["name"] == expected_name, "reviewed_api_name")
    partition, region, account = ("aws-us-gov", "us-gov-west-1", "222222222222") if name == "govcloud_reference_scope" else ("aws", "ca-central-1", "111111111111")
    function = f"arn:{partition}:lambda:{region}:{account}:function:test-api-handler"
    require(resources["aws_lambda_permission"]["function_name"] == function, "reviewed_lambda_input")
    require(one_block(resources["aws_apigatewayv2_stage"]["access_log_settings"], "mandatory_access_logging")["destination_arn"]
        == f"arn:{partition}:logs:{region}:{account}:log-group:{reviewed_log_name(name)}", "reviewed_log_input")
    verify_log_fixture(name, resources["aws_cloudwatch_log_group"], partition, region, account)
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
    return set(REJECTED_SHAPES[name])


def verify_capture(events, exit_code=0):
    require(type(exit_code) is int and exit_code == 0, "terraform_process_failure")
    expected_runs = POSITIVE_RUNS | NEGATIVE_RUNS
    terminal, plans, errors, summaries = set(), {}, set(), []
    declared = None
    files = []
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
                expected_error = "Resource postcondition failed" if (name.startswith(("actual_api_", "actual_log_", "effective_api_", "effective_stage_")) or name in {"log_stream_instead_of_group", "log_group_api_suffix", "mismatched_log_account", "mismatched_log_region", "mismatched_log_partition"}) else "Invalid value for variable"
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
                    if "aws_cloudwatch_log_group" in resources:
                        log = resources["aws_cloudwatch_log_group"]
                        expected = "arn:aws:logs:ca-central-1:111111111111:log-group:" + log["name"]
                        deliberately_bad = name in {"log_stream_instead_of_group", "log_group_api_suffix", "mismatched_log_account", "mismatched_log_region", "mismatched_log_partition", "actual_log_wrong_name", "actual_log_malformed_arn"}
                        require((log["arn"] != expected) if deliberately_bad else (log["arn"] == expected), "rejected_owned_log_identity")
                    if name.startswith("actual_api_"):
                        api = resources["aws_apigatewayv2_api"]
                        require(api["execution_arn"] != "arn:aws:execute-api:ca-central-1:111111111111:" + api["id"], "rejected_api_scope_evidence")
                    if name.startswith(("effective_api_", "effective_stage_")):
                        kind = "aws_apigatewayv2_api" if name.startswith("effective_api_") else "aws_apigatewayv2_stage"
                        require(valid_tags(resources[kind]["tags"]) and not valid_tags(resources[kind]["tags_all"]), "rejected_effective_tags_evidence")
                plans[name] = event["test_plan"]
        if kind == "test_file" and "status" in event["test_file"]:
            require(event["test_file"]["status"] == "pass", "capture_nonpassing_file")
            files.append(event.get("@testfile"))
        if kind == "test_summary":
            summaries.append(event["test_summary"])
    expected = {"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}
    require(declared is not None and len(summaries) == 1 and isinstance(summaries[0], dict)
        and all(type(summaries[0].get(key)) is int for key in ("passed", "failed", "errored", "skipped"))
        and summaries[0] == expected, "capture_summary_counts")
    require(files == [TEST_FILE], "capture_file_completeness")
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
    mutate("unrelated-log-destination", "stage_owned_log_binding", lambda r: r["aws_apigatewayv2_stage"]["access_log_settings"][0].update(destination_arn=r["aws_apigatewayv2_stage"]["access_log_settings"][0]["destination_arn"] + "-other"))
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
    additions = [
        ("lambda-application-log-destination", lambda p,r: r["aws_apigatewayv2_stage"]["access_log_settings"][0].update(destination_arn="arn:aws:logs:ca-central-1:111111111111:log-group:/aws/lambda/test-api-handler")),
        ("owned-log-wrong-account", lambda p,r: r["aws_cloudwatch_log_group"].update(arn=r["aws_cloudwatch_log_group"]["arn"].replace("111111111111","222222222222"))),
        ("owned-log-retention-weakened", lambda p,r: (r["aws_cloudwatch_log_group"].update(retention_in_days=1), p["output_changes"]["access_log_retention_in_days"].update(after=1))),
        ("owned-log-retention-missing", lambda p,r: r["aws_cloudwatch_log_group"].pop("retention_in_days")),
        ("owned-log-protection-disabled", lambda p,r: (r["aws_cloudwatch_log_group"].update(deletion_protection_enabled=False), p["output_changes"]["access_log_deletion_protection_enabled"].update(after=False))),
        ("owned-log-skip-destroy", lambda p,r: r["aws_cloudwatch_log_group"].update(skip_destroy=True)),
        ("owned-log-class", lambda p,r: r["aws_cloudwatch_log_group"].update(log_group_class="INFREQUENT_ACCESS")),
        ("owned-log-unexpected-key", lambda p,r: r["aws_cloudwatch_log_group"].update(kms_key_id="arn:aws:kms:ca-central-1:111111111111:key/00000000-0000-0000-0000-111111111111")),
    ]
    for identifier, transform in additions:
        changed = copy.deepcopy(plan)
        resources = {r["type"]: r["change"]["after"] for r in changed["resource_changes"]}
        transform(changed, resources)
        results.append(expect_rejection(lambda: verify_fixture("default_http_api_configuration", verify_plan(changed)), identifier))
    for identifier, transform in [
        ("missing-owned-log", lambda changes: changes.remove(next(r for r in changes if r["type"] == "aws_cloudwatch_log_group"))),
        ("duplicate-owned-log", lambda changes: changes.append(copy.deepcopy(next(r for r in changes if r["type"] == "aws_cloudwatch_log_group")))),
        ("unexpected-iam-resource", lambda changes: changes.append({"type":"aws_iam_policy", "name":"unreviewed"})),
    ]:
        changed = copy.deepcopy(plan)
        transform(changed["resource_changes"])
        results.append(expect_rejection(lambda: verify_plan(changed), identifier))
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
    inject("missing-file-terminal", lambda e: e.pop(next(i for i,v in enumerate(e) if v["type"] == "test_file" and "status" in v["test_file"])))
    inject("duplicate-file-terminal", lambda e: e.insert(first(e,"test_summary"), copy.deepcopy(next(v for v in e if v["type"] == "test_file" and "status" in v["test_file"]))))
    inject("unknown-owned-log-arn", lambda e: next(r for r in e[first(e,"test_plan")]["test_plan"]["resource_changes"] if r["type"] == "aws_cloudwatch_log_group")["change"]["after_unknown"].update(arn=True))
    inject("missing-known-null-log-key", lambda e: next(r for r in e[first(e,"test_plan")]["test_plan"]["resource_changes"] if r["type"] == "aws_cloudwatch_log_group")["change"]["after"].pop("kms_key_id"))
    inject("missing-known-null-output", lambda e: e[first(e,"test_plan")]["test_plan"]["output_changes"]["access_log_kms_key_arn"].pop("after"))
    inject("wrong-log-output", lambda e: e[first(e,"test_plan")]["test_plan"]["output_changes"]["access_log_group_name"].update(after="/unrelated"))
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
        structure = verify_structure()
        source_faults = source_mutations() if args.self_test else 0
        shapes = Counter("empty" if not plan.get("resource_changes") else "+".join(sorted(r["type"] for r in plan["resource_changes"]))
            for name, plan in plans.items() if name in NEGATIVE_RUNS)
        print(json.dumps({
            "status": "passed", "evidence_type": "static_actual_plan_verification", "aws_api_calls": 0,
            "native_tests": len(POSITIVE_RUNS | NEGATIVE_RUNS), "positive_plans": len(POSITIVE_RUNS), "negative_plans": len(NEGATIVE_RUNS),
            "negative_plan_shapes": dict(shapes), "source_contract": structure, "source_dependency_mutations": source_faults, "resource_inventory": {kind: 1 for kind in sorted(TYPES)},
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
