#!/usr/bin/env python3
"""Build the Kubernetes runtime renderer input (Step 1 item 6c-A).

Workstation only, like run.py: refused in CI, in Claude Code or Codex cloud
sessions, with the cloud session's placeholder credentials and with an AWS
endpoint override, before any tool starts.

The input (``kubernetes/environments/dev/README.md``) is assembled from three
sources and checked against each other before anything is written:

- the applied platform root's ``controller_identity`` (all 11 fields, unchanged),
  ``platform`` and ``private_ingress`` outputs (projected to its 5 reviewed fields)
  and the network root's ``network`` output, read one by one with
  ``terraform output -json <name>``. No other Terraform command runs, so no State
  is read beyond those outputs;
- ``public.json`` from ``k8s_certs.py generate`` (Secret names, SPKI pin, webhook
  CA bundle, hostnames). Only that file and the public ``webhook/ca.crt`` are read;
  no private key is opened. Certificate expiry is taken from the ``not_after`` dates
  that ``public.json`` records; the X.509 certificates themselves are not parsed here
  (``k8s_certs.py register`` verifies them before it applies the Secrets);
- the operator's resource selections (``runtime-selections.example.json``).

Project, account, Region, cluster, OIDC, target group ARN and VPC ID must agree
across all sources, and the result must pass the renderer's own input contract.
The input and a provenance record are written to a new directory outside the
repository (directory 0700, files 0600). The provenance record holds the canonical
SHA-256 of each Terraform output by root and output name; whether the State is
current is NOT_VERIFIED. Nothing here calls Kubernetes, and no
AWS API is called beyond what ``terraform output`` needs for the roots' backends.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff  # noqa: E402
import k8s_certs  # noqa: E402
import preflight  # noqa: E402

sys.path.insert(0, str(preflight.REPOSITORY / "kubernetes/tools"))
import common  # noqa: E402

SELECTIONS_FORMAT = "k8s-runtime-selections-v1"
PROVENANCE_FORMAT = "k8s-runtime-input-provenance-v1"
INPUT_FILE = "runtime-input.json"
PROVENANCE_FILE = "provenance.json"
REGION = "ca-central-1"
# The only Terraform outputs read, by root.
ALLOWED_OUTPUTS = {("platform", "controller_identity"), ("platform", "platform"), ("platform", "private_ingress"),
                   ("network", "network")}
CONTROLLER_FIELDS = ("interface_version", "scope", "role_arn", "oidc_issuer", "oidc_provider_arn", "namespace",
                     "service_account", "target_group_arn", "cluster_name", "kubernetes_version", "active_workload_az")
INGRESS_FIELDS = ("interface_version", "scope", "target_group_arn", "vpc_id", "backend_target_port")
PUBLIC_RUNTIME_FIELDS = ("project", "backend_hostname", "trust_domain", "expected_client_spki", "webhook_ca_bundle",
                         "gateway_tls_secret", "gateway_client_ca_secret", "webhook_tls_secret", "istio_ca_secret")
RESOURCE_PROFILES = ("controller", "istiod", "gateway")
# Expiry comes from public.json; no certificate or key file is parsed here.
CERTIFICATE_BOUNDARY = ("certificate validity: only the not_after dates recorded in public.json are checked; the "
                        "X.509 certificates are not read or verified here (k8s_certs.py register re-checks the "
                        "certificates, keys and chains against the material before it applies the Secrets)")


class InputError(Exception):
    """A check failed; the message never contains key, token or Secret material."""


def require(condition, code):
    if not condition:
        raise InputError(code)


def read_output(terraform, services, root_name, name, env):
    if (root_name, name) not in ALLOWED_OUTPUTS:
        raise InputError("terraform_output_not_allowed:" + root_name + "/" + name)
    try:
        return handoff.terraform_output(terraform, Path(services) / root_name, name, env)
    except preflight.PreflightError as error:
        raise InputError(str(error)) from None


def check_scope(scope, account_id, label):
    expected = {"environment": "dev", "partition": "aws", "region": REGION, "account_id": account_id}
    require(scope == expected, "scope_mismatch:" + label)


def check_outputs(project, account_id, identity, platform, ingress, network):
    """Cross-check the four Terraform outputs; return the two renderer sections."""
    cluster = project + "-dev-eks"
    require(isinstance(identity, dict) and set(identity) == set(CONTROLLER_FIELDS), "controller_identity_fields")
    require(isinstance(ingress, dict) and set(INGRESS_FIELDS) <= set(ingress), "private_ingress_fields")
    require(isinstance(platform, dict) and isinstance(network, dict), "terraform_output_shape")
    check_scope(identity.get("scope"), account_id, "controller_identity")
    check_scope(platform.get("scope"), account_id, "platform")
    check_scope(ingress.get("scope"), account_id, "private_ingress")
    check_scope(network.get("scope"), account_id, "network")
    require(identity["cluster_name"] == cluster and platform.get("cluster_name") == cluster, "cluster_name_mismatch")
    require(platform.get("cluster_arn") == "arn:aws:eks:" + REGION + ":" + account_id + ":cluster/" + cluster,
            "cluster_arn_mismatch")
    require(identity["oidc_issuer"] == platform.get("oidc_issuer")
            and identity["oidc_provider_arn"] == platform.get("oidc_provider_arn"), "oidc_mismatch")
    require(identity["role_arn"] == "arn:aws:iam::" + account_id + ":role/" + project + "-dev-role-lbc",
            "controller_role_mismatch")
    require(identity["target_group_arn"] == ingress["target_group_arn"], "target_group_arn_mismatch")
    require(str(ingress["target_group_arn"]).startswith("arn:aws:elasticloadbalancing:" + REGION + ":" + account_id
                                                        + ":targetgroup/"), "target_group_arn_scope")
    require(ingress["vpc_id"] == network.get("vpc_id"), "vpc_id_mismatch")
    controller = {key: identity[key] for key in CONTROLLER_FIELDS}
    private_ingress = {key: ingress[key] for key in INGRESS_FIELDS}
    return controller, private_ingress


def read_public(project, material, now):
    """public.json from k8s_certs.py generate: public values only, never a key file."""
    material = Path(material).expanduser().resolve()
    require(not k8s_certs.inside_repository(material), "material_inside_repository")
    require(material.is_dir() and not stat.S_IMODE(material.stat().st_mode) & 0o077,
            "material_directory_mode: expected 0700")
    path = material / "public.json"
    require(path.is_file() and not stat.S_IMODE(path.stat().st_mode) & 0o077, "public_json_mode: expected 0600")
    raw = path.read_bytes()
    require(b"PRIVATE KEY" not in raw, "public_json_contains_private_key")
    try:
        public = common.parse(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise InputError("public_json") from None
    require(isinstance(public, dict) and public.get("format") == k8s_certs.FORMAT and public.get("project") == project,
            "public_json_project_mismatch")
    runtime = public.get("runtime")
    require(isinstance(runtime, dict) and set(runtime) == set(PUBLIC_RUNTIME_FIELDS) and runtime["project"] == project,
            "public_runtime_fields")
    require(all(runtime[key] == value for key, value in k8s_certs.secret_names(project).items()),
            "public_secret_names_mismatch")
    require(public.get("secrets") == k8s_certs.public_layout(project), "secret_layout_mismatch")
    recorded = public.get("not_after")
    require(isinstance(recorded, dict) and set(recorded) == {name for name, _ in k8s_certs.DATED}, "not_after_mismatch")
    for name, value in sorted(recorded.items()):
        try:
            end = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        except (TypeError, ValueError):
            raise InputError("not_after_format:" + name) from None
        require(end >= now + datetime.timedelta(days=1), "material_expires_within_a_day:" + name)
    ca = material / "webhook" / "ca.crt"
    require(ca.is_file() and runtime["webhook_ca_bundle"] == base64.b64encode(ca.read_bytes()).decode(),
            "webhook_ca_mismatch")
    return {key: runtime[key] for key in PUBLIC_RUNTIME_FIELDS}, raw


def placeholder(value):
    if isinstance(value, dict):
        return any(placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(placeholder(v) for v in value)
    return isinstance(value, str) and ("REPLACE" in value or "<" in value or ">" in value)


def read_selections(project, path):
    raw = Path(path).expanduser().read_bytes()
    try:
        selections = common.parse(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise InputError("selections_json") from None
    require(isinstance(selections, dict) and set(selections) == {"format", "project", "resources"}
            and selections["format"] == SELECTIONS_FORMAT, "selections_fields")
    require(not placeholder(selections), "selections_placeholder (copy runtime-selections.example.json and choose)")
    require(selections["project"] == project, "selections_project_mismatch")
    require(isinstance(selections["resources"], dict) and set(selections["resources"]) == set(RESOURCE_PROFILES),
            "selections_resources")
    return selections["resources"], raw


def canonical_sha256(document):
    """The renderer's input_sha256 (render evidence) of the same document."""
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_outputs(out_dir, document, provenance):
    target = Path(out_dir).expanduser().resolve()
    require(not k8s_certs.inside_repository(target), "output_inside_repository")
    if target.exists():
        require(target.is_dir() and not any(target.iterdir()), "output_directory_not_empty")
    previous = os.umask(0o077)
    try:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(stat.S_IMODE(target.stat().st_mode) == 0o700, "output_directory_mode: expected 0700")
        for name, data in ((INPUT_FILE, document), (PROVENANCE_FILE, provenance)):
            descriptor = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
            require(stat.S_IMODE((target / name).stat().st_mode) == 0o600, "output_file_mode: expected 0600")
    finally:
        os.umask(previous)
    return target / INPUT_FILE


def build(project, account_id, material, selections, out_dir, terraform="terraform", services=preflight.SERVICES,
          env=None, now=None, out_fn=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out_fn("Refused (" + refusal + "): the runtime input is built only on the operator's workstation.")
        return 1
    k8s_certs.check_project(project)
    require(project not in preflight.PLACEHOLDER_PROJECTS, "placeholder_project")
    require(isinstance(account_id, str) and len(account_id) == 12 and account_id.isdigit(), "account_id_format")
    require(account_id not in preflight.PLACEHOLDER_ACCOUNTS, "placeholder_account")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    public_runtime, public_raw = read_public(project, material, now)
    resources, selections_raw = read_selections(project, selections)
    identity = read_output(terraform, services, "platform", "controller_identity", environment)
    platform = read_output(terraform, services, "platform", "platform", environment)
    ingress = read_output(terraform, services, "platform", "private_ingress", environment)
    network = read_output(terraform, services, "network", "network", environment)
    # Canonical SHA-256 of each output value exactly as terraform output returned it.
    output_digests = [{"root": root, "output": name, "sha256": canonical_sha256(value)}
                      for (root, name), value in ((("platform", "controller_identity"), identity),
                                                  (("platform", "platform"), platform),
                                                  (("platform", "private_ingress"), ingress),
                                                  (("network", "network"), network))]
    controller, private_ingress = check_outputs(project, account_id, identity, platform, ingress, network)
    document = {"interface_version": 2, "fixture": False, "controller_identity": controller,
                "private_ingress": private_ingress, "runtime": dict(public_runtime, resources=resources)}
    try:
        common.metadata(document, fixture=False)
    except (ValueError, KeyError, TypeError) as error:
        raise InputError("renderer_input_contract:" + str(error)) from None
    provenance = {
        "format": PROVENANCE_FORMAT,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": project,
        "input_sha256": canonical_sha256(document),
        "sources": {
            "controller_identity": "terraform output -json controller_identity (platform root), all 11 fields",
            "private_ingress": "terraform output -json private_ingress (platform root), projected to " +
                               ", ".join(INGRESS_FIELDS),
            "runtime": "k8s_certs.py public.json, sha256 " + hashlib.sha256(public_raw).hexdigest(),
            "runtime.resources": "operator selections, sha256 " + hashlib.sha256(selections_raw).hexdigest(),
        },
        "terraform_outputs": output_digests,
        "state_freshness": "NOT_VERIFIED: terraform output returns the values recorded at the last apply; it does "
                           "not prove that the State matches the live resources",
        "cross_checks": ["project", "account", "region", "cluster_name", "cluster_arn", "oidc", "controller_role",
                         "target_group_arn", "vpc_id", "secret_names", "secret_layout", "public_json_not_after",
                         "webhook_ca", "renderer_input_contract"],
        "not_verified": ["kubernetes_version is the requested Terraform value, not the server version",
                         "existence and reachability of the referenced AWS resources",
                         CERTIFICATE_BOUNDARY],
        "never_included": ["private keys", "Secret data", "tokens", "kubeconfig", "Terraform State"],
    }
    path = write_outputs(out_dir, document, provenance)
    out_fn("Wrote the runtime input to " + str(path) + " and its provenance next to it (directory 0700, files 0600).")
    out_fn("Input sha256 " + provenance["input_sha256"] + ". Next: k8s_runtime.py plan --input " + str(path) +
           " --helm <pinned helm>. Nothing was applied.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--material", required=True, help="k8s_certs.py generate directory (public.json is read)")
    parser.add_argument("--selections", required=True, help="resource selections (runtime-selections.example.json)")
    parser.add_argument("--out-dir", required=True, help="new directory outside the repository")
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args(argv)
    try:
        return build(args.project, args.account_id, args.material, args.selections, args.out_dir, args.terraform)
    except (InputError, k8s_certs.CertError, preflight.PreflightError, json.JSONDecodeError, OSError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
