#!/usr/bin/env python3
"""Verify the DEV registry root from actual mock plans, offline.

1. Native events: every expected run passes; the two positive plans contain only
   the ecr_repository module's repositories, with the module's fixed protections
   (checked by the module checker) and the expected tags.
2. Image lock: kubernetes/images.lock.json passes the Kubernetes validator's own
   lock check (raw manifests, digests, platforms), and the planned repositories,
   their names and the registry output are exactly its purposes, no more, no less.
3. Required inputs: omitting project or aws_account_id fails before any plan,
   in a copy without the committed terraform.tfvars.
4. --self-test: semantic mutations and capture failures must be rejected.
No AWS API is called.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[4]
sys.path.insert(0, str(REPOSITORY / "infra/modules/ecr_repository/tests"))
sys.path.insert(0, str(REPOSITORY / "scripts/terraform-testing"))
sys.path.insert(0, str(REPOSITORY / "kubernetes/tools"))
from check_ecr_repository import check_plan, require  # noqa: E402
from isolated_root import tfvars_free_copy  # noqa: E402
from validate import verify_image_lock  # noqa: E402

PREFIX = "module.repositories."
HOST = "000000000000.dkr.ecr.ca-central-1.amazonaws.com"
LOCK_FILE = REPOSITORY / "kubernetes/images.lock.json"
POSITIVE = {
    "registry_from_image_lock": {"force_delete": False, "tags": {}},
    "teardown_switch_and_caller_tags": {"force_delete": True, "tags": {"owner": "platform"}},
}
NEGATIVE = {
    "rejects_invalid_project": "project must be 1-10 lowercase",
    "rejects_long_project": "project must be 1-10 lowercase",
    "rejects_invalid_account": "aws_account_id must be exactly 12 decimal digits",
    "rejects_reserved_tag": "tags must not set project, env, service, managed or Name",
    "rejects_name_tag": "tags must not set project, env, service, managed or Name",
}
REQUIRED = ("project", "aws_account_id")


def lock_purposes(lock):
    # The Kubernetes validator re-proves the lock from the raw manifests; its keys are
    # the only approved purposes, so an unapproved or missing purpose cannot pass.
    return set(verify_image_lock(lock))


def verify(events, exit_code, lock=None):
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8")) if lock is None else lock
    purposes = lock_purposes(lock)
    require(exit_code == 0, "terraform_exit")
    require([e.get("terraform") for e in events if e.get("type") == "version"] == ["1.17.0"], "version")
    expected_runs = set(POSITIVE) | set(NEGATIVE)
    abstracts = [e.get("test_abstract") for e in events if e.get("type") == "test_abstract"]
    require(len(abstracts) == 1 and len(abstracts[0]) == 1 and set(next(iter(abstracts[0].values()))) == expected_runs, "manifest")
    terminals = [(e["test_run"].get("run"), e["test_run"].get("status")) for e in events
                 if e.get("type") == "test_run" and "status" in e.get("test_run", {})]
    require(sorted(terminals) == sorted((run, "pass") for run in expected_runs), "run_terminals")
    require([e.get("test_summary") for e in events if e.get("type") == "test_summary"]
            == [{"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}], "summary")
    plans = {}
    for event in events:
        if event.get("type") == "test_plan":
            require(event.get("@testrun") not in plans, "duplicate_plan")
            plans[event.get("@testrun")] = event.get("test_plan") or {}
    for run, expected in POSITIVE.items():
        plan = copy.deepcopy(plans.get(run))
        require(plan, "missing_plan:" + run)
        planned = set()
        for change in plan.get("resource_changes") or []:
            require(change.get("address", "").startswith(PREFIX), "resource_outside_module:" + run)
            change["address"] = change["address"][len(PREFIX):]
            planned.add(change["address"].split('"')[1] if '"' in change["address"] else change["address"])
        require(planned == purposes, "repositories_differ_from_image_lock:" + run)
        registry = (plan.get("output_changes") or {}).get("registry", {}).get("after") or {}
        require(set(registry) == {"host", "repositories"} and registry["host"] == HOST, "registry_output:" + run)
        require(set(registry["repositories"]) == purposes, "output_differs_from_image_lock:" + run)
        plan["output_changes"] = {"repositories": {"after": registry["repositories"]}}
        check_plan(run, plan, expected)
    for run, fragment in NEGATIVE.items():
        errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("@testrun") == run
                  and e.get("diagnostic", {}).get("severity") == "error"]
        require(errors and all(d.get("summary") == "Invalid value for variable" for d in errors)
                and any(fragment in d.get("detail", "") for d in errors), "negative:" + run)
    require(not [e for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"
                 and e.get("@testrun") not in NEGATIVE], "unexpected_error_diagnostic")
    return {"status": "passed", "evidence_type": "actual_mock_plan_verification", "aws_api_calls": 0,
            "native_tests": len(expected_runs), "positive_plans": len(POSITIVE), "negative_cases": len(NEGATIVE),
            "image_lock_purposes": sorted(purposes)}


def required_inputs(terraform):
    header = (ROOT / "tests/registry.tftest.hcl").read_text(encoding="utf-8").split('\nrun "', 1)[0]
    header, count = re.subn(r"(?m)^variables \{[^}]*\}\n", "", header)
    require(count == 1, "required_fixture_header")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TF_VAR_", "TF_CLI_ARGS"))}
    env.update(TF_INPUT="0", TF_IN_AUTOMATION="1", AWS_EC2_METADATA_DISABLED="true",
               AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null")
    values = {"project": "test", "aws_account_id": "000000000000"}
    results = []
    with tfvars_free_copy(ROOT) as (workspace, isolation):
        env.update(isolation)
        for missing in REQUIRED:
            folder = workspace / "tests" / missing
            folder.mkdir()
            supplied = "\n".join(f"  {k} = {json.dumps(v)}" for k, v in values.items() if k != missing)
            (folder / "missing.tftest.hcl").write_text(header + "\nvariables {\n" + supplied + '\n}\nrun "missing_input" {\n  command = plan\n}\n')
            process = subprocess.run([terraform, "test", "-json", "-no-color", "-test-directory=" + str(folder.relative_to(workspace))],
                                     cwd=workspace, env=env, capture_output=True, text=True, check=False)
            events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith("{")]
            errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e["diagnostic"].get("severity") == "error"]
            require(process.returncode == 1 and not process.stderr.strip() and errors
                    and all(d.get("summary") == "No value for required variable" for d in errors)
                    and any(missing in d.get("detail", "") for d in errors)
                    and not any(e.get("type") == "test_plan" for e in events), "required_input:" + missing)
            results.append(missing)
    return results


def plan_of(events, run):
    return next(e for e in events if e.get("type") == "test_plan" and e.get("@testrun") == run)["test_plan"]


def change(events, run, purpose):
    for item in plan_of(events, run)["resource_changes"]:
        if item["address"] == f'{PREFIX}aws_ecr_repository.this["{purpose}"]':
            return item
    raise KeyError(purpose)


def mutations():
    run = "registry_from_image_lock"

    def extra_repository(e):
        extra = copy.deepcopy(change(e, run, "lbc"))
        extra["address"] = f'{PREFIX}aws_ecr_repository.this["busybox"]'
        extra["change"]["after"].update(name="test-dev-ecr-busybox")
        plan_of(e, run)["resource_changes"].append(extra)

    def missing_repository(e):
        plan_of(e, run)["resource_changes"] = [c for c in plan_of(e, run)["resource_changes"] if "lbc" not in c["address"]]

    def lock_edit(edit):
        def apply(e):
            lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
            edit(lock)
            e.append({"type": "lock_override", "lock": lock})
        return apply

    yield "semantic", "extra_repository", extra_repository
    yield "semantic", "missing_repository", missing_repository
    yield "semantic", "renamed_repository", lambda e: change(e, run, "istio-proxy")["change"]["after"].update(name="test-dev-ecr-istio-proxyv2")
    yield "semantic", "registry_host", lambda e: plan_of(e, run)["output_changes"]["registry"]["after"].update(host="public.ecr.aws")
    yield "semantic", "registry_output_extra", lambda e: plan_of(e, run)["output_changes"]["registry"]["after"].update(token="x")
    yield "semantic", "output_missing_purpose", lambda e: plan_of(e, run)["output_changes"]["registry"]["after"]["repositories"].pop("lbc")
    yield "semantic", "force_delete_by_default", lambda e: change(e, run, "lbc")["change"]["after"].update(force_delete=True)
    yield "semantic", "mutable_tags", lambda e: change(e, run, "istio-pilot")["change"]["after"].update(image_tag_mutability="MUTABLE")
    yield "semantic", "caller_tags_lost", lambda e: change(e, "teardown_switch_and_caller_tags", "lbc")["change"]["after"]["tags"].pop("owner")
    yield "semantic", "lock_extra_purpose", lock_edit(lambda lock: lock["images"].append(dict(lock["images"][0], purpose="busybox")))
    yield "semantic", "lock_missing_purpose", lock_edit(lambda lock: lock["images"].pop())
    yield "semantic", "lock_tag_reference", lock_edit(lambda lock: lock["registry"].update(reference="tag"))
    yield "capture", "resource_outside_module", lambda e: change(e, run, "lbc").update(address='aws_ecr_repository.this["lbc"]')
    yield "capture", "no_summary", lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != "test_summary"])
    yield "capture", "no_plans", lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != "test_plan"])
    yield "capture", "negative_diagnostic_lost", lambda e: e.__setitem__(slice(None), [
        x for x in e if not (x.get("type") == "diagnostic" and x.get("@testrun") == "rejects_invalid_account")])


def self_test(events):
    counts = {"semantic_mutations": 0, "capture_failure_injections": 0}
    for kind, name, mutate in mutations():
        mutated = copy.deepcopy(events)
        mutate(mutated)
        overrides = [x["lock"] for x in mutated if x.get("type") == "lock_override"]
        mutated = [x for x in mutated if x.get("type") != "lock_override"]
        try:
            verify(mutated, 0, overrides[0] if overrides else None)
        except (ValueError, KeyError, TypeError, StopIteration):
            counts["semantic_mutations" if kind == "semantic" else "capture_failure_injections"] += 1
            continue
        raise ValueError("mutation_not_detected:" + name)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-events", required=True)
    parser.add_argument("--terraform-exit-code", type=int, required=True)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        with open(args.test_events, encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        report = verify(events, args.terraform_exit_code)
        report["required_input_rejections"] = len(required_inputs(args.terraform))
        if args.self_test:
            report.update(self_test(events))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print("registry root verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
