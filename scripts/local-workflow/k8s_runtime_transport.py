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
