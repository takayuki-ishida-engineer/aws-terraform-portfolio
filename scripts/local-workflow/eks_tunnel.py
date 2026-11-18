#!/usr/bin/env python3
"""Reach the private EKS endpoint through the developer access host (Step 1 item 6).

Workstation only, like run.py; refused in CI and cloud sessions.

- ``kubeconfig`` writes a kubeconfig (JSON, which kubectl reads as YAML) outside
  the repository. The server is ``https://127.0.0.1:<port>``, ``tls-server-name``
  is the real endpoint host so certificate verification stays on, and the user
  runs ``aws eks get-token`` (optionally with ``--role-arn``). No token is stored.
- ``start`` runs Session Manager port forwarding
  (``AWS-StartPortForwardingSessionToRemoteHost``) from ``127.0.0.1:<port>`` to the
  endpoint on 443 through the developer access host, in the foreground.

Values come from the applied platform and developer-access root outputs.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff  # noqa: E402
import preflight  # noqa: E402

DEFAULT_PORT = 8443


def endpoint_host(platform):
    parsed = urlparse(platform.get("endpoint", ""))
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".eks.amazonaws.com"):
        raise preflight.PreflightError("platform_endpoint_shape")
    return parsed.hostname


def kubeconfig_document(platform, port, role_arn=None):
    name = platform["cluster_name"]
    args = ["eks", "get-token", "--cluster-name", name, "--region", preflight.REGION, "--output", "json"]
    if role_arn:
        args += ["--role-arn", role_arn]
    return {
        "apiVersion": "v1", "kind": "Config", "current-context": name, "preferences": {},
        "clusters": [{"name": name, "cluster": {
            "server": f"https://127.0.0.1:{port}", "certificate-authority-data": platform["certificate_authority_data"],
            "tls-server-name": endpoint_host(platform)}}],
        "users": [{"name": name, "user": {"exec": {
            "apiVersion": "client.authentication.k8s.io/v1beta1", "command": "aws", "args": args,
            "interactiveMode": "Never"}}}],
        "contexts": [{"name": name, "context": {"cluster": name, "user": name}}],
    }


def write_kubeconfig(terraform="terraform", path=None, port=DEFAULT_PORT, role_arn=None, services=preflight.SERVICES,
                     env=None, out=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out("Refused (" + refusal + "): the tunnel runs only on the operator's workstation.")
        return 1
    platform = handoff.terraform_output(terraform, Path(services) / "platform", "platform", environment)
    target = Path(path).expanduser() if path else Path.home() / ".kube" / (platform["cluster_name"] + ".json")
    if preflight.REPOSITORY in target.resolve().parents:
        out("Refused: write the kubeconfig outside the repository: " + str(target))
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(kubeconfig_document(platform, port, role_arn), indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)
    out("Wrote " + str(target) + "; start the tunnel, then: KUBECONFIG=" + str(target) + " kubectl get nodes")
    return 0


def start_tunnel(terraform="terraform", aws="aws", port=DEFAULT_PORT, services=preflight.SERVICES, env=None, out=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out("Refused (" + refusal + "): the tunnel runs only on the operator's workstation.")
        return 1
    platform = handoff.terraform_output(terraform, Path(services) / "platform", "platform", environment)
    access = handoff.terraform_output(terraform, Path(services) / "developer-access", "developer_access", environment)
    if not str(access.get("instance_id", "")).startswith("i-"):
        raise preflight.PreflightError("developer_access_instance_id")
    command = [aws, "ssm", "start-session", "--region", preflight.REGION, "--target", access["instance_id"],
               "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
               "--parameters", f"host={endpoint_host(platform)},portNumber=443,localPortNumber={port}"]
    out("Forwarding 127.0.0.1:" + str(port) + " to the private EKS endpoint; press Ctrl-C to stop.")
    return subprocess.run(command, env=environment, check=False).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["kubeconfig", "start"])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--path", help="kubeconfig path (default ~/.kube/<cluster>.json)")
    parser.add_argument("--role-arn", help="IAM role for aws eks get-token, for example the bootstrap admin role")
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--aws", default="aws")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be from 1024 through 65535")
    try:
        if args.command == "kubeconfig":
            return write_kubeconfig(args.terraform, args.path, args.port, args.role_arn)
        return start_tunnel(args.terraform, args.aws, args.port)
    except (preflight.PreflightError, KeyError, json.JSONDecodeError, OSError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
