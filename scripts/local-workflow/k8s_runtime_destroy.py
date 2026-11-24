#!/usr/bin/env python3
"""Fake-only runtime destroy engine (Step 1 item 6c-B4b, Owner authorization 2026-11-24).

Source and offline only. It orchestrates the destroy of the 62 reviewed runtime objects against a fake API
server, through the 6c-B4a destroy transport (``k8s_runtime_transport.open_destroy_transport``: only the fake can
be opened) and the G9 Secret cleanup (``k8s_certs_receipt.cleanup``: only the fake). It never calls the server
directly, never starts a process, opens a socket, reads a token or a kubeconfig, or sleeps in real time; every
wait runs on ``k8s_runtime_apply.FakeClock``. ``k8s_runtime.py destroy`` still refuses (``operation_not_approved``).
A COMPLETE here is a Fake-only Source/Offline result, never Live evidence.

Owner decisions applied: D3, D5, D6, D11, D12, D18, D19 (2026-11-24), the existing G9, D13 and the receipt and
journal contracts (FORMAT 1, additive destroy records), unchanged.

Preflight (before any write)
  The fake clock and the fake transport only; the caller's manifest and input SHA-256 pins against the plan and the
  rendered objects; the reviewed stage table (9 stages, 62 objects, 17 CRDs, 45 other objects); one manifest per
  plan identity and no Secret; one global D11 deadline for the whole run. The cluster fingerprint (D17) is the
  cluster ARN plus the ``kube-system`` UID read through the destroy transport. The runtime receipt of that
  fingerprint must exist and verify (journal chain, snapshot, project, fingerprint, pins); a missing, corrupt or
  other-fingerprint receipt stops before anything is written, and no new receipt or journal is ever created. An
  unresolved apply INTENT or any QUARANTINE stops. The G9 registration receipt must load and verify too. The DELETE
  map and the CRD verification map come from the verified journal (``owned_uids``, ``crd_receipt_uids``) and the
  plan identities from the reviewed plan; nothing a read returns can widen them, and there is no ownership input.

Order (D12, dependency safety over plain reverse order)
  The apply stages reversed, then ``namespace_phase`` with every Namespace: ingress, binding_writer, admission,
  mesh_security, gateway, istiod, controller, base, namespaces (no deletable member), namespace_phase. Inside a
  stage a fixed kind order: the TargetGroupBinding first, policy bindings before policies, webhook configurations
  before their Deployments, then workloads, Services, RBAC, ServiceAccounts and ConfigMaps. Gates:
  - ingress: no TargetGroupBinding outside the receipt in ``<project>-ingress``;
  - admission and controller: the runtime TargetGroupBinding confirmed absent (trusted NotFound) and none listed;
    before admission, no LoadBalancer Service and no unknown Service in ``<project>-ingress`` (the runtime Service's
    ``spec.type`` from the specialised read, never inferred from metadata);
  - istiod and base: every Istio CRD ZERO_INSTANCES or CRD_NOT_CREATED before an Istio webhook goes;
  - namespace_phase: the G9 cleanup COMPLETE (including the kube-system webhook TLS Secret) and, per namespace,
    a fresh discovery and a COMPLETE metadata inventory with only allowed leftovers (D3, D6, D18).
  The external dependencies of the TargetGroupBinding (the controller's IRSA role, the target group, the ELBv2 and
  STS endpoints, the tunnel) are Terraform roots outside this engine; they must still exist (runbook section 7).

Per object (D7, D13, D19)
  The plan identity, the journal's owned UID, no quarantine, a fresh metadata read, the live UID equal to the
  journal UID, D13 field ownership OWNED (``k8s_runtime_apply.d13_ownership`` with the manifest's required paths;
  never a manager name alone, no allowlist widening), the stage gate, the deadline and the journal's current step.
  Then DESTROY_INTENT (fsynced), the UID-precondition DELETE, an independent metadata read until a trusted NotFound
  (bounded: the TargetGroupBinding finalizer 600 s, a Namespace 600 s, polling every 5 s), and DESTROY_RESULT. A 200
  or 202 is only REQUESTED; a bare 404, 403, 5xx, timeout, invalid response or 409 is never absence or success.
  A recreated object (another UID) is quarantined and never deleted or adopted; an object that exists without a
  journal record is NOT_OWNED and stops. An object never created is judged on its own (no journal record, no open
  INTENT, a trusted NotFound) and never counted as deleted. Finalizers are never stripped; nothing is forced.

Crash recovery
  An open DESTROY_INTENT is resolved before anything else in its step: a trusted NotFound closes it
  ``absent_confirmed``; another UID is quarantined (``delete_unproven``); the same UID needs D13 ownership and the
  gates again, is closed ``failed`` and gets a new INTENT (never an unconditional resend). A stale snapshot is
  refreshed from the journal (the store's existing rule). Every completed step is re-verified on resume and at the
  end: a destroyed object that reappears is quarantined (``recreated_after_delete``) and the run stops.

Namespaces (D3, D6, D18)
  Classes: runtime_object (a receipt UID: stop), owned_child (only ReplicaSet -> Deployment, Pod -> ReplicaSet ->
  Deployment and EndpointSlice -> Service, with ``controller: true`` and the owner's identity, namespace and receipt
  UID; never deleted directly; waited for up to 600 s, terminating children included), allowed_leftover (exactly the
  ServiceAccount ``default``, the ConfigMaps ``kube-root-ca.crt`` and ``istio-ca-root-cert`` and Events),
  istiod_leftover (istio-system Leases: not confirmed Live, so BLOCKED), k8s_certs_secret (stop) and unknown_object
  (stop). After DESTROY_INTENT a second fresh inventory must show exactly the same objects before the DELETE; an
  object added in between stops the run. Real API cascade atomicity is NOT_VERIFIED. ``kube-system`` is never
  inventoried or deleted.

CRDs (D5)
  The 17 CRDs are retained; no CRD DELETE exists. Each is read with the specialised CRD read and verified against
  the CRD receipt map (UID, group, plural, scope, storage version served, Established), then its instances are
  listed (``limit=1``): ZERO_INSTANCES, or CRD_NOT_CREATED only with no creation evidence, no open INTENT, a trusted
  NotFound and discovery not serving its group. The 15 Istio and 2 controller CRDs are reported separately.

Completion
  COMPLETE needs every destroy step in the journal, no open INTENT, no quarantine, all 45 non-CRD objects confirmed
  absent again, the G9 cleanup COMPLETE again, every CRD ZERO_INSTANCES or CRD_NOT_CREATED, ``kube-system`` present
  with its fingerprint UID, and the deadline not reached. Otherwise BLOCKED or UNKNOWN with a fixed reason.
"""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_certs_receipt as g9  # noqa: E402
import k8s_runtime  # noqa: E402
import k8s_runtime_apply as apply  # noqa: E402
import k8s_runtime_receipt as receipt  # noqa: E402
import k8s_runtime_transport as transport  # noqa: E402

NAMESPACE_PHASE = receipt.NAMESPACE_PHASE
KUBE_SYSTEM = {"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "kube-system"}
CRD_KIND = ("apiextensions.k8s.io/v1", "CustomResourceDefinition")
SETTLED_CRD = ("ZERO_INSTANCES", "CRD_NOT_CREATED")
# The order inside one destroy step (D12): dependency safety first, then a fixed kind order, then the plan order.
KIND_ORDER = ("TargetGroupBinding", "Gateway", "ValidatingAdmissionPolicyBinding", "ValidatingAdmissionPolicy",
              "MutatingWebhookConfiguration", "ValidatingWebhookConfiguration", "AuthorizationPolicy",
              "PeerAuthentication", "NetworkPolicy", "Deployment", "Service", "ClusterRoleBinding", "RoleBinding",
              "ClusterRole", "Role", "ServiceAccount", "ConfigMap", "Namespace")
# Namespaces in namespace_phase: the application namespace first, istio-system last.
NAMESPACE_ORDER = ("{project}-app", "{project}-ingress", "istio-system")
EVENTS = {("", "events"), ("events.k8s.io", "events")}
LEFTOVER_CONFIGMAPS = ("kube-root-ca.crt", "istio-ca-root-cert")
TGB_RESOURCE = ("elbv2.k8s.aws", "targetgroupbindings")
LEASES = ("coordination.k8s.io", "leases")
WAIT_SECONDS = {"TargetGroupBinding": transport.TGB_FINALIZER_TIMEOUT_SECONDS,
                "Namespace": transport.NAMESPACE_TERMINATION_TIMEOUT_SECONDS}
STATUS = ("COMPLETE", "BLOCKED", "UNKNOWN")


class DestroyStop(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status, self.reason = status, reason


def halt(status, reason):
    raise DestroyStop(status, reason)


def transport_status(code):
    return "BLOCKED" if code in ("forbidden", "inventory_forbidden") else "UNKNOWN"


def identity_of(key):
    return dict(zip(("apiVersion", "kind", "namespace", "name"), key.split("|")))


def bounded_server(server, deadline):
    """The G9 client's fake server under the run's global deadline and the D11 20 s request bound.

    No request starts at or after the deadline; an answer at or after it, or later than 20 s, is a timeout, which
    G9 records as BLOCKED (``transport_timeout``). G9 itself is unchanged."""
    def call(request):
        if deadline.expired():
            raise TimeoutError("deadline_exceeded")
        start = deadline.clock.now()
        answer = server(request)
        if deadline.expired() or deadline.clock.now() - start > transport.API_READ_TIMEOUT_SECONDS:
            raise TimeoutError("request_timeout")
        return answer
    return call


class Engine:
    def __init__(self, report, objects, receipt_root, g9_root, server, clock, cluster_arn,
                 deadline_seconds=transport.DESTROY_DEADLINE_SECONDS, transport_kind="fake"):
        self.report, self.objects_in = report, objects
        self.receipt_root, self.g9_root = receipt_root, g9_root
        self.server, self.clock, self.cluster_arn = server, clock, cluster_arn
        self.deadline_seconds, self.transport_kind = deadline_seconds, transport_kind
        self.results, self.crds, self.namespaces, self.order = {}, {}, {}, []
        self.g9_report, self.deletes = None, 0
        self.deadline = None

    # -- preflight ----------------------------------------------------------------------------------------------
    def preflight(self, expected_manifest, expected_input):
        if not isinstance(self.clock, apply.FakeClock):
            halt("BLOCKED", "fake_clock_required")
        if self.transport_kind != "fake":
            halt("BLOCKED", "real_transport_not_implemented")
        try:
            k8s_runtime.check_pins(self.report, expected_manifest, expected_input)
        except k8s_runtime.GateError as error:
            halt("BLOCKED", str(error))
        if receipt.digest(receipt.canonical(self.objects_in).encode()) != self.report["manifest_sha256"]:
            halt("BLOCKED", "objects_do_not_match_plan")
        self.project = self.report["project"]
        self.manager = k8s_runtime.runtime_manager(self.project)
        self.plan = receipt.Plan.from_report(self.report)
        counts = [(stage, len(self.plan.members[stage])) for stage in self.plan.stage_order]
        if counts != list(k8s_runtime.STAGE_COUNTS) or sum(n for _, n in counts) != k8s_runtime.RESOURCE_COUNT:
            halt("BLOCKED", "plan_stage_table_changed")
        self.manifests = {}
        for obj in self.objects_in:
            if obj.get("kind") == "Secret":
                halt("BLOCKED", "secret_in_bundle")
            self.manifests.setdefault(receipt.key_of(apply.identity_of(obj)), []).append(obj)
        keys = [k for stage in self.plan.stage_order for k in self.plan.members[stage]]
        if sorted(self.manifests) != sorted(keys) or any(len(v) != 1 for v in self.manifests.values()):
            halt("BLOCKED", "manifest_not_in_bundle")
        self.crd_keys = [k for k in keys if tuple(k.split("|")[:2]) == CRD_KIND]
        self.istio_crds = [k.split("|")[3] for k in self.plan.members["base"] if tuple(k.split("|")[:2]) == CRD_KIND]
        self.controller_crds = [k.split("|")[3] for k in self.plan.members["controller"]
                                if tuple(k.split("|")[:2]) == CRD_KIND]
        if (len(self.crd_keys), len(self.istio_crds), len(self.controller_crds)) != (17, 15, 2):
            halt("BLOCKED", "plan_crd_count_changed")
        self.non_crd = [k for k in keys if k not in self.crd_keys]
        # One global deadline for the whole run: never extended, reset or replaced (D11).
        self.deadline = transport.Deadline(self.clock, self.deadline_seconds)
        probe = transport.open_destroy_transport(
            self.transport_kind, transport.DestroyPolicy(self.project, receipt.plan_identities(self.plan)),
            self.server, self.deadline)
        try:
            kube_system = probe.get_metadata(KUBE_SYSTEM)
        except transport.TransportError as error:
            halt(transport_status(str(error)), "fingerprint_unreadable:" + str(error))
        try:
            self.fp = receipt.fingerprint(self.cluster_arn, (kube_system or {}).get("uid"))
        except receipt.ReceiptError:
            halt("BLOCKED", "fingerprint_unreadable")
        self.expected = {"fingerprint": self.fp, "project": self.project,
                         "manifest_sha256": self.report["manifest_sha256"], "input_sha256": self.report["input_sha256"]}
        self.directory = Path(self.receipt_root).expanduser() / self.fp["id"]
        if not os.path.lexists(self.directory):
            halt("BLOCKED", "receipt:receipt_missing")  # never a fresh start: no receipt, no destroy
        state = receipt.load(self.directory, self.plan, self.expected)["state"]
        if state["open_intent"] is not None and state["phase"] == "apply":
            halt("BLOCKED", "unresolved_apply_intent")
        if state["quarantined"]:
            halt("BLOCKED", "quarantined")
        try:
            g9_directory = g9.receipt_directory(Path(self.g9_root).expanduser(), self.fp, create=False)
            with g9.locked(g9_directory):
                g9.load_receipt(g9_directory, self.project, self.fp)
        except g9.CleanupError as error:
            halt("BLOCKED", "g9:" + str(error))

    def open_transport(self, state):
        """The run's destroy transport: scopes from the reviewed plan and the verified journal only."""
        specs = dict(transport.crd_spec_from_manifest(self.manifests[k][0]) for k in self.crd_keys)
        gateway_service = {"apiVersion": "v1", "kind": "Service", "namespace": self.project + "-ingress",
                           "name": self.project + "-gateway"}
        policy = transport.DestroyPolicy(self.project, receipt.plan_identities(self.plan),
                                         owned_uids=receipt.owned_uids(state), inventory=True, discovery=True,
                                         crd_specs=specs, services=[gateway_service],
                                         crd_receipt_uids=receipt.crd_receipt_uids(state))
        self.policy = policy
        self.gateway_service = gateway_service
        self.fake = transport.open_destroy_transport(self.transport_kind, policy, self.server, self.deadline)

    # -- journal ------------------------------------------------------------------------------------------------
    def load(self):
        self.state = receipt.load(self.store.dir, self.plan, self.expected)["state"]
        return self.state

    def receipt_uids(self):
        return {v["owned_uid"] for v in self.state["objects"].values() if v["owned_uid"] is not None}

    # -- reads --------------------------------------------------------------------------------------------------
    def read(self, identity):
        try:
            return self.fake.get_metadata(identity)
        except transport.TransportError as error:
            halt(transport_status(str(error)), "read:" + str(error))

    def ownership(self, identity, metadata):
        observed = apply.observed_of({"apiVersion": identity["apiVersion"], "kind": identity["kind"],
                                      "metadata": metadata}, self.manifests[receipt.key_of(identity)][0])
        return apply.d13_ownership(observed, self.manager)

    def discovery(self):
        found = self.fake.discover_all()
        if found["status"] != "COMPLETE":
            halt(found["status"] if found["status"] in STATUS else "UNKNOWN", "discovery:" + str(found["reason"]))
        return found.get("evidence")

    def inventory(self, namespace):
        evidence = self.discovery()
        listed = self.fake.inventory_namespace(evidence, namespace)
        if listed["status"] != "COMPLETE":
            halt(listed["status"] if listed["status"] in STATUS else "UNKNOWN",
                 "inventory:" + namespace + ":" + str(listed["reason"]))
        return listed.get("objects", [])

    # -- per object ---------------------------------------------------------------------------------------------
    def record(self, key, category):
        self.results[key] = category

    def wait_absent(self, identity, uid):
        """Poll an independent metadata read until a trusted NotFound, bounded by the kind's D11 wait."""
        limit = self.clock.now() + WAIT_SECONDS.get(identity["kind"], 0)
        while True:
            metadata = self.read(identity)
            if metadata is None:
                return None
            if metadata["uid"] != uid:
                return metadata["uid"]
            if self.clock.now() >= limit:
                halt("BLOCKED", ("tgb_finalizer_stuck" if identity["kind"] == "TargetGroupBinding" else
                                 "namespace_termination_timeout" if identity["kind"] == "Namespace" else
                                 "delete_not_confirmed") + ":" + identity["name"])
            self.clock.sleep(transport.DESTROY_POLL_SECONDS)

    def confirm_destroyed(self, key, identity, obj):
        """A destroyed object must stay absent; one that reappears is quarantined, never deleted or adopted."""
        metadata = self.read(identity)
        if metadata is not None:
            self.store.quarantine(identity, metadata["uid"], "recreated_after_delete")
            halt("BLOCKED", "recreated_after_destroy:" + identity["name"])
        self.record(key, obj["destroyed"])

    def delete_owned(self, step, key, identity, uid, metadata):
        """DESTROY_INTENT, the UID-precondition DELETE, a trusted NotFound, DESTROY_RESULT."""
        if self.plan.destroy_step(key) != step or step != self.next_step():
            halt("BLOCKED", "journal_step_mismatch")
        if self.deadline.expired():
            halt("UNKNOWN", "deadline_exceeded")
        seq = self.store.destroy_intent(identity, uid)
        if metadata is None:
            # Owned but already absent: an independent read, never a DELETE; recorded apart from a deletion.
            if self.read(identity) is not None:
                halt("BLOCKED", "absence_not_confirmed:" + identity["name"])
            self.store.destroy_result(seq, identity, "absent_confirmed")
            self.record(key, "absent_confirmed")
            return
        try:
            self.fake.delete_runtime(identity, uid)
        except transport.TransportError as error:
            # The DELETE's outcome is unknown: the INTENT stays open and the next run rechecks it.
            halt(transport_status(str(error)), "delete:" + str(error) + ":" + identity["name"])
        self.deletes += 1
        observed = self.wait_absent(identity, uid)
        if observed is not None:
            self.store.quarantine(identity, observed, "recreated_after_delete")
            halt("BLOCKED", "recreated_after_delete:" + identity["name"])
        self.store.destroy_result(seq, identity, "deleted")
        self.record(key, "deleted")

    def destroy_object(self, step, key):
        identity = identity_of(key)
        obj = self.state["objects"].get(key)
        if key in self.state["quarantined"]:
            halt("BLOCKED", "quarantined:" + identity["name"])
        if obj is not None and obj.get("destroyed") in receipt.DESTROYED:
            return self.confirm_destroyed(key, identity, obj)
        owned = obj["owned_uid"] if obj is not None else None
        metadata = self.read(identity)
        if owned is None:
            if metadata is not None:
                halt("BLOCKED", "not_owned:" + identity["name"])  # never adopted
            self.record(key, "never_created")
            return
        if metadata is not None:
            if metadata["uid"] != owned:
                self.store.quarantine(identity, metadata["uid"], "uid_changed_before_delete")
                halt("BLOCKED", "uid_changed:" + identity["name"])
            verdict = self.ownership(identity, metadata)
            if verdict != "OWNED":
                halt("BLOCKED", verdict.lower() + ":" + identity["name"])
        self.delete_owned(step, key, identity, owned, metadata)

    def resolve_open_intent(self):
        """An interrupted DELETE (crash before or after it): recheck, never resend unconditionally."""
        intent = self.state["open_intent"]
        if intent is None:
            return
        identity = identity_of(intent["key"])
        metadata = self.read(identity)
        if metadata is None:
            self.store.destroy_result(intent["seq"], identity, "absent_confirmed")
        elif metadata["uid"] != intent["uid"]:
            self.store.quarantine(identity, metadata["uid"], "delete_unproven")
            halt("BLOCKED", "uid_changed_after_intent:" + identity["name"])
        else:
            verdict = self.ownership(identity, metadata)
            self.store.destroy_result(intent["seq"], identity, "failed", metadata["uid"])
            if verdict != "OWNED":
                halt("BLOCKED", verdict.lower() + ":" + identity["name"])
        self.load()

    def next_step(self):
        done = self.state["destroy_stages_done"]
        return self.plan.destroy_order[len(done)] if len(done) < len(self.plan.destroy_order) else None

    def ordered(self, step):
        keys = self.plan.destroy_members(step)
        position = {k: i for i, k in enumerate(keys)}
        if step == NAMESPACE_PHASE:
            names = [n.format(project=self.project) for n in NAMESPACE_ORDER]
            return sorted(keys, key=lambda k: names.index(k.split("|")[3]))
        return sorted(keys, key=lambda k: (KIND_ORDER.index(k.split("|")[1]), position[k]))

    # -- gates (D12) --------------------------------------------------------------------------------------------
    def tgb_identity(self):
        return next(identity_of(k) for k in self.plan.members["ingress"] if k.split("|")[1] == "TargetGroupBinding")

    def foreign_tgbs(self, allowed_uid):
        ingress = self.project + "-ingress"
        return [o for o in self.inventory(ingress) if TGB_RESOURCE in {tuple(r) for r in o["resources"]}
                and o["uid"] != allowed_uid]

    def tgb_gone(self):
        if self.read(self.tgb_identity()) is not None:
            halt("BLOCKED", "target_group_binding_remains")
        if self.foreign_tgbs(None):
            halt("BLOCKED", "target_group_binding_remains")

    def no_load_balancer(self):
        ingress = self.project + "-ingress"
        service_key = receipt.key_of(self.gateway_service)
        runtime = (self.state["objects"].get(service_key) or {}).get("owned_uid")
        for item in self.inventory(ingress):
            if ("", "services") not in {tuple(r) for r in item["resources"]}:
                continue
            if runtime is None or item["uid"] != runtime:
                halt("BLOCKED", "unknown_service:" + item["name"])
            try:
                service = self.fake.read_service_type(self.gateway_service)
            except transport.TransportError as error:
                halt(transport_status(str(error)), "service_type:" + str(error))
            if service is None or service["uid"] != runtime:
                halt("UNKNOWN", "service_type_inconsistent")
            if service["load_balancer"]:
                halt("BLOCKED", "load_balancer_service_remains")

    def gate(self, step):
        if step == "ingress":
            tgb = (self.state["objects"].get(receipt.key_of(self.tgb_identity())) or {}).get("owned_uid")
            if self.foreign_tgbs(tgb):
                halt("BLOCKED", "foreign_target_group_binding")
        elif step == "admission":
            self.tgb_gone()
            self.no_load_balancer()
        elif step == "controller":
            self.tgb_gone()
        elif step in ("istiod", "base"):
            self.require_crds(self.istio_crds)
        elif step == NAMESPACE_PHASE:
            self.g9_cleanup()

    # -- CRDs (D5) ----------------------------------------------------------------------------------------------
    def crd_verdict(self, name, advertised):
        key = "|".join(CRD_KIND + ("", name))
        obj = self.state["objects"].get(key)
        if key in self.state["quarantined"]:
            return {"verdict": "BLOCKED", "reason": "crd_quarantined"}
        try:
            read = self.fake.read_crd(name)
        except transport.TransportError as error:
            return {"verdict": transport_status(str(error)), "reason": str(error)}
        owned = self.policy.crd_receipt_uid(name)
        if read["state"] == "absent":
            if obj is not None and owned is None:
                return {"verdict": "UNKNOWN", "reason": "crd_creation_evidence"}
            open_intent = (self.state["open_intent"] or {}).get("key") == key
            found = transport.classify_crd(self.policy, name, ("absent", None), owned, open_intent,
                                           self.policy.crd_spec(name)["group"] in advertised)
            return {"verdict": found["verdict"], "reason": found["reason"]}
        verified = self.fake.verify_crd(read["evidence"])
        if verified["verdict"] != "VERIFIED":
            return {"verdict": verified["verdict"], "reason": verified["reason"]}
        counted = self.fake.crd_instances(verified["evidence"])
        return {"verdict": counted["verdict"], "reason": counted["reason"]}

    def check_crds(self, names):
        evidence = self.discovery()
        payload = transport.evidence_payload(evidence, self.policy, "discovery")
        advertised = {group for group, _ in payload["advertised"]}
        return {name: self.crd_verdict(name, advertised) for name in names}

    def require_crds(self, names):
        for name, found in self.check_crds(names).items():
            self.crds[name] = found
            if found["verdict"] not in SETTLED_CRD:
                halt("BLOCKED" if found["verdict"] == "BLOCKED" else "UNKNOWN",
                     "crd:" + name + ":" + str(found["reason"]))

    # -- G9 -----------------------------------------------------------------------------------------------------
    def g9_cleanup(self):
        if self.deadline.expired():
            halt("UNKNOWN", "deadline_exceeded")
        try:
            report = g9.cleanup(self.project, self.cluster_arn, root=Path(self.g9_root).expanduser(),
                                transport_kind=self.transport_kind, server=bounded_server(self.server, self.deadline))
        except g9.CleanupError as error:
            halt("BLOCKED", "g9:" + str(error))
        self.g9_report = report
        if report["result"] != "COMPLETE" or report["kube_system_webhook_tls"] != "MET":
            reason = next((r["reason"] for r in report["secrets"] if r["state"] not in g9.CLEANED), None)
            halt("BLOCKED", "g9_cleanup_incomplete:" + str(reason))
        return report

    # -- namespaces (D3, D6, D18) -------------------------------------------------------------------------------
    def classify(self, namespace, item, children):
        resources = {tuple(r) for r in item["resources"]}
        secrets = {(i["namespace"], i["name"]) for i in transport.secret_identities(self.project)}
        if item["uid"] in self.receipt_uids():
            return "runtime_object"
        if resources == {("", "secrets")}:
            return "k8s_certs_secret" if (namespace, item["name"]) in secrets else "unknown_object"
        if resources and resources <= EVENTS:
            return "allowed_leftover"
        if resources == {("", "serviceaccounts")} and item["name"] == "default":
            return "allowed_leftover"
        if resources == {("", "configmaps")} and item["name"] in LEFTOVER_CONFIGMAPS:
            return "allowed_leftover"
        controllers = [o for o in item["owners"] if o["controller"] is True]
        if len(controllers) == 1:
            owner = controllers[0]
            if resources == {("apps", "replicasets")} and (owner["apiVersion"], owner["kind"]) == ("apps/v1",
                                                                                                  "Deployment"):
                if self.owner_uid("apps/v1", "Deployment", namespace, owner["name"]) == owner["uid"]:
                    children[item["uid"]] = item["name"]
                    return "owned_child"
            if resources == {("", "pods")} and (owner["apiVersion"], owner["kind"]) == ("apps/v1", "ReplicaSet"):
                if children.get(owner["uid"]) == owner["name"]:
                    return "owned_child"
            if resources == {("discovery.k8s.io", "endpointslices")} and (owner["apiVersion"], owner["kind"]) == \
                    ("v1", "Service"):
                if self.owner_uid("v1", "Service", namespace, owner["name"]) == owner["uid"]:
                    return "owned_child"
        if namespace == "istio-system" and resources == {LEASES}:
            return "istiod_leftover"
        return "unknown_object"

    def owner_uid(self, api_version, kind, namespace, name):
        obj = self.state["objects"].get("|".join((api_version, kind, namespace, name)))
        return obj["owned_uid"] if obj is not None else None

    def namespace_contents(self, namespace, wait):
        """A fresh COMPLETE inventory with only allowed leftovers; owned children are waited for (600 s)."""
        limit = self.clock.now() + transport.OWNED_CHILD_TIMEOUT_SECONDS
        children = {}
        while True:
            items = self.inventory(namespace)
            classes = {}
            for item in sorted(items, key=lambda i: (("apps", "replicasets") not in
                                                     {tuple(r) for r in i["resources"]}, i["uid"])):
                classes[item["uid"]] = self.classify(namespace, item, children)
            for item in items:
                found = classes[item["uid"]]
                if found in ("runtime_object", "k8s_certs_secret", "istiod_leftover", "unknown_object"):
                    halt("BLOCKED", found + ":" + namespace + ":" + item["name"])
            if not any(found == "owned_child" for found in classes.values()):
                return sorted(classes)
            if not wait or self.clock.now() >= limit:
                halt("BLOCKED", "owned_child_remains:" + namespace)
            self.clock.sleep(transport.DESTROY_POLL_SECONDS)

    def destroy_namespace(self, key):
        identity = identity_of(key)
        name = identity["name"]
        obj = self.state["objects"].get(key)
        if obj is not None and obj.get("destroyed") in receipt.DESTROYED:
            self.namespaces[name] = "DELETED_EARLIER"
            return self.confirm_destroyed(key, identity, obj)
        owned = obj["owned_uid"] if obj is not None else None
        metadata = self.read(identity)
        if owned is None:
            if metadata is not None:
                halt("BLOCKED", "not_owned:" + name)
            self.namespaces[name] = "NEVER_CREATED"
            return self.record(key, "never_created")
        if metadata is not None:
            if metadata["uid"] != owned:
                self.store.quarantine(identity, metadata["uid"], "uid_changed_before_delete")
                halt("BLOCKED", "uid_changed:" + name)
            verdict = self.ownership(identity, metadata)
            if verdict != "OWNED":
                halt("BLOCKED", verdict.lower() + ":" + name)
            conditions = (self.g9_report or {}).get("namespace_secret_condition") or {}
            if name != self.project + "-app" and conditions.get(name) != "MET":
                halt("BLOCKED", "g9_namespace_secret_condition:" + name)
            if name == self.project + "-ingress":
                self.tgb_gone()
            first = self.namespace_contents(name, wait=True)
            seq = self.store.destroy_intent(identity, owned)
            # Race protection (fake contract): the contents must be unchanged right before the DELETE.
            second = self.namespace_contents(name, wait=False)
            if second != first:
                self.store.destroy_result(seq, identity, "failed", metadata["uid"])
                halt("BLOCKED", "namespace_changed_after_inventory:" + name)
            if self.deadline.expired():
                halt("UNKNOWN", "deadline_exceeded")
            try:
                self.fake.delete_runtime(identity, owned)
            except transport.TransportError as error:
                halt(transport_status(str(error)), "delete:" + str(error) + ":" + name)
            self.deletes += 1
            observed = self.wait_absent(identity, owned)
            if observed is not None:
                self.store.quarantine(identity, observed, "recreated_after_delete")
                halt("BLOCKED", "recreated_after_delete:" + name)
            self.store.destroy_result(seq, identity, "deleted")
            self.namespaces[name] = "DELETED"
            return self.record(key, "deleted")
        self.namespaces[name] = "ABSENT_CONFIRMED"
        return self.delete_owned(NAMESPACE_PHASE, key, identity, owned, None)

    # -- the run ------------------------------------------------------------------------------------------------
    def run_step(self, step):
        self.gate(step)
        self.resolve_open_intent()
        for key in self.ordered(step):
            self.order.append(key)
            if step == NAMESPACE_PHASE:
                self.destroy_namespace(key)
            else:
                self.destroy_object(step, key)
        self.store.destroy_stage_done(step)
        self.load()

    def revalidate(self, step):
        for key in self.plan.destroy_members(step):
            obj = self.state["objects"].get(key)
            if obj is not None and obj.get("destroyed") in receipt.DESTROYED:
                self.confirm_destroyed(key, identity_of(key), obj)
            elif obj is not None and obj["owned_uid"] is not None:
                halt("BLOCKED", "journal_step_incomplete:" + key)
            elif self.read(identity_of(key)) is not None:
                halt("BLOCKED", "not_owned:" + identity_of(key)["name"])
            else:
                self.record(key, "never_created")

    def complete(self):
        state = self.load()
        if state["phase"] != "destroy" or state["destroy_stages_done"] != self.plan.destroy_order:
            halt("BLOCKED", "journal_incomplete")
        if state["open_intent"] is not None or state["quarantined"]:
            halt("BLOCKED", "journal_unresolved")
        for step in self.plan.destroy_order:
            self.revalidate(step)
        if sorted(self.results) != sorted(self.non_crd):
            halt("BLOCKED", "objects_not_all_judged")
        self.g9_cleanup()  # again: the four Secrets are confirmed absent through G9's own reads
        self.require_crds(self.istio_crds + self.controller_crds)
        kube_system = self.read(KUBE_SYSTEM)
        if kube_system is None or kube_system.get("uid") != self.fp["kube_system_uid"]:
            halt("BLOCKED", "kube_system_not_retained")
        if self.deadline.expired():
            halt("UNKNOWN", "deadline_exceeded")
        return "COMPLETE"

    def run(self, expected_manifest, expected_input):
        self.preflight(expected_manifest, expected_input)
        self.store = receipt.Store(self.receipt_root, self.fp, self.project, self.report["manifest_sha256"],
                                   self.report["input_sha256"], self.plan)
        with self.store.lock():
            self.store.begin()  # verifies the journal; refreshes only a stale snapshot; never creates a journal
            state = self.load()
            if state["phase"] == "apply":
                self.store.begin_destroy()
                state = self.load()
            self.open_transport(state)
            for step in self.plan.destroy_order:
                if step in self.state["destroy_stages_done"]:
                    self.revalidate(step)
                else:
                    self.run_step(step)
            return self.complete()


def summary(engine):
    counts = {"deleted": 0, "absent_confirmed": 0, "never_created": 0}
    for category in engine.results.values():
        counts[category] += 1
    crds = {"istio": {n: engine.crds.get(n, {}).get("verdict") for n in getattr(engine, "istio_crds", [])},
            "controller": {n: engine.crds.get(n, {}).get("verdict") for n in getattr(engine, "controller_crds", [])}}
    return {"objects": dict(sorted(engine.results.items())), "counts": counts, "crds": crds,
            "retained_crds": sum(1 for g in crds.values() for v in g.values() if v in SETTLED_CRD),
            "namespaces": dict(engine.namespaces), "secrets": engine.g9_report, "order": list(engine.order),
            "deletes": engine.deletes}


def destroy(report, objects, receipt_root, g9_root, server, clock, expected_manifest, expected_input, cluster_arn,
            deadline_seconds=transport.DESTROY_DEADLINE_SECONDS, transport_kind="fake"):
    """Fake-only destroy. Returns a report; never raises for a stop. COMPLETE is never Live evidence."""
    engine = Engine(report, objects, receipt_root, g9_root, server, clock, cluster_arn, deadline_seconds,
                    transport_kind)
    try:
        status, reason = engine.run(expected_manifest, expected_input), None
    except DestroyStop as stopped:
        status, reason = stopped.status, stopped.reason
    except receipt.ReceiptError as error:
        status, reason = "BLOCKED", "receipt:" + str(error)
    except transport.TransportError as error:
        status, reason = transport_status(str(error)), "transport:" + str(error)
    except g9.CleanupError as error:
        status, reason = "BLOCKED", "g9:" + str(error)
    result = {"status": status, "reason": reason, "executor": "fake", "live": "NOT_TESTED",
              "kube_system": "NEVER_DELETED", "evidence_source": "FAKE_API_ONLY"}
    result.update(summary(engine))
    return result
