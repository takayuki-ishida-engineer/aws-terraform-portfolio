#!/usr/bin/env python3
"""Fake-only apply engine for the first four runtime stages (Step 1 items 6c-B3b-Apply-A and Apply-B1).

Source and offline only. It covers the ``namespaces`` (2 objects), ``base`` (16
objects), ``controller`` (13 objects), ``istiod`` (12 objects) and ``gateway`` (5 objects)
stages against a ``FakeAdapter`` and nothing else. Stage 6 (``mesh_security``) onward is refused.

Apply-B2 (gateway, Owner instruction 2026-11-23, Source/Offline only), design section 4.1:
- Pre-apply, in order: istiod in-stage readiness in this run, the injector caBundle populated, both
  gateway Secrets (metadata only, D2), the locked istio-proxy index and amd64 child (fake ECR, D4),
  and the base validator serving resolved. That last item needs Live probe F (D20) and a confirmed
  istiod manager name (D13), which no fake can supply, so the gateway stage always stops before any
  write with ``deferred_readiness_unresolved:base_validator_serving`` (exit 3). This is the design's
  "stop before gateway" and is never bypassed.
- The stage's own contract is implemented behind that gate and tested directly: minimal completion,
  in-stage readiness (Deployment, Pods, revision injection with ``sidecar.istio.io/status`` and the
  locked ``istio-proxy`` image, ``MATCH_PLATFORM`` digest) and the deferred gateway TLS serving item,
  which stays BLOCKED while ingress is BLOCKED.
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
- D13: the design record section 10 allowlist (``d13_ownership``), with field-level evidence: the
  runtime's Apply entry must own exactly the manifest's leaf paths (nested, never collapsed).
  - Only the structural status rule is treated as verified.
  - The istiod and controller manager names are unverified, so their entries
    leave ownership NOT_VERIFIED, and only within their section 10 rows
    (``within_section10``). Outside those rows they are ``FOREIGN_FIELD``:
    - istiod (``pilot-discovery``): Update, no subresource, on exactly the three Istio
      webhook objects (kind and name, cluster-scoped), owning only the ``caBundle`` of a
      fixed webhook present on the object, or its ``failurePolicy`` while the live value
      is ``Fail``;
    - the controller: Update, no subresource, on TargetGroupBinding ``<project>-gateway``
      in ``<project>-ingress``, owning exactly the finalizer ``elbv2.k8s.aws/resources``.
      Any other finalizer on a TargetGroupBinding is ``FOREIGN_FIELD``.
  - Malformed evidence is ``OWNERSHIP_NOT_VERIFIED``: managedFields that is not a list of
    well-formed entries, a fieldsV1 tree that is not mappings with prefixed keys, a
    duplicate manager/operation/subresource entry, a malformed webhook list or
    finalizer list.
  - Any unknown manager or field is ``FOREIGN_FIELD``.
  - Conflicts are never forced.

Apply-B1 (controller and istiod, Owner instruction 2026-11-23, Source/Offline only):
- Pre-apply (design section 4.1), each stopping before the stage changes anything:
  - base minimal completion (not its deferred item);
  - controller only: the bundle's controller webhook caBundle equals the pinned input's public CA;
  - required Secrets: metadata-only presence with the ``k8s_certs.py`` labels and manager (D2). A
    response that is not ``PartialObjectMetadata`` or carries ``data``/``stringData`` stops
    (``secret_metadata_only_unsupported``) and is never printed; there is no full Secret read;
  - ECR (D4, Live not approved): only an in-memory ``FakeRegistry`` is accepted. No registry means
    NOT_VERIFIED, and the index plus its ``linux/amd64`` child must match the image lock;
  - a Ready ``amd64`` node in the Deployment's zone (D3 Node read).
- In-stage readiness within the D11 Deployment bound (600 s, 5 s cadence): Deployment Available
  with the current observed generation and all replicas ready, Pods ready, Service endpoints
  ready on the reviewed ports (controller 9443; istiod 15017 and 15012), the IRSA annotation, and
  for istiod the caBundle populated on all three Istio webhooks. No new timeout is introduced.
- Digests (section 9): only ``MATCH_PLATFORM`` (the lock's amd64 digest on an amd64 node) passes.
  ``MATCH_INDEX``, a missing or unparseable ``imageID`` or a non-amd64 node is NOT_VERIFIED;
  any other digest is ``digest_mismatch``.
- Probes F and G are classified against the fake only (D9). A wrong class stops; a fake pass is
  recorded as ``CLASSIFIED_FAKE_ONLY`` and never resolves a Live requirement (D20).
- Deferred items resolve only when every requirement is MET. Live-only (D20, D21) and BLOCKED
  (D1, ingress) requirements have a fixed status, so no deferred item of these stages can pass.

Flow:
1. Gate.
2. Pins and the receipt HEADER pins.
3. D17 fingerprint.
4. Receipt reconcile. A quarantined, unproven, foreign, changed or unknown object
   stops the run before any write.
5. Per stage:
   - pre-apply conditions, including C1 for ``base``;
   - fake server-side dry-run for every object;
   - per object: INTENT, then the conditional fake server-side apply without
     force, then the readback with the UID and D13 ownership checks, then RESULT
     (a success RESULT only when the readback proves OWNED, otherwise QUARANTINE);
   - minimal completion;
   - STAGE_DONE;
   - in-stage readiness for ``controller`` and ``istiod``, which must hold before the next stage.
6. Deferred items of every stage in range, evaluated on evidence only.

Every write is conditional: create only if absent, and update only on the recorded UID and only while
the object's field ownership still proves OWNED under D13 (the runtime's Apply entry owns exactly the
manifest's required paths, every other manager is the status rule). A missing, emptied, partial, extra or
malformed runtime entry fails closed like a foreign manager. An object that appears where none was
recorded stops the run before its INTENT. The fake enforces these conditions atomically and refuses
before changing anything (``WRITE_REFUSALS``); the Live mechanism is NOT_VERIFIED.

A success RESULT is written only after the readback proves the UID and the field ownership. A landed write
that cannot be proven is quarantined (reason ``ownership_unproven`` or ``uid_changed``), never recorded as
owned and never turned back into "not applied".

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

APPROVED_STAGES = ("namespaces", "base", "controller", "istiod", "gateway")
API_READ_TIMEOUT_SECONDS = 20
CRD_ESTABLISHED_TIMEOUT_SECONDS = 120
DEPLOYMENT_READY_TIMEOUT_SECONDS = 600
READINESS_POLL_SECONDS = 5
EXIT_STATUS = {0: "STAGES_ACCEPTED", 1: "REFUSED", 2: "STOPPED", 3: "UNDETERMINED", 4: "APPLY_FAILED",
               5: "READINESS_TIMEOUT", 6: "APPLIED_WITH_DEFERRED"}
STATUS_KINDS = {"CustomResourceDefinition", "Deployment", "ValidatingAdmissionPolicy", "TargetGroupBinding"}
# Section 10 managers whose names are not confirmed on a real cluster: never treated as verified.
UNVERIFIED_MANAGERS = ("pilot-discovery", "aws-load-balancer-controller")
ISTIOD_MANAGER = "pilot-discovery"
LBC_MANAGER = "aws-load-balancer-controller"
LBC_FINALIZER = "elbv2.k8s.aws/resources"
RUNTIME_SUFFIX = "-k8s-runtime"
FIELD_PREFIXES = ("f:", "k:", "v:", "i:")
WEBHOOK_KINDS = ("ValidatingWebhookConfiguration", "MutatingWebhookConfiguration")
PRESENT_KINDS = {"ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding", "Service", "ConfigMap", "Deployment"}
WORKLOAD_STAGES = ("controller", "istiod", "gateway")
SIDECAR_STATUS = "sidecar.istio.io/status"
# Ready endpoint ports the plan names for each workload stage's Service.
ENDPOINT_PORTS = {"controller": {9443}, "istiod": {15017, 15012}}
LOCK_PATH = HERE.parent.parent / "kubernetes" / "images.lock.json"
REQUIRED_PLATFORM = "linux/amd64"
NODE_ARCHITECTURE = "amd64"
ZONE_LABEL = "topology.kubernetes.io/zone"
IRSA_ANNOTATION = "eks.amazonaws.com/role-arn"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
DEFERRED = {
    "base": [{"item": "istiod-default-validator serving (caBundle by istiod, endpoints, probe F)",
              "resolved_by": "istiod",
              "requires": ["base_validator_cabundle_populated", "istio_cabundle_manager_verified",
                           "istiod_endpoints_ready", "live_probe_F"]}],
    "controller": [{"item": "LBC webhook serving (probe B)", "resolved_by": "admission", "requires": ["live_probe_B"]},
                   {"item": "IRSA and AWS calls", "resolved_by": "ingress", "requires": ["ingress_blocked"]}],
    "istiod": [{"item": "CA in use (istio-ca-root-cert equals the local public root, D21)", "resolved_by": "istiod",
                "requires": ["live_ca_root_match"]},
               {"item": "sidecar injection (probe G)", "resolved_by": "gateway", "requires": ["live_probe_G"]}],
    "gateway": [{"item": "gateway TLS serving", "resolved_by": "ingress", "requires": ["ingress_blocked"]}],
}
# Requirements no fake evidence can meet: Live-only (D20, D21) or BLOCKED (D1, ingress). They always win.
FIXED_REQUIREMENTS = {"live_probe_F": "NOT_VERIFIED", "live_probe_B": "NOT_VERIFIED", "live_probe_G": "NOT_VERIFIED",
                      "live_ca_root_match": "NOT_VERIFIED", "ingress_blocked": "BLOCKED"}
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


class PreconditionFailed(Exception):
    """The fake's atomic write precondition (absent, or the expected UID) did not hold; nothing was changed."""


class OwnershipRefused(Exception):
    """The fake refused an update because the object's ownership did not prove OWNED; nothing was changed.

    Its argument is the D13 verdict (FOREIGN_FIELD, NOT_OWNED or OWNERSHIP_NOT_VERIFIED).
    """


# Stop reason of a write the fake refused before changing anything, by D13 verdict.
WRITE_REFUSALS = {"FOREIGN_FIELD": "foreign_field_refused", "NOT_OWNED": "not_owned_refused",
                  "OWNERSHIP_NOT_VERIFIED": "ownership_not_verified_refused"}


def field_paths(value, prefix=()):
    """FieldsV1-style leaf paths of a manifest fragment in this fake's model.

    Maps recurse as ``f:<key>``; lists of named items as ``k:{"name": ...}``; other lists and scalars are
    leaves. How a real API server records each list type is NOT_VERIFIED.
    """
    if isinstance(value, dict) and value:
        paths = set()
        for key, item in value.items():
            paths |= field_paths(item, prefix + ("f:" + key,))
        return paths
    if isinstance(value, list) and value and all(isinstance(i, dict) and "name" in i for i in value):
        paths = set()
        for item in value:
            entry = prefix + ('k:{"name":' + json.dumps(item["name"]) + "}",)
            rest = {k: v for k, v in item.items() if k != "name"}
            paths |= field_paths(rest, entry) if rest else {entry}
        return paths
    return {prefix}


def required_paths(manifest):
    """The fields the runtime's Apply entry must own for this object: every leaf it sets except identity."""
    fragment = {k: copy.deepcopy(v) for k, v in manifest.items() if k not in ("apiVersion", "kind")}
    metadata = {k: v for k, v in fragment.pop("metadata", {}).items() if k not in ("name", "namespace")}
    if metadata:
        fragment["metadata"] = metadata
    return frozenset(field_paths(fragment)) if fragment else frozenset()


def fieldsv1_of(paths):
    tree = {}
    for path in paths:
        node = tree
        for part in path:
            node = node.setdefault(part, {})
    return tree


def paths_of(fieldsv1, prefix=()):
    """Leaf paths of a managedFields fieldsV1 tree, without collapsing nested paths."""
    if not isinstance(fieldsv1, dict) or not fieldsv1:
        return {prefix} if prefix else set()
    paths = set()
    for key, item in fieldsv1.items():
        if key != ".":
            paths |= paths_of(item, prefix + (key,))
    return paths


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


class FakeRegistry:
    """In-memory stand-in for the D4 ECR read (Live use is not approved): manifests by (repository, digest)."""

    is_fake = True

    def __init__(self):
        self.manifests = {}   # (repository, index digest) -> {"kind": "index", "platforms": {platform: digest}}
        self.timeouts = set()
        self.calls = []

    def describe(self, repository, digest):
        self.calls.append((repository, digest))
        if (repository, digest) in self.timeouts:
            raise AdapterTimeout(repository)
        return copy.deepcopy(self.manifests.get((repository, digest)))


def fake_node(name, zone, architecture, ready=True):
    return {"metadata": {"name": name, "labels": {ZONE_LABEL: zone}},
            "status": {"nodeInfo": {"architecture": architecture},
                       "conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


class FakeAdapter:
    """In-memory cluster for offline tests. Reads are limited to an explicit scope (D3)."""

    is_fake = True

    def __init__(self, clock, kube_system_uid, read_scope, secret_scope=()):
        self.clock = clock
        self.read_scope = set(read_scope) | {"v1|Namespace||kube-system"}
        self.secret_scope = {tuple(s) for s in secret_scope}  # (namespace, name) of the required Secrets only
        self.objects = {"v1|Namespace||kube-system": {"apiVersion": "v1", "kind": "Namespace",
                                                      "metadata": {"name": "kube-system", "uid": kube_system_uid},
                                                      "status": {"phase": "Active"}}}
        self.latency = {}          # key -> seconds a read takes
        self.conflicts = set()     # keys whose server-side apply conflicts
        self.crd_ready_after = {}  # key -> seconds after creation, or None for never
        self.dry_run = {}          # key -> (status, body)
        self.before_write = {}            # key -> callable(adapter) run just before the atomic write check
        self.apply_timeouts = set()       # keys whose apply times out before it lands
        self.post_apply_timeouts = set()  # keys whose apply lands but whose answer is lost
        self.calls = []
        self.serial = 0
        self.secrets = {}          # (namespace, name) -> metadata-only response
        self.nodes = [fake_node("node-a", "ca-central-1a", NODE_ARCHITECTURE)]
        # Deployment key -> {"ready_after": s or None, "image_ids": {container: imageID}, "node", "status",
        # "pods_ready", "spec_images"}. A Deployment becomes ready 30 s after creation unless set.
        self.workloads = {}
        self.endpoints = {}        # Service key -> EndpointSlice list that replaces the derived one
        self.istiod_patches_cabundle = True
        self.istio_ca_bundle = "ZmFrZS1pc3Rpb2QtY2E="
        self.project = None        # learnt from the runtime field manager of the first write
        self.probes = {}           # probe name -> (status, body)

    def _wait(self, key):
        latency = self.latency.get(key, 0)
        self.clock.sleep(min(latency, API_READ_TIMEOUT_SECONDS))
        if latency > API_READ_TIMEOUT_SECONDS:
            raise AdapterTimeout(key)

    def _ready(self, key, obj):
        after = self.workloads.get(key, {}).get("ready_after", 30)
        return after is not None and self.clock.now() >= obj["metadata"].get("_created", 0) + after

    def _deployment_status(self, key, obj):
        config = self.workloads.get(key, {})
        if "status" in config:
            return copy.deepcopy(config["status"])
        replicas = obj["spec"].get("replicas", 1)
        count = replicas if self._ready(key, obj) else 0
        return {"observedGeneration": obj["metadata"].get("generation", 1), "replicas": replicas,
                "updatedReplicas": replicas, "readyReplicas": count, "availableReplicas": count,
                "conditions": [{"type": "Available", "status": "True" if count else "False"}]}

    def _istiod_acts(self):
        """The fake istiod: once its Deployment is ready it writes the caBundle of every Istio webhook (D23)."""
        if not self.istiod_patches_cabundle or self.project is None:
            return
        if not any(o["kind"] == "Deployment" and o["metadata"]["name"].startswith("istiod") and self._ready(k, o)
                   for k, o in self.objects.items()):
            return
        allowed = istio_webhooks(self.project)
        for obj in self.objects.values():
            if (obj["kind"], obj["metadata"]["name"]) not in allowed:
                continue
            if all(w.get("clientConfig", {}).get("caBundle") for w in obj.get("webhooks", [])):
                continue
            for webhook in obj.get("webhooks", []):
                webhook.setdefault("clientConfig", {})["caBundle"] = self.istio_ca_bundle
            paths = {("f:webhooks", 'k:{"name":' + json.dumps(w["name"]) + "}", "f:clientConfig", "f:caBundle")
                     for w in obj.get("webhooks", [])}
            others = [m for m in obj["metadata"].get("managedFields") or [] if m.get("manager") != ISTIOD_MANAGER]
            obj["metadata"]["managedFields"] = others + [{"manager": ISTIOD_MANAGER, "operation": "Update",
                                                          "fieldsType": "FieldsV1", "fieldsV1": fieldsv1_of(paths)}]
            self.serial += 1
            obj["metadata"]["resourceVersion"] = str(self.serial)

    def list_nodes(self):
        self.calls.append(("list", "nodes"))
        self._wait("nodes")
        return copy.deepcopy(self.nodes)

    def list_pods(self, namespace, selector):
        """D3: Pods only of an approved Deployment, by its namespace and exact selector."""
        self._istiod_acts()
        owners = [(k, o) for k, o in self.objects.items() if k in self.read_scope and o["kind"] == "Deployment"
                  and o["metadata"].get("namespace") == namespace
                  and o["spec"]["selector"].get("matchLabels") == selector]
        if not owners:
            raise AdapterError("pods_out_of_scope")
        self.calls.append(("list", "pods|" + namespace))
        self._wait("pods|" + namespace)
        pods = []
        for key, obj in owners:
            config = self.workloads.get(key, {})
            ready = config.get("pods_ready", self._ready(key, obj))
            containers = obj["spec"]["template"]["spec"]["containers"]
            for index in range(obj["spec"].get("replicas", 1)):
                pods.append({
                    "metadata": {"name": obj["metadata"]["name"] + "-" + str(index), "namespace": namespace,
                                 "labels": dict(selector), "annotations": config.get(
                                     "annotations", self._injected(obj))},
                    "spec": {"nodeName": config.get("node", "node-a"),
                             "containers": [{"name": c["name"],
                                             "image": config.get("spec_images", {}).get(c["name"], c["image"])}
                                            for c in containers]},
                    "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
                               "containerStatuses": [{"name": c["name"], "ready": ready, "image": c["image"],
                                                      "imageID": config.get("image_ids", {}).get(c["name"])}
                                                     for c in containers]}})
        return pods

    def _injected(self, deployment):
        """The fake injector: a Pod asking for revision injection gets sidecar.istio.io/status once the
        injector webhook has its caBundle."""
        labels = deployment["spec"]["template"]["metadata"].get("labels") or {}
        if labels.get("sidecar.istio.io/inject") != "true":
            return {}
        ready = any(o["kind"] == "MutatingWebhookConfiguration" and o["metadata"]["name"].startswith("istio-sidecar-injector")
                    and o.get("webhooks") and all(w.get("clientConfig", {}).get("caBundle") for w in o["webhooks"])
                    for o in self.objects.values())
        return {SIDECAR_STATUS: json.dumps({"containers": ["istio-proxy"], "revision": labels.get("istio.io/rev")})} \
            if ready else {}

    def list_endpoint_slices(self, namespace, service):
        """D3: EndpointSlices only of an approved Service."""
        key = "v1|Service|" + namespace + "|" + service
        self._scope(key)
        self._istiod_acts()
        self.calls.append(("list", "endpointslices|" + namespace))
        self._wait("endpointslices|" + namespace)
        if key in self.endpoints:
            return copy.deepcopy(self.endpoints[key])
        svc = self.objects.get(key)
        if svc is None:
            return []
        selector = svc["spec"].get("selector") or {}
        backing = [(k, o) for k, o in self.objects.items() if o["kind"] == "Deployment"
                   and o["metadata"].get("namespace") == namespace
                   and selector.items() <= (o["spec"]["template"]["metadata"].get("labels") or {}).items()]
        if not backing:
            return []
        dkey, deployment = backing[0]
        named = {p.get("name"): p.get("containerPort") for c in deployment["spec"]["template"]["spec"]["containers"]
                 for p in c.get("ports") or []}
        ports = []
        for port in svc["spec"].get("ports") or []:
            target = port.get("targetPort", port["port"])
            ports.append({"name": port.get("name"), "port": named.get(target) if isinstance(target, str) else target})
        return [{"addressType": "IPv4", "ports": ports,
                 "endpoints": [{"addresses": ["10.0.0.10"], "conditions": {"ready": self._ready(dkey, deployment)}}]}]

    def get_secret_metadata(self, namespace, name):
        """D2: a metadata-only Secret read of a required Secret; never the full object."""
        if (namespace, name) not in self.secret_scope:
            raise AdapterError("secret_out_of_scope")
        self.calls.append(("secret_metadata", namespace + "/" + name))
        self._wait("secret|" + namespace + "/" + name)
        return copy.deepcopy(self.secrets.get((namespace, name)))

    def probe(self, name):
        """D9: a dry-run admission probe answered by the fake only (Live use needs D20)."""
        self.calls.append(("probe", name))
        return copy.deepcopy(self.probes.get(name))

    def _scope(self, key):
        if key not in self.read_scope:
            raise AdapterError("read_out_of_scope")

    def get(self, identity):
        key = key_of(identity)
        self._scope(key)
        self._istiod_acts()
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
        if obj["kind"] == "Deployment":
            obj["status"] = self._deployment_status(key, self.objects[key])
        obj["metadata"].pop("_created", None)
        return obj

    def server_side_apply(self, identity, manifest, field_manager, force=False, dry_run=False, precondition=None):
        key = key_of(identity)
        self._scope(key)
        if force:
            raise AdapterError("force_conflicts_refused")
        self.project = project_of(field_manager) or self.project
        self.calls.append(("dry_run" if dry_run else "apply", key))
        if dry_run:
            return self.dry_run.get(key, (200, ""))
        if not (precondition == {"absent": True} or (isinstance(precondition, dict) and set(precondition) == {"uid"}
                                                      and isinstance(precondition["uid"], str))):
            raise AdapterError("precondition_required")
        if key in self.apply_timeouts:
            raise AdapterTimeout(key)
        if key in self.before_write:
            self.before_write.pop(key)(self)
        current = self.objects.get(key)
        precondition = precondition or {}
        # Atomic in this fake: the precondition is checked and the write made with nothing in between.
        if precondition.get("absent") and current is not None:
            raise PreconditionFailed("object_exists")
        if "uid" in precondition and (current is None or current["metadata"].get("uid") != precondition["uid"]):
            raise PreconditionFailed("uid_mismatch")
        # Atomic in this fake as well: an update proceeds only while the object's ownership still proves OWNED
        # under D13, the same check the engine applies to its readback. The runtime's own Apply entry is verified
        # too (exactly the manifest's required paths), so a missing, emptied, partial, extra or malformed entry
        # is refused like a foreign manager. Nothing (object, resourceVersion, managedFields, serial) changes
        # before this check passes. This is a property of the fake, not a claim about the real API server
        # (NOT_VERIFIED).
        if current is not None:
            verdict = d13_ownership(observed_of(current, manifest), field_manager)
            if verdict != "OWNED":
                raise OwnershipRefused(verdict)
        if key in self.conflicts:
            raise ApplyConflict(key)
        entry = {"manager": field_manager, "operation": "Apply", "fieldsType": "FieldsV1",
                 "fieldsV1": fieldsv1_of(required_paths(manifest))}
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


def fields_tree_well_formed(tree):
    """A fieldsV1 tree: mappings all the way down, every key ``.`` or prefixed ``f:``, ``k:``, ``v:`` or ``i:``."""
    return isinstance(tree, dict) and all(
        isinstance(key, str) and (key == "." or key.startswith(FIELD_PREFIXES)) and fields_tree_well_formed(value)
        for key, value in tree.items())


def managed_entry_well_formed(entry):
    """A managedFields entry this fake can read: a mapping with string manager, operation and subresource,
    and a well-formed fieldsV1 tree. Anything else is malformed evidence."""
    return (isinstance(entry, dict) and isinstance(entry.get("manager"), str)
            and isinstance(entry.get("operation"), str) and isinstance(entry.get("subresource", ""), str)
            and fields_tree_well_formed(entry.get("fieldsV1", {})))


def live_webhooks(obj):
    """{webhook name: failurePolicy} of a webhook configuration, or None when the list is malformed."""
    items = obj.get("webhooks")
    items = [] if items is None else items
    if not isinstance(items, list) or not all(isinstance(w, dict) and isinstance(w.get("name"), str) for w in items):
        return None
    names = [w["name"] for w in items]
    return None if len(set(names)) != len(names) else {w["name"]: w.get("failurePolicy") for w in items}


def observed_of(obj, manifest=None):
    """Presence data for reconcile and D13: UID, kind, each manager's full nested paths, the required paths.

    Malformed managedFields evidence is flagged (``malformed``), never dropped silently; D13 fails it closed.
    """
    meta = obj["metadata"]
    entries = meta.get("managedFields")
    entries = [] if entries is None else entries
    malformed = not isinstance(entries, list) or not all(managed_entry_well_formed(m) for m in entries)
    managers = [] if malformed else [
        {"manager": m["manager"], "operation": m["operation"], "subresource": m.get("subresource", ""),
         "paths": frozenset(paths_of(m.get("fieldsV1") or {}))} for m in entries]
    # The API server keeps one entry per manager, operation and subresource; a duplicate is not evidence.
    triples = [(m["manager"], m["operation"], m["subresource"]) for m in managers]
    malformed = malformed or len(set(triples)) != len(triples)
    webhooks = live_webhooks(obj) if obj["kind"] in WEBHOOK_KINDS else {}
    finalizers = meta.get("finalizers")
    finalizers = [] if finalizers is None else finalizers
    if webhooks is None or not isinstance(finalizers, list) or not all(isinstance(f, str) for f in finalizers):
        malformed, webhooks, finalizers = True, {}, []
    return {"uid": meta.get("uid"), "kind": obj["kind"], "name": meta.get("name"), "namespace": meta.get("namespace", ""),
            "webhooks": webhooks, "finalizers": list(finalizers), "managers": managers, "malformed": malformed,
            "required": required_paths(manifest) if manifest is not None else None}


def status_only(entry, kind):
    """D13 structural rule: a status-subresource Update touching only f:status paths on a kind with status."""
    paths = entry.get("paths") or frozenset()
    return (entry.get("subresource") == "status" and entry.get("operation") == "Update" and kind in STATUS_KINDS
            and bool(paths) and all(path and path[0] == "f:status" for path in paths))


def project_of(runtime_manager):
    if isinstance(runtime_manager, str) and runtime_manager.endswith(RUNTIME_SUFFIX) \
            and len(runtime_manager) > len(RUNTIME_SUFFIX):
        return runtime_manager[:-len(RUNTIME_SUFFIX)]
    return None


def istio_webhooks(project):
    """C1/D23 and section 10: the three Istio webhook objects istiod may write, with their fixed webhook names."""
    return {("ValidatingWebhookConfiguration", "istiod-default-validator"): {"validation.istio.io"},
            ("ValidatingWebhookConfiguration", "istio-validator-" + project + "-v1-istio-system"):
                {"rev.validation.istio.io"},
            ("MutatingWebhookConfiguration", "istio-sidecar-injector-" + project + "-v1"):
                {"rev.namespace.sidecar-injector.istio.io", "rev.object.sidecar-injector.istio.io"}}


def webhook_key(name):
    return 'k:{"name":' + json.dumps(name) + "}"


def within_section10(entry, observed, project):
    """The section 10 row of an unverified manager; anything outside its row is foreign.

    - istiod: Update, no subresource, on one of the three Istio webhook objects (exact kind and name,
      cluster-scoped), owning only ``f:webhooks[name=<fixed>].f:clientConfig.f:caBundle`` of a fixed webhook
      present on the object, or its ``f:failurePolicy`` while the live value is ``Fail``.
    - the controller: Update, no subresource, on TargetGroupBinding ``<project>-gateway`` in
      ``<project>-ingress``, owning exactly the finalizer ``elbv2.k8s.aws/resources``.
    """
    paths = entry.get("paths") or frozenset()
    if not paths or entry.get("operation") != "Update" or entry.get("subresource") or project is None:
        return False
    if entry.get("manager") == ISTIOD_MANAGER:
        fixed = istio_webhooks(project).get((observed.get("kind"), observed.get("name")))
        if fixed is None or observed.get("namespace"):
            return False
        live = observed.get("webhooks") or {}
        keys = {webhook_key(name): name for name in fixed if name in live}
        for path in paths:
            if len(path) < 3 or path[0] != "f:webhooks" or path[1] not in keys:
                return False
            if path[2:] == ("f:clientConfig", "f:caBundle"):
                continue
            if path[2:] == ("f:failurePolicy",) and live[keys[path[1]]] == "Fail":
                continue
            return False
        return True
    if entry.get("manager") == LBC_MANAGER:
        return (observed.get("kind") == "TargetGroupBinding" and observed.get("name") == project + "-gateway"
                and observed.get("namespace") == project + "-ingress"
                and set(paths) == {("f:metadata", "f:finalizers", "v:" + json.dumps(LBC_FINALIZER))})
    return False


def d13_ownership(observed, runtime_manager):
    """Section 10 allowlist (D13) with field-level evidence; anything unproven fails closed.

    OWNED needs the runtime's Apply entry to own exactly the required paths of the manifest, and every
    other manager to be the structural status rule. Unverified manager names give OWNERSHIP_NOT_VERIFIED;
    any other manager or field gives FOREIGN_FIELD. A manager name alone never proves ownership, and
    malformed managedFields evidence gives OWNERSHIP_NOT_VERIFIED.
    """
    if observed.get("malformed"):
        return "OWNERSHIP_NOT_VERIFIED"
    project = project_of(runtime_manager)
    managers = observed.get("managers") or []
    runtime = [m for m in managers if m.get("manager") == runtime_manager and m.get("operation") == "Apply"
               and not m.get("subresource")]
    if not runtime:
        return "NOT_OWNED"
    verdict = "OWNED"
    for entry in managers:
        if entry in runtime or status_only(entry, observed.get("kind")):
            continue
        if entry.get("manager") in UNVERIFIED_MANAGERS and within_section10(entry, observed, project):
            verdict = "OWNERSHIP_NOT_VERIFIED"
            continue
        return "FOREIGN_FIELD"
    # Section 10: any finalizer other than the controller's on a TargetGroupBinding stops.
    if observed.get("kind") == "TargetGroupBinding" and set(observed.get("finalizers") or ()) - {LBC_FINALIZER}:
        return "FOREIGN_FIELD"
    required = observed.get("required")
    owned = set().union(*(set(m.get("paths") or ()) for m in runtime))
    if not required or owned != set(required):
        return "OWNERSHIP_NOT_VERIFIED"
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


def outstanding_deferred(stage, done, evidence):
    """Deferred items of a stage that lack verified evidence, each with the status of every requirement.

    A later stage's STAGE_DONE never resolves a deferred item on its own (``done`` is deliberately not
    used). An item resolves only when every requirement is ``MET``. Live-only and BLOCKED requirements
    (``FIXED_REQUIREMENTS``) keep their fixed status whatever the evidence says, so a fake can never
    resolve them.
    """
    items = []
    for item in DEFERRED.get(stage, []):
        status = {req: FIXED_REQUIREMENTS.get(req, evidence.get(req, "NOT_VERIFIED")) for req in item["requires"]}
        if all(value == "MET" for value in status.values()):
            continue
        items.append(dict(item, evidence=status, status="BLOCKED" if "BLOCKED" in status.values() else "NOT_VERIFIED"))
    return items


def classify_image_digest(image_id, index_digest, platform_digest, node_architecture):
    """Section 9: ``MATCH_PLATFORM`` only for the lock's amd64 digest on an amd64 node."""
    digest = image_id.rsplit("@", 1)[1] if isinstance(image_id, str) and "@" in image_id else None
    if digest is None or not DIGEST.fullmatch(digest):
        return "NOT_VERIFIED"
    if digest == platform_digest:
        return "MATCH_PLATFORM" if node_architecture == NODE_ARCHITECTURE else "NOT_VERIFIED"
    if digest == index_digest:
        return "MATCH_INDEX"
    return "digest_mismatch"


def metadata_only(response):
    """D2 / section 8: a PartialObjectMetadata answer without data; anything else is never used or printed."""
    return (isinstance(response, dict) and response.get("kind") == "PartialObjectMetadata"
            and response.get("apiVersion") == "meta.k8s.io/v1" and "data" not in response
            and "stringData" not in response and isinstance(response.get("metadata"), dict))


def node_ready(node):
    return {c.get("type"): c.get("status") for c in (node.get("status") or {}).get("conditions") or []}.get("Ready") == "True"


def deployment_available(obj, manifest):
    status, replicas = obj.get("status") or {}, manifest["spec"].get("replicas", 1)
    generation, observed = obj["metadata"].get("generation"), status.get("observedGeneration")
    return (conditions_true(obj, ("Available",)) and isinstance(generation, int) and isinstance(observed, int)
            and observed >= generation
            and status.get("readyReplicas") == status.get("availableReplicas") == status.get("updatedReplicas") == replicas)


def pod_ready(pod):
    statuses = (pod.get("status") or {}).get("containerStatuses") or []
    return conditions_true(pod, ("Ready",)) and bool(statuses) and all(c.get("ready") is True for c in statuses)


def cabundle_paths(entry):
    return [p for p in entry.get("paths") or () if p and p[-1] == "f:caBundle"]


class Engine:
    def __init__(self, report, objects, store, adapter, clock, cluster_arn, registry=None, webhook_ca_bundle=None):
        self.report, self.store, self.adapter, self.clock = report, store, adapter, clock
        self.cluster_arn = cluster_arn
        self.registry, self.webhook_ca_bundle = registry, webhook_ca_bundle
        arn = str(cluster_arn).split(":")
        self.registry_host = (arn[4] + ".dkr.ecr." + arn[3] + ".amazonaws.com/") if len(arn) > 5 else None
        self.lock = json.loads(LOCK_PATH.read_text())
        self.evidence = {}
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
        if self.registry is not None and (not isinstance(self.registry, FakeRegistry)
                                          or getattr(self.registry, "is_fake", False) is not True):
            stop(1, "real_registry_not_approved")
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
        order = self.plan.stage_order
        return tuple(order[:order.index(through) + 1]) if through in order else ()

    def reconcile(self, approved):
        scope = {k for stage in approved for k in self.plan.members[stage]}

        def observe(identity):
            if key_of(identity) not in scope:
                return "unknown", "not_in_scope"
            obj = self.read(identity)
            return ("absent", None) if obj is None else ("present", observed_of(obj, self.manifest(identity)))
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
        if stage == "gateway":
            self.gateway_pre_apply(done)
        elif stage == "base":
            if "namespaces" not in done:
                stop(2, "pre_apply_not_verified:namespaces_not_accepted")
            if c1_violations([self.manifest(i) for i in self.members(stage)]):
                stop(4, "istio_cabundle_ownership_unsafe")
        elif stage in WORKLOAD_STAGES:
            if "base" not in done:
                stop(2, "pre_apply_not_verified:base_not_accepted")
            if stage == "controller":
                self.check_bundle_ca(stage)
            self.check_secrets(stage)
            self.check_registry(stage)
            self.check_nodes(stage)

    def gateway_pre_apply(self, done):
        """Design 4.1 gateway row, plus the base row's "stop before gateway" when validator serving is unproven."""
        if "istiod" not in done or self.evidence.get("istiod_in_stage_readiness") != "MET":
            stop(3, "pre_apply_not_verified:istiod_not_ready")
        injector = [i for i in self.members("istiod") if i["kind"] == "MutatingWebhookConfiguration"]
        for identity in injector:
            obj = self.read(identity)
            if obj is None or not obj.get("webhooks") or not all(
                    w.get("clientConfig", {}).get("caBundle") for w in obj.get("webhooks") or []):
                stop(3, "pre_apply_not_verified:injector_cabundle")
        self.check_secrets("gateway")
        self.check_registry("gateway")
        if outstanding_deferred("base", done, self.evidence):
            stop(3, "deferred_readiness_unresolved:base_validator_serving")

    def stage_report(self, stage):
        return next(s for s in self.report["stages"] if s["name"] == stage)

    def deployments(self, stage):
        return [i for i in self.members(stage) if i["kind"] == "Deployment"]

    def check_bundle_ca(self, stage):
        """The controller webhooks carry the pinned input's public CA (plan); the runtime owns it (C1)."""
        if not self.webhook_ca_bundle:
            stop(3, "pre_apply_not_verified:webhook_ca_bundle")
        for identity in self.members(stage):
            if identity["kind"] in WEBHOOK_KINDS:
                for webhook in self.manifest(identity).get("webhooks", []):
                    if webhook.get("clientConfig", {}).get("caBundle") != self.webhook_ca_bundle:
                        stop(3, "pre_apply_not_verified:bundle_ca_differs")

    def check_secrets(self, stage):
        """D2: metadata-only presence, labels and manager of each required Secret; never its data."""
        project = self.report["project"]
        for secret in self.stage_report(stage).get("required_secrets") or []:
            where = secret["namespace"] + "/" + secret["name"]
            try:
                response = self.adapter.get_secret_metadata(secret["namespace"], secret["name"])
            except AdapterTimeout:
                stop(3, "api_timeout")
            if response is None:
                stop(3, "pre_apply_not_verified:secret_absent:" + where)
            if not metadata_only(response):
                stop(3, "secret_metadata_only_unsupported")  # discarded, never printed or used
            meta = response["metadata"]
            labels = meta.get("labels") if isinstance(meta.get("labels"), dict) else {}
            entries = meta.get("managedFields") if isinstance(meta.get("managedFields"), list) else []
            registered = any(isinstance(m, dict) and m.get("manager") == project + "-k8s-certs"
                             and m.get("operation") == "Apply" for m in entries)
            if (meta.get("namespace"), meta.get("name")) != (secret["namespace"], secret["name"]) \
                    or labels.get("app.kubernetes.io/managed-by") != "k8s_certs.py" \
                    or labels.get("app.kubernetes.io/part-of") != project or not registered:
                stop(3, "pre_apply_not_verified:secret_not_registered:" + where)

    def lock_entry(self, image):
        """The image lock entry of a bundle image: ``<host>/<project>-dev-ecr-<purpose>@<index digest>``."""
        host = self.registry_host or ""
        repository, _, digest = (image[len(host):] if host and image.startswith(host) else "").partition("@")
        for entry in self.lock.get("images") or []:
            platform = ((entry.get("platforms") or {}).get(REQUIRED_PLATFORM) or {}).get("digest")
            if repository == self.report["project"] + "-dev-ecr-" + entry["purpose"] and digest == entry["digest"] \
                    and platform:
                return {"purpose": entry["purpose"], "repository": repository, "index": digest, "platform": platform}
        stop(3, "digest_not_verified:bundle_image_not_locked")

    def images(self, stage):
        return [(identity, c, self.lock_entry(c["image"])) for identity in self.deployments(stage)
                for c in self.manifest(identity)["spec"]["template"]["spec"]["containers"]]

    def check_registry(self, stage):
        """D4 (fake only): the locked index and its amd64 child exist in the private ECR repository."""
        if self.registry is None:
            stop(3, "pre_apply_not_verified:ecr_evidence_unavailable")
        for _, _, entry in self.images(stage):
            try:
                found = self.registry.describe(entry["repository"], entry["index"])
            except AdapterTimeout:
                stop(3, "api_timeout")
            if not isinstance(found, dict) or found.get("kind") != "index":
                stop(3, "pre_apply_not_verified:ecr_index_missing:" + entry["purpose"])
            if (found.get("platforms") or {}).get(REQUIRED_PLATFORM) != entry["platform"]:
                stop(3, "digest_not_verified:ecr_platform_child:" + entry["purpose"])

    def list_nodes(self):
        try:
            return self.adapter.list_nodes()
        except AdapterTimeout:
            stop(3, "api_timeout")

    def check_nodes(self, stage):
        """D3: a Ready amd64 node in each Deployment's selected zone."""
        nodes = self.list_nodes()
        for identity in self.deployments(stage):
            zone = (self.manifest(identity)["spec"]["template"]["spec"].get("nodeSelector") or {}).get(ZONE_LABEL)
            if not zone or not any(node_ready(n) and (n["metadata"].get("labels") or {}).get(ZONE_LABEL) == zone
                                   and ((n.get("status") or {}).get("nodeInfo") or {}).get("architecture")
                                   == NODE_ARCHITECTURE for n in nodes):
                stop(3, "pre_apply_not_verified:nodes")

    def dry_run(self, stage):
        order = self.plan.stage_order
        webhooks = [self.manifest(i) for s in order[:order.index(stage) + 1] for i in self.members(s)
                    if i["kind"] in WEBHOOK_KINDS]
        if not dry_run_permitted(webhooks):
            stop(3, "dry_run_unsupported")  # the API server would refuse the dry-run; never a pass
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
        if recorded is None and live is not None:
            stop(4, "foreign_object_appeared")  # create only what is absent; never touch a foreign object
        if recorded is not None and (live is None or live["metadata"].get("uid") != recorded):
            stop(4, "uid_changed")
        prior = {"state": "owned", "uid": recorded} if recorded is not None else {"state": "absent"}
        seq = self.store.intent(stage, identity, prior, "update" if recorded else "create")
        # The write itself is conditional (absent, or the recorded UID). The fake checks it atomically; how a
        # real API server would enforce the same condition is NOT_VERIFIED (D19 production transport).
        precondition = {"uid": recorded} if recorded is not None else {"absent": True}
        try:
            self.adapter.server_side_apply(identity, self.manifest(identity), self.manager, force=False,
                                           precondition=precondition)
        except PreconditionFailed:
            self.store.result(seq, identity, None, None, None, "failed")  # refused before the write: not applied
            stop(4, "precondition_failed")
        except OwnershipRefused as refused:
            self.store.result(seq, identity, None, None, None, "failed")  # refused before the write: not applied
            stop(4, WRITE_REFUSALS.get(str(refused), "ownership_not_verified_refused"))
        except ApplyConflict:
            self.store.result(seq, identity, None, None, None, "failed")
            stop(4, "field_conflict")
        except AdapterTimeout:
            stop(3, "api_timeout")  # outcome unknown: the INTENT stays open for reconciliation
        # The write landed. From here a refusal must not look like "not applied": an unproven outcome is
        # quarantined (closing the INTENT), so it is neither re-applied nor adopted without the Owner (D16).
        # A success RESULT, and with it a newly owned UID, is written only after ownership is proven.
        after = self.read(identity)  # a timeout stops with the INTENT open; the rerun reconciles it
        if after is None:
            self.store.quarantine(identity, None, "uid_changed" if recorded is not None else "creation_unproven")
            stop(4, "apply_not_observed")
        meta = after["metadata"]
        if recorded is not None and meta.get("uid") != recorded:
            self.store.quarantine(identity, meta.get("uid"), "uid_changed")
            stop(4, "uid_changed")
        owned = d13_ownership(observed_of(after, self.manifest(identity)), self.manager)
        if owned != "OWNED":
            self.store.quarantine(identity, meta.get("uid"), "ownership_unproven")
            stop(4, {"NOT_OWNED": "foreign_owner", "OWNERSHIP_NOT_VERIFIED": "ownership_not_verified"}
                 .get(owned, "foreign_field"))
        self.store.result(seq, identity, meta["uid"], str(meta.get("resourceVersion", "0")),
                          int(meta.get("generation", 0)), "applied")

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
        elif identity["kind"] in WEBHOOK_KINDS:
            obj = self.read(identity)
            # C1/D23: the runtime never claims an Istio caBundle. istiod may fill it later (its own entry).
            if obj is None or c1_violations([manifest]) or self.runtime_claims_istio_cabundle(obj, manifest):
                stop(4, "istio_cabundle_ownership_unsafe")
            if identity["name"].startswith("aws-load-balancer-controller") and \
                    [w.get("clientConfig", {}).get("caBundle") for w in obj.get("webhooks") or []] != \
                    [w.get("clientConfig", {}).get("caBundle") for w in manifest.get("webhooks") or []]:
                stop(4, "controller_webhook_cabundle_differs")
        elif identity["kind"] == "ServiceAccount":
            obj = self.read(identity)
            if obj is None:
                stop(3, "object_not_present")
            wanted = (manifest["metadata"].get("annotations") or {}).get(IRSA_ANNOTATION)
            if wanted is not None and (obj["metadata"].get("annotations") or {}).get(IRSA_ANNOTATION) != wanted:
                stop(3, "irsa_annotation_differs")
        elif identity["kind"] in PRESENT_KINDS:
            if self.read(identity) is None:
                stop(3, "object_not_present")
        else:
            stop(2, "kind_not_in_approved_stages")

    def runtime_claims_istio_cabundle(self, obj, manifest):
        if (obj["kind"], identity_of(obj)["name"]) not in istio_webhooks(self.report["project"]):
            return False
        observed = observed_of(obj, manifest)
        return observed["malformed"] or any(cabundle_paths(m) for m in observed["managers"]
                                            if m["manager"] == self.manager and m["operation"] == "Apply")

    def in_stage_readiness(self, stage):
        """Controller and istiod in-stage readiness within the D11 Deployment bound; anything else is N/A."""
        if stage not in WORKLOAD_STAGES:
            return "NOT_APPLICABLE"
        started = self.clock.now()
        while True:
            unmet = self.workload_unmet(stage)
            if unmet is None:
                break
            if self.clock.now() - started >= DEPLOYMENT_READY_TIMEOUT_SECONDS:
                stop(5, unmet)
            self.clock.sleep(READINESS_POLL_SECONDS)
        if stage == "gateway":
            self.check_injection(stage)
        self.check_digests(stage)
        if stage == "controller":
            self.check_controller_webhooks(stage)
        elif stage == "istiod":
            self.check_istio_webhooks()
            self.istiod_evidence()
            self.run_probes()
        self.evidence[stage + "_in_stage_readiness"] = "MET"
        return "MET"

    def check_injection(self, stage):
        """Revision injection: every gateway Pod carries sidecar.istio.io/status and the locked istio-proxy."""
        wanted = self.proxy_image()
        for identity in self.deployments(stage):
            for pod in self.list_pods(identity):
                annotations = (pod.get("metadata") or {}).get("annotations") or {}
                containers = (pod.get("spec") or {}).get("containers") or []
                if not isinstance(annotations.get(SIDECAR_STATUS), str) or not annotations[SIDECAR_STATUS] or \
                        wanted is None or not any(c.get("name") == "istio-proxy" and c.get("image") == wanted
                                                  for c in containers):
                    stop(4, "injection_missing")
        self.evidence[stage + "_injection"] = "MET"

    def list_pods(self, identity):
        manifest = self.manifest(identity)
        try:
            return self.adapter.list_pods(identity["namespace"], manifest["spec"]["selector"].get("matchLabels"))
        except AdapterTimeout:
            stop(3, "api_timeout")

    def workload_unmet(self, stage):
        for identity in self.deployments(stage):
            manifest, obj = self.manifest(identity), self.read(identity)
            if obj is None or not deployment_available(obj, manifest):
                return "deployment_not_ready"
            pods = self.list_pods(identity)
            if len(pods) != manifest["spec"].get("replicas", 1) or not all(pod_ready(p) for p in pods):
                return "pods_not_ready"
        for identity in self.members(stage):
            if identity["kind"] == "Service" and stage in ENDPOINT_PORTS and not self.endpoints_ready(stage, identity):
                return "endpoints_not_ready"
        if stage == "istiod" and not all(
                w.get("clientConfig", {}).get("caBundle")
                for obj in self.istio_webhooks() for w in obj.get("webhooks") or []):
            return "cabundle_not_populated"
        return None

    def check_istio_webhooks(self):
        """After istiod writes the caBundle: every Istio webhook keeps failurePolicy Fail, and its ownership
        is at worst NOT_VERIFIED (istiod's unconfirmed name), never foreign or lost."""
        for stage in ("base", "istiod"):
            for identity in self.members(stage):
                if identity["kind"] not in WEBHOOK_KINDS:
                    continue
                obj = self.read(identity)
                if obj is None:
                    stop(3, "object_not_present")
                if any(w.get("failurePolicy") != "Fail" for w in obj.get("webhooks") or []) or not obj.get("webhooks"):
                    stop(4, "istio_failure_policy_not_fail")
                verdict = d13_ownership(observed_of(obj, self.manifest(identity)), self.manager)
                if verdict == "FOREIGN_FIELD":
                    stop(4, "foreign_field")
                if verdict == "NOT_OWNED":
                    stop(4, "foreign_owner")

    def endpoints_ready(self, stage, identity):
        try:
            slices = self.adapter.list_endpoint_slices(identity["namespace"], identity["name"])
        except AdapterTimeout:
            stop(3, "api_timeout")
        ready_ports = set()
        for piece in slices or []:
            if any((e.get("conditions") or {}).get("ready") is True for e in piece.get("endpoints") or []):
                ready_ports |= {p.get("port") for p in piece.get("ports") or []}
        return ENDPOINT_PORTS[stage] <= ready_ports

    def istio_webhooks(self):
        found = []
        for stage in ("base", "istiod"):
            for identity in self.members(stage):
                if identity["kind"] in WEBHOOK_KINDS:
                    obj = self.read(identity)
                    found.append(obj if obj is not None else {"webhooks": [{}]})
        return found

    def check_digests(self, stage):
        """Section 9: every container of every Pod must be MATCH_PLATFORM against the lock."""
        nodes = {n["metadata"].get("name"): n for n in self.list_nodes()}
        for identity in self.deployments(stage):
            expected = {c["name"]: (c["image"], entry) for i, c, entry in self.images(stage) if i == identity}
            for pod in self.list_pods(identity):
                if {c.get("name"): c.get("image") for c in pod["spec"].get("containers") or []} != \
                        {name: image for name, (image, _) in expected.items()}:
                    stop(4, "digest_mismatch:spec_image")
                node = nodes.get(pod["spec"].get("nodeName")) or {}
                architecture = ((node.get("status") or {}).get("nodeInfo") or {}).get("architecture")
                statuses = {c.get("name"): c for c in (pod.get("status") or {}).get("containerStatuses") or []}
                for name, (_, entry) in expected.items():
                    verdict = classify_image_digest((statuses.get(name) or {}).get("imageID"), entry["index"],
                                                    entry["platform"], architecture)
                    if verdict == "digest_mismatch":
                        stop(4, "digest_mismatch")
                    if verdict != "MATCH_PLATFORM":
                        stop(3, "digest_not_verified:" + verdict.lower())
        self.evidence[stage + "_digest"] = "MATCH_PLATFORM"

    def check_controller_webhooks(self, stage):
        """The controller webhook caBundle stays owned only by the runtime, with the bundle's value."""
        for identity in self.members(stage):
            if identity["kind"] in WEBHOOK_KINDS:
                obj, manifest = self.read(identity), self.manifest(identity)
                if obj is None or d13_ownership(observed_of(obj, manifest), self.manager) != "OWNED" or \
                        [w.get("clientConfig", {}).get("caBundle") for w in obj.get("webhooks") or []] != \
                        [w.get("clientConfig", {}).get("caBundle") for w in manifest.get("webhooks") or []]:
                    stop(4, "controller_webhook_cabundle_not_runtime_owned")

    def istiod_evidence(self):
        """Evidence for the base validator's deferred serving item; it can never be fully MET here."""
        validators = [i for i in self.members("base") if i["kind"] in WEBHOOK_KINDS]
        populated, owners, in_row = True, set(), True
        for identity in validators:
            obj = self.read(identity)
            populated = populated and obj is not None and all(
                w.get("clientConfig", {}).get("caBundle") for w in obj.get("webhooks") or [])
            observed = observed_of(obj, self.manifest(identity)) if obj is not None else {"managers": [],
                                                                                         "malformed": True}
            in_row = in_row and d13_ownership(observed, self.manager) == "OWNERSHIP_NOT_VERIFIED"
            owners |= {(m["manager"], m["operation"]) for m in observed["managers"] if cabundle_paths(m)}
        self.evidence["base_validator_cabundle_populated"] = "MET" if populated else "NOT_MET"
        self.evidence["istiod_endpoints_ready"] = "MET"
        # Only istiod, inside its section 10 row, may own the caBundle; its name is NOT_VERIFIED (D13), so the
        # best this can be is NOT_VERIFIED.
        self.evidence["istio_cabundle_manager_verified"] = (
            "NOT_VERIFIED" if in_row and owners == {(ISTIOD_MANAGER, "Update")} else "NOT_MET")

    def proxy_image(self):
        entry = next((e for e in self.lock.get("images") or [] if e["purpose"] == "istio-proxy"), None)
        if entry is None or not self.registry_host:
            return None
        return self.registry_host + self.report["project"] + "-dev-ecr-istio-proxy@" + entry["digest"]

    def run_probes(self):
        names = {w["name"] for i in self.members("base") if i["kind"] in WEBHOOK_KINDS
                 for w in self.manifest(i).get("webhooks") or []}
        self.fake_probe("F", {"webhook_denied:" + n for n in names})
        self.fake_probe("G", {"allowed"})

    def fake_probe(self, name, expected):
        """D9 against the fake only. A wrong class stops; a fake pass never meets a Live requirement (D20)."""
        answer = self.adapter.probe(name)
        if answer is None:
            self.evidence["fake_probe_" + name] = "NOT_RUN"
            return
        status, body = answer
        outcome = classify_admission(status, body)
        if outcome not in expected:
            stop(3 if outcome in ("webhook_unreachable", "unknown", "dry_run_unsupported") else 4,
                 "probe_" + name + ":" + outcome)
        if name == "G" and not self.injected(body):
            stop(4, "probe_G:injection_missing")
        self.evidence["fake_probe_" + name] = "CLASSIFIED_FAKE_ONLY"

    def injected(self, body):
        try:
            pod = json.loads(body) if isinstance(body, str) else None
        except ValueError:
            return False
        spec = (pod or {}).get("spec") if isinstance(pod, dict) else None
        containers = ((spec or {}).get("containers") or []) + ((spec or {}).get("initContainers") or [])
        wanted = self.proxy_image()
        return wanted is not None and any(isinstance(c, dict) and c.get("name") == "istio-proxy"
                                          and c.get("image") == wanted for c in containers)

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
                row = {"name": stage, "applied": applied, "minimal_completion": "MET", "in_stage_readiness": None,
                       "deferred": None, "final_acceptance": "NOT_REACHED"}
                self.stages.append(row)
                # In-stage readiness must hold before the next stage starts (stop before istiod or gateway).
                row["in_stage_readiness"] = self.in_stage_readiness(stage)
            for row in self.stages:
                deferred = outstanding_deferred(row["name"], done, self.evidence)
                row.update({"deferred": deferred, "final_acceptance": "DEFERRED" if deferred else "PASS"})
        return 6 if any(s["deferred"] for s in self.stages) else 0


def apply_stages(report, objects, store, adapter, clock, expected_manifest, expected_input, cluster_arn,
                 through="base", registry=None, webhook_ca_bundle=None):
    """Run the approved stages against the fake. Returns a report; never raises for a stop.

    ``registry`` is the fake ECR evidence (D4); ``webhook_ca_bundle`` is the pinned input's public CA.
    Without either, the controller and istiod stages stop at pre-apply as NOT_VERIFIED.
    """
    engine = Engine(report, objects, store, adapter, clock, cluster_arn, registry, webhook_ca_bundle)
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
            "evidence": dict(engine.evidence), "live": "NOT_TESTED", "approved_stages": list(APPROVED_STAGES)}
