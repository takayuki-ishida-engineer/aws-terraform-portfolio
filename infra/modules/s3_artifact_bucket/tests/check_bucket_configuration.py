#!/usr/bin/env python3
"""Fail-closed checks of actual credential-free Terraform mock-plan captures.

This verifies one reviewed S3 configuration contract, not live AWS authorization,
bucket ownership, propagation, or uploaded artifacts. Only the Python standard
library is used; no Terraform subprocess, credentials, SDK or network is accessed.
"""

import argparse
import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path


TEST_FILE = "tests/s3_artifact_bucket.tftest.hcl"
POSITIVE_RUNS = {
    "default_private_bucket", "resource_attribute_outputs", "minimum_name_length",
    "maximum_name_length", "caller_owned_tags", "maximum_tag_limits",
    "effective_provider_default_tags",
}
# Updated from the reviewed native suite, not from a capture's reported count.
NEGATIVE_RUNS = {
    "empty_bucket_name", "too_short_bucket_name", "too_long_bucket_name", "uppercase_bucket_name",
    "bucket_name_with_period", "unsupported_bucket_character", "leading_hyphen_bucket_name",
    "trailing_hyphen_bucket_name", "wildcard_bucket_name", "bucket_arn_instead_of_name", "null_bucket_name",
    "xn_reserved_prefix", "sthree_reserved_prefix", "amzn_s3_demo_reserved_prefix", "s3alias_reserved_suffix",
    "object_lambda_reserved_suffix", "mrap_reserved_suffix", "directory_bucket_reserved_suffix",
    "table_bucket_reserved_suffix", "account_regional_reserved_suffix", "empty_tag_key", "reserved_tag_prefix",
    "case_variant_reserved_tag_prefix", "null_tag_value", "overlong_tag_key", "overlong_tag_value",
    "too_many_tags", "effective_provider_tags_exceed_limit", "effective_provider_reserved_tag_prefix",
    "effective_provider_overlong_tag_value",
}
RESOURCE_TYPES = {
    "aws_s3_bucket", "aws_s3_bucket_versioning", "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_ownership_controls",
    "aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_policy",
}
PAB_FLAGS = {"block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets"}


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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def any_unknown(value):
    if isinstance(value, dict):
        return any(any_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(any_unknown(item) for item in value)
    require(type(value) is bool, "unknown_metadata_shape")
    return value


def unknown_at(metadata, path):
    for key in path:
        if type(metadata) is bool:
            return metadata
        require(isinstance(metadata, (dict, list)), "unknown_metadata_shape")
        if isinstance(metadata, dict):
            metadata = metadata.get(key, False)
        else:
            require(isinstance(key, int) and key < len(metadata), "unknown_metadata_shape")
            metadata = metadata[key]
    return any_unknown(metadata)


def one_block(value, code):
    require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict), code)
    return value[0]


def valid_name(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", value) and not (
        value.startswith(("xn--", "sthree-", "amzn-s3-demo-")) or
        value.endswith(("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3", "-an"))
    )


def valid_tags(tags):
    return isinstance(tags, dict) and len(tags) <= 50 and all(
        isinstance(key, str) and 1 <= len(key) <= 128 and not key.lower().startswith("aws:")
        and isinstance(value, str) and len(value) <= 256 for key, value in tags.items()
    )


def verify_policy(encoded, bucket_arn):
    require(isinstance(encoded, str), "policy_json_type")
    policy = parse_json(encoded)
    require(isinstance(policy, dict) and set(policy) == {"Version", "Statement"}
        and policy["Version"] == "2012-10-17", "policy_document")
    statement = one_block(policy["Statement"], "policy_single_statement")
    require(set(statement) == {"Sid", "Effect", "Principal", "Action", "Resource", "Condition"}
        and statement["Sid"] == "DenyInsecureTransport", "policy_statement_elements")
    require(statement["Effect"] == "Deny", "policy_deny_only")
    require(statement["Principal"] == "*", "policy_principal")
    require(statement["Action"] == "s3:*", "policy_action")
    require(isinstance(statement["Resource"], list) and len(statement["Resource"]) == 2
        and set(statement["Resource"]) == {bucket_arn, bucket_arn + "/*"}, "policy_resource_scope")
    require(statement["Condition"] == {"Bool": {
        "aws:SecureTransport": "false", "aws:PrincipalIsAWSService": "false",
    }}, "policy_transport_conditions")
    return policy


def resources_of(plan, complete):
    require(isinstance(plan, dict), "plan_shape")
    changes = plan.get("resource_changes")
    if not complete and changes is None:
        changes = []
    require(isinstance(changes, list), "plan_resource_changes")
    resources = {}
    for resource in changes:
        require(isinstance(resource, dict), "resource_shape")
        kind = resource.get("type")
        require(kind in RESOURCE_TYPES and kind not in resources, "resource_inventory")
        change = resource.get("change")
        require(isinstance(change, dict) and "before" in change and change["before"] is None
            and "after_unknown" in change, "resource_change_metadata")
        any_unknown(change["after_unknown"])
        require(resource.get("mode") == "managed" and resource.get("name") == "this"
            and resource.get("address") == kind + ".this" and "index" not in resource
            and resource.get("provider_name") == "registry.terraform.io/hashicorp/aws"
            and resource.get("change", {}).get("actions") == ["create"], "resource_create_identity")
        after = resource["change"].get("after")
        require(isinstance(after, dict), "resource_after")
        paths = [("bucket",)]
        paths += {
            "aws_s3_bucket": [(key,) for key in ("id", "arn", "bucket_namespace", "force_destroy", "tags", "tags_all")],
            "aws_s3_bucket_versioning": [("versioning_configuration", 0, "status")],
            "aws_s3_bucket_public_access_block": [(key,) for key in PAB_FLAGS],
            "aws_s3_bucket_ownership_controls": [("rule", 0, "object_ownership")],
            "aws_s3_bucket_server_side_encryption_configuration": [("rule", 0, "apply_server_side_encryption_by_default", 0, "sse_algorithm")],
            "aws_s3_bucket_policy": [("policy",)],
        }[kind]
        require(not any(unknown_at(resource["change"].get("after_unknown", {}), path) for path in paths), "required_configuration_unknown")
        resources[kind] = after
    if complete:
        require(set(resources) == RESOURCE_TYPES, "complete_resource_inventory")
    return resources


def verify_fixed(resources):
    """Check every emitted configuration, including rejected partial plans."""
    bucket = resources.get("aws_s3_bucket")
    if bucket is not None:
        require(bucket.get("force_destroy") is False, "bucket_force_destroy")
        require(bucket.get("bucket_namespace") == "global", "bucket_shared_namespace")
        # These deprecated embedded interfaces must not bypass the six-resource contract.
        require(all(not bucket.get(key) for key in (
            "acl", "grant", "cors_rule", "lifecycle_rule", "logging", "policy", "replication_configuration",
            "server_side_encryption_configuration", "versioning", "website", "object_lock_configuration",
        )) and bucket.get("object_lock_enabled") in (None, False), "bucket_embedded_configuration")
    if "aws_s3_bucket_versioning" in resources:
        block = one_block(resources["aws_s3_bucket_versioning"].get("versioning_configuration"), "versioning_block")
        require(block.get("status") == "Enabled" and block.get("mfa_delete") in (None, "Disabled"), "versioning_enabled")
        require(not resources["aws_s3_bucket_versioning"].get("mfa"), "versioning_mfa_delete")
    if "aws_s3_bucket_public_access_block" in resources:
        require(all(resources["aws_s3_bucket_public_access_block"].get(key) is True for key in PAB_FLAGS), "public_access_block")
    if "aws_s3_bucket_ownership_controls" in resources:
        block = one_block(resources["aws_s3_bucket_ownership_controls"].get("rule"), "ownership_rule")
        require(block == {"object_ownership": "BucketOwnerEnforced"}, "ownership_enforced")
    if "aws_s3_bucket_server_side_encryption_configuration" in resources:
        block = one_block(resources["aws_s3_bucket_server_side_encryption_configuration"].get("rule"), "encryption_rule")
        default = one_block(block.get("apply_server_side_encryption_by_default"), "encryption_default")
        require(default.get("sse_algorithm") == "AES256" and not default.get("kms_master_key_id")
            and block.get("bucket_key_enabled") in (None, False), "encryption_sse_s3")
    if "aws_s3_bucket_policy" in resources:
        require(bucket is not None and isinstance(bucket.get("arn"), str), "policy_bucket_reference")
        verify_policy(resources["aws_s3_bucket_policy"].get("policy"), bucket["arn"])


def verify_plan(plan, complete=True):
    resources = resources_of(plan, complete)
    verify_fixed(resources)
    if not complete:
        return resources
    bucket = resources["aws_s3_bucket"]
    require(valid_name(bucket.get("bucket")), "bucket_name")
    require(isinstance(bucket.get("arn"), str) and re.fullmatch(
        r"arn:aws(?:-[a-z0-9]+)*:s3:::" + re.escape(bucket["bucket"]), bucket["arn"]
    ), "bucket_arn_scope")
    require(bucket.get("id") == bucket["bucket"] and not bucket.get("bucket_prefix"), "bucket_identity")
    require(valid_tags(bucket.get("tags")) and valid_tags(bucket.get("tags_all")), "effective_tags")
    require(all(bucket["tags_all"].get(key) == value for key, value in bucket["tags"].items()), "caller_tag_precedence")
    for kind, value in resources.items():
        if kind != "aws_s3_bucket":
            require(value.get("bucket") == bucket["id"], "configuration_bucket_binding")
    outputs = plan.get("output_changes")
    require(isinstance(outputs, dict) and set(outputs) == {"bucket_name", "bucket_arn", "versioning_status"}, "output_inventory")
    for name, expected in {"bucket_name": bucket["bucket"], "bucket_arn": bucket["arn"], "versioning_status": "Enabled"}.items():
        output = outputs[name]
        require(output.get("actions") == ["create"] and output.get("after_sensitive") is False
            and not any_unknown(output.get("after_unknown", False)) and output.get("after") == expected, "output_binding:" + name)
    return resources


def verify_fixture(name, resources):
    """Reviewed native inputs independently bind planned bucket name and tags."""
    expected_name = {"minimum_name_length": "0a0", "maximum_name_length": "a" * 63}.get(name, "test-lambda-artifacts")
    expected_tags = {}
    if name == "caller_owned_tags":
        expected_tags = {"Owner": "Root-Owned", "Purpose": "artifact storage", "Empty": ""}
    if name == "maximum_tag_limits":
        expected_tags = {"K" * 128: "v" * 256, **{f"tag-{i:02}": "" for i in range(47)}}
    if name == "effective_provider_default_tags":
        expected_tags = {"Owner": "Root-Owned"}
    # Module-owned Name and service win over caller tags (docs/deployment-configuration.md section 5).
    expected_tags = {**expected_tags, "Name": expected_name, "service": "s3"}
    expected_all = {**expected_tags, **({"CostCentre": "test-default"} if name == "effective_provider_default_tags" else {})}
    bucket = resources["aws_s3_bucket"]
    require(bucket["bucket"] == expected_name and bucket["tags"] == expected_tags
        and bucket["tags_all"] == expected_all, "reviewed_input_binding")
    if name == "resource_attribute_outputs":
        require(bucket["arn"] == "arn:aws-us-gov:s3:::" + expected_name, "resource_derived_arn_fixture")


def read_events(path):
    for line in Path(path).open(encoding="utf-8"):
        event = parse_json(line)
        require(isinstance(event, dict), "capture_event_shape")
        # Discard bulky provider schemas; all planned changes and output values remain actual.
        if event.get("type") == "test_plan":
            plan = event["test_plan"]
            require(isinstance(plan, dict), "plan_shape")
            event["test_plan"] = {key: plan[key] for key in ("resource_changes", "output_changes") if key in plan}
        yield event


def verify_capture(events, terraform_exit_code=0):
    require(type(terraform_exit_code) is int and terraform_exit_code == 0, "terraform_process_failure")
    expected_runs = POSITIVE_RUNS | NEGATIVE_RUNS
    terminal, plans, errors, summaries = set(), {}, set(), []
    declared = None
    for event in events:
        require(isinstance(event, dict) and isinstance(event.get("type"), str), "capture_event_shape")
        require(not summaries, "capture_after_summary")
        kind = event["type"]
        require(kind in {"version", "test_abstract", "test_run", "test_plan", "test_file", "diagnostic", "test_summary", "log"}, "capture_event_type")
        if kind == "diagnostic":
            require(isinstance(event.get("diagnostic"), dict), "capture_diagnostic_shape")
            require((event["diagnostic"].get("severity") == "error") == (event.get("@level") == "error"), "capture_diagnostic_level")
        if kind == "test_abstract":
            abstract = event["test_abstract"]
            require(declared is None and isinstance(abstract, dict) and set(abstract) == {TEST_FILE}
                and isinstance(abstract[TEST_FILE], list), "capture_test_files")
            declared = abstract[TEST_FILE]
            require(len(declared) == len(expected_runs) and set(declared) == expected_runs, "capture_declared_coverage")
        if kind in {"test_run", "test_plan"} or event.get("@level") == "error":
            name = event.get("@testrun")
            require(event.get("@testfile") == TEST_FILE and name in expected_runs, "capture_unexpected_run")
            if event.get("@level") == "error":
                require(name in NEGATIVE_RUNS and kind == "diagnostic", "capture_unexpected_error")
                diagnostic = event.get("diagnostic", {})
                expected_summary = "Resource postcondition failed" if name.startswith("effective_provider_") else "Invalid value for variable"
                require(diagnostic.get("severity") == "error" and diagnostic.get("summary") == expected_summary, "capture_unexpected_validation_error")
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
                    effective_tags_rejection = name.startswith("effective_provider_")
                    expected_types = {"aws_s3_bucket"} if effective_tags_rejection else set()
                    require(set(resources) == expected_types, "rejected_plan_shape")
                    if effective_tags_rejection:
                        bucket = resources["aws_s3_bucket"]
                        require(bucket.get("bucket") == "test-lambda-artifacts" and valid_tags(bucket.get("tags"))
                            and not valid_tags(bucket.get("tags_all")), "rejected_effective_tags_evidence")
                plans[name] = event["test_plan"]
        if kind == "test_file" and event["test_file"].get("status"):
            require(event["test_file"]["status"] == "pass", "capture_nonpassing_file")
        if kind == "test_summary":
            summaries.append(event["test_summary"])
    require(declared is not None and len(summaries) == 1, "capture_unique_summary")
    expected = {"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}
    require(canonical(summaries[0]) == canonical(expected), "capture_summary_counts")
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

    def mutate(identifier, code, change):
        changed = copy.deepcopy(plan)
        resources = {r["type"]: r["change"]["after"] for r in changed["resource_changes"]}
        change(resources)
        results.append(expect_rejection(lambda: verify_plan(changed), identifier, code))

    for flag in sorted(PAB_FLAGS):
        mutate("disable-" + flag, "public_access_block", lambda r, key=flag: r["aws_s3_bucket_public_access_block"].update({key: False}))
    mutate("suspend-versioning", "versioning_enabled", lambda r: r["aws_s3_bucket_versioning"]["versioning_configuration"][0].update(status="Suspended"))
    mutate("force-destroy", "bucket_force_destroy", lambda r: r["aws_s3_bucket"].update(force_destroy=True))
    mutate("account-regional-namespace", "bucket_shared_namespace", lambda r: r["aws_s3_bucket"].update(bucket_namespace="account-regional"))
    mutate("enable-acls", "ownership_enforced", lambda r: r["aws_s3_bucket_ownership_controls"]["rule"][0].update(object_ownership="BucketOwnerPreferred"))
    mutate("change-encryption", "encryption_sse_s3", lambda r: r["aws_s3_bucket_server_side_encryption_configuration"]["rule"][0]["apply_server_side_encryption_by_default"][0].update(sse_algorithm="aws:kms"))
    mutate("remove-encryption", "encryption_rule", lambda r: r["aws_s3_bucket_server_side_encryption_configuration"].update(rule=[]))

    def policy_mutation(identifier, code, change):
        def transform(resources):
            policy = parse_json(resources["aws_s3_bucket_policy"]["policy"])
            change(policy)
            resources["aws_s3_bucket_policy"]["policy"] = canonical(policy)
        mutate(identifier, code, transform)

    policy_mutation("remove-https-deny", "policy_single_statement", lambda p: p.update(Statement=[]))
    policy_mutation("allow-instead-of-deny", "policy_deny_only", lambda p: p["Statement"][0].update(Effect="Allow"))
    policy_mutation("extra-allow", "policy_single_statement", lambda p: p["Statement"].append({"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "*"}))
    policy_mutation("weaken-transport-condition", "policy_transport_conditions", lambda p: p["Statement"][0]["Condition"]["Bool"].update({"aws:SecureTransport": "true"}))
    policy_mutation("remove-service-exception", "policy_transport_conditions", lambda p: p["Statement"][0]["Condition"]["Bool"].pop("aws:PrincipalIsAWSService"))
    policy_mutation("unexpected-access-exception", "policy_transport_conditions", lambda p: p["Statement"][0]["Condition"].update(StringNotEquals={"aws:PrincipalAccount": "000000000000"}))
    policy_mutation("wrong-resource-scope", "policy_resource_scope", lambda p: p["Statement"][0].update(Resource=["*"]))
    return results


def capture_faults(events):
    results = []

    def inject(identifier, change):
        changed = copy.deepcopy(events)
        change(changed)
        results.append(expect_rejection(lambda: verify_capture(changed), identifier))

    def first(items, kind):
        return next(i for i, event in enumerate(items) if event["type"] == kind)

    results.append(expect_rejection(lambda: verify_capture(events, 1), "nonzero-process-status", "terraform_process_failure"))
    inject("missing-plan", lambda e: e.pop(first(e, "test_plan")))
    inject("duplicate-plan", lambda e: e.insert(first(e, "test_plan"), copy.deepcopy(e[first(e, "test_plan")])))
    inject("missing-summary", lambda e: e.pop(first(e, "test_summary")))
    inject("duplicate-summary", lambda e: e.append(copy.deepcopy(e[first(e, "test_summary")])) )
    inject("skipped-summary", lambda e: e[first(e, "test_summary")]["test_summary"].update(skipped=1))
    inject("failed-run", lambda e: next(v["test_run"] for v in e if v["type"] == "test_run" and v["test_run"].get("status")).update(status="fail"))
    inject("missing-run", lambda e: e.pop(next(i for i, v in enumerate(e) if v["type"] == "test_run" and v["test_run"].get("status"))))
    inject("unexpected-run", lambda e: e[first(e, "test_plan")].update({"@testrun": "unreviewed-run"}))
    inject("missing-resource", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"].pop())
    inject("extra-resource", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"].append(copy.deepcopy(e[first(e, "test_plan")]["test_plan"]["resource_changes"][0])))
    inject("non-create-action", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].update(actions=["delete", "create"]))
    inject("unknown-output", lambda e: e[first(e, "test_plan")]["test_plan"]["output_changes"]["bucket_arn"].update(after_unknown=True))
    inject("unknown-security-value", lambda e: e[first(e, "test_plan")]["test_plan"]["resource_changes"][0]["change"].update(after_unknown=True))
    inject("disguised-error-diagnostic", lambda e: e.insert(first(e, "test_plan"), {
        "type": "diagnostic", "@level": "info", "@testfile": TEST_FILE,
        "@testrun": "default_private_bucket", "diagnostic": {"severity": "error", "summary": "Test assertion failed"},
    }))
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
        mutations = semantic_mutations(plans["default_private_bucket"]) if args.self_test else []
        faults = capture_faults(events) if args.self_test else []
        print(json.dumps({
            "status": "passed", "evidence_type": "static_actual_plan_verification", "aws_api_calls": 0,
            "native_tests": len(POSITIVE_RUNS | NEGATIVE_RUNS), "positive_plans": len(POSITIVE_RUNS),
            "negative_plans": len(NEGATIVE_RUNS), "resource_inventory": {kind: 1 for kind in sorted(RESOURCE_TYPES)},
            "negative_plan_shapes": {"empty": 27, "bucket_only": 3},
            "semantic_mutations": mutations, "semantic_mutation_count": len(mutations),
            "capture_faults": faults, "capture_failure_injections": len(faults),
            "limitations": ["Static mock evidence only; no AWS deployment, authorization, ownership, uniqueness or propagation was tested."],
        }, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("S3 actual-plan verification failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
