#!/usr/bin/env python3
"""Registration UID receipt and safe Secret cleanup for k8s_certs.py (Step 1 item 6c, G9; D19 Fake-only).

Source/Offline code only (Owner decision D19/G9, 2026-11-24). Every request goes
through ``k8s_runtime_transport``, where only the offline fake can be opened; a real
transport is refused (``real_transport_not_implemented``). Nothing here starts a
process, opens a socket, reads a token or a kubeconfig, or calls kubectl.

Scope: the four Secrets of ``k8s_certs.secret_layout`` (``secret_identities``),
nothing else. The transport policy built here names exactly those four and the
``kube-system`` namespace read of the cluster fingerprint (D17).

Registration UID receipt (``register_with_receipt``)
  Called with the registration's apply step (``apply_fn``). After the apply it reads
  each Secret's metadata (PartialObjectMetadata, never the full object) and records
  the UID only when the apply confirmed that Secret and the metadata shows the
  ``k8s_certs.py`` labels and a single ``<project>-k8s-certs`` Apply entry that owns
  exactly the registered fields. Otherwise the entry is NOT_VERIFIED with no UID, and
  the receipt result is INCOMPLETE, never success. A receipt is never rebuilt from
  names or current UIDs alone: an existing receipt is replaced only when every UID it
  holds is unchanged or was cleaned up. The real ``k8s_certs.py register`` is
  unchanged and writes no receipt (no real transport exists).

Receipt store
  ``<root>/<fingerprint id>/registration.json``, default root
  ``~/.local/state/<project>-k8s-certs``, outside the repository, separate from the
  runtime receipt (whose Secret refusal is unchanged). Directory 0700, file 0600,
  owned by the current user; symlinks, other owners and group/other permissions are
  refused (the ``k8s_runtime_receipt`` file checks). Writers hold an exclusive lock;
  every write is validated first, then replaced atomically (temporary file, fsync,
  rename, directory fsync). A missing, corrupt, non-canonical, oversized or
  schema-invalid receipt, another project, another fingerprint or another identity
  list is refused. The receipt holds only the schema, project, fingerprint (cluster
  ARN, ``kube-system`` UID, id), the four identities, UIDs, fixed result codes and
  timestamps: no Secret value, key, token, kubeconfig, object body or annotation.

Cleanup (``cleanup``), per Secret, in this order
  1. receipt integrity, project, fingerprint and identity (before any Secret request);
  2. metadata-only GET;
  3. label ``app.kubernetes.io/managed-by: k8s_certs.py``;
  4. label ``app.kubernetes.io/part-of: <project>``;
  5. the ``<project>-k8s-certs`` Apply entry;
  6. no other manager, operation or field ownership;
  7. live UID equal to the receipt UID;
  8. DELETE with ``preconditions.uid`` (DELETE_REQUESTED is recorded first);
  9. metadata GET confirming NotFound;
  10. the result recorded in the receipt.
  A 200 or 202 alone is never success. A 409, 403, timeout, unexpected response,
  a Secret still present or recreated, or any failed check is BLOCKED and the Secret
  stays in place; there is no retry, no full Secret read, no name-only delete and no
  namespace fallback. A Secret already absent before the delete is recorded
  ALREADY_ABSENT, apart from DELETED.

D18 (recorded, not implemented): the report marks a namespace's Secret condition
BLOCKED while any of its Secrets is not cleaned up. ``kube-system`` is never
deleted; its webhook TLS Secret is its own completion condition. Namespace deletion
is not implemented here (6c-B4) and also needs the section 5.1 inventory (D3).
"""
import contextlib
import fcntl
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_certs  # noqa: E402
import k8s_runtime_receipt as safety  # noqa: E402
import k8s_runtime_transport as transport  # noqa: E402

SCHEMA = "k8s-certs-registration-receipt-v1"
RECEIPT = "registration.json"
LOCK = "lock"
MAX_RECEIPT_BYTES = 64 * 1024
MANAGED_BY_LABEL, MANAGED_BY = "app.kubernetes.io/managed-by", "k8s_certs.py"
PART_OF_LABEL = "app.kubernetes.io/part-of"
KUBE_SYSTEM = {"apiVersion": "v1", "kind": "Namespace", "namespace": "", "name": "kube-system"}
TOP_FIELDS = {"schema", "project", "cluster", "registered_at", "result", "secrets"}
CLUSTER_FIELDS = {"cluster_arn", "kube_system_uid", "fingerprint_id"}
ENTRY_FIELDS = {"identity", "uid", "registration", "reason", "cleanup"}
CLEANUP_FIELDS = {"state", "reason", "at"}
MANAGER_FIELDS = {"manager", "operation", "apiVersion", "time", "fieldsType", "fieldsV1"}
CLEANUP_STATES = {"DELETE_REQUESTED", "DELETED", "ALREADY_ABSENT", "BLOCKED"}
CLEANED = {"DELETED", "ALREADY_ABSENT"}
# Codes the transport raises; any other failure of a request is UNKNOWN (transport_unknown).
TRANSPORT_REASONS = {"forbidden", "unexpected_status", "uid_precondition_failed", "response_too_large",
                     "response_not_json", "response_shape", "response_not_metadata_only",
                     "response_not_partial_object_metadata", "response_identity_mismatch", "response_uid_invalid",
                     "response_secret_annotation_refused"}
REASONS = TRANSPORT_REASONS | {
    "transport_timeout", "transport_unknown", "apply_not_confirmed", "absent_after_apply", "label_managed_by",
    "label_project", "apply_entry_missing", "manager_operation", "foreign_manager", "managed_fields_malformed",
    "field_ownership", "uid_mismatch", "receipt_uid_unavailable", "recreated_after_cleanup", "deleted_concurrently",
    "still_present_after_delete", "recreated_after_delete"}


class CleanupError(Exception):
    """The receipt or the request cannot be trusted; the message is a fixed code."""


def need(condition, code):
    if not condition:
        raise CleanupError(code)


@contextlib.contextmanager
def refusals():
    """Fixed codes of the reused store checks and the transport, as CleanupError."""
    try:
        yield
    except (safety.ReceiptError, transport.TransportError) as error:
        raise CleanupError(str(error)) from None


def check_project(project):
    try:
        return k8s_certs.check_project(project)
    except k8s_certs.CertError:
        raise CleanupError("project_name") from None


def secret_identities(project):
    """The transport allowlist, which must be exactly the k8s_certs.py layout."""
    with refusals():
        identities = transport.secret_identities(project)
    layout = [{"apiVersion": s["apiVersion"], "kind": s["kind"], "namespace": s["metadata"]["namespace"],
               "name": s["metadata"]["name"]} for s in k8s_certs.secret_layout(project, None)]
    need(identities == layout, "secret_allowlist_mismatch")
    return identities


def open_client(project, transport_kind, server, delete):
    identities = secret_identities(project)
    with refusals():
        policy = transport.Policy([KUBE_SYSTEM] + identities, identities if delete else (), secret_project=project)
        return transport.open_transport(transport_kind, policy, server)


def attempt(call):
    """(value, None) or (None, reason): no response body or exception text is ever kept."""
    try:
        return call(), None
    except transport.TransportError as error:
        return None, str(error) if str(error) in TRANSPORT_REASONS else "transport_unknown"
    except TimeoutError:
        return None, "transport_timeout"
    except Exception:  # noqa: BLE001 - any other failure is UNKNOWN, never success
        return None, "transport_unknown"


def observe_fingerprint(client, cluster_arn):
    """D17 from the same transport: the cluster ARN plus the kube-system namespace UID."""
    metadata, reason = attempt(lambda: client.get_metadata(KUBE_SYSTEM))
    uid = metadata.get("uid") if isinstance(metadata, dict) else None
    need(reason is None and uid is not None, "fingerprint_unreadable")
    with refusals():
        return safety.fingerprint(cluster_arn, uid)


# ---- ownership ----------------------------------------------------------------------------------------------------

def field_leaves(fields, prefix=()):
    """The leaf paths of a FieldsV1 tree, or None when it is not the plain f: form a Secret has."""
    if not isinstance(fields, dict) or fields.get(".", {}) != {}:
        return None
    children = {key: value for key, value in fields.items() if key != "."}
    if not children:
        return {prefix} if prefix else None
    leaves = set()
    for key, value in children.items():
        if not (isinstance(key, str) and key.startswith("f:") and len(key) > 2):
            return None
        below = field_leaves(value, prefix + (key,))
        if below is None:
            return None
        leaves |= below
    return leaves


def expected_leaves(project, identity):
    secret = next(s for s in k8s_certs.secret_layout(project, None)
                  if (s["metadata"]["namespace"], s["metadata"]["name"]) == (identity["namespace"], identity["name"]))
    leaves = {("f:metadata", "f:labels", "f:" + label) for label in secret["metadata"]["labels"]}
    return leaves | {("f:type",)} | {("f:data", "f:" + key) for key in secret["data"]}


def ownership_problem(project, identity, metadata):
    """None when the metadata proves the k8s_certs.py registration; otherwise the first failed check."""
    labels = metadata.get("labels")
    if not isinstance(labels, dict) or labels.get(MANAGED_BY_LABEL) != MANAGED_BY:
        return "label_managed_by"
    if labels.get(PART_OF_LABEL) != project:
        return "label_project"
    managers = metadata.get("managedFields")
    entries = managers if isinstance(managers, list) else []
    if entries is not managers or not all(isinstance(m, dict) for m in entries):
        return "managed_fields_malformed"
    named = [m for m in entries if isinstance(m, dict) and m.get("manager") == project + "-k8s-certs"]
    if not named:
        return "apply_entry_missing"
    if any(m.get("operation") != "Apply" for m in named):
        return "manager_operation"
    if len(named) != len(entries):
        return "foreign_manager"
    if len(named) != 1:
        return "managed_fields_malformed"
    entry = named[0]
    if set(entry) - MANAGER_FIELDS or entry.get("apiVersion") != "v1" or entry.get("fieldsType") != "FieldsV1":
        return "managed_fields_malformed"
    if field_leaves(entry.get("fieldsV1")) != expected_leaves(project, identity):
        return "field_ownership"
    return None


# ---- receipt store ------------------------------------------------------------------------------------------------

def default_root(project):
    return Path.home() / ".local" / "state" / (project + "-k8s-certs")


def receipt_directory(root, fp, create):
    root = Path(root).expanduser()
    need(not safety.inside_repository(root), "receipt_inside_repository")
    directory = root / fp["id"]
    with refusals():
        if create:
            safety.make_dir(root)
            if not os.path.lexists(directory):
                os.mkdir(directory, 0o700)
        else:
            safety.check_dir(root)
        safety.check_dir(directory)
    return directory


@contextlib.contextmanager
def locked(directory):
    with refusals():
        fd = safety.open_checked(directory / LOCK, os.O_RDWR | os.O_CREAT)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CleanupError("receipt_locked") from None
        yield
    finally:
        os.close(fd)


def scan(value):
    """Only short printable strings without key, token or blob shapes; nothing else but None and lists or dicts."""
    if isinstance(value, dict):
        for item in value.values():
            scan(item)
    elif isinstance(value, list):
        for item in value:
            scan(item)
    elif isinstance(value, str):
        need(len(value) <= 512 and value.isprintable() and not safety.SECRET_LIKE.search(value), "secret_like_value")
    else:
        need(value is None, "receipt_schema")


def known(value, allowed):
    return isinstance(value, str) and value in allowed


def check_entry(entry, identity):
    need(isinstance(entry, dict) and set(entry) == ENTRY_FIELDS, "receipt_schema")
    need(entry["identity"] == identity, "receipt_identity_mismatch")
    if entry["registration"] == "REGISTERED":
        need(isinstance(entry["uid"], str) and safety.UID.fullmatch(entry["uid"]) is not None
             and entry["reason"] is None, "receipt_schema")
    else:
        need(entry["registration"] == "NOT_VERIFIED" and entry["uid"] is None and known(entry["reason"], REASONS),
             "receipt_schema")
    cleanup = entry["cleanup"]
    if cleanup is not None:
        need(isinstance(cleanup, dict) and set(cleanup) == CLEANUP_FIELDS and known(cleanup["state"], CLEANUP_STATES)
             and isinstance(cleanup["at"], str) and safety.TIMESTAMP.fullmatch(cleanup["at"]) is not None,
             "receipt_schema")
        need(known(cleanup["reason"], REASONS) if cleanup["state"] == "BLOCKED" else cleanup["reason"] is None,
             "receipt_schema")
        # Without a recorded UID nothing may have been deleted.
        need(entry["registration"] == "REGISTERED" or cleanup["state"] == "BLOCKED", "receipt_schema")


def check_receipt(document, project, fp):
    need(isinstance(document, dict) and set(document) == TOP_FIELDS and document["schema"] == SCHEMA, "receipt_schema")
    scan(document)
    need(document["project"] == project, "receipt_project_mismatch")
    cluster = document["cluster"]
    need(isinstance(cluster, dict) and set(cluster) == CLUSTER_FIELDS, "receipt_schema")
    need((cluster["cluster_arn"], cluster["kube_system_uid"], cluster["fingerprint_id"])
         == (fp["cluster_arn"], fp["kube_system_uid"], fp["id"]), "fingerprint_mismatch")
    need(isinstance(document["registered_at"], str) and safety.TIMESTAMP.fullmatch(document["registered_at"])
         is not None, "receipt_schema")
    entries, identities = document["secrets"], secret_identities(project)
    need(isinstance(entries, list) and len(entries) == len(identities), "receipt_identity_mismatch")
    for entry, identity in zip(entries, identities):
        check_entry(entry, identity)
    complete = all(entry["registration"] == "REGISTERED" for entry in entries)
    need(document["result"] == ("REGISTERED" if complete else "INCOMPLETE"), "receipt_schema")


def load_receipt(directory, project, fp):
    path = directory / RECEIPT
    need(os.path.lexists(path), "receipt_missing")
    with refusals():
        data = safety.read_checked(path, MAX_RECEIPT_BYTES)
    try:
        document = json.loads(data.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise CleanupError("receipt_corrupt") from None
    need(safety.canonical(document).encode() == data, "receipt_corrupt")
    check_receipt(document, project, fp)
    return document


def write_receipt(directory, document, project, fp):
    """Validate, then replace atomically; a failed write leaves the previous receipt and no temporary file."""
    check_receipt(document, project, fp)
    data = safety.canonical(document).encode()
    need(len(data) <= MAX_RECEIPT_BYTES, "receipt_too_large")
    temporary, created = directory / (RECEIPT + ".tmp"), False
    try:
        with refusals():
            if os.path.lexists(temporary):
                safety.check_file_info(os.lstat(temporary))
                os.unlink(temporary)
            fd = safety.open_checked(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        created = True
        try:
            need(os.write(fd, data) == len(data), "receipt_save_failed")
            os.fsync(fd)
        finally:
            os.close(fd)
        if os.path.lexists(directory / RECEIPT):
            with refusals():
                safety.check_file_info(os.lstat(directory / RECEIPT))
        os.replace(temporary, directory / RECEIPT)
        created = False
        safety.fsync_dir(directory)
    except BaseException as error:
        if created:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
        if isinstance(error, OSError):
            raise CleanupError("receipt_save_failed") from None
        raise


# ---- registration -------------------------------------------------------------------------------------------------

def confirmed_by_apply(applied, identities):
    """The Secrets the apply step reported applied; a malformed or foreign report confirms none."""
    allowed = {(i["namespace"], i["name"]) for i in identities}
    if not isinstance(applied, dict) or set(applied) - allowed:
        return set()
    return {key for key, outcome in applied.items() if outcome == "applied"}


def register_with_receipt(project, cluster_arn, apply_fn, root=None, transport_kind="fake", server=None):
    """Fake-only: run the registration's apply step, then record the UID receipt from metadata reads."""
    project = check_project(project)
    identities = secret_identities(project)
    client = open_client(project, transport_kind, server, delete=False)
    fp = observe_fingerprint(client, cluster_arn)
    directory = receipt_directory(root or default_root(project), fp, create=True)
    with locked(directory):
        existing = load_receipt(directory, project, fp) if os.path.lexists(directory / RECEIPT) else None
        try:
            applied = apply_fn()
        except Exception:  # noqa: BLE001 - a failed apply confirms nothing
            applied = None
        confirmed = confirmed_by_apply(applied, identities)
        entries = []
        for identity in identities:
            uid, reason = None, "apply_not_confirmed"
            if (identity["namespace"], identity["name"]) in confirmed:
                metadata, reason = attempt(lambda: client.get_metadata(identity))
                if reason is None:
                    reason = "absent_after_apply" if metadata is None else ownership_problem(project, identity, metadata)
                if reason is None:
                    uid = metadata["uid"]
            entries.append({"identity": identity, "uid": uid, "registration": "REGISTERED" if uid else "NOT_VERIFIED",
                            "reason": None if uid else reason, "cleanup": None})
        for old, new in zip(existing["secrets"] if existing else [], entries):
            # Never drop or replace a UID that may still name a live Secret.
            if old["registration"] == "REGISTERED" and (old["cleanup"] or {}).get("state") not in CLEANED:
                need(new["uid"] == old["uid"], "receipt_conflict")
        complete = all(entry["uid"] for entry in entries)
        document = {"schema": SCHEMA, "project": project,
                    "cluster": {"cluster_arn": fp["cluster_arn"], "kube_system_uid": fp["kube_system_uid"],
                                "fingerprint_id": fp["id"]},
                    "registered_at": safety.now(), "result": "REGISTERED" if complete else "INCOMPLETE",
                    "secrets": entries}
        write_receipt(directory, document, project, fp)
    return {"result": document["result"],
            "secrets": [{"namespace": e["identity"]["namespace"], "name": e["identity"]["name"],
                         "registration": e["registration"], "reason": e["reason"]} for e in entries]}


# ---- cleanup ------------------------------------------------------------------------------------------------------

def clean_one(client, project, entry, record):
    identity, uid = entry["identity"], entry["uid"]
    previous = (entry["cleanup"] or {}).get("state")
    if entry["registration"] != "REGISTERED":
        return record("BLOCKED", "receipt_uid_unavailable")
    metadata, reason = attempt(lambda: client.get_metadata(identity))
    if reason is not None:
        return record("BLOCKED", reason)
    if metadata is None:
        return record("DELETED" if previous == "DELETED" else "ALREADY_ABSENT")
    if previous in CLEANED:
        return record("BLOCKED", "recreated_after_cleanup")
    reason = ownership_problem(project, identity, metadata)
    if reason is not None:
        return record("BLOCKED", reason)
    if metadata["uid"] != uid:
        return record("BLOCKED", "uid_mismatch")
    record("DELETE_REQUESTED")
    outcome, reason = attempt(lambda: client.delete_with_uid(identity, uid))
    if reason is not None:
        return record("BLOCKED", reason)
    if outcome not in ("deleted", "accepted"):
        return record("BLOCKED", "deleted_concurrently")
    after, reason = attempt(lambda: client.get_metadata(identity))
    if reason is not None:
        return record("BLOCKED", reason)
    if after is not None:
        return record("BLOCKED", "still_present_after_delete" if after["uid"] == uid else "recreated_after_delete")
    return record("DELETED")


def report(project, results):
    def condition(namespace):
        mine = [r for r in results if r["namespace"] == namespace]
        return "MET" if mine and all(r["state"] in CLEANED for r in mine) else "BLOCKED"
    ingress = project + "-ingress"
    return {"result": "COMPLETE" if all(r["state"] in CLEANED for r in results) else "INCOMPLETE",
            "secrets": results,
            # D18: a namespace with a remaining Secret is never deleted; MET is necessary, not sufficient.
            "namespace_secret_condition": {"istio-system": condition("istio-system"), ingress: condition(ingress),
                                           "kube-system": "NEVER_DELETED"},
            "kube_system_webhook_tls": condition("kube-system"),
            "namespace_deletion": "NOT_IMPLEMENTED"}


def cleanup(project, cluster_arn, root=None, transport_kind="fake", server=None):
    """Fake-only: delete the four registered Secrets by receipt UID, one at a time, recording each result."""
    project = check_project(project)
    client = open_client(project, transport_kind, server, delete=True)
    fp = observe_fingerprint(client, cluster_arn)
    directory = receipt_directory(root or default_root(project), fp, create=False)
    results = []
    with locked(directory):
        document = load_receipt(directory, project, fp)
        for entry in document["secrets"]:
            def record(state, reason=None, entry=entry):
                entry["cleanup"] = {"state": state, "reason": reason, "at": safety.now()}
                write_receipt(directory, document, project, fp)
                return state, reason
            state, reason = clean_one(client, project, entry, record)
            results.append({"namespace": entry["identity"]["namespace"], "name": entry["identity"]["name"],
                            "state": state, "reason": reason})
    return report(project, results)
