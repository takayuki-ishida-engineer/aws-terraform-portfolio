#!/usr/bin/env python3
"""Offline tests for the fake-only apply engine of the first two stages (item 6c-B3b-Apply-A).

Nothing here reaches a cluster or AWS. The bundle is one real render of the
synthetic fixture with the pinned Helm (``K8S_RUNTIME_HELM``, required). Each case
runs ``k8s_runtime_apply.apply_stages`` against a ``FakeAdapter`` and a
``FakeClock``, with a receipt store in a temporary directory outside the
repository.

``MutationTests`` removes one guard at a time from ``k8s_runtime_apply.py`` (and
the D13 hook in ``k8s_runtime_receipt.py``). The matching scenario must detect each
one.
"""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_runtime  # noqa: E402
import k8s_runtime_apply  # noqa: E402
import k8s_runtime_receipt  # noqa: E402
import preflight  # noqa: E402

import common  # noqa: E402  (kubernetes/tools, on sys.path through k8s_runtime)
import render  # noqa: E402

FIXTURE = preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json"
HELM = os.environ.get("K8S_RUNTIME_HELM", "")
KUBE_SYSTEM_UID = "11111111-2222-4333-8444-555555555555"
CACHE = {}


def bundle():
    if "objects" not in CACHE:
        if not HELM or not Path(HELM).is_file():
            raise AssertionError("K8S_RUNTIME_HELM must point to the pinned Helm binary (install_helm.py)")
        document = common.parse(FIXTURE.read_text())
        objects, evidence = render.render(document, HELM, True)
        with mock.patch.object(render, "render", return_value=(copy.deepcopy(objects), copy.deepcopy(evidence))):
            report = k8s_runtime.plan(FIXTURE, HELM, True)
        scope = document["controller_identity"]
        CACHE.update(objects=objects, report=report,
                     arn="arn:aws:eks:" + scope["scope"]["region"] + ":" + scope["scope"]["account_id"] + ":cluster/"
                     + scope["cluster_name"])
    return copy.deepcopy(CACHE["objects"]), copy.deepcopy(CACHE["report"]), CACHE["arn"]


def sha(objects):
    return hashlib.sha256(json.dumps(objects, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Mods(types.SimpleNamespace):
    pass


def real_mods():
    return Mods(apply=k8s_runtime_apply, receipt=k8s_runtime_receipt)


class Run:
    """A fresh store, fake clock and fake adapter for the first two stages."""

    def __init__(self, mods, objects=None, report=None, store_manifest=None, kube_uid=KUBE_SYSTEM_UID):
        self.mods = mods
        base_objects, base_report, self.arn = bundle()
        self.objects = objects if objects is not None else base_objects
        self.report = report if report is not None else base_report
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-apply-"))
        os.chmod(self.tmp, 0o700)
        self.plan = mods.receipt.Plan.from_report(self.report)
        self.fp = mods.receipt.fingerprint(self.arn, KUBE_SYSTEM_UID)
        self.store = self.new_store(store_manifest)
        self.clock = mods.apply.FakeClock()
        self.members = {s: [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|")))
                            for k in self.plan.members[s]] for s in ("namespaces", "base")}
        scope = [k for s in ("namespaces", "base") for k in self.plan.members[s]]
        self.adapter = mods.apply.FakeAdapter(self.clock, kube_uid, scope)

    def new_store(self, store_manifest=None):
        return self.mods.receipt.Store(self.tmp / "state", self.fp, self.report["project"],
                                       store_manifest or self.report["manifest_sha256"], self.report["input_sha256"],
                                       self.plan)

    def run(self, through="base", manifest=None, input_sha=None, adapter=None, store=None):
        try:
            return self.mods.apply.apply_stages(self.report, self.objects, store or self.store,
                                                adapter or self.adapter, self.clock,
                                                manifest or self.report["manifest_sha256"],
                                                input_sha or self.report["input_sha256"], self.arn, through)
        except Exception as raised:  # noqa: BLE001 - a mutant may crash; that is a failed outcome, not a pass
            return {"exit_code": "crash", "status": type(raised).__name__, "reason": str(raised), "stages": []}

    def journal(self):
        path = self.store.dir / "journal.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def applies(self):
        return [c for c in self.adapter.calls if c[0] == "apply"]

    def key(self, stage, index):
        return k8s_runtime_receipt.key_of(self.members[stage][index])

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@contextlib.contextmanager
def run_for(mods, **kwargs):
    run = Run(mods, **kwargs)
    try:
        yield run
    finally:
        run.cleanup()


def outcome(result):
    return result["exit_code"], result["status"], result["reason"]


def crd_key(run):
    return next(k8s_runtime_receipt.key_of(i) for i in run.members["base"] if i["kind"] == "CustomResourceDefinition")


# ---- scenarios -----------------------------------------------------------------------------------------------------

def scenario_success_is_deferred(case, mods):
    with run_for(mods) as r:
        result = r.run()
        case.assertEqual(outcome(result), (6, "APPLIED_WITH_DEFERRED", None))
        case.assertEqual([(s["name"], s["final_acceptance"]) for s in result["stages"]],
                         [("namespaces", "PASS"), ("base", "DEFERRED")])
        case.assertEqual(result["stages"][1]["deferred"][0]["resolved_by"], "istiod")
        case.assertEqual(result["runtime_final_acceptance"], "NOT_REACHED")
        types_ = [rec["type"] for rec in r.journal()]
        case.assertEqual((types_.count("INTENT"), types_.count("RESULT"), types_.count("STAGE_DONE")), (18, 18, 2))
        case.assertEqual(len(r.applies()), 18)
        case.assertEqual(sum(1 for c in r.adapter.calls if c[0] == "dry_run"), 18)
        case.assertTrue(all(o["metadata"]["managedFields"][-1]["manager"] == "test-k8s-runtime"
                            for k, o in r.adapter.objects.items() if not k.endswith("|kube-system")))


def scenario_namespaces_only(case, mods):
    with run_for(mods) as r:
        result = r.run(through="namespaces")
        case.assertEqual(outcome(result), (0, "STAGES_ACCEPTED", None))
        case.assertEqual([(s["name"], s["final_acceptance"]) for s in result["stages"]], [("namespaces", "PASS")])
        case.assertEqual(len(r.applies()), 2)


def scenario_rerun_reverifies(case, mods):
    with run_for(mods) as r:
        r.run()
        records = len(r.journal())
        r.adapter.calls.clear()
        result = r.run(store=r.new_store())
        case.assertEqual(outcome(result), (6, "APPLIED_WITH_DEFERRED", None))
        case.assertEqual(len(r.journal()), records)
        case.assertEqual(r.applies(), [])
        case.assertEqual([s["applied"] for s in result["stages"]], [False, False])


def scenario_status_manager_allowed(case, mods):
    with run_for(mods) as r:
        r.run()
        r.adapter.objects[crd_key(r)]["metadata"]["managedFields"].append(
            {"manager": "kube-apiserver", "operation": "Update", "subresource": "status", "fieldsV1": {"f:status": {}}})
        case.assertEqual(r.run(store=r.new_store())["exit_code"], 6)


def scenario_pins(case, mods):
    with run_for(mods) as r:
        case.assertEqual(outcome(r.run(manifest="f" * 64))[2], "sha_mismatch")
        case.assertEqual(outcome(r.run(input_sha="abc"))[2], "sha_pin_invalid")
        case.assertEqual(r.adapter.calls, [])
        case.assertEqual(r.journal(), [])


def scenario_bundle_changed(case, mods):
    with run_for(mods, store_manifest="c" * 64) as r:
        case.assertEqual(outcome(r.run()), (2, "STOPPED", "bundle_changed"))
        case.assertEqual(r.journal(), [])


def scenario_objects_match_plan(case, mods):
    objects, report, _ = bundle()
    objects[0]["metadata"].setdefault("labels", {})["tampered"] = "true"
    with run_for(mods, objects=objects, report=report) as r:
        case.assertEqual(outcome(r.run()), (2, "STOPPED", "objects_do_not_match_plan"))
        case.assertEqual(r.applies(), [])


def scenario_fingerprint(case, mods):
    with run_for(mods, kube_uid="99999999-2222-4333-8444-555555555555") as r:
        case.assertEqual(outcome(r.run()), (2, "STOPPED", "fingerprint_mismatch"))
        case.assertEqual(r.journal(), [])


def scenario_gates(case, mods):
    with run_for(mods) as r:
        impostor = types.SimpleNamespace(is_fake=True, calls=[])
        case.assertEqual(outcome(r.run(adapter=impostor)), (1, "REFUSED", "real_adapter_not_approved"))
        case.assertEqual(outcome(r.run(through="controller")), (1, "REFUSED", "stage_not_approved:controller"))
        case.assertEqual(r.journal(), [])
        with case.assertRaises(mods.apply.AdapterError):
            mods.apply.RealAdapter()


def scenario_plan_order(case, mods):
    objects, report, _ = bundle()
    report["stages"][0], report["stages"][1] = report["stages"][1], report["stages"][0]
    with run_for(mods, objects=objects, report=report) as r:
        case.assertEqual(outcome(r.run()), (2, "STOPPED", "plan_stage_order"))


def scenario_receipt_damage(case, mods):
    with run_for(mods) as r:
        r.run(through="namespaces")
        (r.store.dir / "journal.jsonl").write_text("corrupt\n")
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "receipt:journal_corrupt:not_json")
    with run_for(mods) as r:
        r.run(through="namespaces")
        os.unlink(r.store.dir / "journal.jsonl")
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "receipt:journal_missing")


def scenario_crash_before_apply(case, mods):
    with run_for(mods) as r:
        first = r.key("namespaces", 0)
        r.adapter.apply_timeouts.add(first)
        case.assertEqual(outcome(r.run()), (3, "UNDETERMINED", "api_timeout"))
        case.assertEqual(r.journal()[-1]["type"], "INTENT")
        r.adapter.apply_timeouts.clear()
        case.assertEqual(r.run(store=r.new_store())["exit_code"], 6)
        closed = [rec for rec in r.journal() if rec["type"] == "RESULT" and rec["seq"] == 1]
        case.assertEqual([rec["outcome"] for rec in closed], ["failed"])


def scenario_crash_after_apply(case, mods):
    with run_for(mods) as r:
        first = r.key("namespaces", 0)
        r.adapter.post_apply_timeouts.add(first)
        case.assertEqual(outcome(r.run())[2], "api_timeout")
        r.adapter.post_apply_timeouts.clear()
        case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "quarantined"))
        case.assertEqual(r.journal()[-1]["type"], "QUARANTINE")
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "quarantined")
        case.assertEqual(sum(1 for rec in r.journal() if rec["type"] == "QUARANTINE"), 1)


def scenario_uid_changed(case, mods):
    with run_for(mods) as r:
        r.run()
        r.adapter.objects[r.key("namespaces", 1)]["metadata"]["uid"] = "00000000-0000-4000-9000-0000000000ff"
        case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "uid_changed"))


def scenario_foreign_owner(case, mods):
    with run_for(mods) as r:
        manifest = r.objects[0]
        foreign = copy.deepcopy(manifest)
        foreign["metadata"].update(uid="00000000-0000-4000-9000-0000000000aa", managedFields=[
            {"manager": "kubectl", "operation": "Apply", "fieldsV1": {"f:metadata": {}}}])
        foreign["status"] = {"phase": "Active"}
        r.adapter.objects[r.key("namespaces", 0)] = foreign
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "foreign_owner"))
        case.assertEqual(r.applies(), [])


def scenario_foreign_field(case, mods):
    with run_for(mods) as r:
        r.run()
        r.adapter.objects[crd_key(r)]["metadata"]["managedFields"].append(
            {"manager": "kubectl-edit", "operation": "Update", "fieldsV1": {"f:spec": {}}})
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "foreign_field")
    with run_for(mods) as r:
        r.run()
        validator = next(k8s_runtime_receipt.key_of(i) for i in r.members["base"]
                         if i["kind"] == "ValidatingWebhookConfiguration")
        r.adapter.objects[validator]["metadata"]["managedFields"].append(
            {"manager": "pilot-discovery", "operation": "Update", "fieldsV1": {"f:webhooks": {}}})
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "ownership_not_verified")


def scenario_conflict(case, mods):
    with run_for(mods) as r:
        r.adapter.conflicts.add(crd_key(r))
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "field_conflict"))
        last = r.journal()[-1]
        case.assertEqual((last["type"], last.get("outcome")), ("RESULT", "failed"))
        case.assertNotIn(crd_key(r), r.adapter.objects)
        case.assertFalse(any(rec["type"] == "STAGE_DONE" and rec["stage"] == "base" for rec in r.journal()))


def scenario_stage_order(case, mods):
    with run_for(mods) as r:
        engine = mods.apply.Engine(r.report, r.objects, r.store, r.adapter, r.clock, r.arn)
        with case.assertRaises(mods.apply.ApplyStop) as raised:
            engine.pre_apply("base", set())
        case.assertEqual(raised.exception.reason, "pre_apply_not_verified:namespaces_not_accepted")


def scenario_crd_timeout(case, mods):
    with run_for(mods) as r:
        r.adapter.crd_ready_after[crd_key(r)] = None
        start = r.clock.now()
        case.assertEqual(outcome(r.run()), (5, "READINESS_TIMEOUT", "crd_not_established"))
        elapsed = r.clock.now() - start
        case.assertGreaterEqual(elapsed, 120)
        case.assertLess(elapsed, 120 + 2 * 20 + 10)
        case.assertFalse(any(rec["type"] == "STAGE_DONE" and rec["stage"] == "base" for rec in r.journal()))
    with run_for(mods) as r:
        r.adapter.crd_ready_after[crd_key(r)] = 30
        case.assertEqual(r.run()["exit_code"], 6)


def scenario_api_timeout(case, mods):
    with run_for(mods) as r:
        r.adapter.latency[r.key("namespaces", 0)] = 25
        case.assertEqual(outcome(r.run()), (3, "UNDETERMINED", "api_timeout"))
    with run_for(mods) as r:
        r.adapter.latency[r.key("namespaces", 0)] = 15
        case.assertEqual(r.run()["exit_code"], 6)


def tamper_c1(objects):
    validator = next(o for o in objects if o["kind"] == "ValidatingWebhookConfiguration"
                     and o["metadata"]["name"] == "istiod-default-validator")
    validator["webhooks"][0]["clientConfig"]["caBundle"] = ""


def scenario_c1(case, mods):
    objects, report, _ = bundle()
    tamper_c1(objects)
    report["manifest_sha256"] = sha(objects)
    with run_for(mods, objects=objects, report=report) as r:
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "istio_cabundle_ownership_unsafe"))
        base_keys = set(r.plan.members["base"])
        case.assertFalse(any(c[1] in base_keys for c in r.adapter.calls if c[0] in ("apply", "dry_run")))
        case.assertEqual(mods.apply.c1_violations(objects), ["istiod-default-validator"])


def scenario_deferred_never_pass(case, mods):
    with run_for(mods) as r:
        result = r.run()
        case.assertEqual(result["exit_code"], 6)
        case.assertNotEqual(result["status"], "STAGES_ACCEPTED")
        case.assertEqual(result["stages"][-1]["final_acceptance"], "DEFERRED")


def scenario_dry_run(case, mods):
    with run_for(mods) as r:
        r.adapter.dry_run[r.key("namespaces", 0)] = (403, 'admission webhook "validation.istio.io" denied the request')
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "dry_run:webhook_denied:validation.istio.io"))
        case.assertEqual(r.applies(), [])
    with run_for(mods) as r:
        r.adapter.dry_run[crd_key(r)] = (400, "admission webhook has side effects and does not support dry run")
        case.assertEqual(outcome(r.run())[2], "dry_run:dry_run_unsupported")


def scenario_classify(case, mods):
    c = mods.apply.classify_admission
    case.assertEqual(c(201, ""), "allowed")
    case.assertEqual(c(403, 'admission webhook "vtargetgroupbinding.elbv2.k8s.aws" denied the request'),
                     "webhook_denied:vtargetgroupbinding.elbv2.k8s.aws")
    case.assertEqual(c(403, "ValidatingAdmissionPolicy 'test-no-lb-service' with binding 'test-no-lb-service' denied "
                            "request: This namespace permits ClusterIP Services"), "vap_denied:test-no-lb-service")
    case.assertEqual(c(403, 'User "x" cannot create resource "services"'), "authz_denied")
    case.assertEqual(c(403, "forbidden for an unknown reason"), "unknown")
    case.assertEqual(c(422, "Invalid value"), "schema_invalid")
    case.assertEqual(c(500, 'Internal error: failed calling webhook "validation.istio.io"'), "webhook_unreachable")
    case.assertEqual(c(500, "boom"), "unknown")
    case.assertFalse(mods.apply.probe_passes("vap_denied:test-target-registration", 403,
                                             'User "x" cannot create resource "targetgroupbindings"'))
    case.assertTrue(mods.apply.probe_passes("vap_denied:test-target-registration", 403,
                                            "ValidatingAdmissionPolicy 'test-target-registration' with binding "
                                            "'test-target-registration' denied request"))
    case.assertTrue(mods.apply.dry_run_permitted([{"webhooks": [{"sideEffects": "None"},
                                                                {"sideEffects": "NoneOnDryRun"}]}]))
    case.assertFalse(mods.apply.dry_run_permitted([{"webhooks": [{"sideEffects": "Some"}]}]))
    case.assertFalse(mods.apply.dry_run_permitted([{"webhooks": [{}]}]))


def scenario_d13(case, mods):
    own = mods.apply.d13_ownership
    runtime = {"manager": "test-k8s-runtime", "operation": "Apply", "subresource": "", "fields": ["f:spec"]}
    status = {"manager": "kube-apiserver", "operation": "Update", "subresource": "status", "fields": ["f:status"]}
    case.assertEqual(own({"kind": "CustomResourceDefinition", "managers": [runtime, status]}, "test-k8s-runtime"),
                     "OWNED")
    case.assertEqual(own({"kind": "Namespace", "managers": [runtime, status]}, "test-k8s-runtime"), "FOREIGN_FIELD")
    wide = dict(status, fields=["f:status", "f:spec"])
    case.assertEqual(own({"kind": "CustomResourceDefinition", "managers": [runtime, wide]}, "test-k8s-runtime"),
                     "FOREIGN_FIELD")
    spoof = dict(runtime, operation="Update")
    case.assertEqual(own({"kind": "Namespace", "managers": [runtime, spoof]}, "test-k8s-runtime"), "FOREIGN_FIELD")
    case.assertEqual(own({"kind": "Namespace", "managers": [spoof]}, "test-k8s-runtime"), "NOT_OWNED")
    istiod = {"manager": "pilot-discovery", "operation": "Update", "subresource": "", "fields": ["f:webhooks"]}
    case.assertEqual(own({"kind": "ValidatingWebhookConfiguration", "managers": [runtime, istiod]},
                         "test-k8s-runtime"), "OWNERSHIP_NOT_VERIFIED")


def scenario_adapter_boundary(case, mods):
    with run_for(mods) as r:
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.get({"apiVersion": "v1", "kind": "Pod", "namespace": "istio-system", "name": "x"})
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.server_side_apply(r.members["namespaces"][0], r.objects[0], "test-k8s-runtime", force=True)


def scenario_cli_refused(case, mods):
    err = io.StringIO()
    with mock.patch("subprocess.run", side_effect=AssertionError("no process may start")), \
            contextlib.redirect_stderr(err):
        code = k8s_runtime.main(["apply", "--through", "base"])
    case.assertEqual(code, 1)
    case.assertIn("operation_not_approved:apply", err.getvalue())


def scenario_no_network_or_process(case, mods):
    tree = ast.parse((HERE / "k8s_runtime_apply.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    case.assertEqual(imported & {"socket", "ssl", "http", "urllib", "requests", "subprocess", "kubernetes"}, set())


def scenario_namespace_inactive(case, mods):
    with run_for(mods) as r:
        original = r.adapter.server_side_apply

        def inactive(identity, manifest, field_manager, force=False, dry_run=False):
            answer = original(identity, manifest, field_manager, force, dry_run)
            key = k8s_runtime_receipt.key_of(identity)
            if not dry_run and identity["kind"] == "Namespace":
                r.adapter.objects[key]["status"] = {"phase": "Terminating"}
            return answer
        r.adapter.server_side_apply = inactive
        case.assertEqual(outcome(r.run()), (3, "UNDETERMINED", "namespace_not_active"))


def scenario_uid_changed_live_only(case, mods):
    """The live UID changes after reconcile but before the write (a race); nothing may be written before stopping."""
    with run_for(mods) as r:
        first, second = r.key("namespaces", 0), r.key("namespaces", 1)
        r.adapter.conflicts.add(second)
        case.assertEqual(outcome(r.run())[2], "field_conflict")
        r.adapter.conflicts.clear()
        engine = mods.apply.Engine(r.report, r.objects, r.new_store(), r.adapter, r.clock, r.arn)
        state = mods.receipt.load(r.store.dir, r.plan, r.store.expected)["state"]
        before = len(r.journal())
        r.adapter.objects[first]["metadata"]["uid"] = "00000000-0000-4000-9000-0000000000ee"
        try:
            with engine.store.lock():
                engine.apply_object("namespaces", r.members["namespaces"][0], state)
            reason = None
        except mods.apply.ApplyStop as stopped:
            reason = stopped.reason
        except Exception as raised:  # noqa: BLE001 - a mutant may crash instead
            reason = "crash:" + type(raised).__name__
        case.assertEqual(reason, "uid_changed")
        case.assertEqual(len(r.journal()), before)


def scenario_foreign_field_during_apply(case, mods):
    """A foreign manager appears on the object as it is applied: the post-apply ownership check must stop."""
    with run_for(mods) as r:
        target = crd_key(r)
        original = r.adapter.server_side_apply

        def tainted(identity, manifest, field_manager, force=False, dry_run=False):
            answer = original(identity, manifest, field_manager, force, dry_run)
            if not dry_run and k8s_runtime_receipt.key_of(identity) == target:
                r.adapter.objects[target]["metadata"]["managedFields"].append(
                    {"manager": "helm", "operation": "Update", "fieldsV1": {"f:spec": {}}})
            return answer
        r.adapter.server_side_apply = tainted
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "foreign_field"))
        case.assertFalse(any(rec["type"] == "STAGE_DONE" and rec["stage"] == "base" for rec in r.journal()))


# ---- unit tests ----------------------------------------------------------------------------------------------------

class EngineTests(unittest.TestCase):
    def test_success_ends_applied_with_deferred(self):
        scenario_success_is_deferred(self, real_mods())
        scenario_deferred_never_pass(self, real_mods())

    def test_namespaces_only_is_accepted(self):
        scenario_namespaces_only(self, real_mods())

    def test_rerun_reverifies_without_writes(self):
        scenario_rerun_reverifies(self, real_mods())
        scenario_status_manager_allowed(self, real_mods())

    def test_pins_bundle_and_objects(self):
        scenario_pins(self, real_mods())
        scenario_bundle_changed(self, real_mods())
        scenario_objects_match_plan(self, real_mods())

    def test_fingerprint(self):
        scenario_fingerprint(self, real_mods())

    def test_gates_and_plan_order(self):
        scenario_gates(self, real_mods())
        scenario_plan_order(self, real_mods())

    def test_receipt_damage_stops(self):
        scenario_receipt_damage(self, real_mods())

    def test_crash_recovery(self):
        scenario_crash_before_apply(self, real_mods())
        scenario_crash_after_apply(self, real_mods())

    def test_uid_change_and_foreign_ownership(self):
        scenario_uid_changed(self, real_mods())
        scenario_foreign_owner(self, real_mods())
        scenario_foreign_field(self, real_mods())

    def test_conflict_never_forced(self):
        scenario_conflict(self, real_mods())

    def test_namespace_must_be_active(self):
        scenario_namespace_inactive(self, real_mods())

    def test_uid_race_before_write(self):
        scenario_uid_changed_live_only(self, real_mods())

    def test_foreign_field_during_apply(self):
        scenario_foreign_field_during_apply(self, real_mods())

    def test_stage_order(self):
        scenario_stage_order(self, real_mods())

    def test_crd_and_api_timeouts(self):
        scenario_crd_timeout(self, real_mods())
        scenario_api_timeout(self, real_mods())

    def test_c1_protection(self):
        scenario_c1(self, real_mods())

    def test_dry_run_and_classification(self):
        scenario_dry_run(self, real_mods())
        scenario_classify(self, real_mods())

    def test_d13_allowlist(self):
        scenario_d13(self, real_mods())

    def test_adapter_boundary_and_cli(self):
        scenario_adapter_boundary(self, real_mods())
        scenario_cli_refused(self, real_mods())
        scenario_no_network_or_process(self, real_mods())


# ---- mutations -----------------------------------------------------------------------------------------------------

A, R = "k8s_runtime_apply.py", "k8s_runtime_receipt.py"
MUTATIONS = [
    ("adapter_gate", A, '        if not isinstance(self.adapter, FakeAdapter) or getattr(self.adapter, "is_fake", False) is not True:',
     "        if False:", scenario_gates),
    ("stage_gate", A, "        if through not in APPROVED_STAGES:", "        if False:", scenario_gates),
    ("plan_order", A, "        if self.plan.stage_order[:len(APPROVED_STAGES)] != list(APPROVED_STAGES):", "        if False:",
     scenario_plan_order),
    ("pins", A, "            k8s_runtime.check_pins(self.report, expected_manifest, expected_input)", "            pass",
     scenario_pins),
    ("objects_sha", A, '        if self.objects_sha256 != self.report["manifest_sha256"]:', "        if False:",
     scenario_objects_match_plan),
    ("bundle_changed", A, '            stop(2, "bundle_changed")', "            pass", scenario_bundle_changed),
    ("fingerprint", A, '        if fp != expected["fingerprint"]:', "        if False:", scenario_fingerprint),
    ("quarantine_record", A, '                self.store.quarantine(row["identity"], live["metadata"]["uid"] if live else None, "creation_unproven")\n',
     "", scenario_crash_after_apply),
    ("stop_verdicts", A, '"UID_CHANGED": (4, "uid_changed"),', "", scenario_uid_changed),
    ("foreign_owner_verdict", A, '"NOT_OWNED": (4, "foreign_owner"),', "", scenario_foreign_owner),
    ("pre_apply_order", A, '            if "namespaces" not in done:', "            if False:", scenario_stage_order),
    ("c1_pre_apply", A, '            if c1_violations([self.manifest(i) for i in self.members(stage)]):', "            if False:",
     scenario_c1),
    ("dry_run_check", A, '            if outcome == "allowed":\n                continue', '            if True:\n                continue',
     scenario_dry_run),
    ("conflict_result", A, '            self.store.result(seq, identity, None, None, None, "failed")\n            stop(4, "field_conflict")',
     '            stop(4, "field_conflict")', scenario_conflict),
    ("post_apply_ownership", A, '        if owned != "OWNED":', "        if False:", scenario_foreign_field_during_apply),
    ("namespace_active", A, '            if obj is None or (obj.get("status") or {}).get("phase") != "Active":',
     "            if obj is None:", scenario_namespace_inactive),
    ("crd_conditions", A, '                if obj is not None and conditions_true(obj, ("Established", "NamesAccepted")):',
     "                if obj is not None:", scenario_crd_timeout),
    ("crd_timeout_value", A, "CRD_ESTABLISHED_TIMEOUT_SECONDS = 120", "CRD_ESTABLISHED_TIMEOUT_SECONDS = 12",
     scenario_crd_timeout),
    ("api_timeout_value", A, "API_READ_TIMEOUT_SECONDS = 20", "API_READ_TIMEOUT_SECONDS = 30", scenario_api_timeout),
    ("deferred_label", A, '"final_acceptance": "DEFERRED" if deferred else "PASS"', '"final_acceptance": "PASS"',
     scenario_deferred_never_pass),
    ("deferred_exit", A, '        return 6 if any(s["deferred"] for s in self.stages) else 0', "        return 0",
     scenario_success_is_deferred),
    ("d13_status_fields", A, ' and fields and fields <= {"f:status"}', "", scenario_d13),
    ("d13_unverified", A, '            verdict = "OWNERSHIP_NOT_VERIFIED"\n            continue', "            continue",
     scenario_d13),
    ("classify_unknown", A, '            return "authz_denied"\n        return "unknown"', '            return "authz_denied"\n        return "allowed"',
     scenario_classify),
    ("probe_exact", A, "    return classify_admission(status, body) == expected_class",
     '    return classify_admission(status, body) != "allowed"', scenario_classify),
    ("dry_run_side_effects", A, 'w.get("sideEffects") in ("None", "NoneOnDryRun")', 'w.get("sideEffects") != "Some"',
     scenario_classify),
    ("adapter_scope", A, '            raise AdapterError("read_out_of_scope")', "            pass", scenario_adapter_boundary),
    ("adapter_force", A, '            raise AdapterError("force_conflicts_refused")', "            pass", scenario_adapter_boundary),
    ("uid_before_apply", A, '        if recorded is not None and (live is None or live["metadata"].get("uid") != recorded):\n            stop(4, "uid_changed")',
     "", scenario_uid_changed_live_only),
    ("close_interrupted_intent", A, '            self.store.result(intent["seq"], identity, None, None, None, "failed")\n', "",
     scenario_crash_before_apply),
    ("receipt_ownership_hook", R, "    owns = ownership_fn or ownership", "    owns = ownership", scenario_status_manager_allowed),
]


def mutant(filename, old, new):
    path = HERE / filename
    source = path.read_text()
    if source.count(old) != 1:
        raise AssertionError("mutation target not found exactly once in " + filename + ": " + old.strip()[:80])
    spec = importlib.util.spec_from_loader("mutant_" + filename.replace(".py", ""), loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(source.replace(old, new), module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


def mods_for(filename, old, new):
    if filename == A:
        return Mods(apply=mutant(filename, old, new), receipt=k8s_runtime_receipt)
    receipt_mutant = mutant(filename, old, new)
    apply_module = mutant(A, "import k8s_runtime_receipt as receipt  # noqa: E402",
                          "import k8s_runtime_receipt as receipt  # noqa: E402")
    apply_module.receipt = receipt_mutant
    return Mods(apply=apply_module, receipt=receipt_mutant)


class MutationTests(unittest.TestCase):
    def test_each_guard_mutation_is_detected(self):
        self.assertEqual(len(MUTATIONS), 31)
        undetected = []
        for name, filename, old, new, scenario in MUTATIONS:
            mods = mods_for(filename, old, new)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, mods)
            except AssertionError:
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
