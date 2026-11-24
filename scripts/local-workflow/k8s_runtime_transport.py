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
#   namespace LIST               -> DestroyPolicy.namespaces (istio-system, <project>-ingress, <project>-app only)
#   CRD instance LIST            -> DestroyPolicy.crds      (the reviewed CRDs, at their verified storage version)
#   specialised CRD read         -> DestroyPolicy.crds      (structured fields only, never the object)
#   specialised Service read     -> DestroyPolicy.services  (spec.type of the runtime's <project>-ingress Services)
#   runtime DELETE               -> DestroyPolicy.delete    (identity -> UID proven by the receipt; no CRD, Secret or
#                                                            kube-system namespace)
#   G9 Secret DELETE             -> Policy(secret_project=...) above, unchanged
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
INVENTORY_NAMESPACES = ("istio-system", "{project}-ingress", "{project}-app")
# Namespaced resources without the list verb that design section 5.1 allows: virtual, never persisted.
VIRTUAL_RESOURCES = frozenset({("", "bindings"), ("authorization.k8s.io", "localsubjectaccessreviews")})
# The same objects served under two resources (design section 5.1: both are listed).
RESOURCE_ALIASES = (frozenset({("", "events"), ("events.k8s.io", "events")}),)
CRD_TYPE = ("apiextensions.k8s.io/v1", "CustomResourceDefinition")
KUBE_SYSTEM_KEY = ("v1", "Namespace", "", "kube-system")
LIST_ITEM_METADATA = {"name", "namespace", "uid", "ownerReferences", "deletionTimestamp", "finalizers"}
SERVICE_TYPES = {"ClusterIP", "NodePort", "LoadBalancer", "ExternalName"}
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


class DestroyPolicy:
    """What a destroy transport may read, list and delete. Immutable; nothing a read returns can widen it."""

    def __init__(self, project, plan_identities, owned_uids=None, inventory=False, discovery=False, crd_specs=None,
                 services=()):
        namespaces = inventory_namespaces(project)
        plan = {}
        for identity in plan_identities:
            key = identity_key(identity)
            need(key[1] != "Secret", "secret_path_not_approved")
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

    def __setattr__(self, name, value):
        raise TransportError("policy_immutable")

    def delete_uid(self, key):
        return dict(self.delete).get(key)

    def crd_spec(self, name):
        found = dict(self.crds).get(name)
        need(found is not None, "crd_not_reviewed")
        return json.loads(found)


def api_prefix(api_version):
    return "/api/v1" if api_version == "v1" else "/apis/" + api_version


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


def namespace_list_request(policy, namespace, group, version, resource, token=None):
    """Metadata-only LIST of one discovered resource in one approved namespace, one page."""
    need(namespace in policy.namespaces, "namespace_not_approved")
    need(isinstance(resource, str) and RESOURCE.fullmatch(resource) is not None, "list_resource_invalid")
    query = dict({"limit": str(LIST_PAGE_SIZE)}, **continue_query(token))
    return {"method": "GET", "path": group_version_path(group, version) + "/namespaces/" + namespace + "/" + resource,
            "query": query, "headers": {"Accept": LIST_ACCEPT}, "body": None}


def crd_read_request(policy, name):
    """The specialised CRD read: one reviewed CRD, structured fields only (validate_crd_response)."""
    policy.crd_spec(name)
    return {"method": "GET", "path": "/apis/apiextensions.k8s.io/v1/customresourcedefinitions/" + name, "query": {},
            "headers": {"Accept": JSON_ACCEPT}, "body": None}


def crd_instance_list_request(policy, name, verified):
    """Cluster-wide metadata-only LIST (limit=1) at the storage version the specialised read verified."""
    spec = policy.crd_spec(name)
    need(isinstance(verified, dict) and verified.get("verdict") == "VERIFIED" and verified.get("name") == name
         and verified.get("storage_version") == spec["storage_version"], "crd_not_verified")
    return {"method": "GET", "path": group_version_path(spec["group"], spec["storage_version"]) + "/" + spec["plural"],
            "query": {"limit": "1"}, "headers": {"Accept": LIST_ACCEPT}, "body": None}


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
    """Defence in depth before anything is sent: only the shapes the builders make."""
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
    return validate_metadata_response(identity, status, body)


def object_state(metadata):
    """UID, whether deletion was requested, and the finalizers: nothing else of the metadata."""
    finalizers = metadata.get("finalizers", [])
    need(isinstance(finalizers, list) and all(isinstance(f, str) and FINALIZER.fullmatch(f) for f in finalizers),
         "response_finalizers_invalid")
    deletion = metadata.get("deletionTimestamp")
    need(deletion is None or isinstance(deletion, str), "response_shape")
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
             and all(isinstance(v, str) and VERSION.fullmatch(v) for v in document["versions"]), "discovery_invalid")
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
             and all(isinstance(v, str) for v in resource["verbs"]) and resource["name"] not in seen,
             "discovery_invalid")
        seen.add(resource["name"])
        resources.append({"name": resource["name"], "namespaced": resource["namespaced"],
                          "verbs": sorted(set(resource["verbs"]))})
    return {"resources": resources}


def discovery_targets(core, groups, resource_lists):
    """Every namespaced, listable resource of every advertised group version, or UNKNOWN with a reason.

    Every advertised version is examined, not only the preferred one; a group version without its resource list,
    a malformed resource name or a namespaced resource without list (outside the virtual allowlist) is UNKNOWN.
    """
    if "v1" not in core["versions"]:
        return {"status": "UNKNOWN", "reason": "discovery_core_missing"}
    advertised = [("", "v1")] + [(g["name"], v) for g in groups["groups"] for v in g["versions"]]
    targets = []
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
            if not resource["namespaced"]:
                continue
            if "list" in resource["verbs"]:
                targets.append((group, version, name))
            elif (group, name) not in VIRTUAL_RESOURCES:
                return {"status": "UNKNOWN", "reason": "resource_not_listable"}
    return {"status": "COMPLETE", "targets": sorted(targets)}


# ---- metadata LIST and pagination ---------------------------------------------------------------------------------

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
         and isinstance(meta.get("resourceVersion"), str) and isinstance(items, list), "response_shape")
    token = meta.get("continue", "")
    need(isinstance(token, str) and (token == "" or CONTINUE_TOKEN.fullmatch(token) is not None),
         "continue_token_invalid")
    need(len(items) <= limit, "list_over_limit")
    result, uids, names = [], set(), set()
    for item in items:
        need(isinstance(item, dict), "response_shape")
        need(not (FORBIDDEN_RESPONSE_KEYS & set(item)), "response_not_metadata_only")
        need(set(item) <= {"kind", "apiVersion", "metadata"} and item.get("kind", "PartialObjectMetadata")
             == "PartialObjectMetadata", "response_shape")
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
        need(uid not in uids and (item_namespace, name) not in names, "list_duplicate_item")
        uids.add(uid)
        names.add((item_namespace, name))
        owners = metadata.get("ownerReferences", [])
        need(isinstance(owners, list), "response_shape")
        minimal_owners = []
        for owner in owners:
            need(isinstance(owner, dict) and isinstance(owner.get("uid"), str) and UID.fullmatch(owner["uid"])
                 and isinstance(owner.get("kind"), str) and isinstance(owner.get("name"), str)
                 and owner.get("controller", False) in (True, False), "response_owner_invalid")
            minimal_owners.append({"kind": owner["kind"], "name": owner["name"], "uid": owner["uid"],
                                   "controller": owner.get("controller", False) is True})
        state = object_state(dict(metadata, uid=uid))
        result.append({"name": name, "namespace": item_namespace, "uid": uid, "owners": minimal_owners,
                       "deletion_requested": state["deletion_requested"], "finalizers": state["finalizers"]})
    return {"items": result, "continue": token or None, "resource_version": meta["resourceVersion"]}


def collect_list(fetch_page, deadline=None):
    """One logical LIST, page by page, within the D11 bounds; COMPLETE only when the last page has no token.

    410 restarts the list from the beginning (the partial result is discarded) at most LIST_RESTART_LIMIT times;
    all pages, restarts included, count against LIST_PAGE_LIMIT. A repeated token, a snapshot change, a duplicate
    item, a timeout or an invalid page is UNKNOWN; 403 is BLOCKED. Never an empty success.
    """
    pages, restarts = 0, 0
    while restarts <= LIST_RESTART_LIMIT:
        items, uids, tokens, token, snapshot = [], set(), set(), None, None
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
                uids.add(item["uid"])
                items.append(item)
            token = page["continue"]
            if token is None:
                return {"status": "COMPLETE", "items": items, "pages": pages, "restarts": restarts}
            if token in tokens:
                return {"status": "UNKNOWN", "reason": "list_continue_repeated"}
            tokens.add(token)
        restarts += 1
    return {"status": "UNKNOWN", "reason": "list_restart_limit"}


def merge_listed(listed):
    """Merge COMPLETE lists of every discovered (group, version, resource) of one namespace by UID.

    The same UID may appear under several versions of one resource, or under the two event resources, always with
    the same name and namespace; any other repetition is an unknown mapping (UNKNOWN). No classification here.
    """
    merged = {}
    for (group, version, resource), result in sorted(listed.items()):
        if result.get("status") != "COMPLETE":
            return {"status": result.get("status", "UNKNOWN"), "reason": result.get("reason", "list_incomplete")}
        for item in result["items"]:
            seen = merged.get(item["uid"])
            if seen is None:
                merged[item["uid"]] = {"resources": {(group, resource)}, "versions": {(group, version)},
                                       "name": item["name"], "namespace": item["namespace"], "item": item}
                continue
            same_resource = (group, resource) in seen["resources"]
            alias = any({(group, resource)} | seen["resources"] <= pair for pair in RESOURCE_ALIASES)
            if (seen["name"], seen["namespace"]) != (item["name"], item["namespace"]) or not (same_resource or alias):
                return {"status": "UNKNOWN", "reason": "unknown_resource_mapping"}
            seen["resources"].add((group, resource))
            seen["versions"].add((group, version))
    return {"status": "COMPLETE", "objects": [
        {"uid": uid, "name": m["name"], "namespace": m["namespace"], "resources": sorted(m["resources"]),
         "owners": m["item"]["owners"], "deletion_requested": m["item"]["deletion_requested"],
         "finalizers": m["item"]["finalizers"]} for uid, m in sorted(merged.items())]}


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
         and isinstance(crd_status, dict), "crd_response_invalid")
    versions = spec["versions"]
    need(all(isinstance(v, dict) and isinstance(v.get("name"), str) and isinstance(v.get("served"), bool)
             and isinstance(v.get("storage"), bool) for v in versions), "crd_response_invalid")
    storage = [v["name"] for v in versions if v["storage"]]
    conditions = crd_status.get("conditions", [])
    need(isinstance(conditions, list) and all(isinstance(c, dict) for c in conditions), "crd_response_invalid")
    established = any(c.get("type") == "Established" and c.get("status") == "True" for c in conditions)
    return {"name": name, "uid": metadata["uid"], "group": spec.get("group"), "plural": spec["names"].get("plural"),
            "scope": spec.get("scope"), "storage_versions": storage,
            "served_versions": sorted(v["name"] for v in versions if v["served"]), "established": established}


def verify_crd(policy, name, info, receipt_uid):
    """VERIFIED only when the live CRD is the reviewed one: UID, group, plural, scope, storage version served,
    Established. A 200 on a later LIST is never evidence of any of these."""
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
    owns, or None. ``open_intent``: an unresolved apply INTENT for it. ``advertised``: whether discovery serves its
    (group, plural), or None when discovery is not COMPLETE. CRD_NOT_CREATED needs no creation evidence, no open
    INTENT, a trusted NotFound and a discovery that does not serve the plural. A claimed CRD that is gone, another
    UID and a foreign CRD (present, not claimed) are BLOCKED: never deleted, never adopted.
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
    """Offline double for the destroy contracts: every request is built by a builder and checked before sending."""

    def __init__(self, policy, server):
        self.policy = policy
        self.server = server
        self.requests = []

    def send(self, request):
        check_request(request)
        self.requests.append(request)
        return self.server(request)

    def get_metadata(self, identity):
        status, body = self.send(destroy_metadata_request(self.policy, identity))
        return validate_destroy_metadata(identity, status, body)

    def discover(self, path):
        status, body = self.send(discovery_request(self.policy, path))
        return validate_discovery_response(path, status, body)

    def list_namespace(self, namespace, group, version, resource, deadline=None):
        def page(token):
            status, body = self.send(namespace_list_request(self.policy, namespace, group, version, resource, token))
            return validate_list_response(namespace, LIST_PAGE_SIZE, status, body)
        return collect_list(page, deadline)

    def read_crd(self, name):
        status, body = self.send(crd_read_request(self.policy, name))
        return validate_crd_response(name, status, body)

    def crd_instances(self, name, verified):
        try:
            status, body = self.send(crd_instance_list_request(self.policy, name, verified))
        except TimeoutError:
            return {"verdict": "UNKNOWN", "reason": "transport_timeout"}
        return classify_crd_instances(status, body)

    def read_service_type(self, identity):
        status, body = self.send(service_type_request(self.policy, identity))
        return validate_service_type_response(identity, status, body)

    def delete_runtime(self, identity, uid):
        status, _ = self.send(runtime_delete_request(self.policy, identity, uid))
        return validate_runtime_delete_response(status)


def open_destroy_transport(kind, policy=None, server=None):
    """Only the offline fake; any real destroy transport is refused."""
    need(APPROVED_TRANSPORTS.__contains__(kind), "real_transport_not_implemented")
    need(isinstance(policy, DestroyPolicy) and callable(server), "fake_transport_needs_policy_and_server")
    return FakeDestroyTransport(policy, server)
