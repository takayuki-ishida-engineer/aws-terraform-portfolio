#!/usr/bin/env python3
"""Offline tests for the 6c-B4a Fake-only destroy safety foundation.

Covers the destroy contracts of ``k8s_runtime_transport`` (separate read, discovery, LIST, specialised CRD and
Service read and runtime DELETE scopes; strict response validation; bounded pagination; the D11 deadline) and the
destroy phase of ``k8s_runtime_receipt`` (DESTROY_BEGIN, DESTROY_INTENT, DESTROY_RESULT, DESTROY_STAGE_DONE,
reconciliation after a crash, backward compatibility of apply-only journals), plus the apply engine's refusal
to resume on a destroy-phase journal. There is no destroy engine: nothing here orchestrates deletions.

A fake API answers each request. Every receipt lives in a temporary directory outside the repository. Synthetic
receipts stand in for apply evidence that the fake apply engine cannot reach (it stops before the gateway).

``DESTROY_MUTATIONS`` removes one guard at a time. A mutation counts as detected only when its scenario fails an
assertion; a crash is reported as undetected. These tests run inside the ``k8s_runtime_receipt_tests`` suite.
"""
import contextlib
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
import k8s_runtime_transport  # noqa: E402

PROJECT = "acme"
ARN = "arn:aws:eks:ca-central-1:444455556666:cluster/acme-dev-eks"
KUBE_SYSTEM_UID = "11111111-2222-4333-8444-555555555555"
SHA_A, SHA_B = "a" * 64, "b" * 64
MARKER = "B4A-SECRET-VALUE-MARKER-91c2"
TABLE = k8s_runtime.load_stage_table(PROJECT)
IDENTITIES = [dict(zip(("apiVersion", "kind", "namespace", "name"), row)) for _, rows in TABLE for row in rows]


def ident(kind, name, namespace=""):
    found = [i for i in IDENTITIES if i["kind"] == kind and i["name"] == name and i["namespace"] == namespace]
    assert len(found) == 1, (kind, name, namespace)
    return found[0]


DEPLOYMENT = ident("Deployment", "istiod-acme-v1", "istio-system")
NAMESPACE_INGRESS = ident("Namespace", "acme-ingress")
NAMESPACE_APP = ident("Namespace", "acme-app")
GATEWAY_SERVICE = ident("Service", "acme-gateway", "acme-ingress")
WEBHOOK_SERVICE = ident("Service", "aws-load-balancer-controller-webhook-service", "kube-system")
TGB = ident("TargetGroupBinding", "acme-gateway", "acme-ingress")
VALIDATOR = ident("ValidatingWebhookConfiguration", "istiod-default-validator")
CRD_NAME = "gateways.networking.istio.io"
CRD = ident("CustomResourceDefinition", CRD_NAME)
KUBE_SYSTEM = {"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "kube-system"}
SECRET = {"apiVersion": "v1", "kind": "Secret", "namespace": "acme-ingress", "name": "acme-gateway-tls"}


def uid(n):
    return "00000000-0000-4000-8000-%012x" % n


def key(identity):
    return k8s_runtime_transport.identity_key(identity)


class Mods(types.SimpleNamespace):
    """The modules under test; a mutation replaces one of them."""


def real_mods():
    return Mods(transport=k8s_runtime_transport, receipt=k8s_runtime_receipt, apply=k8s_runtime_apply)


def code_of(call, mods):
    """The fixed code of a refusal, or None; any other exception propagates (a crash is never a detection)."""
    try:
        call()
    except (mods.transport.TransportError, mods.receipt.ReceiptError, k8s_runtime_transport.TransportError,
            k8s_runtime_receipt.ReceiptError) as refused:
        return str(refused)
    return None


def crd_manifest(name, storage="v1", served=("v1",), scope="Namespaced"):
    plural, group = name.split(".", 1)
    versions = [{"name": v, "served": v in served, "storage": v == storage} for v in sorted(set(served) | {storage})]
    return {"apiVersion": "apiextensions.k8s.io/v1", "kind": "CustomResourceDefinition", "metadata": {"name": name},
            "spec": {"group": group, "names": {"plural": plural, "kind": "X"}, "scope": scope, "versions": versions}}


def spec_of(mods, name=CRD_NAME, **kwargs):
    return mods.transport.crd_spec_from_manifest(crd_manifest(name, **kwargs))[1]


def policy(mods, owned=None, **kwargs):
    return mods.transport.DestroyPolicy(PROJECT, IDENTITIES, owned_uids=owned, **kwargs)


def not_found(group, resource, name):
    details = {"name": name, "kind": resource}
    if group:
        details["group"] = group
    return 404, json.dumps({"kind": "Status", "apiVersion": "v1", "status": "Failure", "reason": "NotFound",
                            "code": 404, "details": details}).encode()


def item(name, namespace, uid_value, **metadata):
    return {"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
            "metadata": dict({"name": name, "namespace": namespace, "uid": uid_value}, **metadata)}


def page(items, rv="100", token=None, **extra):
    meta = {"resourceVersion": rv}
    if token is not None:
        meta["continue"] = token
    document = dict({"kind": "PartialObjectMetadataList", "apiVersion": "meta.k8s.io/v1", "metadata": meta,
                     "items": items}, **extra)
    return 200, json.dumps(document).encode()


class Pages:
    """A fake paged LIST: each call returns the next scripted answer (status, body) or raises it."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.tokens = []

    def __call__(self, token):
        self.tokens.append(token)
        answer = self.answers.pop(0) if self.answers else page([], token="next-%d" % len(self.tokens))
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer
        return k8s_runtime_transport.validate_list_response("acme-app", k8s_runtime_transport.LIST_PAGE_SIZE,
                                                            status, body)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t


def discovery_docs():
    core = {"kind": "APIVersions", "versions": ["v1"]}
    groups = {"kind": "APIGroupList", "apiVersion": "v1", "groups": [
        {"name": "apps", "versions": [{"groupVersion": "apps/v1", "version": "v1"}],
         "preferredVersion": {"groupVersion": "apps/v1", "version": "v1"}},
        {"name": "autoscaling", "versions": [{"groupVersion": "autoscaling/v2", "version": "v2"},
                                             {"groupVersion": "autoscaling/v1", "version": "v1"}],
         "preferredVersion": {"groupVersion": "autoscaling/v2", "version": "v2"}},
        {"name": "events.k8s.io", "versions": [{"groupVersion": "events.k8s.io/v1", "version": "v1"}]},
        {"name": "authorization.k8s.io", "versions": [{"groupVersion": "authorization.k8s.io/v1", "version": "v1"}]},
    ]}
    lists = {
        "v1": [{"name": "configmaps", "namespaced": True, "verbs": ["get", "list"]},
               {"name": "secrets", "namespaced": True, "verbs": ["get", "list"]},
               {"name": "events", "namespaced": True, "verbs": ["list"]},
               {"name": "bindings", "namespaced": True, "verbs": ["create"]},
               {"name": "pods/log", "namespaced": True, "verbs": ["get"]},
               {"name": "namespaces", "namespaced": False, "verbs": ["list"]}],
        "apps/v1": [{"name": "deployments", "namespaced": True, "verbs": ["list"]}],
        "autoscaling/v2": [{"name": "horizontalpodautoscalers", "namespaced": True, "verbs": ["list"]}],
        "autoscaling/v1": [{"name": "horizontalpodautoscalers", "namespaced": True, "verbs": ["list"]}],
        "events.k8s.io/v1": [{"name": "events", "namespaced": True, "verbs": ["list"]}],
        "authorization.k8s.io/v1": [{"name": "localsubjectaccessreviews", "namespaced": True, "verbs": ["create"]}],
    }
    return core, groups, lists


def resource_list(group_version, resources):
    return {"kind": "APIResourceList", "groupVersion": group_version, "resources": resources}


def validated_discovery(mods, core=None, groups=None, lists=None):
    t = mods.transport
    d_core, d_groups, d_lists = discovery_docs()
    core, groups, lists = core or d_core, groups or d_groups, d_lists if lists is None else lists
    v_core = t.validate_discovery_response("/api", 200, json.dumps(core).encode())
    v_groups = t.validate_discovery_response("/apis", 200, json.dumps(groups).encode())
    v_lists = {}
    for gv, resources in lists.items():
        path = "/api/v1" if gv == "v1" else "/apis/" + gv
        v_lists[gv] = t.validate_discovery_response(path, 200, json.dumps(resource_list(gv, resources)).encode())
    return v_core, v_groups, v_lists


# ---- transport: scopes and requests ---------------------------------------------------------------------------------

def scenario_policy_scopes(case, mods):
    t = mods.transport
    p = policy(mods, {key(DEPLOYMENT): uid(1), key(NAMESPACE_APP): uid(2)}, inventory=True, discovery=True,
               crd_specs={CRD_NAME: spec_of(mods)}, services=[GATEWAY_SERVICE])
    case.assertEqual(p.namespaces, frozenset({"istio-system", "acme-ingress", "acme-app"}))
    case.assertEqual(dict(p.delete), {key(DEPLOYMENT): uid(1), key(NAMESPACE_APP): uid(2)})
    case.assertEqual(p.services, frozenset({key(GATEWAY_SERVICE)}))
    case.assertIn(key(KUBE_SYSTEM), p.read)
    case.assertEqual(policy(mods).namespaces, frozenset(), "no LIST without the inventory scope")
    case.assertFalse(policy(mods).discovery)
    case.assertEqual(code_of(lambda: setattr(p, "delete", ()), mods), "policy_immutable")
    cases = [({key(CRD): uid(3)}, "crd_delete_refused"), ({key(KUBE_SYSTEM): uid(3)}, "kube_system_delete_refused"),
             ({key(SECRET): uid(3)}, "secret_delete_refused"),
             ({("v1", "ConfigMap", "acme-app", "unknown"): uid(3)}, "delete_not_in_plan"),
             ({key(DEPLOYMENT): "not-a-uid"}, "uid_invalid")]
    for owned, code in cases:
        case.assertEqual(code_of(lambda: policy(mods, owned), mods), code, code)
    case.assertEqual(code_of(lambda: t.DestroyPolicy(PROJECT, IDENTITIES + [SECRET]), mods), "secret_path_not_approved")
    for service in (WEBHOOK_SERVICE, ident("Service", "istiod-acme-v1", "istio-system")):
        case.assertEqual(code_of(lambda: policy(mods, services=[service]), mods), "service_read_not_approved")
    case.assertEqual(code_of(lambda: policy(mods, crd_specs={"other.example.com": spec_of(mods)}), mods),
                     "crd_not_reviewed")
    bad = dict(spec_of(mods), plural="sidecars")
    case.assertEqual(code_of(lambda: policy(mods, crd_specs={CRD_NAME: bad}), mods), "crd_spec_invalid")


def scenario_runtime_delete(case, mods):
    t = mods.transport
    p = policy(mods, {key(DEPLOYMENT): uid(1)})
    request = t.runtime_delete_request(p, DEPLOYMENT, uid(1))
    case.assertEqual(request["method"], "DELETE")
    case.assertEqual(json.loads(request["body"]), {"apiVersion": "v1", "kind": "DeleteOptions",
                                                   "preconditions": {"uid": uid(1)},
                                                   "propagationPolicy": "Background"})
    case.assertIsNone(code_of(lambda: t.check_request(request), mods))
    case.assertEqual(code_of(lambda: t.runtime_delete_request(p, DEPLOYMENT, uid(2)), mods), "delete_uid_not_proven")
    case.assertEqual(code_of(lambda: t.runtime_delete_request(p, VALIDATOR, uid(1)), mods), "delete_not_allowed")
    case.assertEqual(code_of(lambda: t.runtime_delete_request(p, CRD, uid(1)), mods), "crd_delete_refused")
    case.assertEqual(code_of(lambda: t.runtime_delete_request(p, KUBE_SYSTEM, uid(1)), mods),
                     "kube_system_delete_refused")
    case.assertEqual(code_of(lambda: t.runtime_delete_request(p, SECRET, uid(1)), mods), "secret_delete_refused")
    case.assertEqual(t.validate_runtime_delete_response(200), "REQUESTED")
    case.assertEqual(t.validate_runtime_delete_response(202), "REQUESTED")
    for status, code in ((409, "uid_precondition_failed"), (404, "not_found_at_delete"), (403, "forbidden"),
                         (500, "unexpected_status")):
        case.assertEqual(code_of(lambda: t.validate_runtime_delete_response(status), mods), code)


def delete_request(path, body=None, query=None):
    body = body if body is not None else {"apiVersion": "v1", "kind": "DeleteOptions",
                                          "preconditions": {"uid": uid(1)}, "propagationPolicy": "Background"}
    return {"method": "DELETE", "path": path, "query": query or {}, "headers": {},
            "body": body if isinstance(body, str) else json.dumps(body)}


def scenario_check_request(case, mods):
    t = mods.transport
    obj = "/apis/apps/v1/namespaces/istio-system/deployments/istiod-acme-v1"
    case.assertIsNone(code_of(lambda: t.check_request(delete_request(obj)), mods))
    options = {"apiVersion": "v1", "kind": "DeleteOptions", "preconditions": {"uid": uid(1)},
               "propagationPolicy": "Background"}
    refused = [
        (dict(delete_request(obj), method="PATCH"), "method_not_allowed"),
        (dict(delete_request(obj), method="POST"), "method_not_allowed"),
        (delete_request("/apis/apps/v1/namespaces/istio-system/deployments"), "path_not_allowed"),
        (delete_request("/api/v1/namespaces"), "path_not_allowed"),
        (delete_request(obj, query={"labelSelector": "a=b"}), "query_not_allowed"),
        (delete_request(obj, dict(options, gracePeriodSeconds=0)), "delete_options_invalid"),
        (delete_request(obj, dict(options, propagationPolicy="Orphan")), "delete_options_invalid"),
        (delete_request(obj, {k: v for k, v in options.items() if k != "preconditions"}), "delete_options_invalid"),
        (delete_request(obj, dict(options, preconditions={"uid": uid(1), "resourceVersion": "1"})),
         "delete_options_invalid"),
        (delete_request(obj + "?force=true"), "path_not_allowed"),
        ({"method": "GET", "path": "/healthz", "query": {}, "headers": {}, "body": None}, "path_not_allowed"),
        ({"method": "GET", "path": obj, "query": {"fieldSelector": "x"}, "headers": {}, "body": None},
         "query_not_allowed"),
        ({"method": "GET", "path": obj, "query": {"limit": "1000"}, "headers": {}, "body": None}, "query_not_allowed"),
        ({"method": "GET", "path": "/apis/../api", "query": {}, "headers": {}, "body": None}, "path_not_allowed"),
    ]
    for request, code in refused:
        case.assertEqual(code_of(lambda: t.check_request(request), mods), code, request)


def scenario_namespace_list_scope(case, mods):
    t = mods.transport
    p = policy(mods, inventory=True)
    request = t.namespace_list_request(p, "acme-app", "", "v1", "configmaps")
    case.assertEqual((request["path"], request["query"], request["headers"]["Accept"]),
                     ("/api/v1/namespaces/acme-app/configmaps", {"limit": "500"}, t.LIST_ACCEPT))
    case.assertEqual(t.namespace_list_request(p, "acme-ingress", "apps", "v1", "deployments", "abc")["query"],
                     {"limit": "500", "continue": "abc"})
    for namespace in ("kube-system", "default", "acme-other"):
        case.assertEqual(code_of(lambda: t.namespace_list_request(p, namespace, "", "v1", "secrets"), mods),
                         "namespace_not_approved", namespace)
    case.assertEqual(code_of(lambda: t.namespace_list_request(policy(mods), "acme-app", "", "v1", "pods"), mods),
                     "namespace_not_approved")
    case.assertEqual(code_of(lambda: t.namespace_list_request(p, "acme-app", "", "v1", "pods/log"), mods),
                     "list_resource_invalid")
    case.assertEqual(code_of(lambda: t.namespace_list_request(p, "acme-app", "Apps", "v1", "x"), mods),
                     "list_group_invalid")
    case.assertEqual(code_of(lambda: t.namespace_list_request(p, "acme-app", "", "v2", "x"), mods),
                     "list_version_invalid")
    case.assertEqual(code_of(lambda: t.namespace_list_request(p, "acme-app", "", "v1", "pods", "a b"), mods),
                     "continue_token_invalid")
    case.assertEqual(code_of(lambda: t.discovery_request(p, "/api"), mods), "discovery_not_allowed")
    d = policy(mods, discovery=True)
    for path in ("/api", "/apis", "/api/v1", "/apis/apps/v1"):
        case.assertEqual(t.discovery_request(d, path)["path"], path)
    for path in ("/apis/apps", "/apis/apps/v1/deployments", "/openapi/v2", "/api/v2"):
        case.assertEqual(code_of(lambda: t.discovery_request(d, path), mods), "discovery_path_not_allowed", path)


# ---- discovery ------------------------------------------------------------------------------------------------------

def scenario_discovery_targets(case, mods):
    t = mods.transport
    core, groups, lists = validated_discovery(mods)
    result = t.discovery_targets(core, groups, lists)
    case.assertEqual(result["status"], "COMPLETE")
    case.assertEqual(result["targets"], [
        ("", "v1", "configmaps"), ("", "v1", "events"), ("", "v1", "secrets"), ("apps", "v1", "deployments"),
        ("autoscaling", "v1", "horizontalpodautoscalers"), ("autoscaling", "v2", "horizontalpodautoscalers"),
        ("events.k8s.io", "v1", "events")])


def scenario_discovery_incomplete(case, mods):
    t = mods.transport
    core, groups, lists = validated_discovery(mods)
    without = dict(lists)
    del without["autoscaling/v1"]  # a non-preferred version: it still has to be read
    case.assertEqual(t.discovery_targets(core, groups, without), {"status": "UNKNOWN",
                                                                   "reason": "discovery_group_missing"})
    unlistable = dict(lists, **{"apps/v1": {"resources": [{"name": "deployments", "namespaced": True,
                                                            "verbs": ["get"]}]}})
    case.assertEqual(t.discovery_targets(core, groups, unlistable).get("reason"), "resource_not_listable")
    odd = dict(lists, **{"apps/v1": {"resources": [{"name": "Deployments", "namespaced": True, "verbs": ["list"]}]}})
    case.assertEqual(t.discovery_targets(core, groups, odd).get("reason"), "unknown_resource_mapping")
    case.assertEqual(t.discovery_targets({"versions": []}, groups, lists).get("reason"), "discovery_core_missing")


def scenario_discovery_validation(case, mods):
    t = mods.transport
    core, groups, _ = discovery_docs()
    bad = [("/api", dict(core, kind="APIGroupList")), ("/apis", dict(groups, kind="APIVersions")),
           ("/apis", dict(groups, groups=groups["groups"] + groups["groups"][:1])),
           ("/apis", dict(groups, groups=[{"name": "apps", "versions": [{"groupVersion": "other/v1",
                                                                         "version": "v1"}]}])),
           ("/apis/apps/v1", resource_list("apps/v2", [])),
           ("/apis/apps/v1", resource_list("apps/v1", [{"name": "d", "namespaced": True, "verbs": ["list"]}] * 2)),
           ("/apis/apps/v1", resource_list("apps/v1", [{"name": "d", "namespaced": "yes", "verbs": ["list"]}]))]
    for path, document in bad:
        case.assertEqual(code_of(lambda: t.validate_discovery_response(path, 200, json.dumps(document).encode()),
                                 mods), "discovery_invalid", (path, document))
    case.assertEqual(code_of(lambda: t.validate_discovery_response("/api", 403, b""), mods), "forbidden")
    case.assertEqual(code_of(lambda: t.validate_discovery_response("/api", 503, b""), mods), "unexpected_status")


# ---- LIST pages and pagination --------------------------------------------------------------------------------------

def scenario_list_page(case, mods):
    t = mods.transport
    owner = {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "rs", "uid": uid(9), "controller": True,
             "blockOwnerDeletion": True}
    managed = [{"manager": "kubectl", "operation": "Update", "fieldsType": "FieldsV1",
                "fieldsV1": {"f:data": {"f:tls.key": {}}, "f:stringData": {}}}]
    status, body = page([item("p", "acme-app", uid(1), ownerReferences=[owner], labels={"a": MARKER},
                              annotations={"note": MARKER}, managedFields=managed, finalizers=["x.io/y"],
                              deletionTimestamp="2026-11-24T00:00:00Z")], token="t1")
    result = t.validate_list_response("acme-app", 500, status, body)
    case.assertEqual(result["continue"], "t1")
    case.assertEqual(result["items"], [{"name": "p", "namespace": "acme-app", "uid": uid(1),
                                        "owners": [{"kind": "ReplicaSet", "name": "rs", "uid": uid(9),
                                                    "controller": True}],
                                        "deletion_requested": True, "finalizers": ["x.io/y"]}])
    case.assertNotIn(MARKER, json.dumps(result), "labels and annotations are never returned")
    case.assertIsNone(t.validate_list_response("acme-app", 500, *page([], token=""))["continue"])


def scenario_list_page_refusals(case, mods):
    t = mods.transport
    good = item("p", "acme-app", uid(1))
    refused = [
        (page([item("p", "other", uid(1))]), "response_namespace_mismatch"),
        (page([dict(good, data={"k": MARKER})]), "response_not_metadata_only"),
        (page([dict(good, stringData={"k": MARKER})]), "response_not_metadata_only"),
        (page([dict(good, binaryData={"k": MARKER})]), "response_not_metadata_only"),
        (page([item("s", "acme-app", uid(1), annotations={
            "kubectl.kubernetes.io/last-applied-configuration": MARKER})]), "response_secret_annotation_refused"),
        (page([good], extra="x"), "response_shape"),
        ((200, json.dumps({"kind": "SecretList", "apiVersion": "v1", "metadata": {"resourceVersion": "1"},
                           "items": []}).encode()), "response_not_partial_object_metadata_list"),
        (page([item("p", "acme-app", "bad")]), "response_uid_invalid"),
        (page([good, item("q", "acme-app", uid(1))]), "list_duplicate_item"),
        (page([good, item("p", "acme-app", uid(2))]), "list_duplicate_item"),
        (page([good], token="bad token"), "continue_token_invalid"),
        (page([item("p", "acme-app", uid(1), ownerReferences=[{"kind": "X", "name": "x", "uid": "bad"}])]),
         "response_owner_invalid"),
        (page([item("p", "acme-app", uid(1), finalizers=["Not Valid"])]), "response_finalizers_invalid"),
        ((403, b""), "forbidden"), ((410, b""), "list_expired"), ((500, b""), "unexpected_status"),
        ((200, b"{nope"), "response_not_json"),
    ]
    for (status, body), code in refused:
        result = code_of(lambda: t.validate_list_response("acme-app", 500, status, body), mods)
        case.assertEqual(result, code, code)
        case.assertNotIn(MARKER, str(result))
    case.assertEqual(code_of(lambda: t.validate_list_response("acme-app", 1, *page([good, item("q", "acme-app",
                                                                                                 uid(2))])), mods),
                     "list_over_limit")


def scenario_pagination(case, mods):
    t = mods.transport
    pages = Pages([page([item("a", "acme-app", uid(1))], token="t1"), page([item("b", "acme-app", uid(2))],
                                                                           token="t2"),
                   page([item("c", "acme-app", uid(3))], token="")])
    result = t.collect_list(pages)
    case.assertEqual((result["status"], [i["name"] for i in result["items"]], result["pages"]),
                     ("COMPLETE", ["a", "b", "c"], 3))
    case.assertEqual(pages.tokens, [None, "t1", "t2"])
    case.assertEqual(t.collect_list(Pages([page([])]))["status"], "COMPLETE", "no continue key at all is final")


def scenario_pagination_failures(case, mods):
    t = mods.transport
    cases = [
        ([page([item("a", "acme-app", uid(1))], token="t1"), page([item("b", "acme-app", uid(2))], token="t1")],
         "UNKNOWN", "list_continue_repeated"),
        ([page([item("a", "acme-app", uid(1))], token="t1"), page([item("b", "acme-app", uid(2))], rv="101")],
         "UNKNOWN", "list_snapshot_inconsistent"),
        ([page([item("a", "acme-app", uid(1))], token="t1"), page([item("b", "acme-app", uid(1))])],
         "UNKNOWN", "list_duplicate_item"),
        ([(403, b"")], "BLOCKED", "inventory_forbidden"),
        ([(404, b"")], "UNKNOWN", "unexpected_status"),
        ([(503, b"")], "UNKNOWN", "unexpected_status"),
        ([TimeoutError("slow")], "UNKNOWN", "transport_timeout"),
        ([ConnectionResetError("reset")], "UNKNOWN", "transport_unknown"),
        ([page([item("a", "acme-app", uid(1))], token="t1"), (200, b"{bad")], "UNKNOWN", "response_not_json"),
    ]
    for answers, status, reason in cases:
        result = t.collect_list(Pages(answers))
        case.assertEqual((result["status"], result.get("reason")), (status, reason), reason)
        case.assertNotIn("items", result, "a partial list is never returned")


def scenario_pagination_restart(case, mods):
    t = mods.transport
    pages = Pages([page([item("old", "acme-app", uid(1))], token="t1"), (410, b""),
                   page([item("a", "acme-app", uid(2))], token="t9"), page([item("b", "acme-app", uid(3))])])
    result = t.collect_list(pages)
    case.assertEqual((result["status"], result.get("restarts"), [i["name"] for i in result.get("items", [])]),
                     ("COMPLETE", 1, ["a", "b"]), "the partial list before the 410 is discarded")
    case.assertEqual(pages.tokens, [None, "t1", None, "t9"])
    limited = t.collect_list(Pages([(410, b""), (410, b""), (410, b""), page([])]))
    case.assertEqual((limited["status"], limited.get("reason")), ("UNKNOWN", "list_restart_limit"))
    twice = t.collect_list(Pages([(410, b""), (410, b""), page([item("a", "acme-app", uid(1))])]))
    case.assertEqual((twice["status"], twice.get("restarts")), ("COMPLETE", 2))


def scenario_pagination_bounds(case, mods):
    t = mods.transport
    endless = Pages([])  # every page carries a new token
    result = t.collect_list(endless)
    case.assertEqual((result["status"], result.get("reason"), len(endless.tokens)), ("UNKNOWN", "list_page_limit", 100))
    restarts = Pages([page([], token="r%d" % i) for i in range(60)] + [(410, b"")]
                     + [page([], token="s%d" % i) for i in range(60)])
    limited = t.collect_list(restarts)
    case.assertEqual((limited.get("reason"), len(restarts.tokens)), ("list_page_limit", 100), "restarts count too")
    clock = Clock()
    deadline = t.Deadline(clock)
    clock.t += t.DESTROY_DEADLINE_SECONDS
    silent = Pages([page([])])
    case.assertEqual(t.collect_list(silent, deadline), {"status": "UNKNOWN", "reason": "deadline_exceeded"})
    case.assertEqual(silent.tokens, [], "nothing is sent after the deadline")


def scenario_deadline(case, mods):
    t = mods.transport
    clock = Clock()
    deadline = t.Deadline(clock)
    case.assertEqual(deadline.remaining(), 3600)
    clock.t += 3599
    case.assertFalse(deadline.expired())
    clock.t += 1
    case.assertTrue(deadline.expired())
    case.assertEqual(code_of(lambda: setattr(deadline, "_end", 10 ** 9), mods), "deadline_immutable")
    case.assertTrue(deadline.expired(), "it cannot be extended")
    case.assertEqual(code_of(lambda: t.Deadline(clock, 3601), mods), "deadline_invalid")
    case.assertEqual(code_of(lambda: t.Deadline(clock, 0), mods), "deadline_invalid")
    case.assertFalse(any(hasattr(deadline, n) for n in ("reset", "extend", "restart")))
    values = (t.API_READ_TIMEOUT_SECONDS, t.DELETE_REQUEST_TIMEOUT_SECONDS, t.DELETE_CONFIRM_TIMEOUT_SECONDS,
              t.TGB_FINALIZER_TIMEOUT_SECONDS, t.OWNED_CHILD_TIMEOUT_SECONDS, t.NAMESPACE_TERMINATION_TIMEOUT_SECONDS,
              t.DESTROY_POLL_SECONDS, t.LIST_PAGE_SIZE, t.LIST_PAGE_LIMIT, t.LIST_RESTART_LIMIT,
              t.DESTROY_DEADLINE_SECONDS)
    case.assertEqual(values, (20, 20, 20, 600, 600, 600, 5, 500, 100, 2, 3600))


def scenario_merge_listed(case, mods):
    t = mods.transport

    def complete(*items):
        return {"status": "COMPLETE", "items": [{"name": n, "namespace": "acme-app", "uid": u, "owners": [],
                                                 "deletion_requested": False, "finalizers": []} for n, u in items]}
    listed = {("autoscaling", "v1", "horizontalpodautoscalers"): complete(("h", uid(1))),
              ("autoscaling", "v2", "horizontalpodautoscalers"): complete(("h", uid(1))),
              ("", "v1", "events"): complete(("e", uid(2))), ("events.k8s.io", "v1", "events"): complete(("e", uid(2)))}
    merged = t.merge_listed(listed)
    case.assertEqual(merged["status"], "COMPLETE")
    case.assertEqual([(o["name"], o["resources"]) for o in merged["objects"]],
                     [("h", [("autoscaling", "horizontalpodautoscalers")]),
                      ("e", [("", "events"), ("events.k8s.io", "events")])])
    renamed = {**listed, ("autoscaling", "v2", "horizontalpodautoscalers"): complete(("other", uid(1)))}
    case.assertEqual(t.merge_listed(renamed).get("reason"), "unknown_resource_mapping")
    crossed = {**listed, ("", "v1", "configmaps"): complete(("h", uid(1)))}
    case.assertEqual(t.merge_listed(crossed).get("reason"), "unknown_resource_mapping")
    partial = {**listed, ("", "v1", "secrets"): {"status": "UNKNOWN", "reason": "transport_timeout"}}
    case.assertEqual(t.merge_listed(partial), {"status": "UNKNOWN", "reason": "transport_timeout"})


# ---- specialised CRD and Service reads ------------------------------------------------------------------------------

def crd_body(name=CRD_NAME, uid_value=uid(5), storage="v1", served=("v1",), scope="Namespaced", established=True,
             group=None):
    manifest = crd_manifest(name, storage, served, scope)
    manifest["metadata"].update(uid=uid_value, annotations={"note": MARKER})
    if group:
        manifest["spec"]["group"] = group
    for version in manifest["spec"]["versions"]:
        version["schema"] = {"openAPIV3Schema": {"description": MARKER}}
    manifest["status"] = {"conditions": [{"type": "Established", "status": "True" if established else "False"}],
                          "storedVersions": [storage]}
    return 200, json.dumps(manifest).encode()


def scenario_crd_read(case, mods):
    t = mods.transport
    p = policy(mods, crd_specs={CRD_NAME: spec_of(mods)})
    request = t.crd_read_request(p, CRD_NAME)
    case.assertEqual(request["path"], "/apis/apiextensions.k8s.io/v1/customresourcedefinitions/" + CRD_NAME)
    info = t.validate_crd_response(CRD_NAME, *crd_body())
    case.assertEqual(set(info), {"name", "uid", "group", "plural", "scope", "storage_versions", "served_versions",
                                 "established"})
    case.assertNotIn(MARKER, json.dumps(info), "no annotation or schema leaves the module")
    verdict = t.verify_crd(p, CRD_NAME, info, uid(5))
    case.assertEqual(verdict, {"verdict": "VERIFIED", "name": CRD_NAME, "storage_version": "v1", "reason": None})
    case.assertEqual(code_of(lambda: t.crd_read_request(p, "sidecars.networking.istio.io"), mods),
                     "crd_not_reviewed")
    case.assertEqual(code_of(lambda: t.crd_read_request(policy(mods), CRD_NAME), mods), "crd_not_reviewed")
    list_request = t.crd_instance_list_request(p, CRD_NAME, verdict)
    case.assertEqual((list_request["path"], list_request["query"], list_request["headers"]["Accept"]),
                     ("/apis/networking.istio.io/v1/gateways", {"limit": "1"}, t.LIST_ACCEPT))
    for verified in (None, {"verdict": "BLOCKED", "name": CRD_NAME, "storage_version": "v1"},
                     dict(verdict, storage_version="v1beta1"), dict(verdict, name="other")):
        case.assertEqual(code_of(lambda: t.crd_instance_list_request(p, CRD_NAME, verified), mods),
                         "crd_not_verified")


def scenario_crd_mismatches(case, mods):
    t = mods.transport
    p = policy(mods, crd_specs={CRD_NAME: spec_of(mods)})
    cases = [(crd_body(uid_value=uid(6)), "crd_uid_mismatch"), (crd_body(group="networking.example.io"),
                                                                "crd_group_mismatch"),
             (crd_body(scope="Cluster"), "crd_scope_mismatch"), (crd_body(storage="v1beta1", served=("v1", "v1beta1")),
                                                                 "crd_storage_version_mismatch"),
             (crd_body(served=("v1beta1",)), "crd_storage_not_served"), (crd_body(established=False),
                                                                        "crd_not_established")]
    for (status, body), reason in cases:
        info = t.validate_crd_response(CRD_NAME, status, body)
        case.assertEqual(t.verify_crd(p, CRD_NAME, info, uid(5)), {"verdict": "BLOCKED", "name": CRD_NAME,
                                                                   "reason": reason}, reason)
    plural = t.validate_crd_response(CRD_NAME, *crd_body())
    plural["plural"] = "sidecars"
    case.assertEqual(t.verify_crd(p, CRD_NAME, plural, uid(5))["reason"], "crd_plural_mismatch")
    case.assertIsNone(t.validate_crd_response(CRD_NAME, *not_found("apiextensions.k8s.io",
                                                                   "customresourcedefinitions", CRD_NAME)))
    for status, body in ((404, b"404 page not found"), not_found("apiextensions.k8s.io", "customresourcedefinitions",
                                                                 "other"), not_found("", "customresourcedefinitions",
                                                                                     CRD_NAME)):
        case.assertEqual(code_of(lambda: t.validate_crd_response(CRD_NAME, status, body), mods),
                         "not_found_untrusted")
    case.assertEqual(code_of(lambda: t.validate_crd_response("other.networking.istio.io", *crd_body()), mods),
                     "response_identity_mismatch")
    case.assertEqual(code_of(lambda: t.crd_spec_from_manifest({"metadata": {}}), mods), "crd_manifest_invalid")


def scenario_crd_classification(case, mods):
    t = mods.transport
    p = policy(mods, crd_specs={CRD_NAME: spec_of(mods)})
    info = t.validate_crd_response(CRD_NAME, *crd_body())
    cases = [
        (("present", info), uid(5), False, True, "VERIFIED", None),
        (("present", info), None, False, True, "BLOCKED", "foreign_crd"),
        (("absent", None), uid(5), False, False, "BLOCKED", "crd_claimed_but_absent"),
        (("absent", None), None, True, False, "UNKNOWN", "crd_open_intent"),
        (("absent", None), None, False, None, "UNKNOWN", "discovery_incomplete"),
        (("absent", None), None, False, True, "UNKNOWN", "crd_discovery_inconsistent"),
        (("absent", None), None, False, False, "CRD_NOT_CREATED", None),
        (("unknown", "forbidden"), uid(5), False, True, "UNKNOWN", "forbidden"),
    ]
    for read, claim, intent, advertised, verdict, reason in cases:
        result = t.classify_crd(p, CRD_NAME, read, claim, intent, advertised)
        case.assertEqual((result["verdict"], result["reason"]), (verdict, reason), (verdict, reason))


def scenario_crd_instances(case, mods):
    t = mods.transport
    cases = [(page([]), "ZERO_INSTANCES", None), (page([], token=""), "ZERO_INSTANCES", None),
             (page([item("g", "acme-app", uid(1))]), "BLOCKED", "crd_instances_remain"),
             (page([], token="more"), "UNKNOWN", "crd_list_inconsistent"),
             ((403, b""), "BLOCKED", "crd_list_forbidden"), ((404, b""), "UNKNOWN", "unexpected_status"),
             ((500, b""), "UNKNOWN", "unexpected_status"), ((200, b"[]"), "UNKNOWN", "response_shape"),
             (page([dict(item("g", "acme-app", uid(1)), spec={})]), "UNKNOWN", "response_not_metadata_only")]
    for (status, body), verdict, reason in cases:
        case.assertEqual(t.classify_crd_instances(status, body), {"verdict": verdict, "reason": reason}, reason)
    case.assertNotEqual("CRD_NOT_CREATED", t.classify_crd_instances(*page([]))["verdict"],
                        "never reported as the same evidence")


def service_body(type_="ClusterIP", name="acme-gateway", namespace="acme-ingress"):
    return 200, json.dumps({"kind": "Service", "apiVersion": "v1",
                            "metadata": {"name": name, "namespace": namespace, "uid": uid(7),
                                         "annotations": {"note": MARKER}},
                            "spec": {"type": type_, "ports": [{"port": 443}], "selector": {"x": MARKER}}}).encode()


def scenario_service_type(case, mods):
    t = mods.transport
    p = policy(mods, services=[GATEWAY_SERVICE])
    request = t.service_type_request(p, GATEWAY_SERVICE)
    case.assertEqual(request["path"], "/api/v1/namespaces/acme-ingress/services/acme-gateway")
    info = t.validate_service_type_response(GATEWAY_SERVICE, *service_body())
    case.assertEqual(info, {"uid": uid(7), "type": "ClusterIP", "load_balancer": False})
    case.assertNotIn(MARKER, json.dumps(info))
    case.assertTrue(t.validate_service_type_response(GATEWAY_SERVICE, *service_body("LoadBalancer"))["load_balancer"])
    case.assertEqual(code_of(lambda: t.service_type_request(p, WEBHOOK_SERVICE), mods), "service_read_not_approved")
    case.assertEqual(code_of(lambda: t.service_type_request(policy(mods), GATEWAY_SERVICE), mods),
                     "service_read_not_approved")
    case.assertEqual(code_of(lambda: t.validate_service_type_response(GATEWAY_SERVICE, *service_body("Weird")), mods),
                     "service_type_invalid")
    case.assertEqual(code_of(lambda: t.validate_service_type_response(GATEWAY_SERVICE, *service_body(name="x")),
                             mods), "response_identity_mismatch")
    case.assertIsNone(t.validate_service_type_response(GATEWAY_SERVICE, *not_found("", "services", "acme-gateway")))
    case.assertEqual(code_of(lambda: t.validate_service_type_response(GATEWAY_SERVICE, 404, b""), mods),
                     "not_found_untrusted")


def scenario_metadata_and_absence(case, mods):
    t = mods.transport
    p = policy(mods)
    request = t.destroy_metadata_request(p, TGB)
    case.assertEqual(request["headers"], {"Accept": t.METADATA_ACCEPT})
    case.assertEqual(code_of(lambda: t.destroy_metadata_request(p, SECRET), mods), "identity_not_allowed")
    case.assertEqual(code_of(lambda: t.destroy_metadata_request(p, dict(TGB, name="foreign")), mods),
                     "identity_not_allowed")
    case.assertIsNone(t.validate_destroy_metadata(TGB, *not_found("elbv2.k8s.aws", "targetgroupbindings",
                                                                  "acme-gateway")))
    for status, body in ((404, b"404 page not found"), not_found("elbv2.k8s.aws", "targetgroupbindings", "other"),
                         not_found("", "targetgroupbindings", "acme-gateway"),
                         not_found("elbv2.k8s.aws", "services", "acme-gateway")):
        case.assertEqual(code_of(lambda: t.validate_destroy_metadata(TGB, status, body), mods), "not_found_untrusted")
    body = json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                       "metadata": {"name": "acme-gateway", "namespace": "acme-ingress", "uid": uid(8),
                                    "finalizers": ["elbv2.k8s.aws/resources"],
                                    "deletionTimestamp": "2026-11-24T00:00:00Z"}}).encode()
    state = t.object_state(t.validate_destroy_metadata(TGB, 200, body))
    case.assertEqual(state, {"uid": uid(8), "deletion_requested": True, "finalizers": ["elbv2.k8s.aws/resources"]})


class FakeApi:
    """A fake API server for the destroy transport: object metadata, CRDs, Services, discovery and LIST pages."""

    def __init__(self):
        self.objects = {}
        self.answers = {}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        key_ = (request["method"], request["path"], request["query"].get("continue"))
        if key_ in self.answers:
            return self.answers[key_]
        if request["path"] in self.objects:
            return 200, self.objects[request["path"]]
        return 404, b"404 page not found"


def scenario_fake_transport(case, mods):
    t = mods.transport
    p = policy(mods, {key(TGB): uid(8)}, inventory=True, discovery=True, crd_specs={CRD_NAME: spec_of(mods)},
               services=[GATEWAY_SERVICE])
    api = FakeApi()
    fake = t.open_destroy_transport("fake", p, api)
    api.answers[("DELETE", "/apis/elbv2.k8s.aws/v1beta1/namespaces/acme-ingress/targetgroupbindings/acme-gateway",
                 None)] = (202, b"")
    case.assertEqual(fake.delete_runtime(TGB, uid(8)), "REQUESTED")
    api.answers[("GET", "/apis/elbv2.k8s.aws/v1beta1/namespaces/acme-ingress/targetgroupbindings/acme-gateway",
                 None)] = not_found("elbv2.k8s.aws", "targetgroupbindings", "acme-gateway")
    case.assertIsNone(fake.get_metadata(TGB))
    api.answers[("GET", "/api/v1/namespaces/acme-app/configmaps", None)] = page([item("x", "acme-app", uid(1))],
                                                                                token="c1")
    api.answers[("GET", "/api/v1/namespaces/acme-app/configmaps", "c1")] = page([item("y", "acme-app", uid(2))])
    listed = fake.list_namespace("acme-app", "", "v1", "configmaps")
    case.assertEqual((listed["status"], [i["name"] for i in listed["items"]]), ("COMPLETE", ["x", "y"]))
    api.answers[("GET", "/apis/apiextensions.k8s.io/v1/customresourcedefinitions/" + CRD_NAME, None)] = crd_body()
    verdict = t.verify_crd(p, CRD_NAME, fake.read_crd(CRD_NAME), uid(5))
    api.answers[("GET", "/apis/networking.istio.io/v1/gateways", None)] = page([])
    case.assertEqual(fake.crd_instances(CRD_NAME, verdict), {"verdict": "ZERO_INSTANCES", "reason": None})
    api.answers[("GET", "/api/v1/namespaces/acme-ingress/services/acme-gateway", None)] = service_body()
    case.assertEqual(fake.read_service_type(GATEWAY_SERVICE)["type"], "ClusterIP")
    api.answers[("GET", "/apis", None)] = (200, json.dumps(discovery_docs()[1]).encode())
    case.assertEqual(len(fake.discover("/apis")["groups"]), 4)
    sent = len(api.requests)
    case.assertEqual(code_of(lambda: fake.send({"method": "PATCH", "path": "/api/v1/namespaces/acme-app",
                                                "query": {}, "headers": {}, "body": "{}"}), mods),
                     "method_not_allowed")
    case.assertEqual(len(api.requests), sent, "a refused request never reaches the server")
    case.assertEqual(code_of(lambda: fake.delete_runtime(DEPLOYMENT, uid(1)), mods), "delete_not_allowed")


def scenario_real_refused(case, mods):
    t = mods.transport
    p = policy(mods)
    for kind in ("https", "kubectl", "real"):
        case.assertEqual(code_of(lambda: t.open_destroy_transport(kind, p, lambda r: (404, b"")), mods),
                         "real_transport_not_implemented")
    case.assertEqual(code_of(lambda: t.open_destroy_transport("fake", t.Policy([DEPLOYMENT]), lambda r: (404, b"")),
                             mods), "fake_transport_needs_policy_and_server")
    case.assertEqual(code_of(lambda: t.HttpsTransport(p), mods), "real_transport_not_implemented")
    case.assertEqual(k8s_runtime.APPROVED_OPERATIONS, ("plan", "status", "receipt-verify"))
    case.assertEqual(_gate_code(lambda: k8s_runtime.check_operation("destroy")), "operation_not_approved:destroy")


def _gate_code(call):
    try:
        call()
    except k8s_runtime.GateError as error:
        return str(error)
    return None


# ---- receipt / journal ----------------------------------------------------------------------------------------------

def plan_of(module):
    return module.Plan([(name, [dict(zip(("apiVersion", "kind", "namespace", "name"), row)) for row in rows])
                        for name, rows in TABLE])


class Env:
    def __init__(self, mods):
        self.mods = mods
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-destroy-"))
        os.chmod(self.tmp, 0o700)
        self.plan = plan_of(mods.receipt)
        self.fp = mods.receipt.fingerprint(ARN, KUBE_SYSTEM_UID)
        self.expected = {"fingerprint": self.fp, "project": PROJECT, "manifest_sha256": SHA_A, "input_sha256": SHA_B}
        self.store = mods.receipt.Store(self.tmp / "state", self.fp, PROJECT, SHA_A, SHA_B, self.plan)
        self.counter = 100
        self.uids = {}

    def members(self, stage):
        return [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|"))) for k in self.plan.members[stage]]

    def apply(self, stages):
        """Synthetic apply evidence (the fake apply engine stops before the gateway)."""
        with self.store.lock():
            self.store.begin()
            for stage in stages:
                for identity in self.members(stage):
                    self.counter += 1
                    seq = self.store.intent(stage, identity, {"state": "absent"}, "create")
                    self.store.result(seq, identity, uid(self.counter), "100", 1, "applied")
                    self.uids[self.mods.receipt.key_of(identity)] = uid(self.counter)
                self.store.stage_done(stage)

    def uid_of(self, identity):
        return self.uids[self.mods.receipt.key_of(identity)]

    def load(self):
        return self.mods.receipt.load(self.store.dir, self.plan, self.expected)

    def journal(self):
        return (self.store.dir / "journal.jsonl").read_bytes()

    def snapshot(self):
        return json.loads((self.store.dir / "receipt.json").read_text())

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@contextlib.contextmanager
def env_for(mods, stages=()):
    env = Env(mods)
    try:
        if stages:
            env.apply(stages)
        yield env
    finally:
        env.cleanup()


def write(env, call):
    with env.store.lock():
        return call()


def destroy_steps_until(env, step):
    """DESTROY_STAGE_DONE for every step before ``step`` (all without owned members in these fixtures)."""
    for name in env.plan.destroy_order[:env.plan.destroy_order.index(step)]:
        write(env, lambda name=name: env.store.destroy_stage_done(name))


def old_summary(state):
    """The snapshot summary as it was before 6c-B4a (a frozen reference)."""
    return {"header": state["header"], "stages_done": list(state["stages_done"]),
            "objects": {k: {"identity": v["identity"], "stage": v["stage"], "owned_uid": v["owned_uid"],
                            "last_outcome": v["last_outcome"]} for k, v in sorted(state["objects"].items())},
            "quarantined": dict(sorted(state["quarantined"].items())), "open_intent": state["open_intent"],
            "last_seq": state["last_seq"]}


def scenario_apply_only_compatible(case, mods):
    with env_for(mods, ("namespaces", "base")) as env:
        loaded = env.load()
        case.assertEqual(loaded["receipt"], "CURRENT")
        snapshot = env.snapshot()
        case.assertEqual(snapshot["state"], json.loads(json.dumps(old_summary(loaded["state"]))))
        case.assertNotIn("destroy", snapshot["state"])
        case.assertEqual(snapshot["format"], 1)
        case.assertEqual(loaded["state"]["phase"], "apply")
        before = (env.journal(), (env.store.dir / "receipt.json").read_bytes())
        case.assertEqual(write(env, env.store.begin), "CURRENT")
        case.assertEqual((env.journal(), (env.store.dir / "receipt.json").read_bytes()), before, "never rewritten")


def scenario_destroy_phase(case, mods):
    with env_for(mods, ("namespaces",)) as env:
        write(env, env.store.begin_destroy)
        loaded = env.load()
        case.assertEqual(loaded["state"]["phase"], "destroy")
        case.assertEqual(env.snapshot()["state"]["destroy"], {"stages_done": [], "destroyed": {}})
        before = env.journal()
        identity = env.members("base")[0]
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.intent("base", identity, {"state": "absent"},
                                                                             "create")), mods),
                         "journal_inconsistent:destroy_phase")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.stage_done("base")), mods),
                         "journal_inconsistent:destroy_phase")
        case.assertEqual(code_of(lambda: write(env, env.store.begin_destroy), mods),
                         "journal_inconsistent:destroy_begin")
        case.assertEqual(env.journal(), before, "a refused record never reaches the journal")


def scenario_open_apply_intent(case, mods):
    with env_for(mods, ("namespaces",)) as env:
        identity = env.members("base")[0]
        write(env, lambda: env.store.intent("base", identity, {"state": "absent"}, "create"))
        case.assertEqual(code_of(lambda: write(env, env.store.begin_destroy), mods), "journal_inconsistent:open_intent")
        case.assertEqual(env.load()["state"]["phase"], "apply")


def scenario_destroy_intent_rules(case, mods):
    with env_for(mods, ("namespaces", "base", "controller", "istiod")) as env:
        write(env, env.store.begin_destroy)
        deployment = DEPLOYMENT
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(deployment,
                                                                                     env.uid_of(deployment))), mods),
                         "journal_inconsistent:destroy_stage_order", "istiod waits for the later stages")
        destroy_steps_until(env, "istiod")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(deployment, uid(999))), mods),
                         "destroy_uid_mismatch")
        gateway = ident("Deployment", "acme-gateway", "acme-ingress")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(gateway, uid(1))), mods),
                         "destroy_not_owned")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(CRD, env.uid_of(CRD))), mods),
                         "record_invalid:crd_retained")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(SECRET, uid(1))), mods),
                         "secret_identity_refused")
        seq = write(env, lambda: env.store.destroy_intent(deployment, env.uid_of(deployment)))
        case.assertEqual(env.load()["state"]["open_intent"], {"seq": seq, "key": env.mods.receipt.key_of(deployment),
                                                              "uid": env.uid_of(deployment), "phase": "destroy"})
        other = ident("Service", "istiod-acme-v1", "istio-system")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(other, env.uid_of(other))), mods),
                         "journal_inconsistent:open_intent", "one open INTENT at a time")


def scenario_destroy_result_rules(case, mods):
    with env_for(mods, ("namespaces", "base", "controller", "istiod")) as env:
        write(env, env.store.begin_destroy)
        destroy_steps_until(env, "istiod")
        seq = write(env, lambda: env.store.destroy_intent(DEPLOYMENT, env.uid_of(DEPLOYMENT)))
        other = ident("Service", "istiod-acme-v1", "istio-system")
        for call, code in ((lambda: env.store.destroy_result(seq + 1, DEPLOYMENT, "deleted"),
                            "journal_inconsistent:result"),
                           (lambda: env.store.destroy_result(seq, other, "deleted"), "journal_inconsistent:result"),
                           (lambda: env.store.destroy_result(seq, DEPLOYMENT, "deleted", uid(3)), "record_invalid:uid"),
                           (lambda: env.store.destroy_result(seq, DEPLOYMENT, "gone"), "record_invalid:outcome"),
                           (lambda: env.store.result(seq, DEPLOYMENT, None, None, None, "failed"),
                            "journal_inconsistent:destroy_phase")):
            case.assertEqual(code_of(lambda: write(env, call), mods), code, code)
        write(env, lambda: env.store.destroy_result(seq, DEPLOYMENT, "failed", env.uid_of(DEPLOYMENT)))
        state = env.load()["state"]
        case.assertIsNone(state["open_intent"])
        case.assertNotIn(env.mods.receipt.key_of(DEPLOYMENT), env.snapshot()["state"]["destroy"]["destroyed"])
        seq2 = write(env, lambda: env.store.destroy_intent(DEPLOYMENT, env.uid_of(DEPLOYMENT)))
        case.assertEqual(seq2, seq + 1, "a retry is a new INTENT with the next sequence")
        write(env, lambda: env.store.destroy_result(seq2, DEPLOYMENT, "deleted"))
        snapshot = env.snapshot()["state"]
        k = env.mods.receipt.key_of(DEPLOYMENT)
        case.assertEqual(snapshot["destroy"]["destroyed"][k], "deleted")
        case.assertEqual(snapshot["objects"][k]["owned_uid"], env.uid_of(DEPLOYMENT), "ownership evidence is kept")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(DEPLOYMENT,
                                                                                     env.uid_of(DEPLOYMENT))), mods),
                         "journal_inconsistent:already_destroyed")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_result(seq2, DEPLOYMENT, "deleted")),
                                 mods), "journal_inconsistent:result", "no RESULT without an open INTENT")


def scenario_destroy_stage_done_rules(case, mods):
    with env_for(mods, ("namespaces", "base")) as env:
        write(env, env.store.begin_destroy)
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_stage_done("base")), mods),
                         "journal_inconsistent:destroy_stage_order")
        destroy_steps_until(env, "base")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_stage_done("base")), mods),
                         "journal_inconsistent:destroy_stage_incomplete", "the validator is still owned")
        seq = write(env, lambda: env.store.destroy_intent(VALIDATOR, env.uid_of(VALIDATOR)))
        write(env, lambda: env.store.destroy_result(seq, VALIDATOR, "absent_confirmed"))
        write(env, lambda: env.store.destroy_stage_done("base"))  # the 15 CRDs are retained and never block it
        write(env, lambda: env.store.destroy_stage_done("namespaces"))  # its Namespaces wait for namespace_phase
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_stage_done("namespace_phase")), mods),
                         "journal_inconsistent:destroy_stage_incomplete")
        for namespace in (ident("Namespace", "istio-system"), NAMESPACE_INGRESS):
            s = write(env, lambda n=namespace: env.store.destroy_intent(n, env.uid_of(n)))
            case.assertEqual(env.load()["records"][-1]["stage"], "namespace_phase")
            write(env, lambda n=namespace, s=s: env.store.destroy_result(s, n, "deleted"))
        write(env, lambda: env.store.destroy_stage_done("namespace_phase"))
        snapshot = env.snapshot()["state"]
        case.assertEqual(snapshot["destroy"]["stages_done"], env.plan.destroy_order)
        crd_key = env.mods.receipt.key_of(CRD)
        case.assertNotIn(crd_key, snapshot["destroy"]["destroyed"], "CRDs stay owned and retained")
        case.assertEqual(snapshot["objects"][crd_key]["owned_uid"], env.uid_of(CRD))


def scenario_destroy_order(case, mods):
    plan = plan_of(mods.receipt)
    case.assertEqual(plan.destroy_order, ["ingress", "binding_writer", "admission", "mesh_security", "gateway",
                                          "istiod", "controller", "base", "namespaces", "namespace_phase"])
    members = plan.destroy_members("mesh_security")
    case.assertNotIn(mods.receipt.key_of(NAMESPACE_APP), members, "acme-app waits for namespace_phase")
    case.assertEqual(len(members), 4)
    case.assertEqual(sorted(k.split("|")[3] for k in plan.destroy_members("namespace_phase")),
                     ["acme-app", "acme-ingress", "istio-system"])
    case.assertEqual(plan.destroy_members("base"), [mods.receipt.key_of(VALIDATOR)], "the 15 CRDs are retained")
    case.assertEqual(len(plan.destroy_members("controller")), 11, "the 2 controller CRDs are retained")
    case.assertEqual(plan.destroy_members("namespaces"), [])


def scenario_quarantine_in_destroy(case, mods):
    with env_for(mods, ("namespaces", "base", "controller", "istiod")) as env:
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.quarantine(DEPLOYMENT, uid(5),
                                                                                 "recreated_after_delete")), mods),
                         "record_invalid:reason", "destroy reasons only in the destroy phase")
        write(env, env.store.begin_destroy)
        destroy_steps_until(env, "istiod")
        seq = write(env, lambda: env.store.destroy_intent(DEPLOYMENT, env.uid_of(DEPLOYMENT)))
        write(env, lambda: env.store.quarantine(DEPLOYMENT, uid(77), "uid_changed_before_delete"))
        state = env.load()["state"]
        case.assertIsNone(state["open_intent"])
        case.assertIn(env.mods.receipt.key_of(DEPLOYMENT), state["quarantined"])
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_intent(DEPLOYMENT,
                                                                                     env.uid_of(DEPLOYMENT))), mods),
                         "quarantined")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_stage_done("istiod")), mods),
                         "journal_inconsistent:destroy_stage_incomplete")
        case.assertEqual(code_of(lambda: env.store.release_quarantine(DEPLOYMENT), mods),
                         "quarantine_release_not_approved")
        case.assertGreater(seq, 0)


def scenario_quarantined_never_owned(case, mods):
    with env_for(mods, ("namespaces",)) as env:
        member = VALIDATOR  # the base stage's only deletable member (its 15 CRDs are retained)
        write(env, lambda: env.store.intent("base", member, {"state": "absent"}, "create"))
        write(env, lambda: env.store.quarantine(member, uid(55), "creation_unproven"))  # never owned
        write(env, env.store.begin_destroy)
        destroy_steps_until(env, "base")
        case.assertEqual(code_of(lambda: write(env, lambda: env.store.destroy_stage_done("base")), mods),
                         "journal_inconsistent:destroy_stage_incomplete", "a quarantined member blocks its step")


def observer(table):
    return lambda identity: table.get(k8s_runtime_receipt.key_of(identity), ("absent", None))


def present(uid_value, manager="acme-k8s-runtime"):
    return ("present", {"uid": uid_value, "managers": [{"manager": manager, "operation": "Apply"}]})


def verdict_of(verdicts, identity):
    return next(v["verdict"] for v in verdicts if v["identity"] == identity)


def scenario_crash_states(case, mods):
    r = mods.receipt
    with env_for(mods, ("namespaces", "base", "controller", "istiod")) as env:
        write(env, env.store.begin_destroy)
        destroy_steps_until(env, "istiod")
        k = r.key_of(DEPLOYMENT)
        owned = {r.key_of(i): present(env.uid_of(i)) for stage in ("namespaces", "base", "controller", "istiod")
                 for i in env.members(stage)}
        seq = write(env, lambda: env.store.destroy_intent(DEPLOYMENT, env.uid_of(DEPLOYMENT)))
        state = env.load()["state"]
        rows = r.reconcile(state, env.plan, observer(owned), "acme-k8s-runtime")
        case.assertEqual(verdict_of(rows, DEPLOYMENT), "DELETE_PENDING_RECHECK", "sent or not: never an auto-resend")
        gone = dict(owned)
        gone.pop(k)
        case.assertEqual(verdict_of(r.reconcile(state, env.plan, observer(gone), "acme-k8s-runtime"), DEPLOYMENT),
                         "DELETE_ABSENT_UNCONFIRMED", "a lost response: absence still needs its RESULT")
        changed = dict(owned, **{k: present(uid(4242))})
        case.assertEqual(verdict_of(r.reconcile(state, env.plan, observer(changed), "acme-k8s-runtime"), DEPLOYMENT),
                         "UID_CHANGED")
        write(env, lambda: env.store.destroy_result(seq, DEPLOYMENT, "absent_confirmed"))
        state = env.load()["state"]
        case.assertEqual(verdict_of(r.reconcile(state, env.plan, observer(gone), "acme-k8s-runtime"), DEPLOYMENT),
                         "DESTROYED")
        case.assertEqual(verdict_of(r.reconcile(state, env.plan, observer(changed), "acme-k8s-runtime"), DEPLOYMENT),
                         "RECREATED_AFTER_DESTROY")
        case.assertEqual(verdict_of(r.reconcile(state, env.plan, observer(owned), "acme-k8s-runtime"), CRD),
                         "CONSISTENT", "a retained CRD stays owned")
        case.assertIn("DESTROYED", r.SETTLED_VERDICTS)
        case.assertNotIn("RECREATED_AFTER_DESTROY", r.SETTLED_VERDICTS)


def scenario_crash_snapshot(case, mods):
    with env_for(mods, ("namespaces", "base", "controller", "istiod")) as env:
        write(env, env.store.begin_destroy)
        destroy_steps_until(env, "istiod")
        seq = write(env, lambda: env.store.destroy_intent(DEPLOYMENT, env.uid_of(DEPLOYMENT)))
        stale = (env.store.dir / "receipt.json").read_bytes()
        write(env, lambda: env.store.destroy_result(seq, DEPLOYMENT, "deleted"))
        (env.store.dir / "receipt.json").write_bytes(stale)  # a crash after the RESULT, before the snapshot
        case.assertEqual(env.load()["receipt"], "STALE")
        case.assertEqual(write(env, env.store.begin), "REFRESHED")
        case.assertEqual(env.load()["receipt"], "CURRENT")
        case.assertEqual(env.snapshot()["state"]["destroy"]["destroyed"], {env.mods.receipt.key_of(DEPLOYMENT):
                                                                           "deleted"})
        (env.store.dir / "receipt.json").unlink()
        case.assertEqual(code_of(lambda: write(env, env.store.begin), mods), "receipt_snapshot_missing")
        case.assertFalse((env.store.dir / "receipt.json").exists(), "never regenerated over destroy records")


def scenario_missing_and_corrupt(case, mods):
    with env_for(mods, ("namespaces",)) as env:
        write(env, env.store.begin_destroy)
        journal = env.store.dir / "journal.jsonl"
        good = journal.read_bytes()
        journal.write_bytes(good.replace(b'"DESTROY_BEGIN"', b'"DESTROY_BEGUN"'))
        case.assertIn(code_of(env.load, mods), ("record_type_unknown", "journal_corrupt:chain"))
        journal.write_bytes(good[:-5])
        case.assertEqual(code_of(env.load, mods), "journal_corrupt:truncated_line")
        journal.unlink()
        case.assertEqual(code_of(env.load, mods), "journal_missing")


def scenario_old_reader_refuses(case, mods):
    with env_for(mods, ("namespaces",)) as env:
        write(env, env.store.begin_destroy)
        old_fields = {k: v for k, v in mods.receipt.RECORD_FIELDS.items() if not k.startswith("DESTROY_")}
        with mock.patch.object(mods.receipt, "RECORD_FIELDS", old_fields):
            case.assertEqual(code_of(env.load, mods), "record_type_unknown")


def scenario_apply_refuses_destroy_phase(case, mods):
    with env_for(mods, ("namespaces",)) as env:
        engine = mods.apply.Engine.__new__(mods.apply.Engine)
        engine.store, engine.plan, engine.manager = env.store, env.plan, "acme-k8s-runtime"
        engine.read = lambda identity: (_ for _ in ()).throw(AssertionError("no read before the phase check"))
        with env.store.lock():
            case.assertIsNotNone(engine.reconcile(()), "an apply-phase journal reconciles")
        write(env, env.store.begin_destroy)
        before = env.journal()
        with env.store.lock():
            try:
                engine.reconcile(("namespaces",))
                stopped = None
            except mods.apply.ApplyStop as stop:
                stopped = (stop.exit_code, stop.reason)
        case.assertEqual(stopped, (2, "receipt_destroy_phase"))
        case.assertEqual(env.journal(), before)


# ---- unit tests ---------------------------------------------------------------------------------------------------

class DestroyTransportTests(unittest.TestCase):
    def test_scopes_are_separate_and_immutable(self):
        scenario_policy_scopes(self, real_mods())

    def test_runtime_delete_needs_the_receipt_uid(self):
        scenario_runtime_delete(self, real_mods())

    def test_unapproved_method_path_query_and_options_refused(self):
        scenario_check_request(self, real_mods())

    def test_list_and_discovery_scope(self):
        scenario_namespace_list_scope(self, real_mods())

    def test_metadata_read_and_trusted_not_found(self):
        scenario_metadata_and_absence(self, real_mods())

    def test_fake_transport_and_real_refusal(self):
        scenario_fake_transport(self, real_mods())
        scenario_real_refused(self, real_mods())


class DiscoveryAndListTests(unittest.TestCase):
    def test_discovery_reads_every_advertised_version(self):
        scenario_discovery_targets(self, real_mods())

    def test_incomplete_discovery_is_unknown(self):
        scenario_discovery_incomplete(self, real_mods())
        scenario_discovery_validation(self, real_mods())

    def test_list_pages_are_metadata_only(self):
        scenario_list_page(self, real_mods())
        scenario_list_page_refusals(self, real_mods())

    def test_pagination_completes_only_on_the_last_page(self):
        scenario_pagination(self, real_mods())
        scenario_pagination_failures(self, real_mods())

    def test_pagination_restart_and_bounds(self):
        scenario_pagination_restart(self, real_mods())
        scenario_pagination_bounds(self, real_mods())
        scenario_deadline(self, real_mods())

    def test_merge_by_uid(self):
        scenario_merge_listed(self, real_mods())


class CrdAndServiceReadTests(unittest.TestCase):
    def test_crd_read_contract(self):
        scenario_crd_read(self, real_mods())
        scenario_crd_mismatches(self, real_mods())

    def test_crd_classification_and_instances(self):
        scenario_crd_classification(self, real_mods())
        scenario_crd_instances(self, real_mods())

    def test_service_type_read(self):
        scenario_service_type(self, real_mods())


class DestroyJournalTests(unittest.TestCase):
    def test_apply_only_journals_unchanged(self):
        scenario_apply_only_compatible(self, real_mods())
        scenario_old_reader_refuses(self, real_mods())

    def test_destroy_phase_transition(self):
        scenario_destroy_phase(self, real_mods())
        scenario_open_apply_intent(self, real_mods())

    def test_destroy_intent_and_result(self):
        scenario_destroy_intent_rules(self, real_mods())
        scenario_destroy_result_rules(self, real_mods())

    def test_destroy_steps(self):
        scenario_destroy_order(self, real_mods())
        scenario_destroy_stage_done_rules(self, real_mods())

    def test_quarantine_and_crash_recovery(self):
        scenario_quarantine_in_destroy(self, real_mods())
        scenario_quarantined_never_owned(self, real_mods())
        scenario_crash_states(self, real_mods())
        scenario_crash_snapshot(self, real_mods())

    def test_missing_or_corrupt_receipt(self):
        scenario_missing_and_corrupt(self, real_mods())

    def test_apply_never_resumes_a_destroy_phase_journal(self):
        scenario_apply_refuses_destroy_phase(self, real_mods())


# ---- mutations ----------------------------------------------------------------------------------------------------

T, R, A = "k8s_runtime_transport.py", "k8s_runtime_receipt.py", "k8s_runtime_apply.py"
RESTART_HEAD = ("    pages, restarts = 0, 0\n    while restarts <= LIST_RESTART_LIMIT:\n"
                "        items, uids, tokens, token, snapshot = [], set(), set(), None, None\n")
DESTROY_MUTATIONS = [
    # transport scopes and DELETE
    ("policy_crd_delete", T, '            need((key[0], key[1]) != CRD_TYPE, "crd_delete_refused")\n            need(key[1] != "Secret", "secret_delete_refused")\n            need(key in plan',
     '            need(key[1] != "Secret", "secret_delete_refused")\n            need(key in plan', scenario_policy_scopes),
    ("policy_kube_system", T, '            need(key != KUBE_SYSTEM_KEY, "kube_system_delete_refused")\n            need((key[0], key[1]) != CRD_TYPE, "crd_delete_refused")\n            need(key[1] != "Secret", "secret_delete_refused")\n            need(key in plan',
     '            need((key[0], key[1]) != CRD_TYPE, "crd_delete_refused")\n            need(key[1] != "Secret", "secret_delete_refused")\n            need(key in plan',
     scenario_policy_scopes),
    ("policy_in_plan", T, 'need(key in plan, "delete_not_in_plan")', "pass", scenario_policy_scopes),
    ("policy_immutable", T, '        raise TransportError("policy_immutable")', "        object.__setattr__(self, name, value)",
     scenario_policy_scopes),
    ("service_scope", T, 'need(key in plan and key[1] == "Service" and key[2] == namespaces[1], "service_read_not_approved")',
     'need(key in plan, "service_read_not_approved")', scenario_policy_scopes),
    ("delete_uid_proven", T, 'need(isinstance(uid, str) and uid == expected, "delete_uid_not_proven")', "pass",
     scenario_runtime_delete),
    ("delete_allowlist", T, '    expected = policy.delete_uid(key)\n    need(expected is not None, "delete_not_allowed")',
     "    expected = uid", scenario_runtime_delete),
    ("delete_crd_guard", T, '    need((key[0], key[1]) != CRD_TYPE, "crd_delete_refused")\n    need(key[1] != "Secret", "secret_delete_refused")\n    expected',
     '    need(key[1] != "Secret", "secret_delete_refused")\n    expected', scenario_runtime_delete),
    ("delete_response_requested", T, 'need(status != 404, "not_found_at_delete")', "pass", scenario_runtime_delete),
    ("check_method", T, 'need(method in ("GET", "DELETE"), "method_not_allowed")', "pass", scenario_check_request),
    ("check_query", T, '''need(isinstance(query, dict) and set(query) <= {"limit", "continue"}''',
     "need(isinstance(query, dict)", scenario_check_request),
    ("check_collection_delete", T, "and single_object_path(path), \"path_not_allowed\")", ', "path_not_allowed")',
     scenario_check_request),
    ("check_delete_options", T, '''need(isinstance(options, dict) and set(options) == DELETE_BODY_KEYS and options["kind"] == "DeleteOptions"''',
     '''need(isinstance(options, dict) and options["kind"] == "DeleteOptions"''', scenario_check_request),
    ("check_propagation", T, ' and options["propagationPolicy"] == "Background"', "", scenario_check_request),
    ("fake_checks_requests", T, "        check_request(request)\n        self.requests.append(request)",
     "        self.requests.append(request)", scenario_fake_transport),
    ("namespace_scope", T, 'need(namespace in policy.namespaces, "namespace_not_approved")', "pass",
     scenario_namespace_list_scope),
    ("discovery_flag", T, 'need(policy.discovery, "discovery_not_allowed")', "pass", scenario_namespace_list_scope),
    ("real_destroy_transport", T, 'need(APPROVED_TRANSPORTS.__contains__(kind), "real_transport_not_implemented")',
     "pass", scenario_real_refused),
    # discovery
    ("discovery_all_versions", T, '    advertised = [("", "v1")] + [(g["name"], v) for g in groups["groups"] for v in g["versions"]]',
     '    advertised = [("", "v1")] + [(g["name"], g["versions"][0]) for g in groups["groups"]]',
     scenario_discovery_incomplete),
    ("discovery_missing_group", T, '            return {"status": "UNKNOWN", "reason": "discovery_group_missing"}',
     "            continue", scenario_discovery_incomplete),
    ("discovery_unlistable", T, '            elif (group, name) not in VIRTUAL_RESOURCES:\n                return',
     "            elif False:\n                return", scenario_discovery_incomplete),
    ("discovery_virtual", T, '            elif (group, name) not in VIRTUAL_RESOURCES:', "            elif True:",
     scenario_discovery_targets),
    ("discovery_groupversion", T, '''and entry.get("groupVersion") == group["name"] + "/" + entry["version"], "discovery_invalid")''',
     ''', "discovery_invalid")''', scenario_discovery_validation),
    # LIST pages
    ("list_item_payload", T, '        need(not (FORBIDDEN_RESPONSE_KEYS & set(item)), "response_not_metadata_only")\n', "",
     scenario_list_page_refusals),
    ("list_last_applied", T, 'need(LAST_APPLIED not in annotations.keys(), "response_secret_annotation_refused")',
     "pass", scenario_list_page_refusals),
    ("list_namespace", T, "and (namespace is None or item_namespace == namespace)", "", scenario_list_page_refusals),
    ("list_duplicate", T, '        need(uid not in uids and (item_namespace, name) not in names, "list_duplicate_item")',
     "        pass", scenario_list_page_refusals),
    ("list_limit", T, 'need(len(items) <= limit, "list_over_limit")', "pass", scenario_list_page_refusals),
    ("list_kind", T, '''    need(document.get("kind") == "PartialObjectMetadataList" and document.get("apiVersion") == "meta.k8s.io/v1",
         "response_not_partial_object_metadata_list")''', "    pass", scenario_list_page_refusals),
    ("list_minimal_items", T, '        result.append({"name": name, "namespace": item_namespace, "uid": uid, "owners": minimal_owners,',
     '        result.append({"labels": metadata.get("labels"), "name": name, "namespace": item_namespace, "uid": uid, "owners": minimal_owners,',
     scenario_list_page),
    # pagination
    ("page_final", T, "            if token is None:\n                return {\"status\": \"COMPLETE\"",
     "            if True:\n                return {\"status\": \"COMPLETE\"", scenario_pagination),
    ("page_repeat", T, '            if token in tokens:\n                return {"status": "UNKNOWN", "reason": "list_continue_repeated"}',
     "            if False:\n                return {\"status\": \"UNKNOWN\", \"reason\": \"list_continue_repeated\"}",
     scenario_pagination_failures),
    ("page_snapshot", T, '            elif page["resource_version"] != snapshot:', "            elif False:",
     scenario_pagination_failures),
    ("page_duplicate", T, '                if item["uid"] in uids:\n                    return', "                if False:\n                    return",
     scenario_pagination_failures),
    ("page_forbidden_blocked", T, '                    return {"status": "BLOCKED", "reason": "inventory_forbidden"}',
     '                    return {"status": "UNKNOWN", "reason": "inventory_forbidden"}', scenario_pagination_failures),
    ("page_restart_discards", T, RESTART_HEAD, "    pages, restarts = 0, 0\n    items = []\n    while restarts <= LIST_RESTART_LIMIT:\n        uids, tokens, token, snapshot = set(), set(), None, None\n",
     scenario_pagination_restart),
    ("page_restart_limit", T, "    while restarts <= LIST_RESTART_LIMIT:", "    while restarts <= LIST_RESTART_LIMIT + 1:",
     scenario_pagination_restart),
    ("page_limit", T, "            if pages >= LIST_PAGE_LIMIT:", "            if pages >= LIST_PAGE_LIMIT * 2:",
     scenario_pagination_bounds),
    ("page_restart_counts", T, RESTART_HEAD, "    restarts = 0\n    while restarts <= LIST_RESTART_LIMIT:\n        pages = 0\n        items, uids, tokens, token, snapshot = [], set(), set(), None, None\n",
     scenario_pagination_bounds),
    ("page_deadline", T, '            if deadline is not None and deadline.expired():', "            if False:",
     scenario_pagination_bounds),
    ("deadline_immutable", T, '        raise TransportError("deadline_immutable")', "        object.__setattr__(self, name, value)",
     scenario_deadline),
    ("deadline_bound", T, "and 0 < seconds <= DESTROY_DEADLINE_SECONDS,", "and 0 < seconds,", scenario_deadline),
    ("merge_mapping", T, "            if (seen[\"name\"], seen[\"namespace\"]) != (item[\"name\"], item[\"namespace\"]) or not (same_resource or alias):",
     "            if False:", scenario_merge_listed),
    # CRD and Service reads
    ("crd_uid", T, '(info["uid"] == receipt_uid, "crd_uid_mismatch"),', "", scenario_crd_mismatches),
    ("crd_established", T, '(info["established"] is True, "crd_not_established"),', "", scenario_crd_mismatches),
    ("crd_storage", T, '(info["storage_versions"] == [spec["storage_version"]], "crd_storage_version_mismatch"),', "",
     scenario_crd_mismatches),
    ("crd_served", T, '(spec["storage_version"] in info["served_versions"], "crd_storage_not_served"),', "",
     scenario_crd_mismatches),
    ("crd_scope", T, '(info["scope"] == spec["scope"], "crd_scope_mismatch"),', "", scenario_crd_mismatches),
    ("crd_trusted_404", T, '''        need(trusted_not_found("apiextensions.k8s.io", "customresourcedefinitions", name, status, body),
             "not_found_untrusted")''', "        pass", scenario_crd_mismatches),
    ("crd_list_verified", T, '''    need(isinstance(verified, dict) and verified.get("verdict") == "VERIFIED" and verified.get("name") == name
         and verified.get("storage_version") == spec["storage_version"], "crd_not_verified")''', "    pass",
     scenario_crd_read),
    ("crd_reviewed_only", T, '    need(found is not None, "crd_not_reviewed")', "    found = found or '{}'", scenario_crd_read),
    ("crd_foreign", T, '        return {"verdict": "BLOCKED", "name": name, "reason": "foreign_crd"}',
     '        return verify_crd(policy, name, value, value["uid"])', scenario_crd_classification),
    ("crd_claimed_absent", T, '            return {"verdict": "BLOCKED", "name": name, "reason": "crd_claimed_but_absent"}',
     '            return {"verdict": "CRD_NOT_CREATED", "name": name, "reason": None}', scenario_crd_classification),
    ("crd_discovery_consistency", T, "        if advertised:\n", "        if False:\n", scenario_crd_classification),
    ("crd_instances_remain", T, '    if page["items"]:\n        return {"verdict": "BLOCKED", "reason": "crd_instances_remain"}',
     '    if False:\n        return {"verdict": "BLOCKED", "reason": "crd_instances_remain"}', scenario_crd_instances),
    ("crd_instances_continue", T, '    if page["continue"] is not None:\n        return {"verdict": "UNKNOWN", "reason": "crd_list_inconsistent"}',
     '    if False:\n        return {"verdict": "UNKNOWN", "reason": "crd_list_inconsistent"}', scenario_crd_instances),
    ("service_type_values", T, 'need(isinstance(spec, dict) and spec.get("type") in SERVICE_TYPES, "service_type_invalid")',
     "pass", scenario_service_type),
    ("trusted_not_found_name", T, 'and document.get("code") == 404 and details.get("name") == name and details.get("kind") == resource',
     'and document.get("code") == 404 and details.get("kind") == resource', scenario_metadata_and_absence),
    ("destroy_metadata_untrusted", T, '''        need(trusted_not_found(group, resource, identity["name"], status, body), "not_found_untrusted")''',
     "        pass", scenario_metadata_and_absence),
    # receipt / journal
    ("phase_apply_refused", R, '            need(state["phase"] == "apply", "journal_inconsistent:destroy_phase")', "            pass",
     scenario_destroy_phase),
    ("phase_begin_once", R, '            need(state["phase"] == "apply", "journal_inconsistent:destroy_begin")', "            pass",
     scenario_destroy_phase),
    ("phase_open_intent", R, '            need(state["open_intent"] is None, "journal_inconsistent:open_intent")\n            state["phase"] = "destroy"',
     '            state["phase"] = "destroy"', scenario_open_apply_intent),
    ("destroy_uid", R, 'need(owned == record["uid"], "destroy_uid_mismatch")', "pass", scenario_destroy_intent_rules),
    ("destroy_owned", R, 'need(owned is not None, "destroy_not_owned")', "pass", scenario_destroy_intent_rules),
    ("destroy_crd_retained", R, 'need(not key.startswith(CRD_KEY_PREFIX), "record_invalid:crd_retained")', "pass",
     scenario_destroy_intent_rules),
    ("destroy_single_intent", R, '                need(state["open_intent"] is None, "journal_inconsistent:open_intent")\n                need(record["seq"]',
     '                need(record["seq"]', scenario_destroy_intent_rules),
    ("destroy_order", R, '                need(done == plan.destroy_order[:position], "journal_inconsistent:destroy_stage_order")',
     "                pass", scenario_destroy_intent_rules),
    ("destroy_quarantined", R, 'need(not state["quarantined"].get(key), "quarantined")', "pass", scenario_quarantine_in_destroy),
    ("destroy_result_match", R, '''need(intent is not None and intent.get("phase") == "destroy" and intent["seq"] == record["seq"]''',
     '''need(intent is not None and intent.get("phase") == "destroy"''', scenario_destroy_result_rules),
    ("destroy_already", R, 'need((obj or {}).get("destroyed") is None, "journal_inconsistent:already_destroyed")', "pass",
     scenario_destroy_result_rules),
    ("destroy_failed_keeps_owned", R, '                if record["outcome"] in DESTROYED:\n                    obj["destroyed"]',
     '                if True:\n                    obj["destroyed"]', scenario_destroy_result_rules),
    ("destroy_result_uid", R, '''            need(observed is None if record["outcome"] in DESTROYED''',
     '''            need(True if record["outcome"] in DESTROYED''', scenario_destroy_result_rules),
    ("stage_done_complete", R, '                need(obj is None or obj["owned_uid"] is None or obj.get("destroyed") in DESTROYED,',
     "                need(True,", scenario_destroy_stage_done_rules),
    ("stage_done_quarantine", R, '                need(member not in state["quarantined"], "journal_inconsistent:destroy_stage_incomplete")',
     "                pass", scenario_quarantined_never_owned),
    ("stage_done_order", R, '''            need(len(done) < len(plan.destroy_order) and record["stage"] == plan.destroy_order[len(done)],
                 "journal_inconsistent:destroy_stage_order")''', "            pass", scenario_destroy_stage_done_rules),
    ("namespace_deferred", R, '        return NAMESPACE_PHASE if key.split("|")[1] == "Namespace" else self.stage_of.get(key)',
     "        return self.stage_of.get(key)", scenario_destroy_order),
    ("crds_retained_members", R, "        return [k for k in keys if not k.startswith(CRD_KEY_PREFIX) and self.destroy_step(k) == step]",
     "        return [k for k in keys if self.destroy_step(k) == step]", scenario_destroy_order),
    ("destroy_quarantine_reasons", R, '            need(state["phase"] == "destroy" or record["reason"] in QUARANTINE_REASONS, "record_invalid:reason")',
     "            pass", scenario_quarantine_in_destroy),
    ("summary_apply_only", R, '    if state.get("phase") == "destroy":\n        # Only after DESTROY_BEGIN',
     "    if True:\n        # Only after DESTROY_BEGIN", scenario_apply_only_compatible),
    ("reconcile_destroyed", R, '                verdict = "DESTROYED" if presence == "absent" else "RECREATED_AFTER_DESTROY"',
     '                verdict = "DESTROYED"', scenario_crash_states),
    ("reconcile_recheck", R, '                elif observed["uid"] != open_intent["uid"]:\n                    verdict = "UID_CHANGED"',
     '                elif False:\n                    verdict = "UID_CHANGED"', scenario_crash_states),
    ("reconcile_absent_unconfirmed", R, '                    verdict = "DELETE_ABSENT_UNCONFIRMED"', '                    verdict = "DESTROYED"',
     scenario_crash_states),
    # apply phase guard
    ("apply_phase_guard", A, '        if receipt.load(self.store.dir, self.plan, self.store.expected)["state"]["phase"] != "apply":',
     "        if False:", scenario_apply_refuses_destroy_phase),
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


class DestroyMutationTests(unittest.TestCase):
    def test_each_destroy_guard_mutation_is_detected_by_an_assertion(self):
        self.assertEqual(len(DESTROY_MUTATIONS), 83)
        self.assertEqual(len(DESTROY_MUTATIONS), len({m[0] for m in DESTROY_MUTATIONS}))
        undetected = []
        for name, filename, old, new, scenario in DESTROY_MUTATIONS:
            mods = real_mods()
            setattr(mods, {T: "transport", R: "receipt", A: "apply"}[filename], mutant(filename, old, new))
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, mods)
            except AssertionError:
                continue
            except Exception as crashed:  # noqa: BLE001 - a crash is never counted as a detection
                undetected.append(name + ":crashed:" + type(crashed).__name__)
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
