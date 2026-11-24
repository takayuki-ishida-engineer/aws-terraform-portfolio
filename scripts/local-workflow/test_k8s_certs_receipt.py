#!/usr/bin/env python3
"""Offline tests for the G9 registration UID receipt and Secret cleanup and the D19 Secret transport contract.

Covers ``k8s_certs_receipt`` (receipt store, Fake-only registration record, the
ten-step cleanup and the D18 report), the four-Secret extension of
``k8s_runtime_transport`` and the retired name-based ``k8s_certs.py delete``.

A fake Kubernetes API (``FakeCluster``) answers the transport's requests. It returns
a full Secret, with a value marker, whenever a GET lacks the metadata-only Accept
header, and it honours ``preconditions.uid`` on DELETE like the API server. Nothing
reaches a cluster or AWS; receipt roots are temporary directories outside the
repository.

``SECRET_MUTATIONS`` removes one guard at a time. A mutation counts as detected only
when its scenario fails an assertion: a mutant that crashes (any other exception) is
reported as undetected. These tests and mutations run inside the
``k8s_runtime_receipt_tests`` suite (``test_k8s_runtime_receipt`` imports them).
"""
import base64
import contextlib
import copy
import fcntl
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import ast
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_certs  # noqa: E402
import k8s_certs_receipt  # noqa: E402
import k8s_runtime_receipt  # noqa: E402
import k8s_runtime_transport  # noqa: E402

PROJECT = "acme"
ARN = "arn:aws:eks:ca-central-1:444455556666:cluster/acme-dev-eks"
KUBE_SYSTEM_UID = "11111111-2222-4333-8444-555555555555"
VALUE_MARKER = "G9-SECRET-VALUE-MARKER-7f3a"
ENCODED_MARKER = base64.b64encode(VALUE_MARKER.encode()).decode()
IDS = k8s_runtime_transport.secret_identities(PROJECT)
CACERTS, WEBHOOK, GATEWAY, CLIENT_CA = (i["name"] for i in IDS)
NAMESPACE_OF = {i["name"]: i["namespace"] for i in IDS}


def uid(n):
    return "00000000-0000-4000-8000-%012x" % n


class Mods(types.SimpleNamespace):
    """The modules under test; a mutation replaces one of them."""


def real_mods():
    return Mods(cleanup=k8s_certs_receipt, transport=k8s_runtime_transport, certs=k8s_certs)


def code_of(call, mods):
    """The fixed code of a refusal, or None; any other exception propagates (a crash is never a detection)."""
    try:
        call()
    except (mods.cleanup.CleanupError, mods.transport.TransportError, k8s_certs_receipt.CleanupError,
            k8s_runtime_transport.TransportError) as refused:
        return str(refused)
    return None


def layout_of(name, project=PROJECT):
    return next(s for s in k8s_certs.secret_layout(project, None) if s["metadata"]["name"] == name)


def secret_metadata(name, uid_value, project=PROJECT):
    layout = layout_of(name, project)
    fields = {"f:data": dict({".": {}}, **{"f:" + key: {} for key in sorted(layout["data"])}),
              "f:metadata": {"f:labels": {".": {}, "f:app.kubernetes.io/managed-by": {},
                                          "f:app.kubernetes.io/part-of": {}}},
              "f:type": {}}
    return {"name": name, "namespace": layout["metadata"]["namespace"], "uid": uid_value, "resourceVersion": "100",
            "creationTimestamp": "2026-11-24T00:00:00Z", "labels": dict(layout["metadata"]["labels"]),
            "managedFields": [{"manager": project + "-k8s-certs", "operation": "Apply", "apiVersion": "v1",
                               "time": "2026-11-24T00:00:00Z", "fieldsType": "FieldsV1", "fieldsV1": fields}]}


def partial(metadata):
    return json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1", "metadata": metadata}).encode()


SECRET_PATH = re.compile(r"/api/v1/namespaces/([a-z0-9.-]+)/secrets/([a-z0-9.-]+)")


class FakeCluster:
    """The fake API server: kube-system namespace metadata and the Secrets, with API-like GET and DELETE."""

    def __init__(self):
        self.objects = {}
        self.requests = []
        self.hooks = {}
        self.counter = 100

    def new_uid(self):
        self.counter += 1
        return uid(self.counter)

    def put(self, name, uid_value=None):
        self.objects[name] = secret_metadata(name, uid_value or self.new_uid())
        return self.objects[name]["uid"]

    def seed(self, names=None):
        """Secrets that exist before any registration (correct labels and manager, unknown to any receipt)."""
        for name in ([i["name"] for i in IDS] if names is None else names):
            self.put(name)

    def apply(self, plan):
        """The fake's conditional server-side apply, checked atomically: create only if absent, update only the
        expected UID. A refused item is a conflict that reports the object it found and changes nothing."""
        results = []
        for item in plan:
            name, stored = item["name"], self.objects.get(item["name"])
            found = stored["uid"] if stored else None
            if item["expect_uid"] is None and stored is None:
                outcome, written = "created", self.put(name)
            elif item["expect_uid"] is not None and found == item["expect_uid"]:
                outcome, written = "updated", self.put(name, found)
            else:
                outcome, written = "conflict", found
            results.append({"namespace": item["namespace"], "name": name, "outcome": outcome, "uid": written})
        return results

    def server(self, request):
        self.requests.append(copy.deepcopy(request))
        if request["path"] == "/api/v1/namespaces/kube-system":
            return 200, partial({"name": "kube-system", "uid": KUBE_SYSTEM_UID})
        match = SECRET_PATH.fullmatch(request["path"])
        if not match or match.group(1) != NAMESPACE_OF.get(match.group(2)):
            return 400, b""
        name = match.group(2)
        hook = self.hooks.get((request["method"], name))
        if hook is not None:
            answer = hook(request)
            if answer is not None:
                return answer
        stored = self.objects.get(name)
        if request["method"] == "GET":
            if stored is None:
                return 404, b'{"kind":"Status","code":404}'
            if request["headers"].get("Accept") != k8s_runtime_transport.METADATA_ACCEPT:
                full = {"kind": "Secret", "apiVersion": "v1", "metadata": stored, "type": "Opaque",
                        "data": {"tls.key": ENCODED_MARKER}}
                return 200, json.dumps(full).encode()
            return 200, partial(stored)
        if request["method"] == "DELETE":
            if stored is None:
                return 404, b""
            precondition = (json.loads(request["body"] or "{}").get("preconditions") or {}).get("uid")
            if precondition is not None and precondition != stored["uid"]:
                return 409, b'{"kind":"Status","reason":"Conflict"}'
            del self.objects[name]
            return 200, b'{"kind":"Status","status":"Success"}'
        return 405, b""


class Env:
    """A temporary receipt root outside the repository and a fake cluster."""

    def __init__(self, mods):
        self.mods = mods
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-certs-receipt-"))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "state"
        self.cluster = FakeCluster()
        self.fp = k8s_runtime_receipt.fingerprint(ARN, KUBE_SYSTEM_UID)
        self.apply_calls = []

    @property
    def dir(self):
        return self.root / self.fp["id"]

    @property
    def receipt(self):
        return self.dir / "registration.json"

    def register(self, apply_fn=None, kind="fake", root=None):
        apply_fn = apply_fn or self.cluster.apply

        def recorded(plan):
            self.apply_calls.append(copy.deepcopy(plan))
            return apply_fn(plan)
        return self.mods.cleanup.register_with_receipt(PROJECT, ARN, recorded, root=root or self.root,
                                                       transport_kind=kind, server=self.cluster.server)

    def uids(self):
        return {name: self.cluster.objects[name]["uid"] for name in self.cluster.objects}

    def cleanup(self, kind="fake", root=None):
        return self.mods.cleanup.cleanup(PROJECT, ARN, root=root or self.root, transport_kind=kind,
                                         server=self.cluster.server)

    def document(self):
        return json.loads(self.receipt.read_text())

    def write_document(self, document):
        self.receipt.write_bytes(k8s_runtime_receipt.canonical(document).encode())

    def tamper(self, change):
        document = self.document()
        change(document)
        self.write_document(document)

    def secret_requests(self):
        return [r for r in self.cluster.requests if "/secrets/" in r["path"]]

    def deletes(self):
        return [r for r in self.cluster.requests if r["method"] == "DELETE"]

    def state_of(self, report, name):
        return next((r["state"], r["reason"]) for r in report["secrets"] if r["name"] == name)

    def cleanup_of(self, name):
        entry = next(e for e in self.document()["secrets"] if e["identity"]["name"] == name)
        return entry["cleanup"]

    def cleanup_env(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@contextlib.contextmanager
def env_for(mods):
    env = Env(mods)
    try:
        yield env
    finally:
        env.cleanup_env()


def assert_no_value(case, env, *values):
    text = (env.receipt.read_text() if env.receipt.exists() else "") + json.dumps(values, default=str)
    case.assertNotIn(VALUE_MARKER, text)
    case.assertNotIn(ENCODED_MARKER, text)


def registered(env):
    result = env.register()
    assert result["result"] == "REGISTERED", result
    env.cluster.requests.clear()
    env.apply_calls.clear()
    return result


def refused_before_apply(case, env, mods, code, call=None):
    """The registration is refused with the code before the apply step, and nothing changes."""
    before_receipt = env.receipt.read_bytes() if env.receipt.exists() else None
    before_objects = copy.deepcopy(env.cluster.objects)
    case.assertEqual(code_of(call or env.register, mods), code)
    case.assertEqual(env.apply_calls, [], "the apply step is never called")
    case.assertEqual(env.receipt.read_bytes() if env.receipt.exists() else None, before_receipt)
    case.assertEqual(env.cluster.objects, before_objects, "no Secret is written")


# ---- transport (D19 Secret extension) -----------------------------------------------------------------------------

def scenario_secret_allowlist(case, mods):
    t = mods.transport
    case.assertEqual(t.secret_identities(PROJECT), [
        {"apiVersion": "v1", "kind": "Secret", "namespace": "istio-system", "name": "cacerts"},
        {"apiVersion": "v1", "kind": "Secret", "namespace": "kube-system", "name": "aws-load-balancer-controller-tls"},
        {"apiVersion": "v1", "kind": "Secret", "namespace": "acme-ingress", "name": "acme-gateway-tls"},
        {"apiVersion": "v1", "kind": "Secret", "namespace": "acme-ingress", "name": "acme-gateway-client-cacert"}])
    # The allowlist is exactly the k8s_certs.py layout.
    case.assertEqual([(i["namespace"], i["name"]) for i in t.secret_identities(PROJECT)],
                     [(s["metadata"]["namespace"], s["metadata"]["name"]) for s in k8s_certs.secret_layout(PROJECT, None)])
    for project in ("Acme", "aws1", "x" * 11, "a/b", "", None):
        case.assertEqual(code_of(lambda: t.secret_identities(project), mods), "secret_project_invalid", project)
    for other in ({"namespace": "default", "name": "cacerts"}, {"namespace": "istio-system", "name": "istio-ca-secret"},
                  {"namespace": "other-ingress", "name": "other-gateway-tls"},
                  {"namespace": "kube-system", "name": "cacerts"}):
        secret = dict({"apiVersion": "v1", "kind": "Secret"}, **other)
        case.assertEqual(code_of(lambda: t.Policy([secret], secret_project=PROJECT), mods), "secret_path_not_approved",
                         other)
    case.assertEqual(code_of(lambda: t.Policy([dict(IDS[0], apiVersion="v2")], secret_project=PROJECT), mods),
                     "secret_path_not_approved")
    case.assertEqual(code_of(lambda: t.Policy(IDS), mods), "secret_path_not_approved")
    case.assertEqual(code_of(lambda: t.Policy(IDS, secret_project="other"), mods), "secret_path_not_approved")


def scenario_secret_requests(case, mods):
    t = mods.transport
    policy = t.Policy(IDS, IDS[:1], secret_project=PROJECT)
    request = t.metadata_get_request(policy, IDS[0])
    case.assertEqual((request["method"], request["path"], request["body"]),
                     ("GET", "/api/v1/namespaces/istio-system/secrets/cacerts", None))
    case.assertEqual(request["headers"], {"Accept": "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1"})
    case.assertEqual(t.metadata_get_request(policy, IDS[2])["path"],
                     "/api/v1/namespaces/acme-ingress/secrets/acme-gateway-tls")
    delete = t.delete_request(policy, IDS[0], uid(7))
    case.assertEqual((delete["method"], delete["path"]), ("DELETE", "/api/v1/namespaces/istio-system/secrets/cacerts"))
    case.assertEqual(json.loads(delete["body"])["preconditions"], {"uid": uid(7)})
    case.assertEqual(code_of(lambda: t.delete_request(policy, IDS[1], uid(7)), mods), "delete_not_allowed")
    case.assertEqual(code_of(lambda: t.delete_request(policy, IDS[0], None), mods), "uid_invalid")
    case.assertEqual(code_of(lambda: t.object_path(IDS[0]), mods), "secret_path_not_approved")
    # The fake exposes exactly the two contract operations: no arbitrary verb or path.
    fake = t.open_transport("fake", policy, lambda request: (404, b""))
    case.assertEqual({n for n in dir(fake) if not n.startswith("_") and callable(getattr(fake, n))},
                     {"get_metadata", "delete_with_uid", "server"})


def scenario_secret_responses(case, mods):
    t = mods.transport
    stored = dict(secret_metadata(CACERTS, uid(9)), annotations={"example.com/note": VALUE_MARKER})
    metadata = t.validate_metadata_response(IDS[0], 200, partial(stored))
    case.assertEqual(set(metadata), {"name", "namespace", "uid", "labels", "managedFields", "resourceVersion"})
    assert_no_value(case, types.SimpleNamespace(receipt=Path("/nonexistent")), metadata)
    applied = dict(stored, annotations={"kubectl.kubernetes.io/last-applied-configuration": '{"data":{}}'})
    case.assertEqual(code_of(lambda: t.validate_metadata_response(IDS[0], 200, partial(applied)), mods),
                     "response_secret_annotation_refused")
    full = json.dumps({"kind": "Secret", "apiVersion": "v1", "metadata": stored, "data": {"k": ENCODED_MARKER}})
    for body in (full, json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                                   "metadata": stored, "stringData": {"k": VALUE_MARKER}}),
                 json.dumps({"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1",
                             "metadata": stored, "binaryData": {"k": ENCODED_MARKER}})):
        case.assertEqual(code_of(lambda: t.validate_metadata_response(IDS[0], 200, body.encode()), mods),
                         "response_not_metadata_only")
    case.assertEqual(code_of(lambda: t.validate_metadata_response(IDS[0], 200, json.dumps(
        {"kind": "PartialObjectMetadata", "apiVersion": "meta.k8s.io/v1", "metadata": stored, "type": "Opaque"}).encode()),
        mods), "response_shape")
    case.assertEqual(code_of(lambda: t.validate_metadata_response(IDS[0], 200, partial(
        dict(stored, annotations="x"))), mods), "response_shape")


# ---- registration UID receipt -------------------------------------------------------------------------------------

def scenario_register_roundtrip(case, mods):
    with env_for(mods) as env:
        result = env.register()
        case.assertEqual(result["result"], "REGISTERED")
        case.assertEqual([s["registration"] for s in result["secrets"]], ["REGISTERED"] * 4)
        case.assertEqual(env.apply_calls, [[{"namespace": i["namespace"], "name": i["name"], "expect_uid": None}
                                            for i in IDS]])
        case.assertEqual(oct(env.dir.stat().st_mode & 0o777), "0o700")
        case.assertEqual(oct(env.receipt.stat().st_mode & 0o777), "0o600")
        document = env.document()
        case.assertEqual(set(document), {"schema", "project", "cluster", "registered_at", "result", "secrets"})
        case.assertEqual(document["schema"], "k8s-certs-registration-receipt-v1")
        case.assertEqual(document["cluster"], {"cluster_arn": ARN, "kube_system_uid": KUBE_SYSTEM_UID,
                                               "fingerprint_id": env.fp["id"]})
        case.assertEqual([e["identity"] for e in document["secrets"]], IDS)
        case.assertEqual([e["uid"] for e in document["secrets"]],
                         [env.cluster.objects[i["name"]]["uid"] for i in IDS])
        case.assertTrue(all(e["cleanup"] is None and e["reason"] is None for e in document["secrets"]))
        paths = [("GET", "/api/v1/namespaces/%s/secrets/%s" % (i["namespace"], i["name"])) for i in IDS]
        case.assertEqual([(r["method"], r["path"]) for r in env.cluster.requests],
                         [("GET", "/api/v1/namespaces/kube-system")] + paths + paths)
        case.assertTrue(all(r["headers"]["Accept"] == k8s_runtime_transport.METADATA_ACCEPT
                            for r in env.cluster.requests))
        text = env.receipt.read_text()
        for word in ("annotations", "managedFields", "labels", "data", "creationTimestamp"):
            case.assertNotIn(word, text)
        assert_no_value(case, env, result)
        case.assertEqual(sorted(os.listdir(env.dir)), ["lock", "registration.json"])


def scenario_register_again_same_uids(case, mods):
    with env_for(mods) as env:
        registered(env)
        uids = [e["uid"] for e in env.document()["secrets"]]
        outcome = []
        case.assertIsNone(code_of(lambda: outcome.append(env.register()), mods))
        case.assertEqual(outcome[0]["result"], "REGISTERED")
        case.assertEqual([item["expect_uid"] for item in env.apply_calls[0]], uids, "update only the receipt UIDs")
        case.assertEqual([e["uid"] for e in env.document()["secrets"]], uids)


def scenario_register_after_cleanup(case, mods):
    with env_for(mods) as env:
        registered(env)
        case.assertEqual(env.cleanup()["result"], "COMPLETE")
        outcome = []
        case.assertIsNone(code_of(lambda: outcome.append(env.register()), mods), "cleaned-up UIDs may be replaced")
        case.assertEqual(outcome[0]["result"], "REGISTERED")
        case.assertEqual([item["expect_uid"] for item in env.apply_calls[0]], [None] * 4)
        case.assertTrue(all(e["cleanup"] is None for e in env.document()["secrets"]))


def scenario_register_partial(case, mods):
    with env_for(mods) as env:
        # The apply writes all four but its result confirms only three.
        result = env.register(apply_fn=lambda plan: env.cluster.apply(plan)[:3])
        case.assertEqual(result["result"], "INCOMPLETE")
        case.assertEqual((result["secrets"][3]["registration"], result["secrets"][3]["reason"]),
                         ("NOT_VERIFIED", "apply_not_confirmed"))
        document = env.document()
        case.assertEqual(document["result"], "INCOMPLETE")
        case.assertIsNone(document["secrets"][3]["uid"])
        case.assertEqual([e["registration"] for e in document["secrets"][:3]], ["REGISTERED"] * 3)


def scenario_register_failures(case, mods):
    with env_for(mods) as env:
        def failing_apply(plan):
            env.cluster.apply(plan[:1])
            raise RuntimeError("apply failed: " + VALUE_MARKER)
        result = env.register(apply_fn=failing_apply)
        case.assertEqual(result["result"], "INCOMPLETE")
        case.assertEqual({s["reason"] for s in result["secrets"]}, {"apply_not_confirmed"})
        case.assertEqual(len(env.secret_requests()), 4, "only the four reads before the apply")
        assert_no_value(case, env, result)
    with env_for(mods) as env:
        applied = []
        env.cluster.hooks[("GET", WEBHOOK)] = lambda request: (404, b"") if applied else None
        env.cluster.hooks[("GET", GATEWAY)] = lambda request: (403, b"") if applied else None

        def apply_with_foreign(plan):
            outcome = env.cluster.apply(plan)
            applied.append(1)
            env.cluster.objects[CLIENT_CA]["managedFields"].append(
                {"manager": "kubectl-edit", "operation": "Update", "apiVersion": "v1", "fieldsType": "FieldsV1",
                 "fieldsV1": {"f:metadata": {"f:annotations": {}}}})
            return outcome
        result = env.register(apply_fn=apply_with_foreign)
        case.assertEqual([(s["registration"], s["reason"]) for s in result["secrets"]],
                         [("REGISTERED", None), ("NOT_VERIFIED", "absent_after_apply"),
                          ("NOT_VERIFIED", "forbidden"), ("NOT_VERIFIED", "foreign_manager")])
        case.assertEqual(env.document()["result"], "INCOMPLETE")


def scenario_register_ownership(case, mods):
    with env_for(mods) as env:
        def apply_then_edit(plan):
            outcome = env.cluster.apply(plan)
            env.cluster.objects[GATEWAY]["managedFields"].append(
                {"manager": "kubectl-edit", "operation": "Update", "apiVersion": "v1", "fieldsType": "FieldsV1",
                 "fieldsV1": {"f:metadata": {"f:annotations": {}}}})
            env.cluster.objects[CACERTS]["labels"].pop("app.kubernetes.io/managed-by")
            return outcome
        result = env.register(apply_fn=apply_then_edit)
        case.assertEqual(result["result"], "INCOMPLETE")
        case.assertEqual([s["reason"] for s in result["secrets"]], ["label_managed_by", None, "foreign_manager", None])


def scenario_register_foreign_report(case, mods):
    with env_for(mods) as env:
        def with_foreign(plan):
            return env.cluster.apply(plan) + [{"namespace": "default", "name": "other", "outcome": "created",
                                               "uid": uid(950)}]
        result = env.register(apply_fn=with_foreign)
        case.assertEqual(result["result"], "INCOMPLETE")
        case.assertEqual({s["reason"] for s in result["secrets"]}, {"apply_not_confirmed"})
        case.assertEqual(len(env.secret_requests()), 4, "nothing is read back for an untrusted result")


def scenario_apply_evidence(case, mods):
    evidence = mods.cleanup.apply_evidence
    plan = [{"namespace": "istio-system", "name": "cacerts", "expect_uid": None},
            {"namespace": "kube-system", "name": WEBHOOK, "expect_uid": uid(1)}]
    good = [{"namespace": "istio-system", "name": "cacerts", "outcome": "created", "uid": uid(2)},
            {"namespace": "kube-system", "name": WEBHOOK, "outcome": "updated", "uid": uid(1)}]
    case.assertEqual(evidence(good, plan), {("istio-system", "cacerts"): uid(2), ("kube-system", WEBHOOK): uid(1)})
    cases = [
        ("updated with another UID", [good[0], dict(good[1], uid=uid(3))], {("istio-system", "cacerts"): uid(2)}),
        ("created where a UID is claimed", [good[0], dict(good[1], outcome="created")],
         {("istio-system", "cacerts"): uid(2)}),
        ("updated where absent was planned", [dict(good[0], outcome="updated"), good[1]],
         {("kube-system", WEBHOOK): uid(1)}),
        ("conflict reporting the found UID", [dict(good[0], outcome="conflict"), good[1]],
         {("kube-system", WEBHOOK): uid(1)}),
        ("missing UID", [{k: v for k, v in good[0].items() if k != "uid"}, good[1]], {("kube-system", WEBHOOK): uid(1)}),
        ("malformed UID", [dict(good[0], uid="not-a-uid"), good[1]], {("kube-system", WEBHOOK): uid(1)}),
        ("unknown identity", good + [{"namespace": "default", "name": "x", "outcome": "created", "uid": uid(4)}], {}),
        ("repeated identity", [dict(good[0], uid=uid(9))] + good, {}),
        ("not a list", {"cacerts": "applied"}, {}),
    ]
    for label, result, expected in cases:
        case.assertEqual(evidence(result, plan), expected, label)


def scenario_register_existing_without_receipt(case, mods):
    with env_for(mods) as env:
        env.cluster.seed([GATEWAY])
        refused_before_apply(case, env, mods, "existing_secret_without_receipt")
        case.assertFalse(env.receipt.exists())


def scenario_register_all_existing_matching(case, mods):
    with env_for(mods) as env:
        env.cluster.seed()  # correct labels, manager and fields: still unknown without a receipt
        refused_before_apply(case, env, mods, "existing_secret_without_receipt")
        case.assertFalse(env.receipt.exists())


def scenario_register_save_failure(case, mods):
    with env_for(mods) as env:
        with mock.patch.object(mods.cleanup.os, "replace", side_effect=OSError("disk full")):
            case.assertEqual(code_of(env.register, mods), "receipt_save_failed")
        case.assertFalse(env.receipt.exists())
        case.assertEqual(sorted(os.listdir(env.dir)), ["lock"])
        case.assertEqual(len(env.cluster.objects), 4, "the Secrets stay; cleanup is then BLOCKED (no receipt)")
        case.assertEqual(code_of(env.cleanup, mods), "receipt_missing")
        case.assertEqual(env.deletes(), [])
        env.apply_calls.clear()
        refused_before_apply(case, env, mods, "existing_secret_without_receipt")


def scenario_register_uid_mismatch_before_apply(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.cluster.objects.pop(GATEWAY)
        env.cluster.put(GATEWAY)  # recreated by someone else: a different UID
        refused_before_apply(case, env, mods, "receipt_uid_mismatch")


def scenario_register_claimed_absent(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.cluster.objects.pop(WEBHOOK)  # gone without a recorded cleanup
        refused_before_apply(case, env, mods, "receipt_uid_absent")


def scenario_register_claimed_ownership(case, mods):
    with env_for(mods) as env:
        registered(env)
        foreign(env.cluster.objects[GATEWAY], env)
        refused_before_apply(case, env, mods, "precondition_foreign_manager")


def scenario_register_precondition_unreadable(case, mods):
    answers = [lambda request: (403, b""), lambda request: (500, b""), timeout, lambda request: (200, b"{not json"),
               lambda request: (200, partial({"name": CLIENT_CA, "namespace": "acme-ingress", "uid": "bad"}))]
    for answer in answers:
        with env_for(mods) as env:
            env.cluster.hooks[("GET", CLIENT_CA)] = answer  # the last of the four: the first three were fine
            refused_before_apply(case, env, mods, "precondition_unreadable")
            case.assertFalse(env.receipt.exists())
    with env_for(mods) as env:
        registered(env)
        env.cluster.hooks[("GET", CACERTS)] = lambda request: (403, b"")
        refused_before_apply(case, env, mods, "precondition_unreadable")


def scenario_register_recreated_after_cleanup(case, mods):
    with env_for(mods) as env:
        registered(env)
        case.assertEqual(env.cleanup()["result"], "COMPLETE")
        env.cluster.put(CLIENT_CA)  # recreated outside the tool, with matching labels and manager
        refused_before_apply(case, env, mods, "recreated_after_cleanup")


def scenario_register_no_rebuild_from_unverified(case, mods):
    with env_for(mods) as env:
        env.register(apply_fn=lambda plan: env.cluster.apply(plan)[:3])  # CLIENT_CA exists but is NOT_VERIFIED
        env.apply_calls.clear()
        refused_before_apply(case, env, mods, "unverified_secret_present")


def scenario_register_recreated_before_apply(case, mods):
    with env_for(mods) as env:
        def race(plan):
            env.cluster.put(GATEWAY, uid(960))  # created by someone else after the precondition read
            return env.cluster.apply(plan)
        result = env.register(apply_fn=race)
        case.assertEqual((result["secrets"][2]["registration"], result["secrets"][2]["reason"]),
                         ("NOT_VERIFIED", "apply_not_confirmed"))
        case.assertEqual(result["result"], "INCOMPLETE")
        case.assertEqual(env.cluster.objects[GATEWAY]["uid"], uid(960), "the unknown Secret is not overwritten")
        case.assertNotIn(uid(960), env.receipt.read_text(), "and never adopted")


def scenario_register_plan_tamper(case, mods):
    with env_for(mods) as env:
        def tamper(plan):
            env.cluster.put(GATEWAY, uid(961))
            plan[2]["expect_uid"] = uid(961)  # a callback that rewrites the plan cannot widen what is accepted
            return env.cluster.apply(plan)
        result = env.register(apply_fn=tamper)
        case.assertEqual(result["secrets"][2]["reason"], "apply_not_confirmed")
        case.assertNotIn(uid(961), env.receipt.read_text())


def scenario_register_uid_changed_after_apply(case, mods):
    with env_for(mods) as env:
        def apply_then_recreate(plan):
            outcome = env.cluster.apply(plan)
            env.cluster.objects.pop(GATEWAY)
            env.cluster.put(GATEWAY, uid(962))
            return outcome
        result = env.register(apply_fn=apply_then_recreate)
        case.assertEqual((result["secrets"][2]["registration"], result["secrets"][2]["reason"]),
                         ("NOT_VERIFIED", "uid_changed_after_apply"))
        case.assertNotIn(uid(962), env.receipt.read_text())
        case.assertIsNone(env.document()["secrets"][2]["uid"])


def scenario_register_apply_uid_missing_or_wrong(case, mods):
    with env_for(mods) as env:
        def bad_result(plan):
            outcome = env.cluster.apply(plan)
            del outcome[1]["uid"]
            outcome[2]["uid"] = "not-a-uid"
            outcome[3]["uid"] = uid(963)  # a well-formed UID that is not the object's
            return outcome
        result = env.register(apply_fn=bad_result)
        case.assertEqual([s["reason"] for s in result["secrets"]],
                         [None, "apply_not_confirmed", "apply_not_confirmed", "uid_changed_after_apply"])
        case.assertNotIn(uid(963), env.receipt.read_text())


def scenario_register_conflict(case, mods):
    with env_for(mods) as env:
        registered(env)
        before = env.receipt.read_bytes()

        def failing(plan):
            raise RuntimeError("apply failed")
        case.assertEqual(code_of(lambda: env.register(apply_fn=failing), mods), "receipt_conflict")
        case.assertEqual(env.receipt.read_bytes(), before, "a live UID is never dropped from the receipt")


def scenario_register_policy_read_only(case, mods):
    client = mods.cleanup.open_client(PROJECT, "fake", lambda request: (404, b""), delete=False)
    case.assertEqual(client.policy.delete, frozenset())
    case.assertEqual(client.policy.read, frozenset(k8s_runtime_transport.identity_key(i)
                                                   for i in IDS + [mods.cleanup.KUBE_SYSTEM]))
    client = mods.cleanup.open_client(PROJECT, "fake", lambda request: (404, b""), delete=True)
    case.assertEqual(client.policy.delete, frozenset(k8s_runtime_transport.identity_key(i) for i in IDS))


def scenario_allowlist_follows_layout(case, mods):
    original = k8s_certs.secret_layout

    def drifted(project, material):
        layout = original(project, material)
        layout[0]["metadata"]["name"] = "istio-ca-secret"
        return layout
    with mock.patch.object(k8s_certs, "secret_layout", side_effect=drifted):
        case.assertEqual(code_of(lambda: mods.cleanup.secret_identities(PROJECT), mods), "secret_allowlist_mismatch")


# ---- receipt store ------------------------------------------------------------------------------------------------

def scenario_receipt_missing(case, mods):
    with env_for(mods) as env:
        case.assertEqual(code_of(env.cleanup, mods), "receipt_missing")
        env.root.mkdir(mode=0o700)
        env.dir.mkdir(mode=0o700)
        case.assertEqual(code_of(env.cleanup, mods), "receipt_missing")
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_corrupt(case, mods):
    with env_for(mods) as env:
        registered(env)
        good = env.document()
        cases = [
            ("not json", lambda: env.receipt.write_text("{not json"), "receipt_corrupt"),
            ("extra field", lambda: env.write_document(dict(good, note="x")), "receipt_schema"),
            ("schema", lambda: env.write_document(dict(good, schema="k8s-certs-registration-receipt-v0")),
             "receipt_schema"),
            ("result", lambda: env.tamper(lambda d: (d["secrets"][1].update(uid=None, registration="NOT_VERIFIED",
                                                                           reason="apply_not_confirmed"))),
             "receipt_schema"),
            ("uid", lambda: env.tamper(lambda d: d["secrets"][0].update(uid="not-a-uid")), "receipt_schema"),
            ("uid without registration", lambda: env.tamper(lambda d: (
                d.update(result="INCOMPLETE"), d["secrets"][0].update(registration="NOT_VERIFIED",
                                                                      reason="apply_not_confirmed"))),
             "receipt_schema"),
            ("deleted without uid", lambda: env.tamper(lambda d: (
                d.update(result="INCOMPLETE"), d["secrets"][0].update(
                    uid=None, registration="NOT_VERIFIED", reason="apply_not_confirmed",
                    cleanup={"state": "DELETED", "reason": None, "at": "2026-11-24T00:00:00Z"}))),
             "receipt_schema"),
            ("cleanup state", lambda: env.tamper(lambda d: d["secrets"][0].update(
                cleanup={"state": "GONE", "reason": None, "at": "2026-11-24T00:00:00Z"})), "receipt_schema"),
            ("unhashable values", lambda: env.tamper(lambda d: d["secrets"][0].update(
                cleanup={"state": ["BLOCKED"], "reason": ["forbidden"], "at": "2026-11-24T00:00:00Z"})),
             "receipt_schema"),
            ("unhashable reason", lambda: env.tamper(lambda d: (d.update(result="INCOMPLETE"), d["secrets"][0].update(
                uid=None, registration="NOT_VERIFIED", reason=["apply_not_confirmed"]))), "receipt_schema"),
            ("secret-like", lambda: env.tamper(lambda d: d.update(registered_at="-----BEGIN CERTIFICATE-----")),
             "secret_like_value"),
        ]
        for label, setup, expected in cases:
            with case.subTest(label=label):
                env.write_document(good)
                setup()
                env.cluster.requests.clear()
                case.assertEqual(code_of(env.cleanup, mods), expected, label)
                case.assertEqual(env.secret_requests(), [], label)


def scenario_receipt_not_canonical(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.receipt.write_text(json.dumps(env.document(), indent=2))
        case.assertEqual(code_of(env.cleanup, mods), "receipt_corrupt")
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_schema_fields(case, mods):
    with env_for(mods) as env:
        registered(env)
        good = env.document()
        for label, document in (("extra", dict(good, note="x")),
                                ("version", dict(good, schema="k8s-certs-registration-receipt-v2"))):
            env.write_document(document)
            case.assertEqual(code_of(env.cleanup, mods), "receipt_schema", label)
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_secret_scan(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.tamper(lambda d: d.update(registered_at="-----BEGIN CERTIFICATE-----"))
        case.assertEqual(code_of(env.cleanup, mods), "secret_like_value")


def scenario_receipt_entry_rules(case, mods):
    with env_for(mods) as env:
        registered(env)
        good = env.document()
        cases = [
            ("uid", lambda d: d["secrets"][0].update(uid="not-a-uid")),
            ("uid without registration", lambda d: (d.update(result="INCOMPLETE"), d["secrets"][0].update(
                registration="NOT_VERIFIED", reason="apply_not_confirmed"))),
            ("deleted without uid", lambda d: (d.update(result="INCOMPLETE"), d["secrets"][0].update(
                uid=None, registration="NOT_VERIFIED", reason="apply_not_confirmed",
                cleanup={"state": "DELETED", "reason": None, "at": "2026-11-24T00:00:00Z"}))),
            ("result", lambda d: d["secrets"][1].update(uid=None, registration="NOT_VERIFIED",
                                                        reason="apply_not_confirmed")),
        ]
        for label, change in cases:
            env.write_document(good)
            env.tamper(change)
            case.assertEqual(code_of(env.cleanup, mods), "receipt_schema", label)
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_files(case, mods):
    with env_for(mods) as env:
        registered(env)
        os.chmod(env.receipt, 0o644)
        case.assertEqual(code_of(env.cleanup, mods), "receipt_permission")
        os.chmod(env.receipt, 0o600)
        os.chmod(env.dir, 0o750)
        case.assertEqual(code_of(env.cleanup, mods), "receipt_permission")
        os.chmod(env.dir, 0o700)
        real = env.tmp / "elsewhere.json"
        env.receipt.rename(real)
        env.receipt.symlink_to(real)
        case.assertEqual(code_of(env.cleanup, mods), "receipt_symlink")
        env.receipt.unlink()
        real.rename(env.receipt)
        with mock.patch.object(os, "geteuid", return_value=os.geteuid() + 1):
            case.assertEqual(code_of(env.cleanup, mods), "receipt_owner_mismatch")
        case.assertEqual(env.secret_requests(), [])
        case.assertEqual(env.cleanup()["result"], "COMPLETE")


def scenario_receipt_directory_symlink(case, mods):
    with env_for(mods) as env:
        registered(env)
        moved = env.tmp / "moved"
        env.dir.rename(moved)
        env.dir.symlink_to(moved)
        case.assertEqual(code_of(env.cleanup, mods), "receipt_symlink")
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_repository(case, mods):
    with env_for(mods) as env:
        inside = HERE / "nonexistent-k8s-certs-receipt-root"
        case.assertEqual(code_of(lambda: env.cleanup(root=inside), mods), "receipt_inside_repository")
        case.assertFalse(inside.exists())
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_fingerprint(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.tamper(lambda d: d["cluster"].update(kube_system_uid=uid(77)))
        case.assertEqual(code_of(env.cleanup, mods), "fingerprint_mismatch")
        case.assertEqual(env.secret_requests(), [])
        case.assertEqual([r["path"] for r in env.cluster.requests], ["/api/v1/namespaces/kube-system"])


def scenario_receipt_recreated_cluster(case, mods):
    with env_for(mods) as env:
        registered(env)
        other = env.mods.cleanup.cleanup
        case.assertEqual(code_of(lambda: other(PROJECT, ARN.replace("444455556666", "999988887777"), root=env.root,
                                               server=env.cluster.server), mods), "receipt_missing")
        env.cluster.hooks.clear()
        with mock.patch.object(env.cluster, "server", side_effect=lambda request: (
                (200, partial({"name": "kube-system", "uid": uid(55)})) if request["path"].endswith("/kube-system")
                else FakeCluster.server(env.cluster, request))):
            case.assertEqual(code_of(env.cleanup, mods), "receipt_missing")
        case.assertEqual(env.secret_requests(), [])


def scenario_fingerprint_unreadable(case, mods):
    with env_for(mods) as env:
        registered(env)
        for status in (403, 404, 500):
            with mock.patch.object(env.cluster, "server", side_effect=lambda request, status=status: (status, b"")):
                case.assertEqual(code_of(env.cleanup, mods), "fingerprint_unreadable", status)
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_project_identity(case, mods):
    with env_for(mods) as env:
        registered(env)
        good = env.document()
        env.tamper(lambda d: d.update(project="other"))
        case.assertEqual(code_of(env.cleanup, mods), "receipt_project_mismatch")
        env.write_document(good)
        env.tamper(lambda d: d["secrets"][2]["identity"].update(name="acme-gateway-tls-old"))
        case.assertEqual(code_of(env.cleanup, mods), "receipt_identity_mismatch")
        env.write_document(good)
        env.tamper(lambda d: d["secrets"].pop())
        case.assertEqual(code_of(env.cleanup, mods), "receipt_identity_mismatch")
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_lock(case, mods):
    with env_for(mods) as env:
        registered(env)
        fd = os.open(env.dir / "lock", os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            case.assertEqual(code_of(env.cleanup, mods), "receipt_locked")
            case.assertEqual(code_of(env.register, mods), "receipt_locked")
        finally:
            os.close(fd)
        case.assertEqual(env.secret_requests(), [])


def scenario_receipt_write_validated(case, mods):
    with env_for(mods) as env:
        registered(env)
        before = env.receipt.read_bytes()
        bad = dict(env.document(), result="INCOMPLETE")
        case.assertEqual(code_of(lambda: mods.cleanup.write_receipt(env.dir, bad, PROJECT, env.fp), mods),
                         "receipt_schema")
        case.assertEqual(env.receipt.read_bytes(), before)
        case.assertEqual(sorted(os.listdir(env.dir)), ["lock", "registration.json"])


def scenario_receipt_write_cleans_temporary(case, mods):
    with env_for(mods) as env:
        registered(env)
        before = env.receipt.read_bytes()
        with mock.patch.object(mods.cleanup.os, "replace", side_effect=OSError("disk full")):
            case.assertEqual(code_of(lambda: mods.cleanup.write_receipt(env.dir, env.document(), PROJECT, env.fp),
                                     mods), "receipt_save_failed")
        case.assertEqual(env.receipt.read_bytes(), before)
        case.assertEqual(sorted(os.listdir(env.dir)), ["lock", "registration.json"])


# ---- cleanup ------------------------------------------------------------------------------------------------------

def scenario_cleanup_roundtrip(case, mods):
    with env_for(mods) as env:
        registered(env)
        uids = [e["uid"] for e in env.document()["secrets"]]
        report = env.cleanup()
        case.assertEqual(report["result"], "COMPLETE")
        case.assertEqual([(r["state"], r["reason"]) for r in report["secrets"]], [("DELETED", None)] * 4)
        case.assertEqual(report["namespace_secret_condition"], {"istio-system": "MET", "acme-ingress": "MET",
                                                                "kube-system": "NEVER_DELETED"})
        case.assertEqual((report["kube_system_webhook_tls"], report["namespace_deletion"]), ("MET", "NOT_IMPLEMENTED"))
        expected = [("GET", "/api/v1/namespaces/kube-system")]
        for identity in IDS:
            path = "/api/v1/namespaces/%s/secrets/%s" % (identity["namespace"], identity["name"])
            expected += [("GET", path), ("DELETE", path), ("GET", path)]
        case.assertEqual([(r["method"], r["path"]) for r in env.cluster.requests], expected)
        case.assertEqual([json.loads(r["body"])["preconditions"] for r in env.deletes()], [{"uid": u} for u in uids])
        case.assertTrue(all(r["headers"]["Accept"] == k8s_runtime_transport.METADATA_ACCEPT
                            for r in env.cluster.requests if r["method"] == "GET"))
        case.assertEqual([e["cleanup"]["state"] for e in env.document()["secrets"]], ["DELETED"] * 4)
        case.assertEqual(env.cluster.objects, {})
        env.cluster.requests.clear()
        again = env.cleanup()
        case.assertEqual((again["result"], [r["state"] for r in again["secrets"]]), ("COMPLETE", ["DELETED"] * 4))
        case.assertEqual(env.deletes(), [])
        assert_no_value(case, env, report, again)


def scenario_cleanup_delete_requested_first(case, mods):
    with env_for(mods) as env:
        registered(env)
        seen = []
        env.cluster.hooks[("DELETE", GATEWAY)] = lambda request: seen.append(env.cleanup_of(GATEWAY)["state"])
        case.assertEqual(env.cleanup()["result"], "COMPLETE")
        case.assertEqual(seen, ["DELETE_REQUESTED"])


def scenario_cleanup_already_absent(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.cluster.objects.pop(WEBHOOK)
        report = env.cleanup()
        case.assertEqual(env.state_of(report, WEBHOOK), ("ALREADY_ABSENT", None))
        case.assertEqual(env.cleanup_of(WEBHOOK)["state"], "ALREADY_ABSENT")
        case.assertEqual(env.state_of(report, CACERTS), ("DELETED", None))
        case.assertEqual(report["result"], "COMPLETE")
        case.assertNotIn(WEBHOOK, "".join(r["path"] for r in env.deletes()))
        case.assertEqual(report["kube_system_webhook_tls"], "MET")


def blocked_case(case, mods, name, change, reason):
    """Change one registered Secret in the cluster; cleanup must leave it in place with the reason."""
    with env_for(mods) as env:
        registered(env)
        change(env.cluster.objects[name], env)
        report = env.cleanup()
        case.assertEqual(env.state_of(report, name), ("BLOCKED", reason))
        case.assertEqual(env.cleanup_of(name)["state"], "BLOCKED")
        case.assertEqual(env.cleanup_of(name)["reason"], reason)
        case.assertIn(name, env.cluster.objects, "a refused Secret stays in place")
        case.assertFalse(any(r["path"].endswith("/" + name) for r in env.deletes()), "no DELETE for a refused Secret")
        case.assertEqual(report["result"], "INCOMPLETE")
        return report


def scenario_cleanup_labels(case, mods):
    blocked_case(case, mods, CACERTS, lambda m, e: m["labels"].pop("app.kubernetes.io/managed-by"), "label_managed_by")
    blocked_case(case, mods, CACERTS, lambda m, e: m["labels"].update({"app.kubernetes.io/managed-by": "helm"}),
                 "label_managed_by")
    report = blocked_case(case, mods, GATEWAY, lambda m, e: m["labels"].update({"app.kubernetes.io/part-of": "other"}),
                          "label_project")
    case.assertEqual(report["namespace_secret_condition"]["acme-ingress"], "BLOCKED")
    case.assertEqual(report["namespace_secret_condition"]["istio-system"], "MET")


def foreign(m, e):
    m["managedFields"].append({"manager": "kubectl-edit", "operation": "Update", "apiVersion": "v1",
                               "fieldsType": "FieldsV1", "fieldsV1": {"f:metadata": {"f:annotations": {}}}})


def scenario_cleanup_foreign_manager(case, mods):
    report = blocked_case(case, mods, WEBHOOK, foreign, "foreign_manager")
    case.assertEqual(report["kube_system_webhook_tls"], "BLOCKED")
    case.assertEqual(report["namespace_secret_condition"]["kube-system"], "NEVER_DELETED")


def scenario_cleanup_apply_entry(case, mods):
    blocked_case(case, mods, GATEWAY, lambda m, e: m["managedFields"][0].update(manager="acme-k8s-runtime"),
                 "apply_entry_missing")
    blocked_case(case, mods, GATEWAY, lambda m, e: m.update(managedFields=[]), "apply_entry_missing")


def scenario_cleanup_operation(case, mods):
    blocked_case(case, mods, GATEWAY, lambda m, e: m["managedFields"][0].update(operation="Update"),
                 "manager_operation")


def scenario_cleanup_managed_fields_shape(case, mods):
    blocked_case(case, mods, CLIENT_CA, lambda m, e: m.update(managedFields=None), "managed_fields_malformed")
    blocked_case(case, mods, CLIENT_CA, lambda m, e: m["managedFields"][0].update(subresource="status"),
                 "managed_fields_malformed")
    blocked_case(case, mods, CLIENT_CA, lambda m, e: m["managedFields"].append(dict(m["managedFields"][0])),
                 "managed_fields_malformed")


def scenario_cleanup_field_ownership(case, mods):
    blocked_case(case, mods, CLIENT_CA, lambda m, e: m["managedFields"][0]["fieldsV1"]["f:metadata"].update(
        {"f:annotations": {"f:example.com/x": {}}}), "field_ownership")
    blocked_case(case, mods, CLIENT_CA, lambda m, e: m["managedFields"][0]["fieldsV1"].pop("f:type"),
                 "field_ownership")


def scenario_cleanup_uid_mismatch(case, mods):
    blocked_case(case, mods, CACERTS, lambda m, e: m.update(uid=uid(901)), "uid_mismatch")


def scenario_cleanup_delete_conflict(case, mods):
    def recreate_at_delete(m, env):
        def swap(request):
            env.cluster.objects[CACERTS] = secret_metadata(CACERTS, uid(902))
        env.cluster.hooks[("DELETE", CACERTS)] = swap
    with env_for(mods) as env:
        registered(env)
        recreate_at_delete(None, env)
        report = env.cleanup()
        case.assertEqual(env.state_of(report, CACERTS), ("BLOCKED", "uid_precondition_failed"))
        case.assertEqual(env.cluster.objects[CACERTS]["uid"], uid(902), "the recreated Secret is never deleted")
        case.assertEqual(report["namespace_secret_condition"]["istio-system"], "BLOCKED")


def hook_case(case, mods, method, answer, reason, name=GATEWAY):
    with env_for(mods) as env:
        registered(env)
        env.cluster.hooks[(method, name)] = answer
        report = env.cleanup()
        case.assertEqual(env.state_of(report, name), ("BLOCKED", reason), (method, reason))
        case.assertEqual(env.cleanup_of(name)["reason"], reason)
        case.assertEqual(report["result"], "INCOMPLETE")
        case.assertIn(name, env.cluster.objects)
        assert_no_value(case, env, report)
        return env, report


def timeout(request):
    raise TimeoutError("timed out")


def scenario_cleanup_delete_errors(case, mods):
    for status, reason in ((403, "forbidden"), (500, "unexpected_status"), (503, "unexpected_status")):
        hook_case(case, mods, "DELETE", lambda request, status=status: (status, b""), reason)
    hook_case(case, mods, "DELETE", timeout, "transport_timeout")
    hook_case(case, mods, "DELETE", lambda request: (_ for _ in ()).throw(ConnectionResetError("reset")),
              "transport_unknown")


def scenario_cleanup_get_errors(case, mods):
    for status, reason in ((403, "forbidden"), (500, "unexpected_status")):
        env, _ = hook_case(case, mods, "GET", lambda request, status=status: (status, b""), reason)
        case.assertEqual([r for r in env.deletes() if GATEWAY in r["path"]], [])
    hook_case(case, mods, "GET", timeout, "transport_timeout")
    hook_case(case, mods, "GET", lambda request: (200, b"{not json"), "response_not_json")
    hook_case(case, mods, "GET", lambda request: (200, partial({"name": GATEWAY, "namespace": "acme-ingress",
                                                                "uid": "bad"})), "response_uid_invalid")


def scenario_cleanup_full_secret(case, mods):
    full = json.dumps({"kind": "Secret", "apiVersion": "v1", "type": "kubernetes.io/tls",
                       "metadata": secret_metadata(GATEWAY, uid(1)), "data": {"tls.key": ENCODED_MARKER}}).encode()
    hook_case(case, mods, "GET", lambda request: (200, full), "response_not_metadata_only")
    annotated = dict(secret_metadata(GATEWAY, uid(1)),
                     annotations={"kubectl.kubernetes.io/last-applied-configuration": VALUE_MARKER})
    hook_case(case, mods, "GET", lambda request: (200, partial(annotated)), "response_secret_annotation_refused")


def scenario_cleanup_delete_absent(case, mods):
    hook_case(case, mods, "DELETE", lambda request: (404, b""), "deleted_concurrently")


def scenario_cleanup_still_present(case, mods):
    hook_case(case, mods, "DELETE", lambda request: (200, b""), "still_present_after_delete")
    hook_case(case, mods, "DELETE", lambda request: (202, b""), "still_present_after_delete")


def scenario_cleanup_confirm_errors(case, mods):
    for answer, reason in ((lambda: (403, b""), "forbidden"), (lambda: (500, b""), "unexpected_status"),
                           (lambda: timeout(None), "transport_timeout")):
        with env_for(mods) as env:
            registered(env)
            deleted = []
            env.cluster.hooks[("DELETE", GATEWAY)] = lambda request: deleted.append(1)
            env.cluster.hooks[("GET", GATEWAY)] = lambda request, answer=answer: answer() if deleted else None
            report = env.cleanup()
            case.assertEqual(env.state_of(report, GATEWAY), ("BLOCKED", reason))
            case.assertEqual(report["result"], "INCOMPLETE", "absence was not confirmed")


def scenario_cleanup_recreated_after_delete(case, mods):
    with env_for(mods) as env:
        registered(env)

        def delete_then_recreate(request):
            del env.cluster.objects[GATEWAY]
            env.cluster.put(GATEWAY, uid(903))
            return 202, b""
        env.cluster.hooks[("DELETE", GATEWAY)] = delete_then_recreate
        report = env.cleanup()
        case.assertEqual(env.state_of(report, GATEWAY), ("BLOCKED", "recreated_after_delete"))
        case.assertEqual(env.cluster.objects[GATEWAY]["uid"], uid(903))


def scenario_cleanup_accepted_then_gone(case, mods):
    with env_for(mods) as env:
        registered(env)

        def accept(request):
            del env.cluster.objects[GATEWAY]
            return 202, b""
        env.cluster.hooks[("DELETE", GATEWAY)] = accept
        case.assertEqual(env.state_of(env.cleanup(), GATEWAY), ("DELETED", None))


def scenario_cleanup_recreated_after_cleanup(case, mods):
    with env_for(mods) as env:
        registered(env)
        case.assertEqual(env.cleanup()["result"], "COMPLETE")
        env.cluster.put(CLIENT_CA)
        env.cluster.requests.clear()
        report = env.cleanup()
        case.assertEqual(env.state_of(report, CLIENT_CA), ("BLOCKED", "recreated_after_cleanup"))
        case.assertEqual(env.deletes(), [])
        case.assertIn(CLIENT_CA, env.cluster.objects)


def scenario_cleanup_incomplete_receipt(case, mods):
    with env_for(mods) as env:
        env.register(apply_fn=lambda plan: env.cluster.apply(plan)[:3])  # CLIENT_CA written but NOT_VERIFIED
        env.cluster.requests.clear()
        report = env.cleanup()
        case.assertEqual(env.state_of(report, CLIENT_CA), ("BLOCKED", "receipt_uid_unavailable"))
        case.assertFalse(any(CLIENT_CA in r["path"] for r in env.cluster.requests))
        case.assertIn(CLIENT_CA, env.cluster.objects, "an unknown Secret is never adopted or deleted")
        case.assertEqual(report["namespace_secret_condition"]["acme-ingress"], "BLOCKED")
        case.assertEqual(report["result"], "INCOMPLETE")


def scenario_cleanup_rerun_after_block(case, mods):
    with env_for(mods) as env:
        registered(env)

        def deleted_by_someone_else(request):
            del env.cluster.objects[GATEWAY]
            return 404, b""
        env.cluster.hooks[("DELETE", GATEWAY)] = deleted_by_someone_else
        case.assertEqual(env.state_of(env.cleanup(), GATEWAY), ("BLOCKED", "deleted_concurrently"))
        env.cluster.hooks.clear()
        report = env.cleanup()
        case.assertEqual(env.state_of(report, GATEWAY), ("ALREADY_ABSENT", None))
        case.assertEqual(env.cleanup_of(GATEWAY)["state"], "ALREADY_ABSENT")
        case.assertEqual(report["result"], "COMPLETE")


def scenario_no_fallback(case, mods):
    with env_for(mods) as env:
        registered(env)
        env.cluster.hooks[("DELETE", GATEWAY)] = lambda request: (409, b"")
        env.cluster.hooks[("GET", CACERTS)] = lambda request: (403, b"")
        with mock.patch("subprocess.run", side_effect=AssertionError("no process may start")) as run, \
                mock.patch.object(k8s_certs, "delete", side_effect=AssertionError("no name-based delete")) as old:
            report = env.cleanup()
        case.assertEqual((run.call_count, old.call_count), (0, 0))
        case.assertEqual(report["result"], "INCOMPLETE")
        for request in env.cluster.requests:
            case.assertIn(request["method"], ("GET", "DELETE"))
            case.assertTrue(request["path"] == "/api/v1/namespaces/kube-system" or SECRET_PATH.fullmatch(request["path"]))
        for request in env.deletes():
            case.assertTrue(UID_RE.fullmatch(json.loads(request["body"])["preconditions"]["uid"]))
        case.assertEqual(sum(1 for r in env.deletes() if GATEWAY in r["path"]), 1, "no retry, no other delete")
        case.assertEqual(sum(1 for r in env.deletes() if CACERTS in r["path"]), 0)


UID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def scenario_no_process_or_network_code(case, mods):
    tree = ast.parse((HERE / "k8s_certs_receipt.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "k8s_certs":
            case.assertIn(node.attr, {"check_project", "CertError", "secret_layout"}, "only the layout and the project rule")
    case.assertEqual(imported & {"subprocess", "socket", "ssl", "http", "urllib", "requests", "httpx", "urllib3",
                                 "kubernetes"}, set())


def scenario_real_refused(case, mods):
    with env_for(mods) as env:
        for kind in ("https", "kubectl", "real"):
            case.assertEqual(code_of(lambda: env.cleanup(kind=kind), mods), "real_transport_not_implemented", kind)
            case.assertEqual(code_of(lambda: env.register(kind=kind), mods), "real_transport_not_implemented", kind)
        case.assertFalse(env.root.exists(), "no receipt is created before the transport is open")
        case.assertEqual(env.cluster.requests, [])
        policy = k8s_runtime_transport.Policy(IDS, IDS, secret_project=PROJECT)
        case.assertEqual(code_of(lambda: k8s_runtime_transport.open_transport("https", policy, env.cluster.server),
                                 mods), "real_transport_not_implemented")
        case.assertEqual(code_of(lambda: k8s_runtime_transport.HttpsTransport(policy), mods),
                         "real_transport_not_implemented")


def scenario_old_delete_retired(case, mods):
    certs = mods.certs
    output = []
    with mock.patch("subprocess.run", side_effect=AssertionError("no process may start")) as run:
        code = certs.delete(PROJECT, kubectl_binary="/nonexistent/kubectl", env={"PATH": "/usr/bin:/bin"},
                            out_fn=output.append, terraform="/nonexistent/terraform", services=Path("/nonexistent"))
    case.assertEqual((code, run.call_count), (1, 0))
    case.assertEqual(len(output), 1)
    case.assertTrue(output[0].startswith("Refused (name_based_delete_retired)"), output)


def scenario_old_delete_automation_first(case, mods):
    output = []
    with mock.patch("subprocess.run", side_effect=AssertionError("no process may start")):
        code = mods.certs.delete(PROJECT, env={"PATH": "/usr/bin:/bin", "CI": "true"}, out_fn=output.append)
    case.assertEqual(code, 1)
    case.assertTrue(output[0].startswith("Refused (live_refused_in_ci)"), output)


# ---- unit tests ---------------------------------------------------------------------------------------------------

class SecretTransportTests(unittest.TestCase):
    def test_secret_allowlist_is_the_k8s_certs_layout(self):
        scenario_secret_allowlist(self, real_mods())
        scenario_allowlist_follows_layout(self, real_mods())

    def test_secret_requests_metadata_get_and_uid_delete_only(self):
        scenario_secret_requests(self, real_mods())

    def test_secret_responses_metadata_only(self):
        scenario_secret_responses(self, real_mods())

    def test_real_transport_and_real_operations_refused(self):
        scenario_real_refused(self, real_mods())
        scenario_no_process_or_network_code(self, real_mods())
        scenario_old_delete_retired(self, real_mods())
        scenario_old_delete_automation_first(self, real_mods())


class RegistrationReceiptTests(unittest.TestCase):
    def test_register_records_uids_from_metadata(self):
        scenario_register_roundtrip(self, real_mods())
        scenario_register_policy_read_only(self, real_mods())

    def test_normal_registrations(self):
        scenario_register_again_same_uids(self, real_mods())
        scenario_register_after_cleanup(self, real_mods())

    def test_partial_registration_is_never_success(self):
        scenario_register_partial(self, real_mods())
        scenario_register_failures(self, real_mods())
        scenario_register_foreign_report(self, real_mods())
        scenario_register_ownership(self, real_mods())

    def test_receipt_save_failure_is_never_success(self):
        scenario_register_save_failure(self, real_mods())
        scenario_receipt_write_cleans_temporary(self, real_mods())

    def test_receipt_never_drops_a_live_uid(self):
        scenario_register_conflict(self, real_mods())

    def test_existing_secret_without_receipt_never_adopted(self):
        scenario_register_existing_without_receipt(self, real_mods())
        scenario_register_all_existing_matching(self, real_mods())

    def test_preconditions_checked_for_all_four_before_apply(self):
        scenario_register_uid_mismatch_before_apply(self, real_mods())
        scenario_register_claimed_absent(self, real_mods())
        scenario_register_claimed_ownership(self, real_mods())
        scenario_register_precondition_unreadable(self, real_mods())

    def test_cleaned_or_unverified_secret_never_rebuilt(self):
        scenario_register_recreated_after_cleanup(self, real_mods())
        scenario_register_no_rebuild_from_unverified(self, real_mods())

    def test_apply_result_bound_to_metadata_uid(self):
        scenario_apply_evidence(self, real_mods())
        scenario_register_recreated_before_apply(self, real_mods())
        scenario_register_plan_tamper(self, real_mods())
        scenario_register_uid_changed_after_apply(self, real_mods())
        scenario_register_apply_uid_missing_or_wrong(self, real_mods())

    def test_receipt_missing_corrupt_or_tampered(self):
        scenario_receipt_missing(self, real_mods())
        scenario_receipt_corrupt(self, real_mods())
        scenario_receipt_not_canonical(self, real_mods())
        scenario_receipt_write_validated(self, real_mods())

    def test_receipt_modes_symlinks_owner_and_location(self):
        scenario_receipt_files(self, real_mods())
        scenario_receipt_directory_symlink(self, real_mods())
        scenario_receipt_repository(self, real_mods())
        scenario_receipt_lock(self, real_mods())

    def test_receipt_fingerprint_project_and_identity(self):
        scenario_receipt_fingerprint(self, real_mods())
        scenario_receipt_recreated_cluster(self, real_mods())
        scenario_fingerprint_unreadable(self, real_mods())
        scenario_receipt_project_identity(self, real_mods())


class SecretCleanupTests(unittest.TestCase):
    def test_cleanup_deletes_by_receipt_uid_and_confirms_absence(self):
        scenario_cleanup_roundtrip(self, real_mods())
        scenario_cleanup_delete_requested_first(self, real_mods())
        scenario_cleanup_accepted_then_gone(self, real_mods())

    def test_already_absent_recorded_apart_from_deleted(self):
        scenario_cleanup_already_absent(self, real_mods())
        scenario_cleanup_rerun_after_block(self, real_mods())

    def test_labels_required(self):
        scenario_cleanup_labels(self, real_mods())

    def test_field_managers_required(self):
        scenario_cleanup_foreign_manager(self, real_mods())
        scenario_cleanup_apply_entry(self, real_mods())
        scenario_cleanup_operation(self, real_mods())
        scenario_cleanup_managed_fields_shape(self, real_mods())
        scenario_cleanup_field_ownership(self, real_mods())

    def test_uid_mismatch_and_precondition_conflict(self):
        scenario_cleanup_uid_mismatch(self, real_mods())
        scenario_cleanup_delete_conflict(self, real_mods())

    def test_transport_failures_fail_closed(self):
        scenario_cleanup_delete_errors(self, real_mods())
        scenario_cleanup_get_errors(self, real_mods())
        scenario_cleanup_delete_absent(self, real_mods())
        scenario_cleanup_confirm_errors(self, real_mods())

    def test_full_secret_response_refused_without_output(self):
        scenario_cleanup_full_secret(self, real_mods())

    def test_success_status_alone_is_not_success(self):
        scenario_cleanup_still_present(self, real_mods())
        scenario_cleanup_recreated_after_delete(self, real_mods())
        scenario_cleanup_recreated_after_cleanup(self, real_mods())

    def test_unknown_secret_never_adopted(self):
        scenario_cleanup_incomplete_receipt(self, real_mods())

    def test_no_name_based_delete_fallback(self):
        scenario_no_fallback(self, real_mods())


# ---- mutations ----------------------------------------------------------------------------------------------------

C, T, X = "k8s_certs_receipt.py", "k8s_runtime_transport.py", "k8s_certs.py"
SECRET_MUTATIONS = [
    # transport: the four-Secret extension
    ("secret_policy_allowlist", T, 'need(all(k in self.secrets for k in self.read if k[1] == "Secret"), "secret_path_not_approved")',
     "pass", scenario_secret_allowlist),
    ("secret_project_rule", T, '    need(isinstance(project, str) and SECRET_PROJECT.fullmatch(project) is not None\n         and re.search("aws|amazon|cognito", project) is None, "secret_project_invalid")',
     "    pass", scenario_secret_allowlist),
    ("secret_plural", T, 'plural, namespaced = "secrets", True', 'plural, namespaced = "secret", True',
     scenario_secret_requests),
    ("last_applied", T, 'need(LAST_APPLIED not in annotations, "response_secret_annotation_refused")', "pass",
     scenario_secret_responses),
    ("secret_metadata_reduced", T, "return {key: metadata[key] for key in SECRET_METADATA_FIELDS if key in metadata}",
     "return metadata", scenario_secret_responses),
    ("annotation_shape", T, '        need(isinstance(annotations, dict), "response_shape")\n', "", scenario_secret_responses),
    # registration
    ("allowlist_matches_layout", C, 'need(identities == layout, "secret_allowlist_mismatch")', "pass",
     scenario_allowlist_follows_layout),
    ("open_real_refusal", C, "return transport.open_transport(transport_kind, policy, server)",
     "return transport.FakeTransport(policy, server)", scenario_real_refused),
    ("registration_read_only", C, "identities if delete else ()", "identities", scenario_register_policy_read_only),
    ("pre_read_failure", C, 'need(reason is None, "precondition_unreadable")', "pass",
     scenario_register_precondition_unreadable),
    ("unknown_existing", C, "            if current is not None:\n                raise", "            if False:\n                raise",
     scenario_register_all_existing_matching),
    ("claimed_absent", C, 'need(current is not None, "receipt_uid_absent")', "pass", scenario_register_claimed_absent),
    ("claimed_uid", C, 'need(current == claim, "receipt_uid_mismatch")', "pass",
     scenario_register_uid_mismatch_before_apply),
    ("claimed_ownership", C, 'need(problem is None, "precondition_" + str(problem))', "pass",
     scenario_register_claimed_ownership),
    ("unverified_code", C, '    if entry["registration"] != "REGISTERED":\n        return "unverified_secret_present"',
     '    if False:\n        return "unverified_secret_present"', scenario_register_no_rebuild_from_unverified),
    ("live_claim_cleaned", C, 'if entry is None or (entry["cleanup"] or {}).get("state") in CLEANED:',
     "if entry is None:", scenario_register_after_cleanup),
    ("apply_unknown_identity", C, "if len(set(keys)) != len(keys) or not set(keys) <= set(expected):",
     "if len(set(keys)) != len(keys):", scenario_register_foreign_report),
    ("apply_repeated_identity", C, "if len(set(keys)) != len(keys) or not set(keys) <= set(expected):",
     "if not set(keys) <= set(expected):", scenario_apply_evidence),
    ("apply_uid_format", C, "        if not (isinstance(uid, str) and safety.UID.fullmatch(uid) is not None):\n            continue\n",
     "", scenario_register_apply_uid_missing_or_wrong),
    ("apply_created_outcome", C, 'if expect is None and item.get("outcome") == "created":', "if expect is None:",
     scenario_register_recreated_before_apply),
    ("apply_updated_uid", C, 'item.get("outcome") == "updated" and uid == expect:', 'item.get("outcome") == "updated":',
     scenario_apply_evidence),
    ("apply_updated_outcome", C, 'elif expect is not None and item.get("outcome") == "updated" and uid == expect:',
     "elif expect is not None and uid == expect:", scenario_apply_evidence),
    ("post_apply_uid", C, '                if reason is None and metadata["uid"] != applied_uid:\n',
     "                if False:\n", scenario_register_uid_changed_after_apply),
    ("plan_copied", C, "result = apply_fn(copy.deepcopy(plan))", "result = apply_fn(plan)",
     scenario_register_plan_tamper),
    ("registration_ownership", C,
     'reason = "absent_after_apply" if metadata is None else ownership_problem(project, identity, metadata)',
     'reason = "absent_after_apply" if metadata is None else None', scenario_register_ownership),
    ("registration_conflict", C, 'need(new["uid"] == claim, "receipt_conflict")', "pass",
     scenario_register_conflict),
    ("save_failure_cleanup", C, "            with contextlib.suppress(OSError):\n                os.unlink(temporary)",
     "            pass", scenario_receipt_write_cleans_temporary),
    ("write_validated", C, "    check_receipt(document, project, fp)\n    data = safety.canonical(document).encode()",
     "    data = safety.canonical(document).encode()", scenario_receipt_write_validated),
    # receipt store
    ("repository_location", C, 'need(not safety.inside_repository(root), "receipt_inside_repository")', "pass",
     scenario_receipt_repository),
    ("directory_checked", C, "            safety.check_dir(root)\n        safety.check_dir(directory)",
     "            safety.check_dir(root)", scenario_receipt_directory_symlink),
    ("lock_exclusive", C, "fcntl.LOCK_EX | fcntl.LOCK_NB", "fcntl.LOCK_SH | fcntl.LOCK_NB", scenario_receipt_lock),
    ("canonical", C, 'need(safety.canonical(document).encode() == data, "receipt_corrupt")', "pass",
     scenario_receipt_not_canonical),
    ("top_level_schema", C, 'need(isinstance(document, dict) and set(document) == TOP_FIELDS and document["schema"] == SCHEMA, "receipt_schema")',
     'need(isinstance(document, dict), "receipt_schema")', scenario_receipt_schema_fields),
    ("secret_scan", C, 'need(len(value) <= 512 and value.isprintable() and not safety.SECRET_LIKE.search(value), "secret_like_value")',
     "pass", scenario_receipt_secret_scan),
    ("project_match", C, 'need(document["project"] == project, "receipt_project_mismatch")', "pass",
     scenario_receipt_project_identity),
    ("fingerprint_match", C, '         == (fp["cluster_arn"], fp["kube_system_uid"], fp["id"]), "fingerprint_mismatch")',
     '         == (cluster["cluster_arn"], cluster["kube_system_uid"], cluster["fingerprint_id"]), "fingerprint_mismatch")',
     scenario_receipt_fingerprint),
    ("fingerprint_readable", C, 'need(reason is None and uid is not None, "fingerprint_unreadable")', "pass",
     scenario_fingerprint_unreadable),
    ("identity_match", C, 'need(entry["identity"] == identity, "receipt_identity_mismatch")', "pass",
     scenario_receipt_project_identity),
    ("registered_uid_valid", C, "        need(isinstance(entry[\"uid\"], str) and safety.UID.fullmatch(entry[\"uid\"]) is not None\n             and entry[\"reason\"] is None, \"receipt_schema\")",
     "        pass", scenario_receipt_entry_rules),
    ("unverified_without_uid", C, 'need(entry["registration"] == "NOT_VERIFIED" and entry["uid"] is None and known(entry["reason"], REASONS),',
     'need(entry["registration"] == "NOT_VERIFIED" and known(entry["reason"], REASONS),', scenario_receipt_entry_rules),
    ("deleted_needs_uid", C, 'need(entry["registration"] == "REGISTERED" or cleanup["state"] == "BLOCKED", "receipt_schema")',
     "pass", scenario_receipt_entry_rules),
    ("result_consistent", C, 'need(document["result"] == ("REGISTERED" if complete else "INCOMPLETE"), "receipt_schema")',
     "pass", scenario_receipt_entry_rules),
    # cleanup: the ten steps
    ("uid_unavailable_blocks", C, '    if entry["registration"] != "REGISTERED":\n        return record("BLOCKED", "receipt_uid_unavailable")',
     '    if False:\n        return record("BLOCKED", "receipt_uid_unavailable")', scenario_cleanup_incomplete_receipt),
    ("get_failure_not_absent", C, '    metadata, reason = attempt(lambda: client.get_metadata(identity))\n    if reason is not None:\n        return record("BLOCKED", reason)\n    if metadata is None:',
     '    metadata, reason = attempt(lambda: client.get_metadata(identity))\n    if metadata is None:', scenario_cleanup_get_errors),
    ("absent_distinct", C, 'return record("DELETED" if previous == "DELETED" else "ALREADY_ABSENT")', 'return record("DELETED")',
     scenario_cleanup_already_absent),
    ("recreated_after_cleanup", C, "    if previous in CLEANED:\n", "    if False:\n", scenario_cleanup_recreated_after_cleanup),
    ("label_managed_by", C, 'if not isinstance(labels, dict) or labels.get(MANAGED_BY_LABEL) != MANAGED_BY:',
     "if not isinstance(labels, dict):", scenario_cleanup_labels),
    ("label_project", C, "    if labels.get(PART_OF_LABEL) != project:\n", "    if False:\n", scenario_cleanup_labels),
    ("managed_fields_shape", C, "    if entries is not managers or not all(isinstance(m, dict) for m in entries):\n",
     "    if False:\n", scenario_cleanup_managed_fields_shape),
    ("apply_entry_present", C, "    if not named:\n        return \"apply_entry_missing\"",
     "    if False:\n        return \"apply_entry_missing\"", scenario_cleanup_apply_entry),
    ("manager_operation", C, '    if any(m.get("operation") != "Apply" for m in named):\n', "    if False:\n",
     scenario_cleanup_operation),
    ("foreign_manager", C, "    if len(named) != len(entries):\n", "    if False:\n", scenario_cleanup_foreign_manager),
    ("single_entry", C, "    if len(named) != 1:\n", "    if False:\n", scenario_cleanup_managed_fields_shape),
    ("entry_fields", C, 'if set(entry) - MANAGER_FIELDS or entry.get("apiVersion") != "v1"',
     'if entry.get("apiVersion") != "v1"', scenario_cleanup_managed_fields_shape),
    ("field_ownership", C, '    if field_leaves(entry.get("fieldsV1")) != expected_leaves(project, identity):\n',
     "    if False:\n", scenario_cleanup_field_ownership),
    ("uid_match", C, '    if metadata["uid"] != uid:\n', "    if False:\n", scenario_cleanup_uid_mismatch),
    ("delete_requested_first", C, '    record("DELETE_REQUESTED")\n', "", scenario_cleanup_delete_requested_first),
    ("delete_failure_blocks", C, '    outcome, reason = attempt(lambda: client.delete_with_uid(identity, uid))\n    if reason is not None:\n        return record("BLOCKED", reason)',
     '    outcome, reason = attempt(lambda: client.delete_with_uid(identity, uid))', scenario_cleanup_delete_errors),
    ("delete_absent_blocks", C, '    if outcome not in ("deleted", "accepted"):\n', "    if False:\n",
     scenario_cleanup_delete_absent),
    ("confirm_absence", C, "    if after is not None:\n", "    if False:\n", scenario_cleanup_still_present),
    ("recreated_distinct", C, '"still_present_after_delete" if after["uid"] == uid else "recreated_after_delete"',
     '"still_present_after_delete"', scenario_cleanup_recreated_after_delete),
    ("confirm_failure_blocks", C, '    after, reason = attempt(lambda: client.get_metadata(identity))\n    if reason is not None:\n        return record("BLOCKED", reason)',
     '    after, reason = attempt(lambda: client.get_metadata(identity))', scenario_cleanup_confirm_errors),
    ("timeout_unknown", C, '    except TimeoutError:\n        return None, "transport_timeout"\n', "",
     scenario_cleanup_delete_errors),
    ("namespace_condition", C, 'return "MET" if mine and all(r["state"] in CLEANED for r in mine) else "BLOCKED"',
     'return "MET"', scenario_cleanup_labels),
    ("kube_system_never_deleted", C, '"kube-system": "NEVER_DELETED"}', '"kube-system": condition("kube-system")}',
     scenario_cleanup_foreign_manager),
    # the retired name-based delete
    ("old_delete_refusal", X, "    out_fn(DELETE_RETIRED)\n    return 1",
     '    out_fn("Deleted the 4 Secrets from " + context + " (absent ones ignored).")\n    return 0',
     scenario_old_delete_retired),
    ("old_delete_automation", X, "    if refusal:\n        out_fn(refusal)\n        return 1\n    out_fn(DELETE_RETIRED)",
     "    out_fn(DELETE_RETIRED)", scenario_old_delete_automation_first),
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


class SecretMutationTests(unittest.TestCase):
    def test_each_secret_guard_mutation_is_detected_by_an_assertion(self):
        self.assertEqual(len(SECRET_MUTATIONS), 67)
        self.assertEqual(len({m[0] for m in SECRET_MUTATIONS}), len(SECRET_MUTATIONS))
        undetected = []
        for name, filename, old, new, scenario in SECRET_MUTATIONS:
            mods = real_mods()
            setattr(mods, {C: "cleanup", T: "transport", X: "certs"}[filename], mutant(filename, old, new))
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
