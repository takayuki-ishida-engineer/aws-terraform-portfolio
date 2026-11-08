#!/usr/bin/env python3
"""Exercise rejected root inputs with isolated, offline Terraform mock tests.

Terraform 1.17 expect_failures cannot address a child module's input variable.
These cases therefore require a failed mock-test process and the relevant real
variable diagnostic. They are rejected-input evidence, not passing root plans.
The existing initialized root and locked provider are reused without creating
provider installations or altering production configuration.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("missing_artifact_bucket_name", "artifact_bucket_name", None, "missing", "artifact_bucket_name"),
    ("missing_artifact_key", "artifact_key", None, "missing", "artifact_key"),
    ("missing_artifact_object_version", "artifact_object_version", None, "missing", "artifact_object_version"),
    ("missing_lambda_runtime", "lambda_runtime", None, "missing", "lambda_runtime"),
    ("missing_lambda_handler", "lambda_handler", None, "missing", "lambda_handler"),
    ("blank_artifact_key", "artifact_key", "", "invalid", "s3_key"),
    ("blank_artifact_object_version", "artifact_object_version", "", "invalid", "s3_object_version"),
    ("null_artifact_object_version", "artifact_object_version", None, "null", "artifact_object_version"),
    ("null_version_sentinel", "artifact_object_version", "null", "invalid", "s3_object_version"),
    ("unsupported_lambda_runtime", "lambda_runtime", "python2.7", "invalid", "runtime"),
    ("invalid_runtime_handler", "lambda_handler", "app::handler", "invalid", "handler"),
    ("unsafe_artifact_bucket_name", "artifact_bucket_name", "bad..bucket", "invalid", "bucket_name"),
]


def require(condition, code):
    if not condition:
        raise ValueError(code)


def unique_object(pairs):
    result = {}
    for key, val in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = val
    return result


def reject_constant(_value):
    raise ValueError("nonfinite_json")


def inspect_failure(path, expected_name, mode, returncode):
    require(returncode == 1, "expected_rejected_test_exit_1")
    errors, summaries, terminals, files, declarations, plans = [], [], [], [], [], 0
    for line in path.open(encoding="utf-8"):
        event = json.loads(line, object_pairs_hook=unique_object, parse_constant=reject_constant)
        require(isinstance(event, dict), "negative_event_shape")
        require(not summaries, "negative_event_after_summary")
        kind = event.get("type")
        require(kind in {"version", "test_abstract", "test_run", "test_file", "diagnostic", "test_summary", "log", "test_plan"}, "negative_event_type")
        if kind == "test_abstract":
            declarations.append(event.get("test_abstract"))
        if kind == "test_file" and "status" in event.get("test_file", {}):
            files.append(event["test_file"]["status"])
        if kind == "diagnostic":
            diagnostic = event.get("diagnostic", {})
            if diagnostic.get("severity") == "error":
                require(event.get("@level") == "error", "negative_diagnostic_level")
                errors.append(diagnostic)
        if kind == "test_run" and "status" in event.get("test_run", {}):
            require(event.get("@testrun") == "rejected_input" and event["test_run"].get("run") == "rejected_input", "negative_run_identity")
            terminals.append(event["test_run"]["status"])
        if kind == "test_plan":
            # Terraform only emits verbose test_plan after successful runs;
            # reject any purported complete configuration in a failing case.
            plans += 1
        if kind == "test_summary":
            summaries.append(event.get("test_summary"))
    require(errors and not plans, "negative_requires_diagnostic_without_successful_plan")
    allowed = {"No value for required variable"} if mode == "missing" else {
        "Invalid value for variable", "Required variable not set"}
    require(all(item.get("summary") in allowed for item in errors), "unexpected_negative_diagnostic")
    require(any(re.search(r"\b" + re.escape(expected_name) + r"\b", item.get("detail", "")) for item in errors), "negative_variable_identity")
    require(len(declarations) == 1 and isinstance(declarations[0], dict) and len(declarations[0]) == 1
        and list(declarations[0].values()) == [["rejected_input"]], "negative_declared_coverage")
    require(len(files) == 1 and files[0] in {"fail", "error"}, "negative_file_terminal")
    # Intentional input errors must remain explicit failures with complete
    # terminal evidence; they are never counted as passing resource plans.
    require(len(terminals) == 1 and all(status in {"fail", "error"} for status in terminals), "negative_nonfailing_run")
    require(len(summaries) == 1 and summaries[0].get("status") in {"fail", "error"}
        and all(type(summaries[0].get(key)) is int for key in ("passed", "failed", "errored", "skipped"))
        and summaries[0].get("passed") == 0 and summaries[0].get("skipped") == 0
        and summaries[0].get("failed", 0) + summaries[0].get("errored", 0) == 1, "negative_summary")
    return {"expected_variable": expected_name, "exit_code": returncode,
        "error_summaries": sorted({item["summary"] for item in errors}), "successful_plans": plans}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args()
    try:
        source = (ROOT / "tests/root_integration.tftest.hcl").read_text(encoding="utf-8")
        header, marker, _runs = source.partition('\nrun "')
        require(marker and re.search(r'^mock_provider "aws" \{\}', header, re.M)
            and "override_module" not in header and len(re.findall(r'^variables \{', header, re.M)) == 1, "reviewed_native_fixture_header")
        env = {key: val for key, val in os.environ.items() if not key.startswith(("AWS_", "TF_VAR_", "TF_CLI_ARGS"))}
        env.update(TF_INPUT="0", TF_IN_AUTOMATION="1", AWS_EC2_METADATA_DISABLED="true",
            AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null")
        reports = []
        # Terraform requires a relative local test directory. These temporary
        # test files reuse this root's initialization and are removed on exit;
        # no additional .terraform/provider directory or initialization is made.
        with tempfile.TemporaryDirectory(prefix=".negative-inputs-", dir=ROOT / "tests") as work:
            work = Path(work)
            for identifier, variable, supplied, mode, expected_name in CASES:
                fixture = work / identifier
                fixture.mkdir()
                pattern = r'^  ' + re.escape(variable) + r'\s*=.*\n'
                replacement = "" if mode == "missing" else "  " + variable + " = " + json.dumps(supplied) + "\n"
                text, count = re.subn(pattern, lambda _match: replacement, header, flags=re.M)
                require(count == 1, "fixture_input_assignment:" + identifier)
                (fixture / "negative.tftest.hcl").write_text(text + '\nrun "rejected_input" {\n  command = plan\n}\n', encoding="utf-8")
                events = fixture / "events.jsonl"
                with events.open("w", encoding="utf-8") as output:
                    process = subprocess.run([args.terraform, "test", "-json", "-verbose", "-no-color", "-test-directory=" + str(fixture.relative_to(ROOT))],
                        cwd=ROOT, env=env, stdout=output, stderr=subprocess.PIPE, text=True, check=False)
                require(not process.stderr.strip(), "negative_unexpected_stderr:" + identifier)
                try:
                    report = inspect_failure(events, expected_name, mode, process.returncode)
                except ValueError as error:
                    raise ValueError(identifier + ":" + str(error)) from error
                reports.append({"id": identifier, "detected": True, **report})
        print(json.dumps({"status": "passed", "aws_api_calls": 0, "rejected_input_cases": len(reports),
            "native_pass_count": 0, "cases": reports,
            "limitations": ["These intentional mock-test failures validate input rejection, not deployable resource configurations."]}, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("Root negative-input verification failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
