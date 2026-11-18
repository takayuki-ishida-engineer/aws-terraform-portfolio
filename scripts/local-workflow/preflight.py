#!/usr/bin/env python3
"""Preflight checks for a local DEV plan, apply or destroy.

Run from the operator's workstation before any real AWS operation
(docs/deployment-configuration.md sections 1 and 2). Two levels:

- Offline (default): the root's untracked ``local.auto.tfvars`` exists, is
  ignored and untracked, assigns every environment-specific input, and no
  effective value is still a documented placeholder or example value. The
  effective values come from ``terraform console`` in the initialized root, so
  Terraform's own tfvars precedence applies. No AWS API is called.
- Optional S3 backend (offline): when a root has an untracked
  ``backend_override.tf``, its untracked ``backend.s3.tfbackend`` must hold
  exactly the bucket, key, Region, native locking and encryption settings that
  docs/deployment-configuration.md section 3 defines, and nothing else (no
  profile, role or credential). The tfstate bootstrap root always stays local.
- Live (``--live``, workstation only): read-only AWS calls with the operator's
  own CLI credentials confirm the caller account, the State bucket's versioning
  and public access block when the S3 backend is used and, for the platform
  root, that the pinned EKS add-on versions and node AMI release exist and that
  the node egress prefix list is the regional S3 list. Refused
  in CI, in Claude Code or Codex cloud sessions, with the cloud session's
  placeholder credentials and whenever an AWS endpoint override is set.

The script never reads, prints or writes a credential or secret value.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
SERVICES = REPOSITORY / "infra/services/dev/ca-central-1"
REGION = "ca-central-1"
LOCAL_FILE = "local.auto.tfvars"

# Inputs whose real value is environment specific and must come from the
# untracked local.auto.tfvars, never from the committed placeholders.
ENVIRONMENT_INPUTS = {
    "network": ("project", "aws_account_id"),
    "platform": ("project", "aws_account_id", "bootstrap_admin_role_arn", "network_reference"),
    "serverless-api": ("project", "aws_account_id", "artifact_object_version"),
    "api": ("project", "aws_account_id", "callback_urls", "logout_urls", "default_redirect_uri"),
    "tfstate": ("project", "aws_account_id"),
}
BACKEND_OVERRIDE = "backend_override.tf"
BACKEND_CONFIG = "backend.s3.tfbackend"
# Roots that may use the optional S3 backend; the tfstate bootstrap root may not.
BACKEND_ROOTS = ("network", "platform", "serverless-api", "api")
BACKEND_SETTINGS = ("bucket", "key", "region", "use_lockfile", "encrypt")
EMPTY_S3_BACKEND = 'terraform{backend"s3"{}}'
# Signals that the process runs in automation or an agent cloud session, where
# real AWS access is prohibited (AGENTS.md). The cloud session also exposes the
# placeholder value below in AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.
CI_MARKERS = ("CI", "GITHUB_ACTIONS")
CLOUD_SESSION_MARKERS = ("CLAUDE_CODE_REMOTE", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED")
PLACEHOLDER_CREDENTIAL = "proxy-injected"
CREDENTIAL_VARIABLES = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")

# Documented placeholders (section 1), values from the local.auto.tfvars.example
# templates and the Emulator's synthetic account. Any of them in an effective
# environment-specific value means the root is not ready for real AWS.
PLACEHOLDER_PROJECTS = {"project", "myproj"}
PLACEHOLDER_ACCOUNTS = {"123456789012", "111122223333", "000000000000"}
PLACEHOLDER_PATTERNS = [
    re.compile(r"(^|[^0-9])203\.0\.113\."),
    re.compile(r"(^|[.@/])example\.(com|net|org)($|[/:])"),
    re.compile(r"your-domain\.test"),
    re.compile(r"example-role|your-eks-admin-role"),
    re.compile(r"placeholder|your-uploaded-object-version-id"),
    re.compile(r"\.\.\."),
    re.compile(r"^(vpc|subnet|rtb|nat)-0123456789abcdef0$|^(vpc|subnet|rtb|nat)-0{8,}[0-9]*$"),
]
# Account IDs inside ARNs, and bare 12-digit values such as scope.account_id.
ARN_ACCOUNT = re.compile(r"arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:([0-9]{12}):")
BARE_ACCOUNT = re.compile(r"^([0-9]{12})$")
READ_ONLY_AWS = {("sts", "get-caller-identity"), ("eks", "describe-addon-versions"), ("ssm", "get-parameter"),
                 ("s3api", "get-bucket-versioning"), ("s3api", "get-public-access-block"),
                 ("ec2", "describe-managed-prefix-lists")}
ADDON_NAMES = {"vpc_cni": "vpc-cni", "coredns": "coredns", "kube_proxy": "kube-proxy"}


class PreflightError(Exception):
    """A check could not be run (for example, an uninitialized root)."""


def root_directory(name, services=SERVICES):
    if name not in ENVIRONMENT_INPUTS:
        raise PreflightError("unknown_root:" + name)
    return Path(services) / name


def declared_variables(root):
    names = set()
    for source in sorted(Path(root).glob("*.tf")):
        names.update(re.findall(r'(?m)^variable\s+"([A-Za-z_][A-Za-z0-9_-]*)"', source.read_text(encoding="utf-8")))
    if not names:
        raise PreflightError("no_variables_declared")
    return sorted(names)


def effective_values(root, terraform="terraform", env=None):
    """Return every root variable's effective value as Terraform evaluates it."""
    names = declared_variables(root)
    expression = "base64encode(jsonencode({" + ", ".join(f'"{name}" = var.{name}' for name in names) + "}))\n"
    process = subprocess.run([terraform, "console", "-no-color"], cwd=root, env=env, input=expression,
                             capture_output=True, text=True, check=False)
    output = process.stdout.strip()
    if process.returncode != 0 or not re.fullmatch(r'"[A-Za-z0-9+/=]+"', output):
        detail = (process.stderr or process.stdout).strip().splitlines()
        raise PreflightError("terraform_console_failed (run terraform init in the root first): " + (detail[0] if detail else "no output"))
    values = json.loads(base64.b64decode(output[1:-1]))
    if set(values) != set(names):
        raise PreflightError("console_variable_mismatch")
    return values


def local_file_findings(root_name, root):
    """Check the untracked local.auto.tfvars without reading any other file."""
    path = Path(root) / LOCAL_FILE
    if not path.is_file():
        return ["local_tfvars_missing"]
    findings = git_state_findings(root, path, "local_tfvars")
    text = path.read_text(encoding="utf-8")
    for key in ENVIRONMENT_INPUTS[root_name]:
        if not re.search(r"(?m)^\s*" + re.escape(key) + r"\s*=", text):
            findings.append("local_value_missing:" + key)
    return findings


def git_work_tree(root):
    """The Git work tree that contains the root (the repository in normal use)."""
    process = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise PreflightError("root_not_in_git_work_tree")
    return Path(process.stdout.strip())


def git_state_findings(root, path, label):
    """Findings when an untracked local file is tracked or not ignored by Git."""
    work_tree = git_work_tree(root)
    relative = os.path.relpath(path, work_tree)
    git = ["git", "-C", str(work_tree)]
    if subprocess.run(git + ["ls-files", "--error-unmatch", "--", relative], capture_output=True, check=False).returncode == 0:
        return [label + "_tracked"]
    if subprocess.run(git + ["check-ignore", "-q", "--", relative], capture_output=True, check=False).returncode != 0:
        return [label + "_not_ignored"]
    return []


def local_value(root, key):
    """A plain string assignment from local.auto.tfvars, read without Terraform."""
    path = Path(root) / LOCAL_FILE
    if not path.is_file():
        return None
    match = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*=\s*"([^"]*)"\s*(#.*)?$', path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def parse_backend_config(path):
    """Parse a .tfbackend file of plain `name = "string"` / `name = true|false` lines."""
    settings = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        match = re.fullmatch(r'([a-z_]+)\s*=\s*("([^"\\]*)"|true|false)', line)
        if not match or match.group(1) in settings:
            raise ValueError("backend_config_unparsable")
        settings[match.group(1)] = match.group(3) if match.group(3) is not None else match.group(2) == "true"
    return settings


def backend_state(root_name, root, project):
    """Return (settings or None, findings) for the optional local S3 backend."""
    root = Path(root)
    override, config = root / BACKEND_OVERRIDE, root / BACKEND_CONFIG
    if not override.exists() and not config.exists():
        return None, []
    if root_name not in BACKEND_ROOTS:
        return None, ["bootstrap_backend_must_stay_local"]
    if not override.is_file():
        return None, ["backend_config_without_override"]
    if not config.is_file():
        return None, ["backend_config_missing"]
    findings = git_state_findings(root, override, "backend_override") + git_state_findings(root, config, "backend_config")
    source = re.sub(r"(?m)(#|//).*$", "", override.read_text(encoding="utf-8"))
    if re.sub(r"\s+", "", source) != EMPTY_S3_BACKEND:
        findings.append("backend_override_unexpected_content")
    try:
        settings = parse_backend_config(config)
    except ValueError as error:
        return None, findings + [str(error)]
    if set(settings) != set(BACKEND_SETTINGS):
        return None, findings + ["backend_config_settings"]
    if project in PLACEHOLDER_PROJECTS or project is None:
        findings.append("placeholder:backend")
    if settings["bucket"] != f"{project}-dev-s3-tfstate":
        findings.append("backend_bucket_mismatch")
    if settings["key"] != f"{project}/dev/{REGION}/{root_name}/terraform.tfstate":
        findings.append("backend_key_mismatch")
    if settings["region"] != REGION:
        findings.append("backend_region_mismatch")
    if settings["use_lockfile"] is not True:
        findings.append("backend_lockfile_disabled")
    if settings["encrypt"] is not True:
        findings.append("backend_encryption_disabled")
    return settings, findings


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def accounts_in(texts):
    return {found for text in texts for pattern in (ARN_ACCOUNT, BARE_ACCOUNT) for found in pattern.findall(text)}


def value_findings(root_name, values):
    """Placeholder, example and account-consistency findings for effective values."""
    findings = []
    account = values.get("aws_account_id")
    if values.get("project") in PLACEHOLDER_PROJECTS:
        findings.append("placeholder:project")
    if account in PLACEHOLDER_ACCOUNTS:
        findings.append("placeholder:aws_account_id")
    for key in ENVIRONMENT_INPUTS[root_name]:
        if key in ("project", "aws_account_id"):
            continue
        texts = list(strings_in(values.get(key)))
        accounts = accounts_in(texts)
        if not texts or accounts & PLACEHOLDER_ACCOUNTS \
                or any(pattern.search(text) for text in texts for pattern in PLACEHOLDER_PATTERNS):
            findings.append("placeholder:" + key)
        elif account not in PLACEHOLDER_ACCOUNTS and accounts - {account}:
            findings.append("account_mismatch:" + key)
    return findings


def run_aws(aws, arguments, env):
    if tuple(arguments[:2]) not in READ_ONLY_AWS:
        raise PreflightError("aws_command_not_read_only:" + " ".join(arguments[:2]))
    process = subprocess.run([aws] + arguments + ["--region", REGION, "--output", "json"], env=env,
                             capture_output=True, text=True, check=False)
    if process.returncode != 0:
        return None
    return json.loads(process.stdout)


def automation_refusal(env):
    """The refusal code when real AWS access must not happen here, else None."""
    if any(env.get(key) for key in CI_MARKERS):
        return "live_refused_in_ci"
    if any(env.get(key) for key in CLOUD_SESSION_MARKERS):
        return "live_refused_in_cloud_session"
    if any(env.get(key) == PLACEHOLDER_CREDENTIAL for key in CREDENTIAL_VARIABLES):
        return "live_refused_placeholder_credentials"
    if any(key == "AWS_ENDPOINT_URL" or key.startswith("AWS_ENDPOINT_URL_") for key in env):
        return "live_refused_endpoint_override"
    return None


def caller_findings(account, aws, env):
    identity = run_aws(aws, ["sts", "get-caller-identity"], env)
    if not isinstance(identity, dict) or not isinstance(identity.get("Account"), str):
        return ["caller_identity_unavailable"]
    if identity["Account"] in PLACEHOLDER_ACCOUNTS:
        return ["caller_account_synthetic"]
    if identity["Account"] != account:
        return ["caller_account_mismatch"]
    return []


def state_bucket_findings(bucket, aws, env):
    """Read-only checks that the State bucket exists, is versioned and private."""
    versioning = run_aws(aws, ["s3api", "get-bucket-versioning", "--bucket", bucket], env)
    if not isinstance(versioning, dict):
        return ["state_bucket_unavailable"]
    findings = [] if versioning.get("Status") == "Enabled" else ["state_bucket_versioning_not_enabled"]
    block = run_aws(aws, ["s3api", "get-public-access-block", "--bucket", bucket], env)
    settings = (block or {}).get("PublicAccessBlockConfiguration", {}) if isinstance(block, dict) else {}
    if not all(settings.get(key) is True for key in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
        findings.append("state_bucket_public_access_not_blocked")
    return findings


def live_findings(root_name, values, aws="aws", env=None, backend=None):
    """Read-only checks against the operator's AWS account. Never run in CI or a cloud session."""
    environment = os.environ if env is None else env
    refusal = automation_refusal(environment)
    if refusal:
        return [refusal]
    findings = caller_findings(values.get("aws_account_id"), aws, environment)
    if findings:
        return findings
    if backend:
        findings += state_bucket_findings(backend["bucket"], aws, environment)
    if root_name == "platform":
        version = values["kubernetes_version"]
        for key, addon in ADDON_NAMES.items():
            catalog = run_aws(aws, ["eks", "describe-addon-versions", "--kubernetes-version", version, "--addon-name", addon], environment)
            available = {item.get("addonVersion") for entry in (catalog or {}).get("addons", []) if entry.get("addonName") == addon
                         for item in entry.get("addonVersions", [])
                         if any(c.get("clusterVersion") == version for c in item.get("compatibilities", []))}
            if values["addon_versions"][key] not in available:
                findings.append("addon_version_unavailable:" + key)
        node = values["node_group"]
        architecture = {"AL2023_x86_64_STANDARD": "x86_64", "AL2023_ARM_64_STANDARD": "arm64"}.get(node["ami_type"])
        release = re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-([0-9]{8})", node["release_version"])
        if architecture is None or release is None:
            findings.append("node_release_unavailable")
        else:
            name = (f"/aws/service/eks/optimized-ami/{version}/amazon-linux-2023/{architecture}/standard/"
                    f"amazon-eks-node-al2023-{architecture}-standard-{version}-v{release.group(1)}/image_id")
            parameter = run_aws(aws, ["ssm", "get-parameter", "--name", name], environment)
            if not isinstance(parameter, dict) or not str(parameter.get("Parameter", {}).get("Value", "")).startswith("ami-"):
                findings.append("node_release_unavailable")
        if values.get("node_https_egress_prefix_list_ids"):
            lists = run_aws(aws, ["ec2", "describe-managed-prefix-lists", "--filters",
                                  f"Name=prefix-list-name,Values=com.amazonaws.{REGION}.s3"], environment)
            actual = {item.get("PrefixListId") for item in (lists or {}).get("PrefixLists", [])} if isinstance(lists, dict) else set()
            if len(actual) != 1 or not actual <= set(values["node_https_egress_prefix_list_ids"]):
                findings.append("s3_prefix_list_mismatch")
    return findings


def preflight(root_name, terraform="terraform", aws="aws", live=False, services=SERVICES, env=None, root=None):
    """Check one root; ``root`` overrides its directory (used by the CI copy check)."""
    default = root_directory(root_name, services)
    root = default if root is None else Path(root)
    findings = local_file_findings(root_name, root)
    values = effective_values(root, terraform, env)
    findings += value_findings(root_name, values)
    backend, backend_issues = backend_state(root_name, root, values.get("project"))
    findings += backend_issues
    if live:
        findings += ["live_skipped_offline_findings"] if findings else live_findings(root_name, values, aws, env, backend)
    return {"root": root_name, "mode": "live" if live else "offline", "status": "failed" if findings else "passed",
            "findings": findings}


def migration_findings(root_name, root, aws="aws", env=None):
    """Checks before moving a root's local State into the S3 backend.

    The root is not yet initialized for S3, so values come from
    local.auto.tfvars directly instead of terraform console.
    """
    environment = os.environ if env is None else env
    root = Path(root)
    findings = local_file_findings(root_name, root)
    project, account = local_value(root, "project"), local_value(root, "aws_account_id")
    if project is None or account is None:
        findings.append("local_identity_unreadable")
    elif account in PLACEHOLDER_ACCOUNTS:
        findings.append("placeholder:aws_account_id")
    backend, issues = backend_state(root_name, root, project)
    findings += issues
    if backend is None and not issues:
        findings.append("backend_override_missing")
    if findings:
        return findings
    refusal = automation_refusal(environment)
    if refusal:
        return [refusal]
    return caller_findings(account, aws, environment) or state_bucket_findings(backend["bucket"], aws, environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="+", choices=sorted(ENVIRONMENT_INPUTS))
    parser.add_argument("--live", action="store_true", help="also run read-only AWS checks (workstation only)")
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--aws", default="aws")
    args = parser.parse_args(argv)
    reports = []
    try:
        for name in args.roots:
            reports.append(preflight(name, args.terraform, args.aws, args.live))
    except PreflightError as error:
        print("Preflight could not run: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps({"aws_api_calls": "read-only" if args.live else 0, "reports": reports}, indent=2))
    return 0 if all(report["status"] == "passed" for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
