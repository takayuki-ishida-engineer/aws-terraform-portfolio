#!/usr/bin/env python3
"""Reviewed expected test and mutation counts, kept apart from the CI logic.

The values live in tests/expected-counts.json, a reviewable data file. Full CI and
PR Safety CI steps read them through ``load(suite)``; the checks themselves (the
comparisons, statuses and evidence types) stay in the workflow. A normal count
update changes only the data file, so it needs no workflow change, and
scripts/ci/impact.py selects exactly the steps that load the changed suites.

Fail closed (CountsError):
* the file is missing, unparsable, has another schema or unknown top-level fields;
* a suite or key is missing or unknown (SCHEMA below is the exact contract);
* a value is not a positive integer (booleans and strings are refused);
* an ``approved_reductions`` record is malformed.

The values are reviewed expectations. They are never generated from, or rewritten
to match, the counts a run observes. A decrease against the base branch fails PR
Safety CI unless it carries an approved_reductions record, and a recorded decrease
is high-risk (Full CI and Owner review). SCHEMA is CI logic: adding a suite or key
changes this file, which is a high-risk CI change.
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
COUNTS_FILE = "tests/expected-counts.json"
TOP_LEVEL = {"schema", "comment", "suites", "approved_reductions"}
REDUCTION_FIELDS = {"suite", "key", "from", "to", "reason"}
_TERRAFORM = ["native_tests", "positive_plans", "negative_cases", "semantic_mutations", "capture_failure_injections"]
_OFFLINE = ["native_tests", "positive_plans", "negative_tests", "security_mutations", "evidence_faults"]
SCHEMA = {
    "ci_policy": ["tests", "mutations"],
    "network_required_inputs": ["required_input_rejections", "security_input_rejections"],
    "network": _TERRAFORM + ["source_dependency_mutations", "policy_structure_mutations"],
    "platform_required_inputs": ["required_input_rejections", "network_field_rejections"],
    "platform": _TERRAFORM + ["source_dependency_mutations"],
    "platform_ingress": _TERRAFORM + ["source_dependency_mutations", "iam_policy_mutations"],
    "eks_platform": _TERRAFORM + ["source_dependency_mutations"],
    "eks_platform_source": ["native_source_mutations"],
    "private_ingress": _TERRAFORM + ["source_dependency_mutations", "iam_policy_mutations"],
    "private_ingress_source": ["actual_source_mutations"],
    "vpc": _TERRAFORM + ["source_dependency_mutations", "policy_structure_mutations"],
    "secrets": ["native_tests"],
    "account_policies": ["native_tests"],
    "iam": ["native_tests"],
    "cloudwatch_logs": ["native_tests", "rejected_plans"],
    "lambda_workload": ["native_tests", "positive_plans", "negative_plans", "matrix_cases", "semantic_mutation_count",
                        "capture_failure_injections", "reference_failure_injections", "workload_semantic_mutation_count",
                        "workload_capture_failure_injections", "source_dependency_mutations"],
    "artifact_bucket": ["native_tests", "positive_plans", "negative_plans", "semantic_mutation_count", "capture_failure_injections"],
    "http_api": ["native_tests", "positive_plans", "negative_plans", "semantic_mutation_count", "capture_failure_injections",
                 "source_dependency_mutations"],
    "kubernetes_render": ["actual_helm_renders", "positive_configurations", "resource_count", "schema_checked_objects",
                          "semantic_mutations", "negative_cases", "evidence_faults", "image_lock_faults",
                          "injection_template_faults", "cabundle_render_faults"],
    "k8s_runtime_plan_tests": ["tests", "mutations"],
    "k8s_runtime_status_tests": ["tests", "mutations"],
    "k8s_runtime_receipt_tests": ["tests", "mutations"],
    "k8s_runtime_apply_tests": ["tests", "mutations"],
    "k8s_certificates_tests": ["tests"],
    "image_mirror_tests": ["tests", "mutations"],
    "cognito": _OFFLINE,
    "cognito_rejections": ["source_mutations", "required_root_inputs"],
    "api": _OFFLINE,
    "rest_child": _OFFLINE,
    "rest_root": _OFFLINE,
    "rest_source": ["source_mutations", "missing_required_inputs"],
    "tfstate_module": _TERRAFORM,
    "tfstate_root": ["native_tests", "positive_plans", "negative_cases", "required_input_rejections", "semantic_mutations",
                     "capture_failure_injections"],
    "registry_module": _TERRAFORM,
    "registry_root": ["native_tests", "positive_plans", "negative_cases", "required_input_rejections", "semantic_mutations",
                      "capture_failure_injections"],
    "developer_access_module": _TERRAFORM + ["source_mutations"],
    "developer_access_root": ["native_tests", "positive_plans", "negative_cases", "required_input_rejections",
                              "semantic_mutations", "capture_failure_injections"],
    "toolkit": ["tests"],
}


class CountsError(Exception):
    """The expected counts cannot be trusted: fail closed."""


def require(condition, message):
    if not condition:
        raise CountsError(message)


def positive_integer(value):
    return type(value) is int and value > 0


def validate(data, schema=SCHEMA):
    """Return the suites of a parsed counts document, or raise CountsError."""
    require(isinstance(data, dict), "counts_not_an_object")
    require(set(data) <= TOP_LEVEL and {"schema", "suites", "approved_reductions"} <= set(data), "counts_top_level_fields")
    require(data["schema"] == 1, "counts_schema")
    suites = data["suites"]
    require(isinstance(suites, dict), "counts_suites_not_an_object")
    missing, unknown = sorted(set(schema) - set(suites)), sorted(set(suites) - set(schema))
    require(not missing and not unknown, "counts_suites_differ:missing=" + ",".join(missing) + ":unknown=" + ",".join(unknown))
    for suite, keys in schema.items():
        values = suites.get(suite)
        require(isinstance(values, dict) and sorted(values) == sorted(keys), "counts_keys_differ:" + suite)
        for key, value in values.items():
            require(positive_integer(value), "counts_value_not_a_positive_integer:" + suite + "." + key)
    reductions = data["approved_reductions"]
    require(isinstance(reductions, list), "counts_reductions_not_a_list")
    for record in reductions:
        require(isinstance(record, dict) and set(record) == REDUCTION_FIELDS, "counts_reduction_fields")
        require(record["suite"] in schema and record["key"] in schema[record["suite"]], "counts_reduction_unknown_key")
        require(positive_integer(record["from"]) and positive_integer(record["to"]) and record["to"] < record["from"],
                "counts_reduction_values")
        require(isinstance(record["reason"], str) and len(record["reason"].strip()) >= 20, "counts_reduction_reason")
    return suites


def parse(text, schema=SCHEMA):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise CountsError("counts_unparsable:" + str(error)) from error
    validate(data, schema)
    return data


def load(suite, path=None):
    """The reviewed counts of one suite, as a dict of its exact keys."""
    source = Path(path) if path else REPO / COUNTS_FILE
    require(source.is_file(), "counts_file_missing:" + str(source))
    data = parse(source.read_text(encoding="utf-8"))
    require(suite in data["suites"], "counts_unknown_suite:" + suite)
    return dict(data["suites"][suite])


def reductions(base, head):
    """(unapproved, approved) decreases from the base document to the head document."""
    unapproved, approved = [], []
    records = {(item["suite"], item["key"], item["from"], item["to"]) for item in head["approved_reductions"]}
    for suite, values in head["suites"].items():
        for key, value in values.items():
            old = (base.get("suites", {}).get(suite) or {}).get(key)
            if positive_integer(old) and value < old:
                entry = f"{suite}.{key}:{old}->{value}"
                (approved if (suite, key, old, value) in records else unapproved).append(entry)
    return unapproved, approved


def changed_suites(base, head):
    """Suites whose values differ (every suite when there is no comparable base)."""
    if not isinstance(base, dict) or not isinstance(base.get("suites"), dict):
        return sorted(head["suites"])
    return sorted(suite for suite, values in head["suites"].items() if base["suites"].get(suite) != values)


if __name__ == "__main__":
    try:
        data = parse((REPO / COUNTS_FILE).read_text(encoding="utf-8"))
    except CountsError as error:
        print("Expected counts refused: " + str(error), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"status": "passed", "suites": len(data["suites"])}))
