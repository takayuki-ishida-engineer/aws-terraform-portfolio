#!/usr/bin/env python3
"""Transport boundary for metadata-only reads and UID-precondition deletes (Step 1 item 6c-B3a, decisions D19 and G9).

Contract only. This module defines what a future Kubernetes API transport may send
and what it must accept, and a fake transport for offline tests. It contains no
network code: no socket, TLS, HTTP client, token retrieval or kubeconfig parsing.
Opening a real transport is refused (``real_transport_not_implemented``) until the
Owner approves its implementation separately.

Two request kinds exist, each built only for an allowlisted object identity:
- ``GET`` of one object's metadata, with
  ``Accept: application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1``;
- ``DELETE`` of one object with ``DeleteOptions.preconditions.uid``.

Responses are validated before anything is returned. A metadata response must be a
``PartialObjectMetadata`` for the requested object and carry no ``data``,
``stringData``, ``binaryData``, ``spec`` or ``status``.

Secrets (Owner decision D19/G9, 2026-11-24, Fake-only): a policy may name only the
four ``k8s_certs.py`` Secret identities of one project (``SECRET_TEMPLATES``), and
only when it is built with that project. No other Secret, namespace, path or verb
exists. A Secret metadata response is refused when it carries the
``kubectl.kubernetes.io/last-applied-configuration`` annotation (which can hold the
data), and only the name, namespace, UID, labels, managedFields and resourceVersion
are returned: no annotation value leaves this module. Metadata LIST, discovery and
destroy inventory reads are not part of this contract (D3 and D19, before 6c-B4).

``UNIMPLEMENTED_REQUIREMENTS`` lists what the real transport must satisfy before it
may be approved.
"""
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True

METADATA_ACCEPT = "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1"
MAX_RESPONSE_BYTES = 1024 * 1024
UID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
NAME = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
# The kinds of the 62 reviewed objects: (apiVersion, kind) -> (plural, namespaced).
KINDS = {
    ("v1", "Namespace"): ("namespaces", False),
    ("v1", "ConfigMap"): ("configmaps", True),
    ("v1", "Service"): ("services", True),
    ("v1", "ServiceAccount"): ("serviceaccounts", True),
    ("apps/v1", "Deployment"): ("deployments", True),
    ("apiextensions.k8s.io/v1", "CustomResourceDefinition"): ("customresourcedefinitions", False),
    ("admissionregistration.k8s.io/v1", "MutatingWebhookConfiguration"): ("mutatingwebhookconfigurations", False),
    ("admissionregistration.k8s.io/v1", "ValidatingWebhookConfiguration"): ("validatingwebhookconfigurations", False),
    ("admissionregistration.k8s.io/v1", "ValidatingAdmissionPolicy"): ("validatingadmissionpolicies", False),
    ("admissionregistration.k8s.io/v1", "ValidatingAdmissionPolicyBinding"):
        ("validatingadmissionpolicybindings", False),
    ("rbac.authorization.k8s.io/v1", "ClusterRole"): ("clusterroles", False),
    ("rbac.authorization.k8s.io/v1", "ClusterRoleBinding"): ("clusterrolebindings", False),
    ("rbac.authorization.k8s.io/v1", "Role"): ("roles", True),
    ("rbac.authorization.k8s.io/v1", "RoleBinding"): ("rolebindings", True),
    ("networking.k8s.io/v1", "NetworkPolicy"): ("networkpolicies", True),
    ("networking.istio.io/v1", "Gateway"): ("gateways", True),
    ("security.istio.io/v1", "AuthorizationPolicy"): ("authorizationpolicies", True),
    ("security.istio.io/v1", "PeerAuthentication"): ("peerauthentications", True),
    ("elbv2.k8s.aws/v1beta1", "TargetGroupBinding"): ("targetgroupbindings", True),
}
FORBIDDEN_RESPONSE_KEYS = {"data", "stringData", "spec", "status", "binaryData"}
# The four Secrets k8s_certs.py registers (secret_layout), as (namespace, name) templates of the project.
SECRET_TEMPLATES = (("istio-system", "cacerts"), ("kube-system", "aws-load-balancer-controller-tls"),
                    ("{project}-ingress", "{project}-gateway-tls"),
                    ("{project}-ingress", "{project}-gateway-client-cacert"))
# The DEV roots' project rule (k8s_certs.PROJECT, kubernetes/tools/common.py PROJECT).
SECRET_PROJECT = re.compile(r"[a-z]([a-z0-9-]{0,8}[a-z0-9])?")
LAST_APPLIED = "kubectl.kubernetes.io/last-applied-configuration"
SECRET_METADATA_FIELDS = ("name", "namespace", "uid", "labels", "managedFields", "resourceVersion")
APPROVED_TRANSPORTS = frozenset({"fake"})
UNIMPLEMENTED_REQUIREMENTS = [
    "TLS: verify the server certificate against the cluster CA from the eks_tunnel.py kubeconfig, never disabled",
    "SNI and hostname: connect to https://127.0.0.1:<port> (the developer-access tunnel) with server name equal to "
    "the kubeconfig tls-server-name, which must equal the applied platform endpoint host",
    "kubeconfig: accepted only after k8s_certs.check_kubeconfig for context <project>-dev-eks",
    "token: obtained with aws eks get-token for that cluster, held in memory only; never in arguments, environment "
    "of child processes, files, logs, receipts or error messages",
    "requests: only the GET and DELETE shapes built here, for allowlisted identities; no other verb, path or "
    "query parameter",
    "request body: DELETE sends exactly the DeleteOptions built here (UID precondition); GET sends no body",
    "responses: validated by validate_metadata_response and validate_delete_response, size limited, never printed",
    "timeouts and retries: bounded; a timeout or connection error is UNKNOWN, never success",
    "Secrets: only metadata GET and UID-precondition DELETE of the four k8s_certs.py Secret identities (G9); "
    "full Secret reads, Secret lists and any other Secret are never allowed",
]


class TransportError(Exception):
    """A request or response outside the contract; the message is a fixed code."""


def need(condition, code):
    if not condition:
        raise TransportError(code)


def identity_key(identity):
    return (identity["apiVersion"], identity["kind"], identity.get("namespace", ""), identity["name"])


def secret_identities(project):
    """The four k8s_certs.py Secret identities of one project, in registration order."""
    need(isinstance(project, str) and SECRET_PROJECT.fullmatch(project) is not None
         and re.search("aws|amazon|cognito", project) is None, "secret_project_invalid")
    return [{"apiVersion": "v1", "kind": "Secret", "namespace": namespace.format(project=project),
             "name": name.format(project=project)} for namespace, name in SECRET_TEMPLATES]


class Policy:
    """The identities a transport may touch. Built from the reviewed plan; Secrets only the four of secret_project."""

    def __init__(self, read_identities, delete_identities=(), secret_project=None):
        self.read = frozenset(identity_key(i) for i in read_identities)
        self.delete = frozenset(identity_key(i) for i in delete_identities)
        self.secrets = frozenset() if secret_project is None else \
            frozenset(identity_key(i) for i in secret_identities(secret_project))
        need(self.delete <= self.read, "delete_identity_not_readable")
        need(all(k in self.secrets for k in self.read if k[1] == "Secret"), "secret_path_not_approved")
        # 6c-B4a: this generic policy is never a way around the destroy contract (DestroyPolicy): no CRD and no
        # kube-system namespace can be deleted through it.
        need(not any((k[0], k[1]) == ("apiextensions.k8s.io/v1", "CustomResourceDefinition")
                     or k == ("v1", "Namespace", "", "kube-system") for k in self.delete), "delete_identity_refused")


def object_path(identity, secrets=frozenset()):
    """The API path of one allowlisted object; refuses unknown kinds, other Secrets and malformed names."""
    api_version, kind, namespace, name = identity_key(identity)
    if kind == "Secret":
        need(identity_key(identity) in secrets, "secret_path_not_approved")
        plural, namespaced = "secrets", True
    else:
        need((api_version, kind) in KINDS, "kind_not_allowed")
        plural, namespaced = KINDS[(api_version, kind)]
    need(NAME.fullmatch(name) is not None, "name_invalid")
    need(namespaced == bool(namespace), "namespace_scope_mismatch")
    need(not namespace or NAME.fullmatch(namespace) is not None, "namespace_invalid")
    prefix = "/api/v1" if api_version == "v1" else "/apis/" + api_version
    return prefix + ("/namespaces/" + namespace if namespace else "") + "/" + plural + "/" + name


def metadata_get_request(policy, identity):
    need(identity_key(identity) in policy.read, "identity_not_allowed")
    return {"method": "GET", "path": object_path(identity, policy.secrets), "headers": {"Accept": METADATA_ACCEPT},
            "body": None}


def delete_request(policy, identity, uid):
    need(identity_key(identity) in policy.delete, "delete_not_allowed")
    need(isinstance(uid, str) and UID.fullmatch(uid) is not None, "uid_invalid")
    body = {"apiVersion": "v1", "kind": "DeleteOptions", "preconditions": {"uid": uid},
            "propagationPolicy": "Background"}
    return {"method": "DELETE", "path": object_path(identity, policy.secrets),
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
            "body": json.dumps(body, sort_keys=True, separators=(",", ":"))}


def validate_metadata_response(identity, status, body):
    """Metadata of the requested object, or None when it does not exist (404)."""
    if status == 404:
        return None
    need(status != 403, "forbidden")
    need(status == 200, "unexpected_status")
    need(isinstance(body, (bytes, bytearray)) and len(body) <= MAX_RESPONSE_BYTES, "response_too_large")
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise TransportError("response_not_json") from None
    need(isinstance(document, dict), "response_shape")
    need(not (FORBIDDEN_RESPONSE_KEYS & set(document)), "response_not_metadata_only")
    need(document.get("kind") == "PartialObjectMetadata" and document.get("apiVersion") == "meta.k8s.io/v1",
         "response_not_partial_object_metadata")
    need(set(document) <= {"kind", "apiVersion", "metadata"}, "response_shape")
    metadata = document.get("metadata")
    need(isinstance(metadata, dict), "response_shape")
    need(metadata.get("name") == identity["name"] and metadata.get("namespace", "") == identity.get("namespace", ""),
         "response_identity_mismatch")
    need(isinstance(metadata.get("uid"), str) and UID.fullmatch(metadata["uid"]) is not None, "response_uid_invalid")
    if identity["kind"] == "Secret":
        annotations = metadata.get("annotations", {})
        need(isinstance(annotations, dict), "response_shape")
        need(LAST_APPLIED not in annotations, "response_secret_annotation_refused")
        return {key: metadata[key] for key in SECRET_METADATA_FIELDS if key in metadata}
    return metadata


def validate_delete_response(status):
    """deleted, accepted or absent; a failed UID precondition is a conflict, never success."""
    need(status != 409, "uid_precondition_failed")
    need(status != 403, "forbidden")
    results = {200: "deleted", 202: "accepted", 404: "absent"}
    need(status in results, "unexpected_status")
    return results[status]


class Transport:
    """The interface a future transport implements."""

    def get_metadata(self, identity):
        raise NotImplementedError

    def delete_with_uid(self, identity, uid):
        raise NotImplementedError


class FakeTransport(Transport):
    """Offline test double: requests are built and responses validated exactly as the contract requires."""

    def __init__(self, policy, server):
        self.policy = policy
        self.server = server
        self.requests = []

    def get_metadata(self, identity):
        request = metadata_get_request(self.policy, identity)
        self.requests.append(request)
        status, body = self.server(request)
        return validate_metadata_response(identity, status, body)

    def delete_with_uid(self, identity, uid):
        request = delete_request(self.policy, identity, uid)
        self.requests.append(request)
        status, _ = self.server(request)
        return validate_delete_response(status)


class HttpsTransport(Transport):
    """Placeholder for the real transport; constructing it is refused until separately approved."""

    def __init__(self, *args, **kwargs):
        raise TransportError("real_transport_not_implemented")


def open_transport(kind, policy=None, server=None):
    """Only the offline fake exists; any real transport is refused."""
    need(kind in APPROVED_TRANSPORTS, "real_transport_not_implemented")
    need(isinstance(policy, Policy) and callable(server), "fake_transport_needs_policy_and_server")
    return FakeTransport(policy, server)


# ---- 6c-B4a: destroy transport foundation (Owner decisions D3, D5, D11, D12, D19; 2026-11-24, Fake-only) -------------
#
# Separate scopes, each built only from the reviewed plan and the receipt, never from what a read returns:
#   single-object metadata read  -> DestroyPolicy.read      (the plan's identities and the kube-system namespace)
#   discovery                    -> DestroyPolicy.discovery (GET /api, /apis and each advertised group version)
#   namespace LIST               -> DestroyPolicy.namespaces and the transport's complete discovery evidence
#   CRD instance LIST            -> DestroyPolicy.crds and the transport's own CRD verification evidence
#   specialised CRD read         -> DestroyPolicy.crds      (structured fields only, never the object)
#   specialised Service read     -> DestroyPolicy.services  (spec.type of the runtime's <project>-ingress Services)
#   runtime DELETE               -> DestroyPolicy.delete    (identity -> UID proven by the receipt; no CRD, Secret or
#                                                            kube-system namespace)
#   G9 Secret DELETE             -> Policy(secret_project=...) above, unchanged
# The plan identities come from the reviewed plan (k8s_runtime_receipt.plan_identities) and the UIDs from a verified
# journal (k8s_runtime_receipt.owned_uids). Every request is authorised again at the send boundary
# (FakeDestroyTransport.authorize): it must equal, field for field, the request a builder makes for this policy and
# this transport's evidence; anything else never reaches the server. Every request runs under one global Deadline.
# There is no destroy engine here: nothing orchestrates deletions (6c-B4b).

# D11 destroy values (approved 2026-11-24). Every bound is finite; the global deadline is never extended or reset.
API_READ_TIMEOUT_SECONDS = 20
DELETE_REQUEST_TIMEOUT_SECONDS = 20
DELETE_CONFIRM_TIMEOUT_SECONDS = 20
TGB_FINALIZER_TIMEOUT_SECONDS = 600
OWNED_CHILD_TIMEOUT_SECONDS = 600
NAMESPACE_TERMINATION_TIMEOUT_SECONDS = 600
DESTROY_POLL_SECONDS = 5
LIST_PAGE_SIZE = 500
LIST_PAGE_LIMIT = 100       # pages per logical LIST, restarts included
LIST_RESTART_LIMIT = 2      # HTTP 410 restarts per logical LIST
DESTROY_DEADLINE_SECONDS = 3600
LIST_ACCEPT = "application/json;as=PartialObjectMetadataList;g=meta.k8s.io;v=v1"
JSON_ACCEPT = "application/json"
MAX_OBJECT_RESPONSE_BYTES = 4 * 1024 * 1024  # a CRD with its schema; only structured fields leave this module
GROUP = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
VERSION = re.compile(r"v[0-9]+((alpha|beta)[0-9]+)?")
RESOURCE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
CONTINUE_TOKEN = re.compile(r"[A-Za-z0-9_+/=-]{1,4096}")
FINALIZER = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?(/[A-Za-z0-9_.-]{1,316})?")
RFC3339 = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z")
API_VERSION_FORM = re.compile(r"([a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?/)?v[0-9]+((alpha|beta)[0-9]+)?")
KIND_FORM = re.compile(r"[A-Z][A-Za-z0-9]{0,62}")
RESOURCE_VERSION_FORM = re.compile(r"[0-9]{1,20}")
OWNER_KEYS = {"apiVersion", "kind", "name", "uid", "controller", "blockOwnerDeletion"}
VERB = re.compile(r"[a-z]{1,32}")
# Core v1 resources a namespace inventory can never miss (review of PR #100, R02): each must be advertised,
# namespaced, listable and mapped to its kind, or discovery is not COMPLETE. Secrets above all (D18).
REQUIRED_CORE_RESOURCES = {"secrets": "Secret", "services": "Service", "configmaps": "ConfigMap", "pods": "Pod",
                           "serviceaccounts": "ServiceAccount"}
INVENTORY_NAMESPACES = ("istio-system", "{project}-ingress", "{project}-app")
# Namespaced resources without the list verb that design section 5.1 allows: virtual, never persisted.
VIRTUAL_RESOURCES = frozenset({("", "bindings"), ("authorization.k8s.io", "localsubjectaccessreviews")})
# The same objects served under two resources (design section 5.1: both are listed).
RESOURCE_ALIASES = (frozenset({("", "events"), ("events.k8s.io", "events")}),)
CRD_TYPE = ("apiextensions.k8s.io/v1", "CustomResourceDefinition")
CRD_PATH = "/apis/apiextensions.k8s.io/v1/customresourcedefinitions/"
KUBE_SYSTEM_KEY = ("v1", "Namespace", "", "kube-system")
SERVICE_TYPES = {"ClusterIP", "NodePort", "LoadBalancer", "ExternalName"}
CONDITION_STATES = {"True", "False", "Unknown"}
DELETE_BODY_KEYS = {"apiVersion", "kind", "preconditions", "propagationPolicy"}
OBJECT_PATH = re.compile(r"/(api/v1|apis/[a-z0-9.-]+/v[0-9a-z]+)(/namespaces/[a-z0-9.-]+)?/[a-z0-9-]+(/[a-z0-9.-]+)?")
DISCOVERY_PATH = re.compile(r"/api|/apis|/api/v1|/apis/[a-z0-9.-]+/v[0-9a-z]+")


class Deadline:
    """The destroy run's global deadline on a (fake) clock: set once, never extended, reset or replaced."""

    def __init__(self, clock, seconds=DESTROY_DEADLINE_SECONDS):
        need(isinstance(seconds, int) and not isinstance(seconds, bool) and 0 < seconds <= DESTROY_DEADLINE_SECONDS,
             "deadline_invalid")
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_end", clock.now() + seconds)

    def __setattr__(self, name, value):
        raise TransportError("deadline_immutable")

    @property
    def clock(self):
        return self._clock

    def expired(self):
        return self._clock.now() >= self._end

    def remaining(self):
        return max(0, self._end - self._clock.now())


def inventory_namespaces(project):
    secret_identities(project)  # the project rule
    return tuple(namespace.format(project=project) for namespace in INVENTORY_NAMESPACES)


def crd_spec_from_manifest(manifest):
    """The reviewed CRD fields from a rendered manifest: group, plural, scope, storage version, served versions."""
    try:
        spec = manifest["spec"]
        versions = spec["versions"]
        storage = [v["name"] for v in versions if v.get("storage") is True]
        result = {"group": spec["group"], "plural": spec["names"]["plural"], "scope": spec["scope"],
                  "storage_version": storage[0] if len(storage) == 1 else None,
                  "served_versions": sorted(v["name"] for v in versions if v.get("served") is True)}
        name = manifest["metadata"]["name"]
    except (KeyError, TypeError, IndexError):
        raise TransportError("crd_manifest_invalid") from None
    check_crd_spec(name, result)
    return name, result


def check_crd_spec(name, spec):
    need(isinstance(spec, dict) and set(spec) == {"group", "plural", "scope", "storage_version", "served_versions"},
         "crd_spec_invalid")
    need(isinstance(spec["group"], str) and GROUP.fullmatch(spec["group"]) is not None
         and isinstance(spec["plural"], str) and RESOURCE.fullmatch(spec["plural"]) is not None
         and spec["scope"] in ("Namespaced", "Cluster")
         and isinstance(spec["storage_version"], str) and VERSION.fullmatch(spec["storage_version"]) is not None
         and isinstance(spec["served_versions"], list)
         and all(isinstance(v, str) and VERSION.fullmatch(v) for v in spec["served_versions"]), "crd_spec_invalid")
    need(name == spec["plural"] + "." + spec["group"], "crd_spec_invalid")
    need(spec["storage_version"] in spec["served_versions"], "crd_spec_invalid")


def identity_of(key):
    return dict(zip(("apiVersion", "kind", "namespace", "name"), key))


class DestroyPolicy:
    """What a destroy transport may read, list and delete. Immutable; nothing a read returns can widen it.

    ``plan_identities`` are the reviewed plan's identities (k8s_runtime_receipt.plan_identities),
    ``owned_uids`` the runtime DELETE map of a verified journal (k8s_runtime_receipt.owned_uids) and
    ``crd_receipt_uids`` the separate CRD verification map (k8s_runtime_receipt.crd_receipt_uids): the UIDs the
    journal owns for retained CRDs. The CRD map never grants a DELETE; the DELETE map never holds a CRD.
    """

    def __init__(self, project, plan_identities, owned_uids=None, inventory=False, discovery=False, crd_specs=None,
                 services=(), crd_receipt_uids=None):
        namespaces = inventory_namespaces(project)
        plan = {}
        for identity in plan_identities:
            key = identity_key(identity)
            need(key[1] != "Secret", "secret_path_not_approved")
            need(key not in plan and (key[0], key[1]) in KINDS, "plan_identity_invalid")
            object_path(identity)  # name, namespace and scope rules
            plan[key] = identity
        owned = {}
        for key, uid in dict(owned_uids or {}).items():
            need(isinstance(key, tuple) and len(key) == 4, "delete_identity_invalid")
            need(key != KUBE_SYSTEM_KEY, "kube_system_delete_refused")
            need((key[0], key[1]) != CRD_TYPE, "crd_delete_refused")
            need(key[1] != "Secret", "secret_delete_refused")
            need(key in plan, "delete_not_in_plan")
            need(isinstance(uid, str) and UID.fullmatch(uid) is not None, "uid_invalid")
            owned[key] = uid
        crd_names = {key[3] for key in plan if (key[0], key[1]) == CRD_TYPE}
        crds = {}
        for name, spec in dict(crd_specs or {}).items():
            need(name in crd_names, "crd_not_reviewed")
            check_crd_spec(name, spec)
            crds[name] = {k: (list(v) if isinstance(v, list) else v) for k, v in spec.items()}
        crd_owned = {}
        for key, uid in dict(crd_receipt_uids or {}).items():
            need(isinstance(key, tuple) and len(key) == 4 and (key[0], key[1]) == CRD_TYPE and key in plan,
                 "crd_receipt_identity_invalid")
            need(isinstance(uid, str) and UID.fullmatch(uid) is not None, "uid_invalid")
            crd_owned[key[3]] = uid
        approved_services = set()
        for identity in services:
            key = identity_key(identity)
            need(key in plan and key[1] == "Service" and key[2] == namespaces[1], "service_read_not_approved")
            approved_services.add(key)
        object.__setattr__(self, "project", project)
        object.__setattr__(self, "plan", frozenset(plan))
        object.__setattr__(self, "read", frozenset(plan) | {KUBE_SYSTEM_KEY})
        object.__setattr__(self, "delete", tuple(sorted(owned.items())))
        object.__setattr__(self, "namespaces", frozenset(namespaces) if inventory else frozenset())
        object.__setattr__(self, "discovery", bool(discovery))
        object.__setattr__(self, "crds", tuple(sorted((n, json.dumps(s, sort_keys=True)) for n, s in crds.items())))
        object.__setattr__(self, "services", frozenset(approved_services))
        object.__setattr__(self, "crd_owned", tuple(sorted(crd_owned.items())))

    def __setattr__(self, name, value):
        raise TransportError("policy_immutable")

    def crd_receipt_uid(self, name):
        """The UID the verified journal owns for a retained CRD, or None; never a DELETE permission."""
        return dict(self.crd_owned).get(name)

    def delete_uid(self, key):
        return dict(self.delete).get(key)

    def crd_spec(self, name):
        found = dict(self.crds).get(name)
        need(found is not None, "crd_not_reviewed")
        return json.loads(found)


class Evidence:
    """A validated result issued by one transport for one policy; immutable and sealed.

    A builder accepts it only for its own policy and kind with an intact seal; the transport accepts only evidence it
    issued itself and has not withdrawn. Hand-made, copied, re-bound or edited evidence is refused (evidence_invalid).
    """

    def __init__(self, policy, kind, payload):
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        object.__setattr__(self, "_policy", policy)
        object.__setattr__(self, "_kind", kind)
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_seal", hashlib.sha256((kind + "\n" + data).encode()).hexdigest())

    def __setattr__(self, name, value):
        raise TransportError("evidence_immutable")

    def payload_for(self, policy, kind):
        need(isinstance(self, Evidence) and self._policy is policy and self._kind == kind
             and hashlib.sha256((self._kind + "\n" + self._data).encode()).hexdigest() == self._seal,
             "evidence_invalid")
        return json.loads(self._data)


def evidence_payload(evidence, policy, kind):
    need(isinstance(evidence, Evidence), "evidence_invalid")
    return evidence.payload_for(policy, kind)


def destroy_metadata_request(policy, identity):
    """Single-object metadata GET (finalizers, deletionTimestamp, UID) of a plan identity or kube-system."""
    need(policy.read.__contains__(identity_key(identity)), "identity_not_allowed")
    headers = {"Accept": METADATA_ACCEPT}
    return {"method": "GET", "path": object_path(identity), "query": {}, "headers": headers, "body": None}


def discovery_request(policy, path):
    need(policy.discovery, "discovery_not_allowed")
    valid = path in ("/api", "/apis", "/api/v1")
    if not valid and isinstance(path, str) and path.startswith("/apis/"):
        parts = path.split("/")
        valid = len(parts) == 4 and GROUP.fullmatch(parts[2]) is not None and VERSION.fullmatch(parts[3]) is not None
    need(valid, "discovery_path_not_allowed")
    return {"method": "GET", "path": path, "query": {}, "headers": {"Accept": JSON_ACCEPT}, "body": None}


def group_version_path(group, version):
    need(isinstance(version, str) and VERSION.fullmatch(version) is not None, "list_version_invalid")
    if group == "":
        need(version == "v1", "list_version_invalid")
        return "/api/v1"
    need(isinstance(group, str) and GROUP.fullmatch(group) is not None, "list_group_invalid")
    return "/apis/" + group + "/" + version


def continue_query(token):
    if token is None:
        return {}
    need(isinstance(token, str) and CONTINUE_TOKEN.fullmatch(token) is not None, "continue_token_invalid")
    return {"continue": token}


def namespace_list_request(policy, targets, namespace, group, version, resource, token=None):
    """Metadata-only LIST, one page, of a resource that a complete discovery returned, in an approved namespace."""
    need(namespace in policy.namespaces, "namespace_not_approved")
    need(isinstance(resource, str) and RESOURCE.fullmatch(resource) is not None, "list_resource_invalid")
    path = group_version_path(group, version) + "/namespaces/" + namespace + "/" + resource
    need((group, version, resource) in targets, "list_target_not_discovered")
    query = dict({"limit": str(LIST_PAGE_SIZE)}, **continue_query(token))
    return {"method": "GET", "path": path, "query": query, "headers": {"Accept": LIST_ACCEPT}, "body": None}


def crd_read_request(policy, name):
    """The specialised CRD read: one reviewed CRD, structured fields only (validate_crd_response)."""
    policy.crd_spec(name)
    return {"method": "GET", "path": CRD_PATH + name, "query": {}, "headers": {"Accept": JSON_ACCEPT}, "body": None}


def crd_instance_request_for(spec):
    return {"method": "GET", "path": group_version_path(spec["group"], spec["storage_version"]) + "/" + spec["plural"],
            "query": {"limit": "1"}, "headers": {"Accept": LIST_ACCEPT}, "body": None}


def crd_instance_list_request(policy, verified):
    """Cluster-wide metadata-only LIST (limit=1) at the storage version the specialised read verified.

    ``verified`` is the transport's crd_verified Evidence for this policy; a hand-made VERIFIED record is refused.
    """
    payload = evidence_payload(verified, policy, "crd_verified")
    spec = policy.crd_spec(payload.get("name"))
    need(payload.get("storage_version") == spec["storage_version"] and payload.get("uid") is not None
         and payload.get("uid") == payload.get("receipt_uid"), "crd_not_verified")
    return crd_instance_request_for(spec)


def service_type_request(policy, identity):
    """The specialised Service read: spec.type of an approved runtime Service, nothing else."""
    need(identity_key(identity) in policy.services, "service_read_not_approved")
    return {"method": "GET", "path": object_path(identity), "query": {}, "headers": {"Accept": JSON_ACCEPT},
            "body": None}


def runtime_delete_request(policy, identity, uid):
    """UID-precondition DELETE of a runtime object whose UID the receipt proves; never a CRD, Secret or kube-system."""
    key = identity_key(identity)
    need(key != KUBE_SYSTEM_KEY, "kube_system_delete_refused")
    need((key[0], key[1]) != CRD_TYPE, "crd_delete_refused")
    need(key[1] != "Secret", "secret_delete_refused")
    expected = policy.delete_uid(key)
    need(expected is not None, "delete_not_allowed")
    need(isinstance(uid, str) and uid == expected, "delete_uid_not_proven")
    body = {"apiVersion": "v1", "kind": "DeleteOptions", "propagationPolicy": "Background",
            "preconditions": dict(uid=uid)}
    return {"method": "DELETE", "path": object_path(identity), "query": {},
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
            "body": json.dumps(body, sort_keys=True, separators=(",", ":"))}


def check_request(request):
    """Structural defence in depth: only the shapes the builders make (policy authorisation is separate)."""
    need(isinstance(request, dict) and set(request) == {"method", "path", "query", "headers", "body"},
         "request_shape")
    method, path, query, body = request["method"], request["path"], request["query"], request["body"]
    need(method in ("GET", "DELETE"), "method_not_allowed")
    need(isinstance(path, str) and ".." not in path and "%" not in path and "?" not in path, "path_not_allowed")
    need(isinstance(query, dict) and set(query) <= {"limit", "continue"}
         and all(isinstance(v, str) for v in query.values()), "query_not_allowed")
    if "limit" in query:
        need(query["limit"] in (str(LIST_PAGE_SIZE), "1"), "query_not_allowed")
    if "continue" in query:
        need(CONTINUE_TOKEN.fullmatch(query["continue"]) is not None, "query_not_allowed")
    if method == "GET":
        need(body is None, "request_shape")
        need(DISCOVERY_PATH.fullmatch(path) is not None or OBJECT_PATH.fullmatch(path) is not None,
             "path_not_allowed")
        return
    need(query == {} and OBJECT_PATH.fullmatch(path) is not None and single_object_path(path), "path_not_allowed")
    try:
        options = json.loads(body)
    except (TypeError, ValueError):
        raise TransportError("delete_options_invalid") from None
    need(isinstance(options, dict) and set(options) == DELETE_BODY_KEYS and options["kind"] == "DeleteOptions"
         and options["apiVersion"] == "v1" and options["propagationPolicy"] == "Background"
         and isinstance(options["preconditions"], dict) and set(options["preconditions"]) == {"uid"}
         and isinstance(options["preconditions"]["uid"], str) and UID.fullmatch(options["preconditions"]["uid"]),
         "delete_options_invalid")


def single_object_path(path):
    """A path that names one object: never a collection, so no delete-all or selector delete can be expressed."""
    parts = path.split("/")
    core = parts[1] == "api"
    base = 3 if core else 4                      # ["", "api", "v1"] or ["", "apis", group, version]
    rest = parts[base:]
    if len(rest) == 4:
        return rest[0] == "namespaces"           # namespaces/<ns>/<plural>/<name>
    return len(rest) == 2 and (core or rest[0] != "namespaces")  # <plural>/<name>, or the core namespaces/<name>


def parse_json(status, body, limit=MAX_RESPONSE_BYTES):
    need(status != 403, "forbidden")
    need(status != 410, "list_expired")
    need(status == 200, "unexpected_status")
    need(isinstance(body, (bytes, bytearray)) and len(body) <= limit, "response_too_large")
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise TransportError("response_not_json") from None
    need(isinstance(document, dict), "response_shape")
    return document


def trusted_not_found(group, resource, name, status, body):
    """A 404 the API server gives for a missing object at a valid endpoint, not for a missing endpoint or resource."""
    if status != 404 or not isinstance(body, (bytes, bytearray)) or len(body) > MAX_RESPONSE_BYTES:
        return False
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return False
    details = document.get("details") if isinstance(document, dict) else None
    return (isinstance(details, dict) and document.get("kind") == "Status" and document.get("apiVersion") == "v1"
            and document.get("status") == "Failure" and document.get("reason") == "NotFound"
            and document.get("code") == 404 and details.get("name") == name and details.get("kind") == resource
            and details.get("group", "") == group)


def identity_resource(identity):
    api_version, kind = identity["apiVersion"], identity["kind"]
    need((api_version, kind) in KINDS, "kind_not_allowed")
    return (api_version.split("/")[0] if "/" in api_version else ""), KINDS[(api_version, kind)][0]


def validate_destroy_metadata(identity, status, body):
    """Metadata of a plan object, None only for a trusted NotFound; any other 404 is not absence."""
    if status == 404:
        group, resource = identity_resource(identity)
        need(trusted_not_found(group, resource, identity["name"], status, body), "not_found_untrusted")
        return None
    metadata = validate_metadata_response(identity, status, body)
    object_state(metadata)
    return metadata


def object_state(metadata):
    """UID, whether deletion was requested, and the finalizers: nothing else of the metadata."""
    finalizers = metadata.get("finalizers", [])
    need(isinstance(finalizers, list) and all(isinstance(f, str) and FINALIZER.fullmatch(f) for f in finalizers)
         and len(set(finalizers)) == len(finalizers), "response_finalizers_invalid")
    deletion = metadata.get("deletionTimestamp")
    need(deletion is None or (isinstance(deletion, str) and RFC3339.fullmatch(deletion) is not None),
         "response_deletion_invalid")
    return {"uid": metadata["uid"], "deletion_requested": deletion is not None, "finalizers": list(finalizers)}


def validate_runtime_delete_response(status):
    """REQUESTED only: a 200 or 202 is never completion, which needs a trusted NotFound afterwards."""
    need(status not in (409,), "uid_precondition_failed")
    need(status != 403, "forbidden")
    need(status != 404, "not_found_at_delete")
    need(status in (200, 202), "unexpected_status")
    return "REQUESTED"


# ---- discovery -------------------------------------------------------------------------------------------------------

def validate_discovery_response(path, status, body):
    document = parse_json(status, body)
    if path == "/api":
        need(document.get("kind") == "APIVersions" and isinstance(document.get("versions"), list)
             and all(isinstance(v, str) and VERSION.fullmatch(v) for v in document["versions"])
             and len(set(document["versions"])) == len(document["versions"]), "discovery_invalid")
        return {"versions": list(document["versions"])}
    if path == "/apis":
        need(document.get("kind") == "APIGroupList" and document.get("apiVersion") == "v1"
             and isinstance(document.get("groups"), list), "discovery_invalid")
        groups, names = [], set()
        for group in document["groups"]:
            need(isinstance(group, dict) and isinstance(group.get("name"), str) and GROUP.fullmatch(group["name"])
                 and group["name"] not in names and isinstance(group.get("versions"), list) and group["versions"],
                 "discovery_invalid")
            versions = []
            for entry in group["versions"]:
                need(isinstance(entry, dict) and isinstance(entry.get("version"), str)
                     and VERSION.fullmatch(entry["version"])
                     and entry.get("groupVersion") == group["name"] + "/" + entry["version"], "discovery_invalid")
                versions.append(entry["version"])
            need(len(versions) == len(set(versions)), "discovery_invalid")
            names.add(group["name"])
            groups.append({"name": group["name"], "versions": versions})
        return {"groups": groups}
    expected = "v1" if path == "/api/v1" else path[len("/apis/"):]
    need(document.get("kind") == "APIResourceList" and document.get("groupVersion") == expected
         and isinstance(document.get("resources"), list), "discovery_invalid")
    resources, seen = [], set()
    for resource in document["resources"]:
        need(isinstance(resource, dict) and isinstance(resource.get("name"), str)
             and isinstance(resource.get("namespaced"), bool) and isinstance(resource.get("verbs"), list)
             and all(isinstance(v, str) and VERB.fullmatch(v) for v in resource["verbs"])
             and len(set(resource["verbs"])) == len(resource["verbs"]) and resource["name"] not in seen,
             "discovery_invalid")
        need(isinstance(resource.get("kind"), str) and KIND_FORM.fullmatch(resource["kind"]) is not None,
             "discovery_mapping_invalid")
        seen.add(resource["name"])
        resources.append({"name": resource["name"], "kind": resource.get("kind"), "namespaced": resource["namespaced"],
                          "verbs": sorted(resource["verbs"])})
    return {"groupVersion": expected, "resources": resources}


def discovery_targets(core, groups, resource_lists):
    """Every namespaced, listable resource of every advertised group version, or UNKNOWN with a reason.

    Every advertised version is examined, not only the preferred one; the resource lists must be exactly the
    advertised group versions; a missing or unexpected list, a malformed resource name or a namespaced resource
    without list (outside the virtual allowlist) is UNKNOWN. The REQUIRED_CORE_RESOURCES must be present,
    namespaced, listable and mapped to their kind. This is a Fake-only contract: it never proves that a real API
    server's discovery is complete.
    """
    if "v1" not in core["versions"]:
        return {"status": "UNKNOWN", "reason": "discovery_core_missing"}
    advertised = [("", "v1")] + [(g["name"], v) for g in groups["groups"] for v in g["versions"]]
    expected_lists = {group + "/" + version if group else "v1" for group, version in advertised}
    if set(resource_lists) - expected_lists:
        return {"status": "UNKNOWN", "reason": "discovery_unexpected_group"}
    core_resources = {r["name"]: r for r in (resource_lists.get("v1") or {"resources": []})["resources"]}
    for name, kind in sorted(REQUIRED_CORE_RESOURCES.items()):
        required = core_resources.get(name) or {}
        if not required:
            return {"status": "UNKNOWN", "reason": "discovery_required_resource_missing"}
        if not (required.get("namespaced") is True and "list" in required.get("verbs", ())
                and required.get("kind") == kind):
            return {"status": "UNKNOWN", "reason": "discovery_required_resource_invalid"}
    targets, mapped = [], []
    for group, version in advertised:
        listing = resource_lists.get(group + "/" + version if group else "v1")
        if listing is None:
            return {"status": "UNKNOWN", "reason": "discovery_group_missing"}
        for resource in listing["resources"]:
            name = resource["name"]
            if "/" in name:
                continue
            if RESOURCE.fullmatch(name) is None:
                return {"status": "UNKNOWN", "reason": "unknown_resource_mapping"}
            # 6c-B4b: every resource's verified mapping (namespaced or cluster-scoped) stays with the evidence, so a
            # CRD is judged by its exact group, version and plural, never by its group alone.
            mapped.append((group, version, name, resource["kind"], resource["namespaced"]))
            if not resource["namespaced"]:
                continue
            if "list" in resource["verbs"]:
                targets.append((group, version, name))
            elif (group, name) not in VIRTUAL_RESOURCES:
                return {"status": "UNKNOWN", "reason": "resource_not_listable"}
    if not targets:
        return {"status": "UNKNOWN", "reason": "discovery_targets_empty"}
    return {"status": "COMPLETE", "targets": sorted(targets), "advertised": sorted(advertised),
            "resources": sorted(mapped)}


# ---- metadata LIST and pagination ---------------------------------------------------------------------------------

def owner_references(owners):
    """Minimal owner references; malformed entries, two controllers or a repeated owner UID are refused."""
    need(isinstance(owners, list), "response_owner_invalid")
    result, uids = [], set()
    for owner in owners:
        need(isinstance(owner, dict) and set(owner) <= OWNER_KEYS
             and isinstance(owner.get("apiVersion"), str) and API_VERSION_FORM.fullmatch(owner["apiVersion"])
             and isinstance(owner.get("kind"), str) and KIND_FORM.fullmatch(owner["kind"])
             and isinstance(owner.get("name"), str) and NAME.fullmatch(owner["name"])
             and isinstance(owner.get("uid"), str) and UID.fullmatch(owner["uid"])
             and isinstance(owner.get("controller", False), bool)
             and isinstance(owner.get("blockOwnerDeletion", False), bool), "response_owner_invalid")
        need(owner["uid"] not in uids, "response_owner_conflict")
        uids.add(owner["uid"])
        result.append({"apiVersion": owner["apiVersion"], "kind": owner["kind"], "name": owner["name"],
                       "uid": owner["uid"], "controller": owner.get("controller", False)})
    need(sum(1 for o in result if o["controller"]) <= 1, "response_owner_conflict")
    return result


def validate_list_response(namespace, limit, status, body):
    """One PartialObjectMetadataList page: minimal item metadata, the continue token and the snapshot version.

    ``namespace`` is the requested namespace, or None for a cluster-wide CRD instance list. Item payload keys
    (``data``, ``spec`` and the like) and the last-applied annotation are refused by their position in the
    document; managedFields are never returned, so their field paths are never mistaken for payload.
    """
    document = parse_json(status, body)
    need(FORBIDDEN_RESPONSE_KEYS.isdisjoint(document), "response_not_metadata_only")
    need(document.get("kind") == "PartialObjectMetadataList" and document.get("apiVersion") == "meta.k8s.io/v1",
         "response_not_partial_object_metadata_list")
    need(set(document) == {"kind", "apiVersion", "metadata", "items"}, "response_shape")
    meta, items = document["metadata"], document["items"]
    need(isinstance(meta, dict) and set(meta) <= {"continue", "resourceVersion", "remainingItemCount"}
         and isinstance(items, list), "response_shape")
    need(isinstance(meta.get("resourceVersion"), str) and RESOURCE_VERSION_FORM.fullmatch(meta["resourceVersion"]),
         "list_resource_version_invalid")
    token = meta.get("continue", "")
    need(isinstance(token, str) and (token == "" or CONTINUE_TOKEN.fullmatch(token) is not None),
         "continue_token_invalid")
    remaining = meta.get("remainingItemCount")
    need(remaining is None or (type(remaining) is int and remaining >= 0 and (token != "" or remaining == 0)),
         "list_remaining_invalid")
    need(len(items) <= limit, "list_over_limit")
    result, uids, names = [], set(), set()
    for item in items:
        need(isinstance(item, dict), "response_shape")
        need(not (FORBIDDEN_RESPONSE_KEYS & set(item)), "response_not_metadata_only")
        need(set(item) <= {"kind", "apiVersion", "metadata"}, "response_shape")
        typed = ("kind" in item, "apiVersion" in item)
        need(typed == (False, False) or (item.get("kind") == "PartialObjectMetadata"
                                         and item.get("apiVersion") == "meta.k8s.io/v1"), "response_item_type_invalid")
        metadata = item.get("metadata")
        need(isinstance(metadata, dict), "response_shape")
        annotations = metadata.get("annotations", {})
        need(type(annotations) is dict, "response_shape")
        need(LAST_APPLIED not in annotations.keys(), "response_secret_annotation_refused")
        name, item_namespace, uid = metadata.get("name"), metadata.get("namespace", ""), metadata.get("uid")
        need(isinstance(name, str) and NAME.fullmatch(name) is not None, "response_identity_invalid")
        need(isinstance(item_namespace, str) and (namespace is None or item_namespace == namespace)
             and (item_namespace == "" or NAME.fullmatch(item_namespace) is not None), "response_namespace_mismatch")
        need(isinstance(uid, str) and UID.fullmatch(uid) is not None, "response_uid_invalid")
        version = metadata.get("resourceVersion")
        need(version is None or (isinstance(version, str) and RESOURCE_VERSION_FORM.fullmatch(version)),
             "response_item_invalid")
        need(uid not in uids and (item_namespace, name) not in names, "list_duplicate_item")
        uids.add(uid)
        names.add((item_namespace, name))
        owners = owner_references(metadata.get("ownerReferences", []))
        state = object_state(dict(metadata, uid=uid))
        result.append({"name": name, "namespace": item_namespace, "uid": uid, "owners": owners,
                       "deletion_requested": state["deletion_requested"], "finalizers": state["finalizers"]})
    return {"items": result, "continue": token or None, "resource_version": meta["resourceVersion"]}


def collect_list(fetch_page, deadline=None):
    """One logical LIST, page by page, within the D11 bounds; COMPLETE only when the last page has no token.

    410 restarts the list from the beginning (the partial result is discarded) at most LIST_RESTART_LIMIT times;
    all pages, restarts included, count against LIST_PAGE_LIMIT. A repeated token, a snapshot change, a duplicate
    UID, one name with two UIDs, a timeout, the deadline or an invalid page is UNKNOWN; 403 is BLOCKED.
    """
    pages, restarts = 0, 0
    while restarts <= LIST_RESTART_LIMIT:
        items, uids, tokens, token, snapshot = [], set(), set(), None, None
        names = {}
        while True:
            if pages >= LIST_PAGE_LIMIT:
                return {"status": "UNKNOWN", "reason": "list_page_limit"}
            if deadline is not None and deadline.expired():
                return {"status": "UNKNOWN", "reason": "deadline_exceeded"}
            pages += 1
            try:
                page = fetch_page(token)
            except TransportError as error:
                if str(error) == "list_expired":
                    break
                if str(error) == "forbidden":
                    return {"status": "BLOCKED", "reason": "inventory_forbidden"}
                return {"status": "UNKNOWN", "reason": str(error)}
            except TimeoutError:
                return {"status": "UNKNOWN", "reason": "transport_timeout"}
            except Exception:  # noqa: BLE001 - anything else is UNKNOWN, never an empty list
                return {"status": "UNKNOWN", "reason": "transport_unknown"}
            if snapshot is None:
                snapshot = page["resource_version"]
            elif page["resource_version"] != snapshot:
                return {"status": "UNKNOWN", "reason": "list_snapshot_inconsistent"}
            for item in page["items"]:
                if item["uid"] in uids:
                    return {"status": "UNKNOWN", "reason": "list_duplicate_item"}
                if names.setdefault((item["namespace"], item["name"]), item["uid"]) != item["uid"]:
                    return {"status": "UNKNOWN", "reason": "list_identity_conflict"}
                uids.add(item["uid"])
                items.append(item)
            token = page["continue"]
            if deadline is not None and deadline.remaining() <= 0:
                return {"status": "UNKNOWN", "reason": "deadline_exceeded"}  # never COMPLETE at or after it
            if token is None:
                return {"status": "COMPLETE", "items": items, "pages": pages, "restarts": restarts}
            if token in tokens:
                return {"status": "UNKNOWN", "reason": "list_continue_repeated"}
            tokens.add(token)
        restarts += 1
    return {"status": "UNKNOWN", "reason": "list_restart_limit"}


def merge_listed(expected_targets, results):
    """Merge the COMPLETE lists of exactly the discovered targets of one namespace by UID.

    ``results`` is a list of (target, result). Every expected target must be listed once and COMPLETE: a missing,
    unexpected or repeated target, an empty target set or an incomplete list is never an (empty) inventory. The same
    UID may appear under several versions of one resource, or under the two event resources, only with the same
    name, namespace, owners, finalizers and deletion state; anything else is UNKNOWN. No classification here.
    """
    expected = {tuple(t) for t in expected_targets}
    if not expected:
        return {"status": "UNKNOWN", "reason": "discovery_targets_empty"}
    listed = [tuple(target) for target, _ in results]
    if len(set(listed)) != len(listed):
        return {"status": "UNKNOWN", "reason": "list_target_duplicate"}
    for _, result in results:
        if result.get("status") != "COMPLETE":
            return {"status": result.get("status", "UNKNOWN"), "reason": result.get("reason", "list_incomplete")}
    if expected - set(listed):
        return {"status": "UNKNOWN", "reason": "list_target_missing"}
    if set(listed) - expected:
        return {"status": "UNKNOWN", "reason": "list_target_unexpected"}
    merged, identities = {}, {}
    for (group, version, resource), result in sorted(((tuple(t), r) for t, r in results), key=lambda x: x[0]):
        logical = next((pair for pair in RESOURCE_ALIASES if (group, resource) in pair), (group, resource))
        for item in result["items"]:
            # One logical object (resource or approved alias, namespace, name) has one UID across versions.
            if identities.setdefault((logical, item["namespace"], item["name"]), item["uid"]) != item["uid"]:
                return {"status": "UNKNOWN", "reason": "cross_version_identity_conflict"}
            evidence = (item["name"], item["namespace"], json.dumps(item["owners"], sort_keys=True),
                        tuple(sorted(item["finalizers"])), item["deletion_requested"])
            seen = merged.get(item["uid"])
            if seen is None:
                merged[item["uid"]] = {"resources": {(group, resource)}, "evidence": evidence, "item": item}
                continue
            same_resource = (group, resource) in seen["resources"]
            alias = any({(group, resource)} | seen["resources"] <= pair for pair in RESOURCE_ALIASES)
            if not (same_resource or alias):
                return {"status": "UNKNOWN", "reason": "unknown_resource_mapping"}
            if seen["evidence"] != evidence:
                return {"status": "UNKNOWN", "reason": "cross_version_conflict"}
            seen["resources"].add((group, resource))
    return {"status": "COMPLETE", "targets": len(expected), "objects": [
        {"uid": uid, "name": m["item"]["name"], "namespace": m["item"]["namespace"],
         "resources": sorted(m["resources"]), "owners": m["item"]["owners"],
         "deletion_requested": m["item"]["deletion_requested"], "finalizers": m["item"]["finalizers"]}
        for uid, m in sorted(merged.items())]}


# ---- specialised CRD and Service reads ------------------------------------------------------------------------------

def validate_crd_response(name, status, body):
    """Structured CRD fields only (identity, UID, group, plural, scope, versions, Established), None for NotFound."""
    if status == 404:
        need(trusted_not_found("apiextensions.k8s.io", "customresourcedefinitions", name, status, body),
             "not_found_untrusted")
        return None
    document = parse_json(status, body, MAX_OBJECT_RESPONSE_BYTES)
    need(document.get("kind") == "CustomResourceDefinition" and document.get("apiVersion")
         == "apiextensions.k8s.io/v1", "crd_response_invalid")
    metadata, spec, crd_status = document.get("metadata"), document.get("spec"), document.get("status", {})
    need(isinstance(metadata, dict) and metadata.get("name") == name, "response_identity_mismatch")
    need(isinstance(metadata.get("uid"), str) and UID.fullmatch(metadata["uid"]) is not None, "response_uid_invalid")
    need(isinstance(spec, dict) and isinstance(spec.get("names"), dict) and isinstance(spec.get("versions"), list)
         and isinstance(spec.get("group"), str) and isinstance(spec["names"].get("plural"), str)
         and isinstance(spec.get("scope"), str) and isinstance(crd_status, dict), "crd_response_invalid")
    versions = spec["versions"]
    need(all(isinstance(v, dict) and isinstance(v.get("name"), str) and VERSION.fullmatch(v["name"])
             and isinstance(v.get("served"), bool) and isinstance(v.get("storage"), bool) for v in versions)
         and len({v["name"] for v in versions}) == len(versions), "crd_versions_invalid")
    storage = [v["name"] for v in versions if v["storage"]]
    need(len(storage) == 1, "crd_versions_invalid")
    conditions = crd_status.get("conditions", [])
    need(isinstance(conditions, list) and all(isinstance(c, dict) for c in conditions), "crd_response_invalid")
    established = [c for c in conditions if c.get("type") == "Established"]
    need(len(established) == 1 and established[0].get("status") in CONDITION_STATES, "crd_established_invalid")
    return {"name": name, "uid": metadata["uid"], "group": spec["group"], "plural": spec["names"]["plural"],
            "scope": spec["scope"], "storage_versions": storage,
            "served_versions": sorted(v["name"] for v in versions if v["served"]),
            "established": established[0].get("status") == "True"}


def verify_crd(policy, name, info, receipt_uid):
    """VERIFIED only when the live CRD is the reviewed one: UID, group, plural, scope, storage version served,
    Established. A 200 on a later LIST is never evidence of any of these. This is the verdict only; the evidence a
    CRD instance LIST needs is issued by FakeDestroyTransport.verify_crd."""
    spec = policy.crd_spec(name)
    checks = (
        (info["uid"] == receipt_uid, "crd_uid_mismatch"),
        (info["group"] == spec["group"], "crd_group_mismatch"),
        (info["plural"] == spec["plural"], "crd_plural_mismatch"),
        (info["scope"] == spec["scope"], "crd_scope_mismatch"),
        (info["storage_versions"] == [spec["storage_version"]], "crd_storage_version_mismatch"),
        (spec["storage_version"] in info["served_versions"], "crd_storage_not_served"),
        (info["established"] is True, "crd_not_established"),
    )
    for ok, reason in checks:
        if not ok:
            return {"verdict": "BLOCKED", "name": name, "reason": reason}
    return {"verdict": "VERIFIED", "name": name, "storage_version": spec["storage_version"], "reason": None}


def classify_crd(policy, name, read, receipt_uid, open_intent, advertised):
    """VERIFIED, CRD_NOT_CREATED, BLOCKED or UNKNOWN for one reviewed CRD (D5).

    ``read``: ("present", info), ("absent", None) or ("unknown", reason). ``receipt_uid``: the UID the receipt
    owns, or None. ``open_intent``: an unresolved apply INTENT for it. ``advertised``: whether a COMPLETE discovery
    serves its (group, plural), or None when discovery is not COMPLETE. CRD_NOT_CREATED needs no creation evidence,
    no open INTENT, a trusted NotFound and a discovery that does not serve the plural. A claimed CRD that is gone,
    another UID and a foreign CRD (present, not claimed) are BLOCKED: never deleted, never adopted.
    """
    state, value = read
    if state == "unknown":
        return {"verdict": "UNKNOWN", "name": name, "reason": value}
    if state == "absent":
        if receipt_uid is not None:
            return {"verdict": "BLOCKED", "name": name, "reason": "crd_claimed_but_absent"}
        if open_intent:
            return {"verdict": "UNKNOWN", "name": name, "reason": "crd_open_intent"}
        if advertised is None:
            return {"verdict": "UNKNOWN", "name": name, "reason": "discovery_incomplete"}
        if advertised:
            return {"verdict": "UNKNOWN", "name": name, "reason": "crd_discovery_inconsistent"}
        return {"verdict": "CRD_NOT_CREATED", "name": name, "reason": None}
    if receipt_uid is None:
        return {"verdict": "BLOCKED", "name": name, "reason": "foreign_crd"}
    return verify_crd(policy, name, value, receipt_uid)


def classify_crd_instances(status, body):
    """ZERO_INSTANCES only for 200, no items and no continue token; instances are BLOCKED; anything else UNKNOWN."""
    try:
        page = validate_list_response(None, 1, status, body)
    except TransportError as error:
        if str(error) == "forbidden":
            return {"verdict": "BLOCKED", "reason": "crd_list_forbidden"}
        return {"verdict": "UNKNOWN", "reason": str(error)}
    if page["items"]:
        return {"verdict": "BLOCKED", "reason": "crd_instances_remain"}
    if page["continue"] is not None:
        return {"verdict": "UNKNOWN", "reason": "crd_list_inconsistent"}
    return {"verdict": "ZERO_INSTANCES", "reason": None}


def validate_service_type_response(identity, status, body):
    """{uid, type} of a runtime Service, None for a trusted NotFound; nothing else of the object is returned."""
    if status == 404:
        need(trusted_not_found("", "services", identity["name"], status, body), "not_found_untrusted")
        return None
    document = parse_json(status, body)
    need(document.get("kind") == "Service" and document.get("apiVersion") == "v1", "service_response_invalid")
    metadata, spec = document.get("metadata"), document.get("spec")
    need(isinstance(metadata, dict) and metadata.get("name") == identity["name"]
         and metadata.get("namespace") == identity["namespace"], "response_identity_mismatch")
    need(isinstance(metadata.get("uid"), str) and UID.fullmatch(metadata["uid"]) is not None, "response_uid_invalid")
    need(isinstance(spec, dict) and spec.get("type") in SERVICE_TYPES, "service_type_invalid")
    return {"uid": metadata["uid"], "type": spec["type"], "load_balancer": spec["type"] == "LoadBalancer"}


class FakeDestroyTransport:
    """Offline double for the destroy contracts.

    ``send`` is the only way to the server. It refuses after the global deadline, authorises the request against the
    policy and this transport's evidence (it must equal, field for field, what a builder makes; see authorize), and
    refuses an answer that arrives at or after the global deadline (deadline_exceeded) or after the request's own
    timeout (request_timeout). A refused request never reaches the server.
    """

    def __init__(self, policy, server, deadline):
        need(isinstance(policy, DestroyPolicy) and callable(server) and isinstance(deadline, Deadline),
             "fake_transport_needs_policy_server_and_deadline")
        self.policy = policy
        self.server = server
        self.deadline = deadline
        self.requests = []
        self._issued = {}
        self._targets = frozenset()
        self._verified_crds = set()
        self._paths = {object_path(identity_of(key)): identity_of(key) for key in policy.read}

    # -- evidence ---------------------------------------------------------------------------------------------------
    def _issue(self, kind, payload, scope):
        evidence = Evidence(self.policy, kind, payload)
        self._issued[id(evidence)] = (evidence, evidence._seal, scope)
        return evidence

    def _withdraw(self, scope):
        """Withdraw every evidence of a scope: ("discovery",) or ("crd", name)."""
        for key in [k for k, entry in self._issued.items() if entry[2] == scope]:
            self._issued.pop(key)

    def _accept(self, evidence, kind):
        stored = self._issued.get(id(evidence)) if isinstance(evidence, Evidence) else None
        need(stored is not None and stored[0] is evidence and stored[1] == evidence._seal, "evidence_invalid")
        payload = evidence.payload_for(self.policy, kind)
        if kind == "crd_verified":
            need(payload.get("name") in self._verified_crds
                 and payload.get("receipt_uid") == self.policy.crd_receipt_uid(payload.get("name")), "evidence_invalid")
        return payload

    def _invalidate_observed(self, request):
        """R01-R: an authorised read of a CRD (its specialised GET or its metadata GET, both on CRD_PATH) or of a
        discovery path may observe new state, so before it reaches the server it withdraws the earlier evidence that
        state backs, whatever the answer: absence, another UID, not Established, another storage version, 403, 5xx,
        timeout, an invalid or an identical answer. Other CRDs keep theirs. Every authorised request on these paths is
        a GET (a CRD DELETE is refused by the policy)."""
        path = request["path"]
        if path.startswith(CRD_PATH):
            observed = path[len(CRD_PATH):]
            self._withdraw(("crd", observed))
            self._verified_crds.discard(observed)
        if DISCOVERY_PATH.fullmatch(path) is not None:
            self._withdraw(scope=("discovery",))
            self._targets = frozenset()

    # -- the send boundary ------------------------------------------------------------------------------------------
    def _candidates(self, request):
        """(expected request, timeout) pairs this policy and this transport's evidence allow for this method and path."""
        method, path, query = request["method"], request["path"], request["query"]
        identity = self._paths.get(path)
        if method == "DELETE":
            if identity is not None and self.policy.delete_uid(identity_key(identity)) is not None:
                yield (lambda: runtime_delete_request(self.policy, identity,
                                                      self.policy.delete_uid(identity_key(identity)))), \
                    DELETE_REQUEST_TIMEOUT_SECONDS
            return
        if identity is not None:
            yield (lambda: destroy_metadata_request(self.policy, identity)), API_READ_TIMEOUT_SECONDS
            if identity_key(identity) in self.policy.services:
                yield (lambda: service_type_request(self.policy, identity)), API_READ_TIMEOUT_SECONDS
        if DISCOVERY_PATH.fullmatch(path):
            yield (lambda: discovery_request(self.policy, path)), API_READ_TIMEOUT_SECONDS
        if path.startswith(CRD_PATH):
            yield (lambda: crd_read_request(self.policy, path[len(CRD_PATH):])), API_READ_TIMEOUT_SECONDS
        for name in sorted(self._verified_crds):
            yield (lambda name=name: crd_instance_request_for(self.policy.crd_spec(name))), API_READ_TIMEOUT_SECONDS
        parts = path.split("/")
        if len(parts) == 6 and parts[1:4] == ["api", "v1", "namespaces"]:
            target = ("", "v1", parts[5])
            namespace = parts[4]
        elif len(parts) == 7 and parts[1] == "apis" and parts[4] == "namespaces":
            target = (parts[2], parts[3], parts[6])
            namespace = parts[5]
        else:
            return
        yield (lambda: namespace_list_request(self.policy, self._targets, namespace, *target,
                                              query.get("continue"))), API_READ_TIMEOUT_SECONDS

    def authorize(self, request):
        """The request's timeout if this policy and this transport's evidence allow exactly this request."""
        check_request(request)
        for build, timeout in self._candidates(request):
            try:
                expected = build()
            except TransportError:
                continue
            if expected == request:
                return timeout
        raise TransportError("request_not_authorized")

    def send(self, request):
        need(not self.deadline.expired(), "deadline_exceeded")
        timeout = self.authorize(request)
        self._invalidate_observed(request)  # R01-R: before the request can reach the server
        clock = self.deadline.clock
        start = clock.now()
        self.requests.append(request)
        try:
            status, body = self.server(request)
        except TimeoutError:
            raise TransportError("transport_timeout") from None
        if self.deadline.expired():
            raise TransportError("deadline_exceeded")  # an answer at or after the global deadline is never evidence
        need(clock.now() - start <= timeout, "request_timeout")  # the request's own D11 bound, 20 s inclusive
        return status, body

    # -- operations -------------------------------------------------------------------------------------------------
    def get_metadata(self, identity):
        status, body = self.send(destroy_metadata_request(self.policy, identity))
        return validate_destroy_metadata(identity, status, body)

    def _discover(self, path):
        status, body = self.send(discovery_request(self.policy, path))
        return validate_discovery_response(path, status, body)

    def discover_all(self):
        """Complete discovery: /api, /apis, /api/v1 and every advertised group version. Only a COMPLETE result issues
        the discovery evidence that namespace LISTs need; a new discovery withdraws the previous evidence."""
        self._withdraw(("discovery",))
        self._targets = frozenset()
        try:
            core = self._discover("/api")
            groups = self._discover("/apis")
            lists = {"v1": self._discover("/api/v1")}
            for group in groups["groups"]:
                for version in group["versions"]:
                    gv = group["name"] + "/" + version
                    lists[gv] = self._discover("/apis/" + gv)
        except TransportError as error:
            return {"status": "BLOCKED" if str(error) == "forbidden" else "UNKNOWN", "reason": str(error)}
        result = discovery_targets(core, groups, lists)
        if result["status"] != "COMPLETE":
            return result
        self._targets = frozenset(result["targets"])
        evidence = self._issue("discovery", {"targets": [list(t) for t in result["targets"]],
                                             "advertised": [list(a) for a in result["advertised"]],
                                             "resources": [list(r) for r in result["resources"]]}, ("discovery",))
        return {"status": "COMPLETE", "targets": result["targets"], "evidence": evidence}

    def list_namespace(self, discovery, namespace, group, version, resource):
        targets = frozenset(tuple(t) for t in self._accept(discovery, "discovery")["targets"])
        need((group, version, resource) in targets, "list_target_not_discovered")

        def page(token):
            status, body = self.send(namespace_list_request(self.policy, targets, namespace, group, version, resource,
                                                            token))
            return validate_list_response(namespace, LIST_PAGE_SIZE, status, body)
        return collect_list(page, self.deadline)

    def inventory_namespace(self, discovery, namespace):
        """Every discovered target of one namespace, listed and merged; no classification (6c-B4b)."""
        targets = [tuple(t) for t in self._accept(discovery, "discovery")["targets"]]
        results = []
        for target in targets:
            result = self.list_namespace(discovery, namespace, *target)
            results.append((target, result))
            if result["status"] != "COMPLETE":
                break
        return merge_listed(targets, results)

    def discovery_payload(self, discovery):
        """The payload of this transport's own, current discovery evidence (stale or foreign evidence is refused)."""
        return self._accept(discovery, "discovery")

    def read_crd(self, name):
        """A new read of a CRD withdraws every earlier read and verification of it first, whatever this read finds
        (absent, another UID, not Established, changed versions, an error): only a later verification of this read
        allows its instance LIST again."""
        self.policy.crd_spec(name)
        self._withdraw(("crd", name))
        self._verified_crds.discard(name)
        status, body = self.send(crd_read_request(self.policy, name))
        info = validate_crd_response(name, status, body)
        if info is None:
            return {"state": "absent"}
        return {"state": "present", "info": info, "evidence": self._issue("crd_read", info, ("crd", name))}

    def verify_crd(self, read_evidence, receipt_uid=None):
        """The verdict for this transport's latest CRD read against the UID the verified journal owns for it.

        The policy's CRD receipt map is the only ownership evidence: no CRD UID there, or a ``receipt_uid`` other
        than it, is BLOCKED and never VERIFIED. VERIFIED carries the evidence a CRD instance LIST needs."""
        info = self._accept(read_evidence, "crd_read")
        canonical = self.policy.crd_receipt_uid(info["name"])
        if canonical is None:
            return {"verdict": "BLOCKED", "name": info["name"], "reason": "crd_not_owned_by_receipt"}
        if receipt_uid is not None and receipt_uid != canonical:
            return {"verdict": "BLOCKED", "name": info["name"], "reason": "crd_receipt_uid_mismatch"}
        verdict = verify_crd(self.policy, info["name"], info, canonical)
        if verdict["verdict"] != "VERIFIED":
            return verdict
        self._verified_crds.add(info["name"])
        evidence = self._issue("crd_verified", {"name": info["name"], "uid": info["uid"], "receipt_uid": canonical,
                                                "storage_version": self.policy.crd_spec(info["name"])["storage_version"]},
                               ("crd", info["name"]))
        return dict(verdict, evidence=evidence)

    def crd_instances(self, verified):
        self._accept(verified, "crd_verified")
        try:
            status, body = self.send(crd_instance_list_request(self.policy, verified))
        except TransportError as error:
            return {"verdict": "UNKNOWN", "reason": str(error)}
        return classify_crd_instances(status, body)

    def read_service_type(self, identity):
        status, body = self.send(service_type_request(self.policy, identity))
        return validate_service_type_response(identity, status, body)

    def delete_runtime(self, identity, uid):
        status, _ = self.send(runtime_delete_request(self.policy, identity, uid))
        return validate_runtime_delete_response(status)


def open_destroy_transport(kind, policy=None, server=None, deadline=None):
    """Only the offline fake; any real destroy transport is refused."""
    need(APPROVED_TRANSPORTS.__contains__(kind), "real_transport_not_implemented")
    return FakeDestroyTransport(policy, server, deadline)
