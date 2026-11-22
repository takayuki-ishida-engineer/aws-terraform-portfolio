#!/usr/bin/env python3
"""Fake-only apply engine for the first two runtime stages (Step 1 item 6c-B3b-Apply-A).

Source and offline only. It applies the ``namespaces`` (2 objects) and ``base`` (16
objects) stages to a ``FakeAdapter`` and nothing else.
- It has no command line. ``k8s_runtime.py apply`` still refuses
  (``operation_not_approved``).
- Any other adapter is refused, and ``RealAdapter`` cannot be constructed.

Owner decisions applied (2026-11-22, Source/Offline only). None of these is Live
evidence:
- D2: Secrets are metadata-only fakes. The first two stages read no Secret.
- D3: the apply read scope is limited to the approved stages' objects and the
  ``kube-system`` namespace. The Pods, Nodes, EndpointSlices and ConfigMap reads
  of later stages are design scope only.
- D9: server-side dry-run responses and admission probes are classified exactly
  (``classify_admission``). They run only against the fake.
- D11: API read 20 s, CRD established 120 s, Deployment ready 600 s (unused by
  these stages). The CRD poll interval is 5 s, a cadence inside the 120 s
  bound and not a timeout. There are no unbounded retries.
- D13: the design record section 10 allowlist (``d13_ownership``).
  - Only the structural status rule is treated as verified.
  - The istiod and controller manager names are unverified, so their entries
    leave ownership NOT_VERIFIED.
  - Any unknown manager or field is ``FOREIGN_FIELD``.
  - Conflicts are never forced.

Flow:
1. Gate.
2. Pins and the receipt HEADER pins.
3. D17 fingerprint.
4. Receipt reconcile. A quarantined, unproven, foreign, changed or unknown object
   stops the run before any write.
5. Per stage:
   - pre-apply conditions, including C1 for ``base``;
   - fake server-side dry-run for every object;
   - per object: INTENT, then fake server-side apply without force, then RESULT
     with the UID read back, then the ownership check;
   - minimal completion;
   - STAGE_DONE.

``base`` leaves the istiod-default-validator serving deferred to the ``istiod``
stage, which is not approved here. So a successful run ends in exit 6
``APPLIED_WITH_DEFERRED``, never PASS.

The journal schema is unchanged. Deferral is derived from the journal: a closed
stage whose resolving stage is not closed.
"""
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_runtime  # noqa: E402
import k8s_runtime_receipt as receipt  # noqa: E402

APPROVED_STAGES = ("namespaces", "base")
API_READ_TIMEOUT_SECONDS = 20
CRD_ESTABLISHED_TIMEOUT_SECONDS = 120
DEPLOYMENT_READY_TIMEOUT_SECONDS = 600
READINESS_POLL_SECONDS = 5
EXIT_STATUS = {0: "STAGES_ACCEPTED", 1: "REFUSED", 2: "STOPPED", 3: "UNDETERMINED", 4: "APPLY_FAILED",
               5: "READINESS_TIMEOUT", 6: "APPLIED_WITH_DEFERRED"}
STATUS_KINDS = {"CustomResourceDefinition", "Deployment", "ValidatingAdmissionPolicy", "TargetGroupBinding"}
# Section 10 managers whose names are not confirmed on a real cluster: never treated as verified.
UNVERIFIED_MANAGERS = ("pilot-discovery", "aws-load-balancer-controller")
DEFERRED = {"base": [{"item": "istiod-default-validator serving (caBundle by istiod, endpoints, probe F)",
                      "resolved_by": "istiod"}]}
PROCEED_VERDICTS = {"ABSENT", "NOT_APPLIED", "REAPPLY_SAFE", "CONSISTENT"}
STOP_VERDICTS = {"QUARANTINED": (4, "quarantined"), "UID_CHANGED": (4, "uid_changed"),
                 "NOT_OWNED": (4, "foreign_owner"), "OWNERSHIP_NOT_VERIFIED": (4, "ownership_not_verified"),
                 "FOREIGN_FIELD": (4, "foreign_field"), "UNKNOWN": (3, "observation_unknown")}


class ApplyStop(Exception):
    def __init__(self, exit_code, reason):
        super().__init__(reason)
        self.exit_code = exit_code
        self.reason = reason


class AdapterTimeout(Exception):
    """A fake API call exceeded the D11 read timeout; the outcome is unknown."""


class AdapterError(Exception):
    """A request the fake refuses (out of read scope, forced apply)."""


class ApplyConflict(Exception):
    """A server-side apply field conflict; never forced."""


def stop(exit_code, reason):
    raise ApplyStop(exit_code, reason)


def key_of(identity):
    return receipt.key_of(identity)


def identity_of(obj):
    return {"apiVersion": obj["apiVersion"], "kind": obj["kind"], "namespace": obj["metadata"].get("namespace", ""),
            "name": obj["metadata"]["name"]}


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.value = float(start)

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += float(seconds)


class RealAdapter:
    """No real adapter exists in this item; constructing one is refused."""

    def __init__(self, *args, **kwargs):
        raise AdapterError("real_adapter_not_implemented")


class FakeAdapter:
    """In-memory cluster for offline tests. Reads are limited to an explicit scope (D3)."""

    is_fake = True

    def __init__(self, clock, kube_system_uid, read_scope):
        self.clock = clock
        self.read_scope = set(read_scope) | {"v1|Namespace||kube-system"}
        self.objects = {"v1|Namespace||kube-system": {"apiVersion": "v1", "kind": "Namespace",
                                                      "metadata": {"name": "kube-system", "uid": kube_system_uid},
                                                      "status": {"phase": "Active"}}}
        self.latency = {}          # key -> seconds a read takes
        self.conflicts = set()     # keys whose server-side apply conflicts
        self.crd_ready_after = {}  # key -> seconds after creation, or None for never
        self.dry_run = {}          # key -> (status, body)
        self.apply_timeouts = set()       # keys whose apply times out before it lands
        self.post_apply_timeouts = set()  # keys whose apply lands but whose answer is lost
        self.calls = []
        self.serial = 0

    def _scope(self, key):
        if key not in self.read_scope:
            raise AdapterError("read_out_of_scope")

    def get(self, identity):
        key = key_of(identity)
        self._scope(key)
        self.calls.append(("get", key))
        latency = self.latency.get(key, 0)
        self.clock.sleep(min(latency, API_READ_TIMEOUT_SECONDS))
        if latency > API_READ_TIMEOUT_SECONDS:
            raise AdapterTimeout(key)
        obj = self.objects.get(key)
        if obj is None:
            return None
        obj = copy.deepcopy(obj)
        if obj["kind"] == "CustomResourceDefinition":
            delay = self.crd_ready_after.get(key, 0)
            ready = delay is not None and self.clock.now() >= obj["metadata"]["_created"] + delay
            state = "True" if ready else "False"
            obj["status"] = {"conditions": [{"type": "NamesAccepted", "status": state},
                                            {"type": "Established", "status": state}]}
        obj["metadata"].pop("_created", None)
        return obj

    def server_side_apply(self, identity, manifest, field_manager, force=False, dry_run=False):
        key = key_of(identity)
        self._scope(key)
        if force:
            raise AdapterError("force_conflicts_refused")
        self.calls.append(("dry_run" if dry_run else "apply", key))
        if dry_run:
            return self.dry_run.get(key, (200, ""))
        if key in self.apply_timeouts:
            raise AdapterTimeout(key)
        if key in self.conflicts:
            raise ApplyConflict(key)
        current = self.objects.get(key)
        fields = sorted("f:" + k for k in manifest if k not in ("apiVersion", "kind"))
        entry = {"manager": field_manager, "operation": "Apply", "fieldsType": "FieldsV1",
                 "fieldsV1": {f: {} for f in fields}}
        if current is None:
            self.serial += 1
            obj = copy.deepcopy(manifest)
            obj["metadata"].update(uid="00000000-0000-4000-9000-%012x" % self.serial, resourceVersion=str(self.serial),
                                   generation=1, managedFields=[entry], _created=self.clock.now())
            if obj["kind"] == "Namespace":
                obj["status"] = {"phase": "Active"}
            self.objects[key] = obj
            if key in self.post_apply_timeouts:
                raise AdapterTimeout(key)
            return 201, ""
        others = [m for m in current["metadata"].get("managedFields", []) if m.get("manager") != field_manager]
        keep = {k: current["metadata"][k] for k in ("uid", "_created", "generation", "resourceVersion")
                if k in current["metadata"]}
        obj = copy.deepcopy(manifest)
        obj["metadata"].update(keep)
        obj["metadata"]["managedFields"] = others + [entry]
        if "status" in current:
            obj["status"] = current["status"]
        self.serial += 1
        obj["metadata"]["resourceVersion"] = str(self.serial)
        self.objects[key] = obj
        return 200, ""


def observed_of(obj):
    """Presence data for reconcile and D13: UID, kind and each manager's top-level fields."""
    managers = [{"manager": m.get("manager"), "operation": m.get("operation"), "subresource": m.get("subresource", ""),
                 "fields": sorted((m.get("fieldsV1") or {}).keys())} for m in obj["metadata"].get("managedFields") or []]
    return {"uid": obj["metadata"].get("uid"), "kind": obj["kind"], "managers": managers}


def d13_ownership(observed, runtime_manager):
    """Section 10 allowlist (D13). Only the structural status rule is verified; anything unknown fails closed."""
    managers = observed.get("managers") or []
    runtime = [m for m in managers if m.get("manager") == runtime_manager and m.get("operation") == "Apply"
               and not m.get("subresource")]
    if not runtime:
        return "NOT_OWNED"
    verdict = "OWNED"
    for entry in managers:
        if entry in runtime:
            continue
        fields = set(entry.get("fields") or [])
        if (entry.get("subresource") == "status" and entry.get("operation") == "Update"
                and observed.get("kind") in STATUS_KINDS and fields and fields <= {"f:status"}):
            continue
        if entry.get("manager") in UNVERIFIED_MANAGERS:
            verdict = "OWNERSHIP_NOT_VERIFIED"
            continue
        return "FOREIGN_FIELD"
    return verdict


WEBHOOK_DENIED = re.compile(r'admission webhook "([^"]+)" denied')
VAP_DENIED = re.compile(r"ValidatingAdmissionPolicy '([^']+)' with binding '[^']+' denied request")
AUTHZ_DENIED = re.compile(r"cannot [a-z]+ resource")


def classify_admission(status, body):
    """D9: the exact outcome class of a dry-run or probe; anything unrecognised is ``unknown``, never allowed."""
    text = body if isinstance(body, str) else ""
    if status in (200, 201):
        return "allowed"
    if status == 400 and "dry run" in text.lower() and "side effects" in text.lower():
        return "dry_run_unsupported"
    if status == 403:
        match = WEBHOOK_DENIED.search(text)
        if match:
            return "webhook_denied:" + match.group(1)
        match = VAP_DENIED.search(text)
        if match:
            return "vap_denied:" + match.group(1)
        if AUTHZ_DENIED.search(text):
            return "authz_denied"
        return "unknown"
    if status == 422:
        return "schema_invalid"
    if status in (500, 502, 503, 504) and "failed calling webhook" in text:
        return "webhook_unreachable"
    return "unknown"


def probe_passes(expected_class, status, body):
    """A probe passes only on the exact expected class; a different denial is not a pass."""
    return classify_admission(status, body) == expected_class


def dry_run_permitted(webhook_configurations):
    """The API server refuses a dry-run unless every matching webhook has no side effects."""
    return all(w.get("sideEffects") in ("None", "NoneOnDryRun")
               for config in webhook_configurations for w in config.get("webhooks", []))


def c1_violations(manifests):
    """Istio webhooks that would make the runtime own a caBundle (C1, D23)."""
    found = []
    for obj in manifests:
        if obj["kind"] in ("ValidatingWebhookConfiguration", "MutatingWebhookConfiguration") and \
                not obj["metadata"]["name"].startswith("aws-load-balancer-controller"):
            found += [obj["metadata"]["name"] for w in obj.get("webhooks", []) if "caBundle" in w.get("clientConfig", {})]
    return found


def conditions_true(obj, names):
    conditions = {c.get("type"): c.get("status") for c in (obj.get("status") or {}).get("conditions") or []}
    return all(conditions.get(n) == "True" for n in names)


class Engine:
    def __init__(self, report, objects, store, adapter, clock, cluster_arn):
        self.report, self.store, self.adapter, self.clock = report, store, adapter, clock
        self.cluster_arn = cluster_arn
        self.plan = receipt.Plan.from_report(report)
        self.manager = k8s_runtime.runtime_manager(report["project"])
        self.objects_sha256 = hashlib.sha256(json.dumps(objects, sort_keys=True, separators=(",", ":"))
                                             .encode()).hexdigest()
        self.manifests = {}
        for obj in objects:
            self.manifests.setdefault(key_of(identity_of(obj)), []).append(obj)
        self.stages = []

    def read(self, identity):
        try:
            return self.adapter.get(identity)
        except AdapterTimeout:
            stop(3, "api_timeout")

    def members(self, stage):
        return [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|"))) for k in self.plan.members[stage]]

    def manifest(self, identity):
        found = self.manifests.get(key_of(identity), [])
        if len(found) != 1 or found[0]["kind"] == "Secret":
            stop(2, "manifest_not_in_bundle")
        return found[0]

    def preflight(self, expected_manifest, expected_input, through):
        if not isinstance(self.adapter, FakeAdapter) or getattr(self.adapter, "is_fake", False) is not True:
            stop(1, "real_adapter_not_approved")
        if through not in APPROVED_STAGES:
            stop(1, "stage_not_approved:" + str(through))
        if self.plan.stage_order[:len(APPROVED_STAGES)] != list(APPROVED_STAGES):
            stop(2, "plan_stage_order")
        try:
            k8s_runtime.check_pins(self.report, expected_manifest, expected_input)
        except k8s_runtime.GateError as error:
            stop(2, str(error))
        if self.objects_sha256 != self.report["manifest_sha256"]:
            stop(2, "objects_do_not_match_plan")
        expected = self.store.expected
        if (expected["manifest_sha256"], expected["input_sha256"]) != (self.report["manifest_sha256"],
                                                                        self.report["input_sha256"]):
            stop(2, "bundle_changed")
        kube_system = self.read({"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "kube-system"})
        if kube_system is None:
            stop(2, "fingerprint_unreadable")
        try:
            fp = receipt.fingerprint(self.cluster_arn, kube_system["metadata"].get("uid"))
        except receipt.ReceiptError:
            stop(2, "fingerprint_unreadable")
        if fp != expected["fingerprint"]:
            stop(2, "fingerprint_mismatch")
        return APPROVED_STAGES[:APPROVED_STAGES.index(through) + 1]

    def reconcile(self, approved):
        scope = {k for stage in approved for k in self.plan.members[stage]}

        def observe(identity):
            if key_of(identity) not in scope:
                return "unknown", "not_in_scope"
            obj = self.read(identity)
            return ("absent", None) if obj is None else ("present", observed_of(obj))
        state = receipt.load(self.store.dir, self.plan, self.store.expected)["state"]
        verdicts = receipt.reconcile(state, self.plan, observe, self.manager, ownership_fn=d13_ownership)
        for row in verdicts:
            if key_of(row["identity"]) not in scope:
                continue
            if row["verdict"] == "QUARANTINE_REQUIRED":
                live = self.read(row["identity"])
                self.store.quarantine(row["identity"], live["metadata"]["uid"] if live else None, "creation_unproven")
                stop(4, "quarantined")
            if row["verdict"] in STOP_VERDICTS:
                stop(*STOP_VERDICTS[row["verdict"]])
            if row["verdict"] not in PROCEED_VERDICTS:
                stop(3, "verdict_unclassified")
        intent = state["open_intent"]
        if intent is not None and intent["key"] in scope:
            # An interrupted attempt whose object is provably safe (NOT_APPLIED or REAPPLY_SAFE above):
            # close it as unconfirmed before writing a new INTENT; ownership already recorded is kept.
            identity = dict(zip(("apiVersion", "kind", "namespace", "name"), intent["key"].split("|")))
            self.store.result(intent["seq"], identity, None, None, None, "failed")
            state = receipt.load(self.store.dir, self.plan, self.store.expected)["state"]
        return state

    def pre_apply(self, stage, done):
        if stage == "base":
            if "namespaces" not in done:
                stop(2, "pre_apply_not_verified:namespaces_not_accepted")
            if c1_violations([self.manifest(i) for i in self.members(stage)]):
                stop(4, "istio_cabundle_ownership_unsafe")

    def dry_run(self, stage):
        for identity in self.members(stage):
            status, body = self.adapter.server_side_apply(identity, self.manifest(identity), self.manager,
                                                          force=False, dry_run=True)
            outcome = classify_admission(status, body)
            if outcome == "allowed":
                continue
            stop(3 if outcome in ("dry_run_unsupported", "webhook_unreachable", "unknown") else 4,
                 "dry_run:" + outcome)

    def apply_object(self, stage, identity, state):
        recorded = state["objects"].get(key_of(identity), {}).get("owned_uid")
        live = self.read(identity)
        if recorded is not None and (live is None or live["metadata"].get("uid") != recorded):
            stop(4, "uid_changed")
        prior = {"state": "owned", "uid": recorded} if recorded is not None else {"state": "absent"}
        seq = self.store.intent(stage, identity, prior, "update" if recorded else "create")
        try:
            self.adapter.server_side_apply(identity, self.manifest(identity), self.manager, force=False)
        except ApplyConflict:
            self.store.result(seq, identity, None, None, None, "failed")
            stop(4, "field_conflict")
        except AdapterTimeout:
            stop(3, "api_timeout")  # outcome unknown: the INTENT stays open for reconciliation
        after = self.read(identity)
        if after is None or (recorded is not None and after["metadata"].get("uid") != recorded):
            self.store.result(seq, identity, None, None, None, "failed")
            stop(4, "uid_changed" if after is not None else "apply_not_observed")
        meta = after["metadata"]
        self.store.result(seq, identity, meta["uid"], str(meta.get("resourceVersion", "0")),
                          int(meta.get("generation", 0)), "applied")
        owned = d13_ownership(observed_of(after), self.manager)
        if owned != "OWNED":
            stop(4, {"NOT_OWNED": "foreign_owner", "OWNERSHIP_NOT_VERIFIED": "ownership_not_verified"}
                 .get(owned, "foreign_field"))

    def minimal_completion(self, identity):
        manifest = self.manifest(identity)
        if identity["kind"] == "Namespace":
            obj = self.read(identity)
            labels = (obj or {}).get("metadata", {}).get("labels") or {}
            if obj is None or (obj.get("status") or {}).get("phase") != "Active":
                stop(3, "namespace_not_active")
            if any(labels.get(k) != v for k, v in (manifest["metadata"].get("labels") or {}).items()):
                stop(3, "namespace_labels_differ")
        elif identity["kind"] == "CustomResourceDefinition":
            started = self.clock.now()
            while True:
                obj = self.read(identity)
                if obj is not None and conditions_true(obj, ("Established", "NamesAccepted")):
                    break
                if self.clock.now() - started >= CRD_ESTABLISHED_TIMEOUT_SECONDS:
                    stop(5, "crd_not_established")
                self.clock.sleep(READINESS_POLL_SECONDS)
        elif identity["kind"] in ("ValidatingWebhookConfiguration", "MutatingWebhookConfiguration"):
            obj = self.read(identity)
            if obj is None or c1_violations([obj]):
                stop(4, "istio_cabundle_ownership_unsafe")
        else:
            stop(2, "kind_not_in_approved_stages")

    def run(self, expected_manifest, expected_input, through):
        approved = self.preflight(expected_manifest, expected_input, through)
        with self.store.lock():
            self.store.begin()
            state = self.reconcile(approved)
            done = set(state["stages_done"])
            for stage in approved:
                applied = stage not in done
                if applied:
                    self.pre_apply(stage, done)
                    self.dry_run(stage)
                    for identity in self.members(stage):
                        self.apply_object(stage, identity, state)
                for identity in self.members(stage):
                    self.minimal_completion(identity)
                if applied:
                    self.store.stage_done(stage)
                    state = receipt.load(self.store.dir, self.plan, self.store.expected)["state"]
                done.add(stage)
                deferred = [dict(d) for d in DEFERRED.get(stage, []) if d["resolved_by"] not in done]
                self.stages.append({"name": stage, "applied": applied, "minimal_completion": "MET",
                                    "deferred": deferred, "final_acceptance": "DEFERRED" if deferred else "PASS"})
        return 6 if any(s["deferred"] for s in self.stages) else 0


def apply_stages(report, objects, store, adapter, clock, expected_manifest, expected_input, cluster_arn,
                 through="base"):
    """Run the approved stages against the fake. Returns a report; never raises for a stop."""
    engine = Engine(report, objects, store, adapter, clock, cluster_arn)
    try:
        code, reason = engine.run(expected_manifest, expected_input, through), None
    except ApplyStop as stopped:
        code, reason = stopped.exit_code, stopped.reason
    except receipt.ReceiptError as error:
        code, reason = 2, "receipt:" + str(error)
    except AdapterError as error:
        code, reason = 3, "adapter:" + str(error)
    return {"status": EXIT_STATUS[code], "exit_code": code, "reason": reason, "executor": "fake",
            "stages": engine.stages, "runtime_final_acceptance": "NOT_REACHED",
            "live": "NOT_TESTED", "approved_stages": list(APPROVED_STAGES)}
