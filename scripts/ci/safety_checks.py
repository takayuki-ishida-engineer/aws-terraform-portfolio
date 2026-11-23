#!/usr/bin/env python3
"""Always-on PR Safety checks (Owner decision 2026-11-23), offline and credential-free.

* ``workflows``: every workflow keeps its safety invariants: read-only token, no
  secrets or cloud credentials, SHA-pinned actions, standard ubuntu-24.04 runners,
  job timeouts, never-cancelling concurrency, checkout without persisted
  credentials, no caches, artifacts, registry pushes or self-hosted runners, the
  exact allowed triggers per workflow, the unchanged Emulator rehearsal trigger
  paths, and the fixed Full CI and PR Safety CI check names and timeouts.
* ``secrets``: no tracked file holds a credential-shaped value or a private key,
  and no credential-like file name is tracked.
* ``guards``: every real AWS/EKS operation entry point is refused under CI markers
  before it reads input or starts a process that could reach AWS or a cluster.
* ``changed``: the changed files of a pull request parse (Python, JSON, YAML, shell)
  and introduce no whitespace errors (git diff --check).

Nothing here calls AWS, Kubernetes or any network service.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "kubernetes/vendor/pyyaml"))
import yaml  # noqa: E402

WORKFLOWS = ".github/workflows"
PINNED = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
ALLOWED_TRIGGERS = {
    "terraform-offline-ci.yml": {"pull_request", "workflow_dispatch"},
    "pr-safety-ci.yml": {"pull_request"},
    "aws-emulator-contracts.yml": {"pull_request", "push"},
    "aws-emulator-rehearsal.yml": {"push", "workflow_dispatch"},
    "aws-emulator-verification.yml": {"workflow_dispatch"},
}
REHEARSAL_PATHS = [
    "infra/**",
    "scripts/emulator-rehearsal/**",
    "scripts/emulator-verification/gates.py",
    "scripts/emulator-verification/runtime_contracts.py",
    "scripts/emulator-verification/prepare.py",
    "scripts/emulator-verification/versions.json",
    "scripts/emulator-verification/awscli-publisher.asc",
    ".github/workflows/aws-emulator-rehearsal.yml",
]
FORBIDDEN_TEXT = [
    (re.compile(r"\$\{\{\s*secrets\."), "secrets-context"),
    (re.compile(r"\bgithub\.token\b|\bGITHUB_TOKEN\b"), "github-token"),
    (re.compile(r"pull_request_target|workflow_run\b"), "privileged-trigger"),
    (re.compile(r"id-token\s*:"), "oidc-token"),
    (re.compile(r"aws-actions/|configure-aws-credentials|AWS_ACCESS_KEY_ID\s*:|AWS_SECRET_ACCESS_KEY\s*:|AWS_SESSION_TOKEN\s*:"), "aws-credentials"),
    (re.compile(r"actions/cache|actions/upload-artifact|actions/download-artifact|docker/login-action|docker push|\bgit push\b"), "persistence-or-push"),
    (re.compile(r"self-hosted|larger-runner|ubuntu-latest"), "runner"),
    (re.compile(r"cancel-in-progress:\s*true"), "cancelling-concurrency"),
]
EXPECTED_JOB_ENV = {
    "TF_IN_AUTOMATION": "true", "TF_INPUT": "false", "CHECKPOINT_DISABLE": "1", "PYTHONDONTWRITEBYTECODE": "1",
    "AWS_EC2_METADATA_DISABLED": "true", "AWS_SHARED_CREDENTIALS_FILE": "/dev/null", "AWS_CONFIG_FILE": "/dev/null",
}
SECRET_PATTERNS = [
    (re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b"), "aws-access-key-id"),
    (re.compile(r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])"), "aws-secret-access-key"),
    (re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"), "private-key"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"), "github-token"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "slack-token"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "anthropic-key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "google-api-key"),
]
SECRET_NAMES = re.compile(r"(?i)(?:^|/)(?:\.env(?:\.[^/]*)?|[^/]*\.pem|[^/]*\.key|[^/]*\.p12|[^/]*\.pfx|[^/]*\.jks|id_(?:rsa|dsa|ecdsa|ed25519)"
                          r"|\.netrc|\.npmrc|\.pypirc|credentials(?:\.json)?|kubeconfig|[^/]*\.kubeconfig|terraform\.rc|\.terraformrc)$")
SECRET_NAME_ALLOW = {".env.example"}
GUARD_COMMANDS = [
    (["scripts/local-workflow/run.py", "network", "plan", "--terraform", "/nonexistent", "--aws", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/run.py", "network", "apply", "--terraform", "/nonexistent", "--aws", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/run.py", "network", "destroy", "--terraform", "/nonexistent", "--aws", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/handoff.py", "network", "--terraform", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/eks_tunnel.py", "kubeconfig", "--terraform", "/nonexistent", "--aws", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/eks_tunnel.py", "start", "--terraform", "/nonexistent", "--aws", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/empty_bucket.py", "--aws", "/nonexistent", "acme-dev-s3-tfstate"], "live_refused_in_ci"),
    (["scripts/local-workflow/k8s_certs.py", "register", "--project", "acme", "--material", "/nonexistent", "--kubectl", "/nonexistent",
      "--openssl", "/nonexistent", "--terraform", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/k8s_certs.py", "delete", "--project", "acme", "--kubectl", "/nonexistent", "--terraform", "/nonexistent"],
     "live_refused_in_ci"),
    (["scripts/local-workflow/k8s_runtime_input.py", "--project", "acme", "--account-id", "444455556666", "--material", "/nonexistent",
      "--selections", "/nonexistent", "--out-dir", "/nonexistent", "--terraform", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/k8s_runtime.py", "status", "--input", "/nonexistent", "--helm", "/nonexistent", "--kubectl", "/nonexistent",
      "--terraform", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/k8s_runtime.py", "receipt", "verify", "--cluster", "--input", "/nonexistent", "--helm", "/nonexistent",
      "--receipt-dir", "/nonexistent", "--expect-manifest-sha256", "0", "--expect-input-sha256", "0", "--kubectl", "/nonexistent",
      "--terraform", "/nonexistent"], "live_refused_in_ci"),
    (["scripts/local-workflow/k8s_runtime.py", "apply", "--input", "/nonexistent"], "operation_not_approved:apply"),
    (["scripts/local-workflow/k8s_runtime.py", "destroy", "--input", "/nonexistent"], "operation_not_approved:destroy"),
    (["scripts/local-workflow/mirror_images.py", "mirror", "--project", "acme", "--account-id", "444455556666", "--aws", "/nonexistent",
      "--skopeo", "/nonexistent"], "live_refused_in_ci"),
]


class SafetyError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SafetyError(message)


def git(*args, cwd=REPO):
    process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    require(process.returncode == 0, "git_failed:" + " ".join(args[:2]) + ":" + process.stderr.strip()[:200])
    return process.stdout


def triggers(data):
    # YAML 1.1 reads the bare key "on" as boolean true.
    value = data.get("on", data.get(True))
    if isinstance(value, str):
        return {value: None}
    if isinstance(value, list):
        return {item: None for item in value}
    require(isinstance(value, dict), "workflow_triggers_unreadable")
    return value


def check_workflow(name, text, impact_map):
    """Problems in one workflow file (an empty list means it is safe)."""
    problems = []
    for pattern, label in FORBIDDEN_TEXT:
        if pattern.search(text):
            problems.append(name + ":" + label)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return problems + [name + ":unparsable"]
    if not isinstance(data, dict):
        return problems + [name + ":not-a-mapping"]
    on = triggers(data)
    if name not in ALLOWED_TRIGGERS:
        problems.append(name + ":unreviewed-workflow")
    elif set(on) != ALLOWED_TRIGGERS[name]:
        problems.append(name + ":triggers:" + ",".join(sorted(map(str, on))))
    if data.get("permissions") != {"contents": "read"}:
        problems.append(name + ":permissions")
    concurrency = data.get("concurrency")
    if not isinstance(concurrency, dict) or concurrency.get("cancel-in-progress") is not False or not concurrency.get("group"):
        problems.append(name + ":concurrency")
    jobs = data.get("jobs") or {}
    if not jobs:
        problems.append(name + ":no-jobs")
    for job_id, job in jobs.items():
        prefix = name + ":" + str(job_id)
        if not isinstance(job, dict):
            problems.append(prefix + ":job-not-mapping")
            continue
        if "permissions" in job:
            problems.append(prefix + ":job-permissions")
        if job.get("runs-on") != "ubuntu-24.04":
            problems.append(prefix + ":runs-on")
        if not isinstance(job.get("timeout-minutes"), int) or not 0 < job["timeout-minutes"] <= 60:
            problems.append(prefix + ":timeout")
        if "if" in job:
            problems.append(prefix + ":job-level-if")
        if "secrets" in job or "services" in job or "container" in job:
            problems.append(prefix + ":secrets-services-or-container")
        for step in job.get("steps") or []:
            uses = step.get("uses") if isinstance(step, dict) else None
            if uses:
                if not PINNED.match(uses):
                    problems.append(prefix + ":unpinned:" + uses)
                if uses.startswith("actions/checkout@") and (step.get("with") or {}).get("persist-credentials") is not False:
                    problems.append(prefix + ":checkout-persists-credentials")
    full, safety = impact_map["full_ci"], impact_map["pr_safety"]
    if name == Path(full["workflow"]).name:
        job = jobs.get(full["job"]) or {}
        if job.get("name") != full["job_name"] or job.get("timeout-minutes") != full["timeout_minutes"]:
            problems.append(name + ":full-ci-check-name-or-timeout")
        if job.get("env") != EXPECTED_JOB_ENV:
            problems.append(name + ":job-env")
        pull = on.get("pull_request") or {}
        expected = [pattern for patterns in impact_map["high_risk"].values() for pattern in patterns]
        if pull.get("branches") != ["main"] or pull.get("paths") != expected:
            problems.append(name + ":high-risk-paths-differ-from-impact-map")
        inputs = (on.get("workflow_dispatch") or {}).get("inputs") or {}
        if sorted(inputs) != ["expected_head_sha", "pull_request_number", "reason"] or any(not inputs[key].get("required") for key in inputs):
            problems.append(name + ":dispatch-inputs")
        steps = job.get("steps") or []
        ids = [step.get("id") for step in steps]
        if ids[:3] != ["provider_cache", "checkout", "trigger"] or "python3 scripts/ci/full_ci_trigger.py" not in (steps[2].get("run") or ""):
            problems.append(name + ":trigger-step-must-follow-checkout")
        if (steps[1].get("with") or {}).get("fetch-depth") != 0:
            problems.append(name + ":checkout-fetch-depth")
    if name == Path(safety["workflow"]).name:
        job = jobs.get(safety["job"]) or {}
        if job.get("name") != safety["job_name"] or job.get("timeout-minutes") != safety["timeout_minutes"]:
            problems.append(name + ":pr-safety-check-name-or-timeout")
        if job.get("env") != EXPECTED_JOB_ENV:
            problems.append(name + ":job-env")
        pull = on.get("pull_request") or {}
        if pull != {"branches": ["main"]}:
            problems.append(name + ":pr-safety-must-run-on-every-pull-request")
    if name == "aws-emulator-rehearsal.yml":
        push = on.get("push") or {}
        if push.get("branches") != ["main"] or push.get("paths") != REHEARSAL_PATHS:
            problems.append(name + ":rehearsal-trigger-paths-changed")
    return problems


def check_workflows(root=REPO):
    impact_map = json.loads((root / "scripts/ci/impact_map.json").read_text(encoding="utf-8"))
    names = sorted(path.name for path in (root / WORKFLOWS).iterdir())
    problems = []
    if names != sorted(ALLOWED_TRIGGERS):
        problems.append("workflow-set:" + ",".join(names))
    job_names = {}
    for name in names:
        text = (root / WORKFLOWS / name).read_text(encoding="utf-8")
        problems += check_workflow(name, text, impact_map)
        try:
            for job_id, job in (yaml.safe_load(text).get("jobs") or {}).items():
                label = job.get("name", job_id) if isinstance(job, dict) else job_id
                job_names.setdefault(label, []).append(name)
        except (yaml.YAMLError, AttributeError):
            pass
    for label, owners in job_names.items():
        if len(owners) > 1:
            problems.append("duplicate-check-name:" + label)
    return problems


def scan_text(path, text):
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{path}:{number}:{label}")
    return findings


def check_secrets(root=REPO, paths=None):
    tracked = paths if paths is not None else [name for name in git("ls-files", "-z", cwd=root).split("\0") if name]
    findings = []
    for name in tracked:
        if SECRET_NAMES.search(name) and Path(name).name not in SECRET_NAME_ALLOW:
            findings.append(name + ":credential-like-file-name")
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        findings += scan_text(name, data.decode("utf-8", "replace"))
    return findings


def guard_environment():
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("AWS_", "KUBE")) and key not in ("CI", "GITHUB_ACTIONS")}
    environment.update(CI="true", GITHUB_ACTIONS="true", KUBECONFIG="/dev/null", PYTHONDONTWRITEBYTECODE="1",
                       AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_CONFIG_FILE="/dev/null", AWS_EC2_METADATA_DISABLED="true")
    return environment


def check_guards(root=REPO, commands=GUARD_COMMANDS):
    problems = []
    for arguments, expected in commands:
        process = subprocess.run([sys.executable, *arguments], cwd=root, env=guard_environment(), capture_output=True,
                                 text=True, timeout=60, check=False)
        output = process.stdout + process.stderr
        if process.returncode != 1 or ("Refused (" + expected + ")") not in output:
            problems.append(" ".join(arguments[:2]) + ": exit " + str(process.returncode) + ", expected refusal " + expected)
    return problems


def syntax_problem(path, data):
    text = data.decode("utf-8")
    suffix = Path(path).suffix
    if suffix == ".py":
        ast.parse(text, filename=path)
    elif suffix == ".json":
        json.loads(text)
    elif suffix in (".yml", ".yaml"):
        list(yaml.safe_load_all(text))
    elif suffix == ".sh":
        process = subprocess.run(["bash", "-n"], input=text, capture_output=True, text=True, check=False)
        if process.returncode:
            raise ValueError(process.stderr.strip()[:200])


def check_changed(base, head, root=REPO):
    problems = []
    names = [name for name in git("diff", "--name-only", "--no-renames", "--diff-filter=d", "-z", base, head, cwd=root).split("\0") if name]
    for name in names:
        data = subprocess.run(["git", "show", head + ":" + name], cwd=root, capture_output=True, check=False).stdout
        if b"\0" in data[:8192]:
            continue
        try:
            syntax_problem(name, data)
        except (SyntaxError, ValueError, UnicodeDecodeError, yaml.YAMLError) as error:
            problems.append(name + ":syntax:" + str(error).splitlines()[0][:160])
    check = subprocess.run(["git", "diff", "--check", base, head], cwd=root, capture_output=True, text=True, check=False)
    if check.returncode:
        problems += ["whitespace:" + line for line in check.stdout.splitlines()[:20]]
    return problems, len(names)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("workflows", "secrets", "guards"):
        commands.add_parser(name)
    changed = commands.add_parser("changed")
    changed.add_argument("--base", required=True)
    changed.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    if args.command == "workflows":
        problems, detail = check_workflows(), {"workflows": len(ALLOWED_TRIGGERS)}
    elif args.command == "secrets":
        problems = check_secrets()
        detail = {"tracked_files_scanned": len([name for name in git("ls-files", "-z").split("\0") if name])}
    elif args.command == "guards":
        problems, detail = check_guards(), {"refusals_verified": len(GUARD_COMMANDS)}
    else:
        problems, count = check_changed(args.base, args.head)
        detail = {"changed_files_parsed": count}
    if problems:
        print("PR Safety " + args.command + " check failed closed:", file=sys.stderr)
        for problem in problems:
            print("  " + problem, file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "check": args.command, **detail}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
