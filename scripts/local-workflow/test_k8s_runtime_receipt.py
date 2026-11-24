#!/usr/bin/env python3
"""Offline tests for the 6c-B3a execution safety foundation.

Covers ``k8s_runtime_receipt`` (store, journal, snapshot, crash reconciliation),
``k8s_runtime_transport`` (the D19 contract and its fake) and the ``k8s_runtime``
gate, pins, fingerprint and read-only ``receipt verify``.

Nothing here reaches a cluster or AWS. Stores live in temporary directories outside
the repository. ``receipt verify --cluster`` runs against the fake kubectl and
synthetic cluster of ``test_k8s_runtime_status``, so the pinned Helm
(``K8S_RUNTIME_HELM``) is required for those cases, as for the status tests.

``MutationTests`` removes one guard at a time from the three modules and requires
the matching scenario to detect it.

The G9/D19 tests of ``test_k8s_certs_receipt`` (registration UID receipt, Secret
cleanup, the four-Secret transport extension and the retired name-based delete) run
in this suite too: their test classes are imported below, and ``MUTATIONS`` counts
the runtime mutations and ``SECRET_MUTATIONS`` together.

The 6c-B4a destroy foundation tests of ``test_k8s_runtime_destroy_foundation`` (destroy
transport scopes, discovery, metadata LIST and pagination, the specialised CRD and Service
reads, the destroy phase of the journal and the apply phase guard) run here as well, and
``DESTROY_MUTATIONS`` is part of ``MUTATIONS``.
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
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
import k8s_runtime_receipt  # noqa: E402
import k8s_runtime_transport  # noqa: E402
import preflight  # noqa: E402
from test_k8s_certs_receipt import (SECRET_MUTATIONS, RegistrationReceiptTests, SecretCleanupTests,  # noqa: E402,F401
                                    SecretMutationTests, SecretTransportTests)
from test_k8s_runtime_destroy_foundation import (DESTROY_MUTATIONS, CrdAndServiceReadTests,  # noqa: E402,F401
                                                 DestroyJournalTests, DestroyMutationTests, DestroyTransportTests,
                                                 DiscoveryAndListTests)

PROJECT = "acme"
ARN = "arn:aws:eks:ca-central-1:444455556666:cluster/acme-dev-eks"
KUBE_SYSTEM_UID = "11111111-2222-4333-8444-555555555555"
SHA_A = "a" * 64
SHA_B = "b" * 64
ABSENT = {"state": "absent"}


def uid(n):
    return "00000000-0000-4000-8000-%012x" % n


def table_plan(module):
    return module.Plan([(name, [dict(zip(("apiVersion", "kind", "namespace", "name"), row)) for row in rows])
                        for name, rows in k8s_runtime.load_stage_table(PROJECT)])


class Mods(types.SimpleNamespace):
    """The three modules under test; a mutation replaces one of them."""


def real_mods():
    return Mods(receipt=k8s_runtime_receipt, transport=k8s_runtime_transport, runtime=k8s_runtime)


class Env:
    """A temporary root outside the repository, a store and the stage-table plan."""

    def __init__(self, mods):
        self.mods = mods
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-receipt-"))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "state"
        self.plan = table_plan(mods.receipt)
        self.fp = mods.receipt.fingerprint(ARN, KUBE_SYSTEM_UID)
        self.expected = {"fingerprint": self.fp, "project": PROJECT, "manifest_sha256": SHA_A, "input_sha256": SHA_B}

    def store(self, **overrides):
        args = dict(fp=self.fp, project=PROJECT, manifest_sha256=SHA_A, input_sha256=SHA_B)
        args.update(overrides)
        return self.mods.receipt.Store(self.root, args["fp"], args["project"], args["manifest_sha256"],
                                       args["input_sha256"], self.plan)

    def members(self, stage):
        return [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|"))) for k in self.plan.members[stage]]

    def apply_stage(self, store, stage, base=1):
        for offset, identity in enumerate(self.members(stage)):
            seq = store.intent(stage, identity, ABSENT, "create")
            store.result(seq, identity, uid(base + offset), "100", 1, "applied")
        store.stage_done(stage)

    def load(self, expected=None, directory=None):
        return self.mods.receipt.load(directory or self.root / self.fp["id"], self.plan, expected or self.expected)

    @property
    def dir(self):
        return self.root / self.fp["id"]

    def journal_lines(self):
        return (self.dir / "journal.jsonl").read_bytes().splitlines(keepends=True)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@contextlib.contextmanager
def env_for(mods):
    env = Env(mods)
    try:
        yield env
    finally:
        env.cleanup()


def error_of(call, *exceptions):
    try:
        call()
    except exceptions as raised:
        return str(raised)
    except Exception as raised:  # noqa: BLE001 - mutants raise their own exception classes
        return type(raised).__name__ + ":" + str(raised)
    return None


# ---- scenarios (shared by the unit tests and the mutation tests) ---------------------------------------------------

def scenario_roundtrip(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            case.assertEqual(store.begin(), "CREATED")
            env.apply_stage(store, "namespaces")
        loaded = env.load()
        case.assertEqual(loaded["receipt"], "CURRENT")
        case.assertEqual(loaded["state"]["stages_done"], ["namespaces"])
        case.assertEqual(stat.S_IMODE(os.stat(env.dir).st_mode), 0o700)
        for name in ("journal.jsonl", "receipt.json", "lock"):
            case.assertEqual(stat.S_IMODE(os.stat(env.dir / name).st_mode), 0o600, name)
        case.assertEqual(len(env.journal_lines()), 1 + 2 * 2 + 1)


def scenario_symlink(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        link = env.root / ("f" * 32)
        os.symlink(env.dir, link)
        case.assertEqual(error_of(lambda: env.load(directory=link), mods.receipt.ReceiptError), "receipt_symlink")
        target = env.tmp / "elsewhere.jsonl"
        shutil.copy(env.dir / "journal.jsonl", target)
        os.chmod(target, 0o600)
        os.unlink(env.dir / "journal.jsonl")
        os.symlink(target, env.dir / "journal.jsonl")
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_symlink")


def scenario_dir_permission(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        os.chmod(env.dir, 0o750)
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_permission")


def scenario_file_permission(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        os.chmod(env.dir / "receipt.json", 0o640)
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_permission")


def scenario_dir_owner(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        real = os.geteuid()
        with mock.patch.object(mods.receipt.os, "geteuid", return_value=real + 4242):
            case.assertEqual(error_of(lambda: mods.receipt.check_dir(env.dir), mods.receipt.ReceiptError),
                             "receipt_owner_mismatch")


def scenario_file_owner(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        info = os.lstat(env.dir / "journal.jsonl")
        with mock.patch.object(mods.receipt.os, "geteuid", return_value=info.st_uid + 4242):
            case.assertEqual(error_of(lambda: mods.receipt.check_file_info(info), mods.receipt.ReceiptError),
                             "receipt_owner_mismatch")


def scenario_repository_location(case, mods):
    with env_for(mods) as env:
        inside = preflight.REPOSITORY / "k8s-receipt-must-not-exist"
        error = error_of(lambda: mods.receipt.Store(inside, env.fp, PROJECT, SHA_A, SHA_B, env.plan),
                         mods.receipt.ReceiptError)
        exists = inside.exists()
        if exists:
            shutil.rmtree(inside, ignore_errors=True)
        case.assertEqual(error, "receipt_inside_repository")
        case.assertFalse(exists)


def scenario_lock(case, mods):
    with env_for(mods) as env:
        first, second = env.store(), env.store()
        with first.lock():
            case.assertEqual(error_of(lambda: second.lock().__enter__(), mods.receipt.ReceiptError), "receipt_locked")
        case.assertEqual(error_of(second.begin, mods.receipt.ReceiptError), "receipt_not_locked")
        case.assertEqual(error_of(lambda: second.stage_done("namespaces"), mods.receipt.ReceiptError),
                         "receipt_not_locked")


def scenario_secret_values(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            before = env.journal_lines()
            secret = {"apiVersion": "v1", "kind": "Secret", "namespace": "istio-system", "name": "cacerts"}
            case.assertEqual(error_of(lambda: store.intent("namespaces", secret, ABSENT, "create"),
                                      mods.receipt.ReceiptError), "secret_identity_refused")
            # Synthetic look-alikes, assembled at run time so no literal key or token is committed.
            for value in ("eyJ" + "hbGciOiJIUzI1NiJ9abcdef", "k8s-aws-v1." + "aHR0cHM6", "AKIA" + "ABCDEFGHIJKLMNOP",
                          "MIIEvQIBADANBgkqhkiG9w0B" + "AQEFAASCBKcwggSjAgEAAoIBAQ"):
                identity = dict(env.members("namespaces")[0], name=value)
                case.assertEqual(error_of(lambda: store.intent("namespaces", identity, ABSENT, "create"),
                                          mods.receipt.ReceiptError), "secret_like_value", value)
            case.assertEqual(env.journal_lines(), before)


def scenario_extra_field(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            for offset, identity in enumerate(env.members("namespaces")):
                seq = store.intent("namespaces", identity, ABSENT, "create")
                store.result(seq, identity, uid(1 + offset), "100", 1, "applied")
            before = env.journal_lines()
            record = {"type": "STAGE_DONE", "stage": "namespaces", "at": "2026-11-22T00:00:00Z",
                      "spec": {"replicas": 1}}
            case.assertEqual(error_of(lambda: store._append(record), mods.receipt.ReceiptError),
                             "record_field_not_allowed")
            case.assertEqual(env.journal_lines(), before)


def scenario_header_pins(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        case.assertEqual(error_of(lambda: env.load(dict(env.expected, manifest_sha256="c" * 64)),
                                  mods.receipt.ReceiptError), "bundle_changed")
        changed = env.store(input_sha256="d" * 64)
        with changed.lock():
            case.assertEqual(error_of(changed.begin, mods.receipt.ReceiptError), "bundle_changed")


def scenario_fingerprint(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        other = mods.receipt.fingerprint(ARN, uid(99))
        case.assertEqual(error_of(lambda: env.load(dict(env.expected, fingerprint=other)), mods.receipt.ReceiptError),
                         "fingerprint_mismatch")
        case.assertEqual(error_of(lambda: env.load(dict(env.expected, project="other")), mods.receipt.ReceiptError),
                         "project_mismatch")


def scenario_directory_name(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        moved = env.root / ("e" * 32)
        os.rename(env.dir, moved)
        case.assertEqual(error_of(lambda: env.load(directory=moved), mods.receipt.ReceiptError),
                         "receipt_directory_mismatch")


def scenario_missing(case, mods):
    with env_for(mods) as env:
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_missing")
        store = env.store()
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_missing")
        with store.lock():
            store.begin()
        os.unlink(env.dir / "receipt.json")
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_snapshot_missing")


def written(env, store):
    with store.lock():
        store.begin()
        env.apply_stage(store, "namespaces")


def scenario_chain(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        lines = env.journal_lines()
        (env.dir / "journal.jsonl").write_bytes(b"".join(lines[:2] + lines[3:]))
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_corrupt:chain")


def scenario_canonical(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        lines = env.journal_lines()
        lines[2] = (json.dumps(json.loads(lines[2]), indent=None) + "\n").encode()
        (env.dir / "journal.jsonl").write_bytes(b"".join(lines))
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_corrupt:not_canonical")


def scenario_tamper_value(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        data = (env.dir / "journal.jsonl").read_bytes().replace(uid(1).encode(), uid(7).encode())
        (env.dir / "journal.jsonl").write_bytes(data)
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_corrupt:chain")
        (env.dir / "journal.jsonl").write_bytes(data[:-1])
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_corrupt:truncated_line")
        (env.dir / "journal.jsonl").write_bytes(b"not json\n")
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_corrupt:not_json")


def scenario_snapshot_mismatch(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        receipt = json.loads((env.dir / "receipt.json").read_text())
        key = sorted(receipt["state"]["objects"])[0]
        receipt["state"]["objects"][key]["owned_uid"] = uid(55)
        (env.dir / "receipt.json").write_text(json.dumps(receipt))
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_journal_mismatch")


def scenario_truncated_journal(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        lines = env.journal_lines()
        (env.dir / "journal.jsonl").write_bytes(b"".join(lines[:-1]))
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_truncated")


def scenario_stale_after_crash(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            identity = env.members("namespaces")[0]
            with mock.patch.object(mods.receipt.Store, "_write_snapshot", side_effect=OSError("crash")):
                case.assertIsNotNone(error_of(lambda: store.intent("namespaces", identity, ABSENT, "create"),
                                              OSError))
        loaded = env.load()
        case.assertEqual(loaded["receipt"], "STALE")
        case.assertIsNotNone(loaded["state"]["open_intent"])
        with store.lock():
            case.assertEqual(store.begin(), "REFRESHED")
        case.assertEqual(env.load()["receipt"], "CURRENT")


def observer(table):
    def observe(identity):
        return table.get(identity["name"], ("absent", None))
    return observe


def present(uid_value, managers=(("acme-k8s-runtime", "Apply"),)):
    return "present", {"uid": uid_value, "managers": [{"manager": m, "operation": o, "subresource": ""}
                                                       for m, o in managers]}


def verdict_of(verdicts, name):
    return next(v["verdict"] for v in verdicts if v["identity"]["name"] == name)


def scenario_intent_crash(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            store.intent("namespaces", first, ABSENT, "create")
        state = env.load()["state"]
        run = lambda table: verdict_of(mods.receipt.reconcile(state, env.plan, observer(table), "acme-k8s-runtime"),
                                       first["name"])
        case.assertEqual(run({}), "NOT_APPLIED")
        case.assertEqual(run({first["name"]: present(uid(9))}), "QUARANTINE_REQUIRED")


def scenario_reapply_owned(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            seq = store.intent("namespaces", first, ABSENT, "create")
            store.result(seq, first, uid(1), "100", 1, "applied")
            store.intent("namespaces", first, {"state": "owned", "uid": uid(1)}, "update")
        state = env.load()["state"]
        run = lambda observed: verdict_of(mods.receipt.reconcile(state, env.plan, observer({first["name"]: observed}),
                                                                 "acme-k8s-runtime"), first["name"])
        case.assertEqual(run(present(uid(1))), "REAPPLY_SAFE")
        case.assertEqual(run(present(uid(1), (("kube-controller-manager", "Update"),))), "NOT_OWNED")
        case.assertEqual(run(present(uid(1), (("acme-k8s-runtime", "Update"),))), "NOT_OWNED")
        case.assertEqual(run(present(uid(1), (("acme-k8s-runtime", "Apply"), ("kube-controller-manager", "Update")))),
                         "OWNERSHIP_NOT_VERIFIED")
        case.assertEqual(run(present(uid(2))), "UID_CHANGED")
        case.assertEqual(run(("absent", None)), "UID_CHANGED")
        case.assertEqual(run(("unknown", "timeout")), "UNKNOWN")


def crash_after_header(env, mods, store):
    """Inject a crash between the fsynced HEADER and the first snapshot."""
    with store.lock():
        with mock.patch.object(mods.receipt.Store, "_write_snapshot", side_effect=OSError("crash")):
            error_of(store.begin, OSError)
    lines = env.journal_lines()
    if len(lines) != 1 or os.path.lexists(env.dir / "receipt.json"):
        raise AssertionError("crash injection did not leave a HEADER-only journal")


def scenario_header_crash_recovery(case, mods):
    with env_for(mods) as env:
        store = env.store()
        crash_after_header(env, mods, store)
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "receipt_snapshot_missing")
        case.assertFalse(os.path.lexists(env.dir / "receipt.json"), "a read must not repair the snapshot")
        with store.lock():
            case.assertEqual(store.begin(), "SNAPSHOT_CREATED")
        case.assertEqual(stat.S_IMODE(os.stat(env.dir / "receipt.json").st_mode), 0o600)
        case.assertFalse(os.path.lexists(env.dir / "receipt.json.tmp"))
        loaded = env.load()
        case.assertEqual((loaded["receipt"], len(loaded["records"])), ("CURRENT", 1))
        with store.lock():
            case.assertEqual(store.begin(), "CURRENT")
        case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_not_locked")


def scenario_header_crash_checks(case, mods):
    with env_for(mods) as env:
        store = env.store()
        crash_after_header(env, mods, store)
        changed = env.store(manifest_sha256="c" * 64)
        with changed.lock():
            case.assertEqual(error_of(changed.begin, mods.receipt.ReceiptError), "bundle_changed")
        other_project = env.store(project="other")
        with other_project.lock():
            case.assertEqual(error_of(other_project.begin, mods.receipt.ReceiptError), "project_mismatch")
        case.assertFalse(os.path.lexists(env.dir / "receipt.json"))
        line = env.journal_lines()[0]
        (env.dir / "journal.jsonl").write_bytes(line.replace(SHA_B.encode(), ("d" * 64).encode()))
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "bundle_changed")
        (env.dir / "journal.jsonl").write_bytes(line.replace(b'"format":1', b'"format": 1'))
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "journal_corrupt:not_canonical")
        case.assertFalse(os.path.lexists(env.dir / "receipt.json"))


def scenario_missing_snapshot_with_operations(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            store.intent("namespaces", first, ABSENT, "create")
        os.unlink(env.dir / "receipt.json")
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_snapshot_missing")
        case.assertFalse(os.path.lexists(env.dir / "receipt.json"))


def scenario_journal_missing(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        snapshot_bytes = (env.dir / "receipt.json").read_bytes()
        os.unlink(env.dir / "journal.jsonl")
        again = env.store()
        with again.lock():
            case.assertEqual(error_of(again.begin, mods.receipt.ReceiptError), "journal_missing")
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "journal_missing")
        case.assertEqual((env.dir / "receipt.json").read_bytes(), snapshot_bytes)
        case.assertFalse(os.path.lexists(env.dir / "journal.jsonl"))
        case.assertEqual(error_of(env.load, mods.receipt.ReceiptError), "journal_missing")


def scenario_existing_directory_not_new(case, mods):
    with env_for(mods) as env:
        first = env.store()
        second = env.store()  # the directory already exists for this Store
        with second.lock():
            case.assertEqual(error_of(second.begin, mods.receipt.ReceiptError), "receipt_directory_not_new")
        case.assertEqual(sorted(os.listdir(env.dir)), ["lock"])
        with first.lock():
            case.assertEqual(first.begin(), "CREATED")
        case.assertEqual(env.load()["receipt"], "CURRENT")


def scenario_same_store_never_reinitialises(case, mods):
    for full in (False, True):
        with env_for(mods) as env:
            store = env.store()
            with store.lock():
                case.assertEqual(store.begin(), "CREATED")
                if full:
                    env.apply_stage(store, "namespaces")
            os.unlink(env.dir / "journal.jsonl")
            os.unlink(env.dir / "receipt.json")
            with store.lock():
                case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_directory_not_new",
                                 "full journal" if full else "header only")
            case.assertFalse(os.path.lexists(env.dir / "journal.jsonl"))
            case.assertFalse(os.path.lexists(env.dir / "receipt.json"))
            other = env.store()
            with other.lock():
                case.assertEqual(error_of(other.begin, mods.receipt.ReceiptError), "receipt_directory_not_new")


def scenario_failed_first_write_consumes_permission(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            with mock.patch.object(mods.receipt.Store, "_append", side_effect=OSError("disk full")):
                case.assertIsNotNone(error_of(store.begin, OSError))
            case.assertFalse(os.path.lexists(env.dir / "journal.jsonl"))
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_directory_not_new")
        case.assertFalse(os.path.lexists(env.dir / "journal.jsonl"))


def scenario_concurrent_mkdir_not_ours(case, mods):
    with env_for(mods) as env:
        os.makedirs(env.root, mode=0o700)
        leaf = str(env.root / env.fp["id"])
        real_mkdir = os.mkdir

        def raced(path, mode=0o777, *args, **kwargs):
            if str(path) == leaf:
                real_mkdir(path, 0o700)  # another process wins the race just before us
                raise FileExistsError(path)
            return real_mkdir(path, mode, *args, **kwargs)
        with mock.patch.object(mods.receipt.os, "mkdir", side_effect=raced):
            store = env.store()
        case.assertFalse(store.created_here)
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_directory_not_new")
        case.assertFalse(os.path.lexists(env.dir / "journal.jsonl"))


def scenario_new_directory_must_be_empty(case, mods):
    with env_for(mods) as env:
        store = env.store()
        stray = env.dir / "stray"
        stray.write_text("unexpected")
        os.chmod(stray, 0o600)
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_directory_not_new")
        case.assertFalse(os.path.lexists(env.dir / "journal.jsonl"))
        case.assertFalse(os.path.lexists(env.dir / "receipt.json"))


def scenario_corrupt_journal_not_reinitialised(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        (env.dir / "journal.jsonl").write_bytes(b"corrupt\n")
        journal_bytes = (env.dir / "journal.jsonl").read_bytes()
        snapshot_bytes = (env.dir / "receipt.json").read_bytes()
        for candidate in (store, env.store()):
            with candidate.lock():
                case.assertEqual(error_of(candidate.begin, mods.receipt.ReceiptError), "journal_corrupt:not_json")
        case.assertEqual((env.dir / "journal.jsonl").read_bytes(), journal_bytes)
        case.assertEqual((env.dir / "receipt.json").read_bytes(), snapshot_bytes)


def scenario_tampered_snapshot_not_regenerated(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
        receipt = json.loads((env.dir / "receipt.json").read_text())
        receipt["journal_last_sha256"] = "e" * 64
        tampered = json.dumps(receipt).encode()
        (env.dir / "receipt.json").write_bytes(tampered)
        with store.lock():
            case.assertEqual(error_of(store.begin, mods.receipt.ReceiptError), "receipt_journal_mismatch")
        case.assertEqual((env.dir / "receipt.json").read_bytes(), tampered)


def scenario_uid_changed(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        state = env.load()["state"]
        first, second = env.members("namespaces")
        verdicts = mods.receipt.reconcile(state, env.plan, observer({first["name"]: present(uid(1)),
                                                                     second["name"]: present(uid(42))}),
                                          "acme-k8s-runtime")
        case.assertEqual(verdict_of(verdicts, first["name"]), "CONSISTENT")
        case.assertEqual(verdict_of(verdicts, second["name"]), "UID_CHANGED")
        verdicts = mods.receipt.reconcile(state, env.plan, observer({first["name"]: present(uid(1))}),
                                          "acme-k8s-runtime")
        case.assertEqual(verdict_of(verdicts, second["name"]), "UID_CHANGED")


def scenario_quarantine(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            store.intent("namespaces", first, ABSENT, "create")
            store.quarantine(first, uid(9), "creation_unproven")
            case.assertEqual(error_of(lambda: store.intent("namespaces", first, ABSENT, "create"),
                                      mods.receipt.ReceiptError), "quarantined")
            case.assertEqual(error_of(lambda: store.release_quarantine(first, uid(9), "owner"),
                                      mods.receipt.ReceiptError), "quarantine_release_not_approved")
            release = {"type": "RELEASE", "identity": first, "at": "2026-11-22T00:00:00Z"}
            case.assertEqual(error_of(lambda: store._append(release), mods.receipt.ReceiptError),
                             "record_type_unknown")
        state = env.load()["state"]
        verdicts = mods.receipt.reconcile(state, env.plan, observer({first["name"]: present(uid(9))}),
                                          "acme-k8s-runtime")
        case.assertEqual(verdict_of(verdicts, first["name"]), "QUARANTINED")


def scenario_adoption(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            before = env.journal_lines()
            first = env.members("namespaces")[0]
            case.assertEqual(error_of(lambda: store.intent("namespaces", first, {"state": "owned", "uid": uid(3)},
                                                           "update"), mods.receipt.ReceiptError), "adoption_refused")
            case.assertEqual(error_of(lambda: store.adopt(first, uid(3)), mods.receipt.ReceiptError),
                             "adoption_refused")
            case.assertEqual(env.journal_lines(), before)
        state = env.load()["state"]
        verdicts = mods.receipt.reconcile(state, env.plan, observer({first["name"]: present(uid(3))}),
                                          "acme-k8s-runtime")
        case.assertEqual(verdict_of(verdicts, first["name"]), "NOT_OWNED")


def scenario_field_managers(case, mods):
    with env_for(mods) as env:
        store = env.store()
        written(env, store)
        state = env.load()["state"]
        first = env.members("namespaces")[0]
        run = lambda observed: verdict_of(mods.receipt.reconcile(state, env.plan, observer({first["name"]: observed}),
                                                                 "acme-k8s-runtime"), first["name"])
        case.assertEqual(run(present(uid(1))), "CONSISTENT")
        case.assertEqual(run(present(uid(1), (("acme-k8s-runtime", "Apply"), ("kube-controller-manager", "Update")))),
                         "OWNERSHIP_NOT_VERIFIED")
        case.assertEqual(run(present(uid(1), (("acme-k8s-runtime", "Update"),))), "NOT_OWNED")
        case.assertEqual(run(("unknown", "timeout")), "UNKNOWN")


def scenario_open_intent_order(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first, second = env.members("namespaces")
            store.intent("namespaces", first, ABSENT, "create")
            case.assertEqual(error_of(lambda: store.intent("namespaces", second, ABSENT, "create"),
                                      mods.receipt.ReceiptError), "journal_inconsistent:open_intent")
            case.assertEqual(error_of(lambda: store.result(1, second, uid(2), "1", 1, "applied"),
                                      mods.receipt.ReceiptError), "journal_inconsistent:result")


def scenario_stage_rules(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            seq = store.intent("namespaces", first, ABSENT, "create")
            store.result(seq, first, uid(1), "1", 1, "applied")
            case.assertEqual(error_of(lambda: store.stage_done("namespaces"), mods.receipt.ReceiptError),
                             "journal_inconsistent:stage_incomplete")
            crd = env.members("base")[0]
            case.assertEqual(error_of(lambda: store.intent("base", crd, ABSENT, "create"), mods.receipt.ReceiptError),
                             "journal_inconsistent:stage_order")
            outsider = dict(first, name="not-in-plan")
            case.assertEqual(error_of(lambda: store.intent("namespaces", outsider, ABSENT, "create"),
                                      mods.receipt.ReceiptError), "identity_not_in_plan")


def scenario_failed_result(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            seq = store.intent("namespaces", first, ABSENT, "create")
            store.result(seq, first, None, None, None, "failed")
            store.intent("namespaces", first, ABSENT, "create")
        state = env.load()["state"]
        case.assertEqual(state["last_seq"], 2)


def scenario_write_validated_first(case, mods):
    with env_for(mods) as env:
        store = env.store()
        with store.lock():
            store.begin()
            first = env.members("namespaces")[0]
            seq = store.intent("namespaces", first, ABSENT, "create")
            before = env.journal_lines()
            case.assertEqual(error_of(lambda: store.result(seq + 5, first, uid(1), "1", 1, "applied"),
                                      mods.receipt.ReceiptError), "journal_inconsistent:result")
            case.assertEqual(env.journal_lines(), before)


# ---- transport scenarios -------------------------------------------------------------------------------------------

DEPLOYMENT = {"apiVersion": "apps/v1", "kind": "Deployment", "namespace": "istio-system", "name": "istiod-acme-v1"}
NAMESPACE = {"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "istio-system"}


def policy(mods, delete=True):
    return mods.transport.Policy([DEPLOYMENT, NAMESPACE], [DEPLOYMENT] if delete else [])


def metadata_body(identity, extra=None, kind="PartialObjectMetadata"):
    document = {"kind": kind, "apiVersion": "meta.k8s.io/v1" if kind == "PartialObjectMetadata" else "apps/v1",
                "metadata": {"name": identity["name"], "uid": uid(5)}}
    if identity["namespace"]:
        document["metadata"]["namespace"] = identity["namespace"]
    document.update(extra or {})
    return json.dumps(document).encode()


def scenario_transport_requests(case, mods):
    t = mods.transport
    request = t.metadata_get_request(policy(mods), DEPLOYMENT)
    case.assertEqual(request["method"], "GET")
    case.assertEqual(request["path"], "/apis/apps/v1/namespaces/istio-system/deployments/istiod-acme-v1")
    case.assertEqual(request["headers"], {"Accept": "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1"})
    case.assertIsNone(request["body"])
    case.assertEqual(t.metadata_get_request(policy(mods), NAMESPACE)["path"], "/api/v1/namespaces/istio-system")
    delete = t.delete_request(policy(mods), DEPLOYMENT, uid(5))
    case.assertEqual(json.loads(delete["body"]), {"apiVersion": "v1", "kind": "DeleteOptions",
                                                  "preconditions": {"uid": uid(5)},
                                                  "propagationPolicy": "Background"})
    other = dict(DEPLOYMENT, name="other")
    case.assertEqual(error_of(lambda: t.metadata_get_request(policy(mods), other), t.TransportError),
                     "identity_not_allowed")
    case.assertEqual(error_of(lambda: t.delete_request(policy(mods, delete=False), DEPLOYMENT, uid(5)),
                              t.TransportError), "delete_not_allowed")
    case.assertEqual(error_of(lambda: t.delete_request(policy(mods), DEPLOYMENT, "not-a-uid"), t.TransportError),
                     "uid_invalid")
    secret = {"apiVersion": "v1", "kind": "Secret", "namespace": "istio-system", "name": "cacerts"}
    case.assertEqual(error_of(lambda: t.object_path(secret), t.TransportError), "secret_path_not_approved")
    case.assertEqual(error_of(lambda: t.Policy([secret]), t.TransportError), "secret_path_not_approved")
    pod = {"apiVersion": "v1", "kind": "Pod", "namespace": "istio-system", "name": "x"}
    case.assertEqual(error_of(lambda: t.object_path(pod), t.TransportError), "kind_not_allowed")
    case.assertEqual(error_of(lambda: t.object_path(dict(NAMESPACE, namespace="x")), t.TransportError),
                     "namespace_scope_mismatch")


def scenario_transport_responses(case, mods):
    t = mods.transport
    case.assertEqual(t.validate_metadata_response(DEPLOYMENT, 200, metadata_body(DEPLOYMENT))["uid"], uid(5))
    case.assertIsNone(t.validate_metadata_response(DEPLOYMENT, 404, b""))
    for status, code in ((403, "forbidden"), (500, "unexpected_status")):
        case.assertEqual(error_of(lambda: t.validate_metadata_response(DEPLOYMENT, status, b"{}"), t.TransportError),
                         code)
    full = metadata_body(DEPLOYMENT, {"spec": {"replicas": 1}})
    case.assertEqual(error_of(lambda: t.validate_metadata_response(DEPLOYMENT, 200, full), t.TransportError),
                     "response_not_metadata_only")
    secret_like = metadata_body(DEPLOYMENT, {"data": {"tls.key": "c2VjcmV0"}})
    case.assertEqual(error_of(lambda: t.validate_metadata_response(DEPLOYMENT, 200, secret_like), t.TransportError),
                     "response_not_metadata_only")
    object_kind = metadata_body(DEPLOYMENT, kind="Deployment")
    case.assertEqual(error_of(lambda: t.validate_metadata_response(DEPLOYMENT, 200, object_kind), t.TransportError),
                     "response_not_partial_object_metadata")
    case.assertEqual(error_of(lambda: t.validate_metadata_response(dict(DEPLOYMENT, name="x"), 200,
                                                                   metadata_body(DEPLOYMENT)), t.TransportError),
                     "response_identity_mismatch")
    huge = b" " * (t.MAX_RESPONSE_BYTES + 1)
    case.assertEqual(error_of(lambda: t.validate_metadata_response(DEPLOYMENT, 200, huge), t.TransportError),
                     "response_too_large")
    case.assertEqual(t.validate_delete_response(200), "deleted")
    case.assertEqual(t.validate_delete_response(404), "absent")
    case.assertEqual(error_of(lambda: t.validate_delete_response(409), t.TransportError), "uid_precondition_failed")


def scenario_transport_refused(case, mods):
    t = mods.transport
    case.assertEqual(error_of(lambda: t.open_transport("https", policy(mods), lambda r: (404, b"")),
                              t.TransportError), "real_transport_not_implemented")
    case.assertEqual(error_of(lambda: t.HttpsTransport(), t.TransportError), "real_transport_not_implemented")
    served = []
    fake = t.open_transport("fake", policy(mods), lambda request: served.append(request) or (200, metadata_body(
        DEPLOYMENT)))
    case.assertEqual(fake.get_metadata(DEPLOYMENT)["uid"], uid(5))
    case.assertEqual(served[0]["headers"]["Accept"], t.METADATA_ACCEPT)


# ---- gate and receipt verify scenarios ------------------------------------------------------------------------------

def run_main(module, argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("subprocess.run", side_effect=AssertionError("no process may start")) as runner, \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main(argv)
        except AssertionError:
            raise
        except BaseException as raised:  # noqa: BLE001 - a mutant may fail in its own way
            code = "raised:" + type(raised).__name__
    return code, runner.call_count, err.getvalue()


def scenario_apply_destroy_refused(case, mods):
    for name in ("apply", "destroy"):
        code, calls, err = run_main(mods.runtime, [name, "--input", "/nonexistent", "--helm", "/nonexistent"])
        case.assertEqual((code, calls), (1, 0), name)
        case.assertIn("operation_not_approved:" + name, err)
    for name in ("apply", "destroy", "recover", "release", "adopt"):
        case.assertEqual(error_of(lambda: mods.runtime.check_operation(name), mods.runtime.GateError),
                         "operation_not_approved:" + name)


class Verify:
    """A built input and fake cluster (from the status tests) plus a receipt written for its plan."""

    def __init__(self, mods):
        import test_k8s_runtime_status as status_tests
        self.status_tests = status_tests
        self.mods = mods
        self.cluster = status_tests.Cluster()
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-verify-"))
        os.chmod(self.tmp, 0o700)
        with self.rendered():
            self.report = k8s_runtime.plan(self.cluster.input, "unused", False)
        self.plan = k8s_runtime_receipt.Plan.from_report(self.report)
        self.fp = k8s_runtime_receipt.fingerprint(
            "arn:aws:eks:ca-central-1:" + self.cluster.document["controller_identity"]["scope"]["account_id"]
            + ":cluster/" + self.cluster.document["controller_identity"]["cluster_name"], KUBE_SYSTEM_UID)
        self.project = self.cluster.project
        manager = self.project + "-k8s-runtime"
        self.cluster.state["objects"]["namespace||kube-system"] = {
            "apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "kube-system", "uid": KUBE_SYSTEM_UID}}
        self.members = [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|")))
                        for k in self.plan.members["namespaces"]]
        for index, identity in enumerate(self.members):
            key = self.status_tests.key_of(identity)
            meta = self.cluster.state["objects"][key]["metadata"]
            meta["uid"] = uid(index + 1)
            meta["managedFields"] = [{"manager": manager, "operation": "Apply", "fieldsType": "FieldsV1"}]
        self.cluster.save()

    @contextlib.contextmanager
    def rendered(self):
        real = self.status_tests.Cluster.bundle
        with mock.patch.object(self.status_tests.render, "render", side_effect=lambda d, h, f: real(d)):
            yield

    def write(self, stages=("namespaces",), fp=None, manifest=None):
        store = k8s_runtime_receipt.Store(self.tmp / "state", fp or self.fp, self.project,
                                          manifest or self.report["manifest_sha256"], self.report["input_sha256"],
                                          self.plan)
        with store.lock():
            store.begin()
            for stage in stages:
                for index, identity in enumerate(self.members):
                    seq = store.intent(stage, identity, ABSENT, "create")
                    store.result(seq, identity, uid(index + 1), "100", 1, "applied")
                store.stage_done(stage)
        return store.dir

    def verify(self, directory, cluster=False, env=None, manifest=None, input_sha=None, runtime=None):
        lines = []
        module = runtime or self.mods.runtime
        with self.rendered():
            try:
                code, report = module.receipt_verify(
                    self.cluster.input, "unused", directory, manifest or self.report["manifest_sha256"],
                    input_sha or self.report["input_sha256"], cluster, None, str(self.cluster.kubectl),
                    str(self.cluster.base.terraform), self.cluster.base.services,
                    env if env is not None else self.cluster.env(), 20, lines.append)
                return code, report, None
            except Exception as raised:  # noqa: BLE001 - mutants raise their own exception classes
                return 2, None, str(raised)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.cluster.cleanup()


@contextlib.contextmanager
def verify_for(mods):
    verify = Verify(mods)
    try:
        yield verify
    finally:
        verify.cleanup()


def scenario_verify_offline(case, mods):
    with verify_for(mods) as v:
        directory = v.write()
        code, report, error = v.verify(directory)
        case.assertEqual((code, error), (0, None))
        case.assertEqual((report["receipt"], report["stages_done"], report["changes_made"]),
                         ("CURRENT", ["namespaces"], False))
        case.assertEqual(v.cluster.calls(), [])


def scenario_verify_pins(case, mods):
    with verify_for(mods) as v:
        directory = v.write()
        case.assertEqual(v.verify(directory, manifest="f" * 64)[2], "sha_mismatch")
        case.assertEqual(v.verify(directory, manifest="abc")[2], "sha_pin_invalid")


def scenario_verify_bundle_changed(case, mods):
    with verify_for(mods) as v:
        directory = v.write(manifest="c" * 64)
        case.assertEqual(v.verify(directory)[2], "bundle_changed")


def scenario_verify_open_intent(case, mods):
    with verify_for(mods) as v:
        store = k8s_runtime_receipt.Store(v.tmp / "state", v.fp, v.project, v.report["manifest_sha256"],
                                          v.report["input_sha256"], v.plan)
        with store.lock():
            store.begin()
            store.intent("namespaces", v.members[0], ABSENT, "create")
        code, report, error = v.verify(store.dir)
        case.assertEqual((code, error, report["open_intent"], report["status"]),
                         (3, None, True, "attention_required"))


def scenario_verify_does_not_repair(case, mods):
    with verify_for(mods) as v:
        store = k8s_runtime_receipt.Store(v.tmp / "state", v.fp, v.project, v.report["manifest_sha256"],
                                          v.report["input_sha256"], v.plan)
        with store.lock():
            with mock.patch.object(k8s_runtime_receipt.Store, "_write_snapshot", side_effect=OSError("crash")):
                error_of(store.begin, OSError)
        case.assertEqual(v.verify(store.dir)[2], "receipt_snapshot_missing")
        case.assertFalse(os.path.lexists(store.dir / "receipt.json"))


def scenario_verify_cluster(case, mods):
    with verify_for(mods) as v:
        directory = v.write()
        code, report, error = v.verify(directory, cluster=True)
        case.assertEqual(error, None)
        case.assertEqual(code, 3)
        case.assertEqual(report["fingerprint_id"], v.fp["id"])
        verdicts = {row["identity"]["name"]: row["verdict"] for row in report["verdicts"]}
        for identity in v.members:
            case.assertEqual(verdicts[identity["name"]], "CONSISTENT")
        case.assertEqual(report["verdict_counts"]["NOT_OWNED"], 59)
        case.assertEqual(report["verdict_counts"]["ABSENT"], 1)
        gets = v.cluster.gets()
        allowed = {v.status_tests.key_of(dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|"))))
                   for k in v.plan.stage_of} | {"namespace||kube-system"}
        for call in gets:
            rest = call[3:]
            namespace = rest[4] if rest[3:4] == ["-n"] else ""
            case.assertIn(rest[1] + "|" + namespace + "|" + rest[2], allowed)
        case.assertEqual(sum(1 for c in gets if c[4:6] == ["namespace", "kube-system"]), 1)
        case.assertFalse(any(c[3] in ("apply", "delete", "patch", "create") for c in v.cluster.calls()))


def scenario_verify_cluster_uid_changed(case, mods):
    with verify_for(mods) as v:
        directory = v.write()
        key = v.status_tests.key_of(v.members[1])
        v.cluster.edit(lambda s: s["objects"][key]["metadata"].update(uid=uid(77)))
        code, report, error = v.verify(directory, cluster=True)
        verdicts = {row["identity"]["name"]: row["verdict"] for row in report["verdicts"]}
        case.assertEqual((code, verdicts[v.members[1]["name"]]), (3, "UID_CHANGED"))


def scenario_verify_fingerprint_mismatch(case, mods):
    with verify_for(mods) as v:
        other = k8s_runtime_receipt.fingerprint(v.fp["cluster_arn"], uid(88))
        directory = v.write(fp=other)
        case.assertEqual(v.verify(directory, cluster=True)[2], "fingerprint_mismatch")
        v.cluster.edit(lambda s: s["objects"]["namespace||kube-system"]["metadata"].update(uid=uid(88)))
        code, report, error = v.verify(directory, cluster=True)
        case.assertEqual((code, error, report["fingerprint_id"]), (3, None, other["id"]))
        moved = directory.parent / v.fp["id"]
        os.rename(directory, moved)
        case.assertEqual(v.verify(moved, cluster=True)[2], "receipt_directory_mismatch")


def scenario_verify_fingerprint_name(case, mods):
    with verify_for(mods) as v:
        directory = v.write()
        v.cluster.edit(lambda s: s["objects"]["namespace||kube-system"]["metadata"].update(name="default"))
        case.assertEqual(v.verify(directory, cluster=True)[2], "fingerprint_unreadable")


def scenario_verify_cluster_refused(case, mods):
    with verify_for(mods) as v:
        directory = v.write()
        code, report, error = v.verify(directory, cluster=True, env=v.cluster.env(CI="true"))
        case.assertEqual((code, report, error), (1, None, None))
        case.assertEqual(v.cluster.calls(), [])


def scenario_fingerprint_scope(case, mods):
    runtime = mods.runtime
    args = ["get", "namespace", "kube-system", "--ignore-not-found", "-o", "json"]
    status_targets = {("namespace", "", "istio-system")}
    case.assertEqual(error_of(lambda: runtime.check_kubectl_command(args, status_targets), runtime.StatusError),
                     "kubectl_object_not_in_inventory")
    case.assertIsNone(error_of(lambda: runtime.check_kubectl_command(args, {runtime.FINGERPRINT_TARGET}),
                               runtime.StatusError))
    other = ["get", "namespace", "default", "--ignore-not-found", "-o", "json"]
    case.assertEqual(error_of(lambda: runtime.check_kubectl_command(other, {runtime.FINGERPRINT_TARGET}),
                              runtime.StatusError), "kubectl_object_not_in_inventory")


def scenario_no_network_code(case, mods):
    forbidden = {"socket", "ssl", "http", "urllib", "requests", "httpx", "urllib3", "kubernetes"}
    for name in ("k8s_runtime_transport.py", "k8s_runtime_receipt.py"):
        tree = ast.parse((HERE / name).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        case.assertEqual(imported & forbidden, set(), name)


# ---- unit tests ---------------------------------------------------------------------------------------------------

class ReceiptTests(unittest.TestCase):
    def test_roundtrip_modes_and_chain(self):
        scenario_roundtrip(self, real_mods())

    def test_symlinks_refused(self):
        scenario_symlink(self, real_mods())

    def test_permissions_refused(self):
        scenario_dir_permission(self, real_mods())
        scenario_file_permission(self, real_mods())

    def test_owner_mismatch_refused(self):
        scenario_dir_owner(self, real_mods())
        scenario_file_owner(self, real_mods())

    def test_repository_location_refused(self):
        scenario_repository_location(self, real_mods())

    def test_lock_exclusive_and_required(self):
        scenario_lock(self, real_mods())

    def test_secret_and_token_values_refused(self):
        scenario_secret_values(self, real_mods())
        scenario_extra_field(self, real_mods())

    def test_bundle_pins_d10(self):
        scenario_header_pins(self, real_mods())

    def test_fingerprint_d17(self):
        scenario_fingerprint(self, real_mods())
        scenario_directory_name(self, real_mods())

    def test_receipt_missing(self):
        scenario_missing(self, real_mods())

    def test_journal_tamper_and_corruption(self):
        scenario_chain(self, real_mods())
        scenario_canonical(self, real_mods())
        scenario_tamper_value(self, real_mods())

    def test_receipt_journal_mismatch(self):
        scenario_snapshot_mismatch(self, real_mods())
        scenario_truncated_journal(self, real_mods())

    def test_stale_receipt_after_crash(self):
        scenario_stale_after_crash(self, real_mods())

    def test_crash_between_intent_and_result(self):
        scenario_intent_crash(self, real_mods())

    def test_reapply_safe_requires_uid_and_ownership(self):
        scenario_reapply_owned(self, real_mods())

    def test_crash_after_header_recovers_snapshot(self):
        scenario_header_crash_recovery(self, real_mods())
        scenario_header_crash_checks(self, real_mods())

    def test_journal_missing_never_reinitialised(self):
        scenario_journal_missing(self, real_mods())

    def test_only_a_new_empty_directory_is_initialised(self):
        scenario_existing_directory_not_new(self, real_mods())
        scenario_new_directory_must_be_empty(self, real_mods())

    def test_same_store_initialises_at_most_once(self):
        scenario_same_store_never_reinitialises(self, real_mods())

    def test_failed_first_write_consumes_permission(self):
        scenario_failed_first_write_consumes_permission(self, real_mods())

    def test_concurrently_created_directory_is_not_ours(self):
        scenario_concurrent_mkdir_not_ours(self, real_mods())

    def test_corrupt_journal_not_reinitialised(self):
        scenario_corrupt_journal_not_reinitialised(self, real_mods())

    def test_missing_or_tampered_snapshot_not_regenerated(self):
        scenario_missing_snapshot_with_operations(self, real_mods())
        scenario_tampered_snapshot_not_regenerated(self, real_mods())

    def test_uid_change_detected(self):
        scenario_uid_changed(self, real_mods())

    def test_quarantine_recorded_never_released(self):
        scenario_quarantine(self, real_mods())

    def test_adoption_refused(self):
        scenario_adoption(self, real_mods())

    def test_ownership_needs_runtime_apply_entry_only(self):
        scenario_field_managers(self, real_mods())

    def test_journal_ordering(self):
        scenario_open_intent_order(self, real_mods())
        scenario_stage_rules(self, real_mods())
        scenario_failed_result(self, real_mods())
        scenario_write_validated_first(self, real_mods())


class TransportTests(unittest.TestCase):
    def test_requests_only_for_allowlisted_identities(self):
        scenario_transport_requests(self, real_mods())

    def test_responses_validated(self):
        scenario_transport_responses(self, real_mods())

    def test_real_transport_refused(self):
        scenario_transport_refused(self, real_mods())
        scenario_no_network_code(self, real_mods())


class GateAndVerifyTests(unittest.TestCase):
    def test_apply_and_destroy_refused(self):
        scenario_apply_destroy_refused(self, real_mods())

    def test_fingerprint_read_scope(self):
        scenario_fingerprint_scope(self, real_mods())

    def test_verify_offline(self):
        scenario_verify_offline(self, real_mods())
        scenario_verify_open_intent(self, real_mods())
        scenario_verify_does_not_repair(self, real_mods())

    def test_verify_pins_and_bundle(self):
        scenario_verify_pins(self, real_mods())
        scenario_verify_bundle_changed(self, real_mods())

    def test_verify_cluster(self):
        scenario_verify_cluster(self, real_mods())
        scenario_verify_cluster_uid_changed(self, real_mods())

    def test_verify_cluster_fingerprint(self):
        scenario_verify_fingerprint_mismatch(self, real_mods())
        scenario_verify_fingerprint_name(self, real_mods())

    def test_verify_cluster_refused_in_automation(self):
        scenario_verify_cluster_refused(self, real_mods())


# ---- mutations ----------------------------------------------------------------------------------------------------

R, T, K = "k8s_runtime_receipt.py", "k8s_runtime_transport.py", "k8s_runtime.py"
RUNTIME_MUTATIONS = [
    ("dir_symlink", R, '    need(not stat.S_ISLNK(info.st_mode), "receipt_symlink")\n    need(stat.S_ISDIR',
     "    need(stat.S_ISDIR", scenario_symlink),
    ("dir_permission", R, 'need(stat.S_IMODE(info.st_mode) & 0o077 == 0, "receipt_permission")', "pass",
     scenario_dir_permission),
    ("dir_owner", R, '    need(info.st_uid == os.geteuid(), "receipt_owner_mismatch")\n    need(stat.S_IMODE(info.st_mode) & 0o077',
     "    need(stat.S_IMODE(info.st_mode) & 0o077", scenario_dir_owner),
    ("file_permission", R, 'need(stat.S_IMODE(info.st_mode) & 0o177 == 0, "receipt_permission")', "pass",
     scenario_file_permission),
    ("file_owner", R, '    need(info.st_uid == os.geteuid(), "receipt_owner_mismatch")\n    need(stat.S_IMODE(info.st_mode) & 0o177',
     "    need(stat.S_IMODE(info.st_mode) & 0o177", scenario_file_owner),
    ("repository_location", R, 'need(not inside_repository(root), "receipt_inside_repository")', "pass",
     scenario_repository_location),
    ("lock_shared", R, "fcntl.LOCK_EX | fcntl.LOCK_NB", "fcntl.LOCK_SH | fcntl.LOCK_NB", scenario_lock),
    ("lock_not_required", R, '        need(self.lock_fd is not None, "receipt_not_locked")\n        records, digests = self._records()\n        record = dict(',
     "        records, digests = self._records()\n        record = dict(", scenario_lock),
    ("secret_scan", R, 'need(len(value) <= 512 and not SECRET_LIKE.search(value), "secret_like_value")', "pass",
     scenario_secret_values),
    ("secret_identity", R, 'need(identity["kind"] != "Secret", "secret_identity_refused")', "pass",
     scenario_secret_values),
    ("field_allowlist", R, 'need(set(record) == RECORD_FIELDS[record["type"]], "record_field_not_allowed")', "pass",
     scenario_extra_field),
    ("chain", R, 'need(isinstance(record, dict) and record.get("prev") == previous, "journal_corrupt:chain")',
     'need(isinstance(record, dict), "journal_corrupt:chain")', scenario_chain),
    ("canonical", R, 'need(canonical(record).encode() == line, "journal_corrupt:not_canonical")', "pass",
     scenario_canonical),
    ("snapshot_compare", R, 'need(receipt == json.loads(canonical(expected_snapshot)), "receipt_journal_mismatch")',
     "pass", scenario_snapshot_mismatch),
    ("truncation", R, 'need(count <= len(records), "journal_truncated")', "pass", scenario_truncated_journal),
    ("stale", R, '"CURRENT" if count == len(records) else "STALE"', '"CURRENT"', scenario_stale_after_crash),
    ("bundle_pins", R, '    need(header["manifest_sha256"] == expected["manifest_sha256"]\n         and header["input_sha256"] == expected["input_sha256"], "bundle_changed")',
     "    pass", scenario_header_pins),
    ("fingerprint_header", R, '== (fp["cluster_arn"], fp["kube_system_uid"], fp["id"]), "fingerprint_mismatch")',
     '== (header["cluster_arn"], header["kube_system_uid"], header["fingerprint_id"]), "fingerprint_mismatch")',
     scenario_fingerprint),
    ("directory_name", R, 'need(directory.name == state["header"]["fingerprint_id"], "receipt_directory_mismatch")',
     "pass", scenario_directory_name),
    ("adoption", R, 'need(obj["owned_uid"] == record["prior"]["uid"], "adoption_refused")', "pass",
     scenario_adoption),
    ("quarantine_block", R, 'need(key not in state["quarantined"], "quarantined")', "pass", scenario_quarantine),
    ("open_intent", R, '            need(state["open_intent"] is None, "journal_inconsistent:open_intent")\n            need(record["seq"]',
     '            need(record["seq"]', scenario_open_intent_order),
    ("stage_incomplete", R, '"journal_inconsistent:stage_incomplete")', '"journal_inconsistent:stage_incomplete") if False else None',
     scenario_stage_rules),
    ("write_validated", R, "state = derive(records + [record], self.plan)", "state = derive(records or [record], self.plan)",
     scenario_write_validated_first),
    ("reconcile_unproven", R, 'verdict = "NOT_APPLIED" if presence == "absent" else "QUARANTINE_REQUIRED"\n                elif presence',
     'verdict = "NOT_APPLIED" if presence == "absent" else "REAPPLY_SAFE"\n                elif presence', scenario_intent_crash),
    ("reconcile_uid", R, 'elif presence == "absent" or observed["uid"] != obj["owned_uid"]:', 'elif presence == "absent":',
     scenario_uid_changed),
    ("reconcile_unrecorded", R, 'verdict = "ABSENT" if presence == "absent" else "NOT_OWNED"',
     'verdict = "ABSENT" if presence == "absent" else "CONSISTENT"', scenario_adoption),
    ("ownership_others", R, 'return "OWNED" if len(runtime) == len(managers) else "OWNERSHIP_NOT_VERIFIED"',
     'return "OWNED"', scenario_field_managers),
    ("ownership_operation", R, ' and m.get("operation") == "Apply"', "", scenario_field_managers),
    ("header_only_repair", R, '            need(len(records) == 1, "receipt_snapshot_missing")', "            pass",
     scenario_missing_snapshot_with_operations),
    ("repair_header_check", R, "            check_header(replayed[\"header\"], self.expected)  # fingerprint and pins before any repair",
     "            pass", scenario_header_crash_checks),
    ("repair_only_when_missing", R, "        if records and not os.path.lexists(self.dir / RECEIPT):",
     "        if records:", scenario_tampered_snapshot_not_regenerated),
    ("journal_missing", R, '            need(not os.path.lexists(self.dir / RECEIPT), "journal_missing")  # never overwrite evidence',
     "            pass", scenario_journal_missing),
    ("directory_not_new", R, '            need(self._init_allowed, "receipt_directory_not_new")', "            pass",
     scenario_existing_directory_not_new),
    ("init_consumed", R, "            self._init_allowed = False  # consumed before the first write: a failed write never re-grants it",
     "            pass", scenario_same_store_never_reinitialises),
    ("atomic_mkdir", R, "        except FileExistsError:\n            created = False",
     "        except FileExistsError:\n            created = True", scenario_concurrent_mkdir_not_ours),
    ("directory_not_empty", R, '            need(set(os.listdir(self.dir)) <= {LOCK}, "receipt_directory_not_new")',
     "            pass", scenario_new_directory_must_be_empty),
    ("load_journal_missing", R, 'raise ReceiptError("journal_missing" if os.path.lexists(directory / RECEIPT) else "receipt_missing")',
     'raise ReceiptError("receipt_missing")', scenario_journal_missing),
    ("reapply_ownership", R, 'verdict = "REAPPLY_SAFE" if owned_prior == "OWNED" else owned_prior', 'verdict = "REAPPLY_SAFE"',
     scenario_reapply_owned),
    ("release", R, '        raise ReceiptError("quarantine_release_not_approved")', "        return None",
     scenario_quarantine),
    ("accept_header", T, '"headers": {"Accept": METADATA_ACCEPT}', '"headers": {"Accept": "application/json"}',
     scenario_transport_requests),
    ("uid_precondition", T, '"preconditions": {"uid": uid},', "", scenario_transport_requests),
    ("read_policy", T, 'need(identity_key(identity) in policy.read, "identity_not_allowed")', "pass",
     scenario_transport_requests),
    ("delete_policy", T, 'need(identity_key(identity) in policy.delete, "delete_not_allowed")', "pass",
     scenario_transport_requests),
    ("metadata_only", T, 'need(not (FORBIDDEN_RESPONSE_KEYS & set(document)), "response_not_metadata_only")', "pass",
     scenario_transport_responses),
    ("partial_kind", T, '    need(document.get("kind") == "PartialObjectMetadata" and document.get("apiVersion") == "meta.k8s.io/v1",\n         "response_not_partial_object_metadata")',
     "    pass", scenario_transport_responses),
    ("precondition_conflict", T, 'need(status != 409, "uid_precondition_failed")', "pass",
     scenario_transport_responses),
    ("real_transport", T, 'need(kind in APPROVED_TRANSPORTS, "real_transport_not_implemented")', "pass",
     scenario_transport_refused),
    ("secret_path", T, 'need(identity_key(identity) in secrets, "secret_path_not_approved")', "pass",
     scenario_transport_requests),
    ("operation_gate", K, "    if operation not in APPROVED_OPERATIONS:", "    if False:",
     scenario_apply_destroy_refused),
    ("apply_intercept", K, '    if argv[:1] in (["apply"], ["destroy"]):', "    if False:",
     scenario_apply_destroy_refused),
    ("pins_equal", K, '    if (bundle["manifest_sha256"], bundle["input_sha256"]) != (expect_manifest, expect_input):',
     "    if False:", scenario_verify_pins),
    ("pins_format", K, "    if not (isinstance(expect_manifest, str) and SHA256.fullmatch(expect_manifest)",
     "    if False and (isinstance(expect_manifest, str) and SHA256.fullmatch(expect_manifest)",
     scenario_verify_pins),
    ("fingerprint_name", K, '        need(metadata["name"] == "kube-system", "fingerprint_unreadable")', "        pass",
     scenario_verify_fingerprint_name),
    ("verify_automation", K, '        if refusal:\n            out_fn("Refused (" + refusal + "): receipt verify',
     '        if False:\n            out_fn("Refused (" + refusal + "): receipt verify', scenario_verify_cluster_refused),
    ("verify_fingerprint", K, "    loaded = receipt.load(receipt_dir, stages, expected)",
     '    loaded = receipt.load(receipt_dir, stages, dict(expected, fingerprint=None))',
     scenario_verify_fingerprint_mismatch),
    ("verify_attention", K, 'attention = attention or any(v["verdict"] not in receipt.SETTLED_VERDICTS for v in verdicts)',
     "attention = attention", scenario_verify_cluster),
    ("verify_open_intent", K, 'attention = loaded["receipt"] != "CURRENT" or state["open_intent"] is not None or bool(state["quarantined"])',
     "attention = False", scenario_verify_open_intent),
]
# Every guard mutation of this suite: the runtime ones above, the G9/D19 ones (SecretMutationTests) and the
# 6c-B4a destroy foundation ones (DestroyMutationTests).
MUTATIONS = RUNTIME_MUTATIONS + SECRET_MUTATIONS + DESTROY_MUTATIONS


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


class MutationTests(unittest.TestCase):
    def test_each_guard_mutation_is_detected(self):
        self.assertEqual(len(RUNTIME_MUTATIONS), 58)
        undetected = []
        for name, filename, old, new, scenario in RUNTIME_MUTATIONS:
            mods = real_mods()
            setattr(mods, {R: "receipt", T: "transport", K: "runtime"}[filename], mutant(filename, old, new))
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, mods)
            except AssertionError:
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
