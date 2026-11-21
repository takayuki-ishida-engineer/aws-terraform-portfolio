#!/usr/bin/env python3
"""Verify the ecr_repository native test events against the actual mock plans.

Reads `terraform test -json -verbose` events (optionally compacted by the EKS
checker's --compact filter) and independently checks every positive plan's
resource set and security-relevant values, every negative run's diagnostic and
the account and Region postconditions. --self-test applies semantic mutations and
capture failures to the captured events and requires each to be rejected.
Offline; no AWS API is called.
"""
import argparse
import copy
import json
import sys

PURPOSES = ("istio-pilot", "istio-proxy", "lbc")
ACCOUNT = "000000000000"
REGION = "ca-central-1"
RESOURCES = {f'aws_ecr_repository.this["{p}"]' for p in PURPOSES}
POSITIVE = {
    "locked_repositories": {"force_delete": False, "tags": {}},
    "teardown_switch_and_caller_tags": {"force_delete": True, "tags": {"owner": "platform"}},
}
POSTCONDITION = "The repository must belong to the expected account and Region"
NEGATIVE = {
    "rejects_foreign_account_repository": ("postcondition", "test-dev-ecr-lbc"),
    "rejects_other_region_repository": ("postcondition", "test-dev-ecr-istio-pilot"),
    "rejects_uppercase_prefix": ("variable", "name_prefix must be <project>-<env>"),
    "rejects_prefix_without_environment": ("variable", "name_prefix must be <project>-<env>"),
    "rejects_long_project_prefix": ("variable", "name_prefix must be <project>-<env>"),
    "rejects_empty_purposes": ("variable", "purposes must hold 1-10"),
    "rejects_uppercase_purpose": ("variable", "purposes must hold 1-10"),
    "rejects_purpose_with_slash": ("variable", "purposes must hold 1-10"),
    "rejects_too_many_purposes": ("variable", "purposes must hold 1-10"),
    "rejects_invalid_account": ("variable", "expected_scope needs a 12-digit account_id"),
    "rejects_invalid_region": ("variable", "expected_scope needs a 12-digit account_id"),
    "rejects_name_tag": ("variable", "tags must not set Name, service"),
    "rejects_service_tag": ("variable", "tags must not set Name, service"),
    "rejects_aws_prefixed_tag": ("variable", "tags must not set Name, service"),
}
REPOSITORY_KEYS = {"arn", "encryption_configuration", "force_delete", "id", "image_scanning_configuration", "image_tag_mutability",
                   "image_tag_mutability_exclusion_filter", "name", "region", "registry_id", "repository_url", "tags", "tags_all", "timeouts"}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def only(items, code):
    require(isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict), code)
    return items[0]


def check_plan(run, plan, expected):
    changes = plan.get("resource_changes") or []
    # Exactly the three locked repositories: no repository or registry policy, lifecycle
    # policy, pull through cache rule, secret, KMS key, IAM role or endpoint.
    require({c.get("address") for c in changes} == RESOURCES and len(changes) == len(RESOURCES), "resource_set:" + run)
    outputs = {}
    for change in changes:
        require(change.get("mode") == "managed" and change.get("type") == "aws_ecr_repository"
                and change["change"].get("actions") == ["create"], "create_only:" + run)
        purpose = change["address"].split('"')[1]
        name = "test-dev-ecr-" + purpose
        after = change["change"].get("after") or {}
        require(set(after) <= REPOSITORY_KEYS, "unexpected_attribute:" + run)
        require(after.get("name") == name, "name:" + run)
        require(after.get("image_tag_mutability") == "IMMUTABLE" and after.get("image_tag_mutability_exclusion_filter") == [], "immutable:" + run)
        require(after.get("force_delete") is expected["force_delete"], "force_delete:" + run)
        encryption = only(after.get("encryption_configuration"), "encryption_shape:" + run)
        require(encryption.get("encryption_type") == "AES256" and not str(encryption.get("kms_key") or "").startswith("arn:"), "encryption:" + run)
        require(only(after.get("image_scanning_configuration"), "scanning_shape:" + run).get("scan_on_push") is False, "scanning:" + run)
        require(after.get("tags") == {**expected["tags"], "Name": name, "service": "ecr"}, "tags:" + run)
        require(after.get("region") == REGION and after.get("registry_id") == ACCOUNT
                and after.get("arn") == f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{name}"
                and after.get("repository_url") == f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{name}", "scope:" + run)
        outputs[purpose] = {"name": name, "arn": after["arn"], "repository_url": after["repository_url"]}
    require((plan.get("output_changes") or {}).get("repositories", {}).get("after") == outputs, "output:" + run)


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
    for run, (kind, fragment) in NEGATIVE.items():
        errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("@testrun") == run
                  and e.get("diagnostic", {}).get("severity") == "error"]
        if kind == "variable":
            require(errors and all(d.get("summary") == "Invalid value for variable" for d in errors)
                    and any(fragment in d.get("detail", "") and "variables.tf" in d.get("detail", "") for d in errors), "negative:" + run)
        else:
            require(errors and all(d.get("summary") == "Resource postcondition failed" for d in errors)
                    and any(POSTCONDITION in d.get("detail", "") and {"traversal": "self.name", "statement": f'is "{fragment}"'}
                            in d.get("snippet", {}).get("values", []) for d in errors), "negative:" + run)
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
                    return item
    raise KeyError(address)


def after(events, run, purpose):
    return change(events, run, f'aws_ecr_repository.this["{purpose}"]')["change"]["after"]


def add_resource(events, address, kind):
    for event in events:
        if event.get("type") == "test_plan" and event.get("@testrun") == "locked_repositories":
            extra = copy.deepcopy(event["test_plan"]["resource_changes"][0])
            extra.update(address=address, type=kind)
            event["test_plan"]["resource_changes"].append(extra)


def semantic_mutations():
    run = "locked_repositories"
    yield "mutable_tags", lambda e: after(e, run, "lbc").update(image_tag_mutability="MUTABLE")
    yield "immutable_with_exclusion", lambda e: after(e, run, "lbc").update(
        image_tag_mutability="IMMUTABLE_WITH_EXCLUSION", image_tag_mutability_exclusion_filter=[{"filter": "latest*", "filter_type": "WILDCARD"}])
    yield "force_delete_by_default", lambda e: after(e, run, "istio-pilot").update(force_delete=True)
    yield "teardown_switch_ignored", lambda e: after(e, "teardown_switch_and_caller_tags", "istio-proxy").update(force_delete=False)
    yield "kms_encryption", lambda e: after(e, run, "istio-proxy")["encryption_configuration"][0].update(encryption_type="KMS")
    yield "customer_kms_key", lambda e: after(e, run, "istio-proxy")["encryption_configuration"][0].update(
        kms_key="arn:aws:kms:ca-central-1:000000000000:key/x")
    yield "scan_on_push", lambda e: after(e, run, "lbc")["image_scanning_configuration"][0].update(scan_on_push=True)
    yield "unlocked_name", lambda e: after(e, run, "lbc").update(name="test-dev-ecr-busybox")
    yield "other_environment_name", lambda e: after(e, run, "lbc").update(name="test-prod-ecr-lbc")
    yield "service_tag", lambda e: after(e, run, "lbc")["tags"].update(service="s3")
    yield "name_tag", lambda e: after(e, run, "istio-pilot")["tags"].update(Name="other")
    yield "caller_tags_lost", lambda e: after(e, "teardown_switch_and_caller_tags", "lbc")["tags"].pop("owner")
    yield "foreign_account", lambda e: after(e, run, "lbc").update(registry_id="111111111111")
    yield "other_region", lambda e: after(e, run, "lbc").update(region="us-east-1")
    yield "public_registry_url", lambda e: after(e, run, "lbc").update(repository_url="public.ecr.aws/test/lbc")
    yield "arn_other_partition", lambda e: after(e, run, "lbc").update(arn="arn:aws-us-gov:ecr:ca-central-1:000000000000:repository/test-dev-ecr-lbc")
    yield "unlocked_repository", lambda e: add_resource(e, 'aws_ecr_repository.this["busybox"]', "aws_ecr_repository")
    yield "repository_policy", lambda e: add_resource(e, "aws_ecr_repository_policy.this", "aws_ecr_repository_policy")
    yield "registry_policy", lambda e: add_resource(e, "aws_ecr_registry_policy.this", "aws_ecr_registry_policy")
    yield "lifecycle_policy", lambda e: add_resource(e, "aws_ecr_lifecycle_policy.this", "aws_ecr_lifecycle_policy")
    yield "pull_through_cache_rule", lambda e: add_resource(e, "aws_ecr_pull_through_cache_rule.this", "aws_ecr_pull_through_cache_rule")
    yield "unexpected_attribute", lambda e: after(e, run, "lbc").update(policy="{}")
    yield "output_leaks_extra", lambda e: next(x for x in e if x.get("type") == "test_plan" and x.get("@testrun") == run)[
        "test_plan"]["output_changes"]["repositories"]["after"]["lbc"].update(token="x")


def capture_failures():
    def drop_type(kind):
        return lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != kind])

    def drop_resource(e):
        for x in e:
            if x.get("type") == "test_plan" and x.get("@testrun") == "teardown_switch_and_caller_tags":
                x["test_plan"]["resource_changes"] = x["test_plan"]["resource_changes"][1:]

    def fail_run(e):
        for x in e:
            if x.get("type") == "test_run" and x.get("test_run", {}).get("run") == "rejects_name_tag" and "status" in x["test_run"]:
                x["test_run"]["status"] = "fail"

    def strip_negative(run):
        return lambda e: e.__setitem__(slice(None), [x for x in e if not (x.get("type") == "diagnostic" and x.get("@testrun") == run)])

    def foreign_error(e):
        e.append({"type": "diagnostic", "@testrun": "locked_repositories", "diagnostic": {"severity": "error", "summary": "x", "detail": ""}})

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
    yield "failed_run", fail_run
    yield "missing_variable_diagnostic", strip_negative("rejects_invalid_account")
    yield "missing_postcondition_diagnostic", strip_negative("rejects_foreign_account_repository")
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
        print("ecr_repository verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
