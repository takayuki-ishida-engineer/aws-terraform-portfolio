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
FIXTURE_DOC = common.parse(FIXTURE.read_text())
STAGES = ("namespaces", "base", "controller", "istiod", "gateway", "mesh_security", "admission", "binding_writer")
KEEP = object()
HELM = os.environ.get("K8S_RUNTIME_HELM", "")
KUBE_SYSTEM_UID = "11111111-2222-4333-8444-555555555555"
CACHE = {}
# Unexpected exceptions raised by the code under test. A mutant that only crashes is not counted as a
# detection of the intended safety contract (MutationTests reports it separately).
CRASHES = []


def crash(raised):
    CRASHES.append(type(raised).__name__ + ": " + str(raised)[:120])
    return "crash:" + type(raised).__name__


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
                            for k in self.plan.members[s]] for s in STAGES}
        scope = [k for s in STAGES for k in self.plan.members[s]]
        secrets = [(x["namespace"], x["name"]) for st in self.report["stages"] if st["name"] in STAGES
                   for x in st.get("required_secrets") or []]
        self.adapter = mods.apply.FakeAdapter(self.clock, kube_uid, scope, secrets)
        self.registry = mods.apply.FakeRegistry()
        self.ca = FIXTURE_DOC["runtime"]["webhook_ca_bundle"]

    def new_store(self, store_manifest=None):
        return self.mods.receipt.Store(self.tmp / "state", self.fp, self.report["project"],
                                       store_manifest or self.report["manifest_sha256"], self.report["input_sha256"],
                                       self.plan)

    def run(self, through="base", manifest=None, input_sha=None, adapter=None, store=None, registry=KEEP, ca=KEEP):
        try:
            return self.mods.apply.apply_stages(self.report, self.objects, store or self.store,
                                                adapter or self.adapter, self.clock,
                                                manifest or self.report["manifest_sha256"],
                                                input_sha or self.report["input_sha256"], self.arn, through,
                                                registry=self.registry if registry is KEEP else registry,
                                                webhook_ca_bundle=self.ca if ca is KEEP else ca)
        except Exception as raised:  # noqa: BLE001 - recorded as a crash, never as a detection
            return {"exit_code": crash(raised), "status": type(raised).__name__, "reason": str(raised), "stages": []}

    def journal(self):
        path = self.store.dir / "journal.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def applies(self):
        return [c for c in self.adapter.calls if c[0] == "apply"]

    def key(self, stage, index):
        return k8s_runtime_receipt.key_of(self.members[stage][index])

    def kind_key(self, stage, kind, nth=0):
        return [k8s_runtime_receipt.key_of(i) for i in self.members[stage] if i["kind"] == kind][nth]

    def manifest(self, key):
        return next(o for o in self.objects if k8s_runtime_apply.key_of(k8s_runtime_apply.identity_of(o)) == key)

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


class Impostor:
    """A fully working adapter that is not a FakeAdapter (it delegates to one); the gate must still refuse it."""

    is_fake = True

    def __init__(self, inner):
        self.inner, self.used = inner, []

    def get(self, identity):
        self.used.append("get")
        return self.inner.get(identity)

    def server_side_apply(self, *args, **kwargs):
        self.used.append("apply")
        return self.inner.server_side_apply(*args, **kwargs)


def scenario_gates(case, mods):
    with run_for(mods) as r:
        impostor = Impostor(r.adapter)
        case.assertEqual(outcome(r.run(adapter=impostor)), (1, "REFUSED", "real_adapter_not_approved"))
        case.assertEqual(impostor.used, [])
        case.assertEqual(outcome(r.run(through="ingress")), (1, "REFUSED", "stage_not_approved:ingress"))
        case.assertEqual(r.journal(), [])
        case.assertEqual(r.applies(), [])
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
            {"manager": "pilot-discovery", "operation": "Update",
             "fieldsV1": {"f:webhooks": {'k:{"name":"validation.istio.io"}': {"f:clientConfig": {"f:caBundle": {}}}}}})
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "ownership_not_verified")
    with run_for(mods) as r:
        r.run()
        validator = next(k8s_runtime_receipt.key_of(i) for i in r.members["base"]
                         if i["kind"] == "ValidatingWebhookConfiguration")
        r.adapter.objects[validator]["metadata"]["managedFields"].append(
            {"manager": "pilot-discovery", "operation": "Update", "fieldsV1": {"f:webhooks": {}}})
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "foreign_field")


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
    a = mods.apply
    own = a.d13_ownership
    namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "n", "labels": {"x": "1", "y": "2"}}}
    crd = {"apiVersion": "apiextensions.k8s.io/v1", "kind": "CustomResourceDefinition",
           "metadata": {"name": "c.example.io"}, "spec": {"group": "example.io", "scope": "Namespaced",
                                                         "names": {"kind": "C", "plural": "cs"}}}
    webhook = {"apiVersion": "admissionregistration.k8s.io/v1", "kind": "ValidatingWebhookConfiguration",
               "metadata": {"name": "v"}, "webhooks": [{"name": "w.example.io", "failurePolicy": "Fail",
                                                        "sideEffects": "None", "rules": [{"operations": ["CREATE"]}]}]}

    def observed(manifest, runtime_paths, *others):
        managers = [{"manager": "test-k8s-runtime", "operation": "Apply", "subresource": "",
                     "paths": frozenset(runtime_paths)}] + list(others)
        return {"kind": manifest["kind"], "managers": managers, "required": a.required_paths(manifest)}

    def other(manager, paths, subresource="", operation="Update"):
        return {"manager": manager, "operation": operation, "subresource": subresource, "paths": frozenset(paths)}
    full = {m["kind"]: a.required_paths(m) for m in (namespace, crd, webhook)}
    for manifest in (namespace, crd, webhook):
        case.assertEqual(own(observed(manifest, full[manifest["kind"]]), "test-k8s-runtime"), "OWNED")
        case.assertEqual(own(observed(manifest, ()), "test-k8s-runtime"), "OWNERSHIP_NOT_VERIFIED")
    case.assertEqual(own(observed(crd, {("f:metadata", "f:labels", "f:a")}), "test-k8s-runtime"),
                     "OWNERSHIP_NOT_VERIFIED")
    case.assertEqual(own(observed(webhook, {p for p in full["ValidatingWebhookConfiguration"]
                                            if p[-1] != "f:failurePolicy"}), "test-k8s-runtime"),
                     "OWNERSHIP_NOT_VERIFIED")
    unknown = set(full["CustomResourceDefinition"]) | {("f:spec", "f:unknownField")}
    case.assertEqual(own(observed(crd, unknown), "test-k8s-runtime"), "OWNERSHIP_NOT_VERIFIED")
    status = other("kube-apiserver", {("f:status", "f:conditions"), ("f:status", "f:acceptedNames")}, "status")
    case.assertEqual(own(observed(crd, full["CustomResourceDefinition"], status), "test-k8s-runtime"), "OWNED")
    case.assertEqual(own(observed(namespace, full["Namespace"], status), "test-k8s-runtime"), "FOREIGN_FIELD")
    wide = other("kube-apiserver", {("f:status", "f:conditions"), ("f:metadata", "f:labels", "f:z")}, "status")
    case.assertEqual(own(observed(crd, full["CustomResourceDefinition"], wide), "test-k8s-runtime"), "FOREIGN_FIELD")
    nested = other("helm", {("f:spec", "f:names", "f:shortNames")})
    case.assertEqual(own(observed(crd, full["CustomResourceDefinition"], nested), "test-k8s-runtime"),
                     "FOREIGN_FIELD")
    spoof = other("test-k8s-runtime", full["Namespace"])
    case.assertEqual(own(observed(namespace, full["Namespace"], spoof), "test-k8s-runtime"), "FOREIGN_FIELD")
    case.assertEqual(own({"kind": "Namespace", "managers": [spoof], "required": full["Namespace"]},
                         "test-k8s-runtime"), "NOT_OWNED")
    # Section 10: istiod is allowed only on the three Istio webhook objects (see scenario_section10).
    istiod = other("pilot-discovery", {("f:webhooks", 'k:{"name":"w.example.io"}', "f:clientConfig", "f:caBundle")})
    case.assertEqual(own(observed(webhook, full["ValidatingWebhookConfiguration"], istiod), "test-k8s-runtime"),
                     "FOREIGN_FIELD")
    case.assertEqual(own(dict(observed(namespace, full["Namespace"]), required=None), "test-k8s-runtime"),
                     "OWNERSHIP_NOT_VERIFIED")
    case.assertEqual(a.paths_of({"f:spec": {"f:names": {"f:kind": {}, "f:plural": {}}}}),
                     {("f:spec", "f:names", "f:kind"), ("f:spec", "f:names", "f:plural")})


def runtime_entry(obj, manager="test-k8s-runtime"):
    return next(m for m in obj["metadata"]["managedFields"] if m["manager"] == manager and m["operation"] == "Apply")


def scenario_incomplete_ownership_consistent(case, mods):
    """CONSISTENT path (closed stages re-verified): a runtime entry with too few fields is not ownership."""
    for mutate in (lambda e: e.update(fieldsV1={}), lambda e: e["fieldsV1"].pop("f:spec")):
        with run_for(mods) as r:
            r.run()
            mutate(runtime_entry(r.adapter.objects[crd_key(r)]))
            case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "ownership_not_verified"))
    with run_for(mods) as r:
        r.run()
        validator = next(k8s_runtime_receipt.key_of(i) for i in r.members["base"]
                         if i["kind"] == "ValidatingWebhookConfiguration")
        runtime_entry(r.adapter.objects[validator])["fieldsV1"].pop("f:webhooks")
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "ownership_not_verified")


def scenario_incomplete_ownership_reapply(case, mods):
    """REAPPLY_SAFE path (an interrupted update): the same UID with incomplete ownership must stop."""
    with run_for(mods) as r:
        first, second = r.key("namespaces", 0), r.key("namespaces", 1)
        r.adapter.conflicts.add(second)
        case.assertEqual(outcome(r.run())[2], "field_conflict")
        r.adapter.conflicts.clear()
        r.adapter.apply_timeouts.add(first)
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "api_timeout")
        case.assertEqual(r.journal()[-1]["prior"]["state"], "owned")
        r.adapter.apply_timeouts.clear()
        runtime_entry(r.adapter.objects[first])["fieldsV1"] = {"f:metadata": {}}
        case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "ownership_not_verified"))


def snapshot(r, key):
    return json.dumps(r.adapter.objects.get(key), sort_keys=True)


def foreign_namespace(r, index, uid="00000000-0000-4000-9000-0000000000f1"):
    obj = copy.deepcopy(next(o for o in r.objects if o["kind"] == "Namespace"
                             and o["metadata"]["name"] == r.members["namespaces"][index]["name"]))
    obj["metadata"].update(uid=uid, resourceVersion="7", generation=1, labels={"owner": "someone-else"},
                           managedFields=[{"manager": "kubectl", "operation": "Apply",
                                           "fieldsV1": {"f:metadata": {"f:labels": {"f:owner": {}}}}}])
    obj["status"] = {"phase": "Active"}
    return obj


def scenario_foreign_appears_before_apply(case, mods):
    """Reconcile saw the namespace absent; a foreign one appears after the dry-run, before the apply."""
    with run_for(mods) as r:
        target = r.key("namespaces", 0)
        original = r.adapter.server_side_apply

        def race(identity, manifest, field_manager, force=False, dry_run=False, precondition=None):
            answer = original(identity, manifest, field_manager, force, dry_run, precondition)
            if dry_run and k8s_runtime_receipt.key_of(identity) == target:
                r.adapter.objects[target] = foreign_namespace(r, 0)
            return answer
        r.adapter.server_side_apply = race
        result = r.run()
        case.assertEqual(outcome(result), (4, "APPLY_FAILED", "foreign_object_appeared"))
        case.assertEqual(json.loads(snapshot(r, target)), foreign_namespace(r, 0))
        case.assertFalse(any(rec["type"] == "INTENT" and k8s_runtime_receipt.key_of(rec["identity"]) == target
                             for rec in r.journal()))
        case.assertEqual(r.applies(), [])


def scenario_replaced_before_write(case, mods):
    """The object is absent at the engine's read, but appears between that read and the write."""
    with run_for(mods) as r:
        target = r.key("namespaces", 0)
        r.adapter.before_write[target] = lambda adapter: adapter.objects.__setitem__(target, foreign_namespace(r, 0))
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "precondition_failed"))
        case.assertEqual(json.loads(snapshot(r, target)), foreign_namespace(r, 0))
        last = r.journal()[-1]
        case.assertEqual((last["type"], last.get("outcome")), ("RESULT", "failed"))


def scenario_update_uid_mismatch(case, mods):
    """An owned object is replaced (new UID) between the engine's read and the conditional update."""
    with run_for(mods) as r:
        first, second = r.key("namespaces", 0), r.key("namespaces", 1)
        r.adapter.conflicts.add(second)
        r.run()
        r.adapter.conflicts.clear()
        replacement = foreign_namespace(r, 0, uid="00000000-0000-4000-9000-0000000000f2")
        r.adapter.before_write[first] = lambda adapter: adapter.objects.__setitem__(first, replacement)
        case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "precondition_failed"))
        case.assertEqual(json.loads(snapshot(r, first)), replacement)


def scenario_owned_update_succeeds(case, mods):
    """With the recorded UID matching, the conditional update proceeds and the UID is unchanged."""
    with run_for(mods) as r:
        first, second = r.key("namespaces", 0), r.key("namespaces", 1)
        r.adapter.conflicts.add(second)
        r.run()
        uid = r.adapter.objects[first]["metadata"]["uid"]
        r.adapter.conflicts.clear()
        r.adapter.calls.clear()
        case.assertEqual(r.run(store=r.new_store())["exit_code"], 6)
        case.assertIn(("apply", first), r.adapter.calls)
        case.assertEqual(r.adapter.objects[first]["metadata"]["uid"], uid)
        updates = [rec for rec in r.journal() if rec["type"] == "INTENT" and rec["action"] == "update"]
        case.assertEqual([k8s_runtime_receipt.key_of(rec["identity"]) for rec in updates], [first])


def scenario_write_needs_precondition(case, mods):
    with run_for(mods) as r:
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.server_side_apply(r.members["namespaces"][0], r.objects[0], "test-k8s-runtime")
        case.assertNotIn(r.key("namespaces", 0), r.adapter.objects)
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.server_side_apply(r.members["namespaces"][0], r.objects[0], "test-k8s-runtime",
                                        precondition={"absent": True, "uid": "x"})


def scenario_deferred_needs_evidence(case, mods):
    """A later stage's STAGE_DONE never resolves a deferred item; only verified evidence could."""
    outstanding = mods.apply.outstanding_deferred
    everything = {"namespaces", "base", "controller", "istiod", "gateway", "admission", "ingress"}
    case.assertEqual(len(outstanding("base", everything, {})), 1)
    case.assertEqual(outstanding("base", everything, {mods.apply.DEFERRED["base"][0]["item"]: True})[0]["resolved_by"],
                     "istiod")
    requirements = {req for items in mods.apply.DEFERRED.values() for item in items for req in item["requires"]}
    case.assertEqual(outstanding("base", everything, {req: "yes" for req in requirements})[0]["status"],
                     "NOT_VERIFIED")
    # Even evidence claiming every requirement MET, Live ones included, resolves nothing that is Live or BLOCKED.
    claimed = {req: "MET" for req in requirements}
    for stage in ("base", "controller", "istiod"):
        left = outstanding(stage, everything, claimed)
        case.assertEqual(len(left), len(mods.apply.DEFERRED[stage]), stage)
        case.assertTrue(all(v in ("NOT_VERIFIED", "BLOCKED") for item in left for k, v in item["evidence"].items()
                            if k.startswith("live_") or k == "ingress_blocked"))
    case.assertEqual([i["status"] for i in outstanding("controller", everything, claimed)], ["NOT_VERIFIED", "BLOCKED"])
    case.assertEqual(outstanding("namespaces", everything, {}), [])


def scenario_adapter_boundary(case, mods):
    with run_for(mods) as r:
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.get({"apiVersion": "v1", "kind": "Pod", "namespace": "istio-system", "name": "x"})
        with case.assertRaises(mods.apply.AdapterError) as raised:
            r.adapter.server_side_apply(r.members["namespaces"][0], r.objects[0], "test-k8s-runtime", force=True,
                                        precondition={"absent": True})
        case.assertEqual(str(raised.exception), "force_conflicts_refused")
        case.assertNotIn(r.key("namespaces", 0), r.adapter.objects)


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

        def inactive(identity, manifest, field_manager, force=False, dry_run=False, precondition=None):
            answer = original(identity, manifest, field_manager, force, dry_run, precondition)
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
        except Exception as raised:  # noqa: BLE001 - recorded as a crash, never as a detection
            reason = crash(raised)
        case.assertEqual(reason, "uid_changed")
        case.assertEqual(len(r.journal()), before)


def taint_after_write(r, target, edit):
    """Change the object right after the fake write lands, before the engine's readback."""
    original = r.adapter.server_side_apply

    def tainted(identity, manifest, field_manager, force=False, dry_run=False, precondition=None):
        answer = original(identity, manifest, field_manager, force, dry_run, precondition)
        if not dry_run and k8s_runtime_receipt.key_of(identity) == target:
            edit(r.adapter.objects[target])
        return answer
    r.adapter.server_side_apply = tainted


def records_for(r, key, kind):
    return [rec for rec in r.journal() if rec["type"] == kind and k8s_runtime_receipt.key_of(rec["identity"]) == key]


def owned_uid(r, key):
    state = k8s_runtime_receipt.load(r.store.dir, r.plan, r.store.expected)["state"]
    return state["objects"].get(key, {}).get("owned_uid")


def assert_quarantined_not_owned(case, r, key, reason, uid_expected):
    applied = [rec for rec in records_for(r, key, "RESULT") if rec["outcome"] != "failed"]
    case.assertEqual(applied, [], "no success RESULT before ownership is proven")
    quarantine = records_for(r, key, "QUARANTINE")
    case.assertEqual([(q["reason"], q["observed_uid"]) for q in quarantine], [(reason, uid_expected)])
    case.assertIsNone(owned_uid(r, key), "the unproven UID must not become owned in the receipt")


def scenario_foreign_field_during_apply(case, mods):
    """P1-07: a foreign manager shows up in the readback; no success RESULT, the outcome is quarantined."""
    with run_for(mods) as r:
        target = crd_key(r)
        taint_after_write(r, target, lambda o: o["metadata"]["managedFields"].append(
            {"manager": "helm", "operation": "Update", "fieldsV1": {"f:spec": {}}}))
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "foreign_field"))
        assert_quarantined_not_owned(case, r, target, "ownership_unproven", r.adapter.objects[target]["metadata"]["uid"])
        case.assertFalse(any(rec["type"] == "STAGE_DONE" and rec["stage"] == "base" for rec in r.journal()))


def scenario_runtime_fields_short_after_apply(case, mods):
    """P1-07: the readback shows the runtime owning too few fields; quarantined, not recorded as owned."""
    with run_for(mods) as r:
        target = r.key("namespaces", 0)
        taint_after_write(r, target, lambda o: runtime_entry(o).update(fieldsV1={"f:metadata": {}}))
        case.assertEqual(outcome(r.run()), (4, "APPLY_FAILED", "ownership_not_verified"))
        assert_quarantined_not_owned(case, r, target, "ownership_unproven", r.adapter.objects[target]["metadata"]["uid"])


def scenario_uid_changed_after_apply(case, mods):
    """P1-07: an owned update lands, then the readback shows another UID; quarantined, never "not applied"."""
    with run_for(mods) as r:
        first, second = r.key("namespaces", 0), r.key("namespaces", 1)
        r.adapter.conflicts.add(second)
        r.run()
        recorded = owned_uid(r, first)
        r.adapter.conflicts.clear()
        replaced = "00000000-0000-4000-9000-0000000000f3"
        taint_after_write(r, first, lambda o: o["metadata"].update(uid=replaced))
        case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "uid_changed"))
        quarantine = records_for(r, first, "QUARANTINE")
        case.assertEqual([(q["reason"], q["observed_uid"]) for q in quarantine], [("uid_changed", replaced)])
        case.assertEqual(owned_uid(r, first), recorded, "the receipt keeps only the UID proven earlier")
        last_results = records_for(r, first, "RESULT")
        case.assertEqual([rec["outcome"] for rec in last_results], ["applied"], "no failed RESULT after a landed write")


def scenario_crash_before_success_result(case, mods):
    """P1-07: the readback fails after the write landed; the INTENT stays open, the rerun quarantines, never adopts."""
    with run_for(mods) as r:
        target = r.key("namespaces", 0)
        taint_after_write(r, target, lambda o: r.adapter.latency.__setitem__(target, 25))
        case.assertEqual(outcome(r.run()), (3, "UNDETERMINED", "api_timeout"))
        case.assertEqual(r.journal()[-1]["type"], "INTENT")
        case.assertIsNone(owned_uid(r, target))
        r.adapter.latency.clear()
        live_uid = r.adapter.objects[target]["metadata"]["uid"]
        case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "quarantined"))
        case.assertEqual([(q["reason"], q["observed_uid"]) for q in records_for(r, target, "QUARANTINE")],
                         [("creation_unproven", live_uid)])
        r.adapter.calls.clear()
        case.assertEqual(outcome(r.run(store=r.new_store()))[2], "quarantined")
        case.assertEqual(r.applies(), [], "a quarantined object is neither re-applied nor adopted")
        case.assertIsNone(owned_uid(r, target))


def stage_open_with_owned_crd(r):
    """Base stage left open with every CRD applied and owned (the webhook conflicts)."""
    validator = next(k8s_runtime_receipt.key_of(i) for i in r.members["base"]
                     if i["kind"] == "ValidatingWebhookConfiguration")
    r.adapter.conflicts.add(validator)
    case_outcome = outcome(r.run())
    r.adapter.conflicts.clear()
    return case_outcome


def scenario_foreign_manager_before_write(case, mods):
    """P1-08: after the engine's read, a foreign manager appears on the same UID; the write is refused unchanged."""
    cases = [("namespaces", 0, {"f:metadata": {"f:labels": {"f:team": {}}}}),
             ("base", 0, {"f:spec": {"f:names": {"f:shortNames": {}}}})]
    for stage, index, fields in cases:
        with run_for(mods) as r:
            if stage == "namespaces":
                r.adapter.conflicts.add(r.key("namespaces", 1))
                r.run()
                r.adapter.conflicts.clear()
                target = r.key("namespaces", 0)
            else:
                case.assertEqual(stage_open_with_owned_crd(r)[2], "field_conflict")
                target = crd_key(r)
            uid_before = owned_uid(r, target)

            def add_foreign(adapter, target=target, fields=fields):
                adapter.objects[target]["metadata"]["managedFields"].append(
                    {"manager": "someone-else", "operation": "Apply", "fieldsType": "FieldsV1", "fieldsV1": fields})
                CAPTURED[target] = snapshot(r, target)
            r.adapter.before_write[target] = add_foreign
            case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", "foreign_field_refused"))
            case.assertEqual(snapshot(r, target), CAPTURED.pop(target), "object, resourceVersion, managedFields unchanged")
            last = records_for(r, target, "RESULT")[-1]
            case.assertEqual(last["outcome"], "failed")
            case.assertEqual(owned_uid(r, target), uid_before)


CAPTURED = {}


def scenario_status_update_allowed(case, mods):
    """P1-08: a status-subresource Update on an owned CRD is allowed; the owned update proceeds and keeps it."""
    with run_for(mods) as r:
        case.assertEqual(stage_open_with_owned_crd(r)[2], "field_conflict")
        target = crd_key(r)
        status = {"manager": "kube-apiserver", "operation": "Update", "subresource": "status",
                  "fieldsType": "FieldsV1", "fieldsV1": {"f:status": {"f:conditions": {}}}}
        r.adapter.objects[target]["metadata"]["managedFields"].append(status)
        r.adapter.calls.clear()
        case.assertEqual(r.run(store=r.new_store())["exit_code"], 6)
        case.assertIn(("apply", target), r.adapter.calls)
        case.assertIn(status, r.adapter.objects[target]["metadata"]["managedFields"])


STATUS_ENTRY = {"manager": "kube-apiserver", "operation": "Update", "subresource": "status",
                "fieldsType": "FieldsV1", "fieldsV1": {"f:status": {"f:conditions": {}}}}


def prepare_owned_update(r, stage):
    """Leave ``stage`` open with its first object (a namespace, or the first CRD) applied and owned."""
    if stage == "namespaces":
        r.adapter.conflicts.add(r.key("namespaces", 1))
        r.run()
        r.adapter.conflicts.clear()
        return r.key("namespaces", 0)
    stage_open_with_owned_crd(r)
    return crd_key(r)


def without_path(prefix):
    """Race: drop one required nested leaf (the first under ``prefix``) from the runtime's Apply entry."""
    def race(obj):
        entry = runtime_entry(obj)
        paths = k8s_runtime_apply.paths_of(entry["fieldsV1"])
        victim = sorted(p for p in paths if p[:len(prefix)] == prefix)[0]
        entry["fieldsV1"] = k8s_runtime_apply.fieldsv1_of(paths - {victim})
    return race


def with_extra_path(path):
    def race(obj):
        entry = runtime_entry(obj)
        entry["fieldsV1"] = k8s_runtime_apply.fieldsv1_of(k8s_runtime_apply.paths_of(entry["fieldsV1"]) | {path})
    return race


def without_runtime_entry(obj):
    obj["metadata"]["managedFields"].remove(runtime_entry(obj))


def assert_refused_unchanged(case, r, stage, target, race, reason):
    """Inject ``race`` after the engine's read and just before the fake write; prove nothing changed."""
    uid_before = owned_uid(r, target)
    applied_before = [rec for rec in records_for(r, target, "RESULT") if rec["outcome"] == "applied"]
    captured = {}

    def inject(adapter):
        race(adapter.objects[target])
        captured.update(object=copy.deepcopy(adapter.objects[target]), serial=adapter.serial)  # after the race
    r.adapter.before_write[target] = inject
    case.assertEqual(outcome(r.run(store=r.new_store())), (4, "APPLY_FAILED", reason))
    case.assertIn("object", captured, "the race ran between the engine's read and the write")
    before, after = captured["object"], r.adapter.objects[target]
    case.assertEqual(json.dumps(after, sort_keys=True), json.dumps(before, sort_keys=True), "object unchanged")
    for field in ("uid", "resourceVersion", "generation", "managedFields", "labels"):
        case.assertEqual(after["metadata"].get(field, "<absent>"), before["metadata"].get(field, "<absent>"), field)
    for field in ("spec", "status"):
        case.assertEqual(after.get(field, "<absent>"), before.get(field, "<absent>"), field)
    case.assertEqual(r.adapter.serial, captured["serial"], "the fake's write serial did not advance")
    applied = [rec for rec in records_for(r, target, "RESULT") if rec["outcome"] == "applied"]
    case.assertEqual(applied, applied_before, "no new success RESULT")
    case.assertEqual(records_for(r, target, "RESULT")[-1]["outcome"], "failed", "refused before the write")
    case.assertEqual(records_for(r, target, "QUARANTINE"), [], "an atomic refusal is not an unproven outcome")
    case.assertFalse(any(rec["type"] == "STAGE_DONE" and rec["stage"] == stage for rec in r.journal()))
    case.assertEqual(owned_uid(r, target), uid_before, "the verified owned UID stays recorded")
    # No adoption and no silent restoration: a rerun stops before any write and leaves the object as it is.
    r.adapter.calls.clear()
    case.assertEqual(outcome(r.run(store=r.new_store()))[0], 4)
    case.assertEqual(r.applies(), [])
    case.assertEqual(json.dumps(r.adapter.objects[target], sort_keys=True), json.dumps(before, sort_keys=True))
    case.assertEqual(owned_uid(r, target), uid_before)


def scenario_write_refused_missing_managed_fields(case, mods):
    """P1-08 case A: the whole managedFields collection disappears on the same UID before the update."""
    for stage in ("namespaces", "base"):
        with run_for(mods) as r:
            target = prepare_owned_update(r, stage)
            assert_refused_unchanged(case, r, stage, target, lambda o: o["metadata"].pop("managedFields"),
                                     "not_owned_refused")


def scenario_write_refused_missing_runtime_entry(case, mods):
    """P1-08 case B: only the runtime's Apply entry disappears; a permitted status entry stays."""
    for stage in ("namespaces", "base"):
        with run_for(mods) as r:
            target = prepare_owned_update(r, stage)
            if stage == "base":
                r.adapter.objects[target]["metadata"]["managedFields"].append(copy.deepcopy(STATUS_ENTRY))
            assert_refused_unchanged(case, r, stage, target, without_runtime_entry, "not_owned_refused")
            if stage == "base":
                case.assertEqual(r.adapter.objects[target]["metadata"]["managedFields"], [STATUS_ENTRY])


def scenario_write_refused_partial_runtime(case, mods):
    """P1-08 case C: the runtime's Apply entry loses a required nested path, is emptied or claims extra."""
    races = [("namespaces", without_path(("f:metadata", "f:labels"))),
             ("base", without_path(("f:spec", "f:names"))),
             ("base", lambda o: runtime_entry(o).update(fieldsV1={})),
             ("namespaces", with_extra_path(("f:metadata", "f:annotations", "f:extra")))]
    for stage, race in races:
        with run_for(mods) as r:
            target = prepare_owned_update(r, stage)
            assert_refused_unchanged(case, r, stage, target, race, "ownership_not_verified_refused")


def scenario_write_refused_malformed(case, mods):
    """P1-08: malformed ownership evidence fails closed at write time, without a crash."""
    races = [("namespaces", lambda o: o["metadata"].__setitem__("managedFields", {"manager": "test-k8s-runtime"})),
             ("base", lambda o: runtime_entry(o).__setitem__("fieldsV1", ["f:spec"]))]
    for stage, race in races:
        with run_for(mods) as r:
            target = prepare_owned_update(r, stage)
            assert_refused_unchanged(case, r, stage, target, race, "ownership_not_verified_refused")


def scenario_write_refused_runtime_lost(case, mods):
    """Cases A, B and C together: the runtime's ownership lost on the same UID is never rebuilt by a write."""
    scenario_write_refused_missing_managed_fields(case, mods)
    scenario_write_refused_missing_runtime_entry(case, mods)
    scenario_write_refused_partial_runtime(case, mods)


def scenario_write_time_ownership(case, mods):
    """Every write-time refusal: a foreign manager, and the runtime's ownership lost."""
    scenario_foreign_manager_before_write(case, mods)
    scenario_write_refused_runtime_lost(case, mods)


# ---- Apply-B1: controller and istiod ------------------------------------------------------------------------------

LOCK = json.loads(k8s_runtime_apply.LOCK_PATH.read_text())
HOST = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/"


def lock_of(purpose):
    entry = next(e for e in LOCK["images"] if e["purpose"] == purpose)
    return entry["digest"], entry["platforms"]["linux/amd64"]["digest"]


def secret_metadata(namespace, name, project="test"):
    return {"apiVersion": "meta.k8s.io/v1", "kind": "PartialObjectMetadata",
            "metadata": {"name": name, "namespace": namespace, "uid": "00000000-0000-4000-9000-00000000c001",
                         "resourceVersion": "5",
                         "labels": {"app.kubernetes.io/part-of": project, "app.kubernetes.io/managed-by": "k8s_certs.py"},
                         "managedFields": [{"manager": project + "-k8s-certs", "operation": "Apply",
                                            "fieldsV1": {"f:type": {}, "f:data": {}}}]}}


def proxy_ref():
    return HOST + "test-dev-ecr-istio-proxy@" + lock_of("istio-proxy")[0]


def injected_pod(image=None):
    return json.dumps({"kind": "Pod", "spec": {"containers": [{"name": "app", "image": "registry.example/app:1"},
                                                              {"name": "istio-proxy", "image": image or proxy_ref()}]}})


def ready_cluster(r):
    """Fake evidence for a clean controller and istiod run: Secrets, ECR, image IDs and the fake probes."""
    for stage in r.report["stages"]:
        if stage["name"] in ("controller", "istiod", "gateway"):
            for secret in stage["required_secrets"]:
                r.adapter.secrets[(secret["namespace"], secret["name"])] = secret_metadata(secret["namespace"],
                                                                                         secret["name"])
    for entry in LOCK["images"]:
        r.registry.manifests[("test-dev-ecr-" + entry["purpose"], entry["digest"])] = {
            "kind": "index", "platforms": {"linux/amd64": entry["platforms"]["linux/amd64"]["digest"]}}
    for stage in ("controller", "istiod", "gateway"):
        key = r.kind_key(stage, "Deployment")
        containers = r.manifest(key)["spec"]["template"]["spec"]["containers"]
        r.adapter.workloads[key] = {"image_ids": {c["name"]: c["image"].split("@")[0] + "@" + platform_of(c["image"])
                                                  for c in containers}}
    r.adapter.probes["F"] = (403, 'admission webhook "validation.istio.io" denied the request: configuration is invalid')
    r.adapter.probes["G"] = (200, injected_pod())
    for name, policy, message in ADMISSION_ANSWERS:
        r.adapter.probes[name] = (403, vap_denial(policy, message))
    return r


NO_LB = "This namespace permits ClusterIP Services, not Ingress or external LB ownership."
TGB_ONLY = "Only the reviewed Platform binding/identity is permitted."
ADMISSION_ANSWERS = (("A", "test-no-lb-service", NO_LB), ("A_prime", "test-no-lb-service", NO_LB),
                     ("B", "test-target-registration", TGB_ONLY))


def vap_denial(policy, message):
    return ("ValidatingAdmissionPolicy '" + policy + "' with binding '" + policy + "' denied request: " + message)


def platform_of(image):
    digest = image.split("@")[1]
    return next(e["platforms"]["linux/amd64"]["digest"] for e in LOCK["images"] if e["digest"] == digest)


def workload(r, stage):
    return r.adapter.workloads[r.kind_key(stage, "Deployment")]


def stage_keys(r, stage):
    return set(r.plan.members[stage])


def assert_no_writes(case, r, stage):
    """Nothing of ``stage`` was dry-run, applied or journaled (a pre-apply stop)."""
    keys = stage_keys(r, stage)
    case.assertFalse(any(c[1] in keys for c in r.adapter.calls if c[0] in ("apply", "dry_run")), stage)
    case.assertFalse(any(rec["type"] == "INTENT" and rec["stage"] == stage for rec in r.journal()), stage)


def scenario_through_istiod(case, mods):
    """Controller and istiod applied and ready; every deferred item stays DEFERRED, never PASS (exit 6)."""
    with run_for(mods) as r:
        ready_cluster(r)
        result = r.run(through="istiod")
        case.assertEqual(outcome(result), (6, "APPLIED_WITH_DEFERRED", None))
        rows = {s["name"]: s for s in result["stages"]}
        case.assertEqual([(s["name"], s["final_acceptance"]) for s in result["stages"]],
                         [("namespaces", "PASS"), ("base", "DEFERRED"), ("controller", "DEFERRED"),
                          ("istiod", "DEFERRED")])
        case.assertEqual([rows[s]["in_stage_readiness"] for s in STAGES[:4]], ["NOT_APPLICABLE", "NOT_APPLICABLE", "MET", "MET"])
        base = rows["base"]["deferred"][0]["evidence"]
        case.assertEqual(base, {"base_validator_cabundle_populated": "MET", "istio_cabundle_manager_verified": "NOT_VERIFIED",
                                "istiod_endpoints_ready": "MET", "live_probe_F": "NOT_VERIFIED"})
        case.assertEqual([d["status"] for d in rows["controller"]["deferred"]], ["NOT_VERIFIED", "BLOCKED"])
        case.assertEqual([d["resolved_by"] for d in rows["istiod"]["deferred"]], ["istiod", "gateway"])
        case.assertEqual(result["runtime_final_acceptance"], "NOT_REACHED")
        case.assertEqual((result["evidence"]["fake_probe_F"], result["evidence"]["fake_probe_G"]),
                         ("CLASSIFIED_FAKE_ONLY", "CLASSIFIED_FAKE_ONLY"))
        case.assertEqual((result["evidence"]["controller_digest"], result["evidence"]["istiod_digest"]),
                         ("MATCH_PLATFORM", "MATCH_PLATFORM"))
        types_ = [rec["type"] for rec in r.journal()]
        case.assertEqual((types_.count("INTENT"), types_.count("RESULT"), types_.count("STAGE_DONE")), (43, 43, 4))
        case.assertEqual(len(r.applies()), 43)
        for name in ("aws-load-balancer-controller-webhook",):
            for kind in ("ValidatingWebhookConfiguration", "MutatingWebhookConfiguration"):
                obj = r.adapter.objects[r.kind_key("controller", kind)]
                case.assertTrue(all(w["clientConfig"]["caBundle"] == r.ca for w in obj["webhooks"]), name)
        istio = [r.kind_key("base", "ValidatingWebhookConfiguration"), r.kind_key("istiod", "ValidatingWebhookConfiguration"),
                 r.kind_key("istiod", "MutatingWebhookConfiguration")]
        for key in istio:
            obj = r.adapter.objects[key]
            case.assertTrue(all(w["clientConfig"].get("caBundle") for w in obj["webhooks"]), key)
            runtime = runtime_entry(obj)
            case.assertFalse(any(p[-1] == "f:caBundle" for p in k8s_runtime_apply.paths_of(runtime["fieldsV1"])), key)
        case.assertEqual(r.registry.calls, [("test-dev-ecr-lbc", lock_of("lbc")[0]),
                                            ("test-dev-ecr-istio-pilot", lock_of("istio-pilot")[0])])
        case.assertFalse(any(c[0] == "get" and "|Secret|" in c[1] for c in r.adapter.calls), "no full Secret read")


def scenario_through_controller(case, mods):
    with run_for(mods) as r:
        ready_cluster(r)
        result = r.run(through="controller")
        case.assertEqual(outcome(result), (6, "APPLIED_WITH_DEFERRED", None))
        case.assertEqual(result["stages"][-1]["final_acceptance"], "DEFERRED")
        case.assertEqual(result["stages"][1]["deferred"][0]["evidence"]["base_validator_cabundle_populated"],
                         "NOT_VERIFIED")
        assert_no_writes(case, r, "istiod")
        # Rerun: the closed controller stage is re-verified (readiness again), not re-applied.
        r.adapter.calls.clear()
        again = r.run(through="controller", store=r.new_store())
        case.assertEqual(outcome(again), (6, "APPLIED_WITH_DEFERRED", None))
        case.assertEqual(r.applies(), [])
        case.assertIn(("list", "pods|kube-system"), r.adapter.calls)


def scenario_rerun_after_istiod(case, mods):
    """istiod's caBundle entry is NOT_VERIFIED (D13): every rerun stops before any write, never adopts it."""
    with run_for(mods) as r:
        ready_cluster(r)
        r.run(through="istiod")
        r.adapter.calls.clear()
        case.assertEqual(outcome(r.run(through="istiod", store=r.new_store())), (4, "APPLY_FAILED", "ownership_not_verified"))
        case.assertEqual(r.applies(), [])


def scenario_istiod_patches_before_readback(case, mods):
    """istiod fills a caBundle before the engine's readback: ownership is unproven, so it is quarantined."""
    with run_for(mods) as r:
        ready_cluster(r)
        workload(r, "istiod")["ready_after"] = 0
        result = r.run(through="istiod")
        case.assertEqual(outcome(result), (4, "APPLY_FAILED", "ownership_not_verified"))
        case.assertEqual({rec["reason"] for rec in r.journal() if rec["type"] == "QUARANTINE"}, {"ownership_unproven"})


def scenario_secret_presence(case, mods):
    cases = [("controller", "kube-system", "aws-load-balancer-controller-tls"), ("istiod", "istio-system", "cacerts")]
    for stage, namespace, name in cases:
        with run_for(mods) as r:
            ready_cluster(r)
            del r.adapter.secrets[(namespace, name)]
            case.assertEqual(outcome(r.run(through="istiod")),
                             (3, "UNDETERMINED", "pre_apply_not_verified:secret_absent:" + namespace + "/" + name))
            assert_no_writes(case, r, stage)


def scenario_secret_metadata_only(case, mods):
    full = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "aws-load-balancer-controller-tls",
                                                               "namespace": "kube-system"}, "data": {"tls.key": "c2VjcmV0"}}
    leaked = dict(secret_metadata("kube-system", "aws-load-balancer-controller-tls"), data={"tls.key": "c2VjcmV0"})
    for response in (full, leaked, dict(secret_metadata("kube-system", "aws-load-balancer-controller-tls"),
                                        stringData={"x": "y"})):
        with run_for(mods) as r:
            ready_cluster(r)
            r.adapter.secrets[("kube-system", "aws-load-balancer-controller-tls")] = response
            result = r.run(through="controller")
            case.assertEqual(outcome(result), (3, "UNDETERMINED", "secret_metadata_only_unsupported"))
            case.assertNotIn("c2VjcmV0", json.dumps(result))
            assert_no_writes(case, r, "controller")


def scenario_secret_registration(case, mods):
    def wrong_manager(m):
        m["metadata"]["managedFields"][0]["manager"] = "kubectl"

    def wrong_label(m):
        m["metadata"]["labels"]["app.kubernetes.io/managed-by"] = "helm"

    def wrong_namespace(m):
        m["metadata"]["namespace"] = "default"
    for edit in (wrong_manager, wrong_label, wrong_namespace):
        with run_for(mods) as r:
            ready_cluster(r)
            edit(r.adapter.secrets[("istio-system", "cacerts")])
            case.assertEqual(outcome(r.run(through="istiod")),
                             (3, "UNDETERMINED", "pre_apply_not_verified:secret_not_registered:istio-system/cacerts"))
            assert_no_writes(case, r, "istiod")


def scenario_registry_evidence(case, mods):
    with run_for(mods) as r:
        ready_cluster(r)
        case.assertEqual(outcome(r.run(through="controller", registry=None)),
                         (3, "UNDETERMINED", "pre_apply_not_verified:ecr_evidence_unavailable"))
        assert_no_writes(case, r, "controller")

    class Impostor:
        is_fake = True
        manifests = {}

        def describe(self, repository, digest):
            return {"kind": "index", "platforms": {"linux/amd64": platform_of(HOST + repository + "@" + digest)}}
    with run_for(mods) as r:
        ready_cluster(r)
        case.assertEqual(outcome(r.run(through="controller", registry=Impostor())),
                         (1, "REFUSED", "real_registry_not_approved"))
        case.assertEqual(r.journal(), [])


def scenario_registry_digests(case, mods):
    lbc_index, _ = lock_of("lbc")
    pilot_index, _ = lock_of("istio-pilot")
    with run_for(mods) as r:
        ready_cluster(r)
        del r.registry.manifests[("test-dev-ecr-lbc", lbc_index)]
        case.assertEqual(outcome(r.run(through="controller"))[2], "pre_apply_not_verified:ecr_index_missing:lbc")
        assert_no_writes(case, r, "controller")
    with run_for(mods) as r:
        ready_cluster(r)
        r.registry.manifests[("test-dev-ecr-istio-pilot", pilot_index)]["platforms"]["linux/amd64"] = "sha256:" + "e" * 64
        case.assertEqual(outcome(r.run(through="istiod")), (3, "UNDETERMINED", "digest_not_verified:ecr_platform_child:istio-pilot"))
        assert_no_writes(case, r, "istiod")
    with run_for(mods) as r:
        ready_cluster(r)
        r.registry.manifests[("test-dev-ecr-lbc", lbc_index)]["kind"] = "manifest"
        case.assertEqual(outcome(r.run(through="controller"))[2], "pre_apply_not_verified:ecr_index_missing:lbc")


def scenario_nodes(case, mods):
    from_k = k8s_runtime_apply.fake_node
    for nodes in ([], [from_k("n", "ca-central-1a", "amd64", ready=False)], [from_k("n", "ca-central-1a", "arm64")],
                  [from_k("n", "ca-central-1b", "amd64")]):
        with run_for(mods) as r:
            ready_cluster(r)
            r.adapter.nodes = nodes
            case.assertEqual(outcome(r.run(through="controller")), (3, "UNDETERMINED", "pre_apply_not_verified:nodes"))
            assert_no_writes(case, r, "controller")


def scenario_bundle_ca(case, mods):
    with run_for(mods) as r:
        ready_cluster(r)
        case.assertEqual(outcome(r.run(through="controller", ca="b3RoZXI=")), (3, "UNDETERMINED", "pre_apply_not_verified:bundle_ca_differs"))
        assert_no_writes(case, r, "controller")
    with run_for(mods) as r:
        ready_cluster(r)
        case.assertEqual(outcome(r.run(through="controller", ca=None)), (3, "UNDETERMINED", "pre_apply_not_verified:webhook_ca_bundle"))


def rebundled(mods, edit):
    objects, report, _ = bundle()
    edit(objects)
    report["manifest_sha256"] = sha(objects)
    return run_for(mods, objects=objects, report=report, store_manifest=report["manifest_sha256"])


def scenario_bundle_image_locked(case, mods):
    def unlocked(objects):
        deployment = next(o for o in objects if o["kind"] == "Deployment"
                          and o["metadata"]["name"] == "aws-load-balancer-controller")
        deployment["spec"]["template"]["spec"]["containers"][0]["image"] = HOST + "test-dev-ecr-lbc@sha256:" + "a" * 64
    with rebundled(mods, unlocked) as r:
        ready_cluster_safe(r)
        case.assertEqual(outcome(r.run(through="controller")), (3, "UNDETERMINED", "digest_not_verified:bundle_image_not_locked"))
        assert_no_writes(case, r, "controller")


def ready_cluster_safe(r):
    """ready_cluster for a re-bundled run whose images may not be locked: image IDs are left unset."""
    try:
        ready_cluster(r)
    except StopIteration:
        pass


def scenario_dry_run_side_effects(case, mods):
    def side_effects(objects):
        webhook = next(o for o in objects if o["kind"] == "ValidatingWebhookConfiguration"
                       and o["metadata"]["name"] == "aws-load-balancer-controller-webhook")
        webhook["webhooks"][0]["sideEffects"] = "Some"
    with rebundled(mods, side_effects) as r:
        ready_cluster(r)
        case.assertEqual(outcome(r.run(through="controller")), (3, "UNDETERMINED", "dry_run_unsupported"))
        assert_no_writes(case, r, "controller")


def scenario_deployment_readiness(case, mods):
    def never(r):
        workload(r, "controller")["ready_after"] = None

    def stale(r):
        workload(r, "controller")["status"] = {"observedGeneration": 0, "replicas": 1, "updatedReplicas": 1,
                                               "readyReplicas": 1, "availableReplicas": 1,
                                               "conditions": [{"type": "Available", "status": "True"}]}

    def unavailable(r):
        workload(r, "controller")["status"] = {"observedGeneration": 1, "replicas": 1, "updatedReplicas": 1,
                                               "readyReplicas": 1, "availableReplicas": 1,
                                               "conditions": [{"type": "Available", "status": "False"}]}

    def pods(r):
        workload(r, "controller")["pods_ready"] = False

    def endpoints(r):
        r.adapter.endpoints[r.kind_key("controller", "Service")] = [
            {"ports": [{"port": 9443}], "endpoints": [{"addresses": ["10.0.0.1"], "conditions": {"ready": False}}]}]

    def wrong_port(r):
        r.adapter.endpoints[r.kind_key("controller", "Service")] = [
            {"ports": [{"port": 443}], "endpoints": [{"addresses": ["10.0.0.1"], "conditions": {"ready": True}}]}]
    for edit, reason in ((never, "deployment_not_ready"), (stale, "deployment_not_ready"),
                         (unavailable, "deployment_not_ready"), (pods, "pods_not_ready"),
                         (endpoints, "endpoints_not_ready"), (wrong_port, "endpoints_not_ready")):
        with run_for(mods) as r:
            ready_cluster(r)
            edit(r)
            started = r.clock.now()
            case.assertEqual(outcome(r.run(through="istiod")), (5, "READINESS_TIMEOUT", reason))
            case.assertGreaterEqual(r.clock.now() - started, 600)
            assert_no_writes(case, r, "istiod")  # stop before istiod


def scenario_istiod_endpoints(case, mods):
    with run_for(mods) as r:
        ready_cluster(r)
        r.adapter.endpoints[r.kind_key("istiod", "Service")] = [
            {"ports": [{"port": 15017}, {"port": 15010}], "endpoints": [{"addresses": ["10.0.0.2"], "conditions": {"ready": True}}]}]
        case.assertEqual(outcome(r.run(through="istiod")), (5, "READINESS_TIMEOUT", "endpoints_not_ready"))


def scenario_deployment_bound(case, mods):
    """D11: a Deployment ready at 590 s is accepted; the bound is 600 s, not shorter."""
    with run_for(mods) as r:
        ready_cluster(r)
        workload(r, "controller")["ready_after"] = 590
        case.assertEqual(r.run(through="controller")["exit_code"], 6)


def scenario_cabundle_population(case, mods):
    with run_for(mods) as r:
        ready_cluster(r)
        r.adapter.istiod_patches_cabundle = False
        result = r.run(through="istiod")
        case.assertEqual(outcome(result), (5, "READINESS_TIMEOUT", "cabundle_not_populated"))
        case.assertNotIn("fake_probe_F", result["evidence"])


def scenario_digests(case, mods):
    index, platform = lock_of("lbc")

    def image_id(value):
        def edit(r):
            workload(r, "controller")["image_ids"]["aws-load-balancer-controller"] = value
        return edit

    def arm_node(r):
        r.adapter.nodes.append(k8s_runtime_apply.fake_node("node-b", "ca-central-1a", "arm64"))
        workload(r, "controller")["node"] = "node-b"

    def spec_image(r):
        workload(r, "controller")["spec_images"] = {"aws-load-balancer-controller": HOST + "test-dev-ecr-lbc:latest"}
    cases = [(image_id(HOST + "test-dev-ecr-lbc@" + index), (3, "UNDETERMINED", "digest_not_verified:match_index")),
             (image_id(HOST + "test-dev-ecr-lbc@sha256:" + "b" * 64), (4, "APPLY_FAILED", "digest_mismatch")),
             (image_id(None), (3, "UNDETERMINED", "digest_not_verified:not_verified")),
             (image_id("docker-pullable://nonsense"), (3, "UNDETERMINED", "digest_not_verified:not_verified")),
             (arm_node, (3, "UNDETERMINED", "digest_not_verified:not_verified")),
             (spec_image, (4, "APPLY_FAILED", "digest_mismatch:spec_image"))]
    for edit, expected in cases:
        with run_for(mods) as r:
            ready_cluster(r)
            edit(r)
            case.assertEqual(outcome(r.run(through="istiod")), expected)
            assert_no_writes(case, r, "istiod")
    c = mods.apply.classify_image_digest
    case.assertEqual(c("x@" + platform, index, platform, "amd64"), "MATCH_PLATFORM")
    case.assertEqual(c("x@" + platform, index, platform, "arm64"), "NOT_VERIFIED")
    case.assertEqual(c("x@" + index, index, platform, "amd64"), "MATCH_INDEX")
    case.assertEqual(c("x@sha256:" + "c" * 64, index, platform, "amd64"), "digest_mismatch")
    case.assertEqual(c("x@sha256:short", index, platform, "amd64"), "NOT_VERIFIED")


def scenario_irsa_annotation(case, mods):
    with run_for(mods) as r:
        ready_cluster(r)
        target = r.kind_key("controller", "ServiceAccount")
        taint_after_write(r, target, lambda o: o["metadata"]["annotations"].pop("eks.amazonaws.com/role-arn"))
        case.assertEqual(outcome(r.run(through="controller")), (3, "UNDETERMINED", "irsa_annotation_differs"))


def scenario_controller_webhook_owned(case, mods):
    """A foreign manager takes the controller webhook caBundle (same value) before readiness: stop."""
    with run_for(mods) as r:
        ready_cluster(r)
        target = r.kind_key("controller", "ValidatingWebhookConfiguration")
        original = r.adapter.list_pods

        def taint(namespace, selector):
            obj = r.adapter.objects[target]
            if not any(m["manager"] == "cert-manager" for m in obj["metadata"]["managedFields"]):
                obj["metadata"]["managedFields"].append({"manager": "cert-manager", "operation": "Update", "fieldsV1": {
                    "f:webhooks": {'k:{"name":"vtargetgroupbinding.elbv2.k8s.aws"}': {"f:clientConfig": {"f:caBundle": {}}}}}})
            return original(namespace, selector)
        r.adapter.list_pods = taint
        case.assertEqual(outcome(r.run(through="controller")),
                         (4, "APPLY_FAILED", "controller_webhook_cabundle_not_runtime_owned"))


def scenario_probes(case, mods):
    cases = [("F", (500, 'Internal error: failed calling webhook "validation.istio.io"'), (3, "UNDETERMINED", "probe_F:webhook_unreachable")),
             ("F", (403, 'User "x" cannot create resource "peerauthentications"'), (4, "APPLY_FAILED", "probe_F:authz_denied")),
             ("F", (200, "{}"), (4, "APPLY_FAILED", "probe_F:allowed")),
             ("G", (200, injected_pod(HOST + "test-dev-ecr-istio-proxy@sha256:" + "d" * 64)), (4, "APPLY_FAILED", "probe_G:injection_missing")),
             ("G", (200, json.dumps({"spec": {"containers": [{"name": "app", "image": "x"}]}})), (4, "APPLY_FAILED", "probe_G:injection_missing")),
             ("G", (200, "not json"), (4, "APPLY_FAILED", "probe_G:injection_missing")),
             ("G", (403, 'admission webhook "rev.object.sidecar-injector.istio.io" denied the request'),
              (4, "APPLY_FAILED", "probe_G:webhook_denied:rev.object.sidecar-injector.istio.io"))]
    for name, answer, expected in cases:
        with run_for(mods) as r:
            ready_cluster(r)
            r.adapter.probes[name] = answer
            case.assertEqual(outcome(r.run(through="istiod")), expected)
    with run_for(mods) as r:
        ready_cluster(r)
        r.adapter.probes.clear()
        result = r.run(through="istiod")
        case.assertEqual(result["exit_code"], 6)
        case.assertEqual((result["evidence"]["fake_probe_F"], result["evidence"]["fake_probe_G"]), ("NOT_RUN", "NOT_RUN"))


def section10_objects():
    objects, _, _ = bundle()
    found = {(o["kind"], o["metadata"]["name"]): o for o in objects}
    return {"base": found[("ValidatingWebhookConfiguration", "istiod-default-validator")],
            "validator": found[("ValidatingWebhookConfiguration", "istio-validator-test-v1-istio-system")],
            "injector": found[("MutatingWebhookConfiguration", "istio-sidecar-injector-test-v1")],
            "lbc": found[("ValidatingWebhookConfiguration", "aws-load-balancer-controller-webhook")],
            "tgb": found[("TargetGroupBinding", "test-gateway")],
            "deployment": found[("Deployment", "istiod-test-v1")]}


def managed(manager, paths, operation="Update", subresource=None, fields=None):
    entry = {"manager": manager, "operation": operation, "fieldsType": "FieldsV1",
             "fieldsV1": fields if fields is not None else k8s_runtime_apply.fieldsv1_of(paths)}
    if subresource is not None:
        entry["subresource"] = subresource
    return entry


def section10_verdict(mods, manifest, *entries, edit=None, runtime="test-k8s-runtime"):
    """D13 on a live copy of ``manifest``: the runtime owns exactly its paths, plus ``entries``."""
    a = mods.apply
    live = copy.deepcopy(manifest)
    live["metadata"]["managedFields"] = [managed(runtime, a.required_paths(manifest), operation="Apply")] + list(entries)
    if edit:
        edit(live)
    return a.d13_ownership(a.observed_of(live, manifest), runtime)


def ca_path(name):
    return ("f:webhooks", 'k:{"name":"' + name + '"}', "f:clientConfig", "f:caBundle")


def fp_path(name):
    return ("f:webhooks", 'k:{"name":"' + name + '"}', "f:failurePolicy")


FINALIZER = ("f:metadata", "f:finalizers", 'v:"elbv2.k8s.aws/resources"')


def scenario_section10(case, mods):
    """Section 10, C1 and D13 by kind, object name, webhook name, manager, operation, subresource, path, value."""
    o = section10_objects()
    v = lambda manifest, *entries, **kw: section10_verdict(mods, manifest, *entries, **kw)  # noqa: E731
    NV, FF = "OWNERSHIP_NOT_VERIFIED", "FOREIGN_FIELD"
    istiod = lambda paths, **kw: managed("pilot-discovery", paths, **kw)  # noqa: E731
    lbc = lambda paths, **kw: managed("aws-load-balancer-controller", paths, **kw)  # noqa: E731

    def with_finalizers(*values):
        return lambda live: live["metadata"].__setitem__("finalizers", list(values))

    def set_policy(name, value):
        def edit(live):
            for w in live["webhooks"]:
                if w["name"] == name:
                    if value is None:
                        w.pop("failurePolicy", None)
                    else:
                        w["failurePolicy"] = value
        return edit
    # Inside the rows: NOT_VERIFIED (the manager names are unconfirmed), never OWNED.
    case.assertEqual(v(o["base"]), "OWNED")
    case.assertEqual(v(o["base"], istiod({ca_path("validation.istio.io")})), NV)
    case.assertEqual(v(o["validator"], istiod({ca_path("rev.validation.istio.io")})), NV)
    both = {ca_path("rev.namespace.sidecar-injector.istio.io"), ca_path("rev.object.sidecar-injector.istio.io")}
    case.assertEqual(v(o["injector"], istiod(both)), NV)
    case.assertEqual(v(o["injector"], istiod(both | {fp_path("rev.object.sidecar-injector.istio.io")})), NV)
    marked = {"f:webhooks": {".": {}, 'k:{"name":"validation.istio.io"}': {".": {}, "f:clientConfig": {"f:caBundle": {}}}}}
    case.assertEqual(v(o["base"], istiod(None, fields=marked)), NV)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER}), edit=with_finalizers("elbv2.k8s.aws/resources")), NV)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER}), managed("kube-controller", {("f:status", "f:conditions")},
                                                         subresource="status")), NV)
    # Object identity: kind, name, project and scope.
    case.assertEqual(v(o["lbc"], istiod({ca_path("vtargetgroupbinding.elbv2.k8s.aws")})), FF)
    case.assertEqual(v(o["base"], istiod({ca_path("validation.istio.io")}),
                       edit=lambda live: live.__setitem__("kind", "MutatingWebhookConfiguration")), FF)
    case.assertEqual(v(o["base"], istiod({ca_path("validation.istio.io")}),
                       edit=lambda live: live["metadata"].__setitem__("namespace", "istio-system")), FF)
    case.assertEqual(v(o["validator"], istiod({ca_path("rev.validation.istio.io")}), runtime="prod-k8s-runtime"), FF)
    case.assertEqual(v(o["deployment"], istiod({("f:spec", "f:replicas")})), FF)
    # Webhook names: fixed for the object, and present on the live object.
    case.assertEqual(v(o["base"], istiod({ca_path("other.istio.io")})), FF)
    case.assertEqual(v(o["base"], istiod({ca_path("rev.validation.istio.io")})), FF)
    case.assertEqual(v(o["injector"], istiod({ca_path("rev.object.sidecar-injector.istio.io")}),
                       edit=lambda live: live.__setitem__("webhooks", [w for w in live["webhooks"]
                                                                      if w["name"] != "rev.object.sidecar-injector.istio.io"])),
                     FF)
    # Paths and values.
    case.assertEqual(v(o["base"], istiod({ca_path("validation.istio.io") + ("f:extra",)})), FF)
    case.assertEqual(v(o["base"], istiod({("f:webhooks", 'k:{"name":"validation.istio.io"}', "f:clientConfig", "f:service")})), FF)
    case.assertEqual(v(o["base"], istiod({("f:webhooks", 'k:{"name":"validation.istio.io"}', "f:rules")})), FF)
    case.assertEqual(v(o["base"], istiod({("f:webhooks",)})), FF)
    case.assertEqual(v(o["base"], istiod(set())), FF)
    case.assertEqual(v(o["base"], istiod({fp_path("validation.istio.io")}), edit=set_policy("validation.istio.io", "Ignore")), FF)
    case.assertEqual(v(o["base"], istiod({fp_path("validation.istio.io")}), edit=set_policy("validation.istio.io", None)), FF)
    case.assertEqual(v(o["base"], istiod({fp_path("validation.istio.io")})), NV)
    # Manager, operation and subresource.
    case.assertEqual(v(o["base"], istiod({ca_path("validation.istio.io")}, operation="Apply")), FF)
    case.assertEqual(v(o["base"], istiod({ca_path("validation.istio.io")}, subresource="status")), FF)
    case.assertEqual(v(o["base"], lbc({ca_path("validation.istio.io")})), FF)
    case.assertEqual(v(o["base"], managed("istiod", {ca_path("validation.istio.io")})), FF)
    # C1: the runtime never owns an Istio caBundle; claiming it leaves ownership unproven.
    a = mods.apply
    claim = copy.deepcopy(o["base"])
    claim["metadata"]["managedFields"] = [managed("test-k8s-runtime", set(a.required_paths(o["base"]))
                                                  | {ca_path("validation.istio.io")}, operation="Apply")]
    case.assertEqual(a.d13_ownership(a.observed_of(claim, o["base"]), "test-k8s-runtime"), NV)
    # The controller row: TargetGroupBinding <project>-gateway in <project>-ingress, that finalizer only.
    case.assertEqual(v(o["tgb"], lbc({("f:metadata", "f:finalizers", 'v:"example.io/other"')})), FF)
    case.assertEqual(v(o["tgb"], lbc({("f:metadata", "f:finalizers")})), FF)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER, ("f:spec", "f:targetGroupARN")})), FF)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER}, operation="Apply")), FF)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER}), edit=lambda live: live["metadata"].__setitem__("name", "other")), FF)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER}), edit=lambda live: live["metadata"].__setitem__("namespace", "test-app")), FF)
    case.assertEqual(v(o["tgb"], edit=with_finalizers("example.io/other")), FF)
    case.assertEqual(v(o["tgb"], lbc({FINALIZER}), edit=with_finalizers("elbv2.k8s.aws/resources", "example.io/x")), FF)
    case.assertEqual(v(o["deployment"], lbc({("f:metadata", "f:finalizers", 'v:"elbv2.k8s.aws/resources"')})), FF)
    case.assertEqual(v(o["tgb"], istiod({FINALIZER})), FF)


def scenario_section10_malformed(case, mods):
    """Malformed evidence is never read as ownership: OWNERSHIP_NOT_VERIFIED, without a crash."""
    o = section10_objects()
    v = lambda manifest, *entries, **kw: section10_verdict(mods, manifest, *entries, **kw)  # noqa: E731
    NV = "OWNERSHIP_NOT_VERIFIED"
    a = mods.apply
    case.assertEqual(v(o["base"], managed("test-k8s-runtime", a.required_paths(o["base"]), operation="Apply")), NV)
    ca = {ca_path("validation.istio.io")}
    case.assertEqual(v(o["base"], managed("pilot-discovery", ca), managed("pilot-discovery", ca)), NV)
    case.assertEqual(v(o["base"], managed("kubectl", None, fields={"spec": {}})), NV)
    case.assertEqual(v(o["base"], managed("pilot-discovery", None, fields={"f:webhooks": {'k:{"name":"validation.istio.io"}': {
        "f:clientConfig": {"f:caBundle": "x"}}}}), managed("kubectl", None, fields={"f:spec": "x"})), NV)
    case.assertEqual(v(o["base"], managed("pilot-discovery", ca),
                       edit=lambda live: live["webhooks"].append(copy.deepcopy(live["webhooks"][0]))), NV)
    case.assertEqual(v(o["base"], managed("pilot-discovery", ca), edit=lambda live: live.__setitem__("webhooks", {"x": 1})), NV)
    case.assertEqual(v(o["base"], managed("pilot-discovery", ca),
                       edit=lambda live: live["webhooks"][0].pop("name")), NV)
    case.assertEqual(v(o["tgb"], edit=lambda live: live["metadata"].__setitem__("finalizers", "example.io/x")), NV)
    case.assertEqual(v(o["tgb"], edit=lambda live: live["metadata"].__setitem__("finalizers", [1])), NV)


def wrap_istiod(r, after):
    """Let the fake istiod act, then run ``after`` on the adapter (a race right after istiod writes)."""
    original = r.adapter._istiod_acts

    def acts():
        original()
        written = [o for o in r.adapter.objects.values() if any(
            isinstance(m, dict) and m.get("manager") == "pilot-discovery" for m in o["metadata"].get("managedFields") or [])]
        if len(written) == 3 and not state:  # once, right after istiod has written all three webhooks
            state.append(True)
            after(r.adapter)
    state = []
    r.adapter._istiod_acts = acts


def scenario_istio_webhooks_at_readiness(case, mods):
    """After istiod writes the caBundle, the Istio webhooks must keep failurePolicy Fail and stay in the row."""
    def ignore(adapter):
        obj = adapter.objects[istio_key_of(adapter, "istio-validator-test-v1-istio-system")]
        obj["webhooks"][0]["failurePolicy"] = "Ignore"
        entry = next(m for m in obj["metadata"]["managedFields"] if m["manager"] == "pilot-discovery")
        entry["fieldsV1"]["f:webhooks"]['k:{"name":"rev.validation.istio.io"}']["f:failurePolicy"] = {}

    def foreign_writer(adapter):
        for obj in adapter.objects.values():
            for m in obj["metadata"].get("managedFields") or []:
                if m.get("manager") == "pilot-discovery" and obj["metadata"]["name"] == "istiod-default-validator":
                    m["manager"] = "kubectl-patch"

    def wider(adapter):
        obj = adapter.objects[istio_key_of(adapter, "istio-sidecar-injector-test-v1")]
        entry = next(m for m in obj["metadata"]["managedFields"] if m["manager"] == "pilot-discovery")
        entry["fieldsV1"]["f:webhooks"]['k:{"name":"rev.object.sidecar-injector.istio.io"}']["f:rules"] = {}
    for after, expected in ((ignore, "istio_failure_policy_not_fail"), (foreign_writer, "foreign_field"),
                            (wider, "foreign_field")):
        with run_for(mods) as r:
            ready_cluster(r)
            wrap_istiod(r, after)
            result = r.run(through="istiod")
            case.assertEqual(outcome(result), (4, "APPLY_FAILED", expected))
            case.assertNotIn("fake_probe_F", result["evidence"])


def istio_key_of(adapter, name):
    """The webhook configuration called ``name`` (a ConfigMap shares the injector's name)."""
    return next(k for k, o in adapter.objects.items()
                if o["metadata"]["name"] == name and o["kind"] in k8s_runtime_apply.WEBHOOK_KINDS)


def scenario_section10_races(case, mods):
    """istiod's manager on a controller webhook is foreign at write time, after the write and on a rerun."""
    def istiod_on_lbc(obj):
        obj["metadata"]["managedFields"].append(managed("pilot-discovery", {ca_path("vtargetgroupbinding.elbv2.k8s.aws")}))
    with run_for(mods) as r:
        ready_cluster(r)
        target = r.kind_key("controller", "ValidatingWebhookConfiguration")
        taint_after_write(r, target, istiod_on_lbc)
        case.assertEqual(outcome(r.run(through="controller")), (4, "APPLY_FAILED", "foreign_field"))
        case.assertEqual([q["reason"] for q in records_for(r, target, "QUARANTINE")], ["ownership_unproven"])
        case.assertIsNone(owned_uid(r, target))
    with run_for(mods) as r:
        ready_cluster(r)
        target = r.kind_key("controller", "ValidatingWebhookConfiguration")
        r.adapter.conflicts.add(r.kind_key("controller", "ServiceAccount"))
        case.assertEqual(outcome(r.run(through="controller"))[2], "field_conflict")
        r.adapter.conflicts.clear()
        captured = {}

        def race(adapter):
            istiod_on_lbc(adapter.objects[target])
            captured["object"] = snapshot(r, target)
        r.adapter.before_write[target] = race
        case.assertEqual(outcome(r.run(through="controller", store=r.new_store())),
                         (4, "APPLY_FAILED", "foreign_field_refused"))
        case.assertEqual(snapshot(r, target), captured["object"])
    # Rerun after istiod: a caBundle entry in the row stops as NOT_VERIFIED; a value outside it as foreign.
    with run_for(mods) as r:
        ready_cluster(r)
        r.run(through="istiod")
        base = istio_key_of(r.adapter, "istiod-default-validator")
        obj = r.adapter.objects[base]
        obj["webhooks"][0]["failurePolicy"] = "Ignore"
        entry = next(m for m in obj["metadata"]["managedFields"] if m["manager"] == "pilot-discovery")
        entry["fieldsV1"]["f:webhooks"]['k:{"name":"validation.istio.io"}']["f:failurePolicy"] = {}
        r.adapter.calls.clear()
        case.assertEqual(outcome(r.run(through="istiod", store=r.new_store())), (4, "APPLY_FAILED", "foreign_field"))
        case.assertEqual(r.applies(), [])
    # Rerun with malformed evidence on a controller object (normally OWNED): NOT_VERIFIED, no write.
    with run_for(mods) as r:
        ready_cluster(r)
        r.run(through="controller")
        target = r.kind_key("controller", "MutatingWebhookConfiguration")
        obj = r.adapter.objects[target]
        obj["metadata"]["managedFields"].append(copy.deepcopy(runtime_entry(obj)))
        r.adapter.calls.clear()
        case.assertEqual(outcome(r.run(through="controller", store=r.new_store())),
                         (4, "APPLY_FAILED", "ownership_not_verified"))
        case.assertEqual(r.applies(), [])


def scenario_workload_read_scope(case, mods):
    with run_for(mods) as r:
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.get_secret_metadata("kube-system", "some-other-secret")
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.get_secret_metadata("test-app", "test-gateway-tls")
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.list_endpoint_slices("test-ingress", "some-other-service")
        with case.assertRaises(mods.apply.AdapterError):
            r.adapter.list_pods("kube-system", {"app": "anything"})


def scenario_istiod_after_controller_ready(case, mods):
    """The istiod stage never starts while the controller's in-stage readiness is unmet, even when closed."""
    with run_for(mods) as r:
        ready_cluster(r)
        r.run(through="controller")
        workload(r, "controller")["pods_ready"] = False
        case.assertEqual(outcome(r.run(through="istiod", store=r.new_store())), (5, "READINESS_TIMEOUT", "pods_not_ready"))
        assert_no_writes(case, r, "istiod")


def scenario_runtime_cabundle_claim(case, mods):
    """Defence behind D13: the runtime's own Apply entry must never own an Istio caBundle path."""
    objects, report, arn = bundle()
    with run_for(mods) as r:
        engine = mods.apply.Engine(report, objects, r.store, r.adapter, r.clock, arn)
        manifest = next(o for o in objects if o["metadata"]["name"] == "istiod-default-validator")
        live = copy.deepcopy(manifest)
        runtime = {"manager": "test-k8s-runtime", "operation": "Apply", "fieldsV1": {"f:webhooks": {}}}
        live["metadata"]["managedFields"] = [runtime]
        case.assertFalse(engine.runtime_claims_istio_cabundle(live, manifest))
        runtime["fieldsV1"] = {"f:webhooks": {'k:{"name":"validation.istio.io"}': {"f:clientConfig": {"f:caBundle": {}}}}}
        case.assertTrue(engine.runtime_claims_istio_cabundle(live, manifest))
        live["metadata"]["managedFields"] = {"manager": "test-k8s-runtime"}
        case.assertTrue(engine.runtime_claims_istio_cabundle(live, manifest))


# ---- Apply-B2: gateway ---------------------------------------------------------------------------------------------

def scenario_gateway_unreachable(case, mods):
    """Design 4.1: base validator serving is unproven after istiod (Live probe F, istiod's name), so the run
    stops before the gateway changes anything; it never becomes PASS or APPLIED."""
    with run_for(mods) as r:
        ready_cluster(r)
        result = r.run(through="gateway")
        case.assertEqual(outcome(result), (3, "UNDETERMINED", "deferred_readiness_unresolved:base_validator_serving"))
        assert_no_writes(case, r, "gateway")
        case.assertEqual([rec["stage"] for rec in r.journal() if rec["type"] == "STAGE_DONE"],
                         ["namespaces", "base", "controller", "istiod"])
        case.assertEqual([s["name"] for s in result["stages"]], ["namespaces", "base", "controller", "istiod"])
        case.assertNotIn("PASS", [s["final_acceptance"] for s in result["stages"]])
        case.assertEqual(result["evidence"]["istiod_in_stage_readiness"], "MET")
        case.assertIn(("secret_metadata", "test-ingress/test-gateway-tls"), r.adapter.calls)
        case.assertIn(("test-dev-ecr-istio-proxy", lock_of("istio-proxy")[0]), r.registry.calls)
        # A rerun cannot reach the gateway either: istiod's caBundle entry is NOT_VERIFIED (D13).
        r.adapter.calls.clear()
        case.assertEqual(outcome(r.run(through="gateway", store=r.new_store())), (4, "APPLY_FAILED", "ownership_not_verified"))
        case.assertEqual(r.applies(), [])
        assert_no_writes(case, r, "gateway")


def scenario_gateway_pre_apply(case, mods):
    """The gateway's own preconditions stop first, each before any gateway write."""
    with run_for(mods) as r:
        ready_cluster(r)
        del r.adapter.secrets[("test-ingress", "test-gateway-client-cacert")]
        case.assertEqual(outcome(r.run(through="gateway")),
                         (3, "UNDETERMINED", "pre_apply_not_verified:secret_absent:test-ingress/test-gateway-client-cacert"))
        assert_no_writes(case, r, "gateway")
    with run_for(mods) as r:
        ready_cluster(r)
        r.adapter.secrets[("test-ingress", "test-gateway-tls")] = dict(
            secret_metadata("test-ingress", "test-gateway-tls"), data={"tls.key": "c2VjcmV0"})
        result = r.run(through="gateway")
        case.assertEqual(outcome(result), (3, "UNDETERMINED", "secret_metadata_only_unsupported"))
        case.assertNotIn("c2VjcmV0", json.dumps(result))
    with run_for(mods) as r:
        ready_cluster(r)
        del r.registry.manifests[("test-dev-ecr-istio-proxy", lock_of("istio-proxy")[0])]
        case.assertEqual(outcome(r.run(through="gateway")),
                         (3, "UNDETERMINED", "pre_apply_not_verified:ecr_index_missing:istio-proxy"))
        assert_no_writes(case, r, "gateway")
    with run_for(mods) as r:
        ready_cluster(r)
        r.adapter.istiod_patches_cabundle = False
        case.assertEqual(outcome(r.run(through="gateway")), (5, "READINESS_TIMEOUT", "cabundle_not_populated"))
        assert_no_writes(case, r, "gateway")
    # Direct checks of the gate's first two conditions (unreachable through a normal run).
    with run_for(mods) as r:
        ready_cluster(r)
        r.run(through="istiod")
        engine = gateway_engine(mods, r)
        done = {"namespaces", "base", "controller", "istiod"}
        with case.assertRaises(mods.apply.ApplyStop) as stopped:
            engine.gateway_pre_apply(done)
        case.assertEqual(stopped.exception.reason, "pre_apply_not_verified:istiod_not_ready")
        engine.evidence["istiod_in_stage_readiness"] = "MET"
        injector = istio_key_of(r.adapter, "istio-sidecar-injector-test-v1")
        r.adapter.istiod_patches_cabundle = False
        r.adapter.objects[injector]["webhooks"][0]["clientConfig"].pop("caBundle")
        with case.assertRaises(mods.apply.ApplyStop) as stopped:
            engine.gateway_pre_apply(done)
        case.assertEqual(stopped.exception.reason, "pre_apply_not_verified:injector_cabundle")
        with case.assertRaises(mods.apply.ApplyStop) as stopped:
            engine.gateway_pre_apply(done - {"istiod"})
        case.assertEqual(stopped.exception.reason, "pre_apply_not_verified:istiod_not_ready")


def gateway_engine(mods, r):
    return mods.apply.Engine(r.report, r.objects, r.store, r.adapter, r.clock, r.arn, r.registry, r.ca)


def staged_gateway(mods, r):
    """Fake-only setup behind the gate: istiod ready, then the gateway objects placed in the fake as if applied."""
    ready_cluster(r)
    case_result = r.run(through="istiod")
    assert case_result["exit_code"] == 6, case_result
    for identity in r.members["gateway"]:
        r.adapter.server_side_apply(identity, r.manifest(k8s_runtime_receipt.key_of(identity)), "test-k8s-runtime",
                                    precondition={"absent": True})
    return gateway_engine(mods, r)


def scenario_gateway_contract(case, mods):
    """The gateway stage contract behind the gate: minimal completion, readiness, injection, digest, deferred."""
    with run_for(mods) as r:
        engine = staged_gateway(mods, r)
        for identity in r.members["gateway"]:
            engine.minimal_completion(identity)
        case.assertEqual(engine.in_stage_readiness("gateway"), "MET")
        case.assertEqual((engine.evidence.get("gateway_injection"), engine.evidence.get("gateway_digest")),
                         ("MET", "MATCH_PLATFORM"))
        deferred = mods.apply.outstanding_deferred("gateway", set(mods.apply.APPROVED_STAGES), engine.evidence)
        case.assertEqual([(d["resolved_by"], d["status"]) for d in deferred], [("ingress", "BLOCKED")])

    def no_status(r):
        workload(r, "gateway")["annotations"] = {}

    def empty_status(r):
        workload(r, "gateway")["annotations"] = {"sidecar.istio.io/status": ""}

    def other_proxy(r):
        workload(r, "gateway")["spec_images"] = {"istio-proxy": HOST + "test-dev-ecr-istio-proxy@sha256:" + "d" * 64}

    def index_digest(r):
        workload(r, "gateway")["image_ids"]["istio-proxy"] = HOST + "test-dev-ecr-istio-proxy@" + lock_of("istio-proxy")[0]

    def other_digest(r):
        workload(r, "gateway")["image_ids"]["istio-proxy"] = HOST + "test-dev-ecr-istio-proxy@sha256:" + "e" * 64

    def never(r):
        workload(r, "gateway")["ready_after"] = None

    def pods(r):
        workload(r, "gateway")["pods_ready"] = False
    cases = [(no_status, (4, "injection_missing")), (empty_status, (4, "injection_missing")),
             (other_proxy, (4, "injection_missing")), (index_digest, (3, "digest_not_verified:match_index")),
             (other_digest, (4, "digest_mismatch")), (never, (5, "deployment_not_ready")), (pods, (5, "pods_not_ready"))]
    for edit, expected in cases:
        with run_for(mods) as r:
            engine = staged_gateway(mods, r)
            edit(r)
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.in_stage_readiness("gateway")
            case.assertEqual((stopped.exception.exit_code, stopped.exception.reason), expected)
            case.assertNotIn("gateway_in_stage_readiness", engine.evidence)
    # Without the injector's caBundle the fake injects nothing, so injection is missing.
    with run_for(mods) as r:
        engine = staged_gateway(mods, r)
        workload(r, "gateway").pop("annotations", None)
        r.adapter.istiod_patches_cabundle = False
        r.adapter.objects[istio_key_of(r.adapter, "istio-sidecar-injector-test-v1")]["webhooks"][1]["clientConfig"].pop("caBundle")
        with case.assertRaises(mods.apply.ApplyStop) as stopped:
            engine.in_stage_readiness("gateway")
        case.assertEqual(stopped.exception.reason, "injection_missing")


# ---- Apply-B3: mesh_security ---------------------------------------------------------------------------------------

def scenario_mesh_unreachable(case, mods):
    """A run through mesh_security still stops at the gateway gate; neither stage is written."""
    with run_for(mods) as r:
        ready_cluster(r)
        result = r.run(through="mesh_security")
        case.assertEqual(outcome(result), (3, "UNDETERMINED", "deferred_readiness_unresolved:base_validator_serving"))
        assert_no_writes(case, r, "gateway")
        assert_no_writes(case, r, "mesh_security")
        case.assertNotIn("PASS", [s["final_acceptance"] for s in result["stages"]])


def scenario_mesh_gate(case, mods):
    """The mesh_security pre-apply gate itself: istiod readiness, then base validator serving."""
    with run_for(mods) as r:
        ready_cluster(r)
        r.run(through="istiod")
        engine = gateway_engine(mods, r)
        done = {"namespaces", "base", "controller", "istiod", "gateway"}
        for evidence, stages, reason in (({}, done, "pre_apply_not_verified:istiod_not_ready"),
                                         ({"istiod_in_stage_readiness": "MET"}, done - {"istiod"},
                                          "pre_apply_not_verified:istiod_not_ready"),
                                         ({"istiod_in_stage_readiness": "MET"}, done,
                                          "deferred_readiness_unresolved:base_validator_serving")):
            engine.evidence = dict(evidence)
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.pre_apply("mesh_security", stages)
            case.assertEqual((stopped.exception.exit_code, stopped.exception.reason), (3, reason))
        # Even with every fake-observable base requirement MET, the Live ones keep the gate shut.
        engine.evidence = {"istiod_in_stage_readiness": "MET", "base_validator_cabundle_populated": "MET",
                           "istiod_endpoints_ready": "MET", "istio_cabundle_manager_verified": "MET", "live_probe_F": "MET"}
        with case.assertRaises(mods.apply.ApplyStop) as stopped:
            engine.pre_apply("mesh_security", done)
        case.assertEqual(stopped.exception.reason, "deferred_readiness_unresolved:base_validator_serving")
        case.assertFalse(any(c[1] in stage_keys(r, "mesh_security") for c in r.adapter.calls if c[0] in ("apply", "dry_run")))


def place(r, keys):
    """Put bundle objects into the fake as the runtime would have applied them (fake-only test setup)."""
    for key in keys:
        identity = dict(zip(("apiVersion", "kind", "namespace", "name"), key.split("|")))
        r.adapter.server_side_apply(identity, r.manifest(key), "test-k8s-runtime", precondition={"absent": True})


def staged_mesh(mods, r):
    """Fake-only setup behind the gate: the five mesh_security objects placed as if applied. The stage's own
    checks read only these objects, so no earlier stage is run (the gate itself is tested separately)."""
    ready_cluster(r)
    for identity in r.members["mesh_security"]:
        r.adapter.server_side_apply(identity, r.manifest(k8s_runtime_receipt.key_of(identity)), "test-k8s-runtime",
                                    precondition={"absent": True})
    return gateway_engine(mods, r)


def stop_of(mods, call, *args):
    """The (exit, reason) of an ApplyStop from a direct engine call, or None; a stop is a contract result."""
    try:
        call(*args)
    except mods.apply.ApplyStop as stopped:
        return stopped.exit_code, stopped.reason
    return None


def mesh_key(r, kind):
    return r.kind_key("mesh_security", kind)


def scenario_mesh_contract(case, mods):
    """Behind the gate: minimal completion, ownership, no drift; enforcement stays NOT_TESTED, never PASS."""
    with run_for(mods) as r:
        engine = staged_mesh(mods, r)
        # Server-set extras on the live objects are not drift.
        r.adapter.objects[mesh_key(r, "NetworkPolicy")]["metadata"]["annotations"] = {"server": "set"}
        r.adapter.objects[mesh_key(r, "PeerAuthentication")]["status"] = {"observedGeneration": 1}
        for identity in r.members["mesh_security"]:
            case.assertIsNone(stop_of(mods, engine.minimal_completion, identity), identity["kind"])
        case.assertIsNone(stop_of(mods, engine.in_stage_readiness, "mesh_security"))
        case.assertEqual(engine.in_stage_readiness("mesh_security"), "MET")
        case.assertEqual(engine.evidence.get("mesh_security_no_drift"), "MET")
        deferred = mods.apply.outstanding_deferred("mesh_security", set(mods.apply.APPROVED_STAGES), engine.evidence)
        case.assertEqual([(d["resolved_by"], d["status"]) for d in deferred], [("traffic", "NOT_TESTED")])
        claimed = {"traffic_enforcement": "MET"}
        case.assertEqual(len(mods.apply.outstanding_deferred("mesh_security", set(), claimed)), 1)

    def edit(kind, change):
        def apply(r):
            change(r.adapter.objects[mesh_key(r, kind)])
        return apply
    drifts = [("PeerAuthentication", lambda o: o["spec"]["mtls"].__setitem__("mode", "PERMISSIVE"), "PeerAuthentication/test-strict-mtls"),
              ("AuthorizationPolicy", lambda o: o["spec"].__setitem__("rules", [{"from": [{}]}]), "AuthorizationPolicy/test-default-deny"),
              ("AuthorizationPolicy", lambda o: o["spec"].__setitem__("action", "DENY"), "AuthorizationPolicy/test-default-deny"),
              ("NetworkPolicy", lambda o: o["spec"].__setitem__("egress", [{}]), "NetworkPolicy/test-default-deny"),
              ("NetworkPolicy", lambda o: o["spec"].pop("ingress"), "NetworkPolicy/test-default-deny"),
              ("NetworkPolicy", lambda o: o["spec"].__setitem__("policyTypes", ["Ingress"]), "NetworkPolicy/test-default-deny"),
              ("ServiceAccount", lambda o: o.__setitem__("automountServiceAccountToken", True), "ServiceAccount/test-application")]
    for kind, change, where in drifts:
        with run_for(mods) as r:
            engine = staged_mesh(mods, r)
            edit(kind, change)(r)
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.in_stage_readiness("mesh_security")
            case.assertEqual((stopped.exception.exit_code, stopped.exception.reason), (4, "drift_detected:" + where))
            case.assertNotIn("mesh_security_in_stage_readiness", engine.evidence)
    ownership = [(lambda o: o["metadata"]["managedFields"].append(
                      {"manager": "kubectl-edit", "operation": "Update", "fieldsV1": {"f:spec": {"f:mtls": {"f:mode": {}}}}}),
                  (4, "foreign_field")),
                 (lambda o: o["metadata"]["managedFields"].remove(runtime_entry(o)), (4, "foreign_owner")),
                 (lambda o: o["metadata"].__setitem__("managedFields", "broken"), (4, "ownership_not_verified"))]
    for change, expected in ownership:
        with run_for(mods) as r:
            engine = staged_mesh(mods, r)
            change(r.adapter.objects[mesh_key(r, "PeerAuthentication")])
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.in_stage_readiness("mesh_security")
            case.assertEqual((stopped.exception.exit_code, stopped.exception.reason), expected)
    minimal = [("Namespace", lambda o: o["status"].__setitem__("phase", "Terminating"), (3, "namespace_not_active")),
               ("Namespace", lambda o: o["metadata"]["labels"].__setitem__("istio.io/rev", "other"), (3, "namespace_labels_differ"))]
    for kind, change, expected in minimal:
        with run_for(mods) as r:
            engine = staged_mesh(mods, r)
            change(r.adapter.objects[mesh_key(r, kind)])
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.minimal_completion(next(i for i in r.members["mesh_security"] if i["kind"] == kind))
            case.assertEqual((stopped.exception.exit_code, stopped.exception.reason), expected)
    for kind in ("PeerAuthentication", "AuthorizationPolicy", "NetworkPolicy"):
        with run_for(mods) as r:
            engine = staged_mesh(mods, r)
            del r.adapter.objects[mesh_key(r, kind)]
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.minimal_completion(next(i for i in r.members["mesh_security"] if i["kind"] == kind))
            case.assertEqual(stopped.exception.reason, "object_not_present")
            with case.assertRaises(mods.apply.ApplyStop) as stopped:
                engine.in_stage_readiness("mesh_security")
            case.assertEqual(stopped.exception.reason, "object_not_present")
    d = mods.apply.drift
    case.assertFalse(d({"a": 1, "b": 2}, {"a": 1}))
    case.assertTrue(d({"a": 1}, {"a": 1, "b": 2}))
    case.assertTrue(d({"a": [1, 2]}, {"a": [1]}))
    case.assertTrue(d({"a": "x"}, {"a": {"b": 1}}))
    case.assertFalse(d({"a": []}, {"a": []}))


# ---- Apply-B4: admission -------------------------------------------------------------------------------------------

def scenario_admission_unreachable(case, mods):
    """A run through admission still stops at the gateway gate; nothing from gateway onward is written."""
    with run_for(mods) as r:
        ready_cluster(r)
        result = r.run(through="admission")
        case.assertEqual(outcome(result), (3, "UNDETERMINED", "deferred_readiness_unresolved:base_validator_serving"))
        for stage in ("gateway", "mesh_security", "admission"):
            assert_no_writes(case, r, stage)
        case.assertNotIn("PASS", [s["final_acceptance"] for s in result["stages"]])
        case.assertFalse(any(c[0] == "probe" and c[1] in ("A", "A_prime", "B") for c in r.adapter.calls))


def staged_admission(mods, r):
    """Fake-only setup behind the gate: the TargetGroupBinding CRD and the four admission objects placed as if
    applied. The stage's own checks read only these objects and the fake probes, so no earlier stage is run."""
    ready_cluster(r)
    place(r, [mods.apply.TGB_CRD])
    for identity in r.members["admission"]:
        r.adapter.server_side_apply(identity, r.manifest(k8s_runtime_receipt.key_of(identity)), "test-k8s-runtime",
                                    precondition={"absent": True})
    return gateway_engine(mods, r)


def admission_identity(r, kind, name):
    return next(i for i in r.members["admission"] if i["kind"] == kind and i["name"] == name)


def scenario_admission_pre_apply(case, mods):
    with run_for(mods) as r:
        engine = staged_admission(mods, r)
        done = {"namespaces", "base", "controller", "istiod", "gateway", "mesh_security"}
        case.assertIsNone(stop_of(mods, engine.pre_apply, "admission", done))
        case.assertEqual(stop_of(mods, engine.pre_apply, "admission", done - {"controller"}),
                         (3, "pre_apply_not_verified:controller_not_accepted"))
        crd = mods.apply.TGB_CRD
        r.adapter.crd_ready_after[crd] = None
        case.assertEqual(stop_of(mods, engine.pre_apply, "admission", done),
                         (3, "pre_apply_not_verified:tgb_crd_not_established"))
        del r.adapter.objects[crd]
        case.assertEqual(stop_of(mods, engine.pre_apply, "admission", done),
                         (3, "pre_apply_not_verified:tgb_crd_not_established"))


def scenario_admission_contract(case, mods):
    """Behind the gate: type checking, Deny bindings, ownership, no drift, probes A/A'/B; never PASS."""
    with run_for(mods) as r:
        engine = staged_admission(mods, r)
        for identity in r.members["admission"]:
            case.assertIsNone(stop_of(mods, engine.minimal_completion, identity), identity["name"])
        case.assertIsNone(stop_of(mods, engine.in_stage_readiness, "admission"))
        case.assertEqual(engine.evidence.get("admission_in_stage_readiness"), "MET")
        case.assertEqual([engine.evidence.get("fake_probe_" + n) for n in ("A", "A_prime", "B")],
                         ["CLASSIFIED_FAKE_ONLY"] * 3)
        deferred = mods.apply.outstanding_deferred("admission", set(mods.apply.APPROVED_STAGES), engine.evidence)
        case.assertEqual([(d["status"], sorted(d["evidence"].values())) for d in deferred],
                         [("NOT_VERIFIED", ["NOT_VERIFIED"] * 3)])
        claimed = {"live_probe_A": "MET", "live_probe_A_prime": "MET", "live_probe_B": "MET"}
        left = mods.apply.outstanding_deferred("admission", set(), claimed)
        case.assertEqual([item["evidence"] for item in left], [{name: "NOT_VERIFIED" for name in claimed}])
    vap, binding = "ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding"
    minimal = [(vap, "test-no-lb-service", lambda r, k: r.adapter.policy_status.__setitem__(
                    k, {"typeChecking": {"expressionWarnings": [{"fieldRef": "spec.validations[0]", "warning": "x"}]}}),
                (4, "policy_type_warnings")),
               (vap, "test-target-registration", lambda r, k: r.adapter.policy_status.__setitem__(k, {}),
                (3, "policy_type_check_not_verified")),
               (vap, "test-target-registration", lambda r, k: r.adapter.policy_status.__setitem__(k, {"typeChecking": "x"}),
                (3, "policy_type_check_not_verified")),
               (binding, "test-no-lb-service", lambda r, k: r.adapter.objects[k]["spec"].__setitem__(
                    "validationActions", ["Audit"]), (4, "binding_not_deny")),
               (binding, "test-no-lb-service", lambda r, k: r.adapter.objects[k]["spec"].__setitem__(
                    "validationActions", ["Deny", "Warn"]), (4, "binding_not_deny")),
               (binding, "test-target-registration", lambda r, k: r.adapter.objects[k]["spec"].__setitem__(
                    "policyName", "test-no-lb-service"), (4, "binding_not_deny")),
               (binding, "test-target-registration", lambda r, k: r.adapter.objects.pop(k), (3, "object_not_present")),
               (vap, "test-no-lb-service", lambda r, k: r.adapter.objects.pop(k), (3, "object_not_present"))]
    for kind, name, change, expected in minimal:
        with run_for(mods) as r:
            engine = staged_admission(mods, r)
            identity = admission_identity(r, kind, name)
            change(r, k8s_runtime_receipt.key_of(identity))
            case.assertEqual(stop_of(mods, engine.minimal_completion, identity), expected, (kind, name))
    readiness = [(vap, "test-no-lb-service", lambda o: o["spec"].__setitem__("failurePolicy", "Ignore"),
                  (4, "drift_detected:ValidatingAdmissionPolicy/test-no-lb-service")),
                 (vap, "test-target-registration", lambda o: o["spec"]["validations"].pop(),
                  (4, "drift_detected:ValidatingAdmissionPolicy/test-target-registration")),
                 (binding, "test-no-lb-service", lambda o: o["metadata"]["managedFields"].append(
                     {"manager": "kubectl-edit", "operation": "Update", "fieldsV1": {"f:spec": {"f:validationActions": {}}}}),
                  (4, "foreign_field"))]
    for kind, name, change, expected in readiness:
        with run_for(mods) as r:
            engine = staged_admission(mods, r)
            change(r.adapter.objects[k8s_runtime_receipt.key_of(admission_identity(r, kind, name))])
            case.assertEqual(stop_of(mods, engine.in_stage_readiness, "admission"), expected)
            case.assertNotIn("admission_in_stage_readiness", engine.evidence)


def scenario_admission_probes(case, mods):
    """Section 11: each probe must be the whole 403 denial of exactly the expected policy, through its own
    binding, with one of its reviewed messages verbatim. Missing answers and every other outcome stop."""
    forbidden = 'services "probe" is forbidden: '
    cases = [
        # Missing or malformed answers: never ready.
        ("A", None, (3, "probe_A:not_run")),
        ("A_prime", None, (3, "probe_A_prime:not_run")),
        ("B", None, (3, "probe_B:not_run")),
        ("B", [403, vap_denial("test-target-registration", TGB_ONLY)], (3, "probe_B:unknown")),
        ("A", ("403", vap_denial("test-no-lb-service", NO_LB)), (3, "probe_A:unknown")),
        ("B", (403, None), (3, "probe_B:unknown")),
        # Wrong policy, wrong binding, altered messages.
        ("A", (403, vap_denial("test-target-registration", TGB_ONLY)), (4, "probe_A:vap_denied:test-target-registration")),
        ("B", (403, "ValidatingAdmissionPolicy 'test-target-registration' with binding 'test-no-lb-service' denied request: "
               + TGB_ONLY), (4, "probe_B:wrong_binding")),
        ("A_prime", (403, "ValidatingAdmissionPolicy 'test-no-lb-service' with binding 'other-binding' denied request: "
                     + NO_LB), (4, "probe_A_prime:wrong_binding")),
        ("A_prime", (403, vap_denial("test-no-lb-service", "some other text")), (4, "probe_A_prime:message_mismatch")),
        ("B", (403, vap_denial("test-target-registration", NO_LB)), (4, "probe_B:message_mismatch")),
        ("B", (403, vap_denial("test-target-registration", TGB_ONLY + " Also allowed.")), (4, "probe_B:message_mismatch")),
        ("B", (403, vap_denial("test-target-registration", TGB_ONLY[:-1])), (4, "probe_B:message_mismatch")),
        ("A", (403, vap_denial("test-no-lb-service", NO_LB.upper())), (4, "probe_A:message_mismatch")),
        # Not the whole text of a denial: substrings and extra lines are refused.
        ("A", (403, vap_denial("test-no-lb-service", NO_LB) + "\nadmission webhook \"x\" denied the request"),
         (4, "probe_A:denial_not_exact")),
        ("B", (403, "note: " + vap_denial("test-target-registration", TGB_ONLY)), (4, "probe_B:denial_not_exact")),
        ("B", (403, vap_denial("test-target-registration", TGB_ONLY) + " "), (4, "probe_B:message_mismatch")),
        ("A", (200, vap_denial("test-no-lb-service", NO_LB)), (4, "probe_A:allowed")),
        # Other kinds of refusal or outcome.
        ("A", (403, 'User "operator" cannot create resource "services"'), (4, "probe_A:authz_denied")),
        ("A", (201, "{}"), (4, "probe_A:allowed")),
        ("A_prime", (500, 'failed calling webhook "x"'), (3, "probe_A_prime:webhook_unreachable")),
        ("B", (403, 'admission webhook "vtargetgroupbinding.elbv2.k8s.aws" denied the request'),
         (4, "probe_B:webhook_denied:vtargetgroupbinding.elbv2.k8s.aws")),
        ("B", (422, "Invalid value"), (4, "probe_B:schema_invalid")),
        ("B", (403, "forbidden"), (3, "probe_B:unknown")),
        ("A", (400, "admission webhook has side effects and does not support dry run"), (3, "probe_A:dry_run_unsupported")),
    ]
    for name, answer, expected in cases:
        with run_for(mods) as r:
            engine = staged_admission(mods, r)
            if answer is None:
                r.adapter.probes.pop(name)
            else:
                r.adapter.probes[name] = answer
            case.assertEqual(stop_of(mods, engine.in_stage_readiness, "admission"), expected, (name, answer))
            case.assertNotIn("admission_in_stage_readiness", engine.evidence)
    # The real API's "<resource> "<name>" is forbidden: " prefix is accepted with the exact rest.
    with run_for(mods) as r:
        engine = staged_admission(mods, r)
        r.adapter.probes["A"] = (403, forbidden + vap_denial("test-no-lb-service", NO_LB))
        case.assertIsNone(stop_of(mods, engine.in_stage_readiness, "admission"))
        case.assertEqual(engine.evidence.get("admission_in_stage_readiness"), "MET")
        case.assertEqual(len(mods.apply.outstanding_deferred("admission", set(), engine.evidence)), 1)
    parse = mods.apply.parse_vap_denial
    case.assertEqual(parse(403, vap_denial("p", "m")), ("p", "p", "m"))
    case.assertIsNone(parse(403, vap_denial("p", "m") + "\nx"))
    case.assertIsNone(parse(401, vap_denial("p", "m")))
    case.assertIsNone(parse(403, "x " + vap_denial("p", "m")))


# ---- Apply-B5: binding_writer --------------------------------------------------------------------------------------

def scenario_binding_writer_unreachable(case, mods):
    """A run through binding_writer still stops at the gateway gate; ingress stays refused."""
    with run_for(mods) as r:
        ready_cluster(r)
        r.adapter.probes.update({"C": (201, "{}"), "D": (201, "{}"), "E": (201, "{}")})
        result = r.run(through="binding_writer")
        case.assertEqual(outcome(result), (3, "UNDETERMINED", "deferred_readiness_unresolved:base_validator_serving"))
        for stage in ("gateway", "mesh_security", "admission", "binding_writer"):
            assert_no_writes(case, r, stage)
        case.assertFalse(any(c[0] == "probe" for c in r.adapter.calls if c[1] in ("C", "D", "E")))
        case.assertEqual(outcome(r.run(through="ingress")), (1, "REFUSED", "stage_not_approved:ingress"))


def staged_binding_writer(mods, r):
    """Fake-only setup behind the gate: the admission objects (and the TargetGroupBinding CRD they need) and the
    three binding_writer objects placed as if applied; no earlier stage is run."""
    ready_cluster(r)
    place(r, [mods.apply.TGB_CRD] + [k8s_runtime_receipt.key_of(i) for i in r.members["admission"]]
          + [k8s_runtime_receipt.key_of(i) for i in r.members["binding_writer"]])
    return gateway_engine(mods, r)


def writer_key(r, kind):
    return r.kind_key("binding_writer", kind)


def scenario_binding_writer_pre_apply(case, mods):
    """Pre-apply re-verifies the admission minimal completion on the live objects."""
    done = {"namespaces", "base", "controller", "istiod", "gateway", "mesh_security", "admission"}
    with run_for(mods) as r:
        engine = staged_binding_writer(mods, r)
        case.assertIsNone(stop_of(mods, engine.pre_apply, "binding_writer", done))
        case.assertEqual(stop_of(mods, engine.pre_apply, "binding_writer", done - {"admission"}),
                         (3, "pre_apply_not_verified:admission_not_accepted"))
    vap = "admissionregistration.k8s.io/v1|ValidatingAdmissionPolicy||test-no-lb-service"
    binding = "admissionregistration.k8s.io/v1|ValidatingAdmissionPolicyBinding||test-target-registration"
    cases = [(lambda r: r.adapter.policy_status.__setitem__(vap, {"typeChecking": {"expressionWarnings": [{"warning": "x"}]}}),
              (4, "policy_type_warnings")),
             (lambda r: r.adapter.policy_status.__setitem__(vap, {}), (3, "policy_type_check_not_verified")),
             (lambda r: r.adapter.objects[binding]["spec"].__setitem__("validationActions", ["Warn"]), (4, "binding_not_deny")),
             (lambda r: r.adapter.objects.pop(binding), (3, "object_not_present"))]
    for edit, expected in cases:
        with run_for(mods) as r:
            engine = staged_binding_writer(mods, r)
            edit(r)
            case.assertEqual(stop_of(mods, engine.pre_apply, "binding_writer", done), expected)


def scenario_binding_writer_contract(case, mods):
    """Behind the gate: present, owned, no drift, automount false; D1 items NOT_TESTED, never PASS."""
    with run_for(mods) as r:
        engine = staged_binding_writer(mods, r)
        r.adapter.probes.update({"C": (201, "{}"), "D": (201, "{}"), "E": (201, "{}")})
        for identity in r.members["binding_writer"]:
            case.assertIsNone(stop_of(mods, engine.minimal_completion, identity), identity["kind"])
        case.assertIsNone(stop_of(mods, engine.in_stage_readiness, "binding_writer"))
        case.assertEqual(engine.evidence.get("binding_writer_in_stage_readiness"), "MET")
        case.assertFalse(any(c[0] == "probe" for c in r.adapter.calls), "no probe C to E is sent or read")
        left = mods.apply.outstanding_deferred("binding_writer", set(mods.apply.APPROVED_STAGES), engine.evidence)
        case.assertEqual([(d["resolved_by"], d["status"]) for d in left], [("D1", "NOT_TESTED")])
        claimed = {name: "MET" for name in mods.apply.BINDING_WRITER_D1}
        left = mods.apply.outstanding_deferred("binding_writer", set(), claimed)
        case.assertEqual([item["evidence"] for item in left], [{name: "NOT_TESTED" for name in claimed}])
    sa = "ServiceAccount"
    minimal = [(sa, lambda o: o.__setitem__("automountServiceAccountToken", True), (4, "sa_automount_token_not_false")),
               (sa, lambda o: o.pop("automountServiceAccountToken"), (4, "sa_automount_token_not_false")),
               (sa, lambda o: o.__setitem__("automountServiceAccountToken", "false"), (4, "sa_automount_token_not_false")),
               (sa, lambda o: o.__setitem__("automountServiceAccountToken", 0), (4, "sa_automount_token_not_false"))]
    for kind, change, expected in minimal:
        with run_for(mods) as r:
            engine = staged_binding_writer(mods, r)
            change(r.adapter.objects[writer_key(r, kind)])
            identity = next(i for i in r.members["binding_writer"] if i["kind"] == kind)
            case.assertEqual(stop_of(mods, engine.minimal_completion, identity), expected)
    for kind in (sa, "Role", "RoleBinding"):
        with run_for(mods) as r:
            engine = staged_binding_writer(mods, r)
            del r.adapter.objects[writer_key(r, kind)]
            identity = next(i for i in r.members["binding_writer"] if i["kind"] == kind)
            case.assertEqual(stop_of(mods, engine.minimal_completion, identity), (3, "object_not_present"))
            case.assertEqual(stop_of(mods, engine.in_stage_readiness, "binding_writer"), (3, "object_not_present"))
    readiness = [
        ("Role", lambda o: o["rules"][0]["verbs"].append("list"), (4, "drift_detected:Role/test-binding-writer")),
        ("Role", lambda o: o["rules"][1]["resourceNames"].append("other"), (4, "drift_detected:Role/test-binding-writer")),
        ("Role", lambda o: o["rules"].pop(), (4, "drift_detected:Role/test-binding-writer")),
        ("RoleBinding", lambda o: o["subjects"][0].__setitem__("name", "default"), (4, "drift_detected:RoleBinding/test-binding-writer")),
        ("RoleBinding", lambda o: o["roleRef"].__setitem__("kind", "ClusterRole"), (4, "drift_detected:RoleBinding/test-binding-writer")),
        (sa, lambda o: o.__setitem__("automountServiceAccountToken", True), (4, "drift_detected:ServiceAccount/test-binding-writer")),
        ("Role", lambda o: o["metadata"]["managedFields"].append(
            {"manager": "kubectl-edit", "operation": "Update", "fieldsV1": {"f:rules": {}}}), (4, "foreign_field")),
        ("RoleBinding", lambda o: o["metadata"]["managedFields"].remove(runtime_entry(o)), (4, "foreign_owner")),
        (sa, lambda o: o["metadata"].__setitem__("managedFields", {"broken": True}), (4, "ownership_not_verified"))]
    for kind, change, expected in readiness:
        with run_for(mods) as r:
            engine = staged_binding_writer(mods, r)
            change(r.adapter.objects[writer_key(r, kind)])
            case.assertEqual(stop_of(mods, engine.in_stage_readiness, "binding_writer"), expected, kind)
            case.assertNotIn("binding_writer_in_stage_readiness", engine.evidence)


def scenario_binding_writer_conflict(case, mods):
    """A field conflict on a binding_writer write is never forced: failed RESULT and stop."""
    with run_for(mods) as r:
        ready_cluster(r)
        engine = gateway_engine(mods, r)
        target = writer_key(r, "Role")
        r.adapter.conflicts.add(target)
        identity = next(i for i in r.members["binding_writer"] if i["kind"] == "Role")
        with r.store.lock():
            r.store.begin()
            # Receipt-level setup only: stages 1 to 7 recorded as applied, so a stage 8 INTENT is in order.
            serial = 0
            for stage in r.plan.stage_order[:r.plan.stage_order.index("binding_writer")]:
                for key in r.plan.members[stage]:
                    member = dict(zip(("apiVersion", "kind", "namespace", "name"), key.split("|")))
                    serial += 1
                    seq = r.store.intent(stage, member, {"state": "absent"}, "create")
                    r.store.result(seq, member, "00000000-0000-4000-9000-%012x" % serial, "1", 1, "applied")
                r.store.stage_done(stage)
            state = mods.receipt.load(r.store.dir, r.plan, r.store.expected)["state"]
            case.assertEqual(stop_of(mods, engine.apply_object, "binding_writer", identity, state), (4, "field_conflict"))
        case.assertNotIn(target, r.adapter.objects)
        case.assertEqual(records_for(r, target, "RESULT")[-1]["outcome"], "failed")


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

    def test_ownership_proven_before_success_result(self):
        scenario_foreign_field_during_apply(self, real_mods())
        scenario_runtime_fields_short_after_apply(self, real_mods())

    def test_landed_write_never_reverts_to_not_applied(self):
        scenario_uid_changed_after_apply(self, real_mods())
        scenario_crash_before_success_result(self, real_mods())

    def test_write_refused_when_foreign_manager_appears(self):
        scenario_foreign_manager_before_write(self, real_mods())

    def test_status_update_allowed_at_write(self):
        scenario_status_update_allowed(self, real_mods())

    def test_write_refused_missing_managed_fields(self):
        scenario_write_refused_missing_managed_fields(self, real_mods())

    def test_write_refused_missing_runtime_entry(self):
        scenario_write_refused_missing_runtime_entry(self, real_mods())

    def test_write_refused_partial_runtime_ownership(self):
        scenario_write_refused_partial_runtime(self, real_mods())

    def test_write_refused_malformed_ownership(self):
        scenario_write_refused_malformed(self, real_mods())

    # Apply-B1: controller and istiod.
    def test_through_istiod_is_deferred(self):
        scenario_through_istiod(self, real_mods())

    def test_through_controller_and_rerun(self):
        scenario_through_controller(self, real_mods())

    def test_rerun_after_istiod_stops(self):
        scenario_rerun_after_istiod(self, real_mods())
        scenario_istiod_patches_before_readback(self, real_mods())

    def test_secret_preconditions(self):
        scenario_secret_presence(self, real_mods())
        scenario_secret_metadata_only(self, real_mods())
        scenario_secret_registration(self, real_mods())

    def test_registry_preconditions(self):
        scenario_registry_evidence(self, real_mods())
        scenario_registry_digests(self, real_mods())
        scenario_bundle_image_locked(self, real_mods())

    def test_node_and_ca_preconditions(self):
        scenario_nodes(self, real_mods())
        scenario_bundle_ca(self, real_mods())
        scenario_dry_run_side_effects(self, real_mods())

    def test_workload_readiness(self):
        scenario_deployment_readiness(self, real_mods())
        scenario_istiod_endpoints(self, real_mods())
        scenario_deployment_bound(self, real_mods())
        scenario_cabundle_population(self, real_mods())
        scenario_istiod_after_controller_ready(self, real_mods())

    def test_digest_classification(self):
        scenario_digests(self, real_mods())

    def test_workload_ownership(self):
        scenario_irsa_annotation(self, real_mods())
        scenario_controller_webhook_owned(self, real_mods())

    def test_section10_rows(self):
        scenario_section10(self, real_mods())

    def test_section10_malformed_evidence(self):
        scenario_section10_malformed(self, real_mods())

    def test_section10_races_and_reruns(self):
        scenario_istio_webhooks_at_readiness(self, real_mods())
        scenario_section10_races(self, real_mods())

    def test_fake_probes(self):
        scenario_probes(self, real_mods())

    # Apply-B2: gateway.
    def test_gateway_unreachable(self):
        scenario_gateway_unreachable(self, real_mods())

    def test_gateway_pre_apply(self):
        scenario_gateway_pre_apply(self, real_mods())

    def test_gateway_contract(self):
        scenario_gateway_contract(self, real_mods())

    # Apply-B3: mesh_security.
    def test_mesh_unreachable(self):
        scenario_mesh_unreachable(self, real_mods())

    def test_mesh_gate(self):
        scenario_mesh_gate(self, real_mods())

    def test_mesh_contract(self):
        scenario_mesh_contract(self, real_mods())

    # Apply-B4: admission.
    def test_admission_unreachable(self):
        scenario_admission_unreachable(self, real_mods())

    def test_admission_pre_apply(self):
        scenario_admission_pre_apply(self, real_mods())

    def test_admission_contract(self):
        scenario_admission_contract(self, real_mods())

    def test_admission_probes(self):
        scenario_admission_probes(self, real_mods())

    # Apply-B5: binding_writer.
    def test_binding_writer_unreachable(self):
        scenario_binding_writer_unreachable(self, real_mods())

    def test_binding_writer_pre_apply(self):
        scenario_binding_writer_pre_apply(self, real_mods())

    def test_binding_writer_contract(self):
        scenario_binding_writer_contract(self, real_mods())
        scenario_binding_writer_conflict(self, real_mods())

    def test_workload_read_scope(self):
        scenario_workload_read_scope(self, real_mods())
        scenario_runtime_cabundle_claim(self, real_mods())

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

    def test_incomplete_ownership_rejected_consistent_and_reapply(self):
        scenario_incomplete_ownership_consistent(self, real_mods())
        scenario_incomplete_ownership_reapply(self, real_mods())

    def test_foreign_object_never_modified(self):
        scenario_foreign_appears_before_apply(self, real_mods())
        scenario_replaced_before_write(self, real_mods())
        scenario_update_uid_mismatch(self, real_mods())

    def test_conditional_writes(self):
        scenario_owned_update_succeeds(self, real_mods())
        scenario_write_needs_precondition(self, real_mods())

    def test_deferred_needs_evidence(self):
        scenario_deferred_needs_evidence(self, real_mods())

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
    ("result_after_ownership", A, '            self.store.quarantine(identity, meta.get("uid"), "ownership_unproven")\n',
     '            self.store.result(seq, identity, meta["uid"], "1", 1, "applied")\n', scenario_runtime_fields_short_after_apply),
    ("success_result_first", A, "        owned = d13_ownership(observed_of(after, self.manifest(identity)), self.manager)\n",
     '        self.store.result(seq, identity, meta["uid"], "1", 1, "applied")\n'
     "        owned = d13_ownership(observed_of(after, self.manifest(identity)), self.manager)\n",
     scenario_foreign_field_during_apply),
    ("uid_after_apply_quarantine", A, '            self.store.quarantine(identity, meta.get("uid"), "uid_changed")\n',
     '            self.store.result(seq, identity, None, None, None, "failed")\n', scenario_uid_changed_after_apply),
    ("uid_after_apply_check", A, '        if recorded is not None and meta.get("uid") != recorded:\n            self.store.quarantine',
     '        if False:\n            self.store.quarantine', scenario_uid_changed_after_apply),
    ("fake_ownership_check", A, '            if verdict != "OWNED":\n                raise OwnershipRefused(verdict)',
     "            pass", scenario_write_time_ownership),
    ("fake_status_allowance", A, "            verdict = d13_ownership(observed_of(current, manifest), field_manager)",
     '            verdict = d13_ownership(dict(observed_of(current, manifest), kind="Namespace"), field_manager)',
     scenario_status_update_allowed),
    # The reviewed f01f5e2 defect: the runtime's own entry skipped by name, only other managers checked.
    ("fake_runtime_entry_skipped", A, "            verdict = d13_ownership(observed_of(current, manifest), field_manager)",
     '            verdict = "OWNED" if all(m.get("manager") == field_manager or status_only('
     '{"subresource": m.get("subresource", ""), "operation": m.get("operation"), '
     '"paths": frozenset(paths_of(m.get("fieldsV1") or {}))}, current["kind"]) '
     'for m in current["metadata"].get("managedFields") or []) else "FOREIGN_FIELD"',
     scenario_write_refused_runtime_lost),
    ("fake_missing_runtime_accepted", A, "        if current is not None:\n            verdict = d13_ownership",
     '        if current is not None and any(m.get("manager") == field_manager '
     'for m in current["metadata"].get("managedFields") or []):\n            verdict = d13_ownership',
     scenario_write_refused_missing_runtime_entry),
    ("fake_incomplete_paths_accepted", A, '            if verdict != "OWNED":',
     '            if verdict not in ("OWNED", "OWNERSHIP_NOT_VERIFIED"):', scenario_write_refused_partial_runtime),
    ("fake_manager_name_only", A, "            verdict = d13_ownership(observed_of(current, manifest), field_manager)",
     '            verdict = "OWNED" if any(m.get("manager") == field_manager '
     'for m in current["metadata"].get("managedFields") or []) else "NOT_OWNED"',
     scenario_write_refused_partial_runtime),
    ("malformed_evidence_accepted", A, '    if observed.get("malformed"):\n        return "OWNERSHIP_NOT_VERIFIED"\n', "",
     scenario_write_refused_malformed),
    ("write_refusal_reason", A, '"NOT_OWNED": "not_owned_refused"', '"NOT_OWNED": "foreign_field_refused"',
     scenario_write_refused_missing_managed_fields),
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
    ("d13_status_fields", A, '            and bool(paths) and all(path and path[0] == "f:status" for path in paths))',
     "            and bool(paths))", scenario_d13),
    ("d13_required_fields", A, '    if not required or owned != set(required):', "    if False:", scenario_incomplete_ownership_consistent),
    ("d13_required_reapply", A, '    if not required or owned != set(required):', "    if not required:",
     scenario_incomplete_ownership_reapply),
    ("d13_nested_collapse", A, '            paths |= paths_of(item, prefix + (key,))', '            paths |= {prefix + (key,)}',
     scenario_d13),
    ("foreign_appeared_check", A, '        if recorded is None and live is not None:\n            stop(4, "foreign_object_appeared")',
     "", scenario_foreign_appears_before_apply),
    ("fake_absent_precondition", A, '        if precondition.get("absent") and current is not None:\n            raise PreconditionFailed("object_exists")',
     "", scenario_replaced_before_write),
    ("fake_uid_precondition", A, '        if "uid" in precondition and (current is None or current["metadata"].get("uid") != precondition["uid"]):\n            raise PreconditionFailed("uid_mismatch")',
     "", scenario_update_uid_mismatch),
    ("engine_precondition_value", A, '        precondition = {"uid": recorded} if recorded is not None else {"absent": True}',
     '        precondition = {"absent": True}', scenario_owned_update_succeeds),
    ("fake_precondition_required", A, '            raise AdapterError("precondition_required")', "            pass",
     scenario_write_needs_precondition),
    ("deferred_by_stage_done", A, '        if all(value == "MET" for value in status.values()):',
     '        if item["resolved_by"] in done:', scenario_deferred_needs_evidence),
    ("d13_unverified", A, '            verdict = "OWNERSHIP_NOT_VERIFIED"\n            continue', "            continue",
     scenario_section10),
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
    # Apply-B1: controller and istiod.
    ("registry_gate", A, "        if self.registry is not None and (not isinstance(self.registry, FakeRegistry)",
     "        if False and (not isinstance(self.registry, FakeRegistry)", scenario_registry_evidence),
    ("registry_required", A, '            stop(3, "pre_apply_not_verified:ecr_evidence_unavailable")', "            return",
     scenario_registry_evidence),
    ("ecr_index_kind", A, '            if not isinstance(found, dict) or found.get("kind") != "index":',
     "            if not isinstance(found, dict):", scenario_registry_digests),
    ("ecr_platform_child", A, '            if (found.get("platforms") or {}).get(REQUIRED_PLATFORM) != entry["platform"]:',
     "            if False:", scenario_registry_digests),
    ("bundle_image_locked", A, '        stop(3, "digest_not_verified:bundle_image_not_locked")',
     '        return {"purpose": "unlocked", "repository": repository, "index": digest, "platform": digest}',
     scenario_bundle_image_locked),
    ("secret_check_call", A, "            self.check_secrets(stage)\n", "", scenario_secret_presence),
    ("secret_absent", A, '                stop(3, "pre_apply_not_verified:secret_absent:" + where)', "                continue",
     scenario_secret_presence),
    ("secret_metadata_only", A, "            if not metadata_only(response):", "            if False:",
     scenario_secret_metadata_only),
    ("secret_data_key", A, 'and "data" not in response', "and True", scenario_secret_metadata_only),
    ("secret_manager", A, '                    or labels.get("app.kubernetes.io/part-of") != project or not registered:',
     '                    or labels.get("app.kubernetes.io/part-of") != project:', scenario_secret_registration),
    ("secret_label", A, 'labels.get("app.kubernetes.io/managed-by") != "k8s_certs.py"', "False", scenario_secret_registration),
    ("node_architecture", A, "                                   == NODE_ARCHITECTURE for n in nodes):",
     "                                   is not None for n in nodes):", scenario_nodes),
    ("node_ready", A, "            if not zone or not any(node_ready(n) and", "            if not zone or not any(True and",
     scenario_nodes),
    ("bundle_ca", A, '                    if webhook.get("clientConfig", {}).get("caBundle") != self.webhook_ca_bundle:',
     "                    if False:", scenario_bundle_ca),
    ("dry_run_side_effects_gate", A, "        if not dry_run_permitted(webhooks):", "        if False:",
     scenario_dry_run_side_effects),
    ("deployment_available", A, '    return (conditions_true(obj, ("Available",)) and isinstance(generation, int)',
     "    return (isinstance(generation, int)", scenario_deployment_readiness),
    ("observed_generation", A, "            and observed >= generation\n", "", scenario_deployment_readiness),
    ("pods_ready", A, '            if len(pods) != manifest["spec"].get("replicas", 1) or not all(pod_ready(p) for p in pods):',
     '            if len(pods) != manifest["spec"].get("replicas", 1):', scenario_deployment_readiness),
    ("endpoints_check", A, '            if identity["kind"] == "Service" and stage in ENDPOINT_PORTS and not self.endpoints_ready(stage, identity):',
     "            if False:", scenario_deployment_readiness),
    ("endpoint_ready_flag", A, 'if any((e.get("conditions") or {}).get("ready") is True for e in piece.get("endpoints") or []):',
     "if True:", scenario_deployment_readiness),
    ("deployment_timeout_value", A, "DEPLOYMENT_READY_TIMEOUT_SECONDS = 600", "DEPLOYMENT_READY_TIMEOUT_SECONDS = 60",
     scenario_deployment_bound),
    ("readiness_before_next_stage", A, '                row["in_stage_readiness"] = self.in_stage_readiness(stage)',
     '                row["in_stage_readiness"] = "MET"', scenario_deployment_readiness),
    ("cabundle_wait", A, '        if stage == "istiod" and not all(', "        if False and not all(",
     scenario_cabundle_population),
    ("digest_match_index", A, '    if digest == index_digest:\n        return "MATCH_INDEX"',
     '    if digest == index_digest:\n        return "MATCH_PLATFORM"', scenario_digests),
    ("digest_mismatch_stop", A, '                    if verdict == "digest_mismatch":\n                        stop(4, "digest_mismatch")',
     '                    if verdict == "digest_mismatch":\n                        continue', scenario_digests),
    ("digest_node_architecture", A, '        return "MATCH_PLATFORM" if node_architecture == NODE_ARCHITECTURE else "NOT_VERIFIED"',
     '        return "MATCH_PLATFORM"', scenario_digests),
    ("digest_spec_image", A, '                    stop(4, "digest_mismatch:spec_image")', "                    pass", scenario_digests),
    ("irsa_annotation", A, '                stop(3, "irsa_annotation_differs")', "                pass", scenario_irsa_annotation),
    ("controller_webhook_owned", A,
     '                if obj is None or d13_ownership(observed_of(obj, manifest), self.manager) != "OWNED" or \\',
     "                if obj is None or \\", scenario_controller_webhook_owned),
    ("probe_class", A, "        if outcome not in expected:", "        if False:", scenario_probes),
    ("probe_injection", A, '        if name == "G" and not self.injected(body):', "        if False:", scenario_probes),
    ("live_requirements_fixed", A, 'FIXED_REQUIREMENTS.get(req, evidence.get(req, "NOT_VERIFIED"))',
     'evidence.get(req, FIXED_REQUIREMENTS.get(req, "NOT_VERIFIED"))', scenario_deferred_needs_evidence),
    ("istio_manager_evidence", A, '"NOT_VERIFIED" if in_row and owners == {(ISTIOD_MANAGER, "Update")} else "NOT_MET")',
     '"MET" if in_row and owners == {(ISTIOD_MANAGER, "Update")} else "NOT_MET")', scenario_through_istiod),
    ("section10_rows", A, "        if entry.get(\"manager\") in UNVERIFIED_MANAGERS and within_section10(entry, observed, project):",
     "        if entry.get(\"manager\") in UNVERIFIED_MANAGERS:", scenario_section10),
    ("section10_webhook_names", A, '            if len(path) < 3 or path[0] != "f:webhooks" or path[1] not in keys:',
     '            if len(path) < 3 or path[0] != "f:webhooks":', scenario_section10),
    # D13 section 10 audit: every element of the rows is pinned by its own mutant.
    ("istiod_object_allowlist", A, '        fixed = istio_webhooks(project).get((observed.get("kind"), observed.get("name")))',
     "        fixed = set().union(*istio_webhooks(project).values())", scenario_section10),
    ("istiod_cluster_scoped", A, '        if fixed is None or observed.get("namespace"):', "        if fixed is None:",
     scenario_section10),
    ("istiod_live_webhook", A, "        keys = {webhook_key(name): name for name in fixed if name in live}",
     "        keys = {webhook_key(name): name for name in fixed}", scenario_section10),
    ("istiod_cabundle_exact", A, '            if path[2:] == ("f:clientConfig", "f:caBundle"):',
     '            if path[2:4] == ("f:clientConfig", "f:caBundle"):', scenario_section10),
    ("istiod_failure_policy_value", A, '            if path[2:] == ("f:failurePolicy",) and live[keys[path[1]]] == "Fail":',
     '            if path[2:] == ("f:failurePolicy",):', scenario_section10),
    ("section10_operation", A, '    if not paths or entry.get("operation") != "Update" or entry.get("subresource") or project is None:',
     '    if not paths or entry.get("subresource") or project is None:', scenario_section10),
    ("section10_subresource", A, '    if not paths or entry.get("operation") != "Update" or entry.get("subresource") or project is None:',
     '    if not paths or entry.get("operation") != "Update" or project is None:', scenario_section10),
    ("section10_empty_paths", A, '    if not paths or entry.get("operation") != "Update" or entry.get("subresource") or project is None:',
     '    if entry.get("operation") != "Update" or entry.get("subresource") or project is None:', scenario_section10),
    ("lbc_object_name", A, '        return (observed.get("kind") == "TargetGroupBinding" and observed.get("name") == project + "-gateway"',
     '        return (observed.get("kind") == "TargetGroupBinding"', scenario_section10),
    ("lbc_namespace", A, '                and observed.get("namespace") == project + "-ingress"\n', "", scenario_section10),
    ("lbc_finalizer_exact", A, '                and set(paths) == {("f:metadata", "f:finalizers", "v:" + json.dumps(LBC_FINALIZER))})',
     '                and all(p[:2] == ("f:metadata", "f:finalizers") for p in paths))', scenario_section10),
    ("tgb_other_finalizer", A,
     '    if observed.get("kind") == "TargetGroupBinding" and set(observed.get("finalizers") or ()) - {LBC_FINALIZER}:',
     "    if False:", scenario_section10),
    ("duplicate_entries", A, "    malformed = malformed or len(set(triples)) != len(triples)", "    malformed = malformed",
     scenario_section10_malformed),
    ("fields_tree", A, '            and fields_tree_well_formed(entry.get("fieldsV1", {})))',
     '            and isinstance(entry.get("fieldsV1", {}), dict))', scenario_section10_malformed),
    ("webhooks_malformed", A, "    if webhooks is None or not isinstance(finalizers, list)",
     "    if False or not isinstance(finalizers, list)", scenario_section10_malformed),
    ("finalizers_malformed", A, "not isinstance(finalizers, list) or not all(isinstance(f, str) for f in finalizers)",
     "False", scenario_section10_malformed),
    ("istio_webhooks_recheck", A, "            self.check_istio_webhooks()\n", "", scenario_istio_webhooks_at_readiness),
    ("istio_failure_policy_fail", A,
     '                if any(w.get("failurePolicy") != "Fail" for w in obj.get("webhooks") or []) or not obj.get("webhooks"):',
     "                if False:", scenario_istio_webhooks_at_readiness),
    ("istio_foreign_at_readiness", A, '                if verdict == "FOREIGN_FIELD":\n                    stop(4, "foreign_field")',
     '                if verdict == "FOREIGN_FIELD":\n                    pass', scenario_istio_webhooks_at_readiness),
    ("runtime_cabundle_claim", A, '        return observed["malformed"] or any(cabundle_paths(m) for m in observed["managers"]',
     '        return False and any(cabundle_paths(m) for m in observed["managers"]', scenario_runtime_cabundle_claim),
    ("pods_scope", A, '            raise AdapterError("pods_out_of_scope")', "            return []", scenario_workload_read_scope),
    ("secret_scope", A, '            raise AdapterError("secret_out_of_scope")', "            pass", scenario_workload_read_scope),
    # Apply-B2: gateway.
    ("gateway_base_gate", A, '        if outstanding_deferred("base", done, self.evidence):\n            stop(3, "deferred_readiness_unresolved:base_validator_serving")\n\n    def mesh_pre_apply',
     '        if False:\n            stop(3, "deferred_readiness_unresolved:base_validator_serving")\n\n    def mesh_pre_apply', scenario_gateway_unreachable),
    ("gateway_istiod_ready", A, '        if "istiod" not in done or self.evidence.get("istiod_in_stage_readiness") != "MET":',
     "        if False:", scenario_gateway_pre_apply),
    ("gateway_istiod_evidence", A, '        if "istiod" not in done or self.evidence.get("istiod_in_stage_readiness") != "MET":',
     '        if "istiod" not in done:', scenario_gateway_pre_apply),
    ("gateway_injector", A, '            if obj is None or not obj.get("webhooks") or not all(',
     '            if obj is None or not obj.get("webhooks") or False and all(', scenario_gateway_pre_apply),
    ("gateway_secrets", A, '        self.check_secrets("gateway")\n', "", scenario_gateway_pre_apply),
    ("gateway_registry", A, '        self.check_registry("gateway")\n', "", scenario_gateway_pre_apply),
    ("gateway_pre_apply_call", A, '        elif stage == "gateway":\n            self.gateway_pre_apply(done)\n',
     '        elif False:\n            self.gateway_pre_apply(done)\n', scenario_gateway_unreachable),
    ("injection_call", A, '            self.check_injection(stage)\n', "            pass\n", scenario_gateway_contract),
    ("injection_annotation", A, '                if not isinstance(annotations.get(SIDECAR_STATUS), str) or not annotations[SIDECAR_STATUS] or \\',
     "                if False or \\", scenario_gateway_contract),
    ("injection_image", A, 'wanted is None or not any(c.get("name") == "istio-proxy" and c.get("image") == wanted',
     'wanted is None or not any(c.get("name") == "istio-proxy"', scenario_gateway_contract),
    ("gateway_readiness_evidence", A, '        self.evidence[stage + "_in_stage_readiness"] = "MET"\n', "", scenario_gateway_unreachable),
    # Apply-B3: mesh_security.
    ("mesh_gate_istiod", A, '        if self.evidence.get("istiod_in_stage_readiness") != "MET" or "istiod" not in done:\n            stop(3, "pre_apply_not_verified:istiod_not_ready")\n        if outstanding_deferred("base", done, self.evidence):\n            stop(3, "deferred_readiness_unresolved:base_validator_serving")\n\n    def admission_pre_apply',
     '        if outstanding_deferred("base", done, self.evidence):\n            stop(3, "deferred_readiness_unresolved:base_validator_serving")\n\n    def admission_pre_apply', scenario_mesh_gate),
    ("mesh_gate_istiod_done", A, '        if self.evidence.get("istiod_in_stage_readiness") != "MET" or "istiod" not in done:',
     '        if self.evidence.get("istiod_in_stage_readiness") != "MET":', scenario_mesh_gate),
    ("mesh_gate_base", A, '            stop(3, "deferred_readiness_unresolved:base_validator_serving")\n\n    def admission_pre_apply',
     '            pass\n\n    def admission_pre_apply', scenario_mesh_gate),
    ("mesh_dispatch", A, '        elif stage == "mesh_security":\n            self.mesh_pre_apply(done)\n',
     '        elif False:\n            self.mesh_pre_apply(done)\n', scenario_mesh_gate),
    ("mesh_readiness_call", A, '        if stage == "mesh_security":\n            return self.mesh_readiness()\n', "",
     scenario_mesh_contract),
    ("mesh_ownership", A, '            if mesh_owned != "OWNED":\n                stop(*STOP_VERDICTS.get(mesh_owned, (4, "foreign_field")))',
     '            if False:\n                stop(*STOP_VERDICTS.get(mesh_owned, (4, "foreign_field")))', scenario_mesh_contract),
    ("mesh_drift_call", A, "            if manifest_drift(obj, manifest):", "            if False:", scenario_mesh_contract),
    ("mesh_present", A, '            if obj is None:\n                stop(3, "object_not_present")\n            mesh_owned = d13_ownership',
     '            if obj is None:\n                continue\n            mesh_owned = d13_ownership', scenario_mesh_contract),
    ("drift_value", A, "    return live != desired\n", "    return False\n", scenario_mesh_contract),
    ("drift_missing_key", A, "any(key not in live or drift(live[key], value)", "any(key in live and drift(live[key], value)",
     scenario_mesh_contract),
    ("policy_kinds", A, '                 "PeerAuthentication", "AuthorizationPolicy", "NetworkPolicy"}', "                 }",
     scenario_mesh_contract),
    ("traffic_fixed", A, '"traffic_enforcement": "NOT_TESTED",', '"traffic_enforcement": "MET",', scenario_mesh_contract),
    ("not_tested_label", A, '                          else "NOT_TESTED" if "NOT_TESTED" in values else "NOT_VERIFIED"))',
     '                          else "NOT_VERIFIED"))', scenario_mesh_contract),
    # Apply-B4: admission.
    ("admission_dispatch", A, '        elif stage == "admission":\n            self.admission_pre_apply(done)\n',
     '        elif False:\n            self.admission_pre_apply(done)\n', scenario_admission_pre_apply),
    ("admission_controller_done", A, '        if "controller" not in done:\n            stop(3, "pre_apply_not_verified:controller_not_accepted")',
     '        if False:\n            stop(3, "pre_apply_not_verified:controller_not_accepted")', scenario_admission_pre_apply),
    ("admission_tgb_crd", A, '        if crd is None or not conditions_true(crd, ("Established", "NamesAccepted")):',
     "        if crd is None:", scenario_admission_pre_apply),
    ("policy_type_missing", A, '            if not isinstance(checking, dict):\n                stop(3, "policy_type_check_not_verified")',
     '            if not isinstance(checking, dict):\n                checking = {}', scenario_admission_contract),
    ("policy_type_warnings", A, '            if checking.get("expressionWarnings"):', "            if False:", scenario_admission_contract),
    ("binding_deny_exact", A, '            if spec.get("validationActions") != ["Deny"] or spec.get("policyName")',
     '            if "Deny" not in (spec.get("validationActions") or []) or spec.get("policyName")', scenario_admission_contract),
    ("binding_policy_name", A, ' or spec.get("policyName") != manifest["spec"]["policyName"]:', ":", scenario_admission_contract),
    ("admission_readiness_call", A, '        if stage == "admission":\n            return self.admission_readiness()\n', "",
     scenario_admission_contract),
    ("admission_owned_no_drift", A, '        self.verify_owned_no_drift("admission")\n', "", scenario_admission_contract),
    ("admission_probe_missing", A, '            stop(3, "probe_" + name + ":not_run")', "            return", scenario_admission_probes),
    ("admission_probe_shape", A, '            stop(3, "probe_" + name + ":unknown")\n        status, body = answer\n        denial',
     '            pass\n        status, body = answer\n        denial', scenario_admission_probes),
    ("admission_probe_policy", A, "        if policy != policy_name:", "        if False:", scenario_admission_probes),
    ("admission_probe_binding", A, "        if binding not in bindings:", "        if False:", scenario_admission_probes),
    ("admission_probe_message", A, "        if message not in messages:",
     "        if not any(m in message for m in messages):", scenario_admission_probes),
    ("admission_probe_message_any", A, "        if message not in messages:", "        if False:", scenario_admission_probes),
    ("vap_denial_fullmatch", A, "    match = VAP_DENIAL.fullmatch(body)", "    match = VAP_DENIAL.search(body)",
     scenario_admission_probes),
    ("vap_denial_status", A, "    if status != 403 or not isinstance(body, str):", "    if not isinstance(body, str):",
     scenario_admission_probes),
    ("admission_probe_not_exact", A, "            if status == 403 and VAP_DENIED.search(body):", "            if False:",
     scenario_admission_probes),
    ("admission_live_fixed", A, '                      "live_probe_A": "NOT_VERIFIED", "live_probe_A_prime": "NOT_VERIFIED",',
     '                      "live_probe_A_prime": "NOT_VERIFIED",', scenario_admission_contract),
    # Apply-B5: binding_writer.
    ("writer_dispatch", A, '        if stage == "binding_writer":\n            self.binding_writer_pre_apply(done)\n        elif stage == "admission":',
     '        if stage == "admission":', scenario_binding_writer_pre_apply),
    ("writer_admission_done", A, '        if "admission" not in done:\n            stop(3, "pre_apply_not_verified:admission_not_accepted")',
     '        if False:\n            stop(3, "pre_apply_not_verified:admission_not_accepted")', scenario_binding_writer_pre_apply),
    ("writer_admission_reverify", A, '        for identity in self.members("admission"):\n            self.minimal_completion(identity)\n',
     "", scenario_binding_writer_pre_apply),
    ("writer_readiness_call", A, '        if stage == "binding_writer":\n            return self.binding_writer_readiness()\n', "",
     scenario_binding_writer_contract),
    ("writer_owned_no_drift", A, '        self.verify_owned_no_drift("binding_writer")\n', "", scenario_binding_writer_contract),
    ("sa_automount_check", A, ' and obj.get("automountServiceAccountToken") is not False:',
     ' and obj.get("automountServiceAccountToken") is True:', scenario_binding_writer_contract),
    ("sa_automount_call", A, '                stop(4, "sa_automount_token_not_false")', "                pass",
     scenario_binding_writer_contract),
    ("d1_permissions_fixed", A, '"d1_effective_permissions": "NOT_TESTED",', "", scenario_binding_writer_contract),
    ("d1_impersonation_fixed", A, '                      "d1_impersonation": "NOT_TESTED",', "                     ",
     scenario_binding_writer_contract),
    ("d1_probe_c_fixed", A, ' "live_probe_C": "NOT_TESTED",', "", scenario_binding_writer_contract),
    ("d1_probe_e_fixed", A, '                      "live_probe_E": "NOT_TESTED"}', "                      }",
     scenario_binding_writer_contract),
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
        """A mutant counts only when a contract assertion fails without the code under test crashing."""
        self.assertEqual(len(MUTATIONS), 163)
        undetected, crashed = [], []
        for name, filename, old, new, scenario in MUTATIONS:
            mods = mods_for(filename, old, new)
            CRASHES.clear()
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, mods)
            except AssertionError:
                if CRASHES:
                    crashed.append(name + " (" + CRASHES[0] + ")")
                continue
            except Exception as raised:  # noqa: BLE001 - an escaped exception is a crash, not a detection
                crashed.append(name + " (" + type(raised).__name__ + ")")
                continue
            undetected.append(name)
        self.assertEqual((undetected, crashed), ([], []))


if __name__ == "__main__":
    unittest.main()
