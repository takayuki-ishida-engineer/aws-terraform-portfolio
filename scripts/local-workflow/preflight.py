#!/usr/bin/env python3
"""Preflight checks for a local DEV plan, apply or destroy.

Run from the operator's workstation before any real AWS operation
(docs/deployment-configuration.md sections 1 and 2). Two levels:

- Offline (default): the root's untracked ``local.auto.tfvars`` exists, is
  ignored and untracked, assigns every environment-specific input, and no
  effective value is still a documented placeholder or example value. The
  effective values come from ``terraform console`` in the initialized root, so
  Terraform's own tfvars precedence applies. No AWS API is called.
- Live (``--live``, workstation only): read-only AWS calls with the operator's
  own CLI credentials confirm the caller account and, for the platform root,
  that the pinned EKS add-on versions and node AMI release exist. Refused in CI
  and whenever an AWS endpoint override is set.

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
}

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
READ_ONLY_AWS = {("sts", "get-caller-identity"), ("eks", "describe-addon-versions"), ("ssm", "get-parameter")}
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
    findings = []
    work_tree = git_work_tree(root)
    relative = os.path.relpath(path, work_tree)
    git = ["git", "-C", str(work_tree)]
    if subprocess.run(git + ["ls-files", "--error-unmatch", "--", relative], capture_output=True, check=False).returncode == 0:
        findings.append("local_tfvars_tracked")
    if subprocess.run(git + ["check-ignore", "-q", "--", relative], capture_output=True, check=False).returncode != 0:
        findings.append("local_tfvars_not_ignored")
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


def live_findings(root_name, values, aws="aws", env=None):
    """Read-only checks against the operator's AWS account. Never run in CI."""
    environment = os.environ if env is None else env
    if environment.get("CI") or environment.get("GITHUB_ACTIONS"):
        return ["live_refused_in_ci"]
    if any(key == "AWS_ENDPOINT_URL" or key.startswith("AWS_ENDPOINT_URL_") for key in environment):
        return ["live_refused_endpoint_override"]
    identity = run_aws(aws, ["sts", "get-caller-identity"], environment)
    if not isinstance(identity, dict) or not isinstance(identity.get("Account"), str):
        return ["caller_identity_unavailable"]
    if identity["Account"] in PLACEHOLDER_ACCOUNTS:
        return ["caller_account_synthetic"]
    if identity["Account"] != values.get("aws_account_id"):
        return ["caller_account_mismatch"]
    findings = []
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
    return findings


def preflight(root_name, terraform="terraform", aws="aws", live=False, services=SERVICES, env=None, root=None):
    """Check one root; ``root`` overrides its directory (used by the CI copy check)."""
    default = root_directory(root_name, services)
    root = default if root is None else Path(root)
    findings = local_file_findings(root_name, root)
    values = effective_values(root, terraform, env)
    findings += value_findings(root_name, values)
    if live:
        findings += ["live_skipped_offline_findings"] if findings else live_findings(root_name, values, aws, env)
    return {"root": root_name, "mode": "live" if live else "offline", "status": "failed" if findings else "passed",
            "findings": findings}


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
