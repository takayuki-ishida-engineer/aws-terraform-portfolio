#!/usr/bin/env python3
"""Candidate bounded Linux fork-per-task executor for offline runtime tests.

No production imports or cloud operations. The caller supplies reviewed task IDs and
functions. Each task runs once in its own process group, HOME and temporary directory.
A valid result is not success until the child exited normally and its group is empty.
"""
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

MAX_WORKERS = 4
MAX_RESULT_BYTES = 1024 * 1024
TASK_ID = re.compile(r"[A-Za-z0-9_.:/-]{1,240}\Z")


class RunnerError(RuntimeError):
    """An incomplete, invalid or unsafe execution is never a passing result."""


def require(condition, code):
    if not condition:
        raise RunnerError(code)


def cgroup_directories(controller):
    """Enumerate visible cgroup ancestors without assuming a host mount layout."""
    groups = Path("/proc/self/cgroup").read_text().splitlines()
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    found = set()
    for group in groups:
        hierarchy, controllers, relative = group.split(":", 2)
        mode = "v2" if hierarchy == "0" and not controllers else "v1" if controller in controllers.split(",") else None
        if mode is None:
            continue
        for mount in mounts:
            left, right = mount.split(" - ", 1)
            fields, fs = left.split(), right.split()
            if not (mode == "v2" and fs[0] == "cgroup2" or
                    mode == "v1" and fs[0] == "cgroup" and controller in fs[2].split(",")):
                continue
            mount_root, mountpoint = Path(fields[3]), Path(fields[4])
            require("\\" not in fields[3] + fields[4], "cgroup_path_unreadable")
            try:
                child = mountpoint / Path(relative).relative_to(mount_root)
            except ValueError:
                if relative != "/":
                    continue
                child = mountpoint
            require(child.is_dir(), "cgroup_directory_unreadable")
            while True:
                found.add((mode, child))
                if child == mountpoint:
                    break
                require(mountpoint in child.parents, "cgroup_path_outside_mount")
                child = child.parent
    require(found, controller + "_cgroup_unresolved")
    return sorted(found)


def available_cpus():
    """Conservative CPU cap, respecting affinity and visible Linux cgroup limits."""
    require(sys.platform == "linux" and hasattr(os, "sched_getaffinity"), "linux_required")
    cap = len(os.sched_getaffinity(0))
    for mode, child in cgroup_directories("cpu"):
        if mode == "v2":
            entry = child / "cpu.max"
            if entry.is_file():
                quota, period = entry.read_text().split()
                if quota != "max":
                    cap = min(cap, max(1, int(quota) // int(period)))
        else:
            quota = int((child / "cpu.cfs_quota_us").read_text())
            period = int((child / "cpu.cfs_period_us").read_text())
            if quota >= 0:
                cap = min(cap, max(1, quota // period))
    require(cap >= 1, "no_available_cpu")
    return min(MAX_WORKERS, cap)


def available_memory():
    """Available bytes; use the smallest host/cgroup headroom, not host RAM alone."""
    match = re.search(r"^MemAvailable:\s+(\d+) kB$", Path("/proc/meminfo").read_text(), re.M)
    require(match is not None, "memory_availability_unknown")
    available = int(match[1]) * 1024
    for mode, child in cgroup_directories("memory"):
        limit_file, current_file = (("memory.max", "memory.current") if mode == "v2" else
                                    ("memory.limit_in_bytes", "memory.usage_in_bytes"))
        limit_path = child / limit_file
        if mode == "v2" and not limit_path.is_file():
            continue
        raw = limit_path.read_text().strip()
        if raw == "max":
            continue
        limit, current = int(raw), int((child / current_file).read_text())
        require(limit > 0 and current >= 0, "memory_limit_invalid")
        available = min(available, max(0, limit - current))
    return available


def available_workers():
    # Profiling peak was 140 MiB. Budget 512 MiB per child and 512 MiB for
    # parent/other work. This is a conservative admission check, not a RAM guarantee.
    mib = 1024 * 1024
    memory_cap = max(0, (available_memory() - 512 * mib) // (512 * mib))
    return min(available_cpus(), memory_cap)


def check_parent():
    """Do not fork from a threaded process or with unexpected open descriptors."""
    require(sys.platform == "linux" and hasattr(os, "fork") and hasattr(os, "waitid"), "linux_fork_required")
    require(threading.active_count() == 1 and len(list(Path("/proc/self/task").iterdir())) == 1,
            "parent_not_single_threaded")
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd <= 2:
            continue
        try:
            os.fstat(fd)
        except OSError:
            continue  # transient descriptor used by listdir itself
        raise RunnerError("unexpected_parent_descriptor:" + name)
    for line in Path("/proc/locks").read_text().splitlines():
        fields = line.split()
        # Linux lock records can have an extra '->' field for blocked requests.
        if len(fields) > 4:
            index = 5 if fields[1] == "->" else 4
            if len(fields) > index and fields[index] == str(os.getpid()):
                raise RunnerError("parent_file_lock")


def checked_inventory(tasks):
    names = [name for name, _ in tasks]
    require(all(isinstance(name, str) and TASK_ID.fullmatch(name) for name in names), "invalid_task_id")
    require(len(names) == len(set(names)), "duplicate_task_id")
    require(all(callable(fn) for _, fn in tasks), "invalid_task_callable")
    return names


def check_results(expected, results):
    """Exact inventory: missing/duplicate/unknown results cannot pass."""
    observed = [item["id"] for item in results]
    require(len(observed) == len(set(observed)), "duplicate_result_id")
    require(set(observed) == set(expected), "result_inventory_mismatch")
    require(len(observed) == len(expected), "result_count_mismatch")
    return {item["id"]: item["value"] for item in results}


def process_group_members(group):
    members = set()
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            # comm can contain spaces and parentheses; parse after the final ')'.
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group:
                members.add(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            continue  # an unrelated process may exit while /proc is traversed
        except PermissionError as exc:
            raise RunnerError("process_group_unobservable") from exc
    return members


def direct_children():
    # Some kernels omit task/children (CONFIG_CHECKPOINT_RESTORE). Read PPid
    # from /proc/<pid>/stat instead; unreadable process metadata fails closed.
    pid = os.getpid()
    children = set()
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[1]) == pid:
                children.add(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as exc:
            raise RunnerError("child_inventory_unobservable") from exc
    return children


@contextlib.contextmanager
def child_subreaper():
    """Adopt orphaned descendants so cleanup does not depend on PID 1 reaping.

    The runner must own every child process while the batch is active. A descendant
    leaving its task group is still an error, even when we can reclaim it.
    """
    require(not direct_children(), "unexpected_existing_child")
    libc = ctypes.CDLL(None, use_errno=True)
    old = ctypes.c_int()
    require(libc.prctl(37, ctypes.byref(old), 0, 0, 0) == 0, "subreaper_query_failed")
    require(libc.prctl(36, 1, 0, 0, 0) == 0, "subreaper_enable_failed")
    try:
        yield
    finally:
        require(libc.prctl(36, old.value, 0, 0, 0) == 0, "subreaper_restore_failed")


def reclaim_adopted(known, deadline):
    """Only signal/reap direct children we own; no signal to reused PID/group IDs."""
    found = False
    while True:
        adopted = direct_children() - set(known)
        if not adopted:
            return found
        found = True
        for pid in adopted:
            try:
                kill_owned(pid)
                status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG)
                # waitid consumes the PID only when it reports a termination.
                if status is not None:
                    continue
            except (ChildProcessError, ProcessLookupError):
                continue
        require(time.monotonic() < deadline, "adopted_child_cleanup_timeout")
        time.sleep(0.01)


def exited(pid):
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def kill_owned(pid):
    """PID is our unreaped child: do not signal any group after reaping it."""
    try:
        group = os.getpgid(pid)
        if group == pid:
            os.killpg(group, signal.SIGKILL)
        else:
            # setsid may not yet have completed. Never kill the parent's group.
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def reap(pid, deadline):
    while not exited(pid):
        if time.monotonic() >= deadline:
            raise RunnerError("child_reap_timeout")
        time.sleep(0.01)
    # Keep the leader unreaped until the process group is inspected/terminated.
    try:
        group = os.getpgid(pid)
    except ProcessLookupError:
        group = None
    residual = set()
    if group == pid:
        residual = process_group_members(pid) - {pid}
        if residual:
            kill_owned(pid)
    _, status = os.waitpid(pid, 0)
    # No further signal may target this PID or group after waitpid.
    return group, residual, status


def validate_exit(pid, outcome):
    group, residual, status = outcome
    require(not residual, "residual_process_group")
    require(group == pid, "child_group_not_established")
    require(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, "child_nonzero_exit")


def private_environment(home, tmp):
    runtime = home / ".runtime"
    runtime.mkdir(mode=0o700)
    os.environ.update(HOME=str(home), TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp),
                      XDG_CACHE_HOME=str(home / ".cache"), XDG_CONFIG_HOME=str(home / ".config"),
                      XDG_DATA_HOME=str(home / ".local/share"), XDG_STATE_HOME=str(home / ".local/state"),
                      XDG_RUNTIME_DIR=str(runtime), HELM_CACHE_HOME=str(home / ".cache/helm"),
                      HELM_CONFIG_HOME=str(home / ".config/helm"), HELM_DATA_HOME=str(home / ".local/share/helm"),
                      HELM_REGISTRY_CONFIG=str(home / ".config/helm/registry/config.json"),
                      HELM_REPOSITORY_CACHE=str(home / ".cache/helm/repository"),
                      HELM_REPOSITORY_CONFIG=str(home / ".config/helm/repositories.yaml"),
                      HELM_PLUGINS=str(home / ".local/share/helm/plugins"),
                      KUBECONFIG="/dev/null", PYTHONDONTWRITEBYTECODE="1")
    tempfile.tempdir = None


# Failure diagnostics contain only code locations and fixed categories. Never
# replay the captured worker output, exception messages, source text or locals.
_DIAGNOSTIC_PATH = None
MAX_DIAGNOSTIC_BYTES = 64 * 1024
_DIAGNOSTIC_KINDS = {"test_failure", "test_error", "subtest_failure", "expected_failure",
                     "worker_exception", "mutation_crash"}
_DIAGNOSTIC_TYPES = {"AssertionError", "RunnerError", "ReceiptError", "TransportError",
                     "GateError", "ApplyStop", "DestroyStop", "AdapterError", "TimeoutError",
                     "RuntimeError", "ValueError", "TypeError", "KeyError", "AttributeError",
                     "ImportError", "ModuleNotFoundError", "SyntaxError", "OSError",
                     "FileNotFoundError", "PermissionError", "SystemExit", "KeyboardInterrupt"}
_DIAGNOSTIC_FILE = re.compile(r"(?:scripts/(?:ci|local-workflow)|kubernetes/(?:tools|tests))/[A-Za-z0-9_/-]+\.py\Z")
_DIAGNOSTIC_FUNCTION = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]{0,95}|<module>|<lambda>|<external>)\Z")


def diagnostic_frame(trace):
    code = trace.tb_frame.f_code
    # Accept repository-relative source locations only; never expose temporary,
    # HOME or interpreter installation paths. External frames remain identifiable
    # by their position in the trace, without their filenames or function names.
    repo = Path(__file__).resolve().parents[2]
    try:
        relative = Path(code.co_filename).resolve().relative_to(repo).as_posix()
    except (ValueError, OSError):
        relative = "<external>"
    if not _DIAGNOSTIC_FILE.fullmatch(relative):
        return ["<external>", trace.tb_lineno, "<external>"]
    function = code.co_name if _DIAGNOSTIC_FUNCTION.fullmatch(code.co_name) else "<external>"
    return [relative, trace.tb_lineno, function]


def exception_diagnostic(kind, err):
    exc_type, _, trace = err
    frames = []
    while trace is not None:
        frames.append(diagnostic_frame(trace))
        trace = trace.tb_next
    return {"kind": kind, "exception": exc_type.__name__ if exc_type.__name__ in _DIAGNOSTIC_TYPES else "OtherException",
            "frames": frames[-32:]}


def validate_diagnostic(item):
    require(type(item) is dict and set(item) == {"kind", "exception", "frames"}, "diagnostic_shape")
    require(type(item["kind"]) is str and item["kind"] in _DIAGNOSTIC_KINDS
            and type(item["exception"]) is str and item["exception"] in _DIAGNOSTIC_TYPES | {"OtherException"},
            "diagnostic_category")
    frames = item["frames"]
    require(type(frames) is list and len(frames) <= 32, "diagnostic_frame_count")
    for frame in frames:
        require(type(frame) is list and len(frame) == 3, "diagnostic_frame_shape")
        file, line, function = frame
        require(type(file) is str and len(file) <= 200 and
                (file == "<external>" or _DIAGNOSTIC_FILE.fullmatch(file)) and
                type(line) is int and 0 < line <= 1000000 and type(function) is str and
                _DIAGNOSTIC_FUNCTION.fullmatch(function) and
                (file != "<external>" or function == "<external>"), "diagnostic_frame_invalid")
    return item


def emit_diagnostic(task, item):
    require(type(task) is str and TASK_ID.fullmatch(task), "diagnostic_task_id")
    validate_diagnostic(item)
    print("Runtime failure diagnostic: " + json.dumps({"task": task, **item}, sort_keys=True), file=sys.stderr, flush=True)


def report_exception(kind, err, task=None):
    item = validate_diagnostic(exception_diagnostic(kind, err))
    if _DIAGNOSTIC_PATH is None:
        emit_diagnostic(task or "coordinator", item)
        return
    data = (json.dumps(item, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(_DIAGNOSTIC_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        require(os.fstat(fd).st_size + len(data) <= MAX_DIAGNOSTIC_BYTES, "diagnostic_too_large")
        require(os.write(fd, data) == len(data), "diagnostic_write_incomplete")
    finally:
        os.close(fd)


def emit_child_diagnostics(directory, task):
    path = directory / "diagnostics"
    if not os.path.lexists(path):
        return
    require(path.is_file() and not path.is_symlink(), "diagnostic_file_unsafe")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        data = handle.read(MAX_DIAGNOSTIC_BYTES + 1)
    require(len(data) <= MAX_DIAGNOSTIC_BYTES, "diagnostic_too_large")
    for line in data.splitlines():
        try:
            item = strict_json(line.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise RunnerError("malformed_diagnostic") from None
        emit_diagnostic(task, item)


def child_entry(name, fn, directory):
    global _DIAGNOSTIC_PATH
    _DIAGNOSTIC_PATH = directory / "diagnostics"
    try:
        os.setsid()
        os.umask(0o077)
        home, tmp = directory / "home", directory / "tmp"
        home.mkdir(mode=0o700)
        tmp.mkdir(mode=0o700)
        private_environment(home, tmp)
        sys.dont_write_bytecode = True
        # Capture both Python and inherited subprocess streams in a private file.
        fd = os.open(directory / "output", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.dup2(fd, 1)
            os.dup2(fd, 2)
        finally:
            os.close(fd)
        value = fn()
        sys.stdout.flush()
        sys.stderr.flush()
        data = json.dumps({"id": name, "value": value}, allow_nan=False, separators=(",", ":")).encode("utf-8")
        require(len(data) <= MAX_RESULT_BYTES, "result_too_large")
        with (directory / "result").open("xb") as output:
            output.write(data)
        os._exit(0)
    except BaseException:
        # A crash, even after writing a result, is never an accepted verdict.
        # Diagnostic failures cannot change the nonzero exit or leak raw output.
        try:
            report_exception("worker_exception", sys.exc_info())
        finally:
            os._exit(1)


def read_result(directory, expected):
    path = directory / "result"
    require(path.is_file() and not path.is_symlink(), "missing_or_unsafe_result")
    require(path.stat().st_size <= MAX_RESULT_BYTES, "result_too_large")
    try:
        with path.open("rb") as handle:
            def pairs(items):
                values = dict(items)
                require(len(values) == len(items), "duplicate_result_field")
                return values
            item = json.load(handle, object_pairs_hook=pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(RunnerError("nonfinite_result")))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RunnerError("malformed_result") from exc
    require(type(item) is dict and set(item) == {"id", "value"}, "malformed_result_fields")
    require(item["id"] == expected, "unexpected_result_id")
    return item


STOP_SIGNALS = {signal.SIGINT, signal.SIGTERM}


@contextlib.contextmanager
def blocked_stop_signals():
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
    try:
        yield previous
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextlib.contextmanager
def managed_signals():
    previous = {sig: signal.getsignal(sig) for sig in STOP_SIGNALS}
    def stop(signum, _frame):
        raise RunnerError("interrupted:" + str(signum))
    try:
        for sig in STOP_SIGNALS:
            signal.signal(sig, stop)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def clean_exec(argv):
    """Run argv in a fresh process that holds only stdin, stdout and stderr.

    A CI host can leave a non-close-on-exec descriptor open in the step shell. It is
    closed in the new child only (close_fds); this process's descriptors are left
    alone, and the coordinator's strict check_parent() guard still applies inside.
    SIGINT/SIGTERM are forwarded. Returns the child's returncode (negative: signal).
    """
    require(type(argv) is list and argv and all(type(arg) is str for arg in argv), "clean_exec_argv")
    sys.stdout.flush()
    sys.stderr.flush()
    holder, pending = [None], []
    previous = {sig: signal.getsignal(sig) for sig in STOP_SIGNALS}
    def forward(signum, _frame):
        if holder[0] is None:
            pending.append(signum)  # forwarded as soon as the child exists
        else:
            holder[0].send_signal(signum)
    try:
        for sig in STOP_SIGNALS:
            signal.signal(sig, forward)
        try:
            process = subprocess.Popen(argv, close_fds=True)
        except OSError:
            raise RunnerError("clean_exec_failed") from None
        holder[0] = process
        while pending:
            process.send_signal(pending.pop(0))
        return process.wait()
    finally:
        if holder[0] is not None and holder[0].poll() is None:
            holder[0].kill()  # never leave the child behind on an unexpected exit
            holder[0].wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def exit_status(returncode):
    """This process's status for a child's returncode: the same code or signal.

    SIGKILL can be neither handled nor blocked. Any other terminating signal gets its
    default action and is unblocked, so a mask inherited by this launcher cannot turn
    the child's signal into an ordinary exit code. If the signal still does not end
    this process, the result is a nonzero 128 + signum, never success.
    """
    if returncode >= 0:
        return returncode
    signum = -returncode
    if signum != signal.SIGKILL:
        signal.signal(signum, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signum})
    os.kill(os.getpid(), signum)
    return 128 + signum


def run_tasks(tasks, workers, *, task_timeout=300, deadline=None):
    """Run a bounded batch, each callable once in a new child. No worker reuse."""
    tasks = list(tasks)
    expected = checked_inventory(tasks)
    require(type(workers) is int and 1 <= workers <= available_workers(), "worker_limit")
    require(type(task_timeout) in (int, float) and 0 < task_timeout <= 300, "invalid_task_timeout")
    deadline = time.monotonic() + 2100 if deadline is None else deadline
    require(deadline > time.monotonic(), "global_deadline")
    check_parent()
    results, active = [], {}
    with managed_signals(), child_subreaper(), tempfile.TemporaryDirectory(prefix="runtime-fork-") as scratch:
        root = Path(scratch)
        cursor = 0
        try:
            while cursor < len(tasks) or active:
                now = time.monotonic()
                require(now < deadline, "global_deadline")
                while cursor < len(tasks) and len(active) < workers:
                    check_parent()
                    name, fn = tasks[cursor]
                    directory = root / str(cursor)
                    directory.mkdir(mode=0o700)
                    # Flush buffered output before fork; child uses os._exit.
                    sys.stdout.flush()
                    sys.stderr.flush()
                    with blocked_stop_signals() as mask:
                        pid = os.fork()
                        if pid == 0:
                            for sig in STOP_SIGNALS:
                                signal.signal(sig, signal.SIG_DFL)
                            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                            child_entry(name, fn, directory)
                            os._exit(1)
                        active[pid] = (name, directory, time.monotonic())
                        cursor += 1
                progress = False
                for pid, (name, directory, started) in list(active.items()):
                    if time.monotonic() - started >= task_timeout:
                        raise RunnerError("task_timeout:" + name)
                    if exited(pid):
                        with blocked_stop_signals():
                            outcome = reap(pid, min(deadline, time.monotonic() + 5))
                            active.pop(pid)  # the PID is now consumed; never signal it again
                        adopted = reclaim_adopted(active, time.monotonic() + 5)
                        # Reap/cleanup checks stay authoritative; diagnostics are
                        # separate from successful JSONL evidence and never a PASS.
                        emit_child_diagnostics(directory, name)
                        try:
                            validate_exit(pid, outcome)
                            require(not adopted, "unexpected_adopted_child")
                            results.append(read_result(directory, name))
                        except RunnerError:
                            print("Runtime failed task: " + name, file=sys.stderr, flush=True)
                            raise
                        shutil.rmtree(directory)
                        progress = True
                if not progress and active:
                    time.sleep(0.01)
        finally:
            with blocked_stop_signals():
                cleanup_errors = []
                # Stop every live task before reaping any, so cleanup is bounded by the
                # slowest group rather than multiplying the timeout by worker count.
                for pid in list(active):
                    try:
                        kill_owned(pid)
                    except OSError:
                        cleanup_errors.append("child_signal_os_error")
                cleanup_deadline = time.monotonic() + 5
                for pid in list(active):
                    try:
                        reap(pid, cleanup_deadline)
                        active.pop(pid)
                    except (RunnerError, OSError) as exc:
                        cleanup_errors.append(type(exc).__name__)
                try:
                    reclaim_adopted(active, cleanup_deadline)
                except (RunnerError, OSError) as exc:
                    cleanup_errors.append(type(exc).__name__)
                require(not active and not direct_children() and not cleanup_errors, "process_cleanup_failed")
    return check_results(expected, results)

# The mapping is reviewed against the base's direct normal-code Scenario calls.
# Each line is a TestCase ID (module prefix supplied below) followed by scenarios.
DESTROY_BASELINES = """
DestroyEngineTests.test_reverse_order_with_dependency_safety destroy_order
DestroyEngineTests.test_partial_apply_cleanup_judges_never_created_objects_one_by_one partial_apply owned_absent
DestroyReceiptTests.test_missing_corrupt_other_fingerprint_and_unpinned_inputs_stop receipt_preflight
DestroyReceiptTests.test_unresolved_apply_intent_and_quarantine_stop_before_any_write open_apply_intent quarantine_preflight
DestroyReceiptTests.test_foreign_object_and_uid_mismatch_are_never_deleted foreign_object uid_mismatch
DestroyReceiptTests.test_d13_field_ownership_is_required d13_ownership
DestroyReceiptTests.test_crd_creation_evidence_and_foreign_crd_are_not_crd_not_created crd_creation_evidence crd_discovery
DestroyOrderingTests.test_target_group_binding_finalizer_wait_and_timeout tgb_finalizer
DestroyOrderingTests.test_foreign_or_remaining_target_group_binding_stops foreign_tgb
DestroyOrderingTests.test_load_balancer_and_unknown_services_stop_admission ingress_services
DestroyOrderingTests.test_istio_custom_resources_stop_webhook_deletion istio_instances
DestroyInventoryTests.test_unknown_objects_and_secrets_stop_namespace_deletion unknown_objects istiod_leftover
DestroyInventoryTests.test_g9_receipt_and_cleanup_gate_namespaces g9_receipt g9_incomplete
DestroyInventoryTests.test_owned_children_and_owner_chains owned_children owner_chain
DestroyInventoryTests.test_objects_added_after_the_inventory_stop_the_namespace_delete inventory_race
DestroyInventoryTests.test_incomplete_or_forbidden_inventory_is_never_empty inventory_failures
DestroyInventoryTests.test_namespace_uid_and_termination_bounds namespace_uid
DestroyCrdTests.test_retained_crd_verification_and_instance_counts crd_safety
DestroyRecoveryTests.test_crash_before_and_after_delete_and_after_result crash_before_delete crash_after_delete
DestroyRecoveryTests.test_delete_responses_are_never_completion delete_responses
DestroyRecoveryTests.test_recreated_objects_are_quarantined_and_completed_steps_revalidated recreated
DestroyRecoveryTests.test_global_deadline_and_g9_bounds deadline bounded_server
DestroyRecoveryTests.test_real_transport_clock_and_cli_are_refused real_refused
DestroyRecoveryTests.test_completion_rechecks_objects_secrets_and_kube_system final_checks
DestroyRecoveryTests.test_local_wait_deadlines_are_strict local_wait local_wait_unit
DestroyReviewTests.test_f01_reviewed_stage_identity_and_order stage_identity
DestroyReviewTests.test_f02_existing_receipt_only_and_locked_revalidation existing_receipt_only store_existing_only
DestroyReviewTests.test_f03_g9_registration_and_fingerprint_binding g9_eligibility fingerprint_binding
DestroyReviewTests.test_f04_cluster_wide_target_group_binding_and_fresh_dependencies tgb_cluster_wide
DestroyReviewTests.test_f04_service_identity_istio_midstage_and_completed_stage service_identity istio_midstage
DestroyReviewTests.test_f05_exact_crd_discovery_mapping crd_mapping stale_discovery
DestroyReviewTests.test_f06_namespace_final_gate_and_current_owner_chain namespace_final_gate owner_chain_current
DestroyReviewTests.test_f03_residual_locked_registration_and_per_secret_fingerprint g9_locked_binding stage_fingerprint
DestroyReviewTests.test_f04_residual_exact_tgb_and_admission_binding exact_tgb_binding
DestroyReviewTests.test_f05_residual_crd_kind_and_listable crd_kind_listable
DestroyReviewTests.test_f06_atomic_namespace_races namespace_atomic_races
DestroyReviewTests.test_f06_atomic_namespace_transport_boundary namespace_atomic_boundary
"""
APPLY_BASELINES = """
EngineTests.test_success_ends_applied_with_deferred success_is_deferred deferred_never_pass
EngineTests.test_rerun_reverifies_without_writes status_manager_allowed
EngineTests.test_pins_bundle_and_objects pins bundle_changed objects_match_plan
EngineTests.test_fingerprint fingerprint
EngineTests.test_gates_and_plan_order gates plan_order
EngineTests.test_crash_recovery crash_before_apply crash_after_apply
EngineTests.test_uid_change_and_foreign_ownership uid_changed foreign_owner
EngineTests.test_conflict_never_forced conflict
EngineTests.test_namespace_must_be_active namespace_inactive
EngineTests.test_uid_race_before_write uid_changed_live_only
EngineTests.test_ownership_proven_before_success_result foreign_field_during_apply runtime_fields_short_after_apply
EngineTests.test_landed_write_never_reverts_to_not_applied uid_changed_after_apply
EngineTests.test_status_update_allowed_at_write status_update_allowed
EngineTests.test_write_refused_missing_managed_fields write_refused_missing_managed_fields
EngineTests.test_write_refused_missing_runtime_entry write_refused_missing_runtime_entry
EngineTests.test_write_refused_partial_runtime_ownership write_refused_partial_runtime
EngineTests.test_write_refused_malformed_ownership write_refused_malformed
EngineTests.test_through_istiod_is_deferred through_istiod
EngineTests.test_secret_preconditions secret_presence secret_metadata_only secret_registration
EngineTests.test_registry_preconditions registry_evidence registry_digests bundle_image_locked
EngineTests.test_node_and_ca_preconditions nodes bundle_ca dry_run_side_effects
EngineTests.test_workload_readiness deployment_readiness deployment_bound cabundle_population
EngineTests.test_digest_classification digests
EngineTests.test_workload_ownership irsa_annotation controller_webhook_owned
EngineTests.test_section10_rows section10
EngineTests.test_section10_malformed_evidence section10_malformed
EngineTests.test_section10_races_and_reruns istio_webhooks_at_readiness
EngineTests.test_fake_probes probes
EngineTests.test_gateway_unreachable gateway_unreachable
EngineTests.test_gateway_pre_apply gateway_pre_apply
EngineTests.test_gateway_contract gateway_contract
EngineTests.test_mesh_gate mesh_gate
EngineTests.test_mesh_contract mesh_contract
EngineTests.test_admission_pre_apply admission_pre_apply
EngineTests.test_admission_contract admission_contract
EngineTests.test_admission_probes admission_probes
EngineTests.test_binding_writer_pre_apply binding_writer_pre_apply
EngineTests.test_binding_writer_contract binding_writer_contract
EngineTests.test_workload_read_scope workload_read_scope runtime_cabundle_claim
EngineTests.test_stage_order stage_order
EngineTests.test_crd_and_api_timeouts crd_timeout api_timeout
EngineTests.test_c1_protection c1
EngineTests.test_dry_run_and_classification dry_run classify
EngineTests.test_d13_allowlist d13
EngineTests.test_incomplete_ownership_rejected_consistent_and_reapply incomplete_ownership_consistent incomplete_ownership_reapply
EngineTests.test_foreign_object_never_modified foreign_appears_before_apply replaced_before_write update_uid_mismatch
EngineTests.test_conditional_writes owned_update_succeeds write_needs_precondition
EngineTests.test_deferred_needs_evidence deferred_needs_evidence
EngineTests.test_adapter_boundary_and_cli adapter_boundary
"""
DESTROY_INLINE = {
    "certs_secret_blocks": "scenario_namespace_certs_secret",
    "runtime_object_class": "scenario_namespace_runtime_object",
    "namespace_d13": "scenario_namespace_d13",
}
APPLY_INLINE = {
    "fake_ownership_check": "scenario_write_time_ownership",
    "fake_runtime_entry_skipped": "scenario_write_refused_runtime_lost",
}


def baseline_map(module, table, mutations, inline, test_ids):
    mapping = {}
    for row in table.strip().splitlines():
        test, *names = row.split()
        full = module.__name__ + "." + test
        require(full in test_ids, "baseline_test_unknown:" + full)
        for name in names:
            scenario = "scenario_" + name
            require(scenario not in mapping, "duplicate_baseline_scenario")
            mapping[scenario] = full
    scenarios = {item[-1].__name__ for item in mutations}
    require(not set(mapping) & set(inline) and set(mapping) | set(inline) == scenarios,
            "baseline_inventory_mismatch")
    return mapping


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def ensure_independent_case(case):
    cls = type(case)
    module = sys.modules[cls.__module__]
    for hook in ("setUpModule", "tearDownModule", "load_tests"):
        require(not hasattr(module, hook), "module_fixture_unsupported:" + hook)
    for hook in ("setUpClass", "tearDownClass"):
        require(getattr(cls, hook).__func__ is getattr(unittest.TestCase, hook).__func__,
                "class_fixture_unsupported:" + hook)
    require(not getattr(cls, "_class_cleanups", ()), "class_cleanup_unsupported")
    require(not getattr(unittest.case, "_module_cleanups", ()), "module_cleanup_unsupported")


class ObservedResult(unittest.TestResult):
    """Keep the actual unittest lifecycle; report only IDs/categories, not payloads."""
    def __init__(self):
        super().__init__()
        self.started = []
        self.stopped = []
        self.succeeded = []
        self.subtest_failures = []

    def startTest(self, test):
        super().startTest(test)
        self.started.append(test.id())

    def stopTest(self, test):
        super().stopTest(test)
        self.stopped.append(test.id())

    def addSuccess(self, test):
        super().addSuccess(test)
        self.succeeded.append(test.id())

    def addFailure(self, test, err):
        super().addFailure(test, err)
        report_exception("test_failure", err, test.id())

    def addError(self, test, err):
        super().addError(test, err)
        report_exception("test_error", err, test.id())

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        report_exception("expected_failure", err, test.id())

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.subtest_failures.append(test.id())
            report_exception("subtest_failure", err, test.id())

    def evidence(self):
        return {"testsRun": self.testsRun, "started": self.started, "stopped": self.stopped,
                "successes": self.succeeded, "successful": self.wasSuccessful(),
                "failures": [test.id() for test, _ in self.failures],
                "errors": [test.id() for test, _ in self.errors],
                "skips": [test.id() for test, _ in self.skipped],
                "expectedFailures": [test.id() for test, _ in self.expectedFailures],
                "unexpectedSuccesses": [test.id() for test in self.unexpectedSuccesses],
                "subtestFailures": self.subtest_failures}


def verify_case_result(test_id, value, witnesses):
    require(type(value) is dict and set(value) == {"result", "baselines"}, "test_result_shape")
    result = value["result"]
    expected = {"testsRun": 1, "started": [test_id], "stopped": [test_id], "successes": [test_id],
                "successful": True, "failures": [], "errors": [], "skips": [],
                "expectedFailures": [], "unexpectedSuccesses": [], "subtestFailures": []}
    require(type(result) is dict and result.keys() == expected.keys()
            and all(type(result[key]) is type(expected[key]) for key in expected)
            and result == expected, "test_not_passed:" + test_id)
    require(value["baselines"] == sorted(witnesses), "baseline_witness_mismatch:" + test_id)
    return result



def record_result(parent, value):
    """Reconstruct the actual result categories; no per-Mutation Test counts."""
    result = value["result"]
    require(type(result.get("testsRun")) is int and result["testsRun"] == 1, "invalid_test_count")
    parent.testsRun += result["testsRun"]
    for category, attr in (("failures", "failures"), ("errors", "errors"), ("skips", "skipped"),
                           ("expectedFailures", "expectedFailures")):
        require(type(result.get(category)) is list and all(type(i) is str for i in result[category]),
                "invalid_test_result_category")
        getattr(parent, attr).extend((test_id, "child " + category) for test_id in result[category])
    for category in ("unexpectedSuccesses", "subtestFailures"):
        require(type(result.get(category)) is list and all(type(i) is str for i in result[category]),
                "invalid_test_result_category")
    parent.unexpectedSuccesses.extend(result["unexpectedSuccesses"])
    parent.subtest_failures.extend(result["subtestFailures"])


def execute_case(case, module=None, scenarios=()):
    """Record completed direct normal-code calls, not merely a Test name's PASS."""
    observed = []
    with contextlib.ExitStack() as stack:
        for name in scenarios:
            original = getattr(module, name)
            def witness(test, mods, *, original=original, name=name):
                real = module.real_mods()
                require(test is case and vars(mods) == vars(real), "baseline_not_normal_code:" + name)
                value = original(test, mods)
                observed.append(name)
                return value
            stack.enter_context(mock.patch.object(module, name, witness))
        result = ObservedResult()
        unittest.TestSuite([case]).run(result)
    return {"result": result.evidence(), "baselines": sorted(observed)}


def verify_mutation_result(name, value, expected_inline):
    require(type(value) is dict and set(value) == {"verdict", "inline_baseline"}, "mutation_result_shape")
    if value["verdict"] != "detected" and TASK_ID.fullmatch(name):
        # The verdict is a fixed category, never a worker-provided message.
        verdict = value["verdict"] if value["verdict"] in ("crashed", "undetected") else "invalid"
        print("Runtime mutation failed: " + name + " (" + verdict + ")", file=sys.stderr, flush=True)
    require(value["verdict"] == "detected", "mutation_not_detected:" + name)
    require(type(value["inline_baseline"]) is bool and value["inline_baseline"] == expected_inline,
            "mutation_baseline_mismatch:" + name)


def cache_fingerprint(cache):
    return hashlib.sha256(json.dumps(cache, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def guarded_call(callback, cache, fingerprint):
    if cache is None:
        return callback()
    require(cache_fingerprint(cache) == fingerprint, "cache_changed_before_task")
    try:
        return callback()
    finally:
        require(cache_fingerprint(cache) == fingerprint, "cache_changed_after_task")


def mutation_dispatch(case, items, execute, workers, deadline, module, mapping, inline, witnessed,
                      cache=None, fingerprint=None):
    tasks = []
    expected = {}
    for item in items:
        name, *_, scenario = item
        is_inline = scenario.__name__ in inline
        if not is_inline:
            require((mapping[scenario.__name__], scenario.__name__) in witnessed,
                    "mutation_baseline_unproven:" + name)
        expected[name] = is_inline
        def run_mutation(item=item):
            # The child alone owns this TestCase copy. Keep diagnostics out of
            # the original verdict and out of the successful comparison payload.
            case._runtime_diagnostic = lambda err: report_exception("mutation_crash", err)
            return guarded_call(lambda: execute(case, item), cache, fingerprint)
        tasks.append((name, run_mutation))
    results = run_tasks(tasks, workers, deadline=deadline)
    require(set(results) == set(expected), "mutation_result_inventory")
    for name, value in results.items():
        verify_mutation_result(name, value, expected[name])
    # The aggregate TestCase receives actual per-ID outcomes and checks its own inventory.
    return results


def run_runtime_suite(suite_module, mutation_module, mutations, table, inline, aggregate_class,
                      workers, deadline, expected, *, cache=None, fingerprint=None):
    cases = list(flatten(unittest.defaultTestLoader.loadTestsFromModule(suite_module)))
    ids = [case.id() for case in cases]
    require(len(ids) == expected["tests"] and len(ids) == len(set(ids)), "test_inventory_mismatch")
    names = [item[0] for item in mutations]
    require(len(names) == len(set(names)), "duplicate_mutation_id")
    require(len(suite_module.MUTATIONS) == expected["mutations"], "mutation_count_mismatch")
    # Preserve group-qualified IDs because different groups may use the same name.
    groups = ({"runtime": suite_module.RUNTIME_MUTATIONS, "secret": suite_module.SECRET_MUTATIONS,
               "foundation": suite_module.DESTROY_MUTATIONS, "engine": mutations}
              if suite_module is not mutation_module else {"apply": mutations})
    definitions = [(group, item[0]) for group, items in groups.items() for item in items]
    require(len(definitions) == expected["mutations"] and len(definitions) == len(set(definitions))
            and list(suite_module.MUTATIONS) == [item for items in groups.values() for item in items],
            "mutation_definition_inventory")
    for case in cases:
        ensure_independent_case(case)
    aggregates = [case for case in cases if type(case) is aggregate_class]
    require(len(aggregates) == 1, "aggregate_test_inventory")
    aggregate = aggregates[0]
    ordinary = [case for case in cases if case is not aggregate]
    mapping = baseline_map(mutation_module, table, mutations, inline, {case.id() for case in ordinary})
    by_test = {case.id(): [] for case in ordinary}
    for scenario, test in mapping.items():
        by_test[test].append(scenario)
    # Imported fast mutation groups keep their original internal loops. They run as
    # actual TestCases, not as synthetic increments of testsRun.
    tasks = [(case.id(), lambda case=case: guarded_call(
        lambda: execute_case(case, mutation_module, by_test[case.id()]), cache, fingerprint)) for case in ordinary]
    # Run normal cases before the unchanged small mutation aggregates. Their
    # internal loops remain serial and each is still one real TestCase.
    fast_aggregates = set()
    if suite_module is not mutation_module:
        fast_classes = {suite_module.MutationTests, suite_module.SecretMutationTests, suite_module.DestroyMutationTests}
        fast_aggregates = {case.id() for case in ordinary if type(case) in fast_classes}
        require(len(fast_aggregates) == len(fast_classes), "serial_aggregate_inventory")
    values = run_tasks([task for task in tasks if task[0] not in fast_aggregates], workers, deadline=deadline)
    if fast_aggregates:
        values.update(run_tasks([task for task in tasks if task[0] in fast_aggregates], workers, deadline=deadline))
    require(set(values) == set(by_test), "ordinary_test_inventory")
    witnessed = set()
    result = ObservedResult()
    for test_id, value in values.items():
        record_result(result, value)
        verify_case_result(test_id, value, by_test[test_id])
        witnessed.update((test_id, scenario) for scenario in value["baselines"])
    mutation_results = {}
    def dispatch(test, items, execute):
        require(test is aggregate and items is mutations and not mutation_results, "aggregate_dispatch_mismatch")
        mutation_results.update(mutation_dispatch(test, items, execute, workers, deadline,
                                                  mutation_module, mapping, inline, witnessed, cache, fingerprint))
        return mutation_results
    aggregate._runtime_dispatch = dispatch
    final = execute_case(aggregate)
    record_result(result, final)
    verify_case_result(aggregate.id(), final, [])
    require(set(mutation_results) == set(names), "aggregate_mutation_inventory")
    require(result.wasSuccessful() and not result.skipped and not result.expectedFailures
            and not result.subtest_failures and result.testsRun == expected["tests"],
            "suite_not_passed")
    if cache is not None:
        require(cache_fingerprint(cache) == fingerprint, "parent_cache_changed")
    print(json.dumps({"suite": suite_module.__name__, "tests": sorted(ids),
                      "baseline_witnesses": sorted([list(pair) for pair in witnessed]),
                      "parallel_mutations": mutation_results, "testsRun": result.testsRun,
                      "mutation_definitions": sorted([list(pair) for pair in definitions]), "status": "passed"}, sort_keys=True), flush=True)
    return result.testsRun


@contextlib.contextmanager
def isolated_parent():
    """All cache preparation occurs in a disposable HOME, not the operator's HOME."""
    old_tmp = tempfile.tempdir
    old_env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="runtime-parent-") as directory:
        root = Path(directory)
        home, tmp = root / "home", root / "tmp"
        home.mkdir(mode=0o700)
        tmp.mkdir(mode=0o700)
        try:
            private_environment(home, tmp)
            yield
        finally:
            tempfile.tempdir = old_tmp
            os.environ.clear()
            os.environ.update(old_env)


def strict_json(text):
    def pairs(items):
        values = dict(items)
        require(len(values) == len(items), "duplicate_evidence_field")
        return values
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(RunnerError("nonfinite_evidence")))


def verify_suite_evidence(item, module_name, expected, table, group, inline):
    fields = {"suite", "tests", "baseline_witnesses", "parallel_mutations", "testsRun", "mutation_definitions", "status"}
    require(type(item) is dict and set(item) == fields and item["suite"] == module_name,
            "evidence_suite_shape")
    tests = item["tests"]
    require(item["status"] == "passed" and type(item["testsRun"]) is int
            and item["testsRun"] == expected["tests"] and type(tests) is list
            and all(type(test) is str and TASK_ID.fullmatch(test) for test in tests)
            and len(tests) == len(set(tests)) == expected["tests"], "evidence_not_passed")
    definitions = item["mutation_definitions"]
    allowed_groups = {"runtime", "secret", "foundation", "engine"} if group == "engine" else {"apply"}
    require(type(definitions) is list and all(type(pair) is list and len(pair) == 2
                and pair[0] in allowed_groups and type(pair[1]) is str and TASK_ID.fullmatch(pair[1])
                for pair in definitions), "evidence_definition_shape")
    require(len(definitions) == len({tuple(pair) for pair in definitions}) == expected["mutations"]
            and {pair[0] for pair in definitions} == allowed_groups, "evidence_definition_inventory")
    ids = {pair[1] for pair in definitions if pair[0] == group}
    mutations = item["parallel_mutations"]
    require(type(mutations) is dict and set(mutations) == ids and set(inline) <= ids, "evidence_mutation_inventory")
    for name, value in mutations.items():
        verify_mutation_result(name, value, name in inline)
    # The reviewed table identifies actual TestCase/Scenario pairs. Receipt's engine
    # tests live in the imported destroy module, not in the receipt module itself.
    prefix = "test_k8s_runtime_destroy" if group == "engine" else module_name
    witnesses = sorted([prefix + "." + test, "scenario_" + name]
                       for row in table.strip().splitlines() for test, *names in [row.split()] for name in names)
    require(item["baseline_witnesses"] == witnesses and all(pair[0] in tests for pair in witnesses),
            "evidence_baseline_inventory")


def read_evidence(path, *, receipt_expected=None, apply_expected=None):
    """Accept complete candidate logs against reviewed counts, not a printed PASS line."""
    from expected_counts import load
    if receipt_expected is None:
        receipt_expected = load("k8s_runtime_receipt_tests")
    if apply_expected is None:
        apply_expected = load("k8s_runtime_apply_tests")
    records = [strict_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(records) == 3 and all(type(record) is dict for record in records), "evidence_record_count")
    require(records[0].get("runtime_runner") == "candidate", "evidence_header")
    suites = records[1:]
    verify_suite_evidence(suites[0], "test_k8s_runtime_receipt", receipt_expected,
                          DESTROY_BASELINES, "engine", DESTROY_INLINE)
    verify_suite_evidence(suites[1], "test_k8s_runtime_apply", apply_expected,
                          APPLY_BASELINES, "apply", APPLY_INLINE)
    return suites


def compare_evidence(left, right):
    require(left == right, "serial_parallel_evidence_mismatch")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--workers", choices=("auto", "1", "2", "4"), default="1")
    mode.add_argument("--compare", nargs=2, metavar=("SERIAL_JSONL", "PARALLEL_JSONL"))
    mode.add_argument("--clean-python-stdin", action="store_true",
                      help="run the Python program on stdin in a fresh process with only stdin/stdout/stderr")
    parser.add_argument("--clean-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.compare:
        compare_evidence(read_evidence(args.compare[0]), read_evidence(args.compare[1]))
        print("Candidate serial/parallel evidence matched")
        return 0
    if args.clean_python_stdin:
        require(not args.clean_child, "clean_child_mode_conflict")
        return exit_status(clean_exec([sys.executable, "-"]))
    if not args.clean_child:
        # Every coordinator run starts behind the clean descriptor boundary.
        return exit_status(clean_exec([sys.executable, str(Path(__file__).resolve()),
                                       "--workers", args.workers, "--clean-child"]))
    return coordinate(args)


def coordinate(args):
    """The fork-based coordinator; main() starts it only behind clean_exec()."""
    require(not sys.flags.optimize, "optimized_python_refused")
    require(os.environ.get("KUBECONFIG") == "/dev/null" and os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
            "offline_environment_required")
    required_env = {"AWS_EC2_METADATA_DISABLED": "true", "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
                    "AWS_CONFIG_FILE": "/dev/null"}
    require(all(os.environ.get(key) == value for key, value in required_env.items()), "credential_free_environment_required")
    require(not any(os.environ.get(key) for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")), "credential_environment_refused")
    # The enclosing CI Step retains the pinned Helm installation and Plan/Status
    # serial checks. The candidate is only the Receipt/Apply execution path.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local-workflow"))
    from expected_counts import load
    workers = available_workers() if args.workers == "auto" else int(args.workers)
    require(1 <= workers <= available_workers(), "worker_limit")
    deadline = time.monotonic() + 2100
    print(json.dumps({"runtime_runner": "candidate", "workers": workers,
                      "cpu_cap": available_cpus(), "available_memory_bytes": available_memory(),
                      "python": sys.version.split()[0]}, sort_keys=True), flush=True)
    with isolated_parent():
        import test_k8s_runtime_receipt as receipt
        import test_k8s_runtime_destroy as destroy
        import test_k8s_runtime_apply as apply
        check_parent()
        apply.bundle()  # existing verified pinned Helm cache, no new persistent cache
        fingerprint = cache_fingerprint(apply.CACHE)
        require(not direct_children(), "unexpected_existing_child")
        require({item[0]: item[-1].__name__ for item in destroy.ENGINE_MUTATIONS
                 if item[-1].__name__ in DESTROY_INLINE.values()} == DESTROY_INLINE, "rc2_inventory_mismatch")
        require({item[0]: item[-1].__name__ for item in apply.MUTATIONS
                 if item[-1].__name__ in APPLY_INLINE.values()} == APPLY_INLINE, "apply_inline_inventory_mismatch")
        run_runtime_suite(receipt, destroy, destroy.ENGINE_MUTATIONS, DESTROY_BASELINES,
                          set(DESTROY_INLINE.values()), destroy.DestroyEngineMutationTests,
                          workers, deadline, load("k8s_runtime_receipt_tests"), cache=apply.CACHE, fingerprint=fingerprint)
        run_runtime_suite(apply, apply, apply.MUTATIONS, APPLY_BASELINES, set(APPLY_INLINE.values()),
                          apply.MutationTests, workers, deadline, load("k8s_runtime_apply_tests"), cache=apply.CACHE, fingerprint=fingerprint)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunnerError as exc:
        print("Runtime test runner refused: " + str(exc), file=sys.stderr)
        sys.exit(1)
