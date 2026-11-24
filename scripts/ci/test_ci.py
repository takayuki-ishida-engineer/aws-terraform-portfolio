#!/usr/bin/env python3
"""Offline unit, negative and mutation tests for the CI policy tooling (Owner decision 2026-11-23).

Covers the PR Safety impact map (impact.py), the generated PR Safety workflow
(pr_safety_workflow.py), the Full CI trigger guard (full_ci_trigger.py), the
post-merge tree check (merge_check.py) and the always-on safety checks
(safety_checks.py). A mutant counts as detected only when a contract assertion
fails; a crash is a test failure. No network, AWS or Kubernetes access.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import expected_counts  # noqa: E402
import full_ci_trigger  # noqa: E402
import impact  # noqa: E402
import merge_check  # noqa: E402
import pr_safety_workflow  # noqa: E402
import safety_checks  # noqa: E402

EXPECTED_TESTS = 31
EXPECTED_MUTATIONS = 73
FULL = ".github/workflows/terraform-offline-ci.yml"
SAFETY = ".github/workflows/pr-safety-ci.yml"
SHA_A, SHA_B, SHA_C, SHA_D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
_TREE = None
_ANALYSIS = None


def tree():
    global _TREE
    if _TREE is None:
        _TREE = impact.Tree()
    return _TREE


def analysis():
    global _ANALYSIS
    if _ANALYSIS is None:
        _ANALYSIS = impact.Analysis(tree())
    return _ANALYSIS


def changes(*paths):
    return [("M", path) for path in paths]


def fails(function, *args, **kwargs):
    """The error text when function fails closed, else None."""
    try:
        function(*args, **kwargs)
    except (impact.ImpactError, full_ci_trigger.TriggerError, merge_check.MergeError, safety_checks.SafetyError,
            expected_counts.CountsError) as error:
        return str(error)
    return None


def with_map(edit):
    mapping = json.loads(tree().read(impact.MAP_FILE))
    edit(mapping)
    return tree().with_files({impact.MAP_FILE: json.dumps(mapping)})


def runner_for(answers):
    """A fake git runner: answers maps joined arguments to (code, stdout)."""
    def run(args):
        key = " ".join(args)
        if key not in answers:
            raise AssertionError("unexpected git call: " + key)
        return answers[key]
    return run


def pull_request_case(**override):
    env = {"EVENT_NAME": "pull_request", "RUN_SHA": SHA_A, "RUN_ATTEMPT": "1", "BASE_REF": "main", "PR_NUMBER": "97", "PR_HEAD_SHA": SHA_C}
    env.update(override.pop("env", {}))
    answers = {"rev-parse HEAD": (0, SHA_A), "rev-list --parents -n 1 HEAD": (0, f"{SHA_A} {SHA_B} {SHA_C}"),
               "rev-parse HEAD^{tree}": (0, SHA_D), f"rev-parse {SHA_C}^{{tree}}": (0, SHA_D)}
    answers.update(override.pop("answers", {}))
    return env, runner_for(answers)


def dispatch_case(**override):
    env = {"EVENT_NAME": "workflow_dispatch", "RUN_SHA": SHA_C, "RUN_ATTEMPT": "1", "REF": "refs/heads/claude/x", "OWNER": "owner",
           "ACTOR": "owner", "TRIGGERING_ACTOR": "owner", "INPUT_PR": "97", "INPUT_SHA": SHA_C, "INPUT_REASON": "owner-milestone",
           "REPOSITORY": "owner/repo"}
    env.update(override.pop("env", {}))
    answers = {"rev-parse HEAD": (0, SHA_C), "rev-parse refs/remotes/origin/main": (0, SHA_B),
               f"merge-base --is-ancestor {SHA_B} HEAD": (0, ""), "rev-parse HEAD^{tree}": (0, SHA_D)}
    answers.update(override.pop("answers", {}))
    return env, runner_for(answers)


def good_pull(**change):
    pull = {"number": 97, "state": "open", "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
            "head": {"ref": "claude/x", "sha": SHA_C, "repo": {"full_name": "owner/repo"}}}
    for path, value in change.items():
        target = pull
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return pull


def fetch_of(pull):
    return lambda repository, number: pull


COUNTS = expected_counts.COUNTS_FILE


def counts_doc():
    return json.loads(tree().read(COUNTS))


def counts_text(edit):
    doc = counts_doc()
    edit(doc)
    return json.dumps(doc, indent=2) + "\n"


def pair(changes_by_path):
    """(head analysis over edited files, base = the committed tree)."""
    return module_analysis(impact, changes_by_path)


def module_analysis(module, changes_by_path):
    base = module.Tree()
    return module.Analysis(base.with_files(changes_by_path), base)


def apply_fake_change():
    """A Fake-only engine change: a new helper with no guard or process keyword."""
    text = tree().read("scripts/local-workflow/k8s_runtime_apply.py")
    return text + "\n\ndef fake_destroy_plan_order(stages):\n    return list(reversed(stages))\n"


def workflow_text(name):
    return (REPO / ".github/workflows" / name).read_text(encoding="utf-8")


def impact_map():
    return json.loads((REPO / impact.MAP_FILE).read_text(encoding="utf-8"))


# ---- probes: each raises AssertionError when a (mutant) module breaks its contract ----

def probe_unmapped(module):
    analysis = module.Analysis(module.Tree())
    assert fails_with(module, analysis.select, changes("new-top-level/file.txt")), "unmapped path accepted"


def fails_with(module, function, *args):
    try:
        function(*args)
    except module.ImpactError:
        return True
    return False


def probe_too_many(module):
    analysis = module.Analysis(module.Tree())
    assert fails_with(module, analysis.select, changes(*["docs/x%d.md" % index for index in range(301)])), "301 files accepted"


def probe_merge(module):
    with mock.patch.object(module, "git", return_value=f"{SHA_A} {SHA_B} {SHA_D}\n"):
        assert fails_with(module, module.merge_changes, SHA_C), "foreign second parent accepted"
    with mock.patch.object(module, "git", return_value=f"{SHA_A} {SHA_B}\n"):
        assert fails_with(module, module.merge_changes, SHA_B), "non-merge checkout accepted"
    with mock.patch.object(module, "git", return_value=f"{SHA_A} {SHA_B} {SHA_C} {SHA_D}\n"):
        assert fails_with(module, module.merge_changes, SHA_C), "octopus merge checkout accepted"


def probe_companion(module):
    analysis = module.Analysis(module.Tree())
    assert "storage_after_first_init" in analysis.expand({"dev"}), "companion step dropped"


def probe_prerequisites(module):
    analysis = module.Analysis(module.Tree())
    selected = analysis.expand({"lambda_workload"})
    assert {"reference", "iam", "account_policies"} <= set(selected), "prerequisites dropped"


def probe_dependents(module):
    analysis = module.Analysis(module.Tree())
    steps, reasons = analysis.map_file("infra/modules/cognito_auth/main.tf")
    assert "api" in steps and "sourced by infra/services/dev/ca-central-1/api" in reasons, "sourcing root not selected"


def probe_module_source(module):
    base = module.Tree()
    bad = base.with_files({"infra/services/dev/ca-central-1/network/extra.tf": 'module "x" {\n  source = "terraform-aws-modules/vpc/aws"\n}\n'})
    assert fails_with(module, module.Terraform, bad, module.load_map(base)), "registry module source accepted"


def probe_local_source(module):
    base = module.Tree()
    bad = base.with_files({"infra/services/dev/ca-central-1/network/extra.tf": 'module "x" {\n  source = "../../../../scripts"\n}\n'})
    assert fails_with(module, module.Terraform, bad, module.load_map(base)), "non-configuration local source accepted"


def probe_dir_inputs(module):
    base = module.Tree()
    steps = module.Steps(base, module.load_map(base))
    inputs = module.step_inputs(base, module.PythonIndex(base), steps.by_id["tfstate"])
    assert "infra/modules/tfstate_bucket/variables.tf" in inputs, "directory the step runs in is not an input"


def probe_dir_code(module):
    base = module.Tree()
    steps = module.Steps(base, module.load_map(base))
    inputs = module.step_inputs(base, module.PythonIndex(base), steps.by_id["registry"])
    assert "kubernetes/tools/common.py" in inputs, "imports of checkers in a step directory not followed"


def probe_imports(module):
    base = module.Tree()
    steps = module.Steps(base, module.load_map(base))
    inputs = module.step_inputs(base, module.PythonIndex(base), steps.by_id["image_mirror"])
    assert "scripts/local-workflow/preflight.py" in inputs, "imported module not an input"


def probe_high_risk(module):
    analysis = module.Analysis(module.Tree())
    report = analysis.select(changes("scripts/local-workflow/preflight.py"))
    assert report["full_ci_required"] and "security-boundary" in report["high_risk"], "high-risk path not reported"


def probe_glob(module):
    assert not module.matches("a/b/c", ["a/*"]) and module.matches("a/b/c", ["a/**"]), "glob semantics"
    assert module.matches("infra/x/iam.tf", ["infra/**/iam.tf"]) and not module.matches("infra/x/iam.tfx", ["infra/**/iam.tf"]), "glob semantics"


def probe_verify(module):
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder, "report.json")
        report.write_text(json.dumps({"selected": ["dev"], "always": ["format"]}))
        workflow = Path(folder, "w.yml")
        workflow.write_text("jobs:\n  pr-safety:\n    steps:\n      - id: checkout\n      - id: impact\n      - id: changed_files\n"
                            "      - id: format\n      - id: dev\n      - id: network\n")
        good = {"checkout": {"outcome": "success"}, "impact": {"outcome": "success"}, "changed_files": {"outcome": "success"},
                "format": {"outcome": "success"}, "dev": {"outcome": "success"}, "network": {"outcome": "skipped"}}
        module.verify(report, workflow, good)
        for step, outcome in (("dev", "skipped"), ("network", "success"), ("dev", "failure"), ("format", "skipped")):
            broken = copy.deepcopy(good)
            broken[step]["outcome"] = outcome
            assert fails_with(module, module.verify, report, workflow, broken), f"{step}={outcome} accepted"


def probe_coverage(module):
    base = module.Tree().with_files({"orphan/area/file.bin": "x"})
    assert fails_with(module, lambda: module.Analysis(base).coverage()), "unmapped tracked file accepted"


def probe_classification(module):
    edited = with_map(lambda mapping: mapping["steps"]["always"].append("nonexistent_step"))
    assert fails_with(module, module.Analysis, edited), "step missing from the workflow accepted"
    edited = with_map(lambda mapping: mapping["steps"]["full_only"].pop("summary"))
    assert fails_with(module, module.Analysis, edited), "unclassified workflow step accepted"


def probe_definitions(module):
    base = module.Tree()
    old = base.read(FULL).replace("python3 tests/check_r2_migration.py --self-test", "python3 tests/check_r2_migration.py")
    changed, _notes = module.changed_step_definitions(module.Steps(base, module.load_map(base)), base.with_files({FULL: old}),
                                                      module.load_map(base), analysis().selectable)
    assert "r1_r2_guards" in changed, "changed step definition not selected"


def probe_trigger_pr_head(module):
    env, run = pull_request_case(answers={"rev-list --parents -n 1 HEAD": (0, f"{SHA_A} {SHA_B} {SHA_D}")})
    assert fails_trigger(module, env, run), "merge commit without the event head accepted"


def fails_trigger(module, env, run, fetch=None):
    try:
        module.verify(env, run, fetch or fetch_of(good_pull()))
    except module.TriggerError:
        return True
    return False


def probe_trigger_binding(module):
    for change in ({"head__ref": "other"}, {"head__sha": SHA_A}, {"base__ref": "develop"}, {"state": "closed"}, {"number": 98},
                   {"head__repo": {"full_name": "fork/repo"}}):
        env, run = dispatch_case()
        assert fails_trigger(module, env, run, fetch_of(good_pull(**change))), f"pull request mismatch accepted: {change}"
    env, run = dispatch_case()
    assert fails_trigger(module, env, run, fetch_of("not_found")), "missing pull request accepted"


def probe_trigger_not_found(module):
    env, run = dispatch_case()
    try:
        module.verify(env, run, fetch_of("not_found"))
    except module.TriggerError as error:
        assert "not_found" in str(error), "missing pull request not reported as not found: " + str(error)
        return
    raise AssertionError("missing pull request accepted")


def probe_trigger_unverified(module):
    env, run = dispatch_case()
    record = module.verify(env, run, fetch_of(None))
    assert record["pull_request_binding"].startswith("NOT_VERIFIED_BY_WORKFLOW"), "unanswered API claimed as verified"


def probe_trigger_actor(module):
    env, run = dispatch_case(env={"TRIGGERING_ACTOR": "someone"})
    assert fails_trigger(module, env, run), "non-owner triggering actor accepted"
    env, run = dispatch_case(env={"ACTOR": "someone"})
    assert fails_trigger(module, env, run), "non-owner actor accepted"


def probe_trigger_ref(module):
    env, run = dispatch_case(env={"REF": "refs/heads/main"})
    assert fails_trigger(module, env, run, fetch_of(good_pull(head__ref="main"))), "dispatch on main accepted"


def probe_trigger_sha(module):
    env, run = dispatch_case(env={"INPUT_SHA": SHA_A})
    assert fails_trigger(module, env, run, fetch_of(good_pull(head__sha=SHA_A))), "expected SHA different from the dispatched commit accepted"


def probe_trigger_main(module):
    env, run = dispatch_case(answers={f"merge-base --is-ancestor {SHA_B} HEAD": (1, "")})
    assert fails_trigger(module, env, run), "branch behind main accepted"


def probe_trigger_event(module):
    env, run = pull_request_case(env={"EVENT_NAME": "push"})
    assert fails_trigger(module, env, run), "push event accepted"


def probe_trigger_checkout(module):
    env, run = dispatch_case(answers={"rev-parse HEAD": (0, SHA_A)})
    assert fails_trigger(module, env, run), "checkout different from the run commit accepted"


def probe_trigger_reason(module):
    env, run = dispatch_case(env={"INPUT_REASON": "because"})
    assert fails_trigger(module, env, run), "unknown reason accepted"


def mutated_workflow(name, old, new):
    text = workflow_text(name)
    assert text.count(old) >= 1, (name, old)
    return text.replace(old, new, 1)


def probe_workflow(module, name, old, new, label):
    problems = module.check_workflow(name, mutated_workflow(name, old, new), impact_map())
    assert any(label in problem for problem in problems), f"{label} not reported: {problems}"


def probe_permissions(module):
    probe_workflow(module, "pr-safety-ci.yml", "permissions:\n  contents: read", "permissions:\n  contents: write", ":permissions")


def probe_pinned(module):
    probe_workflow(module, "aws-emulator-contracts.yml", "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@v7", ":unpinned:")


def probe_triggers(module):
    probe_workflow(module, "terraform-offline-ci.yml", "  workflow_dispatch:\n", "  push:\n    branches: [main]\n  workflow_dispatch:\n", ":triggers:")


def probe_rehearsal(module):
    probe_workflow(module, "aws-emulator-rehearsal.yml", "      - infra/**\n", "      - infra/**\n      - docs/**\n", "rehearsal-trigger-paths-changed")


def probe_high_risk_paths(module):
    probe_workflow(module, "terraform-offline-ci.yml", "      - .gitignore\n", "", "high-risk-paths-differ-from-impact-map")


def probe_every_pr(module):
    probe_workflow(module, "pr-safety-ci.yml", "    branches: [main]\n", "    branches: [main]\n    paths: [infra/**]\n", "pr-safety-must-run-on-every-pull-request")


def probe_persist(module):
    probe_workflow(module, "aws-emulator-contracts.yml", "persist-credentials: false", "persist-credentials: true", "checkout-persists-credentials")


def probe_forbidden(module):
    probe_workflow(module, "pr-safety-ci.yml", "      AWS_CONFIG_FILE: /dev/null\n", "      AWS_CONFIG_FILE: /dev/null\n      TOKEN: ${{ secrets.X }}\n", "secrets-context")


def probe_timeout(module):
    probe_workflow(module, "aws-emulator-contracts.yml", "timeout-minutes: 5", "timeout-minutes: 600", ":timeout")


def probe_check_name(module):
    probe_workflow(module, "terraform-offline-ci.yml", "name: Credential-free Terraform validation", "name: Full CI", "full-ci-check-name-or-timeout")


def probe_secret_scan(module):
    key = "AKIA" + "ABCDEFGHIJKLMNOP"
    assert module.scan_text("x", "id = " + key), "access key id not found"
    assert module.scan_text("x", "-----BEGIN " + "OPENSSH PRIVATE KEY-----"), "private key not found"


def probe_secret_names(module):
    with tempfile.TemporaryDirectory() as folder:
        assert module.check_secrets(Path(folder), [".env", "keys/id_rsa"]), "credential-like file names accepted"


def probe_guards(module):
    problems = module.check_guards(REPO, [(["scripts/ci/impact.py", "--help"], "live_refused_in_ci")])
    assert problems, "a command that is not refused passed the guard check"


def probe_syntax(module):
    for name, data in (("x.py", b"def (:\n"), ("x.json", b"{"), ("x.yml", b"a: [\n"), ("x.sh", b"if then\n")):
        try:
            module.syntax_problem(name, data)
        except Exception:  # noqa: BLE001 - any parse error is the expected refusal
            continue
        raise AssertionError(name + " parsed")


def probe_generator_condition(module):
    text = module.generate()
    for step_id in analysis().selectable:
        assert f"if: ${{{{ contains(fromJSON(steps.impact.outputs.selected), '{step_id}') }}}}" in text, step_id + " not gated"


def probe_generator_full_only(module):
    try:
        text = module.generate()
    except impact.ImpactError as error:
        raise AssertionError("generation must succeed without Full-CI-only steps: " + str(error)) from error
    assert "id: trigger\n" not in text and "id: storage_after_modules\n" not in text, "Full-CI-only step copied"


TREE_V, TREE_X = "e" * 40, "f" * 40


def probe_merge_parent(module):
    assert fails_merge(module, merge_runner(parent=SHA_D)), "squash commit on another parent accepted"


def probe_merge_tree(module):
    assert fails_merge(module, merge_runner(squash_tree=TREE_X)), "squash tree different from the verified tree accepted"


def probe_merge_evidence(module):
    assert fails_merge(module, merge_runner(merged_tree=TREE_X)), "verified tree that is not the reviewed merge accepted"


def probe_merge_dispatch_tree(module):
    assert fails_merge(module, merge_runner(head_tree=TREE_X), "dispatch"), "verified tree that is not the reviewed HEAD accepted"


def probe_merge_dispatch_base(module):
    assert fails_merge(module, merge_runner(head_tree=TREE_V, ancestor=1), "dispatch"), "HEAD without the base accepted"


def merge_runner(parent=SHA_B, squash_tree=TREE_V, merged_tree=TREE_V, head_tree=TREE_V, ancestor=0):
    return runner_for({f"rev-list --parents -n 1 {SHA_A}": (0, f"{SHA_A} {parent}"), f"rev-parse {SHA_A}^{{tree}}": (0, squash_tree),
                       f"merge-tree --write-tree {SHA_B} {SHA_C}": (0, merged_tree), f"rev-parse {SHA_C}^{{tree}}": (0, head_tree),
                       f"merge-base --is-ancestor {SHA_B} {SHA_C}": (ancestor, "")})


def fails_merge(module, run, evidence="pull_request"):
    try:
        module.verify(SHA_A, SHA_C, SHA_B, TREE_V, evidence, run)
    except module.MergeError:
        return True
    return False


def probe_counts_schema(module):
    for edit in (lambda d: d["suites"].pop("toolkit"), lambda d: d["suites"].update(extra={"tests": 1}),
                 lambda d: d["suites"]["toolkit"].pop("tests"), lambda d: d["suites"]["toolkit"].update(more=1)):
        doc = counts_doc()
        edit(doc)
        try:
            module.validate(doc)
        except module.CountsError:
            continue
        raise AssertionError("counts schema drift accepted")


def probe_counts_values(module):
    for value in (True, 0, -1, "153", 153.0, None):
        doc = counts_doc()
        doc["suites"]["toolkit"]["tests"] = value
        try:
            module.validate(doc)
        except module.CountsError:
            continue
        raise AssertionError(f"count value {value!r} accepted")


def probe_counts_reason(module):
    doc = counts_doc()
    doc["approved_reductions"] = [{"suite": "toolkit", "key": "tests", "from": 153, "to": 150, "reason": "short"}]
    try:
        module.validate(doc)
    except module.CountsError:
        return
    raise AssertionError("reduction without a reason accepted")


def probe_counts_reduction(module):
    base, head = counts_doc(), counts_doc()
    head["suites"]["toolkit"]["tests"] = 150
    unapproved, _approved = module.reductions(base, head)
    assert unapproved == ["toolkit.tests:153->150"], "unrecorded decrease not reported"


def decreased(record=False):
    def edit(doc):
        doc["suites"]["k8s_runtime_apply_tests"]["tests"] -= 1
        if record:
            old = doc["suites"]["k8s_runtime_apply_tests"]["tests"] + 1
            doc["approved_reductions"].append({"suite": "k8s_runtime_apply_tests", "key": "tests", "from": old, "to": old - 1,
                                               "reason": "Two engine tests merged into one parametrized test (reviewed)."})
    return counts_text(edit)


def probe_select_unapproved_decrease(module):
    analysis = module_analysis(module, {COUNTS: decreased()})
    assert fails_with(module, analysis.select, changes(COUNTS)), "unrecorded count decrease accepted"


def probe_select_approved_decrease(module):
    report = module_analysis(module, {COUNTS: decreased(record=True)}).select(changes(COUNTS))
    assert report["full_ci_required"] and "expected-count-reduction" in report["high_risk"], "recorded decrease not high-risk"


def increased():
    def edit(doc):
        doc["suites"]["k8s_runtime_apply_tests"]["tests"] += 2
        doc["suites"]["k8s_runtime_apply_tests"]["mutations"] += 5
    return counts_text(edit)


def probe_count_increase_is_normal(module):
    report = module_analysis(module, {COUNTS: increased(), "scripts/local-workflow/k8s_runtime_apply.py": apply_fake_change()}).select(
        changes(COUNTS, "scripts/local-workflow/k8s_runtime_apply.py"))
    assert report["selected"] == ["kubernetes_runtime", "kubernetes_runtime_plan"], "count increase selected " + str(report["selected"])
    assert not report["full_ci_required"], "Fake-only change with a count increase required Full CI"


def probe_counts_suites_loaded(module):
    text = module.Tree().read(FULL).replace('load("toolkit")', 'load("toolkit_renamed")')
    assert fails_with(module, module.Analysis, module.Tree().with_files({FULL: text})), "suite loaded by no step accepted"


def probe_terraform_security_list(module):
    text = module.Tree().read("infra/modules/vpc/outputs.tf") + '\nresource "aws_security_group" "x" {}\n'
    assert fails_with(module, module.Analysis, module.Tree().with_files({"infra/modules/vpc/outputs.tf": text})), \
        "unlisted security-boundary Terraform file accepted"


def probe_diff_risk(module):
    path = "infra/modules/developer_access/variables.tf"
    text = module.Tree().read(path) + '\nvariable "extra_cidr" {\n  type = string\n}\n'
    report = module_analysis(module, {path: text}).select(changes(path))
    assert report["full_ci_required"] and report["owner_dispatch_required"], "security-sensitive Terraform change not flagged"


def probe_guard_diff(module):
    path = "scripts/local-workflow/k8s_runtime.py"
    text = module.Tree().read(path).replace("def refuse_operation(name):", "def refuse_operation(name):\n    # operation_not_approved stays\n", 1)
    report = module_analysis(module, {path: text}).select(changes(path))
    assert "real-operation-guard-change" in report["high_risk"] and report["owner_dispatch_required"], "guard change not flagged"


def probe_automatic(module):
    report = module_analysis(module, {}).select(changes("infra/modules/vpc/routing.tf"))
    assert report["full_ci_required"] and report["full_ci_automatic"] and not report["owner_dispatch_required"], \
        "path-filtered change not required and automatic"


def probe_count_selects_suite(module):
    network = counts_text(lambda doc: doc["suites"]["network"].update(native_tests=16))
    selected = module_analysis(module, {COUNTS: network}).select(changes(COUNTS))["selected"]
    assert selected == ["network"], "changed suite selected " + str(selected)


def probe_verdict(module):
    report = {"full_ci_required": True, "owner_dispatch_required": True, "high_risk": {"x": []}}
    assert "OWNER DISPATCH NEEDED" in module.verdict(report), "dispatch verdict missing"


def probe_hard_coded_count(module):
    problems = module.check_workflow("terraform-offline-ci.yml", workflow_text("terraform-offline-ci.yml").replace(
        'result.testsRun != load("toolkit")["tests"]', "result.testsRun != 153"), impact_map())
    assert any("hard-coded-expected-count" in problem for problem in problems), "hard-coded count accepted"


IMPACT, TRIGGER, SAFETY_CHECKS, GENERATOR, MERGE = "impact.py", "full_ci_trigger.py", "safety_checks.py", "pr_safety_workflow.py", "merge_check.py"
COUNTS_MODULE = "expected_counts.py"
MUTATIONS = [
    (IMPACT, 'require(not unmapped, "unmapped_paths', 'require(True or not unmapped, "unmapped_paths', probe_unmapped),
    (IMPACT, 'len(changes) <= self.mapping["max_changed_files"],', 'True,', probe_too_many),
    (IMPACT, 'require(parents[2:3] == [head_sha_expected],', 'require(True,', probe_merge),
    (IMPACT, 'require(len(parents) == 3, "checkout_is_not_a_merge_commit")', 'require(True, "checkout_is_not_a_merge_commit")', probe_merge),
    (IMPACT, 'selected.update(self.mapping["companions"].get(step_id, ()))', 'pass', probe_companion),
    (IMPACT, '                if needed not in selected:', '                if False:', probe_prerequisites),
    (IMPACT, 'for dependent in sorted(self.terraform.all_dependents(config)):', 'for dependent in []:', probe_dependents),
    (IMPACT, 'require(PROVIDER_SOURCE.match(value),', 'require(True,', probe_module_source),
    (IMPACT, 'require(target in self.configurations,', 'require(True,', probe_local_source),
    (IMPACT, '                data |= tree.under(candidate)\n                named |=', '                named |=', probe_dir_inputs),
    (IMPACT, '                named |= {name for name in tree.under(candidate) if name.endswith(".py")}', '                pass', probe_dir_code),
    (IMPACT, 'code |= self.by_stem.get(alias.name.split(".")[0], set())', 'pass', probe_imports),
    (IMPACT, 'return sorted(category for category, patterns in self.mapping["high_risk"].items() if matches(path, patterns))', 'return []', probe_high_risk),
    (IMPACT, 'out.append("[^/]*")', 'out.append(".*")', probe_glob),
    (IMPACT, 'wanted = "success" if step_id in expected else "skipped"', 'wanted = outcome', probe_verify),
    (IMPACT, 'require(not unmapped, "tracked_files_unmapped:"', 'require(True, "tracked_files_unmapped:"', probe_coverage),
    (IMPACT, 'require(set(classified) == set(self.steps.order),', 'require(True,', probe_classification),
    (IMPACT, 'if old != step["raw"] and step["id"] in selectable:', 'if False:', probe_definitions),
    (TRIGGER, 'require(parents[2:3] == [event_head],', 'require(True,', probe_trigger_pr_head),
    (TRIGGER, 'require(owner and env.get("ACTOR") == owner and env.get("TRIGGERING_ACTOR") == owner,', 'require(owner,', probe_trigger_actor),
    (TRIGGER, 'require(ref.startswith("refs/heads/") and ref != "refs/heads/main",', 'require(ref.startswith("refs/heads/"),', probe_trigger_ref),
    (TRIGGER, 'require(expected == run_sha,', 'require(True,', probe_trigger_sha),
    (TRIGGER, 'require(runner(["merge-base", "--is-ancestor", main, "HEAD"])[0] == 0,', 'require(True,', probe_trigger_main),
    (TRIGGER, 'raise TriggerError("event_not_allowed_for_full_ci:" + event)', 'return record', probe_trigger_event),
    (TRIGGER, 'require(head == run_sha, "checkout_is_not_the_run_commit")', 'require(True, "checkout_is_not_the_run_commit")', probe_trigger_checkout),
    (TRIGGER, 'require(reason in REASONS,', 'require(True,', probe_trigger_reason),
    (SAFETY_CHECKS, 'if data.get("permissions") != {"contents": "read"}:', 'if False:', probe_permissions),
    (SAFETY_CHECKS, 'if not PINNED.match(uses):', 'if False:', probe_pinned),
    (SAFETY_CHECKS, 'elif set(on) != ALLOWED_TRIGGERS[name]:', 'elif False:', probe_triggers),
    (SAFETY_CHECKS, 'if push.get("branches") != ["main"] or push.get("paths") != REHEARSAL_PATHS:', 'if False:', probe_rehearsal),
    (SAFETY_CHECKS, 'or pull.get("paths") != expected:', 'or False:', probe_high_risk_paths),
    (SAFETY_CHECKS, 'if pull != {"branches": ["main"]}:', 'if False:', probe_every_pr),
    (SAFETY_CHECKS, '.get("persist-credentials") is not False:', '.get("persist-credentials") is None and False:', probe_persist),
    (SAFETY_CHECKS, '        if pattern.search(text):', '        if False:', probe_forbidden),
    (SAFETY_CHECKS, 'not 0 < job["timeout-minutes"] <= 60', 'False', probe_timeout),
    (SAFETY_CHECKS, 'if job.get("name") != full["job_name"] or job.get("timeout-minutes") != full["timeout_minutes"]:', 'if False:', probe_check_name),
    (SAFETY_CHECKS, '            if pattern.search(line):', '            if False:', probe_secret_scan),
    (SAFETY_CHECKS, 'if SECRET_NAMES.search(name) and', 'if False and', probe_secret_names),
    (SAFETY_CHECKS, 'if process.returncode != 1 or ("Refused (" + expected + ")") not in output:', 'if process.returncode not in (0, 1):', probe_guards),
    (SAFETY_CHECKS, '        ast.parse(text, filename=path)', '        pass', probe_syntax),
    (SAFETY_CHECKS, '        json.loads(text)', '        pass', probe_syntax),
    (SAFETY_CHECKS, '        list(yaml.safe_load_all(text))', '        pass', probe_syntax),
    (SAFETY_CHECKS, '        if process.returncode:\n            raise ValueError', '        if False:\n            raise ValueError', probe_syntax),
    (GENERATOR, 'return "\\n".join([lines[0], "        if: " + condition] + lines[1:])', 'return raw', probe_generator_condition),
    (GENERATOR, '        if step["id"] in full_only:\n            continue', '        if False:\n            continue', probe_generator_full_only),
    (MERGE, 'require(parents[1:2] == [base], "squash_parent_is_not_the_reviewed_base_main")', 'require(True, "squash_parent_is_not_the_reviewed_base_main")', probe_merge_parent),
    (MERGE, 'require(squash_tree == verified_tree,', 'require(True,', probe_merge_tree),
    (MERGE, 'require(merged == verified_tree,', 'require(True,', probe_merge_evidence),
    (MERGE, 'require(git("rev-parse", reviewed_head + "^{tree}") == verified_tree,', 'require(True,', probe_merge_dispatch_tree),
    (MERGE, 'require(runner(["merge-base", "--is-ancestor", base, reviewed_head])[0] == 0,', 'require(True,', probe_merge_dispatch_base),
    (TRIGGER, 'require(head.get("ref") == branch,', 'require(True,', probe_trigger_binding),
    (TRIGGER, 'require(head.get("sha") == expected, "dispatch_pull_request_head_mismatch")', 'require(True, "dispatch_pull_request_head_mismatch")', probe_trigger_binding),
    (TRIGGER, 'require(base.get("ref") == "main", "dispatch_pull_request_base_not_main")', 'require(True, "dispatch_pull_request_base_not_main")', probe_trigger_binding),
    (TRIGGER, 'require(pull.get("state") == "open",', 'require(True,', probe_trigger_binding),
    (TRIGGER, 'require(pull != "not_found",', 'require(True,', probe_trigger_not_found),
    (TRIGGER, 'if pull is None:\n        return NOT_VERIFIED', 'if pull is None:\n        return "VERIFIED_BY_PUBLIC_API"', probe_trigger_unverified),
    (COUNTS_MODULE, 'require(not missing and not unknown,', 'require(True,', probe_counts_schema),
    (COUNTS_MODULE, 'require(isinstance(values, dict) and sorted(values) == sorted(keys),', 'require(isinstance(values, dict),', probe_counts_schema),
    (COUNTS_MODULE, 'return type(value) is int and value > 0', 'return isinstance(value, (int, float, str)) or value is None', probe_counts_values),
    (COUNTS_MODULE, 'require(isinstance(record["reason"], str) and len(record["reason"].strip()) >= 20,', 'require(True,', probe_counts_reason),
    (COUNTS_MODULE, '(approved if (suite, key, old, value) in records else unapproved).append(entry)', 'approved.append(entry)', probe_counts_reduction),
    (IMPACT, 'require(not unapproved, "expected_count_decrease_without_approved_reductions_record:"', 'require(True, "expected_count_decrease_without_approved_reductions_record:"', probe_select_unapproved_decrease),
    (IMPACT, 'risks["expected-count-reduction"].append(path)', 'pass', probe_select_approved_decrease),
    (IMPACT, 'steps |= self.suite_steps[suite]', 'pass', probe_count_selects_suite),
    (IMPACT, 'inputs.discard(COUNTS_FILE)', 'pass', probe_count_increase_is_normal),
    (IMPACT, 'require(set(self.suite_steps) == set(expected_counts.SCHEMA),', 'require(True,', probe_counts_suites_loaded),
    (IMPACT, 'require(computed == mapping["high_risk"]["terraform-security-boundary"],', 'require(True,', probe_terraform_security_list),
    (IMPACT, 'if lines is None or any(re.search(keywords, line, re.I) for line in lines):', 'if False:', probe_diff_risk),
    (IMPACT, 'automatic = any(matches(path, self.full_ci_paths()) for path in changed_paths)', 'automatic = True', probe_diff_risk),
    (IMPACT, '"owner_dispatch_required": required and not automatic}', '"owner_dispatch_required": False}', probe_guard_diff),
    (IMPACT, 'required = bool(risks)', 'required = False', probe_automatic),
    (IMPACT, '    if report["owner_dispatch_required"]:', '    if False:', probe_verdict),
    (SAFETY_CHECKS, 'if HARD_CODED_COUNT.search(text):', 'if False:', probe_hard_coded_count),
]


def mutant(filename, old, new):
    source = (HERE / filename).read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(f"mutation target must occur exactly once in {filename}: {old!r}")
    module = types.ModuleType("mutant_" + filename[:-3])
    module.__file__ = str(HERE / filename)
    exec(compile(source.replace(old, new), module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


class ImpactTests(unittest.TestCase):
    def test_glob_semantics(self):
        probe_glob(impact)
        self.assertTrue(impact.matches(".github/workflows/x.yml", [".github/**"]))
        self.assertTrue(impact.matches("infra/iam.tf", ["infra/**/iam.tf"]))
        self.assertTrue(impact.matches("docs/.gitkeep", ["**/.gitkeep"]))

    def test_map_is_consistent_and_covers_every_tracked_file(self):
        self.assertEqual(analysis().coverage(), len(tree().files))
        self.assertEqual(len(analysis().terraform.configurations), 22)

    def test_documentation_runs_always_on_checks_only(self):
        report = analysis().select(changes("docs/deployment-configuration.md", "AGENTS.md", "infra/README.md"))
        self.assertEqual(report["selected"], [])
        self.assertFalse(report["full_ci_required"])

    def test_unmapped_and_oversized_changes_fail_closed(self):
        self.assertIn("unmapped_paths", fails(analysis().select, changes("new-top-level/file.txt", "docs/a.md")))
        self.assertIn("too_many_changed_files", fails(analysis().select, changes(*["docs/x%d.md" % index for index in range(301)])))
        probe_coverage(impact)

    def test_module_change_selects_sourcing_roots_and_prerequisites(self):
        report = analysis().select(changes("infra/modules/vpc/main.tf"))
        for step in ("vpc", "network", "committed_values", "dev", "platform", "api", "tfstate", "registry", "developer_access"):
            self.assertIn(step, report["selected"])
        self.assertEqual(report["selected"], [step for step in analysis().steps.order if step in report["selected"]])
        probe_dependents(impact)
        probe_companion(impact)
        probe_prerequisites(impact)

    def test_test_module_source_counts_as_dependency(self):
        steps, reasons = analysis().map_file("infra/modules/iam_account_policies/main.tf")
        self.assertIn("iam", steps)
        self.assertIn("sourced by infra/modules/iam_access", reasons)

    def test_markdown_in_a_configuration_is_not_terraform(self):
        _steps, reasons = analysis().map_file("infra/modules/vpc/README.md")
        self.assertFalse(any(reason.startswith("configuration ") for reason in reasons))

    def test_local_workflow_changes_select_their_tests_only(self):
        self.assertEqual(analysis().select(changes("scripts/local-workflow/k8s_runtime_apply.py"))["selected"],
                         ["kubernetes_runtime", "kubernetes_runtime_plan"])
        self.assertEqual(analysis().select(changes("scripts/local-workflow/mirror_images.py"))["selected"], ["image_mirror"])
        probe_imports(impact)
        probe_dir_inputs(impact)

    def test_high_risk_paths_require_full_ci(self):
        report = analysis().select(changes("scripts/local-workflow/preflight.py", ".github/workflows/terraform-offline-ci.yml"))
        self.assertTrue(report["full_ci_required"])
        self.assertEqual(sorted(report["high_risk"]), ["ci", "real-operation-guard-change", "security-boundary"])
        probe_high_risk(impact)

    def test_unsupported_module_sources_fail_closed(self):
        probe_module_source(impact)
        probe_local_source(impact)
        base = tree().with_files({"infra/modules/vpc/extra.tf": 'module "x" {\n  source = "git::https://example.invalid/m.git"\n}\n'})
        self.assertIn("unsupported_module_source", fails(impact.Terraform, base, impact.load_map(tree())))
        self.assertTrue(impact.PROVIDER_SOURCE.match("registry.terraform.io/hashicorp/aws"))

    def test_map_errors_fail_closed(self):
        probe_classification(impact)
        cases = {
            "map_references_unknown_step": lambda mapping: mapping["rules"][0]["steps"].append("nonexistent"),
            "prerequisite_after_step": lambda mapping: mapping["prerequisites"].update(dev=["committed_values"]),
            "configurations_do_not_match_map": lambda mapping: mapping["configurations"].pop("infra/modules/vpc"),
            "step_classified_twice": lambda mapping: mapping["steps"]["always"].append("dev"),
        }
        for message, edit in cases.items():
            self.assertIn(message, fails(impact.Analysis, with_map(edit)), message)
        renamed = tree().read(FULL).replace("        id: r1_r2_guards\n", "")
        self.assertIn("full_ci_step_without_id", fails(impact.Analysis, tree().with_files({FULL: renamed})))
        contracts = tree().read(".github/workflows/aws-emulator-contracts.yml").replace("Evidence ledger check", "Ledger check")
        self.assertIn("contracts_steps_do_not_match_map", fails(impact.Analysis, tree().with_files({".github/workflows/aws-emulator-contracts.yml": contracts})))

    def test_changed_step_definitions_are_selected(self):
        probe_definitions(impact)

    def test_merge_commit_is_verified(self):
        probe_merge(impact)
        with mock.patch.object(impact, "git", return_value=f"{SHA_A} {SHA_B} {SHA_C}\n"):
            self.assertEqual(impact.merge_changes(SHA_C), (SHA_B, SHA_A))

    def test_outcome_verification(self):
        probe_verify(impact)
        self.assertIn("impact_report_missing", fails(impact.verify, "/nonexistent/report.json", SAFETY, {}))


class GeneratorTests(unittest.TestCase):
    def test_committed_workflow_is_generated_and_gated(self):
        text = pr_safety_workflow.generate()
        self.assertEqual(text, (REPO / SAFETY).read_text(encoding="utf-8"))
        probe_generator_condition(pr_safety_workflow)
        probe_generator_full_only(pr_safety_workflow)
        self.assertLess(text.index("id: emulator_contracts_ledger_check"), text.index("id: storage_final"))
        self.assertIn("selectable_step_has_own_if", fails(pr_safety_workflow.with_condition, "      - name: x\n        if: always()", "c", "x"))


class TriggerTests(unittest.TestCase):
    def test_allowed_triggers(self):
        env, run = pull_request_case()
        record = full_ci_trigger.verify(env, run, fetch_of(None))
        self.assertEqual((record["head_sha"], record["tested_tree"], record["evidence"]), (SHA_C, SHA_D, "pull_request"))
        env, run = dispatch_case()
        record = full_ci_trigger.verify(env, run, fetch_of(good_pull()))
        self.assertEqual((record["pull_request"], record["head_sha"], record["reason"], record["pull_request_binding"]),
                         (97, SHA_C, "owner-milestone", "VERIFIED_BY_PUBLIC_API"))

    def test_refusals(self):
        for probe in (probe_trigger_pr_head, probe_trigger_actor, probe_trigger_ref, probe_trigger_sha, probe_trigger_main,
                      probe_trigger_event, probe_trigger_checkout, probe_trigger_reason, probe_trigger_binding, probe_trigger_unverified, probe_trigger_not_found):
            probe(full_ci_trigger)
        for env in ({"BASE_REF": "develop"}, {"PR_HEAD_SHA": "short"}):
            self.assertTrue(fails_trigger(full_ci_trigger, *pull_request_case(env=env)), env)
        for env in ({"REF": "refs/tags/v1"}, {"INPUT_PR": "0"}, {"INPUT_SHA": "A" * 40}, {"OWNER": ""}):
            self.assertTrue(fails_trigger(full_ci_trigger, *dispatch_case(env=env)), env)
        self.assertTrue(fails_trigger(full_ci_trigger, *pull_request_case(answers={"rev-list --parents -n 1 HEAD": (0, f"{SHA_A} {SHA_B}")})))


class MergeCheckTests(unittest.TestCase):
    def test_tree_and_parent(self):
        self.assertEqual(merge_check.verify(SHA_A, SHA_C, SHA_B, TREE_V, "pull_request", merge_runner())["tree"], TREE_V)
        self.assertEqual(merge_check.verify(SHA_A, SHA_C, SHA_B, TREE_V, "dispatch", merge_runner())["evidence"], "dispatch")
        for probe in (probe_merge_parent, probe_merge_tree, probe_merge_evidence, probe_merge_dispatch_tree, probe_merge_dispatch_base):
            probe(merge_check)
        self.assertTrue(fails_merge(merge_check, runner_for({f"rev-list --parents -n 1 {SHA_A}": (0, f"{SHA_A} {SHA_B} {SHA_C}")})))
        self.assertIn("evidence_kind_invalid", fails(merge_check.verify, SHA_A, SHA_C, SHA_B, TREE_V, "recomputed", merge_runner()))


class SafetyCheckTests(unittest.TestCase):
    def test_repository_workflows_secrets_and_guards_pass(self):
        self.assertEqual(safety_checks.check_workflows(), [])
        self.assertEqual(safety_checks.check_secrets(), [])
        self.assertEqual(safety_checks.check_guards(REPO, safety_checks.GUARD_COMMANDS[:2] + safety_checks.GUARD_COMMANDS[-3:]), [])

    def test_workflow_refusals(self):
        for probe in (probe_permissions, probe_pinned, probe_triggers, probe_rehearsal, probe_high_risk_paths, probe_every_pr,
                      probe_persist, probe_forbidden, probe_timeout, probe_check_name):
            probe(safety_checks)
        for name, old, new, label in (
                ("pr-safety-ci.yml", "runs-on: ubuntu-24.04", "runs-on: self-hosted", ":runner"),
                ("pr-safety-ci.yml", "cancel-in-progress: false", "cancel-in-progress: true", "cancelling-concurrency"),
                ("aws-emulator-contracts.yml", "  pull_request:\n", "  pull_request_target:\n", "privileged-trigger"),
                ("pr-safety-ci.yml", "      - name: Check changed files", "      - uses: actions/cache@0123456789abcdef0123456789abcdef01234567\n"
                 "      - name: Check changed files", "persistence-or-push"),
                ("terraform-offline-ci.yml", "      expected_head_sha:\n", "      expected_sha:\n", "dispatch-inputs"),
                ("pr-safety-ci.yml", "    runs-on: ubuntu-24.04\n", "    runs-on: ubuntu-24.04\n    if: false\n", "job-level-if")):
            probe_workflow(safety_checks, name, old, new, label)

    def test_secret_scan(self):
        probe_secret_scan(safety_checks)
        probe_secret_names(safety_checks)
        token = "ghp_" + "A" * 36
        self.assertTrue(safety_checks.scan_text("x", "token: " + token))
        self.assertTrue(safety_checks.scan_text("x", "aws_secret_access_key = " + "A1b2" * 10))
        for clean in ("aws_secret_access_key=DUMMY_SECRET", r"re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_')",
                      "('-----BEGIN RSA PRIVATE KEY', 'entry-private-key')", "AKIA_EXAMPLE"):
            self.assertEqual(safety_checks.scan_text("x", clean), [], clean)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(safety_checks.check_secrets(Path(folder), [".env.example"]), [])

    def test_guards_and_syntax(self):
        probe_guards(safety_checks)
        probe_syntax(safety_checks)
        safety_checks.syntax_problem("ok.py", b"x = 1\n")
        safety_checks.syntax_problem("ok.yml", b"a: [1]\n---\nb: 2\n")

    def test_changed_files_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def run(*args):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            run("init", "-q")
            run("config", "user.email", "ci@example.invalid")
            run("config", "user.name", "ci")
            (root / "a.txt").write_text("a\n")
            run("add", ".")
            run("commit", "-q", "-m", "base")
            (root / "bad.py").write_text("def (:\n")
            (root / "space.txt").write_text("trailing \n")
            (root / "ok.json").write_text("{}\n")
            run("add", ".")
            run("commit", "-q", "-m", "head")
            problems, count = safety_checks.check_changed("HEAD~1", "HEAD", root)
        self.assertEqual(count, 3)
        self.assertTrue(any(problem.startswith("bad.py:syntax") for problem in problems))
        self.assertTrue(any(problem.startswith("whitespace:") for problem in problems))


class ExpectedCountsTests(unittest.TestCase):
    def test_committed_counts_are_valid_and_exact(self):
        self.assertEqual(expected_counts.load("k8s_runtime_apply_tests"), counts_doc()["suites"]["k8s_runtime_apply_tests"])
        self.assertEqual(sorted(counts_doc()["suites"]), sorted(expected_counts.SCHEMA))
        self.assertIn("counts_unknown_suite", fails(expected_counts.load, "nonexistent"))
        self.assertIn("counts_unparsable", fails(expected_counts.parse, "{"))
        self.assertIn("counts_top_level_fields", fails(expected_counts.validate, {**counts_doc(), "generated_from_run": 1}))
        for probe in (probe_counts_schema, probe_counts_values, probe_counts_reason, probe_counts_reduction):
            probe(expected_counts)

    def test_count_changes_select_only_their_steps(self):
        probe_count_increase_is_normal(impact)
        probe_count_selects_suite(impact)
        probe_counts_suites_loaded(impact)
        probe_hard_coded_count(safety_checks)

    def test_decreases_fail_closed_unless_recorded(self):
        probe_select_unapproved_decrease(impact)
        probe_select_approved_decrease(impact)
        self.assertIn("counts_file_deleted", fails(analysis().select, [("D", COUNTS)]))


class HighRiskTests(unittest.TestCase):
    def test_security_boundary_terraform_starts_full_ci(self):
        for path in ("infra/modules/developer_access/main.tf", "infra/modules/tfstate_bucket/main.tf", "infra/modules/vpc/routing.tf"):
            report = pair({}).select(changes(path))
            self.assertIn("terraform-security-boundary", report["high_risk"], path)
            self.assertTrue(report["full_ci_automatic"] and not report["owner_dispatch_required"], path)
        probe_automatic(impact)
        probe_terraform_security_list(impact)

    def test_security_sensitive_lines_need_an_owner_dispatch(self):
        probe_diff_risk(impact)
        probe_guard_diff(impact)
        probe_verdict(impact)

    def test_normal_changes_need_no_full_ci(self):
        outputs = "infra/modules/vpc/outputs.tf"
        cases = {outputs: tree().read(outputs) + "\n# Outputs are documented in the README.\n",
                 "scripts/local-workflow/k8s_runtime_apply.py": apply_fake_change(),
                 "scripts/local-workflow/test_k8s_runtime_apply.py": tree().read("scripts/local-workflow/test_k8s_runtime_apply.py")
                 + "\n# subprocess and operation_not_approved appear in tests only\n"}
        for path, text in cases.items():
            report = pair({path: text}).select(changes(path))
            self.assertFalse(report["full_ci_required"], (path, report["high_risk"]))
            self.assertIn("NOT REQUIRED", impact.verdict(report))

    def test_ci_logic_changes_start_full_ci(self):
        for path in ("scripts/ci/impact.py", "scripts/ci/expected_counts.py", ".github/workflows/terraform-offline-ci.yml"):
            report = pair({}).select(changes(path))
            self.assertTrue(report["full_ci_required"] and report["full_ci_automatic"], path)


class MutationTests(unittest.TestCase):
    def test_each_guard_mutation_is_detected(self):
        self.assertEqual(len(MUTATIONS), EXPECTED_MUTATIONS)
        undetected = []
        for filename, old, new, probe in MUTATIONS:
            module = mutant(filename, old, new)
            try:
                probe(module)
            except AssertionError:
                continue
            undetected.append(f"{filename}: {old[:70]!r}")
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful() or result.skipped or result.testsRun != EXPECTED_TESTS or len(MUTATIONS) != EXPECTED_MUTATIONS:
        raise SystemExit("CI policy tooling tests failed, skipped or changed the reviewed counts.")
