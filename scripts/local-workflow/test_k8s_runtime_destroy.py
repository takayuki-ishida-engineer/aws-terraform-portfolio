#!/usr/bin/env python3
"""Offline tests for the 6c-B4b Fake-only runtime destroy engine (``k8s_runtime_destroy``).

The bundle is the synthetic fixture rendered with the pinned Helm (``K8S_RUNTIME_HELM``), so every manifest, the
stage table and the 62 identities are the reviewed ones. A stateful fake API server (``FakeCluster``) answers the
destroy transport and the G9 client: metadata reads, discovery, metadata LISTs, the specialised CRD and Service
reads and UID-precondition DELETEs, with a fake clock for finalizers, garbage collection and namespace
termination. Every receipt lives in a temporary directory outside the repository.

Synthetic ownership evidence: the fake apply engine stops before the gateway, so the runtime journal and the
objects' managedFields are written here directly (``World``). The runtime manager owns exactly each manifest's
required paths; the TargetGroupBinding carries the controller's finalizer but, in the positive fixtures, no
controller managedFields entry. That is a fixture, never evidence that a real apply produced it: with the real
controller or istiod entries D13 stays unverified and destroy stops (tested). Nothing here is Live evidence.

``ENGINE_MUTATIONS`` removes one guard of the engine at a time. A mutation counts as detected only when its
scenario fails an assertion; a crash is reported as undetected. These tests run inside the
``k8s_runtime_receipt_tests`` suite.
"""
import contextlib
import copy
import io
import json
import os
import re
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
import k8s_certs_receipt  # noqa: E402
import k8s_runtime  # noqa: E402
import k8s_runtime_apply  # noqa: E402
import k8s_runtime_destroy  # noqa: E402
import k8s_runtime_receipt  # noqa: E402
import k8s_runtime_transport  # noqa: E402
from test_k8s_certs_receipt import secret_metadata  # noqa: E402
from test_k8s_runtime_apply import bundle  # noqa: E402
from test_k8s_runtime_destroy_foundation import mutant  # noqa: E402

T = k8s_runtime_transport
KUBE_SYSTEM_UID = "11111111-2222-4333-8444-555555555555"
FULL = ("namespaces", "base", "controller", "istiod", "gateway", "mesh_security", "admission", "binding_writer",
        "ingress")
PARTIAL = ("namespaces", "base")
ISTIOD = ("namespaces", "base", "controller", "istiod")
CRD_KIND = ("apiextensions.k8s.io/v1", "CustomResourceDefinition")
D = "k8s_runtime_destroy.py"
R = "k8s_runtime_receipt.py"
TR = "k8s_runtime_transport.py"


class Crash(BaseException):
    """A simulated process crash: nothing in the engine catches it."""


class Mods(types.SimpleNamespace):
    pass


def real_mods():
    return Mods(destroy=k8s_runtime_destroy, receipt=k8s_runtime_receipt, transport=k8s_runtime_transport)


def uid(n):
    return "00000000-0000-4000-8000-%012x" % n


def not_found(group, resource, name):
    return 404, json.dumps({"kind": "Status", "apiVersion": "v1", "status": "Failure", "reason": "NotFound",
                            "code": 404, "details": {"name": name, "group": group, "kind": resource}}).encode()


def group_resource(identity):
    group, resource = T.identity_resource(identity) if identity["kind"] != "Secret" else ("", "secrets")
    return group, resource


# ---- the fake API server ---------------------------------------------------------------------------------------------

class FakeCluster:
    """A stateful fake API server for the destroy transport and the G9 client."""

    def __init__(self, clock, project, manifests):
        self.clock, self.project, self.manifests = clock, project, manifests
        self.objects = {}      # object path -> {"identity", "meta"}
        self.extras = {}       # (namespace, group, resource) -> {name: meta}   (listed only)
        self.instances = {}    # (group, plural) -> [(namespace, name, uid)]   (extra custom resources)
        self.service_types = {}
        self.requests, self.faults, self.hooks, self.pending = [], [], [], []
        self.finalizer_release, self.ns_termination, self.gc_delay = 30, 15, 10
        self.latency = {}
        self.served = {}       # extra discovery entries: group version -> resources
        self.hidden_versions = {}   # (group, plural) -> versions a CRD's discovery leaves out
        self.scope_override = {}    # (group, plural) -> the namespaced flag discovery reports
        self.discovery_overrides = {}
        self._atomic_namespace = None
        self._accepted_namespaces = {}
        self.atomic_transport = T
        self.counter = 5000
        self.secret_ids = T.secret_identities(project)
        self.secret_keys = frozenset(T.identity_key(i) for i in self.secret_ids)
        self.paths = {}
        for key in manifests:
            identity = dict(zip(("apiVersion", "kind", "namespace", "name"), key.split("|")))
            self.paths[T.object_path(identity)] = identity
        for identity in self.secret_ids:
            self.paths[T.object_path(identity, self.secret_keys)] = identity
        self.kube_system = {"name": "kube-system", "uid": KUBE_SYSTEM_UID}

    def new_uid(self):
        self.counter += 1
        return uid(self.counter)

    # -- state ------------------------------------------------------------------------------------------------
    def runtime_meta(self, identity, uid_value, finalizers=()):
        manifest = self.manifests[k8s_runtime_receipt.key_of(identity)]
        fields = k8s_runtime_apply.fieldsv1_of(k8s_runtime_apply.required_paths(manifest))
        meta = {"name": identity["name"], "uid": uid_value, "resourceVersion": "100",
                "managedFields": [{"manager": self.project + "-k8s-runtime", "operation": "Apply",
                                   "apiVersion": identity["apiVersion"], "fieldsType": "FieldsV1",
                                   "fieldsV1": fields}]}
        if identity["namespace"]:
            meta["namespace"] = identity["namespace"]
        if finalizers:
            meta["finalizers"] = list(finalizers)
        return meta

    def put(self, identity, uid_value, finalizers=None):
        if finalizers is None:
            finalizers = [k8s_runtime_apply.LBC_FINALIZER] if identity["kind"] == "TargetGroupBinding" else []
        path = T.object_path(identity)
        self.objects[path] = {"identity": identity, "meta": self.runtime_meta(identity, uid_value, finalizers)}
        if identity["kind"] == "Service":
            self.service_types[path] = "ClusterIP"
        return path

    def meta_of(self, identity):
        entry = self.objects.get(T.object_path(identity, self.secret_keys))
        return entry["meta"] if entry else None

    def put_secret(self, name, uid_value=None):
        identity = next(i for i in self.secret_ids if i["name"] == name)
        meta = secret_metadata(name, uid_value or self.new_uid(), self.project)
        self.objects[T.object_path(identity, self.secret_keys)] = {"identity": identity, "meta": meta}
        return meta["uid"]

    def apply_secrets(self, plan):
        results = []
        for item in plan:
            existing = self.meta_of({"apiVersion": "v1", "kind": "Secret", "namespace": item["namespace"],
                                     "name": item["name"]})
            if item["expect_uid"] is None and existing is None:
                outcome, written = "created", self.put_secret(item["name"])
            else:
                outcome, written = "conflict", existing["uid"] if existing else None
            results.append({"namespace": item["namespace"], "name": item["name"], "outcome": outcome,
                            "uid": written})
        return results

    def extra(self, namespace, group, resource, name, owners=(), deleting=False, uid_value=None):
        meta = {"name": name, "namespace": namespace, "uid": uid_value or self.new_uid(), "resourceVersion": "100"}
        if owners:
            meta["ownerReferences"] = [dict(o) for o in owners]
        if deleting:
            meta["deletionTimestamp"] = "2026-11-24T00:00:00Z"
        self.extras.setdefault((namespace, group, resource), {})[name] = meta
        return meta

    def owner(self, identity, controller=True):
        meta = self.meta_of(identity)
        return {"apiVersion": identity["apiVersion"], "kind": identity["kind"], "name": identity["name"],
                "uid": meta["uid"], "controller": controller, "blockOwnerDeletion": True}

    def children(self, deployment):
        """A ReplicaSet and a Pod of a runtime Deployment, garbage-collected after the Deployment is deleted."""
        rs = self.extra(deployment["namespace"], "apps", "replicasets", deployment["name"] + "-6b7f",
                        owners=[self.owner(deployment)])
        self.extra(deployment["namespace"], "", "pods", deployment["name"] + "-6b7f-x2",
                   owners=[{"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": rs["name"], "uid": rs["uid"],
                            "controller": True}])

    def slice_of(self, service):
        self.extra(service["namespace"], "discovery.k8s.io", "endpointslices", service["name"] + "-abcde",
                   owners=[self.owner(service)])

    def leftovers(self, namespace):
        self.extra(namespace, "", "serviceaccounts", "default")
        self.extra(namespace, "", "configmaps", "kube-root-ca.crt")
        self.extra(namespace, "", "configmaps", "istio-ca-root-cert")
        self.extra(namespace, "", "events", "startup.17a3")

    def remove_children_of(self, owner_uid):
        removed = []
        for (namespace, group, resource), items in self.extras.items():
            for name, meta in list(items.items()):
                if any(o.get("uid") == owner_uid and o.get("controller") for o in meta.get("ownerReferences", [])):
                    removed.append(meta["uid"])
                    if not meta.get("finalizers"):
                        del items[name]  # an object with a finalizer stays terminating
        for child in removed:
            self.remove_children_of(child)

    def tick(self):
        now = self.clock.now()
        due = [p for p in self.pending if p[0] <= now]
        self.pending = [p for p in self.pending if p[0] > now]
        for _, action in due:
            action()

    def later(self, delay, action):
        if delay is not None:
            self.pending.append((self.clock.now() + delay, action))

    # -- discovery --------------------------------------------------------------------------------------------
    def discovery(self):
        lists = {
            "v1": [{"name": n, "kind": k, "namespaced": True, "verbs": ["get", "list"]} for n, k in
                   (("configmaps", "ConfigMap"), ("secrets", "Secret"), ("services", "Service"), ("pods", "Pod"),
                    ("serviceaccounts", "ServiceAccount"), ("events", "Event"))]
            + [{"name": "bindings", "kind": "Binding", "namespaced": True, "verbs": ["create"]},
               {"name": "pods/log", "kind": "Pod", "namespaced": True, "verbs": ["get"]},
               {"name": "namespaces", "kind": "Namespace", "namespaced": False, "verbs": ["get", "list"]}],
            "apps/v1": [{"name": "deployments", "kind": "Deployment", "namespaced": True, "verbs": ["get", "list"]},
                        {"name": "replicasets", "kind": "ReplicaSet", "namespaced": True, "verbs": ["get", "list"]}],
            "discovery.k8s.io/v1": [{"name": "endpointslices", "kind": "EndpointSlice", "namespaced": True,
                                     "verbs": ["get", "list"]}],
            "coordination.k8s.io/v1": [{"name": "leases", "kind": "Lease", "namespaced": True,
                                        "verbs": ["get", "list"]}],
            "events.k8s.io/v1": [{"name": "events", "kind": "Event", "namespaced": True, "verbs": ["get", "list"]}],
            "rbac.authorization.k8s.io/v1": [
                {"name": "roles", "kind": "Role", "namespaced": True, "verbs": ["get", "list"]},
                {"name": "rolebindings", "kind": "RoleBinding", "namespaced": True, "verbs": ["get", "list"]},
                {"name": "clusterroles", "kind": "ClusterRole", "namespaced": False, "verbs": ["get", "list"]}],
            "networking.k8s.io/v1": [{"name": "networkpolicies", "kind": "NetworkPolicy", "namespaced": True,
                                      "verbs": ["get", "list"]}],
            "authorization.k8s.io/v1": [{"name": "localsubjectaccessreviews", "kind": "LocalSubjectAccessReview",
                                         "namespaced": True, "verbs": ["create"]}],
            "apiextensions.k8s.io/v1": [{"name": "customresourcedefinitions", "kind": "CustomResourceDefinition",
                                         "namespaced": False, "verbs": ["get", "list"]}],
        }
        for gv, rows in self.served.items():
            lists.setdefault(gv, []).extend(copy.deepcopy(rows))
        for entry in self.objects.values():
            identity = entry["identity"]
            if (identity["apiVersion"], identity["kind"]) != CRD_KIND or "deletionTimestamp" in entry["meta"]:
                continue
            spec = self.manifests[k8s_runtime_receipt.key_of(identity)]["spec"]
            mapping = (spec["group"], spec["names"]["plural"])
            for version in spec["versions"]:
                if version.get("served") and version["name"] not in self.hidden_versions.get(mapping, ()):
                    rows = lists.setdefault(spec["group"] + "/" + version["name"], [])
                    rows.append({"name": spec["names"]["plural"], "kind": spec["names"]["kind"],
                                 "namespaced": self.scope_override.get(mapping, spec["scope"] == "Namespaced"),
                                 "verbs": ["get", "list"]})
        for gv, rows in lists.items():
            group = "" if gv == "v1" else gv.split("/")[0]
            for row in rows:
                row.update(self.discovery_overrides.get((group, row["name"]), {}))
        groups = {}
        for gv in sorted(lists):
            if gv != "v1":
                group, version = gv.split("/")
                groups.setdefault(group, []).append(version)
        return lists, groups

    def discovery_answer(self, path):
        lists, groups = self.discovery()
        if path == "/api":
            return {"kind": "APIVersions", "versions": ["v1"]}
        if path == "/apis":
            return {"kind": "APIGroupList", "apiVersion": "v1", "groups": [
                {"name": g, "versions": [{"groupVersion": g + "/" + v, "version": v} for v in vs]}
                for g, vs in sorted(groups.items())]}
        gv = "v1" if path == "/api/v1" else path[len("/apis/"):]
        if gv not in lists:
            return None
        return {"kind": "APIResourceList", "groupVersion": gv, "resources": lists[gv]}

    # -- LISTs ------------------------------------------------------------------------------------------------
    def listed(self, namespace, group, resource):
        items = []
        for entry in self.objects.values():
            identity = entry["identity"]
            if identity["namespace"] == namespace and group_resource(identity) == (group, resource):
                items.append(entry["meta"])
        logical = ("", "events") if resource == "events" else (group, resource)
        items += list(self.extras.get((namespace,) + logical, {}).values())
        for ns, name, uid_value in self.instances.get((group, resource), []):
            if ns == namespace:
                items.append({"name": name, "namespace": ns, "uid": uid_value, "resourceVersion": "100"})
        return items

    def list_item(self, meta):
        keys = ("name", "namespace", "uid", "ownerReferences", "finalizers", "deletionTimestamp", "resourceVersion")
        return {"metadata": {k: meta[k] for k in keys if k in meta}}

    def list_answer(self, items, limit, token=None):
        body = {"kind": "PartialObjectMetadataList", "apiVersion": "meta.k8s.io/v1",
                "metadata": {"resourceVersion": "100"}, "items": [self.list_item(m) for m in items[:limit]]}
        if token:
            body["metadata"]["continue"] = token
        return 200, json.dumps(body).encode()

    def crd_instances(self, group, plural):
        found = [(e["identity"]["namespace"], e["identity"]["name"], e["meta"]["uid"]) for e in self.objects.values()
                 if group_resource(e["identity"]) == (group, plural)]
        extras = [(ns, name, meta["uid"]) for (ns, g, resource), items in self.extras.items()
                  if (g, resource) == (group, plural) for name, meta in items.items()]
        return found + list(self.instances.get((group, plural), [])) + extras

    # -- the server -------------------------------------------------------------------------------------------
    def __call__(self, request):
        self.tick()
        self.requests.append(copy.deepcopy(request))
        for fault in list(self.faults):
            answer = fault(request)
            if answer is not None:
                self.after(request)
                return answer
        answer = self.answer(request)
        delay = next((d for pattern, d in self.latency.items() if re.search(pattern, request["path"])), 0)
        self.clock.sleep(delay)
        self.after(request)
        return answer

    def after(self, request):
        for hook in list(self.hooks):
            hook(request)

    def atomic_namespace_delete(self, request, evidence, deadline):
        """Out-of-band Fake-only capability. Faults still run before the atomic acceptance check in answer()."""
        if self._atomic_namespace is not None or deadline.expired():
            return 409, b""
        self._atomic_namespace = (copy.deepcopy(request), copy.deepcopy(evidence), deadline)
        try:
            return self(request)
        finally:
            self._atomic_namespace = None

    def current_namespace_inventory(self, namespace):
        """Read the fake's actual store in one synchronous section; reject undiscovered objects as well."""
        try:
            lists, groups = self.discovery()

            def checked(path, body):
                return T.validate_discovery_response(path, 200, json.dumps(body).encode())
            core = checked("/api", {"kind": "APIVersions", "versions": ["v1"]})
            group_list = checked("/apis", {"kind": "APIGroupList", "apiVersion": "v1", "groups": [
                {"name": g, "versions": [{"groupVersion": g + "/" + v, "version": v} for v in vs]}
                for g, vs in groups.items()]})
            validated = {gv: checked("/api/v1" if gv == "v1" else "/apis/" + gv,
                                     {"kind": "APIResourceList", "groupVersion": gv, "resources": rows})
                         for gv, rows in lists.items()}
            found = T.discovery_targets(core, group_list, validated)
        except (T.TransportError, TypeError, ValueError, KeyError, AttributeError):
            return None, None
        if found["status"] != "COMPLETE":
            return None, None
        targets = found["targets"]
        mapped = {(g, r) for g, _, r in targets}

        def logical(group, resource):
            return ("", "events") if (group, resource) in (("", "events"), ("events.k8s.io", "events")) \
                else (group, resource)
        actual = set()
        for entry in self.objects.values():
            ident = entry["identity"]
            if ident["namespace"] == namespace:
                group, resource = group_resource(ident)
                if (group, resource) not in mapped:
                    return None, None
                actual.add((logical(group, resource), ident["name"], entry["meta"]["uid"]))
        for (ns, group, resource), items in self.extras.items():
            if ns == namespace:
                if items and (group, resource) not in mapped:
                    return None, None
                actual.update((logical(group, resource), name, meta["uid"]) for name, meta in items.items())
        for (group, resource), items in self.instances.items():
            if any(ns == namespace for ns, _, _ in items) and (group, resource) not in mapped:
                return None, None
            actual.update((logical(group, resource), name, uid_value) for ns, name, uid_value in items
                          if ns == namespace)
        pages = []
        for target in targets:
            group, _, resource = target
            items = self.listed(namespace, group, resource)
            if len(items) > T.LIST_PAGE_SIZE:
                return None, None  # the fake refuses when it cannot prove the full snapshot
            status, body = self.list_answer(items, T.LIST_PAGE_SIZE)
            try:
                page = T.validate_list_response(namespace, T.LIST_PAGE_SIZE, status, body)
            except T.TransportError:
                return None, None
            pages.append((target, {"status": "COMPLETE", "items": page["items"]}))
        merged = T.merge_listed(targets, pages)
        if merged["status"] != "COMPLETE":
            return None, None
        observed = {(logical(group, resource), item["name"], item["uid"]) for item in merged["objects"]
                    for group, resource in item["resources"]}
        if actual != observed:
            return None, None
        snapshot = {"targets": targets, "advertised": found["advertised"], "resources": found["resources"],
                    "listable": found["listable"]}
        return json.loads(json.dumps(snapshot)), json.loads(json.dumps(merged["objects"]))

    def namespace_gate_ok(self, entry, evidence, terminating=False):
        ident, meta = entry["identity"], entry["meta"]
        name = ident["name"]
        if (name != evidence["namespace"] or meta["uid"] != evidence["uid"]
                or name not in T.inventory_namespaces(self.project)
                or self.kube_system["uid"] != evidence["kube_system_uid"]):
            return False
        current = T.namespace_safety_metadata(meta)
        expected = dict(evidence["metadata"])
        if terminating:
            current.pop("deletionTimestamp", None)
            expected.pop("deletionTimestamp", None)
        if current != expected:
            return False
        manifest = self.manifests[k8s_runtime_receipt.key_of(ident)]
        observed = k8s_runtime_apply.observed_of(dict(ident, metadata=meta), manifest)
        if k8s_runtime_apply.d13_ownership(observed, self.project + "-k8s-runtime") != "OWNED":
            return False
        if not terminating:
            for secret in self.secret_ids:
                if self.meta_of(secret) is not None or secret["name"] in self.extras.get(
                        (secret["namespace"], "", "secrets"), {}):
                    return False
        discovery, items = self.current_namespace_inventory(name)
        return self.atomic_transport.namespace_snapshot_matches(evidence, discovery, items, name)

    def answer(self, request):
        method, path = request["method"], request["path"]
        accept = request["headers"].get("Accept")
        query = request.get("query") or {}
        if path == "/api/v1/namespaces/kube-system" and method == "GET":
            return 200, json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                                    "metadata": self.kube_system}).encode()
        if method == "GET" and T.DISCOVERY_PATH.fullmatch(path) and accept == T.JSON_ACCEPT:
            document = self.discovery_answer(path)
            return (200, json.dumps(document).encode()) if document is not None else (404, b"")
        if method == "GET" and accept == T.LIST_ACCEPT:
            return self.list_request(path, query)
        identity = self.paths.get(path)
        if identity is None:
            return 404, b""
        entry = self.objects.get(path)
        group, resource = group_resource(identity)
        if method == "GET":
            if entry is None:
                return not_found(group, resource, identity["name"])
            if accept == T.METADATA_ACCEPT:
                return 200, json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                                        "metadata": entry["meta"]}).encode()
            if (identity["apiVersion"], identity["kind"]) == CRD_KIND:
                return 200, json.dumps(self.crd_body(identity, entry)).encode()
            if identity["kind"] == "Service":
                return 200, json.dumps({"kind": "Service", "apiVersion": "v1", "metadata": {
                    "name": identity["name"], "namespace": identity["namespace"], "uid": entry["meta"]["uid"]},
                    "spec": {"type": self.service_types.get(path, "ClusterIP")}}).encode()
            return 400, b""
        if method == "DELETE":
            if identity == {"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "kube-system"}:
                return 405, b""
            if entry is None:
                return not_found(group, resource, identity["name"])
            precondition = (json.loads(request["body"] or "{}").get("preconditions") or {}).get("uid")
            if precondition != entry["meta"]["uid"]:
                return 409, b'{"kind":"Status","reason":"Conflict"}'
            if identity["kind"] == "Namespace":
                atomic = self._atomic_namespace
                if atomic is None or atomic[0] != request or atomic[2].expired() \
                        or not self.namespace_gate_ok(entry, atomic[1]):
                    return 409, b'{"kind":"Status","reason":"Conflict"}'
                self._accepted_namespaces[path] = atomic[1]
            self.delete(path, entry)
            return 200, b'{"kind":"Status","status":"Success"}'
        return 405, b""

    def crd_body(self, identity, entry):
        manifest = self.manifests[k8s_runtime_receipt.key_of(identity)]
        status = entry.get("crd_status", {"conditions": [{"type": "Established", "status": "True"}]})
        spec = copy.deepcopy(entry.get("crd_spec") or manifest["spec"])
        return {"kind": "CustomResourceDefinition", "apiVersion": "apiextensions.k8s.io/v1",
                "metadata": {"name": identity["name"], "uid": entry["meta"]["uid"]}, "spec": spec, "status": status}

    def delete(self, path, entry):
        identity, meta = entry["identity"], entry["meta"]
        owner_uid = meta["uid"]

        def gone():
            if self.objects.get(path) is entry:
                del self.objects[path]
                self.later(self.gc_delay, lambda: self.remove_children_of(owner_uid))
        if identity["kind"] == "Namespace":
            meta["deletionTimestamp"] = "2026-11-24T00:00:00Z"

            def terminated():
                # A delayed cascade rechecks the accepted snapshot; a late foreign object is never erased.
                evidence = self._accepted_namespaces.get(path)
                if self.objects.get(path) is entry and evidence is not None and not meta.get("finalizers") \
                        and self.namespace_gate_ok(entry, evidence, terminating=True):
                    del self.objects[path]
                    # Only verified allowed leftovers remain at this point.
                    for key in [k for k, v in self.objects.items() if v["identity"]["namespace"] == identity["name"]]:
                        del self.objects[key]
                    for key in [k for k in self.extras if k[0] == identity["name"]]:
                        del self.extras[key]
                    self._accepted_namespaces.pop(path, None)
            self.later(self.ns_termination, terminated)
        elif meta.get("finalizers"):
            meta["deletionTimestamp"] = "2026-11-24T00:00:00Z"

            def release():
                if self.objects.get(path) is entry:
                    meta["finalizers"] = []
                    gone()
            self.later(self.finalizer_release, release)
        else:
            gone()

    def list_request(self, path, query):
        parts = path.split("/")
        if len(parts) == 6 and parts[1:4] == ["api", "v1", "namespaces"]:
            namespace, group, resource = parts[4], "", parts[5]
        elif len(parts) == 7 and parts[1] == "apis" and parts[4] == "namespaces":
            namespace, group, resource = parts[5], parts[2], parts[6]
        elif len(parts) == 5 and parts[1] == "apis":
            found = self.crd_instances(parts[2], parts[4])
            items = [{"name": n, "namespace": ns, "uid": u, "resourceVersion": "100"} for ns, n, u in found]
            return self.list_answer(items, 1, "more" if len(items) > 1 else None)
        else:
            return 404, b""
        return self.list_answer(self.listed(namespace, group, resource), 500)


# ---- the world: plan, synthetic journal, G9 receipt, fake cluster ----------------------------------------------------

class World:
    def __init__(self, mods, stages=FULL, register=True, children=True, extra=()):
        self.mods = mods
        self.objects, self.report, self.arn = bundle()
        self.project = self.report["project"]
        self.plan = k8s_runtime_receipt.Plan.from_report(self.report)
        self.manifests = {k8s_runtime_receipt.key_of(k8s_runtime_apply.identity_of(o)): o for o in self.objects}
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-destroy-engine-"))
        os.chmod(self.tmp, 0o700)
        self.root, self.g9_root = self.tmp / "runtime", self.tmp / "certs"
        self.clock = k8s_runtime_apply.FakeClock()
        self.cluster = FakeCluster(self.clock, self.project, self.manifests)
        self.cluster.atomic_transport = mods.transport
        self.fp = k8s_runtime_receipt.fingerprint(self.arn, KUBE_SYSTEM_UID)
        self.store = k8s_runtime_receipt.Store(self.root, self.fp, self.project, self.report["manifest_sha256"],
                                               self.report["input_sha256"], self.plan)
        self.counter = 100
        with self.store.lock():
            self.store.begin()
            for stage in stages:
                for identity in self.members(stage):
                    self.counter += 1
                    seq = self.store.intent(stage, identity, {"state": "absent"}, "create")
                    self.store.result(seq, identity, uid(self.counter), "100", 1, "applied")
                    self.cluster.put(identity, uid(self.counter))
                self.store.stage_done(stage)
            for identity in extra:  # applied members of a stage that never finished (a partial apply)
                self.counter += 1
                stage = self.plan.stage_of[k8s_runtime_receipt.key_of(identity)]
                seq = self.store.intent(stage, identity, {"state": "absent"}, "create")
                self.store.result(seq, identity, uid(self.counter), "100", 1, "applied")
                self.cluster.put(identity, uid(self.counter))
        if register:
            result = k8s_certs_receipt.register_with_receipt(self.project, self.arn, self.cluster.apply_secrets,
                                                             root=self.g9_root, server=self.cluster)
            assert result["result"] == "REGISTERED", result
        for identity in self.members_all():
            namespace = identity["namespace"]
            if namespace not in self.inventory_namespaces() or self.cluster.meta_of(identity) is None:
                continue
            if children and identity["kind"] == "Deployment":
                self.cluster.children(identity)
            if children and identity["kind"] == "Service":
                self.cluster.slice_of(identity)
        for namespace in self.inventory_namespaces():
            if self.cluster.meta_of(self.ident("Namespace", namespace)) is not None:
                self.cluster.leftovers(namespace)
        self.cluster.requests.clear()

    def inventory_namespaces(self):
        return ("istio-system", self.project + "-ingress", self.project + "-app")

    def members(self, stage):
        return [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|"))) for k in self.plan.members[stage]]

    def members_all(self):
        return [i for stage in self.plan.stage_order for i in self.members(stage)]

    @staticmethod
    def ident_of(kind, name, namespace=""):
        rows = [row for _, rows in k8s_runtime.load_stage_table("test") for row in rows
                if row[1] == kind and row[3] == name and row[2] == namespace]
        assert len(rows) == 1, (kind, name, namespace)
        return dict(zip(("apiVersion", "kind", "namespace", "name"), rows[0]))

    def ordered_paths(self, stage):
        order = k8s_runtime_destroy.KIND_ORDER
        members = self.members(stage)
        return [self.path(i) for i in sorted(members, key=lambda i: (order.index(i["kind"]), members.index(i)))]

    def ident(self, kind, name, namespace=""):
        found = [i for i in self.members_all() if i["kind"] == kind and i["name"] == name
                 and i["namespace"] == namespace]
        assert len(found) == 1, (kind, name, namespace)
        return found[0]

    def run(self, **kwargs):
        options = dict(expected_manifest=self.report["manifest_sha256"], expected_input=self.report["input_sha256"],
                       cluster_arn=self.arn)
        options.update(kwargs)
        objects = options.pop("objects", self.objects)
        root = options.pop("root", self.root)
        return self.mods.destroy.destroy(self.report, objects, root, self.g9_root, self.cluster, self.clock, **options)

    def journal(self):
        return [json.loads(line) for line in (self.store.dir / "journal.jsonl").read_text().splitlines()]

    def destroy_records(self, kind=None):
        return [r for r in self.journal() if r["type"].startswith("DESTROY") or r["type"] == "QUARANTINE"
                if kind is None or r["type"] == kind]

    def deletes(self):
        return [r for r in self.cluster.requests if r["method"] == "DELETE"]

    def deleted_paths(self):
        return [r["path"] for r in self.deletes()]

    def path(self, identity):
        return T.object_path(identity)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@contextlib.contextmanager
def world(mods, **kwargs):
    w = World(mods, **kwargs)
    try:
        yield w
    finally:
        w.cleanup()


def run_safely(w, **kwargs):
    """The engine's report, or a crash marker (a crash is never an assertion-detected mutation)."""
    return w.run(**kwargs)


# ---- A: positive end to end ------------------------------------------------------------------------------------------

def scenario_full_destroy(case, mods):
    with world(mods) as w:
        start = w.clock.now()
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("COMPLETE", None))
        case.assertGreaterEqual(w.clock.now() - start, 30, "the finalizer wait runs on the fake clock")
        case.assertEqual(result["counts"], {"deleted": 45, "absent_confirmed": 0, "never_created": 0})
        case.assertEqual(len(result["objects"]), 45)
        case.assertEqual(set(result["crds"]["istio"].values()), {"ZERO_INSTANCES"})
        case.assertEqual(len(result["crds"]["istio"]), 15)
        case.assertEqual(set(result["crds"]["controller"].values()), {"ZERO_INSTANCES"})
        case.assertEqual(len(result["crds"]["controller"]), 2)
        case.assertEqual((result["retained_crds"], result["crd_zero_instances"], result["crd_not_created"]),
                         (17, 17, 0))
        case.assertEqual([s["state"] for s in result["secrets"]["secrets"]], ["DELETED"] * 4)
        case.assertEqual(result["secrets"]["kube_system_webhook_tls"], "MET")
        case.assertEqual(result["namespaces"], {"test-app": "DELETED", "test-ingress": "DELETED",
                                                "istio-system": "DELETED"})
        case.assertEqual((result["executor"], result["live"], result["kube_system"]),
                         ("fake", "NOT_TESTED", "NEVER_DELETED"))
        # Every runtime object and Secret is gone; kube-system and the 17 CRDs stay.
        left = sorted(e["identity"]["kind"] for e in w.cluster.objects.values())
        case.assertEqual(left, ["CustomResourceDefinition"] * 17)
        paths = w.deleted_paths()
        case.assertEqual(len(paths), 45 + 4)
        case.assertFalse([p for p in paths if "customresourcedefinitions" in p], "no CRD DELETE")
        case.assertNotIn("/api/v1/namespaces/kube-system", paths)
        for request in w.deletes():
            case.assertIn('"preconditions":{"uid":"', request["body"])
        # Journal: every destroy step, one deleted result per non-CRD object, nothing open.
        state = k8s_runtime_receipt.load(w.store.dir, w.plan, {"fingerprint": w.fp, "project": w.project,
                                                              "manifest_sha256": w.report["manifest_sha256"],
                                                              "input_sha256": w.report["input_sha256"]})["state"]
        case.assertEqual(state["destroy_stages_done"], w.plan.destroy_order)
        case.assertIsNone(state["open_intent"])
        results = w.destroy_records("DESTROY_RESULT")
        case.assertEqual([r["outcome"] for r in results], ["deleted"] * 45)


def order_of(result, kind, name=None):
    return [i for i, k in enumerate(result["order"]) if k.split("|")[1] == kind
            and (name is None or k.split("|")[3] == name)]


def scenario_destroy_order(case, mods):
    with world(mods) as w:
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE")
        order = result["order"]
        stages = [w.plan.destroy_step(k) for k in order]
        case.assertEqual(stages, sorted(stages, key=w.plan.destroy_order.index), "reverse stage order")
        case.assertEqual(order[0].split("|")[1], "TargetGroupBinding", "the TargetGroupBinding goes first")
        case.assertEqual([k.split("|")[1] for k in order[-3:]], ["Namespace"] * 3, "namespaces last")
        case.assertEqual([k.split("|")[3] for k in order[-3:]], ["test-app", "test-ingress", "istio-system"])
        bindings = order_of(result, "ValidatingAdmissionPolicyBinding")
        policies = order_of(result, "ValidatingAdmissionPolicy")
        case.assertLess(max(bindings), min(policies), "policy bindings before policies")
        for stage in ("istiod", "controller"):
            webhooks = [i for i, k in enumerate(order) if w.plan.destroy_step(k) == stage and "Webhook" in k]
            deployments = [i for i, k in enumerate(order) if w.plan.destroy_step(k) == stage
                           and k.split("|")[1] == "Deployment"]
            case.assertLess(max(webhooks), min(deployments), "webhooks before their Deployment: " + stage)
        # The cluster saw the same order of DELETEs (the Secrets come from G9 before the namespaces).
        runtime = [p for p in w.deleted_paths() if "/secrets/" not in p]
        case.assertEqual(runtime, [w.path(dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|"))))
                                   for k in order])
        first_namespace = w.deleted_paths().index(w.path(w.ident("Namespace", "test-app")))
        secrets = [i for i, p in enumerate(w.deleted_paths()) if "/secrets/" in p]
        case.assertLess(max(secrets), first_namespace, "G9 Secret cleanup before the namespaces")
        # Every CRD instance LIST follows a fresh read of that CRD.
        requests = [r["path"] for r in w.cluster.requests]
        for i, path in enumerate(requests):
            if w.cluster.requests[i].get("query") == {"limit": "1"}:
                case.assertIn(T.CRD_PATH, requests[i - 1])


def scenario_rerun_completed(case, mods):
    with world(mods) as w:
        case.assertEqual(run_safely(w)["status"], "COMPLETE")
        w.cluster.requests.clear()
        again = run_safely(w)
        case.assertEqual((again["status"], again["reason"]), ("COMPLETE", None))
        case.assertEqual(w.deletes(), [], "a completed destroy never deletes again")
        case.assertEqual(again["counts"], {"deleted": 45, "absent_confirmed": 0, "never_created": 0})
        case.assertEqual(again["deletes"], 0)


def scenario_partial_apply(case, mods):
    with world(mods, stages=PARTIAL) as w:
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("COMPLETE", None))
        case.assertEqual(result["counts"], {"deleted": 3, "absent_confirmed": 0, "never_created": 42})
        case.assertEqual(set(result["crds"]["istio"].values()), {"ZERO_INSTANCES"})
        case.assertEqual(set(result["crds"]["controller"].values()), {"CRD_NOT_CREATED"})
        case.assertEqual((result["retained_crds"], result["crd_zero_instances"], result["crd_not_created"]),
                         (15, 15, 2), "CRD_NOT_CREATED is never a retained CRD")
        case.assertEqual(result["namespaces"], {"test-app": "NEVER_CREATED", "test-ingress": "DELETED",
                                                "istio-system": "DELETED"})
        case.assertEqual([s["state"] for s in result["secrets"]["secrets"]], ["DELETED"] * 4)
        never = [k for k, v in result["objects"].items() if v == "never_created"]
        case.assertIn("v1|Namespace||test-app", never)
        case.assertEqual(len(w.deleted_paths()), 3 + 4)
        namespaces = [p for p in w.deleted_paths() if p.startswith("/api/v1/namespaces/") and p.count("/") == 4]
        case.assertEqual(namespaces, ["/api/v1/namespaces/test-ingress", "/api/v1/namespaces/istio-system"])
        case.assertEqual(len(w.destroy_records("DESTROY_INTENT")), 3, "never-created objects get no INTENT")
        w.cluster.requests.clear()
        again = run_safely(w)
        case.assertEqual((again["status"], again["deletes"]), ("COMPLETE", 0))
        case.assertEqual(w.deletes(), [])
        case.assertEqual(again["namespaces"], {"test-app": "NEVER_CREATED", "test-ingress": "DELETED",
                                               "istio-system": "DELETED"}, "a rerun still reports every namespace")
        case.assertEqual([s["state"] for s in again["secrets"]["secrets"]], ["DELETED"] * 4, "fresh G9 evidence")


# ---- B: receipt and ownership ----------------------------------------------------------------------------------------

def scenario_receipt_preflight(case, mods):
    with world(mods, stages=PARTIAL) as w:
        missing = run_safely(w, root=w.tmp / "elsewhere")
        case.assertEqual((missing["status"], missing["reason"]), ("BLOCKED", "receipt:receipt_missing"))
        case.assertFalse((w.tmp / "elsewhere").exists(), "no receipt directory is created")
        case.assertEqual(w.deletes(), [])
        before = (w.store.dir / "journal.jsonl").read_bytes()
        w.cluster.kube_system = {"name": "kube-system", "uid": "99999999-2222-4333-8444-555555555555"}
        other = run_safely(w)
        case.assertEqual((other["status"], other["reason"]), ("BLOCKED", "receipt:receipt_missing"))
        w.cluster.kube_system = {"name": "kube-system", "uid": KUBE_SYSTEM_UID}
        wrong = run_safely(w, expected_manifest="c" * 64)
        case.assertEqual((wrong["status"], wrong["reason"]), ("BLOCKED", "sha_mismatch"))
        changed = copy.deepcopy(w.objects)
        changed[0]["metadata"].setdefault("labels", {})["x"] = "y"
        tampered = run_safely(w, objects=changed)
        case.assertEqual((tampered["status"], tampered["reason"]), ("BLOCKED", "objects_do_not_match_plan"))
        case.assertEqual((w.store.dir / "journal.jsonl").read_bytes(), before, "nothing written")
        case.assertEqual(w.deletes(), [])
        with open(w.store.dir / "journal.jsonl", "ab") as handle:
            handle.write(b"{not json}\n")
        corrupt = run_safely(w)
        case.assertEqual(corrupt["status"], "BLOCKED")
        case.assertTrue(corrupt["reason"].startswith("receipt:journal_corrupt"), corrupt["reason"])
        case.assertEqual(w.deletes(), [])


def scenario_receipt_pins(case, mods):
    with world(mods, stages=PARTIAL) as w:
        other = k8s_runtime_receipt.Store(w.tmp / "pinned", w.fp, w.project, "d" * 64, w.report["input_sha256"],
                                          w.plan)
        with other.lock():
            other.begin()
        result = run_safely(w, root=w.tmp / "pinned")
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "receipt:bundle_changed"))
        report = copy.deepcopy(w.report)
        report["stages"][-1]["objects"].pop()
        w.report = report
        changed = run_safely(w)
        case.assertEqual((changed["status"], changed["reason"]), ("BLOCKED", "plan_stage_identity_mismatch"))
        case.assertEqual(w.deletes(), [])


def scenario_open_apply_intent(case, mods):
    with world(mods, stages=PARTIAL) as w:
        identity = w.members("controller")[0]
        with w.store.lock():
            w.store.intent("controller", identity, {"state": "absent"}, "create")
        before = (w.store.dir / "journal.jsonl").read_bytes()
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "unresolved_apply_intent"))
        case.assertEqual((w.store.dir / "journal.jsonl").read_bytes(), before, "no DESTROY_BEGIN")
        case.assertEqual(w.deletes(), [])


def scenario_quarantine_preflight(case, mods):
    with world(mods, stages=PARTIAL) as w:
        identity = w.members("controller")[0]
        with w.store.lock():
            seq = w.store.intent("controller", identity, {"state": "absent"}, "create")
            w.store.quarantine(identity, uid(9), "creation_unproven")
        del seq
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "quarantined"))
        case.assertEqual(w.deletes(), [])


def scenario_foreign_object(case, mods):
    with world(mods, stages=PARTIAL) as w:
        configmap = w.members("istiod")[1]
        w.cluster.put(configmap, uid(77))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "not_owned:" + configmap["name"]))
        case.assertNotIn(w.path(configmap), w.deleted_paths(), "never adopted or deleted")


def scenario_uid_mismatch(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        w.cluster.put(validator, uid(78))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "uid_changed:istiod-default-validator"))
        case.assertEqual(w.deletes(), [])
        quarantine = w.destroy_records("QUARANTINE")
        case.assertEqual([(q["observed_uid"], q["reason"]) for q in quarantine],
                         [(uid(78), "uid_changed_before_delete")])
        again = run_safely(w)
        case.assertEqual((again["status"], again["reason"]), ("BLOCKED", "quarantined"))


def scenario_d13_ownership(case, mods):
    for change, expected in (("foreign", "foreign_field"), ("partial", "ownership_not_verified"),
                             ("update", "not_owned"), ("malformed", "ownership_not_verified")):
        with world(mods, stages=PARTIAL) as w:
            validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
            meta = w.cluster.meta_of(validator)
            if change == "foreign":
                meta["managedFields"].append({"manager": "kubectl-edit", "operation": "Update", "apiVersion":
                                              "admissionregistration.k8s.io/v1", "fieldsType": "FieldsV1",
                                              "fieldsV1": {"f:metadata": {"f:labels": {"f:edited": {}}}}})
            elif change == "partial":
                fields = meta["managedFields"][0]["fieldsV1"]
                fields.pop(sorted(fields)[0])
            elif change == "update":
                meta["managedFields"][0]["operation"] = "Update"
            else:
                meta["managedFields"].append(dict(meta["managedFields"][0]))
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]),
                             ("BLOCKED", expected + ":istiod-default-validator"), change)
            case.assertEqual(w.deletes(), [], change)
            case.assertEqual(w.destroy_records("DESTROY_INTENT"), [], change)
    with world(mods) as w:
        # The real controller's finalizer entry: D13 leaves it unverified; no allowlist widening.
        tgb = w.ident("TargetGroupBinding", "test-gateway", "test-ingress")
        w.cluster.meta_of(tgb)["managedFields"].append(
            {"manager": k8s_runtime_apply.LBC_MANAGER, "operation": "Update", "apiVersion": "elbv2.k8s.aws/v1beta1",
             "fieldsType": "FieldsV1", "fieldsV1": {"f:metadata": {"f:finalizers": {
                 "v:" + json.dumps(k8s_runtime_apply.LBC_FINALIZER): {}}}}})
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "ownership_not_verified:test-gateway"))
        case.assertEqual(w.deletes(), [])


def scenario_istiod_webhook_unverified(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        w.cluster.meta_of(validator)["managedFields"].append(
            {"manager": k8s_runtime_apply.ISTIOD_MANAGER, "operation": "Update",
             "apiVersion": "admissionregistration.k8s.io/v1", "fieldsType": "FieldsV1",
             "fieldsV1": {"f:webhooks": {'k:{"name":"validation.istio.io"}': {"f:clientConfig": {
                 "f:caBundle": {}}}}}})
        result = run_safely(w)
        # Metadata carries no webhook values: istiod's entry cannot be matched to a live webhook, so it never proves
        # ownership (never guessed, never allowlisted here).
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "foreign_field:" + validator["name"]))
        case.assertNotIn(w.path(validator), w.deleted_paths())


def scenario_crd_creation_evidence(case, mods):
    with world(mods, stages=PARTIAL) as w:
        crd = next(i for i in w.members("controller") if i["kind"] == "CustomResourceDefinition")
        with w.store.lock():
            seq = w.store.intent("controller", crd, {"state": "absent"}, "create")
            w.store.result(seq, crd, None, None, None, "failed")
        result = run_safely(w)
        case.assertEqual(result["status"], "UNKNOWN")
        case.assertEqual(result["reason"], "crd:" + crd["name"] + ":crd_creation_evidence")
        case.assertEqual(result["crds"]["controller"][crd["name"]], "UNKNOWN")
    with world(mods, stages=PARTIAL) as w:
        crd = next(i for i in w.members("controller") if i["kind"] == "CustomResourceDefinition")
        w.cluster.put(crd, uid(79))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "crd:" + crd["name"] + ":crd_not_owned_by_receipt"))


# ---- C: ordering and dependencies ------------------------------------------------------------------------------------

def scenario_tgb_finalizer(case, mods):
    with world(mods) as w:
        w.cluster.finalizer_release = None
        start = w.clock.now()
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "tgb_finalizer_stuck:test-gateway"))
        case.assertGreaterEqual(w.clock.now() - start, T.TGB_FINALIZER_TIMEOUT_SECONDS)
        case.assertLess(w.clock.now() - start, T.TGB_FINALIZER_TIMEOUT_SECONDS + 30)
        tgb = w.ident("TargetGroupBinding", "test-gateway", "test-ingress")
        case.assertEqual(w.deleted_paths(), [w.path(tgb)], "nothing the binding depends on is deleted")
        case.assertEqual(w.cluster.meta_of(tgb)["finalizers"], [k8s_runtime_apply.LBC_FINALIZER], "never stripped")
        case.assertEqual([r["outcome"] for r in w.destroy_records("DESTROY_RESULT")], [])


def scenario_foreign_tgb(case, mods):
    with world(mods) as w:
        w.cluster.extra("test-ingress", "elbv2.k8s.aws", "targetgroupbindings", "other-binding")
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "foreign_target_group_binding"))
        case.assertEqual(w.deletes(), [])


def inject_after_delete(w, identity, action):
    path = w.path(identity)
    done = []

    def hook(request):
        if request["method"] == "DELETE" and request["path"] == path and not done:
            done.append(True)
            action()
    w.cluster.hooks.append(hook)


def scenario_tgb_remains(case, mods):
    for stage, last in (("admission", ("ValidatingAdmissionPolicy", "test-no-lb-service")),
                        ("controller", ("ValidatingAdmissionPolicy", "test-target-registration"))):
        with world(mods) as w:
            gateway = w.ident("Gateway", "test-backend", "test-ingress")
            trigger = gateway if stage == "admission" else w.ident(last[0], last[1])
            inject_after_delete(w, trigger, lambda w=w: w.cluster.extra("test-ingress", "elbv2.k8s.aws",
                                                                        "targetgroupbindings", "late-binding"))
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"),
                             stage)
            stage_paths = {w.path(i) for i in w.members(stage) if i["kind"] != "CustomResourceDefinition"}
            case.assertFalse(stage_paths & set(w.deleted_paths()), stage + " objects stay")


def scenario_ingress_services(case, mods):
    with world(mods) as w:
        service = w.ident("Service", "test-gateway", "test-ingress")
        w.cluster.service_types[w.path(service)] = "LoadBalancer"
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "load_balancer_service_remains"))
        admission = {w.path(i) for i in w.members("admission")}
        case.assertFalse(admission & set(w.deleted_paths()))
    with world(mods) as w:
        w.cluster.extra("test-ingress", "", "services", "debug-lb")
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "unknown_service:debug-lb"))


def scenario_istio_instances(case, mods):
    with world(mods, stages=PARTIAL) as w:
        w.cluster.instances[("networking.istio.io", "virtualservices")] = [("test-ingress", "leftover", uid(80))]
        result = run_safely(w)
        case.assertEqual(result["status"], "BLOCKED")
        case.assertEqual(result["reason"], "crd:virtualservices.networking.istio.io:crd_instances_remain")
        case.assertEqual(w.deletes(), [], "no Istio webhook while a custom resource remains")
        case.assertEqual(result["crds"]["istio"]["virtualservices.networking.istio.io"], "BLOCKED")


# ---- D: inventory and Secret safety ----------------------------------------------------------------------------------

def namespace_deleted(w, name):
    return w.path(w.ident("Namespace", name)) in w.deleted_paths()


def scenario_unknown_objects(case, mods):
    cases = (("", "pods", "debug"), ("", "configmaps", "app-config"), ("", "secrets", "app-credentials"),
             ("", "serviceaccounts", "kube-root-ca.crt"), ("", "secrets", "kube-root-ca.crt"),
             ("", "services", "extra"))
    for group, resource, name in cases:
        with world(mods, stages=PARTIAL) as w:
            w.cluster.extra("istio-system", group, resource, name)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]),
                             ("BLOCKED", "unknown_object:istio-system:" + name), name)
            case.assertFalse(namespace_deleted(w, "istio-system"), name)
            case.assertFalse([p for p in w.deleted_paths() if p.endswith("/" + name)], "never deleted: " + name)


def scenario_istiod_leftover(case, mods):
    with world(mods, stages=PARTIAL) as w:
        w.cluster.extra("istio-system", "coordination.k8s.io", "leases", "istio-namespace-controller-election")
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "istiod_leftover:istio-system:istio-namespace-controller-election"))
        case.assertFalse(namespace_deleted(w, "istio-system"))


def scenario_g9_receipt(case, mods):
    with world(mods, stages=PARTIAL, register=False) as w:
        result = run_safely(w)
        case.assertEqual(result["status"], "BLOCKED")
        case.assertTrue(result["reason"].startswith("g9:"), result["reason"])
        case.assertEqual(w.deletes(), [])
    with world(mods, stages=PARTIAL) as w:
        receipt_file = w.g9_root / w.fp["id"] / "registration.json"
        receipt_file.write_bytes(receipt_file.read_bytes()[:-5])
        result = run_safely(w)
        case.assertEqual(result["status"], "BLOCKED")
        case.assertTrue(result["reason"].startswith("g9:"), result["reason"])
        case.assertEqual(w.deletes(), [])


def scenario_g9_incomplete(case, mods):
    with world(mods, stages=PARTIAL) as w:
        meta = w.cluster.meta_of(T.secret_identities(w.project)[0])
        meta["labels"]["app.kubernetes.io/part-of"] = "other"
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "g9_cleanup_incomplete:label_project"))
        # A stopped run still reports each judged object separately: never-created objects are not deletions.
        case.assertEqual(result["counts"], {"deleted": 1, "absent_confirmed": 0, "never_created": 41})
        case.assertFalse(namespace_deleted(w, "istio-system"))
        case.assertFalse(namespace_deleted(w, "test-ingress"))


def scenario_owned_children(case, mods):
    with world(mods, stages=ISTIOD) as w:
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE", "children garbage-collected within the wait")
        case.assertFalse([p for p in w.deleted_paths() if "/replicasets/" in p or "/pods/" in p], "never direct")
    for setup in ("stuck", "terminating"):
        with world(mods, stages=ISTIOD) as w:
            if setup == "stuck":
                w.cluster.gc_delay = None
            else:
                for resource in ("replicasets", "pods"):
                    for meta in w.cluster.extras[("istio-system", "apps" if resource == "replicasets" else "",
                                                  resource)].values():
                        meta["finalizers"] = ["example.com/stuck"]
                        meta["deletionTimestamp"] = "2026-11-24T00:00:00Z"
            start = w.clock.now()
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]),
                             ("BLOCKED", "owned_child_remains:istio-system"), setup)
            case.assertFalse(namespace_deleted(w, "istio-system"), setup)
            case.assertGreaterEqual(w.clock.now() - start, T.OWNED_CHILD_TIMEOUT_SECONDS, setup)
            case.assertFalse([p for p in w.deleted_paths() if "/replicasets/" in p or "/pods/" in p])


def scenario_owner_chain(case, mods):
    for kind in ("wrong_uid", "no_controller", "foreign_owner", "pod_unverified", "slice_wrong_uid"):
        with world(mods, stages=ISTIOD, children=False) as w:
            istiod = w.ident("Deployment", "istiod-test-v1", "istio-system")
            owner = w.cluster.owner(istiod)
            name = "orphan-rs"
            if kind == "wrong_uid":
                owner["uid"] = uid(81)
            elif kind == "no_controller":
                owner["controller"] = False
            elif kind == "foreign_owner":
                owner["name"] = "other-deployment"
            if kind == "pod_unverified":
                name = "orphan-pod"  # its ReplicaSet is not listed: the chain to a receipt UID is unprovable
                w.cluster.extra("istio-system", "", "pods", name, owners=[
                    {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "istiod-test-v1-gone", "uid": uid(88),
                     "controller": True}])
            elif kind == "slice_wrong_uid":
                name = "orphan-slice"
                service = w.cluster.owner(w.ident("Service", "istiod-test-v1", "istio-system"))
                service["uid"] = uid(89)
                w.cluster.extra("istio-system", "discovery.k8s.io", "endpointslices", name, owners=[service])
            else:
                w.cluster.extra("istio-system", "apps", "replicasets", name, owners=[owner])
            w.cluster.gc_delay = None
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]),
                             ("BLOCKED", "unknown_object:istio-system:" + name), kind)
            case.assertFalse(namespace_deleted(w, "istio-system"), kind)


def namespace_race(w, name, add):
    """Add an object once the second inventory of a namespace (after its DESTROY_INTENT) has started."""
    path = w.path(w.ident("Namespace", name))
    seen = {"get": False, "discovery": 0, "done": False}

    def hook(request):
        if request["method"] == "GET" and request["path"] == path and request["headers"].get("Accept") == \
                T.METADATA_ACCEPT:
            seen["get"] = True
        elif seen["get"] and request["path"] == "/api" and not seen["done"]:
            seen["discovery"] += 1
            if seen["discovery"] == 2:
                seen["done"] = True
                add()
    w.cluster.hooks.append(hook)


def scenario_inventory_race(case, mods):
    for resource, name, reason in (("secrets", "late-secret", "unknown_object:istio-system:late-secret"),
                                   ("events", "late.event", "namespace_changed_after_inventory:istio-system")):
        with world(mods, stages=PARTIAL) as w:
            namespace_race(w, "istio-system", lambda w=w: w.cluster.extra("istio-system", "", resource, name))
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", reason), name)
            case.assertFalse(namespace_deleted(w, "istio-system"), name)
            intents = [r for r in w.destroy_records("DESTROY_INTENT") if r["identity"]["name"] == "istio-system"]
            case.assertEqual(len(intents), 1, "the race was seen after the INTENT, before the DELETE")


def scenario_inventory_failures(case, mods):
    def lists(resource, answer):
        return lambda r: answer if r["headers"].get("Accept") == T.LIST_ACCEPT and \
            r["path"] == "/api/v1/namespaces/istio-system/" + resource else None
    token_page = {"kind": "PartialObjectMetadataList", "apiVersion": "meta.k8s.io/v1",
                  "metadata": {"resourceVersion": "100", "continue": "c1"}, "items": []}
    full_secret = {"kind": "PartialObjectMetadataList", "apiVersion": "meta.k8s.io/v1",
                   "metadata": {"resourceVersion": "100"},
                   "items": [{"metadata": {"name": "s", "namespace": "istio-system", "uid": uid(82)},
                              "data": {"k": "dmFsdWU="}}]}
    cases = (
        (lists("secrets", (403, b"")), ("BLOCKED", "inventory:istio-system:inventory_forbidden")),
        (lists("secrets", (500, b"")), ("UNKNOWN", "inventory:istio-system:unexpected_status")),
        (lists("configmaps", (200, json.dumps(token_page).encode())),
         ("UNKNOWN", "inventory:istio-system:list_continue_repeated")),
        (lists("secrets", (200, json.dumps(full_secret).encode())),
         ("UNKNOWN", "inventory:istio-system:response_not_metadata_only")),
    )
    for fault, expected in cases:
        with world(mods, stages=PARTIAL) as w:
            w.cluster.faults.append(fault)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), expected)
            case.assertFalse(namespace_deleted(w, "istio-system"), expected)
    with world(mods, stages=PARTIAL) as w:
        lists_v1 = w.cluster.discovery

        def without_pods():
            found, groups = lists_v1()
            found["v1"] = [r for r in found["v1"] if r["name"] != "pods"]
            return found, groups
        w.cluster.discovery = without_pods
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("UNKNOWN", "discovery:discovery_required_resource_missing"))
        case.assertEqual(w.deletes(), [], "the ingress gate needs discovery before the first DELETE")


def scenario_namespace_uid(case, mods):
    with world(mods, stages=PARTIAL) as w:
        namespace = w.ident("Namespace", "test-ingress")
        w.cluster.meta_of(namespace)["uid"] = uid(83)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "uid_changed:test-ingress"))
        case.assertFalse(namespace_deleted(w, "test-ingress"))
        case.assertEqual([q["reason"] for q in w.destroy_records("QUARANTINE")], ["uid_changed_before_delete"])


def scenario_namespace_termination(case, mods):
    with world(mods, stages=PARTIAL) as w:
        w.cluster.ns_termination = None
        start = w.clock.now()
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "namespace_termination_timeout:test-ingress"))
        case.assertGreaterEqual(w.clock.now() - start, T.NAMESPACE_TERMINATION_TIMEOUT_SECONDS)
        case.assertFalse(namespace_deleted(w, "istio-system"), "the next namespace waits")


# ---- E: CRDs ---------------------------------------------------------------------------------------------------------

def scenario_crd_safety(case, mods):
    gateways = "gateways.networking.istio.io"

    def change(w, edit):
        crd = w.ident("CustomResourceDefinition", gateways)
        edit(w, crd, w.cluster.objects[w.path(crd)])
    edits = (
        ("missing", lambda w, crd, entry: w.cluster.objects.pop(w.path(crd)), "crd_claimed_but_absent"),
        ("uid", lambda w, crd, entry: entry["meta"].update(uid=uid(84)), "crd_uid_mismatch"),
        ("established", lambda w, crd, entry: entry.update(crd_status={"conditions": [
            {"type": "Established", "status": "False"}]}), "crd_not_established"),
        ("storage", lambda w, crd, entry: entry.update(crd_spec=dict(
            copy.deepcopy(w.manifests[k8s_runtime_receipt.key_of(crd)]["spec"]),
            versions=[{"name": "v1", "served": True, "storage": False},
                      {"name": "v1alpha3", "served": True, "storage": True}])), "crd_storage_version_mismatch"),
    )
    for label, edit, reason in edits:
        with world(mods, stages=PARTIAL) as w:
            change(w, edit)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "crd:" + gateways + ":" + reason),
                             label)
            case.assertEqual(w.deletes(), [], label)
    with world(mods, stages=PARTIAL) as w:
        w.cluster.faults.append(lambda r: (500, b"") if r.get("query") == {"limit": "1"} and "/gateways" in r["path"]
                                else None)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "crd:" + gateways + ":unexpected_status"))
        case.assertEqual(result["crds"]["istio"][gateways], "UNKNOWN")
    with world(mods, stages=PARTIAL) as w:
        # A custom resource appears after the last namespace: the final check refuses COMPLETE.
        inject_after_delete(w, w.ident("Namespace", "istio-system"), lambda w=w: w.cluster.instances.update(
            {("networking.istio.io", "sidecars"): [("default", "late", uid(85))]}))
        result = run_safely(w)
        case.assertEqual(result["status"], "BLOCKED")
        case.assertEqual(result["reason"], "crd:sidecars.networking.istio.io:crd_instances_remain")
        case.assertFalse([p for p in w.deleted_paths() if "customresourcedefinitions" in p], "no CRD DELETE")


# ---- F: crash, resume and deadline -----------------------------------------------------------------------------------

def scenario_intent_before_delete(case, mods):
    with world(mods, stages=PARTIAL) as w:
        with mock.patch.object(k8s_runtime_receipt.Store, "destroy_intent",
                               side_effect=k8s_runtime_receipt.ReceiptError("journal_write_incomplete")):
            result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "receipt:journal_write_incomplete"))
        case.assertEqual(w.deletes(), [], "no DELETE without a durable INTENT")


def crash_on_delete(w, path, after):
    state = {"crashed": False}

    def fault(request):
        if request["method"] == "DELETE" and request["path"] == path and not state["crashed"]:
            state["crashed"] = True
            if after:
                w.cluster.answer(request)
            else:
                w.cluster.requests.pop()  # it never reached the server
            raise Crash()
        return None
    w.cluster.faults.append(fault)


def scenario_crash_before_delete(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        crash_on_delete(w, w.path(validator), after=False)
        with case.assertRaises(Crash):
            run_safely(w)
        case.assertEqual([r["type"] for r in w.destroy_records()], ["DESTROY_BEGIN"] + ["DESTROY_STAGE_DONE"] * 7
                         + ["DESTROY_INTENT"])
        case.assertIsNotNone(w.cluster.meta_of(validator), "the DELETE never reached the cluster")
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE")
        records = [(r["type"], r.get("outcome")) for r in w.destroy_records() if r["type"] != "DESTROY_STAGE_DONE"]
        case.assertEqual(records[:5], [("DESTROY_BEGIN", None), ("DESTROY_INTENT", None),
                                       ("DESTROY_RESULT", "failed"), ("DESTROY_INTENT", None),
                                       ("DESTROY_RESULT", "deleted")])
        case.assertEqual(w.deleted_paths().count(w.path(validator)), 1)
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        crash_on_delete(w, w.path(validator), after=False)
        with case.assertRaises(Crash):
            run_safely(w)
        w.cluster.put(validator, uid(92))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "uid_changed_after_intent:istiod-default-validator"))
        case.assertEqual([(q["observed_uid"], q["reason"]) for q in w.destroy_records("QUARANTINE")],
                         [(uid(92), "delete_unproven")])
        case.assertEqual(w.deletes(), [], "the replacement is never deleted")


def scenario_crash_after_delete(case, mods):
    with world(mods) as w:
        tgb = w.ident("TargetGroupBinding", "test-gateway", "test-ingress")
        crash_on_delete(w, w.path(tgb), after=True)
        with case.assertRaises(Crash):
            run_safely(w)
        case.assertIsNotNone(w.cluster.meta_of(tgb)["deletionTimestamp"], "deletion requested, finalizer pending")
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE")
        records = [(r["type"], r.get("seq"), r.get("outcome")) for r in w.destroy_records()][:3]
        # Already terminating with the same UID: rechecked, then the same INTENT waits for absence; no new DELETE.
        case.assertEqual([r[0] for r in records], ["DESTROY_BEGIN", "DESTROY_INTENT", "DESTROY_RESULT"])
        case.assertEqual((records[2][1], records[2][2]), (records[1][1], "absent_confirmed"))
        case.assertEqual(w.deleted_paths().count(w.path(tgb)), 1, "no DELETE is resent for a terminating object")
        case.assertEqual(result["objects"][k8s_runtime_receipt.key_of(tgb)], "absent_confirmed")
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        crash_on_delete(w, w.path(validator), after=True)
        with case.assertRaises(Crash):
            run_safely(w)
        case.assertIsNone(w.cluster.meta_of(validator))
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE")
        case.assertEqual(w.deleted_paths().count(w.path(validator)), 1, "never deleted twice")
        records = [(r["type"], r.get("outcome")) for r in w.destroy_records() if r["type"] != "DESTROY_STAGE_DONE"]
        case.assertEqual(records[2], ("DESTROY_RESULT", "absent_confirmed"))
        case.assertEqual(result["objects"][k8s_runtime_receipt.key_of(validator)], "absent_confirmed")
        case.assertEqual(result["counts"], {"deleted": 2, "absent_confirmed": 1, "never_created": 42})


def scenario_crash_after_result(case, mods):
    with world(mods, stages=PARTIAL) as w:
        original = k8s_runtime_receipt.Store._write_snapshot
        calls = {"n": 0}

        def flaky(store, value):
            if value["state"].get("destroy", {}).get("destroyed") and calls["n"] == 0:
                calls["n"] += 1
                raise Crash()
            return original(store, value)
        with mock.patch.object(k8s_runtime_receipt.Store, "_write_snapshot", flaky):
            with case.assertRaises(Crash):
                run_safely(w)
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        snapshot = json.loads((w.store.dir / "receipt.json").read_text())
        case.assertLess(snapshot["journal_records"], len(w.journal()), "the snapshot is stale")
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE")
        case.assertEqual(w.deleted_paths().count(w.path(validator)), 1, "no duplicate DELETE after a stale snapshot")


def scenario_delete_responses(case, mods):
    name = "istiod-default-validator"
    for answer, expected in (((202, b"{}"), ("BLOCKED", "delete_not_confirmed:" + name)),
                             ((409, b"{}"), ("UNKNOWN", "delete:uid_precondition_failed:" + name))):
        with world(mods, stages=PARTIAL) as w:
            validator = w.ident("ValidatingWebhookConfiguration", name)
            w.cluster.faults.append(lambda r, w=w, answer=answer, v=validator: answer
                                    if r["method"] == "DELETE" and r["path"] == w.path(v) else None)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), expected)
            case.assertEqual([r for r in w.destroy_records("DESTROY_RESULT") if r["outcome"] == "deleted"], [])
            case.assertIsNotNone(w.cluster.meta_of(validator))
            case.assertNotIn(k8s_runtime_receipt.key_of(validator), result["objects"])
    for answer, expected in (((404, b""), ("UNKNOWN", "read:not_found_untrusted")),
                             ((403, b""), ("BLOCKED", "read:forbidden"))):
        with world(mods, stages=PARTIAL) as w:
            validator = w.ident("ValidatingWebhookConfiguration", name)
            w.cluster.faults.append(lambda r, w=w, answer=answer, v=validator: answer
                                    if r["method"] == "GET" and r["path"] == w.path(v) else None)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), expected)
            case.assertEqual(w.deletes(), [], "a bare 404 or a 403 is never absence")
            case.assertNotIn(k8s_runtime_receipt.key_of(validator), result["objects"])


def scenario_recreated(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        inject_after_delete(w, validator, lambda w=w: w.cluster.put(validator, uid(86)))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "recreated_after_delete:istiod-default-validator"))
        case.assertEqual(w.deleted_paths().count(w.path(validator)), 1, "the new UID is never deleted")
        case.assertEqual([(q["observed_uid"], q["reason"]) for q in w.destroy_records("QUARANTINE")],
                         [(uid(86), "recreated_after_delete")])
        again = run_safely(w)
        case.assertEqual((again["status"], again["reason"]), ("BLOCKED", "quarantined"))
    with world(mods, stages=PARTIAL) as w:
        case.assertEqual(run_safely(w)["status"], "COMPLETE")
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        w.cluster.put(validator, uid(87))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "recreated_after_destroy:istiod-default-validator"))
        case.assertEqual(w.deleted_paths().count(w.path(validator)), 1, "a completed step is revalidated, not redone")
        case.assertEqual([(q["observed_uid"], q["reason"]) for q in w.destroy_records("QUARANTINE")],
                         [(uid(87), "recreated_after_delete")])


def scenario_deadline(case, mods):
    with world(mods) as w:
        w.cluster.finalizer_release = 120
        start = w.clock.now()
        result = run_safely(w, deadline_seconds=60)
        case.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "read:deadline_exceeded"))
        case.assertEqual(len(w.deletes()), 1, "no DELETE after the deadline")
        case.assertLessEqual(w.clock.now() - start, 60 + 5)
        case.assertEqual([r["outcome"] for r in w.destroy_records("DESTROY_RESULT")], [])
    with world(mods, stages=PARTIAL) as w:
        seen = {"n": 0}

        def late(request):
            if request["path"] == "/api/v1/namespaces/kube-system" and "query" in request:
                seen["n"] += 1
                if seen["n"] == 2:
                    w.clock.sleep(3600)
            return None
        w.cluster.faults.append(late)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "read:deadline_exceeded"))
        case.assertEqual(seen["n"], 2, "the deadline hit the final check, after every step")
    with world(mods, stages=PARTIAL) as w:
        w.cluster.latency["/secrets/"] = 25
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "g9_cleanup_incomplete:transport_timeout"))
        case.assertFalse(namespace_deleted(w, "test-ingress"))


def scenario_bounded_server(case, mods):
    clock = k8s_runtime_apply.FakeClock()
    deadline = T.Deadline(clock, 100)
    calls = []

    def server(request):
        calls.append(request)
        clock.sleep(request)
        return 200, b""
    bounded = mods.destroy.bounded_server(server, deadline)
    case.assertEqual(bounded(20), (200, b""), "20 s is within the bound")
    with case.assertRaises(TimeoutError):
        bounded(21)
    clock.sleep(100)
    with case.assertRaises(TimeoutError):
        bounded(0)
    case.assertEqual(calls, [20, 21], "no request starts after the deadline")


def scenario_real_refused(case, mods):
    with world(mods, stages=PARTIAL) as w:
        result = run_safely(w, transport_kind="https")
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "real_transport_not_implemented"))
        case.assertEqual(w.cluster.requests, [])

        class RealClock:
            """Any clock other than the fake one is refused, even one that works."""
            def __init__(self):
                self.value = 0.0

            def now(self):
                self.value += 1.0
                return self.value

            def sleep(self, seconds):
                self.value += seconds
        w.clock = RealClock()
        w.cluster.clock = w.clock
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "fake_clock_required"))
        case.assertEqual(w.cluster.requests, [])
    with case.assertRaises(k8s_runtime.GateError):
        k8s_runtime.check_operation("destroy")


def scenario_owned_absent(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        del w.cluster.objects[w.path(validator)]
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("COMPLETE", None))
        case.assertEqual(result["objects"][k8s_runtime_receipt.key_of(validator)], "absent_confirmed")
        case.assertEqual(result["counts"], {"deleted": 2, "absent_confirmed": 1, "never_created": 42})
        case.assertNotIn(w.path(validator), w.deleted_paths(), "an absent object gets no DELETE")


def scenario_namespace_classes(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        w.cluster.extra("istio-system", "", "configmaps", "stray", uid_value=w.cluster.meta_of(validator)["uid"])
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "runtime_object:istio-system:stray"))
        case.assertFalse(namespace_deleted(w, "istio-system"))
    with world(mods, stages=PARTIAL) as w:
        cacerts = next(i for i in T.secret_identities(w.project) if i["name"] == "cacerts")
        path = T.object_path(cacerts, w.cluster.secret_keys)
        w.cluster.hooks.append(lambda r, w=w: w.cluster.extra("istio-system", "", "secrets", "cacerts")
                               if r["method"] == "DELETE" and r["path"] == path else None)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "k8s_certs_secret:istio-system:cacerts"))
        case.assertFalse(namespace_deleted(w, "istio-system"))
    with world(mods, stages=PARTIAL) as w:
        namespace = w.ident("Namespace", "test-ingress")
        w.cluster.meta_of(namespace)["managedFields"].append(
            {"manager": "kubectl-label", "operation": "Update", "apiVersion": "v1", "fieldsType": "FieldsV1",
             "fieldsV1": {"f:metadata": {"f:labels": {"f:team": {}}}}})
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "foreign_field:test-ingress"))
        case.assertFalse(namespace_deleted(w, "test-ingress"))


def scenario_crd_discovery(case, mods):
    with world(mods, stages=PARTIAL) as w:
        w.cluster.served["elbv2.k8s.aws/v1beta1"] = [{"name": "targetgroupbindings", "kind": "TargetGroupBinding",
                                                       "namespaced": True, "verbs": ["get", "list"]}]
        result = run_safely(w)
        # The TargetGroupBinding plural is served without its CRD: that CRD is not CRD_NOT_CREATED, and the
        # cluster-wide TargetGroupBinding gate (before admission) stops on it.
        case.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "tgb_crd:crd_discovery_inconsistent"))
        case.assertEqual(w.deletes(), [])
    with world(mods, stages=PARTIAL) as w:
        # The cluster-scoped IngressClassParams plural is served without its CRD: the final check refuses COMPLETE.
        w.cluster.served["elbv2.k8s.aws/v1beta1"] = [{"name": "ingressclassparams", "kind": "IngressClassParams",
                                                       "namespaced": False, "verbs": ["get", "list"]}]
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("UNKNOWN", "crd:ingressclassparams.elbv2.k8s.aws:crd_discovery_inconsistent"))
        case.assertEqual(result["crds"]["controller"]["ingressclassparams.elbv2.k8s.aws"], "UNKNOWN")


def scenario_final_checks(case, mods):
    with world(mods, stages=PARTIAL) as w:
        validator = w.ident("ValidatingWebhookConfiguration", "istiod-default-validator")
        inject_after_delete(w, w.ident("Namespace", "istio-system"), lambda w=w: w.cluster.put(validator, uid(90)))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "recreated_after_destroy:istiod-default-validator"))
    with world(mods, stages=PARTIAL) as w:
        inject_after_delete(w, w.ident("Namespace", "istio-system"),
                            lambda w=w: w.cluster.put_secret("aws-load-balancer-controller-tls"))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "g9_cleanup_incomplete:recreated_after_cleanup"))
    with world(mods, stages=PARTIAL) as w:
        # Only the very last read (after the final CRD check) sees another kube-system UID.
        state = {"namespace_gone": False, "last_crd": False}
        inject_after_delete(w, w.ident("Namespace", "istio-system"), lambda: state.update(namespace_gone=True))
        tgb_crd = T.CRD_PATH + "targetgroupbindings.elbv2.k8s.aws"
        other = json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                            "metadata": {"name": "kube-system", "uid": uid(91)}}).encode()

        def late(request):
            if state["namespace_gone"] and request["path"] == tgb_crd:
                state["last_crd"] = True
            if state["last_crd"] and "query" in request and request["path"] == "/api/v1/namespaces/kube-system":
                return 200, other
            return None
        w.cluster.faults.append(late)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "kube_system_not_retained"))


# ---- B4B-F01: the reviewed stage table is the only stage layout ------------------------------------------------------


def scenario_stage_identity(case, mods):
    with world(mods, stages=PARTIAL) as w:
        before = (w.store.dir / "journal.jsonl").read_bytes()

        def stages_of(report):
            return {s["name"]: s for s in report["stages"]}
        swapped = copy.deepcopy(w.report)
        by_name = stages_of(swapped)
        a, b = by_name["gateway"]["objects"], by_name["istiod"]["objects"]
        a[0], b[0] = b[0], a[0]  # the same counts, two identities in each other's stage
        reordered = copy.deepcopy(w.report)
        objects = stages_of(reordered)["admission"]["objects"]
        objects[0], objects[1] = objects[1], objects[0]
        version = copy.deepcopy(w.report)
        version["runtime_contract_version"] = k8s_runtime.CONTRACT_VERSION + 1
        cases = ((swapped, "plan_stage_identity_mismatch"), (reordered, "plan_stage_identity_mismatch"),
                 (version, "runtime_contract_version_mismatch"))
        original = w.report
        for report, reason in cases:
            w.report = report
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", reason))
        w.report = original
        # The bundle in another order than the table (its own pins, so only the layout differs).
        bundle = list(w.objects)
        bundle[2], bundle[3] = bundle[3], bundle[2]
        pinned = copy.deepcopy(w.report)
        pinned["manifest_sha256"] = k8s_runtime_receipt.digest(k8s_runtime_receipt.canonical(bundle).encode())
        w.report = pinned
        result = run_safely(w, objects=bundle, expected_manifest=pinned["manifest_sha256"])
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "bundle_stage_identity_mismatch"))
        w.report = original
        case.assertEqual((w.store.dir / "journal.jsonl").read_bytes(), before, "no DESTROY_BEGIN")
        case.assertEqual(w.deletes(), [])


# ---- B4B-F02: existing receipt only, revalidated under the lock ------------------------------------------------------


def after_preflight(w, mods, action):
    """Run once with ``action`` executed between the preflight and the locked revalidation."""
    original = mods.destroy.Engine.preflight

    def preflight(engine, *args):
        original(engine, *args)
        action()
    with mock.patch.object(mods.destroy.Engine, "preflight", preflight):
        return run_safely(w)


def scenario_existing_receipt_only(case, mods):
    def quarantine(w):
        with w.store.lock():
            w.store.quarantine(w.members("controller")[0], uid(93), "creation_unproven")

    def apply_intent(w):
        with w.store.lock():
            w.store.intent("controller", w.members("controller")[0], {"state": "absent"}, "create")
    cases = (
        ("directory", lambda w: shutil.rmtree(w.store.dir), "receipt:receipt_missing"),
        ("journal", lambda w: os.unlink(w.store.dir / "journal.jsonl"), "receipt:journal_missing"),
        ("snapshot", lambda w: os.unlink(w.store.dir / "receipt.json"), "receipt:receipt_snapshot_missing"),
        ("quarantine", quarantine, "quarantined"),
        ("apply_intent", apply_intent, "unresolved_apply_intent"),
        ("fingerprint", lambda w: w.cluster.kube_system.update(uid=uid(106)), "fingerprint_changed"),
    )
    for label, action, reason in cases:
        with world(mods, stages=PARTIAL) as w:
            result = after_preflight(w, mods, lambda w=w, action=action: action(w))
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", reason), label)
            case.assertEqual(w.deletes(), [], label)
            journal = w.store.dir / "journal.jsonl"
            if journal.exists():
                case.assertNotIn("DESTROY_BEGIN", journal.read_text(), label)
            case.assertFalse(journal.exists() and label in ("directory", "journal"), "never initialised: " + label)
    with world(mods, stages=PARTIAL) as w:
        other = k8s_runtime_receipt.Store(w.root, w.fp, w.project, w.report["manifest_sha256"],
                                          w.report["input_sha256"], w.plan)
        with other.lock():
            result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "receipt:receipt_locked"))
        case.assertEqual(w.deletes(), [])


def scenario_store_existing_only(case, mods):
    r = mods.receipt
    tmp = Path(tempfile.mkdtemp(prefix="k8s-store-existing-"))
    os.chmod(tmp, 0o700)
    try:
        plan = k8s_runtime_receipt.Plan.from_report(bundle()[1])
        fp = r.fingerprint("arn:aws:eks:ca-central-1:000000000000:cluster/test-dev-eks", KUBE_SYSTEM_UID)
        with case.assertRaises(r.ReceiptError) as raised:
            r.Store(tmp / "state", fp, "test", "a" * 64, "b" * 64, plan, existing_only=True)
        case.assertEqual(str(raised.exception), "receipt_missing")
        case.assertFalse((tmp / "state").exists(), "existing_only never creates the root")
        (tmp / "state").mkdir(mode=0o700)
        (tmp / "state" / fp["id"]).mkdir(mode=0o700)
        store = r.Store(tmp / "state", fp, "test", "a" * 64, "b" * 64, plan, existing_only=True)
        with store.lock():
            with case.assertRaises(r.ReceiptError) as raised:
                store.begin()
        case.assertEqual(str(raised.exception), "receipt_missing")
        case.assertFalse((tmp / "state" / fp["id"] / "journal.jsonl").exists(), "no HEADER")
        # Apply keeps its own contract: a new store initialises exactly once.
        fresh = r.Store(tmp / "apply", fp, "test", "a" * 64, "b" * 64, plan)
        with fresh.lock():
            case.assertEqual(fresh.begin(), "CREATED")
        existing = r.Store(tmp / "apply", fp, "test", "a" * 64, "b" * 64, plan, existing_only=True)
        with existing.lock():
            case.assertEqual(existing.begin(), "CURRENT")
            os.unlink(existing.dir / "receipt.json")
            with case.assertRaises(r.ReceiptError) as raised:
                existing.begin()
        case.assertEqual(str(raised.exception), "receipt_snapshot_missing", "even a HEADER-only journal")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- B4B-F03: G9 registration and the cluster fingerprint ------------------------------------------------------------


def scenario_g9_eligibility(case, mods):
    with world(mods, stages=PARTIAL, register=False) as w:
        def partial_apply(plan):
            results = w.cluster.apply_secrets(plan)
            results[1]["outcome"] = "conflict"  # one Secret not confirmed: the receipt is schema-valid INCOMPLETE
            return results
        registered = k8s_certs_receipt.register_with_receipt(w.project, w.arn, partial_apply, root=w.g9_root,
                                                             server=w.cluster)
        case.assertEqual(registered["result"], "INCOMPLETE")
        w.cluster.requests.clear()
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "g9_registration_incomplete"))
        case.assertEqual(w.deletes(), [], "neither a runtime nor a G9 DELETE")
        case.assertNotIn("DESTROY_BEGIN", (w.store.dir / "journal.jsonl").read_text())
    with world(mods, stages=PARTIAL) as w:
        # A valid G9 receipt of another fingerprint, and none of the runtime's: it is never used.
        other_fp = k8s_runtime_receipt.fingerprint(w.arn, uid(94))
        directory = w.g9_root / w.fp["id"]
        document = json.loads((directory / "registration.json").read_text())
        document["cluster"] = {"cluster_arn": other_fp["cluster_arn"], "kube_system_uid": other_fp["kube_system_uid"],
                               "fingerprint_id": other_fp["id"]}
        target = k8s_certs_receipt.receipt_directory(w.g9_root, other_fp, create=True)
        with k8s_certs_receipt.locked(target):
            k8s_certs_receipt.write_receipt(target, document, w.project, other_fp)
        shutil.rmtree(directory)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "g9:receipt_missing"))
        case.assertEqual(w.deletes(), [])


def scenario_fingerprint_binding(case, mods):
    with world(mods) as w:
        # kube-system changes after the first runtime DELETE: the next step stops before any further deletion.
        tgb = w.ident("TargetGroupBinding", "test-gateway", "test-ingress")
        inject_after_delete(w, tgb, lambda w=w: w.cluster.kube_system.update(uid=uid(95)))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "fingerprint_changed"))
        case.assertEqual(w.deleted_paths(), [w.path(tgb)], "no further DELETE in the same ingress step")
    with world(mods, stages=PARTIAL) as w:
        # Only G9's own kube-system read sees another cluster: G9 stops before any Secret request.
        other = json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                            "metadata": {"name": "kube-system", "uid": uid(96)}}).encode()
        w.cluster.faults.append(lambda r: (200, other) if "query" not in r
                                and r["path"] == "/api/v1/namespaces/kube-system" else None)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "fingerprint_changed"))
        case.assertFalse([p for p in w.deleted_paths() if "/secrets/" in p], "no G9 DELETE")
        case.assertFalse(namespace_deleted(w, "test-ingress"))
        case.assertFalse([r for r in w.cluster.requests if "/secrets/" in r["path"]], "no Secret request at all")
    clock = k8s_runtime_apply.FakeClock()
    deadline = T.Deadline(clock, 100)
    other = json.dumps({"metadata": {"uid": uid(97)}}).encode()
    bounded = mods.destroy.bounded_server(lambda request: (200, other), deadline, KUBE_SYSTEM_UID)
    with case.assertRaises(mods.destroy.FingerprintChanged):
        bounded({"path": "/api/v1/namespaces/kube-system"})
    case.assertTrue(bounded.tripped)


# ---- B4B-F04: TargetGroupBinding dependencies, cluster-wide and fresh ------------------------------------------------


def scenario_tgb_cluster_wide(case, mods):
    def admission_deleted(w):
        return [p for p in w.deleted_paths() if p in {w.path(i) for i in w.members("admission")}]
    with world(mods) as w:
        w.cluster.instances[("elbv2.k8s.aws", "targetgroupbindings")] = [("other-team", "theirs", uid(98))]
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"))
        case.assertEqual(admission_deleted(w), [], "a binding in another namespace blocks admission")
    with world(mods) as w:
        tgb = w.ident("TargetGroupBinding", "test-gateway", "test-ingress")
        inject_after_delete(w, tgb, lambda w=w: w.cluster.instances.update(
            {("elbv2.k8s.aws", "targetgroupbindings"): [("other-team", "late", uid(99))]}))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"))
        case.assertEqual(admission_deleted(w), [])
    with world(mods) as w:
        binding = w.ident("ValidatingAdmissionPolicyBinding", "test-target-registration")
        inject_after_delete(w, binding, lambda w=w: w.cluster.instances.update(
            {("elbv2.k8s.aws", "targetgroupbindings"): [("other-team", "mid", uid(100))]}))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"))
        case.assertEqual(admission_deleted(w), [w.path(binding)], "fresh evidence before every admission DELETE")
    with world(mods) as w:
        webhook = w.ident("MutatingWebhookConfiguration", "aws-load-balancer-controller-webhook")
        inject_after_delete(w, webhook, lambda w=w: w.cluster.instances.update(
            {("elbv2.k8s.aws", "targetgroupbindings"): [("other-team", "controller", uid(107))]}))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"))
        controller = {w.path(i) for i in w.members("controller")}
        case.assertEqual([p for p in w.deleted_paths() if p in controller], [w.path(webhook)],
                         "fresh evidence before every controller DELETE")
    with world(mods) as w:
        binding = w.ident("ValidatingAdmissionPolicyBinding", "test-target-registration")
        service = w.ident("Service", "test-gateway", "test-ingress")
        inject_after_delete(w, binding, lambda w=w: w.cluster.service_types.update({w.path(service): "LoadBalancer"}))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "load_balancer_service_remains"))
        case.assertEqual(admission_deleted(w), [w.path(binding)])


def scenario_tgb_crd_reads(case, mods):
    tgb_list = "/apis/elbv2.k8s.aws/v1beta1/targetgroupbindings"
    for answer, latency, expected in (((403, b""), 0, ("BLOCKED", "tgb_crd:crd_list_forbidden")),
                                      ((500, b""), 0, ("UNKNOWN", "tgb_crd:unexpected_status")),
                                      (None, 25, ("UNKNOWN", "tgb_crd:request_timeout"))):
        with world(mods) as w:
            if answer is not None:
                w.cluster.faults.append(lambda r, answer=answer: answer if r["path"] == tgb_list else None)
            else:
                w.cluster.latency[tgb_list + "$"] = latency
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), expected)
            admission = {w.path(i) for i in w.members("admission")}
            case.assertFalse(admission & set(w.deleted_paths()), expected)


def scenario_service_identity(case, mods):
    with world(mods) as w:
        service = w.ident("Service", "test-gateway", "test-ingress")
        runtime_uid = w.cluster.meta_of(service)["uid"]
        del w.cluster.objects[w.path(service)]
        w.cluster.extra("test-ingress", "", "services", "imposter", uid_value=runtime_uid)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "unknown_service:imposter"))
        case.assertFalse({w.path(i) for i in w.members("admission")} & set(w.deleted_paths()))


def scenario_istio_midstage(case, mods):
    with world(mods, stages=ISTIOD) as w:
        injector = w.ident("MutatingWebhookConfiguration", "istio-sidecar-injector-test-v1")
        inject_after_delete(w, injector, lambda w=w: w.cluster.instances.update(
            {("networking.istio.io", "virtualservices"): [("test-ingress", "late", uid(101))]}))
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "crd:virtualservices.networking.istio.io:crd_instances_remain"))
        webhooks = [w.path(i) for i in w.members("istiod") if "Webhook" in i["kind"]]
        case.assertEqual([p for p in w.deleted_paths() if p in webhooks], [w.path(injector)])
    with world(mods, stages=ISTIOD) as w:
        injector = w.ident("MutatingWebhookConfiguration", "istio-sidecar-injector-test-v1")
        deployment = w.ident("Deployment", "istiod-test-v1", "istio-system")
        seen = {"done": False}

        def recreate(request):
            if request["method"] == "GET" and request["path"] == w.path(deployment) and not seen["done"]:
                seen["done"] = True
                w.cluster.put(injector, uid(102))
        w.cluster.hooks.append(recreate)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "webhook_remains:istio-sidecar-injector-test-v1"))
        case.assertNotIn(w.path(deployment), w.deleted_paths(), "no Deployment while its webhook exists")


def scenario_completed_stage_dependency(case, mods):
    with world(mods) as w:
        first_binding_writer = w.ordered_paths("binding_writer")[0]
        crash_on_delete(w, first_binding_writer, after=False)
        with case.assertRaises(Crash):
            run_safely(w)
        w.cluster.instances[("elbv2.k8s.aws", "targetgroupbindings")] = [("other-team", "back", uid(103))]
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"))
        case.assertFalse({w.path(i) for i in w.members("admission")} & set(w.deleted_paths()))


# ---- B4B-F05: CRDs judged by exact group, version and plural ---------------------------------------------------------


def scenario_crd_mapping(case, mods):
    gateways = "gateways.networking.istio.io"
    with world(mods, stages=PARTIAL, extra=(World.ident_of("CustomResourceDefinition",
                                                           "targetgroupbindings.elbv2.k8s.aws"),)) as w:
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("COMPLETE", None))
        case.assertEqual(result["crds"]["controller"], {"ingressclassparams.elbv2.k8s.aws": "CRD_NOT_CREATED",
                                                        "targetgroupbindings.elbv2.k8s.aws": "ZERO_INSTANCES"},
                         "another CRD of the same group being served is no reason to refuse CRD_NOT_CREATED")
        case.assertEqual((result["retained_crds"], result["crd_zero_instances"], result["crd_not_created"]),
                         (16, 16, 1))
    for label, setup, expected in (
            ("plural_missing", lambda c: c.hidden_versions.update({("networking.istio.io", "gateways"):
                                                                   {"v1", "v1beta1", "v1alpha3"}}),
             ("UNKNOWN", "crd:" + gateways + ":crd_discovery_mapping_missing")),
            ("storage_missing", lambda c: c.hidden_versions.update({("networking.istio.io", "gateways"): {"v1"}}),
             ("UNKNOWN", "crd:" + gateways + ":crd_discovery_mapping_missing")),
            ("scope", lambda c: c.scope_override.update({("networking.istio.io", "gateways"): False}),
             ("BLOCKED", "crd:" + gateways + ":crd_discovery_scope_mismatch"))):
        with world(mods, stages=PARTIAL) as w:
            setup(w.cluster)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), expected, label)
            case.assertEqual(w.deletes(), [], label)


def scenario_stale_discovery(case, mods):
    with world(mods, stages=PARTIAL) as w:
        t = mods.transport
        policy = t.DestroyPolicy(w.project, k8s_runtime_receipt.plan_identities(w.plan), discovery=True)
        fake = t.open_destroy_transport("fake", policy, w.cluster, t.Deadline(w.clock, 100))
        old = fake.discover_all()["evidence"]
        case.assertIn(["networking.istio.io", "v1", "gateways", "Gateway", True],
                      fake.discovery_payload(old)["resources"])
        fake.discover_all()
        with case.assertRaises(t.TransportError) as raised:
            fake.discovery_payload(old)
        case.assertEqual(str(raised.exception), "evidence_invalid", "stale discovery evidence is refused")


# ---- B4B-F06: namespace final gate -----------------------------------------------------------------------------------


def on_namespace_get(w, name, nth, action):
    """Run ``action`` at the ``nth`` metadata read of a namespace (2 = the final gate after its INTENT)."""
    path = w.path(w.ident("Namespace", name))
    seen = {"n": 0}

    def hook(request):
        if request["method"] == "GET" and request["path"] == path and request["headers"].get("Accept") == \
                T.METADATA_ACCEPT:
            seen["n"] += 1
            if seen["n"] == nth:
                action()
    w.cluster.hooks.append(hook)


def scenario_namespace_final_gate(case, mods):
    def event(w):
        return w.cluster.extras[("istio-system", "", "events")]["startup.17a3"]

    def configmap(w):
        return w.cluster.extras[("istio-system", "", "configmaps")]["kube-root-ca.crt"]
    # The first namespace read is before the first inventory; the second is the final gate after the INTENT.
    cases = (
        ("unknown", 2, lambda w: w.cluster.extra("istio-system", "", "configmaps", "late-config"),
         "unknown_object:istio-system:late-config"),
        ("ownership", 1, lambda w: w.cluster.meta_of(w.ident("Namespace", "istio-system"))["managedFields"].append(
            {"manager": "kubectl-label", "operation": "Update", "apiVersion": "v1", "fieldsType": "FieldsV1",
             "fieldsV1": {"f:metadata": {"f:labels": {"f:team": {}}}}}), "foreign_field:istio-system"),
        ("same_uid_metadata", 2, lambda w: event(w).update(finalizers=["example.com/hold"]),
         "namespace_changed_after_inventory:istio-system"),
        ("owner_chain", 2, lambda w: configmap(w).update(ownerReferences=[
            {"apiVersion": "v1", "kind": "ConfigMap", "name": "other", "uid": uid(104), "controller": False}]),
         "namespace_changed_after_inventory:istio-system"),
        ("g9", 2, lambda w: w.cluster.put_secret("cacerts"), "g9_cleanup_incomplete:recreated_after_cleanup"),
    )
    for label, nth, change, reason in cases:
        with world(mods, stages=PARTIAL) as w:
            on_namespace_get(w, "istio-system", nth, lambda w=w, change=change: change(w))
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", reason), label)
            case.assertFalse(namespace_deleted(w, "istio-system"), label)
            closed = [r for r in w.destroy_records("DESTROY_RESULT") if r["identity"]["name"] == "istio-system"]
            case.assertEqual([r["outcome"] for r in closed], ["failed"], "the INTENT is closed: " + label)


def scenario_owner_chain_current(case, mods):
    with world(mods, stages=ISTIOD) as w:
        # The ReplicaSet is collected but its Pod stays terminating: the chain is unprovable from the current
        # inventory, so the Pod is unknown (never assumed from an earlier poll).
        pods = w.cluster.extras[("istio-system", "", "pods")]
        for meta in pods.values():
            meta["finalizers"] = ["example.com/stuck"]
            meta["deletionTimestamp"] = "2026-11-24T00:00:00Z"
        w.cluster.gc_delay = 40
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "unknown_object:istio-system:istiod-test-v1-6b7f-x2"))
        case.assertFalse(namespace_deleted(w, "istio-system"))


# ---- B4B-F07: local wait deadlines ----------------------------------------------------------------------------------


def scenario_local_wait(case, mods):
    for release, latency, expected in ((599, 0, "COMPLETE"), (600, 0, "COMPLETE"), (601, 0, "BLOCKED"),
                                       (597, 3, "BLOCKED")):
        with world(mods) as w:
            w.cluster.finalizer_release = release
            tgb_path = w.path(w.ident("TargetGroupBinding", "test-gateway", "test-ingress"))
            if latency:  # each read of the binding takes 3 s: the NotFound read started at 600 s ends at 603 s
                w.cluster.faults.append(lambda r, w=w, p=tgb_path: w.clock.sleep(latency)
                                        if r["method"] == "GET" and r["path"] == p else None)
            result = run_safely(w, deadline_seconds=3600)
            if expected == "COMPLETE":
                case.assertEqual((result["status"], result["reason"]), ("COMPLETE", None), (release, latency))
                tgb = "elbv2.k8s.aws/v1beta1|TargetGroupBinding|test-ingress|test-gateway"
                case.assertEqual(result["objects"].get(tgb), "deleted", (release, latency))
            else:
                case.assertEqual((result["status"], result["reason"]),
                                 ("BLOCKED", "tgb_finalizer_stuck:test-gateway"), (release, latency))
                case.assertEqual(len(w.deletes()), 1, "nothing after the stuck binding")


def scenario_local_wait_unit(case, mods):
    engine = mods.destroy.Engine.__new__(mods.destroy.Engine)
    engine.clock = k8s_runtime_apply.FakeClock()
    engine.deadline = T.Deadline(engine.clock, 3600)
    reads = {"n": 0}

    def late_absent(identity):
        reads["n"] += 1
        engine.clock.sleep(601 if reads["n"] == 1 else 0)  # the first answer arrives after the 600 s wait
        return None
    engine.read = late_absent
    namespace = {"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "test-ingress"}
    with case.assertRaises(mods.destroy.DestroyStop) as raised:
        engine.wait_absent(namespace, uid(105))
    case.assertEqual(raised.exception.reason, "namespace_termination_timeout:test-ingress",
                     "a NotFound after the local wait deadline is never evidence")
    engine.clock, calls = k8s_runtime_apply.FakeClock(), []
    engine.deadline = T.Deadline(engine.clock, 3600)

    def inventory(namespace):
        calls.append(engine.clock.now())
        engine.clock.sleep(601 if len(calls) == 1 else 0)
        return []
    engine.inventory = inventory
    engine.state = {"objects": {}}
    engine.project = "test"
    with case.assertRaises(mods.destroy.DestroyStop) as raised:
        engine.namespace_contents("istio-system", wait=True)
    case.assertEqual(raised.exception.reason, "owned_child_remains:istio-system",
                     "an empty inventory after the 600 s wait is never evidence")


# ---- unit tests ------------------------------------------------------------------------------------------------------

class DestroyEngineTests(unittest.TestCase):
    def test_full_synthetic_receipt_destroys_45_objects_and_4_secrets_and_keeps_17_crds(self):
        scenario_full_destroy(self, real_mods())

    def test_reverse_order_with_dependency_safety(self):
        scenario_destroy_order(self, real_mods())

    def test_rerun_of_a_completed_destroy_sends_no_delete(self):
        scenario_rerun_completed(self, real_mods())

    def test_partial_apply_cleanup_judges_never_created_objects_one_by_one(self):
        scenario_partial_apply(self, real_mods())
        scenario_owned_absent(self, real_mods())


class DestroyReceiptTests(unittest.TestCase):
    def test_missing_corrupt_other_fingerprint_and_unpinned_inputs_stop(self):
        scenario_receipt_preflight(self, real_mods())
        scenario_receipt_pins(self, real_mods())

    def test_unresolved_apply_intent_and_quarantine_stop_before_any_write(self):
        scenario_open_apply_intent(self, real_mods())
        scenario_quarantine_preflight(self, real_mods())

    def test_foreign_object_and_uid_mismatch_are_never_deleted(self):
        scenario_foreign_object(self, real_mods())
        scenario_uid_mismatch(self, real_mods())

    def test_d13_field_ownership_is_required(self):
        scenario_d13_ownership(self, real_mods())
        scenario_istiod_webhook_unverified(self, real_mods())

    def test_crd_creation_evidence_and_foreign_crd_are_not_crd_not_created(self):
        scenario_crd_creation_evidence(self, real_mods())
        scenario_crd_discovery(self, real_mods())


class DestroyOrderingTests(unittest.TestCase):
    def test_target_group_binding_finalizer_wait_and_timeout(self):
        scenario_tgb_finalizer(self, real_mods())

    def test_foreign_or_remaining_target_group_binding_stops(self):
        scenario_foreign_tgb(self, real_mods())
        scenario_tgb_remains(self, real_mods())

    def test_load_balancer_and_unknown_services_stop_admission(self):
        scenario_ingress_services(self, real_mods())

    def test_istio_custom_resources_stop_webhook_deletion(self):
        scenario_istio_instances(self, real_mods())


class DestroyInventoryTests(unittest.TestCase):
    def test_unknown_objects_and_secrets_stop_namespace_deletion(self):
        scenario_unknown_objects(self, real_mods())
        scenario_istiod_leftover(self, real_mods())

    def test_g9_receipt_and_cleanup_gate_namespaces(self):
        scenario_g9_receipt(self, real_mods())
        scenario_g9_incomplete(self, real_mods())

    def test_owned_children_and_owner_chains(self):
        scenario_owned_children(self, real_mods())
        scenario_owner_chain(self, real_mods())

    def test_objects_added_after_the_inventory_stop_the_namespace_delete(self):
        scenario_inventory_race(self, real_mods())

    def test_incomplete_or_forbidden_inventory_is_never_empty(self):
        scenario_inventory_failures(self, real_mods())

    def test_namespace_uid_and_termination_bounds(self):
        scenario_namespace_uid(self, real_mods())
        scenario_namespace_termination(self, real_mods())

    def test_runtime_objects_k8s_certs_secrets_and_foreign_namespace_fields_stop(self):
        scenario_namespace_classes(self, real_mods())


class DestroyCrdTests(unittest.TestCase):
    def test_retained_crd_verification_and_instance_counts(self):
        scenario_crd_safety(self, real_mods())


class DestroyRecoveryTests(unittest.TestCase):
    def test_no_delete_without_a_durable_intent(self):
        scenario_intent_before_delete(self, real_mods())

    def test_crash_before_and_after_delete_and_after_result(self):
        scenario_crash_before_delete(self, real_mods())
        scenario_crash_after_delete(self, real_mods())
        scenario_crash_after_result(self, real_mods())

    def test_delete_responses_are_never_completion(self):
        scenario_delete_responses(self, real_mods())

    def test_recreated_objects_are_quarantined_and_completed_steps_revalidated(self):
        scenario_recreated(self, real_mods())

    def test_global_deadline_and_g9_bounds(self):
        scenario_deadline(self, real_mods())
        scenario_bounded_server(self, real_mods())

    def test_real_transport_clock_and_cli_are_refused(self):
        scenario_real_refused(self, real_mods())

    def test_completion_rechecks_objects_secrets_and_kube_system(self):
        scenario_final_checks(self, real_mods())

    def test_local_wait_deadlines_are_strict(self):
        scenario_local_wait(self, real_mods())
        scenario_local_wait_unit(self, real_mods())


# ---- consolidated independent review residuals: F03-R / F04-R / F05-R / F06-R ------------------------

def scenario_stage_fingerprint(case, mods):
    with world(mods, stages=PARTIAL) as w:
        result = run_safely(w)
        case.assertEqual(result["status"], "COMPLETE")
        original = mods.destroy.Engine.revalidate
        seen = []

        def revalidate(engine, step):
            seen.append(step)
            original(engine, step)
            if len(seen) == 1:
                w.cluster.kube_system["uid"] = uid(192)
        with mock.patch.object(mods.destroy.Engine, "revalidate", revalidate):
            result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "fingerprint_changed"))
        case.assertEqual(len(seen), 1, "a changed fingerprint blocks even a completed step before revalidation")


def scenario_g9_locked_binding(case, mods):
    for incomplete in (False, True):
        with world(mods, stages=PARTIAL) as w:
            case.assertEqual(k8s_certs_receipt.cleanup(w.project, w.arn, root=w.g9_root, server=w.cluster)["result"],
                             "COMPLETE")
            w.cluster.requests.clear()
            original = k8s_certs_receipt.cleanup

            def change_registration(*args, **kwargs):
                def replacement(plan):
                    results = w.cluster.apply_secrets(plan)
                    if incomplete:
                        results[0]["outcome"] = "conflict"
                    return results
                registered = k8s_certs_receipt.register_with_receipt(
                    w.project, w.arn, replacement, root=w.g9_root, server=w.cluster)
                case.assertEqual(registered["result"], "INCOMPLETE" if incomplete else "REGISTERED")
                return original(*args, **kwargs)
            with mock.patch.object(k8s_certs_receipt, "cleanup", change_registration):
                result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "g9:g9_registration_changed"))
            case.assertFalse([r for r in w.deletes() if "/secrets/" in r["path"]])

    with world(mods, stages=PARTIAL) as w:
        seen = []

        def changed(request):
            if request["method"] == "DELETE" and "/secrets/" in request["path"] and not seen:
                seen.append(request["path"])
                w.cluster.kube_system["uid"] = uid(190)
        w.cluster.hooks.append(changed)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "fingerprint_changed"))
        case.assertEqual([r["path"] for r in w.deletes() if "/secrets/" in r["path"]], seen)
        case.assertEqual(len(seen), 1)


def scenario_exact_tgb_binding(case, mods):
    for group, resource, name in (("elbv2.k8s.aws", "targetgroupbindings", "imposter"),
                                  ("", "pods", "test-gateway")):
        with world(mods) as w:
            ident = w.ident("TargetGroupBinding", "test-gateway", "test-ingress")
            original_uid = w.cluster.meta_of(ident)["uid"]
            del w.cluster.objects[w.path(ident)]
            w.cluster.extra("test-ingress", group, resource, name, uid_value=original_uid)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "foreign_target_group_binding"))
            case.assertEqual(w.deletes(), [])
    with world(mods) as w:
        w.cluster.extra("other-team", "elbv2.k8s.aws", "targetgroupbindings", "foreign-extra")
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "target_group_binding_remains"))
        case.assertFalse({w.path(i) for i in w.members("admission")} & set(w.deleted_paths()))
    with world(mods) as w:
        binding = w.ident("ValidatingAdmissionPolicyBinding", "test-target-registration")
        policy = w.ident("ValidatingAdmissionPolicy", "test-target-registration")
        # Let the independent confirmation see absence once; recreate after that response.
        state = {"deleted": False, "reads": 0}

        def recreate(request):
            if request["path"] == w.path(binding):
                if request["method"] == "DELETE":
                    state["deleted"] = True
                elif state["deleted"] and request["method"] == "GET":
                    state["reads"] += 1
                    if state["reads"] == 1:
                        w.cluster.put(binding, uid(191))
        w.cluster.hooks.append(recreate)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "admission_binding_remains:test-target-registration"))
        case.assertNotIn(w.path(policy), w.deleted_paths())
    with world(mods) as w:
        binding = w.ident("ValidatingAdmissionPolicyBinding", "test-target-registration")
        policy = w.ident("ValidatingAdmissionPolicy", "test-target-registration")
        state = {"deleted": False, "confirmed": False}

        def after(request):
            if request["path"] == w.path(binding):
                if request["method"] == "DELETE":
                    state["deleted"] = True
                elif state["deleted"] and request["method"] == "GET":
                    state["confirmed"] = True
        def unreadable(request):
            if state["confirmed"] and request["method"] == "GET" and request["path"] == w.path(binding):
                return 403, b""
            return None
        w.cluster.hooks.append(after)
        w.cluster.faults.append(unreadable)
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]), ("BLOCKED", "read:forbidden"))
        case.assertNotIn(w.path(policy), w.deleted_paths())


def scenario_crd_kind_listable(case, mods):
    with world(mods, stages=PARTIAL) as w:
        w.cluster.discovery_overrides[("networking.istio.io", "gateways")] = {"kind": "WrongKind"}
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("BLOCKED", "crd:gateways.networking.istio.io:crd_discovery_kind_or_scope_mismatch"))
        case.assertEqual(w.deletes(), [])
    with world(mods) as w:
        w.cluster.discovery_overrides[("elbv2.k8s.aws", "ingressclassparams")] = {"verbs": ["get"]}
        result = run_safely(w)
        case.assertEqual((result["status"], result["reason"]),
                         ("UNKNOWN", "crd:ingressclassparams.elbv2.k8s.aws:crd_discovery_not_listable"))


def scenario_namespace_atomic_races(case, mods):
    for mode in ("after_secret_list", "before_delete", "before_delete_object", "ownership",
                 "allowed_leftover", "same_uid_metadata", "terminating", "terminating_object", "hidden"):
        with world(mods, stages=PARTIAL) as w:
            name = "istio-system"
            ident = w.ident("Namespace", name)
            path = w.path(ident)
            secret_list = "/api/v1/namespaces/" + name + "/secrets"
            state = {"lists": 0, "added": False}

            def add():
                state["added"] = True
                w.cluster.extra(name, "", "secrets", "late-foreign-secret")

            def after(request):
                if request["method"] == "GET" and request["path"] == secret_list:
                    state["lists"] += 1
                    if mode == "after_secret_list" and state["lists"] == 2:
                        add()
                if mode in ("terminating", "terminating_object") and request["method"] == "DELETE" \
                        and request["path"] == path:
                    if mode == "terminating":
                        add()
                    else:
                        state["added"] = True
                        w.cluster.extra(name, "", "configmaps", "late-foreign-config")
            def before(request):
                if request["method"] == "DELETE" and request["path"] == path:
                    if mode == "before_delete":
                        add()
                    elif mode == "before_delete_object":
                        state["added"] = True
                        w.cluster.extra(name, "", "configmaps", "late-foreign-config")
                    elif mode == "ownership":
                        state["added"] = True
                        w.cluster.meta_of(ident)["managedFields"] = []
                    elif mode == "allowed_leftover":
                        state["added"] = True
                        w.cluster.extra(name, "", "events", "late-event")
                    elif mode == "same_uid_metadata":
                        state["added"] = True
                        w.cluster.extras[(name, "", "events")]["startup.17a3"]["ownerReferences"] = [
                            {"apiVersion": "v1", "kind": "ConfigMap", "name": "foreign",
                             "uid": uid(193), "controller": False}]
                    elif mode == "hidden":
                        state["added"] = True
                        w.cluster.extra(name, "undiscovered.example.com", "objects", "foreign-object")
                return None
            w.cluster.hooks.append(after)
            w.cluster.faults.append(before)
            result = run_safely(w)
            case.assertTrue(state["added"], mode)
            case.assertEqual(result["status"], "BLOCKED", mode)
            case.assertIsNotNone(w.cluster.meta_of(ident), mode)
            if mode in ("after_secret_list", "before_delete", "terminating"):
                case.assertIn("late-foreign-secret", w.cluster.extras[(name, "", "secrets")], mode)
            elif mode in ("before_delete_object", "terminating_object"):
                case.assertIn("late-foreign-config", w.cluster.extras[(name, "", "configmaps")], mode)
            elif mode == "allowed_leftover":
                case.assertIn("late-event", w.cluster.extras[(name, "", "events")])
            elif mode == "hidden":
                case.assertIn("foreign-object", w.cluster.extras[(name, "undiscovered.example.com", "objects")])
            records = [r for r in w.destroy_records("DESTROY_RESULT") if r["identity"]["name"] == name]
            case.assertFalse([r for r in records if r["outcome"] in ("deleted", "absent_confirmed")], mode)
            if mode not in ("terminating", "terminating_object"):
                case.assertEqual([r["outcome"] for r in records], ["failed"], mode)

    # Lost response and crash before acceptance: new evidence only when a DELETE must actually be retried.
    for after in (False, True):
        with world(mods, stages=PARTIAL) as w:
            ident = w.ident("Namespace", "test-ingress")
            path = w.path(ident)
            crash_on_delete(w, path, after)
            with case.assertRaises(Crash):
                run_safely(w)
            result = run_safely(w)
            case.assertEqual((result["status"], result["reason"]), ("COMPLETE", None), after)
            case.assertEqual(w.deleted_paths().count(path), 1, after)

    with world(mods, stages=PARTIAL) as w:
        ident = w.ident("Namespace", "test-ingress")
        path = w.path(ident)
        crash_on_delete(w, path, after=True)
        with case.assertRaises(Crash):
            run_safely(w)
        w.cluster.extra("test-ingress", "", "secrets", "late-resume-secret")
        result = run_safely(w)
        case.assertEqual(result["status"], "BLOCKED")
        case.assertEqual(w.deleted_paths().count(path), 1)
        case.assertIsNotNone(w.cluster.meta_of(ident))
        case.assertIn("late-resume-secret", w.cluster.extras[("test-ingress", "", "secrets")])


def scenario_namespace_atomic_boundary(case, mods):
    t = mods.transport
    with world(mods, stages=PARTIAL) as w:
        k8s_certs_receipt.cleanup(w.project, w.arn, root=w.g9_root, server=w.cluster)
        identity = w.ident("Namespace", "test-ingress")
        uid_value = w.cluster.meta_of(identity)["uid"]
        other_identity = w.ident("Namespace", "istio-system")
        other_uid = w.cluster.meta_of(other_identity)["uid"]
        with case.assertRaises(t.TransportError):
            t.Policy([identity], [identity])
        policy = t.DestroyPolicy(w.project, [identity, other_identity],
                                 owned_uids={t.identity_key(identity): uid_value,
                                             t.identity_key(other_identity): other_uid},
                                 inventory=True, discovery=True)

        def new_fake(server=w.cluster):
            return t.open_destroy_transport("fake", policy, server, t.Deadline(w.clock, 3600))

        def evidence(fake):
            fake.get_metadata(identity)
            fake.get_metadata({"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "kube-system"})
            found = fake.discover_all()
            listed = fake.inventory_namespace(found["evidence"], identity["name"])
            case.assertEqual(listed["status"], "COMPLETE")
            return listed["evidence"]

        fake = new_fake()
        token = evidence(fake)
        request = t.runtime_delete_request(policy, identity, uid_value)
        before = len(w.deletes())
        with case.assertRaises(t.TransportError):
            fake.send(request)
        case.assertEqual(len(w.deletes()), before)
        forged = t.Evidence(policy, "namespace_inventory", token.payload_for(policy, "namespace_inventory"))
        for other, candidate in ((fake, forged), (new_fake(), token)):
            with case.assertRaises(t.TransportError):
                other.delete_runtime(identity, uid_value, namespace_evidence=candidate)
        with case.assertRaises(t.TransportError):
            fake.delete_runtime(other_identity, other_uid, namespace_evidence=token)
        tampered = evidence(fake)
        object.__setattr__(tampered, "_data", tampered._data + " ")
        with case.assertRaises(t.TransportError):
            fake.delete_runtime(identity, uid_value, namespace_evidence=tampered)
        token = evidence(fake)
        fake.discover_all()
        with case.assertRaises(t.TransportError):
            fake.delete_runtime(identity, uid_value, namespace_evidence=token)
        case.assertEqual(len(w.deletes()), before)
        token = evidence(fake)
        fake.send(t.destroy_metadata_request(policy, identity))
        with case.assertRaises(t.TransportError):
            fake.delete_runtime(identity, uid_value, namespace_evidence=token)
        case.assertEqual(len(w.deletes()), before)
        no_capability = new_fake(lambda req: w.cluster(req))
        token = evidence(no_capability)
        with case.assertRaises(t.TransportError):
            no_capability.delete_runtime(identity, uid_value, namespace_evidence=token)
        case.assertEqual(len(w.deletes()), before)
        fake = new_fake()
        token = evidence(fake)
        case.assertEqual(fake.delete_runtime(identity, uid_value, namespace_evidence=token), "REQUESTED")
        with case.assertRaises(t.TransportError):
            fake.delete_runtime(identity, uid_value, namespace_evidence=token)
        case.assertEqual(len(w.deletes()), before + 1)

    with world(mods, stages=PARTIAL) as w:
        k8s_certs_receipt.cleanup(w.project, w.arn, root=w.g9_root, server=w.cluster)
        identity = w.ident("Namespace", "test-ingress")
        uid_value = w.cluster.meta_of(identity)["uid"]
        policy = t.DestroyPolicy(w.project, [identity], owned_uids={t.identity_key(identity): uid_value},
                                 inventory=True, discovery=True)
        fake = t.open_destroy_transport("fake", policy, w.cluster, t.Deadline(w.clock, 10))
        token = evidence(fake)
        w.clock.sleep(10)
        before = len(w.deletes())
        with case.assertRaises(t.TransportError):
            fake.delete_runtime(identity, uid_value, namespace_evidence=token)
        case.assertEqual(len(w.deletes()), before)


class DestroyReviewTests(unittest.TestCase):
    """Corrections B4B-F01 to B4B-F06 of the independent review of PR #101."""

    def test_f01_reviewed_stage_identity_and_order(self):
        scenario_stage_identity(self, real_mods())

    def test_f02_existing_receipt_only_and_locked_revalidation(self):
        scenario_existing_receipt_only(self, real_mods())
        scenario_store_existing_only(self, real_mods())

    def test_f03_g9_registration_and_fingerprint_binding(self):
        scenario_g9_eligibility(self, real_mods())
        scenario_fingerprint_binding(self, real_mods())

    def test_f04_cluster_wide_target_group_binding_and_fresh_dependencies(self):
        scenario_tgb_cluster_wide(self, real_mods())
        scenario_tgb_crd_reads(self, real_mods())

    def test_f04_service_identity_istio_midstage_and_completed_stage(self):
        scenario_service_identity(self, real_mods())
        scenario_istio_midstage(self, real_mods())
        scenario_completed_stage_dependency(self, real_mods())

    def test_f05_exact_crd_discovery_mapping(self):
        scenario_crd_mapping(self, real_mods())
        scenario_stale_discovery(self, real_mods())

    def test_f06_namespace_final_gate_and_current_owner_chain(self):
        scenario_namespace_final_gate(self, real_mods())
        scenario_owner_chain_current(self, real_mods())

    def test_f03_residual_locked_registration_and_per_secret_fingerprint(self):
        scenario_g9_locked_binding(self, real_mods())
        scenario_stage_fingerprint(self, real_mods())

    def test_f04_residual_exact_tgb_and_admission_binding(self):
        scenario_exact_tgb_binding(self, real_mods())

    def test_f05_residual_crd_kind_and_listable(self):
        scenario_crd_kind_listable(self, real_mods())

    def test_f06_atomic_namespace_races(self):
        scenario_namespace_atomic_races(self, real_mods())

    def test_f06_atomic_namespace_transport_boundary(self):
        scenario_namespace_atomic_boundary(self, real_mods())


ENGINE_MUTATIONS = [
    # preflight
    ("fake_clock_only", D, '        if not isinstance(self.clock, apply.FakeClock):', "        if False:", scenario_real_refused),
    ("fake_transport_only", D, '        if self.transport_kind != "fake":', "        if False:", scenario_real_refused),
    ("pins_checked", D, "            k8s_runtime.check_pins(self.report, expected_manifest, expected_input)", "            pass",
     scenario_receipt_preflight),
    ("objects_match_plan", D, '        if receipt.digest(receipt.canonical(self.objects_in).encode()) != self.report["manifest_sha256"]:',
     "        if False:", scenario_receipt_preflight),
    ("stage_table_checked", D, "            table = k8s_runtime.load_stage_table(self.project)",
     '            table = [(s["name"], [(o["apiVersion"], o["kind"], o["namespace"], o["name"]) for o in s["objects"]]) for s in self.report["stages"]]',
     scenario_stage_identity),
    ("apply_intent_refused", D, '        if state["open_intent"] is not None and state["phase"] == "apply":', "        if False:",
     scenario_open_apply_intent),
    ("quarantine_refused", D, '        if state["quarantined"]:\n            halt("BLOCKED", "quarantined")',
     '        if False:\n            halt("BLOCKED", "quarantined")', scenario_quarantine_preflight),
    ("g9_receipt_verified", D, '        except g9.CleanupError as error:\n            halt("BLOCKED", "g9:" + str(error))\n        identities',
     "        except g9.CleanupError as error:\n            return\n        identities",
     scenario_g9_receipt),
    ("destroy_phase_begun", D, '            if state["phase"] == "apply":\n                self.store.begin_destroy()',
     '            if False:\n                self.store.begin_destroy()', scenario_partial_apply),
    # per object
    ("not_owned_refused", D, '                halt("BLOCKED", "not_owned:" + identity["name"])  # never adopted', "                pass",
     scenario_foreign_object),
    ("never_created_category", D, '            self.record(key, "never_created")\n            return\n        if metadata is not None:',
     '            self.record(key, "deleted")\n            return\n        if metadata is not None:', scenario_g9_incomplete),
    ("uid_checked", D, '            if metadata["uid"] != owned:\n                self.store.quarantine(identity, metadata["uid"], "uid_changed_before_delete")\n                halt("BLOCKED", "uid_changed:" + identity["name"])',
     "            if False:\n                pass", scenario_uid_mismatch),
    ("d13_required", D, '            verdict = self.ownership(identity, metadata)\n            if verdict != "OWNED":\n                halt("BLOCKED", verdict.lower() + ":" + identity["name"])\n            self.dependencies(step, key)',
     "            self.dependencies(step, key)", scenario_d13_ownership),
    ("d13_function", D, "        return apply.d13_ownership(observed, self.manager)", '        return "OWNED"', scenario_d13_ownership),
    ("d13_manifest_paths", D, '"metadata": metadata}, self.manifests[receipt.key_of(identity)])', '"metadata": metadata}, None)',
     scenario_partial_apply),
    ("absent_needs_no_delete", D, "        if metadata is None:\n            # Owned but already absent", "        if False:\n            # Owned but already absent",
     scenario_owned_absent),
    ("delete_error_stops", D, '            halt(transport_status(str(error)), "delete:" + str(error) + ":" + identity["name"])', "            pass",
     scenario_delete_responses),
    ("read_forbidden_blocked", D, '    return "BLOCKED" if code in ("forbidden", "inventory_forbidden", "namespace_atomic_conflict",\n                                 "namespace_atomic_capability_required", "namespace_atomic_evidence_required",\n                                 "namespace_inventory_unsafe", "namespace_evidence_mismatch") else "UNKNOWN"', '    return "UNKNOWN"',
     scenario_delete_responses),
    ("recreated_uid_seen", D, '            if metadata["uid"] != uid:\n                return metadata["uid"]', "            if False:\n                return None",
     scenario_recreated),
    ("wait_bound", D, "        limit = self.clock.now() + (bound or 0)", "        limit = self.clock.now() + 10 ** 6",
     scenario_tgb_finalizer),
    ("recreated_after_delete_stops", D, '        if observed is not None:\n            self.store.quarantine(identity, observed, "recreated_after_delete")\n            halt("BLOCKED", "recreated_after_delete:" + identity["name"])',
     "        if False:\n            pass", scenario_recreated),
    ("destroyed_stays_absent", D, '            halt("BLOCKED", "recreated_after_destroy:" + identity["name"])', "            pass", scenario_recreated),
    # crash recovery
    ("intent_absent_outcome", D, '        if metadata is None:\n            self.store.destroy_result(intent["seq"], identity, "absent_confirmed")',
     '        if metadata is None:\n            self.store.destroy_result(intent["seq"], identity, "deleted")', scenario_crash_after_delete),
    ("intent_uid_checked", D, '        elif metadata["uid"] != intent["uid"]:', "        elif False:", scenario_crash_before_delete),
    ("open_intent_resolved", D, "        self.gate(step)\n        self.resolve_open_intent(step)", "        self.gate(step)",
     scenario_crash_before_delete),
    ("done_steps_revalidated", D, '                if step in self.state["destroy_stages_done"]:\n                    self.revalidate(step)',
     "                if False:\n                    self.revalidate(step)", scenario_partial_apply),
    # gates (D12)
    ("gates_run", D, "    def run_step(self, step):\n        self.gate(step)", "    def run_step(self, step):\n        pass", scenario_foreign_tgb),
    ("ingress_gate", D, '            if self.foreign_tgbs(tgb):\n                halt("BLOCKED", "foreign_target_group_binding")',
     '            if False:\n                halt("BLOCKED", "foreign_target_group_binding")', scenario_foreign_tgb),
    ("runtime_tgb_allowed", D, '                and not (allowed_uid is not None and o["uid"] == allowed_uid\n                         and o["namespace"] == identity["namespace"] and o["name"] == identity["name"]\n                         and {tuple(r) for r in o["resources"]} == {TGB_RESOURCE})]', "                ]", scenario_ingress_services),
    ("admission_needs_tgb_gone", D, '        if step == "admission":\n            self.tgb_gone()\n            self.no_load_balancer()\n            if kind == "ValidatingAdmissionPolicy":',
     '        if step == "admission":\n            self.no_load_balancer()\n            if kind == "ValidatingAdmissionPolicy":',
     scenario_tgb_cluster_wide),
    ("controller_needs_tgb_gone", D, '        elif step == "controller":\n            self.tgb_gone()\n        if step in',
     '        elif step == "controller":\n            pass\n        if step in', scenario_tgb_cluster_wide),
    ("unknown_service_refused", D, '            if not (runtime is not None and item["uid"] == runtime and resources == {("", "services")}',
     '            if False and (runtime is not None and item["uid"] == runtime and resources == {("", "services")}',
     scenario_ingress_services),
    ("load_balancer_refused", D, '            if service["load_balancer"]:', "            if False:", scenario_ingress_services),
    ("crd_report_recorded", D, "            self.crds[name] = found\n", "", scenario_partial_apply),
    ("namespace_gate_g9", D, "        elif step == NAMESPACE_PHASE:\n            self.g9_cleanup()", "        elif step == NAMESPACE_PHASE:\n            pass",
     scenario_g9_incomplete),
    ("kind_order", D, '        return sorted(keys, key=lambda k: (KIND_ORDER.index(k.split("|")[1]), position[k]))', "        return keys",
     scenario_destroy_order),
    ("namespace_order", D, '            return sorted(keys, key=lambda k: names.index(k.split("|")[3]))', "            return keys",
     scenario_partial_apply),
    # CRDs (D5)
    ("crd_creation_evidence", D, '            if obj is not None and owned is None:\n                return {"verdict": "UNKNOWN", "reason": "crd_creation_evidence"}',
     '            if False:\n                return {"verdict": "UNKNOWN", "reason": "crd_creation_evidence"}', scenario_crd_creation_evidence),
    ("crd_discovery_considered", D, '                                           (spec["group"], spec["plural"]) in served)',
     "                                           False)", scenario_crd_discovery),
    ("crd_instances_counted", D, '        return {"verdict": counted["verdict"], "reason": counted["reason"]}',
     '        return {"verdict": "ZERO_INSTANCES", "reason": None}', scenario_istio_instances),
    ("crd_verdict_settled", D, '            if found["verdict"] not in SETTLED_CRD:', "            if False:", scenario_crd_safety),
    ("final_crds_all", D, "        self.require_crds(self.istio_crds + self.controller_crds)", "        self.require_crds(self.istio_crds)",
     scenario_crd_discovery),
    # G9 under the deadline
    ("g9_complete_required", D, '        if report["result"] != "COMPLETE" or report["kube_system_webhook_tls"] != "MET":', "        if False:",
     scenario_g9_incomplete),
    ("g9_bounded", D, "                                transport_kind=self.transport_kind, server=server)",
     "                                transport_kind=self.transport_kind, server=self.server)", scenario_deadline),
    ("bounded_before", D, '        if deadline.expired():\n            raise TimeoutError("deadline_exceeded")', "        pass", scenario_bounded_server),
    ("bounded_after", D, "        if deadline.expired() or deadline.clock.now() - start > transport.API_READ_TIMEOUT_SECONDS:",
     "        if deadline.expired():", scenario_bounded_server),
    # namespaces (D3, D6, D18)
    ("discovery_complete", D, '        if found["status"] != "COMPLETE":', "        if False:", scenario_inventory_failures),
    ("inventory_complete", D, '        if listed["status"] != "COMPLETE":', "        if False:", scenario_inventory_failures),
    ("children_waited", D, '            if not any(found == "owned_child" for found in classes.values()):', "            if True:",
     scenario_owned_children),
    ("unknown_blocks", D, '                if found in ("runtime_object", "k8s_certs_secret", "istiod_leftover", "unknown_object"):',
     '                if found in ("runtime_object", "k8s_certs_secret", "istiod_leftover"):', scenario_unknown_objects),
    ("istiod_leftover_blocks", D, '                if found in ("runtime_object", "k8s_certs_secret", "istiod_leftover", "unknown_object"):',
     '                if found in ("runtime_object", "k8s_certs_secret", "unknown_object"):', scenario_istiod_leftover),
    ("certs_secret_blocks", D, '                if found in ("runtime_object", "k8s_certs_secret", "istiod_leftover", "unknown_object"):',
     '                if found in ("runtime_object", "istiod_leftover", "unknown_object"):', scenario_namespace_classes),
    ("runtime_object_class", D, '        if item["uid"] in self.receipt_uids():\n            return "runtime_object"',
     '        if False:\n            return "runtime_object"', scenario_namespace_classes),
    ("unknown_secret_class", D, '            return "k8s_certs_secret" if (namespace, item["name"]) in secrets else "unknown_object"',
     '            return "k8s_certs_secret" if (namespace, item["name"]) in secrets else "allowed_leftover"', scenario_unknown_objects),
    ("events_exact", D, "        if resources and resources <= EVENTS:", "        if resources:", scenario_unknown_objects),
    ("default_sa_exact", D, '        if resources == {("", "serviceaccounts")} and item["name"] == "default":',
     '        if resources == {("", "serviceaccounts")}:', scenario_unknown_objects),
    ("leftover_configmaps_exact", D, '        if resources == {("", "configmaps")} and item["name"] in LEFTOVER_CONFIGMAPS:',
     '        if resources == {("", "configmaps")}:', scenario_unknown_objects),
    ("controller_owner_only", D, '        controllers = [o for o in item["owners"] if o["controller"] is True]',
     '        controllers = list(item["owners"])', scenario_owner_chain),
    ("replicaset_owner_uid", D, '                if self.owner_uid("apps/v1", "Deployment", namespace, owner["name"]) == owner["uid"]:',
     "                if True:", scenario_owner_chain),
    ("pod_chain_verified", D, '                if children.get(owner["uid"]) == owner["name"]:', "                if True:", scenario_owner_chain),
    ("slice_owner_uid", D, '                if self.owner_uid("v1", "Service", namespace, owner["name"]) == owner["uid"]:',
     "                if True:", scenario_owner_chain),
    ("race_detected", D, "            if second != first:", "            if False:", scenario_inventory_race),
    ("namespace_uid_checked", D, '        if metadata["uid"] != owned:\n            self.store.quarantine(identity, metadata["uid"], "uid_changed_before_delete")\n            halt("BLOCKED", "uid_changed:" + identity["name"])\n        verdict',
     "        verdict", scenario_namespace_uid),
    ("namespace_d13", D, '        verdict = self.ownership(identity, metadata)\n        if verdict != "OWNED":\n            halt("BLOCKED", verdict.lower() + ":" + identity["name"])\n        return metadata',
     "        return metadata", scenario_namespace_classes),
    # completion
    ("final_revalidation", D, "        for step in self.plan.destroy_order:\n            self.revalidate(step)\n        if sorted",
     "        if sorted", scenario_final_checks),
    ("final_g9", D, "        self.g9_cleanup()  # again: the four Secrets are confirmed absent through G9's own reads\n", "",
     scenario_final_checks),
    ("kube_system_retained", D, '        if kube_system is None or kube_system.get("uid") != self.fp["kube_system_uid"]:\n            halt("BLOCKED", "kube_system_not_retained")',
     '        if False:\n            halt("BLOCKED", "kube_system_not_retained")',
     scenario_final_checks),
    # B4B-F01: the reviewed stage table
    ("contract_version", D, '        if self.report.get("runtime_contract_version") != k8s_runtime.CONTRACT_VERSION:', "        if False:",
     scenario_stage_identity),
    ("report_stage_identity", D, "        if reported != [(name, list(rows)) for name, rows in table]:", "        if False:",
     scenario_stage_identity),
    ("bundle_stage_identity", D, "        if bundle != [row for _, rows in table for row in rows]:", "        if False:",
     scenario_stage_identity),
    # B4B-F02: existing receipt only, locked revalidation
    ("existing_only_store", D, '                                   self.report["input_sha256"], self.plan, existing_only=True)',
     '                                   self.report["input_sha256"], self.plan)', scenario_existing_receipt_only),
    ("existing_only_begin", R, '            need(records, "journal_missing" if os.path.lexists(self.dir / RECEIPT) else "receipt_missing")\n            need(os.path.lexists(self.dir / RECEIPT), "receipt_snapshot_missing")',
     "            pass", scenario_store_existing_only),
    ("existing_only_root", R, "        if self.existing_only:\n            self.dir = root / fp[\"id\"]", "        if False:\n            self.dir = root / fp[\"id\"]",
     scenario_store_existing_only),
    ("locked_state_checked", D, "            state = self.load()\n            self.check_state(state)", "            state = self.load()",
     scenario_existing_receipt_only),
    ("locked_fingerprint", D, '            self.check_fingerprint()\n            self.g9_eligible()\n            if state["phase"] == "apply":',
     '            if state["phase"] == "apply":', scenario_existing_receipt_only),
    # B4B-F03: G9 registration and the fingerprint
    ("g9_registration_required", D, '        if document["result"] != "REGISTERED" or any(', "        if False and any(",
     scenario_g9_eligibility),
    ("fingerprint_every_step", D, "            for step in self.plan.destroy_order:\n                self.check_fingerprint()",
     "            for step in self.plan.destroy_order:", scenario_stage_fingerprint),
    ("g9_fingerprint_guard_passed", D, '        server = bounded_server(self.server, self.deadline, self.fp["kube_system_uid"])',
     "        server = bounded_server(self.server, self.deadline)", scenario_fingerprint_binding),
    ("g9_fingerprint_reason", D, '            halt("BLOCKED", "fingerprint_changed" if server.tripped else "g9:" + str(error))',
     '            halt("BLOCKED", "g9:" + str(error))', scenario_fingerprint_binding),
    ("bounded_guard_compare", D, "            if observed != self.kube_system_uid:", "            if False:", scenario_fingerprint_binding),
    # B4B-F04: TargetGroupBinding dependencies
    ("tgb_crd_instances", D, '        if found["verdict"] not in SETTLED_CRD:\n            halt("BLOCKED" if found["verdict"] == "BLOCKED" else "UNKNOWN",\n                 "target_group_binding_remains"',
     '        if False:\n            halt("BLOCKED" if found["verdict"] == "BLOCKED" else "UNKNOWN",\n                 "target_group_binding_remains"',
     scenario_tgb_cluster_wide),
    ("fresh_dependencies", D, "            self.dependencies(step, key)  # fresh evidence right before a dependency-sensitive DELETE",
     "            pass", scenario_tgb_cluster_wide),
    ("istio_webhook_dependency", D, '        if step in ("istiod", "base") and kind in WEBHOOK_KINDS:\n            self.require_crds(self.istio_crds)',
     '        if False:\n            self.require_crds(self.istio_crds)', scenario_istio_midstage),
    ("deployment_after_webhooks", D, '        if kind == "Deployment":\n            self.webhooks_gone(step)', '        if False:\n            self.webhooks_gone(step)',
     scenario_istio_midstage),
    ("webhooks_gone_read", D, '            if key.split("|")[1] in WEBHOOK_KINDS and self.read(identity_of(key)) is not None:',
     "            if False:", scenario_istio_midstage),
    ("service_name_exact", D, '                    and item["namespace"] == ingress and item["name"] == self.gateway_service["name"]):',
     "                    and item[\"namespace\"] == ingress):", scenario_service_identity),
    # B4B-F05: exact CRD mapping
    ("crd_plural_exact", D, '                                           (spec["group"], spec["plural"]) in served)',
     '                                           spec["group"] in {group for group, _ in served})', scenario_crd_mapping),
    ("crd_mapping_missing", D, '        if namespaced is None:\n            return {"verdict": "UNKNOWN", "reason": "crd_discovery_mapping_missing"}',
     '        if False:\n            return {"verdict": "UNKNOWN", "reason": "crd_discovery_mapping_missing"}', scenario_crd_mapping),
    ("crd_scope_mapping", D, '        if namespaced != (spec["scope"] == "Namespaced"):', "        if False:", scenario_crd_mapping),
    ("discovery_payload_current", TR, '        return self._accept(discovery, "discovery")',
     '        return discovery.payload_for(self.policy, "discovery")', scenario_stale_discovery),
    ("discovery_mapping_kept", TR, '            mapped.append((group, version, name, resource["kind"], resource["namespaced"]))',
     "            pass", scenario_stale_discovery),
    # B4B-F06: namespace final gate
    ("final_gate_ownership", D, '            if self.namespace_owned(identity, owned) is None:\n                halt("BLOCKED", "namespace_absent_before_delete:" + name)',
     '            if False:\n                halt("BLOCKED", "namespace_absent_before_delete:" + name)', scenario_namespace_final_gate),
    ("final_gate_g9", D, "            self.namespace_gate(name)\n            self.check_fingerprint()\n            second",
     "            self.check_fingerprint()\n            second", scenario_namespace_final_gate),
    ("final_gate_closes_intent", D, '            if self.state["open_intent"] is not None:\n                self.store.destroy_result(seq, identity, "failed", metadata["uid"])',
     '            if False:\n                self.store.destroy_result(seq, identity, "failed", metadata["uid"])', scenario_namespace_final_gate),
    ("children_current_inventory", D, "            children, classes = {}, {}",
     '            children, classes = self.__dict__.setdefault("_kept", {}), {}', scenario_owner_chain_current),
    ("children_local_deadline", D, '            if wait and self.clock.now() > limit:\n                halt("BLOCKED", "owned_child_remains:" + namespace)',
     '            if False:\n                halt("BLOCKED", "owned_child_remains:" + namespace)', scenario_local_wait_unit),
    # B4B-F07: recovery, local waits, counts
    ("terminating_not_resent", D, '            if transport.object_state(metadata)["deletion_requested"]:', "            if False:",
     scenario_crash_after_delete),
    ("late_response_refused", D, "            if bound is not None and self.clock.now() > limit:\n                halt(\"BLOCKED\", self.wait_reason(identity))",
     "            if False:\n                halt(\"BLOCKED\", self.wait_reason(identity))", scenario_local_wait),
    ("retained_counts_split", D, '            "retained_crds": verdicts.count("ZERO_INSTANCES"),', '            "retained_crds": len(verdicts),',
     scenario_partial_apply),
    ("rerun_namespace_report", D, '                if namespace_key:\n                    self.namespaces[name] = "DELETED" if obj["destroyed"] == "deleted" else "ABSENT_CONFIRMED"',
     "                if namespace_key:\n                    pass", scenario_partial_apply),
    # Residual findings. Existing mutation cases remain in the suite.
    ("fingerprint_each_delete", D, '        self.check_fingerprint()  # F03-R: never reuse a stage\'s fingerprint for a later DELETE.',
     "        pass", scenario_fingerprint_binding),
    ("g9_locked_registration_pin", D, "                                expected_registration=self.g9_registration_pin,",
     "                                expected_registration=None,", scenario_g9_locked_binding),
    ("g9_fingerprint_each_delete", D, '        if self.kube_system_uid is not None and request.get("method") == "DELETE":',
     "        if False:", scenario_g9_locked_binding),
    ("exact_tgb_name", D, '                         and o["namespace"] == identity["namespace"] and o["name"] == identity["name"]',
     '                         and o["namespace"] == identity["namespace"]', scenario_exact_tgb_binding),
    ("admission_binding_absence", D, "                self.admission_bindings_gone(key)",
     "                pass", scenario_exact_tgb_binding),
    ("crd_mapping_kind", D, '            if mapping[target] != (spec["scope"] == "Namespaced") or kinds.get(target) != reviewed_kind:',
     '            if mapping[target] != (spec["scope"] == "Namespaced"):', scenario_crd_kind_listable),
    ("crd_mapping_listable", D, "            if target not in listable:", "            if False:", scenario_crd_kind_listable),
    ("namespace_atomic_evidence", TR, '        need(evidence is not None, "namespace_atomic_evidence_required")',
     '        if evidence is None:\n            return self.server(request)', scenario_namespace_atomic_boundary),
    ("namespace_atomic_consume", TR, '        self._invalidate_observed(request)\n        capability = getattr(self.server, "atomic_namespace_delete", None)',
     '        capability = getattr(self.server, "atomic_namespace_delete", None)', scenario_namespace_atomic_boundary),
    ("generic_namespace_delete_refused", TR, '        need(not any(k[1] == "Namespace" for k in self.delete), "namespace_atomic_capability_required")',
     "        pass", scenario_namespace_atomic_boundary),
    ("namespace_atomic_snapshot", TR, '            and namespace_leftovers_only(current_objects, namespace) and current_objects == evidence["objects"])',
     '            and namespace_leftovers_only(current_objects, namespace))', scenario_namespace_atomic_races),
    ("namespace_atomic_snapshot_and_class", TR, '    return (current_discovery == evidence["discovery"] and current_objects is not None\n            and namespace_leftovers_only(current_objects, namespace) and current_objects == evidence["objects"])',
     "    return True", scenario_namespace_atomic_races),
    ("namespace_atomic_no_fallback", TR, '        need(callable(capability), "namespace_atomic_capability_required")',
     '        if not callable(capability):\n            return self.server(request)', scenario_namespace_atomic_boundary),
]


class DestroyEngineMutationTests(unittest.TestCase):
    def test_each_engine_guard_mutation_is_detected_by_an_assertion(self):
        self.assertEqual(len(ENGINE_MUTATIONS), 113)
        self.assertEqual(len(ENGINE_MUTATIONS), len({m[0] for m in ENGINE_MUTATIONS}))
        undetected = []
        for name, filename, old, new, scenario in ENGINE_MUTATIONS:
            mods = real_mods()
            setattr(mods, {D: "destroy", R: "receipt", TR: "transport"}[filename], mutant(filename, old, new))
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, mods)
            except AssertionError:
                continue
            except BaseException as crashed:  # noqa: BLE001 - a crash is never counted as a detection
                undetected.append(name + ":crashed:" + type(crashed).__name__)
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
