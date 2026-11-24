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
  rendered objects; the runtime contract version; the repository's reviewed stage table as the only stage layout:
  the report and the bundle must equal it in stage names and order and in each stage's identities and their order
  (9 stages, 62 objects, 17 CRDs, 45 other objects), and the destroy order comes from it; one global D11 deadline
  for the whole run. The cluster fingerprint (D17) is the
  cluster ARN plus the ``kube-system`` UID read through the destroy transport. The runtime receipt of that
  fingerprint must exist and verify (journal chain, snapshot, project, fingerprint, pins); a missing, corrupt or
  other-fingerprint receipt stops before anything is written, and no new receipt or journal is ever created: the
  store is opened ``existing_only`` (no directory, journal or HEADER; a missing journal or snapshot is never
  repaired, only a verified stale snapshot is refreshed). An unresolved apply INTENT or any QUARANTINE stops. The G9
  registration receipt of exactly this project and runtime fingerprint must hold all four Secrets REGISTERED with
  valid UIDs. After the lock, before the first journal write, everything is checked again (fingerprint, project,
  pins, journal and snapshot, phase, open INTENT, quarantine, G9) and the DELETE and CRD maps come from that locked
  journal (``owned_uids``, ``crd_receipt_uids``); the plan identities come from the reviewed table; nothing a read
  returns can widen them, and there is no ownership input. The fingerprint is read again before every step and
  every G9 cleanup; G9's own kube-system read must show the runtime's UID, otherwise G9 stops before any Secret
  request.

Order (D12, dependency safety over plain reverse order)
  The apply stages reversed, then ``namespace_phase`` with every Namespace: ingress, binding_writer, admission,
  mesh_security, gateway, istiod, controller, base, namespaces (no deletable member), namespace_phase. Inside a
  stage a fixed kind order: the TargetGroupBinding first, policy bindings before policies, webhook configurations
  before their Deployments, then workloads, Services, RBAC, ServiceAccounts and ConfigMaps. Gates:
  - ingress: no TargetGroupBinding outside the receipt in ``<project>-ingress``;
  - admission and controller: no TargetGroupBinding anywhere: the runtime one trusted absent, none listed in
    ``<project>-ingress`` and the TargetGroupBinding CRD's cluster-wide instance LIST empty (or the CRD strictly never
    created); before admission, no LoadBalancer Service and no unknown Service in ``<project>-ingress`` (the runtime
    Service by exact resource, namespace, name and receipt UID, its ``spec.type`` from the specialised read);
  - istiod and base: every Istio CRD ZERO_INSTANCES or CRD_NOT_CREATED before an Istio webhook goes;
  - namespace_phase: the G9 cleanup COMPLETE (including the kube-system webhook TLS Secret) and, per namespace,
    a fresh discovery and a COMPLETE metadata inventory with only allowed leftovers (D3, D6, D18).
  The same dependency evidence is read fresh again right before every dependency-sensitive DELETE (each admission
  and controller object, each Istio webhook, a Deployment after its stage's webhooks are confirmed gone), not only
  at the start of a step.
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
  ``absent_confirmed``; another UID is quarantined (``delete_unproven``); the same UID already terminating needs D13
  ownership and the dependency gates again and then waits for absence under the same INTENT, with no new DELETE; the
  same UID not terminating is closed ``failed`` and gets a new INTENT through the per-object checks (never an
  unconditional resend). Every wait has its own D11 bound on the fake clock; a read that completes after that local
  deadline is never evidence, and a poll never sleeps past it. A stale snapshot is
  refreshed from the journal (the store's existing rule). Every completed step is re-verified on resume and at the
  end: a destroyed object that reappears is quarantined (``recreated_after_delete``) and the run stops.

Namespaces (D3, D6, D18)
  Classes: runtime_object (a receipt UID: stop), owned_child (only ReplicaSet -> Deployment, Pod -> ReplicaSet ->
  Deployment and EndpointSlice -> Service, with ``controller: true`` and the owner's identity, namespace and receipt
  UID; never deleted directly; waited for up to 600 s, terminating children included), allowed_leftover (exactly the
  ServiceAccount ``default``, the ConfigMaps ``kube-root-ca.crt`` and ``istio-ca-root-cert`` and Events),
  istiod_leftover (istio-system Leases: not confirmed Live, so BLOCKED), k8s_certs_secret (stop) and unknown_object
  (stop). The owner chain is proven from the current inventory alone. After DESTROY_INTENT a final gate reads the
  namespace's identity, receipt UID and D13 ownership again, takes fresh G9 evidence and the TargetGroupBinding gate,
  checks the fingerprint, and then a last fresh inventory must equal the first in every safety field (identity,
  resources, owners, deletion state, finalizers, class); a failed final gate closes the INTENT ``failed``. An object
  added after that last inventory and before the DELETE is not detected (a residual race of this Fake contract,
  reported for an Owner decision); real API cascade atomicity is NOT_VERIFIED. ``kube-system`` is never inventoried
  or deleted.

CRDs (D5)
  The 17 CRDs are retained; no CRD DELETE exists. Each is read with the specialised CRD read and verified against
  the CRD receipt map (UID, group, plural, scope, storage version served, Established), then its instances are
  listed (``limit=1``) only when a fresh discovery maps exactly its group, storage version and plural with its scope:
  ZERO_INSTANCES, or CRD_NOT_CREATED only with no creation evidence, no receipt UID, no open INTENT, no quarantine, a
  trusted NotFound and a COMPLETE discovery that does not serve its exact group and plural (another CRD of the same
  group is no reason to refuse it). The 15 Istio and 2 controller CRDs are reported separately, and the report
  separates retained (created, zero instances) from CRD_NOT_CREATED.

Completion
  COMPLETE needs every destroy step in the journal, no open INTENT, no quarantine, all 45 non-CRD objects confirmed
  absent again, the G9 cleanup COMPLETE again, every CRD ZERO_INSTANCES or CRD_NOT_CREATED, ``kube-system`` present
  with its fingerprint UID, and the deadline not reached. Otherwise BLOCKED or UNKNOWN with a fixed reason.
"""
import json
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
KUBE_SYSTEM_PATH = "/api/v1/namespaces/kube-system"
CRD_KIND = ("apiextensions.k8s.io/v1", "CustomResourceDefinition")
TGB_CRD = "targetgroupbindings.elbv2.k8s.aws"
SETTLED_CRD = ("ZERO_INSTANCES", "CRD_NOT_CREATED")
# The order inside one destroy step (D12): dependency safety first, then a fixed kind order, then the plan order.
KIND_ORDER = ("TargetGroupBinding", "Gateway", "ValidatingAdmissionPolicyBinding", "ValidatingAdmissionPolicy",
              "MutatingWebhookConfiguration", "ValidatingWebhookConfiguration", "AuthorizationPolicy",
              "PeerAuthentication", "NetworkPolicy", "Deployment", "Service", "ClusterRoleBinding", "RoleBinding",
              "ClusterRole", "Role", "ServiceAccount", "ConfigMap", "Namespace")
WEBHOOK_KINDS = ("MutatingWebhookConfiguration", "ValidatingWebhookConfiguration")
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


class FingerprintChanged(Exception):
    """Raised to the G9 client when its kube-system read shows another cluster; G9 then stops before any DELETE."""


def halt(status, reason):
    raise DestroyStop(status, reason)


def transport_status(code):
    return "BLOCKED" if code in ("forbidden", "inventory_forbidden") else "UNKNOWN"


def identity_of(key):
    return dict(zip(("apiVersion", "kind", "namespace", "name"), key.split("|")))


def row_identity(row):
    return dict(zip(("apiVersion", "kind", "namespace", "name"), row))


class bounded_server:
    """The G9 client's fake server under the run's global deadline, the D11 20 s request bound and the runtime's
    cluster fingerprint.

    No request starts at or after the deadline; an answer at or after it, or later than 20 s, is a timeout, which
    G9 records as BLOCKED (``transport_timeout``). A kube-system read showing another UID than the runtime receipt's
    fingerprint is refused (``tripped``), so G9 stops at its fingerprint check before any Secret request. G9 itself
    is unchanged."""

    def __init__(self, server, deadline, kube_system_uid=None):
        self.server, self.deadline, self.kube_system_uid, self.tripped = server, deadline, kube_system_uid, False

    def __call__(self, request):
        deadline = self.deadline
        if deadline.expired():
            raise TimeoutError("deadline_exceeded")
        start = deadline.clock.now()
        answer = self.server(request)
        if deadline.expired() or deadline.clock.now() - start > transport.API_READ_TIMEOUT_SECONDS:
            raise TimeoutError("request_timeout")
        if self.kube_system_uid is not None and request.get("path") == KUBE_SYSTEM_PATH:
            try:
                observed = json.loads(answer[1])["metadata"]["uid"]
            except (ValueError, KeyError, TypeError, IndexError):
                observed = None
            if observed != self.kube_system_uid:
                self.tripped = True
                raise FingerprintChanged("fingerprint_changed")
        return answer


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
        if self.report.get("runtime_contract_version") != k8s_runtime.CONTRACT_VERSION:
            halt("BLOCKED", "runtime_contract_version_mismatch")
        if receipt.digest(receipt.canonical(self.objects_in).encode()) != self.report["manifest_sha256"]:
            halt("BLOCKED", "objects_do_not_match_plan")
        self.project = self.report["project"]
        self.manager = k8s_runtime.runtime_manager(self.project)
        # The repository's reviewed stage table is the only source of the stage layout (B4B-F01): names, order,
        # each stage's identities and their order. The caller's report and the bundle must equal it exactly.
        try:
            table = k8s_runtime.load_stage_table(self.project)
        except k8s_runtime.PlanError as error:
            halt("BLOCKED", "stage_table:" + str(error))
        reported = [(s.get("name"), [(o.get("apiVersion"), o.get("kind"), o.get("namespace"), o.get("name"))
                                     for o in s.get("objects", [])]) for s in self.report.get("stages", [])]
        if reported != [(name, list(rows)) for name, rows in table]:
            halt("BLOCKED", "plan_stage_identity_mismatch")
        bundle = [tuple(receipt.key_of(apply.identity_of(o)).split("|")) if o.get("kind") != "Secret" else None
                  for o in self.objects_in]
        if bundle != [row for _, rows in table for row in rows]:
            halt("BLOCKED", "bundle_stage_identity_mismatch")
        self.plan = receipt.Plan([(name, [row_identity(r) for r in rows]) for name, rows in table])
        counts = [(stage, len(self.plan.members[stage])) for stage in self.plan.stage_order]
        if counts != list(k8s_runtime.STAGE_COUNTS) or sum(n for _, n in counts) != k8s_runtime.RESOURCE_COUNT:
            halt("BLOCKED", "plan_stage_table_changed")
        self.manifests = {receipt.key_of(apply.identity_of(o)): o for o in self.objects_in}
        keys = [k for stage in self.plan.stage_order for k in self.plan.members[stage]]
        self.crd_keys = [k for k in keys if tuple(k.split("|")[:2]) == CRD_KIND]
        self.istio_crds = [k.split("|")[3] for k in self.plan.members["base"] if tuple(k.split("|")[:2]) == CRD_KIND]
        self.controller_crds = [k.split("|")[3] for k in self.plan.members["controller"]
                                if tuple(k.split("|")[:2]) == CRD_KIND]
        if (len(self.crd_keys), len(self.istio_crds), len(self.controller_crds)) != (17, 15, 2) \
                or TGB_CRD not in self.controller_crds:
            halt("BLOCKED", "plan_crd_count_changed")
        self.non_crd = [k for k in keys if k not in self.crd_keys]
        # One global deadline for the whole run: never extended, reset or replaced (D11).
        self.deadline = transport.Deadline(self.clock, self.deadline_seconds)
        self.probe = transport.open_destroy_transport(
            self.transport_kind, transport.DestroyPolicy(self.project, receipt.plan_identities(self.plan)),
            self.server, self.deadline)
        try:
            kube_system = self.probe.get_metadata(KUBE_SYSTEM)
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
        # An early read-only refusal; the locked revalidation in run() is what grants anything.
        self.check_state(receipt.load(self.directory, self.plan, self.expected)["state"])
        self.g9_eligible()

    def check_state(self, state):
        if state["open_intent"] is not None and state["phase"] == "apply":
            halt("BLOCKED", "unresolved_apply_intent")
        if state["quarantined"]:
            halt("BLOCKED", "quarantined")

    def g9_eligible(self):
        """The G9 receipt of exactly this project and runtime fingerprint, with all four Secrets REGISTERED."""
        try:
            directory = g9.receipt_directory(Path(self.g9_root).expanduser(), self.fp, create=False)
            with g9.locked(directory):
                document = g9.load_receipt(directory, self.project, self.fp)
        except g9.CleanupError as error:
            halt("BLOCKED", "g9:" + str(error))
        identities = [e["identity"] for e in document["secrets"]]
        if identities != transport.secret_identities(self.project):
            halt("BLOCKED", "g9_identity_mismatch")
        if document["result"] != "REGISTERED" or any(
                e["registration"] != "REGISTERED" or not isinstance(e["uid"], str)
                or transport.UID.fullmatch(e["uid"]) is None for e in document["secrets"]):
            halt("BLOCKED", "g9_registration_incomplete")
        cluster = document["cluster"]
        if (cluster["cluster_arn"], cluster["kube_system_uid"], cluster["fingerprint_id"]) != \
                (self.fp["cluster_arn"], self.fp["kube_system_uid"], self.fp["id"]):
            halt("BLOCKED", "g9_fingerprint_mismatch")

    def check_fingerprint(self):
        """The cluster is still the runtime receipt's (D17); a change stops every later deletion."""
        try:
            kube_system = self.probe.get_metadata(KUBE_SYSTEM)
        except transport.TransportError as error:
            halt(transport_status(str(error)), "read:" + str(error))
        if kube_system is None or kube_system.get("uid") != self.fp["kube_system_uid"]:
            halt("BLOCKED", "fingerprint_changed")

    def open_transport(self, state):
        """The run's destroy transport: scopes from the reviewed plan and the locked, verified journal only."""
        specs = dict(transport.crd_spec_from_manifest(self.manifests[k]) for k in self.crd_keys)
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
                                      "metadata": metadata}, self.manifests[receipt.key_of(identity)])
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
        """Poll an independent metadata read until a trusted NotFound, within the kind's own D11 wait (B4B-F07).

        A read that completes after the local wait deadline is never evidence; a poll never sleeps past it."""
        bound = WAIT_SECONDS.get(identity["kind"])
        limit = self.clock.now() + (bound or 0)
        while True:
            metadata = self.read(identity)
            if bound is not None and self.clock.now() > limit:
                halt("BLOCKED", self.wait_reason(identity))
            if metadata is None:
                return None
            if metadata["uid"] != uid:
                return metadata["uid"]
            if self.clock.now() >= limit:
                halt("BLOCKED", self.wait_reason(identity))
            self.clock.sleep(min(transport.DESTROY_POLL_SECONDS, limit - self.clock.now()))

    @staticmethod
    def wait_reason(identity):
        return ("tgb_finalizer_stuck" if identity["kind"] == "TargetGroupBinding" else
                "namespace_termination_timeout" if identity["kind"] == "Namespace" else
                "delete_not_confirmed") + ":" + identity["name"]

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
            self.dependencies(step, key)  # fresh evidence right before a dependency-sensitive DELETE
        self.delete_owned(step, key, identity, owned, metadata)

    def resolve_open_intent(self, step):
        """An interrupted DELETE (crash before or after it): recheck, never resend unconditionally (B4B-F07).

        Absent: ``absent_confirmed``. Another UID: quarantined. The same UID already terminating: ownership and the
        dependency gates again, then the independent absence wait continues under the same INTENT, with no new
        DELETE. The same UID not terminating (the DELETE never took effect): closed ``failed``; the object then gets a
        new INTENT through the normal per-object checks."""
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
            if verdict != "OWNED":
                self.store.destroy_result(intent["seq"], identity, "failed", metadata["uid"])
                halt("BLOCKED", verdict.lower() + ":" + identity["name"])
            if transport.object_state(metadata)["deletion_requested"]:
                self.dependencies(step, intent["key"])
                observed = self.wait_absent(identity, intent["uid"])
                if observed is not None:
                    self.store.quarantine(identity, observed, "recreated_after_delete")
                    halt("BLOCKED", "recreated_after_delete:" + identity["name"])
                self.store.destroy_result(intent["seq"], identity, "absent_confirmed")
            else:
                self.store.destroy_result(intent["seq"], identity, "failed", metadata["uid"])
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
        """No TargetGroupBinding anywhere (B4B-F04): the runtime one trusted absent, none listed in the ingress
        namespace, and the TargetGroupBinding CRD's cluster-wide instance LIST empty (or the CRD strictly never
        created)."""
        if self.read(self.tgb_identity()) is not None:
            halt("BLOCKED", "target_group_binding_remains")
        if self.foreign_tgbs(None):
            halt("BLOCKED", "target_group_binding_remains")
        found = self.check_crds([TGB_CRD])[TGB_CRD]
        if found["verdict"] not in SETTLED_CRD:
            halt("BLOCKED" if found["verdict"] == "BLOCKED" else "UNKNOWN",
                 "target_group_binding_remains" if found["reason"] == "crd_instances_remain"
                 else "tgb_crd:" + str(found["reason"]))

    def no_load_balancer(self):
        """Only the runtime Service, by exact resource, namespace, name and receipt UID, and not LoadBalancer."""
        ingress = self.project + "-ingress"
        service_key = receipt.key_of(self.gateway_service)
        runtime = (self.state["objects"].get(service_key) or {}).get("owned_uid")
        for item in self.inventory(ingress):
            resources = {tuple(r) for r in item["resources"]}
            if ("", "services") not in resources:
                continue
            if not (runtime is not None and item["uid"] == runtime and resources == {("", "services")}
                    and item["namespace"] == ingress and item["name"] == self.gateway_service["name"]):
                halt("BLOCKED", "unknown_service:" + item["name"])
            try:
                service = self.fake.read_service_type(self.gateway_service)
            except transport.TransportError as error:
                halt(transport_status(str(error)), "service_type:" + str(error))
            if service is None or service["uid"] != runtime:
                halt("UNKNOWN", "service_type_inconsistent")
            if service["load_balancer"]:
                halt("BLOCKED", "load_balancer_service_remains")

    def webhooks_gone(self, step):
        for key in self.plan.destroy_members(step):
            if key.split("|")[1] in WEBHOOK_KINDS and self.read(identity_of(key)) is not None:
                halt("BLOCKED", "webhook_remains:" + key.split("|")[3])

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

    def dependencies(self, step, key):
        """Fresh dependency evidence right before each dependency-sensitive DELETE (B4B-F04), not only at the start
        of its step: admission objects need no TargetGroupBinding and no LoadBalancer Service; controller objects
        need no TargetGroupBinding; Istio webhooks need no Istio custom resource; a Deployment needs its stage's
        webhook configurations gone first."""
        kind = key.split("|")[1]
        if step == "admission":
            self.tgb_gone()
            self.no_load_balancer()
        elif step == "controller":
            self.tgb_gone()
        if step in ("istiod", "base") and kind in WEBHOOK_KINDS:
            self.require_crds(self.istio_crds)
        if kind == "Deployment":
            self.webhooks_gone(step)

    # -- CRDs (D5) ----------------------------------------------------------------------------------------------
    def crd_verdict(self, name, served, mapping):
        key = "|".join(CRD_KIND + ("", name))
        obj = self.state["objects"].get(key)
        if key in self.state["quarantined"]:
            return {"verdict": "BLOCKED", "reason": "crd_quarantined"}
        try:
            read = self.fake.read_crd(name)
        except transport.TransportError as error:
            return {"verdict": transport_status(str(error)), "reason": str(error)}
        owned = self.policy.crd_receipt_uid(name)
        spec = self.policy.crd_spec(name)
        if read["state"] == "absent":
            if obj is not None and owned is None:
                return {"verdict": "UNKNOWN", "reason": "crd_creation_evidence"}
            open_intent = (self.state["open_intent"] or {}).get("key") == key
            found = transport.classify_crd(self.policy, name, ("absent", None), owned, open_intent,
                                           (spec["group"], spec["plural"]) in served)
            return {"verdict": found["verdict"], "reason": found["reason"]}
        verified = self.fake.verify_crd(read["evidence"])
        if verified["verdict"] != "VERIFIED":
            return {"verdict": verified["verdict"], "reason": verified["reason"]}
        # The live discovery must serve exactly this CRD: group, storage version and plural, with its scope.
        namespaced = mapping.get((spec["group"], spec["storage_version"], spec["plural"]))
        if namespaced is None:
            return {"verdict": "UNKNOWN", "reason": "crd_discovery_mapping_missing"}
        if namespaced != (spec["scope"] == "Namespaced"):
            return {"verdict": "BLOCKED", "reason": "crd_discovery_scope_mismatch"}
        counted = self.fake.crd_instances(verified["evidence"])
        return {"verdict": counted["verdict"], "reason": counted["reason"]}

    def check_crds(self, names):
        payload = self.fake.discovery_payload(self.discovery())  # fresh and this transport's own (B4B-F05)
        served = {(group, resource) for group, _, resource, _, _ in payload["resources"]}
        mapping = {(group, version, resource): namespaced for group, version, resource, _, namespaced
                   in payload["resources"]}
        return {name: self.crd_verdict(name, served, mapping) for name in names}

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
        self.check_fingerprint()
        self.g9_eligible()
        server = bounded_server(self.server, self.deadline, self.fp["kube_system_uid"])
        try:
            report = g9.cleanup(self.project, self.cluster_arn, root=Path(self.g9_root).expanduser(),
                                transport_kind=self.transport_kind, server=server)
        except g9.CleanupError as error:
            halt("BLOCKED", "fingerprint_changed" if server.tripped else "g9:" + str(error))
        if server.tripped:
            halt("BLOCKED", "fingerprint_changed")
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
        if len(controllers) == 1 and item["namespace"] == namespace:
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
        """A fresh COMPLETE inventory with only allowed leftovers; owned children are waited for within 600 s.

        The owner chain is proven from the current inventory alone (a ReplicaSet seen in an earlier poll is never
        reused); an inventory that completes after the local wait deadline is never evidence. The result is the
        safety-relevant metadata of every object, compared between inventories."""
        limit = self.clock.now() + transport.OWNED_CHILD_TIMEOUT_SECONDS
        while True:
            items = self.inventory(namespace)
            if wait and self.clock.now() > limit:
                halt("BLOCKED", "owned_child_remains:" + namespace)
            children, classes = {}, {}
            for item in sorted(items, key=lambda i: (("apps", "replicasets") not in
                                                     {tuple(r) for r in i["resources"]}, i["uid"])):
                classes[item["uid"]] = self.classify(namespace, item, children)
            for item in items:
                found = classes[item["uid"]]
                if found in ("runtime_object", "k8s_certs_secret", "istiod_leftover", "unknown_object"):
                    halt("BLOCKED", found + ":" + namespace + ":" + item["name"])
            if not any(found == "owned_child" for found in classes.values()):
                return sorted((i["uid"], i["namespace"], i["name"], tuple(sorted(tuple(r) for r in i["resources"])),
                               json.dumps(i["owners"], sort_keys=True), i["deletion_requested"],
                               tuple(i["finalizers"]), classes[i["uid"]]) for i in items)
            if not wait or self.clock.now() >= limit:
                halt("BLOCKED", "owned_child_remains:" + namespace)
            self.clock.sleep(min(transport.DESTROY_POLL_SECONDS, limit - self.clock.now()))

    def namespace_owned(self, identity, owned):
        """The namespace's exact identity, receipt UID and D13 ownership, read fresh."""
        metadata = self.read(identity)
        if metadata is None:
            return None
        if metadata["uid"] != owned:
            self.store.quarantine(identity, metadata["uid"], "uid_changed_before_delete")
            halt("BLOCKED", "uid_changed:" + identity["name"])
        verdict = self.ownership(identity, metadata)
        if verdict != "OWNED":
            halt("BLOCKED", verdict.lower() + ":" + identity["name"])
        return metadata

    def namespace_gate(self, name):
        """G9 and D18 for this namespace from fresh G9 evidence, and the absent TargetGroupBinding for ingress."""
        report = self.g9_cleanup()
        conditions = report.get("namespace_secret_condition") or {}
        if name != self.project + "-app" and conditions.get(name) != "MET":
            halt("BLOCKED", "g9_namespace_secret_condition:" + name)
        if name == self.project + "-ingress":
            self.tgb_gone()

    def destroy_namespace(self, key):
        identity = identity_of(key)
        name = identity["name"]
        obj = self.state["objects"].get(key)
        if obj is not None and obj.get("destroyed") in receipt.DESTROYED:
            self.namespaces[name] = "DELETED" if obj["destroyed"] == "deleted" else "ABSENT_CONFIRMED"
            return self.confirm_destroyed(key, identity, obj)
        owned = obj["owned_uid"] if obj is not None else None
        if owned is None:
            if self.read(identity) is not None:
                halt("BLOCKED", "not_owned:" + name)
            self.namespaces[name] = "NEVER_CREATED"
            return self.record(key, "never_created")
        metadata = self.namespace_owned(identity, owned)
        if metadata is None:
            self.namespaces[name] = "ABSENT_CONFIRMED"
            return self.delete_owned(NAMESPACE_PHASE, key, identity, owned, None)
        self.namespace_gate(name)
        first = self.namespace_contents(name, wait=True)
        seq = self.store.destroy_intent(identity, owned)
        try:
            # Final gate (B4B-F06), after the INTENT and right before the DELETE: ownership is never assumed from
            # before the inventory wait; the last fresh inventory must equal the first in every safety field.
            if self.namespace_owned(identity, owned) is None:
                halt("BLOCKED", "namespace_absent_before_delete:" + name)
            self.namespace_gate(name)
            self.check_fingerprint()
            second = self.namespace_contents(name, wait=False)
            if second != first:
                halt("BLOCKED", "namespace_changed_after_inventory:" + name)
            if self.deadline.expired():
                halt("UNKNOWN", "deadline_exceeded")
        except DestroyStop:
            self.load()
            if self.state["open_intent"] is not None:
                self.store.destroy_result(seq, identity, "failed", metadata["uid"])
            raise
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

    # -- the run ------------------------------------------------------------------------------------------------
    def run_step(self, step):
        self.gate(step)
        self.resolve_open_intent(step)
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
            name = key.split("|")[3]
            namespace_key = step == NAMESPACE_PHASE
            if obj is not None and obj.get("destroyed") in receipt.DESTROYED:
                self.confirm_destroyed(key, identity_of(key), obj)
                if namespace_key:
                    self.namespaces[name] = "DELETED" if obj["destroyed"] == "deleted" else "ABSENT_CONFIRMED"
            elif obj is not None and obj["owned_uid"] is not None:
                halt("BLOCKED", "journal_step_incomplete:" + key)
            elif self.read(identity_of(key)) is not None:
                halt("BLOCKED", "not_owned:" + name)
            else:
                self.record(key, "never_created")
                if namespace_key:
                    self.namespaces[name] = "NEVER_CREATED"

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
        # Existing receipt only (B4B-F02): never a directory, journal or HEADER created by destroy.
        self.store = receipt.Store(self.receipt_root, self.fp, self.project, self.report["manifest_sha256"],
                                   self.report["input_sha256"], self.plan, existing_only=True)
        with self.store.lock():
            self.store.begin()  # verifies the journal; refreshes only a verified stale snapshot
            # Locked revalidation before the first journal write: fingerprint, project and pins (load), phase, open
            # INTENT, quarantine and ownership from the locked journal, the cluster and the G9 receipt again.
            state = self.load()
            self.check_state(state)
            self.check_fingerprint()
            self.g9_eligible()
            if state["phase"] == "apply":
                self.store.begin_destroy()
                state = self.load()
            self.open_transport(state)
            for step in self.plan.destroy_order:
                self.check_fingerprint()
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
    verdicts = [v for group in crds.values() for v in group.values()]
    return {"objects": dict(sorted(engine.results.items())), "counts": counts, "crds": crds,
            "crd_zero_instances": verdicts.count("ZERO_INSTANCES"),
            "crd_not_created": verdicts.count("CRD_NOT_CREATED"),
            # retained CRDs are the created ones kept with zero instances; CRD_NOT_CREATED is never counted here
            "retained_crds": verdicts.count("ZERO_INSTANCES"),
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
