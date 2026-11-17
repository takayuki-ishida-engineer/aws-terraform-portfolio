#!/usr/bin/env python3
"""Verify the tfstate_bucket native test events against the actual mock plans.

Reads `terraform test -json -verbose` events (optionally compacted by the EKS
checker's --compact filter) and independently checks every positive plan's
resource set and security-relevant values, and every negative run's variable
diagnostic. --self-test applies semantic mutations and capture failures to the
captured events and requires each to be rejected. Offline; no AWS API is called.
"""
import argparse
import copy
import json
import sys

BUCKET = "test-dev-s3-tfstate"
ARN = "arn:aws:s3:::" + BUCKET
RESOURCES = {
    "aws_s3_bucket.this", "aws_s3_bucket_versioning.this", "aws_s3_bucket_public_access_block.this",
    "aws_s3_bucket_ownership_controls.this", "aws_s3_bucket_server_side_encryption_configuration.this",
    "aws_s3_bucket_lifecycle_configuration.this", "aws_s3_bucket_policy.this",
}
POSITIVE = {
    "default_state_bucket": {"retention": 90, "tags": {"Name": BUCKET, "service": "s3"}},
    "custom_retention_and_tags": {"retention": 30, "tags": {"owner": "platform", "Name": BUCKET, "service": "s3"}},
    "maximum_retention": {"retention": 365, "tags": {"Name": BUCKET, "service": "s3"}},
}
NEGATIVE = {
    "rejects_bucket_without_tfstate_suffix": ("bucket_name", "end in -s3-tfstate"),
    "rejects_uppercase_bucket": ("bucket_name", "end in -s3-tfstate"),
    "rejects_reserved_prefix": ("bucket_name", "end in -s3-tfstate"),
    "rejects_period_in_bucket": ("bucket_name", "end in -s3-tfstate"),
    "rejects_short_retention": ("noncurrent_version_retention_days", "from 30 through 365"),
    "rejects_long_retention": ("noncurrent_version_retention_days", "from 30 through 365"),
    "rejects_fractional_retention": ("noncurrent_version_retention_days", "from 30 through 365"),
    "rejects_name_tag": ("tags", "must not set Name, service"),
    "rejects_service_tag": ("tags", "must not set Name, service"),
    "rejects_aws_prefixed_tag": ("tags", "must not set Name, service"),
    "rejects_long_tag_value": ("tags", "must not set Name, service"),
}
POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
         "Resource": [ARN, ARN + "/*"], "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
        {"Sid": "DenyOutdatedTls", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
         "Resource": [ARN, ARN + "/*"], "Condition": {"NumericLessThan": {"s3:TlsVersion": "1.2"}}},
    ],
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def only(items, code):
    require(isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict), code)
    return items[0]


def check_plan(run, plan, expected):
    changes = plan.get("resource_changes") or []
    require({c.get("address") for c in changes} == RESOURCES and len(changes) == len(RESOURCES), "resource_set:" + run)
    after = {}
    for change in changes:
        require(change.get("mode") == "managed" and change["change"].get("actions") == ["create"], "create_only:" + run)
        after[change["address"]] = change["change"].get("after") or {}
    bucket = after["aws_s3_bucket.this"]
    require(bucket.get("bucket") == BUCKET and bucket.get("bucket_namespace") == "global" and bucket.get("force_destroy") is False
            and bucket.get("object_lock_enabled") is False and bucket.get("tags") == expected["tags"], "bucket:" + run)
    for address in RESOURCES - {"aws_s3_bucket.this"}:
        require(after[address].get("bucket") == BUCKET, "binding:" + address + ":" + run)
    require(only(after["aws_s3_bucket_versioning.this"].get("versioning_configuration"), "versioning_shape").get("status") == "Enabled",
            "versioning:" + run)
    block = after["aws_s3_bucket_public_access_block.this"]
    require(all(block.get(key) is True for key in ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")),
            "public_access_block:" + run)
    require(only(after["aws_s3_bucket_ownership_controls.this"].get("rule"), "ownership_shape").get("object_ownership") == "BucketOwnerEnforced",
            "ownership:" + run)
    default = only(only(after["aws_s3_bucket_server_side_encryption_configuration.this"].get("rule"), "sse_shape")
                   .get("apply_server_side_encryption_by_default"), "sse_default_shape")
    require(default.get("sse_algorithm") == "AES256" and default.get("kms_master_key_id") in (None, ""), "encryption:" + run)
    rule = only(after["aws_s3_bucket_lifecycle_configuration.this"].get("rule"), "lifecycle_shape:" + run)
    require(rule.get("id") == "state-history" and rule.get("status") == "Enabled"
            and only(rule.get("noncurrent_version_expiration"), "noncurrent_shape").get("noncurrent_days") == expected["retention"]
            and only(rule.get("abort_incomplete_multipart_upload"), "abort_shape").get("days_after_initiation") == 7
            and rule.get("expiration") == [] and rule.get("transition") == [] and rule.get("noncurrent_version_transition") == [],
            "lifecycle:" + run)
    filters = only(rule.get("filter"), "filter_shape:" + run)
    require(not filters.get("prefix") and filters.get("and") == [] and filters.get("tag") == [], "lifecycle_filter:" + run)
    require(json.loads(after["aws_s3_bucket_policy.this"].get("policy", "{}")) == POLICY, "policy:" + run)


def verify(events, exit_code):
    require(exit_code == 0, "terraform_exit")
    require([e.get("terraform") for e in events if e.get("type") == "version"] == ["1.17.0"], "version")
    abstracts = [e.get("test_abstract") for e in events if e.get("type") == "test_abstract"]
    expected_runs = set(POSITIVE) | set(NEGATIVE)
    require(len(abstracts) == 1 and len(abstracts[0]) == 1 and set(next(iter(abstracts[0].values()))) == expected_runs, "manifest")
    terminals = {}
    for event in events:
        if event.get("type") == "test_run" and "status" in event.get("test_run", {}):
            run = event["test_run"]
            require(run.get("run") not in terminals, "duplicate_terminal")
            terminals[run.get("run")] = run.get("status")
    require(terminals == {run: "pass" for run in expected_runs}, "run_terminals")
    summaries = [e.get("test_summary") for e in events if e.get("type") == "test_summary"]
    require(summaries == [{"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}], "summary")
    plans = {}
    for event in events:
        if event.get("type") == "test_plan":
            require(event.get("@testrun") not in plans, "duplicate_plan")
            plans[event.get("@testrun")] = event.get("test_plan") or {}
    for run, expected in POSITIVE.items():
        require(run in plans, "missing_plan:" + run)
        check_plan(run, plans[run], expected)
    for run, (variable, fragment) in NEGATIVE.items():
        errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("@testrun") == run
                  and e.get("diagnostic", {}).get("severity") == "error"]
        require(errors and all(d.get("summary") == "Invalid value for variable" for d in errors)
                and any(fragment in d.get("detail", "") and "variables.tf" in d.get("detail", "") for d in errors), "negative:" + run)
        require(not any("aws_s3_bucket_lifecycle_configuration.this" == c.get("address") for c in plans.get(run, {}).get("resource_changes") or [])
                or variable != "noncurrent_version_retention_days", "negative_planned_lifecycle:" + run)
    errors = [e for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"
              and e.get("@testrun") not in NEGATIVE]
    require(not errors, "unexpected_error_diagnostic")
    return {"status": "passed", "evidence_type": "actual_mock_plan_verification", "aws_api_calls": 0,
            "native_tests": len(expected_runs), "positive_plans": len(POSITIVE), "negative_cases": len(NEGATIVE)}


def change(events, run, address):
    for event in events:
        if event.get("type") == "test_plan" and event.get("@testrun") == run:
            for item in event["test_plan"]["resource_changes"]:
                if item["address"] == address:
                    return item["change"]["after"]
    raise KeyError(address)


def set_policy(events, edit):
    after = change(events, "default_state_bucket", "aws_s3_bucket_policy.this")
    policy = json.loads(after["policy"])
    edit(policy)
    after["policy"] = json.dumps(policy)


def semantic_mutations():
    run = "default_state_bucket"
    yield "force_destroy", lambda e: change(e, run, "aws_s3_bucket.this").update(force_destroy=True)
    yield "object_lock", lambda e: change(e, run, "aws_s3_bucket.this").update(object_lock_enabled=True)
    yield "bucket_name", lambda e: change(e, run, "aws_s3_bucket.this").update(bucket="other-dev-s3-tfstate")
    yield "tags", lambda e: change(e, run, "aws_s3_bucket.this")["tags"].update(service="other")
    yield "versioning_suspended", lambda e: change(e, run, "aws_s3_bucket_versioning.this")["versioning_configuration"][0].update(status="Suspended")
    for key in ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets"):
        yield "public_access_" + key, lambda e, key=key: change(e, run, "aws_s3_bucket_public_access_block.this").update({key: False})
    yield "ownership", lambda e: change(e, run, "aws_s3_bucket_ownership_controls.this")["rule"][0].update(object_ownership="ObjectWriter")
    yield "kms_algorithm", lambda e: change(e, run, "aws_s3_bucket_server_side_encryption_configuration.this")["rule"][0][
        "apply_server_side_encryption_by_default"][0].update(sse_algorithm="aws:kms")
    yield "kms_key", lambda e: change(e, run, "aws_s3_bucket_server_side_encryption_configuration.this")["rule"][0][
        "apply_server_side_encryption_by_default"][0].update(kms_master_key_id="arn:aws:kms:ca-central-1:000000000000:key/x")
    yield "lifecycle_days", lambda e: change(e, run, "aws_s3_bucket_lifecycle_configuration.this")["rule"][0][
        "noncurrent_version_expiration"][0].update(noncurrent_days=1)
    yield "lifecycle_current_expiry", lambda e: change(e, run, "aws_s3_bucket_lifecycle_configuration.this")["rule"][0].update(
        expiration=[{"days": 30, "date": None, "expired_object_delete_marker": None}])
    yield "lifecycle_disabled", lambda e: change(e, run, "aws_s3_bucket_lifecycle_configuration.this")["rule"][0].update(status="Disabled")
    yield "lifecycle_prefix_filter", lambda e: change(e, run, "aws_s3_bucket_lifecycle_configuration.this")["rule"][0]["filter"][0].update(prefix="x/")
    yield "binding", lambda e: change(e, run, "aws_s3_bucket_policy.this").update(bucket="other")
    yield "policy_drop_tls", lambda e: set_policy(e, lambda p: p["Statement"].pop(0))
    yield "policy_drop_tls_version", lambda e: set_policy(e, lambda p: p["Statement"].pop(1))
    yield "policy_objects_only", lambda e: set_policy(e, lambda p: p["Statement"][0].update(Resource=[ARN + "/*"]))
    yield "policy_allow", lambda e: set_policy(e, lambda p: p["Statement"][0].update(Effect="Allow"))
    yield "policy_service_exception", lambda e: set_policy(e, lambda p: p["Statement"][0]["Condition"]["Bool"].update({"aws:PrincipalIsAWSService": "false"}))
    yield "policy_tls_1_0", lambda e: set_policy(e, lambda p: p["Statement"][1]["Condition"]["NumericLessThan"].update({"s3:TlsVersion": "1.0"}))


def capture_failures():
    def drop_type(kind):
        return lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != kind])

    def drop_resource(e):
        for x in e:
            if x.get("type") == "test_plan" and x.get("@testrun") == "custom_retention_and_tags":
                x["test_plan"]["resource_changes"] = x["test_plan"]["resource_changes"][1:]

    def extra_resource(e):
        for x in e:
            if x.get("type") == "test_plan" and x.get("@testrun") == "maximum_retention":
                extra = copy.deepcopy(x["test_plan"]["resource_changes"][0])
                extra["address"] = "aws_s3_bucket.extra"
                x["test_plan"]["resource_changes"].append(extra)

    def fail_run(e):
        for x in e:
            if x.get("type") == "test_run" and x.get("test_run", {}).get("run") == "rejects_name_tag" and "status" in x["test_run"]:
                x["test_run"]["status"] = "fail"

    def strip_negative(e):
        e[:] = [x for x in e if not (x.get("type") == "diagnostic" and x.get("@testrun") == "rejects_short_retention")]

    def foreign_error(e):
        e.append({"type": "diagnostic", "@testrun": "default_state_bucket", "diagnostic": {"severity": "error", "summary": "x", "detail": ""}})

    def summary_count(e):
        for x in e:
            if x.get("type") == "test_summary":
                x["test_summary"]["passed"] -= 1

    def duplicate_plan(e):
        e.append(copy.deepcopy(next(x for x in e if x.get("type") == "test_plan")))

    yield "no_version", drop_type("version")
    yield "no_manifest", drop_type("test_abstract")
    yield "no_summary", drop_type("test_summary")
    yield "no_plans", drop_type("test_plan")
    yield "missing_resource", drop_resource
    yield "extra_resource", extra_resource
    yield "failed_run", fail_run
    yield "missing_negative_diagnostic", strip_negative
    yield "foreign_error", foreign_error
    yield "summary_count", summary_count
    yield "duplicate_plan", duplicate_plan


def self_test(events):
    counts = {}
    for label, mutations in (("semantic_mutations", semantic_mutations()), ("capture_failure_injections", capture_failures())):
        count = 0
        for name, mutate in mutations:
            mutated = copy.deepcopy(events)
            mutate(mutated)
            try:
                verify(mutated, 0)
            except (ValueError, KeyError, TypeError, StopIteration):
                count += 1
                continue
            raise ValueError("mutation_not_detected:" + name)
        counts[label] = count
    try:
        verify(events, 1)
    except ValueError:
        counts["capture_failure_injections"] += 1
    else:
        raise ValueError("mutation_not_detected:exit_code")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-events", required=True)
    parser.add_argument("--terraform-exit-code", type=int, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        with open(args.test_events, encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        report = verify(events, args.terraform_exit_code)
        if args.self_test:
            report.update(self_test(events))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print("tfstate_bucket verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
