#!/usr/bin/env python3
"""Ownership receipt, write-ahead journal and crash reconciliation for the Kubernetes runtime (item 6c-B3a).

Implements Owner decisions D7, D8 (no forced conflicts: nothing here applies), D10,
D16 and D17 of the 6c-B2 design record, as offline code only. Nothing here talks to
a cluster: it stores and checks local records, and classifies observations that a
caller supplies.

Store
  One directory per cluster fingerprint (D17: the cluster ARN and the
  ``kube-system`` namespace UID), outside the repository, mode 0700, files 0600,
  owned by the current user. Symlinks, other owners and group/other permissions are
  refused. Writers hold an exclusive lock.

Journal (``journal.jsonl``)
  Canonical JSON lines, appended and fsynced one at a time, each chained to the
  previous line by SHA-256. Record types: HEADER (project, fingerprint and the
  pinned manifest and input SHA-256), INTENT (written before an object is applied),
  RESULT (the UID read back), STAGE_DONE and QUARANTINE. Every field is allowlisted
  and validated; Secret identities, unknown fields and Secret- or token-like values
  are refused, so no Secret value, token, kubeconfig or manifest body can be stored.

Receipt (``receipt.json``)
  A snapshot derived from the journal, replaced atomically (temporary file, fsync,
  rename, directory fsync). On disagreement the journal wins; a snapshot behind the
  journal is reported STALE, anything else is a mismatch. The writer recreates a
  missing snapshot only for a journal that holds nothing but a verified HEADER (a
  crash right after the first write); otherwise a missing snapshot stops. A missing
  journal is never a fresh start: a new journal is created only in a directory the
  writer itself has just created and that is still empty; a journal missing next to
  a snapshot stops (``journal_missing``), and an older directory without either
  stops (``receipt_directory_not_new``). "Just created" is the atomic ``mkdir``
  result, and the permission is consumed before the first write, so the same Store
  can never initialise twice, even after a failed write or after both files vanish.

Destroy phase (6c-B4a, Owner 2026-11-24; additive, FORMAT stays 1)
  DESTROY_BEGIN moves the journal from the apply phase to the destroy phase, only with no open INTENT; no apply
  record (INTENT, RESULT, STAGE_DONE) is accepted after it. DESTROY_INTENT is written (and fsynced) before a
  DELETE: the identity, its destroy step and exactly the UID the journal owns. One INTENT is open at a time,
  apply or destroy, with one sequence. DESTROY_RESULT closes only the open DESTROY_INTENT with the same sequence
  and identity: ``deleted`` (a trusted NotFound after the request), ``absent_confirmed`` (NotFound after an
  interrupted request, kept apart) or ``failed`` (the object is still owned; a retry needs a new INTENT after the
  identity, UID and ownership are checked again). Ownership evidence (``owned_uid``) is never erased.
  DESTROY_STAGE_DONE follows the destroy order (the apply stages reversed, then ``namespace_phase``), and only when
  every owned, deletable member of that step is DELETED or ABSENT_CONFIRMED: Namespaces are deferred to
  ``namespace_phase``, CRDs are retained and never get a DESTROY_INTENT. A quarantined member blocks its step; a
  recreated or changed object is quarantined with a destroy reason and never released. A journal without
  destroy records has exactly the snapshot it always had; the destroy state appears only after DESTROY_BEGIN, and
  an older reader refuses the new record types (fail closed).

Ownership (D7)
  An object is the runtime's only when its identity is in the plan, its live UID
  equals the UID recorded in the journal and the runtime field manager has an Apply
  entry. A manager name alone is never proof. Other field managers are not
  classified here (decision D13 is open), so their presence leaves ownership
  NOT_VERIFIED. Objects without a journal record are never adopted, an INTENT may
  only claim an owned prior state with the UID the journal recorded, and quarantined
  objects cannot be released (D16: no release operation exists).
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preflight  # noqa: E402

FORMAT = 1
JOURNAL = "journal.jsonl"
RECEIPT = "receipt.json"
LOCK = "lock"
GENESIS = "0" * 64
MAX_LINE_BYTES = 4096
MAX_RECORDS = 4096
MAX_RECEIPT_BYTES = 4 * 1024 * 1024

UID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SHA256 = re.compile(r"[0-9a-f]{64}")
FINGERPRINT_ID = re.compile(r"[0-9a-f]{32}")
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
NAME = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
KIND = re.compile(r"[A-Z][A-Za-z0-9]{0,62}")
API_VERSION = re.compile(r"([a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?/)?v[0-9]+((alpha|beta)[0-9]+)?")
PROJECT = re.compile(r"[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?")
CLUSTER_ARN = re.compile(r"arn:aws:eks:ca-central-1:[0-9]{12}:cluster/[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
RESOURCE_VERSION = re.compile(r"[0-9]{1,20}")
# Values that look like key material, tokens or encoded blobs are never stored.
SECRET_LIKE = re.compile(r"-----BEGIN|PRIVATE KEY|eyJ[A-Za-z0-9_-]{8,}|k8s-aws-v1\.|\bA[KS]IA[0-9A-Z]{16}\b"
                         r"|(?=[A-Za-z0-9+/]*[g-zG-Z+/])[A-Za-z0-9+/]{40,}={0,2}"
                         r"|password|passwd|bearer |client-key|token[=:]", re.IGNORECASE)

RECORD_FIELDS = {
    "HEADER": {"type", "format", "project", "cluster_arn", "kube_system_uid", "fingerprint_id", "manifest_sha256",
               "input_sha256", "created_at", "prev"},
    "INTENT": {"type", "seq", "stage", "identity", "prior", "action", "at", "prev"},
    "RESULT": {"type", "seq", "identity", "uid", "resource_version", "generation", "outcome", "at", "prev"},
    "STAGE_DONE": {"type", "stage", "at", "prev"},
    "QUARANTINE": {"type", "identity", "observed_uid", "reason", "at", "prev"},
    "DESTROY_BEGIN": {"type", "at", "prev"},
    "DESTROY_INTENT": {"type", "seq", "stage", "identity", "uid", "at", "prev"},
    "DESTROY_RESULT": {"type", "seq", "identity", "outcome", "observed_uid", "at", "prev"},
    "DESTROY_STAGE_DONE": {"type", "stage", "at", "prev"},
}
APPLY_RECORDS = {"INTENT", "RESULT", "STAGE_DONE"}
DESTROY_OUTCOMES = {"deleted", "absent_confirmed", "failed"}
DESTROYED = {"deleted", "absent_confirmed"}
DESTROY_QUARANTINE_REASONS = {"recreated_after_delete", "uid_changed_before_delete", "delete_unproven"}
NAMESPACE_PHASE = "namespace_phase"
CRD_KEY_PREFIX = "apiextensions.k8s.io/v1|CustomResourceDefinition|"
IDENTITY_FIELDS = {"apiVersion", "kind", "namespace", "name"}
ACTIONS = {"create", "update", "noop"}
OUTCOMES = {"applied", "unchanged", "failed"}
# ownership_unproven (6c-B3b-Apply-A): an apply that landed but whose field ownership could not be proven.
QUARANTINE_REASONS = {"creation_unproven", "uid_changed", "ownership_unproven"}
SETTLED_VERDICTS = {"CONSISTENT", "ABSENT", "DESTROYED"}


class ReceiptError(Exception):
    """The receipt or journal is missing, unsafe, inconsistent or refused; the message is a fixed code."""


def need(condition, code):
    if not condition:
        raise ReceiptError(code)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(cluster_arn, kube_system_uid):
    """D17: the cluster ARN plus the kube-system namespace UID; the id names the receipt directory."""
    need(isinstance(cluster_arn, str) and CLUSTER_ARN.fullmatch(cluster_arn) is not None, "fingerprint_arn_invalid")
    need(isinstance(kube_system_uid, str) and UID.fullmatch(kube_system_uid) is not None, "fingerprint_uid_invalid")
    return {"cluster_arn": cluster_arn, "kube_system_uid": kube_system_uid,
            "id": digest((cluster_arn + "\n" + kube_system_uid).encode())[:32]}


def default_root(project):
    return Path.home() / ".local" / "state" / (project + "-k8s-runtime")


def inside_repository(path):
    path = Path(path).expanduser().resolve()
    return path == preflight.REPOSITORY or preflight.REPOSITORY in path.parents


def key_of(identity):
    return "|".join((identity["apiVersion"], identity["kind"], identity["namespace"], identity["name"]))


# ---- file safety --------------------------------------------------------------------------------------------------

def check_dir(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise ReceiptError("receipt_missing") from None
    need(not stat.S_ISLNK(info.st_mode), "receipt_symlink")
    need(stat.S_ISDIR(info.st_mode), "receipt_not_directory")
    need(info.st_uid == os.geteuid(), "receipt_owner_mismatch")
    need(stat.S_IMODE(info.st_mode) & 0o077 == 0, "receipt_permission")


def check_file_info(info):
    need(not stat.S_ISLNK(info.st_mode), "receipt_symlink")
    need(stat.S_ISREG(info.st_mode), "receipt_not_regular_file")
    need(info.st_uid == os.geteuid(), "receipt_owner_mismatch")
    need(stat.S_IMODE(info.st_mode) & 0o177 == 0, "receipt_permission")


def open_checked(path, flags, mode=0o600):
    """Open without following symlinks and check the opened file itself."""
    try:
        before = os.lstat(path)
        check_file_info(before)
    except FileNotFoundError:
        before = None
        need(flags & os.O_CREAT, "receipt_missing")
    try:
        fd = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    except OSError:
        raise ReceiptError("receipt_symlink" if os.path.islink(path) else "receipt_open_failed") from None
    info = os.fstat(fd)
    try:
        check_file_info(info)
        need(before is None or (before.st_dev, before.st_ino) == (info.st_dev, info.st_ino), "receipt_replaced")
    except ReceiptError:
        os.close(fd)
        raise
    return fd


def read_checked(path, limit):
    fd = open_checked(path, os.O_RDONLY)
    try:
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    need(len(data) <= limit, "receipt_too_large")
    return data


def make_dir(path):
    path = Path(path)
    if not os.path.lexists(path):
        os.makedirs(path, mode=0o700)
    check_dir(path)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# ---- record validation --------------------------------------------------------------------------------------------

def scan_values(value):
    if isinstance(value, dict):
        for item in value.values():
            scan_values(item)
    elif isinstance(value, str):
        need(len(value) <= 512 and not SECRET_LIKE.search(value), "secret_like_value")
        need(value.isprintable(), "control_character")


def check_identity(identity, plan):
    need(isinstance(identity, dict) and set(identity) == IDENTITY_FIELDS, "identity_fields")
    need(identity["kind"] != "Secret", "secret_identity_refused")
    need(all(isinstance(identity[f], str) for f in IDENTITY_FIELDS), "identity_fields")
    need(API_VERSION.fullmatch(identity["apiVersion"]) is not None and KIND.fullmatch(identity["kind"]) is not None
         and NAME.fullmatch(identity["name"]) is not None
         and (identity["namespace"] == "" or NAME.fullmatch(identity["namespace"]) is not None), "identity_invalid")
    need(key_of(identity) in plan.stage_of, "identity_not_in_plan")


def check_record(record, plan):
    need(isinstance(record, dict) and record.get("type") in RECORD_FIELDS, "record_type_unknown")
    need(set(record) == RECORD_FIELDS[record["type"]], "record_field_not_allowed")
    scan_values(record)
    need(isinstance(record["prev"], str) and SHA256.fullmatch(record["prev"]) is not None, "record_invalid:prev")
    kind = record["type"]
    if kind == "HEADER":
        need(record["format"] == FORMAT, "record_invalid:format")
        need(PROJECT.fullmatch(str(record["project"])) is not None, "record_invalid:project")
        need(fingerprint(record["cluster_arn"], record["kube_system_uid"])["id"] == record["fingerprint_id"],
             "record_invalid:fingerprint")
        need(all(isinstance(record[f], str) and SHA256.fullmatch(record[f]) for f in ("manifest_sha256",
                                                                                       "input_sha256")),
             "record_invalid:sha256")
        need(isinstance(record["created_at"], str) and TIMESTAMP.fullmatch(record["created_at"]), "record_invalid:time")
        return
    need(isinstance(record["at"], str) and TIMESTAMP.fullmatch(record["at"]) is not None, "record_invalid:time")
    if kind == "DESTROY_BEGIN":
        return
    if kind == "DESTROY_STAGE_DONE":
        need(record["stage"] in plan.destroy_order, "record_invalid:stage")
        return
    if kind in ("DESTROY_INTENT", "DESTROY_RESULT"):
        check_identity(record["identity"], plan)
        key = key_of(record["identity"])
        need(isinstance(record["seq"], int) and not isinstance(record["seq"], bool) and record["seq"] >= 1,
             "record_invalid:seq")
        if kind == "DESTROY_INTENT":
            need(not key.startswith(CRD_KEY_PREFIX), "record_invalid:crd_retained")
            need(record["stage"] == plan.destroy_step(key), "record_invalid:stage")
            need(isinstance(record["uid"], str) and UID.fullmatch(record["uid"]) is not None, "record_invalid:uid")
        else:
            need(record["outcome"] in DESTROY_OUTCOMES, "record_invalid:outcome")
            observed = record["observed_uid"]
            need(observed is None if record["outcome"] in DESTROYED
                 else observed is None or (isinstance(observed, str) and UID.fullmatch(observed) is not None),
                 "record_invalid:uid")
        return
    if kind == "STAGE_DONE":
        need(record["stage"] in plan.stage_order, "record_invalid:stage")
        return
    check_identity(record["identity"], plan)
    if kind == "INTENT":
        need(isinstance(record["seq"], int) and not isinstance(record["seq"], bool) and record["seq"] >= 1,
             "record_invalid:seq")
        need(record["stage"] in plan.stage_order, "record_invalid:stage")
        need(record["action"] in ACTIONS, "record_invalid:action")
        prior = record["prior"]
        need(prior in ({"state": "absent"},) or (isinstance(prior, dict) and set(prior) == {"state", "uid"}
                                                   and prior["state"] == "owned" and isinstance(prior["uid"], str)
                                                   and UID.fullmatch(prior["uid"])), "record_invalid:prior")
    elif kind == "RESULT":
        need(isinstance(record["seq"], int) and not isinstance(record["seq"], bool) and record["seq"] >= 1,
             "record_invalid:seq")
        need(record["outcome"] in OUTCOMES, "record_invalid:outcome")
        if record["outcome"] == "failed":
            need(record["uid"] is None and record["resource_version"] is None and record["generation"] is None,
                 "record_invalid:failed_result")
        else:
            need(isinstance(record["uid"], str) and UID.fullmatch(record["uid"]) is not None, "record_invalid:uid")
            need(isinstance(record["resource_version"], str)
                 and RESOURCE_VERSION.fullmatch(record["resource_version"]) is not None, "record_invalid:rv")
            need(isinstance(record["generation"], int) and not isinstance(record["generation"], bool)
                 and 0 <= record["generation"] < 2 ** 53, "record_invalid:generation")
    elif kind == "QUARANTINE":
        need(record["reason"] in QUARANTINE_REASONS | DESTROY_QUARANTINE_REASONS, "record_invalid:reason")
        need(record["observed_uid"] is None or (isinstance(record["observed_uid"], str)
                                                and UID.fullmatch(record["observed_uid"])), "record_invalid:uid")


class Plan:
    """The reviewed stage order and the stage of every identity, from ``k8s_runtime.plan``."""

    def __init__(self, stages):
        self.stage_order = [name for name, _ in stages]
        self.stage_of = {}
        self.members = {}
        for name, identities in stages:
            self.members[name] = [key_of(i) for i in identities]
            for identity in identities:
                self.stage_of[key_of(identity)] = name
        need(len(self.stage_order) == len(set(self.stage_order)), "plan_invalid")
        need(NAMESPACE_PHASE not in self.stage_order, "plan_invalid")
        # Destroy (6c-B4a): the apply stages reversed, then every Namespace together; CRDs are retained.
        self.destroy_order = list(reversed(self.stage_order)) + [NAMESPACE_PHASE]

    def destroy_step(self, key):
        return NAMESPACE_PHASE if key.split("|")[1] == "Namespace" else self.stage_of.get(key)

    def destroy_members(self, step):
        """The deletable members of a destroy step: never a CRD; Namespaces only in namespace_phase."""
        keys = [k for stage in self.stage_order for k in self.members[stage]] if step == NAMESPACE_PHASE \
            else self.members[step]
        return [k for k in keys if not k.startswith(CRD_KEY_PREFIX) and self.destroy_step(k) == step]

    @classmethod
    def from_report(cls, report):
        return cls([(s["name"], [{"apiVersion": o["apiVersion"], "kind": o["kind"], "namespace": o["namespace"],
                                  "name": o["name"]} for o in s["objects"]]) for s in report["stages"]])


def derive(records, plan):
    """Replay the journal; every inconsistency stops (journal_inconsistent:*)."""
    state = {"header": None, "objects": {}, "stages_done": [], "quarantined": {}, "open_intent": None, "last_seq": 0,
             "phase": "apply", "destroy_stages_done": []}
    for index, record in enumerate(records):
        check_record(record, plan)
        kind = record["type"]
        need((index == 0) == (kind == "HEADER"), "journal_inconsistent:header")
        if kind == "HEADER":
            state["header"] = {k: v for k, v in record.items() if k not in ("type", "prev")}
            continue
        if kind in APPLY_RECORDS:
            need(state["phase"] == "apply", "journal_inconsistent:destroy_phase")
        if kind == "DESTROY_BEGIN":
            need(state["phase"] == "apply", "journal_inconsistent:destroy_begin")
            need(state["open_intent"] is None, "journal_inconsistent:open_intent")
            state["phase"] = "destroy"
            continue
        if kind == "DESTROY_STAGE_DONE":
            need(state["phase"] == "destroy", "journal_inconsistent:not_destroy_phase")
            need(state["open_intent"] is None, "journal_inconsistent:open_intent")
            done = state["destroy_stages_done"]
            need(len(done) < len(plan.destroy_order) and record["stage"] == plan.destroy_order[len(done)],
                 "journal_inconsistent:destroy_stage_order")
            for member in plan.destroy_members(record["stage"]):
                obj = state["objects"].get(member)
                need(member not in state["quarantined"], "journal_inconsistent:destroy_stage_incomplete")
                need(obj is None or obj["owned_uid"] is None or obj.get("destroyed") in DESTROYED,
                     "journal_inconsistent:destroy_stage_incomplete")
            done.append(record["stage"])
            continue
        if kind in ("DESTROY_INTENT", "DESTROY_RESULT"):
            need(state["phase"] == "destroy", "journal_inconsistent:not_destroy_phase")
            key = key_of(record["identity"])
            obj = state["objects"].get(key)
            if kind == "DESTROY_INTENT":
                need(state["open_intent"] is None, "journal_inconsistent:open_intent")
                need(record["seq"] == state["last_seq"] + 1, "journal_inconsistent:seq")
                need(not state["quarantined"].get(key), "quarantined")
                owned = obj["owned_uid"] if obj is not None else None
                need(owned is not None, "destroy_not_owned")
                need(owned == record["uid"], "destroy_uid_mismatch")
                need((obj or {}).get("destroyed") is None, "journal_inconsistent:already_destroyed")
                done = state["destroy_stages_done"]
                position = plan.destroy_order.index(record["stage"])
                need(done == plan.destroy_order[:position], "journal_inconsistent:destroy_stage_order")
                state["last_seq"] = record["seq"]
                state["open_intent"] = {"seq": record["seq"], "key": key, "uid": record["uid"], "phase": "destroy"}
            else:
                intent = state["open_intent"]
                need(intent is not None and intent.get("phase") == "destroy" and intent["seq"] == record["seq"]
                     and intent["key"] == key, "journal_inconsistent:result")
                if record["outcome"] in DESTROYED:
                    obj["destroyed"] = record["outcome"]
                state["open_intent"] = None
            continue
        if kind == "STAGE_DONE":
            need(state["open_intent"] is None, "journal_inconsistent:open_intent")
            done = state["stages_done"]
            need(len(done) < len(plan.stage_order) and record["stage"] == plan.stage_order[len(done)],
                 "journal_inconsistent:stage_order")
            for member in plan.members[record["stage"]]:
                obj = state["objects"].get(member)
                need(obj is not None and obj["owned_uid"] is not None and member not in state["quarantined"],
                     "journal_inconsistent:stage_incomplete")
            done.append(record["stage"])
            continue
        key = key_of(record["identity"])
        obj = state["objects"].setdefault(key, {"identity": record["identity"], "stage": plan.stage_of[key],
                                                "owned_uid": None, "last_outcome": None})
        if kind == "INTENT":
            need(state["open_intent"] is None, "journal_inconsistent:open_intent")
            need(record["seq"] == state["last_seq"] + 1, "journal_inconsistent:seq")
            need(key not in state["quarantined"], "quarantined")
            need(record["stage"] == plan.stage_of[key], "journal_inconsistent:stage")
            need(record["stage"] not in state["stages_done"], "journal_inconsistent:stage_closed")
            position = plan.stage_order.index(record["stage"])
            need(state["stages_done"] == plan.stage_order[:position], "journal_inconsistent:stage_order")
            if record["prior"]["state"] == "owned":
                need(obj["owned_uid"] == record["prior"]["uid"], "adoption_refused")
            else:
                need(obj["owned_uid"] is None, "journal_inconsistent:prior")
            state["last_seq"] = record["seq"]
            state["open_intent"] = {"seq": record["seq"], "key": key, "prior": record["prior"],
                                    "action": record["action"]}
        elif kind == "RESULT":
            intent = state["open_intent"]
            need(intent is not None and intent["seq"] == record["seq"] and intent["key"] == key,
                 "journal_inconsistent:result")
            if record["outcome"] != "failed":
                prior = intent["prior"]
                need(prior["state"] == "absent" or prior["uid"] == record["uid"], "journal_inconsistent:uid")
                obj["owned_uid"] = record["uid"]
            obj["last_outcome"] = record["outcome"]
            state["open_intent"] = None
        elif kind == "QUARANTINE":
            need(state["phase"] == "destroy" or record["reason"] in QUARANTINE_REASONS, "record_invalid:reason")
            intent = state["open_intent"]
            need(intent is None or intent["key"] == key, "journal_inconsistent:open_intent")
            need(key not in state["quarantined"], "journal_inconsistent:quarantine")
            state["quarantined"][key] = {"observed_uid": record["observed_uid"], "reason": record["reason"]}
            state["open_intent"] = None
    need(state["header"] is not None, "journal_inconsistent:header")
    return state


def plan_identities(plan):
    """The reviewed plan's identities, the only input a destroy policy (k8s_runtime_transport.DestroyPolicy) reads."""
    return [dict(zip(("apiVersion", "kind", "namespace", "name"), k.split("|")))
            for stage in plan.stage_order for k in plan.members[stage]]


def owned_uids(state):
    """The destroy policy's DELETE map from a verified journal: owned, not destroyed, not quarantined, never a CRD."""
    return {tuple(k.split("|")): v["owned_uid"] for k, v in sorted(state["objects"].items())
            if v["owned_uid"] is not None and v.get("destroyed") is None and k not in state["quarantined"]
            and not k.startswith(CRD_KEY_PREFIX)}


def crd_receipt_uids(state):
    """The destroy policy's separate CRD verification map: retained CRDs the journal owns, not quarantined.

    It proves which CRD UID is the runtime's for the specialised CRD read; it never grants a DELETE."""
    return {tuple(k.split("|")): v["owned_uid"] for k, v in sorted(state["objects"].items())
            if k.startswith(CRD_KEY_PREFIX) and v["owned_uid"] is not None and k not in state["quarantined"]}


def parse_journal(data, plan):
    """Records and line digests; every line canonical and chained to the one before it."""
    need(len(data) <= MAX_RECORDS * MAX_LINE_BYTES, "receipt_too_large")
    need(data.endswith(b"\n"), "journal_corrupt:truncated_line")
    records, digests, previous = [], [], GENESIS
    for line in data[:-1].split(b"\n"):
        need(0 < len(line) < MAX_LINE_BYTES, "journal_corrupt:line_size")
        try:
            record = json.loads(line.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            raise ReceiptError("journal_corrupt:not_json") from None
        need(canonical(record).encode() == line, "journal_corrupt:not_canonical")
        need(isinstance(record, dict) and record.get("prev") == previous, "journal_corrupt:chain")
        previous = digest(line)
        records.append(record)
        digests.append(previous)
    need(len(records) <= MAX_RECORDS, "receipt_too_large")
    derive(records, plan)
    return records, digests


def summary(state):
    result = apply_summary(state)
    if state.get("phase") == "destroy":
        # Only after DESTROY_BEGIN: an apply-only journal keeps exactly its earlier snapshot.
        result["destroy"] = {"stages_done": list(state["destroy_stages_done"]),
                             "destroyed": {k: v["destroyed"] for k, v in sorted(state["objects"].items())
                                           if v.get("destroyed")}}
    return result


def apply_summary(state):
    return {"header": state["header"], "stages_done": list(state["stages_done"]),
            "objects": {k: {"identity": v["identity"], "stage": v["stage"], "owned_uid": v["owned_uid"],
                            "last_outcome": v["last_outcome"]} for k, v in sorted(state["objects"].items())},
            "quarantined": dict(sorted(state["quarantined"].items())), "open_intent": state["open_intent"],
            "last_seq": state["last_seq"]}


def snapshot(records, digests, plan):
    return {"format": FORMAT, "fingerprint_id": records[0]["fingerprint_id"], "journal_records": len(records),
            "journal_last_sha256": digests[-1], "state": summary(derive(records, plan))}


def check_header(header, expected):
    """D17 fingerprint, the project and D10 pins: a different bundle stops."""
    if expected.get("fingerprint") is not None:
        fp = expected["fingerprint"]
        need((header["cluster_arn"], header["kube_system_uid"], header["fingerprint_id"])
             == (fp["cluster_arn"], fp["kube_system_uid"], fp["id"]), "fingerprint_mismatch")
    need(header["project"] == expected["project"], "project_mismatch")
    need(header["manifest_sha256"] == expected["manifest_sha256"]
         and header["input_sha256"] == expected["input_sha256"], "bundle_changed")


def load(directory, plan, expected):
    """Read-only: validate the store, the journal chain, the snapshot and the header expectations."""
    directory = Path(directory)
    check_dir(directory)
    if not os.path.lexists(directory / JOURNAL):
        raise ReceiptError("journal_missing" if os.path.lexists(directory / RECEIPT) else "receipt_missing")
    records, digests = parse_journal(read_checked(directory / JOURNAL, MAX_RECORDS * MAX_LINE_BYTES), plan)
    state = derive(records, plan)
    need(directory.name == state["header"]["fingerprint_id"], "receipt_directory_mismatch")
    check_header(state["header"], expected)
    need(os.path.lexists(directory / RECEIPT), "receipt_snapshot_missing")
    try:
        receipt = json.loads(read_checked(directory / RECEIPT, MAX_RECEIPT_BYTES).decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise ReceiptError("receipt_journal_mismatch") from None
    need(isinstance(receipt, dict) and set(receipt) == {"format", "fingerprint_id", "journal_records",
                                                        "journal_last_sha256", "state"}
         and isinstance(receipt["journal_records"], int) and receipt["journal_records"] >= 1,
         "receipt_journal_mismatch")
    count = receipt["journal_records"]
    need(count <= len(records), "journal_truncated")
    expected_snapshot = snapshot(records[:count], digests[:count], plan)
    need(receipt == json.loads(canonical(expected_snapshot)), "receipt_journal_mismatch")
    return {"records": records, "digests": digests, "state": state,
            "receipt": "CURRENT" if count == len(records) else "STALE"}


class Store:
    """The writer. Every write holds the exclusive lock and is validated by replaying the journal first."""

    def __init__(self, root, fp, project, manifest_sha256, input_sha256, plan):
        root = Path(root).expanduser()
        need(not inside_repository(root), "receipt_inside_repository")
        self.plan = plan
        self.expected = {"fingerprint": fp, "project": project, "manifest_sha256": manifest_sha256,
                         "input_sha256": input_sha256}
        make_dir(root)
        self.dir = root / fp["id"]
        # Only a directory this Store creates itself may be initialised, decided by the atomic mkdir
        # result (a directory made by anyone else, even a moment earlier, is FileExistsError). Any
        # earlier directory may have held ownership evidence, so a missing journal there is never a
        # fresh start. The permission is used at most once (see begin).
        try:
            os.mkdir(self.dir, 0o700)
            created = True
        except FileExistsError:
            created = False
        check_dir(self.dir)
        self.created_here = created
        self._init_allowed = created
        self.lock_fd = None

    @contextlib.contextmanager
    def lock(self):
        fd = open_checked(self.dir / LOCK, os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReceiptError("receipt_locked") from None
            self.lock_fd = fd
            yield self
        finally:
            self.lock_fd = None
            os.close(fd)

    def _records(self):
        if not os.path.lexists(self.dir / JOURNAL):
            return [], []
        return parse_journal(read_checked(self.dir / JOURNAL, MAX_RECORDS * MAX_LINE_BYTES), self.plan)

    def _append(self, record):
        need(self.lock_fd is not None, "receipt_not_locked")
        records, digests = self._records()
        record = dict(record, prev=digests[-1] if digests else GENESIS)
        line = canonical(record).encode()
        need(len(line) < MAX_LINE_BYTES, "journal_corrupt:line_size")
        state = derive(records + [record], self.plan)  # refuse an invalid write before it reaches the disk
        check_header(state["header"], self.expected)
        fd = open_checked(self.dir / JOURNAL, os.O_WRONLY | os.O_APPEND | (0 if records else os.O_CREAT | os.O_EXCL))
        try:
            written = os.write(fd, line + b"\n")
            need(written == len(line) + 1, "journal_write_incomplete")
            os.fsync(fd)
        finally:
            os.close(fd)
        if not records:
            fsync_dir(self.dir)
        self._write_snapshot(snapshot(records + [record], digests + [digest(line)], self.plan))
        return state

    def _write_snapshot(self, value):
        temporary = self.dir / (RECEIPT + ".tmp")
        if os.path.lexists(temporary):
            check_file_info(os.lstat(temporary))
            os.unlink(temporary)
        fd = open_checked(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            data = canonical(value).encode()
            need(len(data) <= MAX_RECEIPT_BYTES, "receipt_too_large")
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, self.dir / RECEIPT)
        fsync_dir(self.dir)

    def begin(self):
        """Write the HEADER of a new journal, or check an existing one and repair only what is provably safe.

        A snapshot behind a verified journal prefix is refreshed (STALE). A missing snapshot is
        recreated only when the journal holds nothing but a verified HEADER (a crash right after the
        first write); with any other record it stays missing and the run stops. A present but
        inconsistent snapshot is never rewritten.
        """
        need(self.lock_fd is not None, "receipt_not_locked")
        records, digests = self._records()
        if records and not os.path.lexists(self.dir / RECEIPT):
            replayed = derive(records, self.plan)  # chain and schema already checked by _records
            check_header(replayed["header"], self.expected)  # fingerprint and pins before any repair
            need(len(records) == 1, "receipt_snapshot_missing")
            self._write_snapshot(snapshot(records, digests, self.plan))
            return "SNAPSHOT_CREATED"
        if not records:
            need(not os.path.lexists(self.dir / RECEIPT), "journal_missing")  # never overwrite evidence
            need(self._init_allowed, "receipt_directory_not_new")
            self._init_allowed = False  # consumed before the first write: a failed write never re-grants it
            need(set(os.listdir(self.dir)) <= {LOCK}, "receipt_directory_not_new")
            fp = self.expected["fingerprint"]
            self._append({"type": "HEADER", "format": FORMAT, "project": self.expected["project"],
                          "cluster_arn": fp["cluster_arn"], "kube_system_uid": fp["kube_system_uid"],
                          "fingerprint_id": fp["id"], "manifest_sha256": self.expected["manifest_sha256"],
                          "input_sha256": self.expected["input_sha256"], "created_at": now()})
            return "CREATED"
        loaded = load(self.dir, self.plan, self.expected)
        if loaded["receipt"] == "STALE":
            self._write_snapshot(snapshot(records, digests, self.plan))
            return "REFRESHED"
        return "CURRENT"

    def intent(self, stage, identity, prior, action):
        records, _ = self._records()
        seq = derive(records, self.plan)["last_seq"] + 1 if records else 1
        self._append({"type": "INTENT", "seq": seq, "stage": stage, "identity": identity, "prior": prior,
                      "action": action, "at": now()})
        return seq

    def result(self, seq, identity, uid, resource_version, generation, outcome):
        self._append({"type": "RESULT", "seq": seq, "identity": identity, "uid": uid,
                      "resource_version": resource_version, "generation": generation, "outcome": outcome,
                      "at": now()})

    def stage_done(self, stage):
        self._append({"type": "STAGE_DONE", "stage": stage, "at": now()})

    def quarantine(self, identity, observed_uid, reason):
        self._append({"type": "QUARANTINE", "identity": identity, "observed_uid": observed_uid, "reason": reason,
                      "at": now()})

    def begin_destroy(self):
        self._append({"type": "DESTROY_BEGIN", "at": now()})

    def destroy_intent(self, identity, uid):
        """Written and fsynced before a DELETE; refused (nothing written) unless the journal owns exactly that UID."""
        records, _ = self._records()
        seq = derive(records, self.plan)["last_seq"] + 1
        self._append({"type": "DESTROY_INTENT", "seq": seq, "stage": self.plan.destroy_step(key_of(identity)),
                      "identity": identity, "uid": uid, "at": now()})
        return seq

    def destroy_result(self, seq, identity, outcome, observed_uid=None):
        self._append({"type": "DESTROY_RESULT", "seq": seq, "identity": identity, "outcome": outcome,
                      "observed_uid": observed_uid, "at": now()})

    def destroy_stage_done(self, stage):
        self._append({"type": "DESTROY_STAGE_DONE", "stage": stage, "at": now()})

    def release_quarantine(self, *args, **kwargs):
        raise ReceiptError("quarantine_release_not_approved")

    def adopt(self, *args, **kwargs):
        raise ReceiptError("adoption_refused")


def ownership(observed, runtime_manager):
    """D7 field-manager part: the runtime's Apply entry, and no other manager (D13 is open)."""
    managers = observed.get("managers") or []
    runtime = [m for m in managers if m.get("manager") == runtime_manager and m.get("operation") == "Apply"
               and not m.get("subresource")]
    if not runtime:
        return "NOT_OWNED"
    return "OWNED" if len(runtime) == len(managers) else "OWNERSHIP_NOT_VERIFIED"


def reconcile(state, plan, observe, runtime_manager, ownership_fn=None):
    """Classify every planned object against the journal; read-only, never adopts or releases anything.

    ``observe(identity)`` returns ("absent", None), ("present", {"uid", "managers"}) or ("unknown", code).
    ``ownership_fn`` replaces the strict default (only the runtime Apply entry) where a caller applies the
    reviewed field-ownership allowlist (decision D13); ``receipt verify`` keeps the strict default.
    """
    owns = ownership_fn or ownership
    verdicts = []
    open_intent = state["open_intent"]
    for stage in plan.stage_order:
        for key in plan.members[stage]:
            apiversion, kind, namespace, name = key.split("|")
            identity = {"apiVersion": apiversion, "kind": kind, "namespace": namespace, "name": name}
            presence, observed = observe(identity)
            obj = state["objects"].get(key)
            if key in state["quarantined"]:
                verdict = "QUARANTINED"
            elif presence == "unknown":
                verdict = "UNKNOWN"
            elif obj is None:
                verdict = "ABSENT" if presence == "absent" else "NOT_OWNED"
            elif obj.get("destroyed") in DESTROYED:
                verdict = "DESTROYED" if presence == "absent" else "RECREATED_AFTER_DESTROY"
            elif open_intent is not None and open_intent["key"] == key and open_intent.get("phase") == "destroy":
                # An interrupted DELETE: absence still needs a trusted NotFound and its RESULT; the same UID needs
                # identity, UID and ownership checked again before any new DELETE. Never an automatic resend.
                if presence == "absent":
                    verdict = "DELETE_ABSENT_UNCONFIRMED"
                elif observed["uid"] != open_intent["uid"]:
                    verdict = "UID_CHANGED"
                else:
                    verdict = "DELETE_PENDING_RECHECK"
            elif open_intent is not None and open_intent["key"] == key:
                prior = open_intent["prior"]
                if prior["state"] == "absent":
                    verdict = "NOT_APPLIED" if presence == "absent" else "QUARANTINE_REQUIRED"
                elif presence == "absent" or observed["uid"] != prior["uid"]:
                    verdict = "UID_CHANGED"
                else:
                    # D7: the same UID is not enough; the runtime's field ownership must also hold.
                    owned_prior = owns(observed, runtime_manager)
                    verdict = "REAPPLY_SAFE" if owned_prior == "OWNED" else owned_prior
            elif obj["owned_uid"] is None:
                verdict = "NOT_APPLIED" if presence == "absent" else "QUARANTINE_REQUIRED"
            elif presence == "absent" or observed["uid"] != obj["owned_uid"]:
                verdict = "UID_CHANGED"
            else:
                owned = owns(observed, runtime_manager)
                verdict = "CONSISTENT" if owned == "OWNED" else owned
            verdicts.append({"stage": stage, "identity": identity, "verdict": verdict})
    return verdicts
