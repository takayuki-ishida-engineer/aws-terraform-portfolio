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
  journal is reported STALE, anything else is a mismatch.

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
}
IDENTITY_FIELDS = {"apiVersion", "kind", "namespace", "name"}
ACTIONS = {"create", "update", "noop"}
OUTCOMES = {"applied", "unchanged", "failed"}
QUARANTINE_REASONS = {"creation_unproven", "uid_changed"}
SETTLED_VERDICTS = {"CONSISTENT", "ABSENT"}


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
        need(record["reason"] in QUARANTINE_REASONS, "record_invalid:reason")
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

    @classmethod
    def from_report(cls, report):
        return cls([(s["name"], [{"apiVersion": o["apiVersion"], "kind": o["kind"], "namespace": o["namespace"],
                                  "name": o["name"]} for o in s["objects"]]) for s in report["stages"]])


def derive(records, plan):
    """Replay the journal; every inconsistency stops (journal_inconsistent:*)."""
    state = {"header": None, "objects": {}, "stages_done": [], "quarantined": {}, "open_intent": None, "last_seq": 0}
    for index, record in enumerate(records):
        check_record(record, plan)
        kind = record["type"]
        need((index == 0) == (kind == "HEADER"), "journal_inconsistent:header")
        if kind == "HEADER":
            state["header"] = {k: v for k, v in record.items() if k not in ("type", "prev")}
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
            intent = state["open_intent"]
            need(intent is None or intent["key"] == key, "journal_inconsistent:open_intent")
            need(key not in state["quarantined"], "journal_inconsistent:quarantine")
            state["quarantined"][key] = {"observed_uid": record["observed_uid"], "reason": record["reason"]}
            state["open_intent"] = None
    need(state["header"] is not None, "journal_inconsistent:header")
    return state


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
    need(os.path.lexists(directory / JOURNAL), "receipt_missing")
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
        make_dir(self.dir)
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
        """Write the HEADER of a new journal, or check an existing one and refresh a stale snapshot."""
        need(self.lock_fd is not None, "receipt_not_locked")
        records, digests = self._records()
        if not records:
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


def reconcile(state, plan, observe, runtime_manager):
    """Classify every planned object against the journal; read-only, never adopts or releases anything.

    ``observe(identity)`` returns ("absent", None), ("present", {"uid", "managers"}) or ("unknown", code).
    """
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
            elif open_intent is not None and open_intent["key"] == key:
                prior = open_intent["prior"]
                if prior["state"] == "absent":
                    verdict = "NOT_APPLIED" if presence == "absent" else "QUARANTINE_REQUIRED"
                else:
                    verdict = "REAPPLY_SAFE" if presence == "present" and observed["uid"] == prior["uid"] \
                        else "UID_CHANGED"
            elif obj["owned_uid"] is None:
                verdict = "NOT_APPLIED" if presence == "absent" else "QUARANTINE_REQUIRED"
            elif presence == "absent" or observed["uid"] != obj["owned_uid"]:
                verdict = "UID_CHANGED"
            else:
                owned = ownership(observed, runtime_manager)
                verdict = "CONSISTENT" if owned == "OWNED" else owned
            verdicts.append({"stage": stage, "identity": identity, "verdict": verdict})
    return verdicts
