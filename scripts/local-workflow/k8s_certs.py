#!/usr/bin/env python3
"""DEV certificates and keys for the Kubernetes runtime (Step 1 item 6b-A, finding F4).

Keys and certificates are created on the operator's workstation and go straight
into the cluster as Kubernetes Secrets. They never enter the repository,
Terraform (configuration, variables, State or plans) or a CI log
(docs/deployment-configuration.md section 9).

- ``generate`` (offline) uses OpenSSL 3 to write a new material directory outside
  the repository (directory 0700, files 0600):
  - the Istio plug-in CA: root, intermediate (``pathlen:0``) and chain;
  - the gateway's server certificate for the backend hostname, signed by its own CA;
  - a client CA and one client certificate, whose public key is the pinned SPKI;
  - the AWS Load Balancer Controller webhook's CA and serving certificate.
  The root and issuing CA private keys are deleted as soon as they have signed,
  except the Istio intermediate key, which istiod needs. ``public.json`` holds only
  public values: the renderer's ``runtime`` fields (SPKI pin, webhook CA bundle,
  Secret names), the Secret layout and the expiry dates.
- ``register`` (workstation only) checks the material against ``public.json``
  (hostname and SANs, validity, Secret layout, keys and chains), then checks that
  the context ``<project>-dev-eks`` is exactly the kubeconfig ``eks_tunnel.py
  kubeconfig`` writes for the applied platform root: the loopback tunnel as API
  server, TLS verification against the cluster's own CA and endpoint host, and
  ``aws eks get-token`` for that cluster. Only then does it apply the four Secrets
  with ``kubectl apply --server-side``. The Secret data goes through stdin, never
  through arguments or output. Afterwards it deletes the server private keys from
  the material directory unless ``--keep-material`` is given.
- ``delete`` is retired (G9, Owner decision 2026-11-24): it deleted by name with
  ``kubectl delete --ignore-not-found``, without a UID check, so it now refuses on
  every path and never calls kubectl. Automation is still refused first. The safe
  replacement is ``k8s_certs_receipt.cleanup`` (metadata-only reads, the
  registration UID receipt and UID-precondition DELETE through the D19 transport),
  which is Source/Offline only: no real transport exists.

Secret names follow ``<project>-<purpose>`` where the project creates them
(``<project>-gateway-tls``, ``<project>-gateway-client-cacert``) and keep the
names that Istio (``cacerts``) and the AWS Load Balancer Controller chart
(``aws-load-balancer-controller-tls``) mandate. ``register`` and ``delete`` are
refused in CI, in Claude Code or Codex cloud sessions, with the cloud session's
placeholder credentials and with an AWS endpoint override, like the other
workstation scripts. Nothing here calls an AWS API.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eks_tunnel  # noqa: E402
import handoff  # noqa: E402
import preflight  # noqa: E402

FORMAT = "k8s-certs-public-v1"
# The DEV roots' project rule (kubernetes/tools/common.py PROJECT).
PROJECT = re.compile(r"[a-z]([a-z0-9-]{0,8}[a-z0-9])?")
DNS = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
MAX_DAYS = 90
WEBHOOK_SERVICE = "aws-load-balancer-controller-webhook-service"
ISTIO_FILES = ("ca-cert.pem", "ca-key.pem", "root-cert.pem", "cert-chain.pem")
# Every file generate writes, relative to the material directory.
MATERIAL = (
    "istio/root-cert.pem", "istio/ca-cert.pem", "istio/ca-key.pem", "istio/cert-chain.pem",
    "gateway/tls.crt", "gateway/tls.key", "gateway/server-ca.crt", "gateway/client-ca.crt",
    "client/tls.crt", "client/tls.key",
    "webhook/ca.crt", "webhook/tls.crt", "webhook/tls.key",
    "public.json",
)
# Private keys that live in the cluster after register; the client key stays local.
# Certificates whose validity public.json records, by name.
DATED = (("istio_root", "istio/root-cert.pem"), ("istio_intermediate", "istio/ca-cert.pem"),
         ("gateway_server", "gateway/tls.crt"), ("gateway_client", "client/tls.crt"), ("webhook", "webhook/tls.crt"))
LOOPBACK_SERVER = re.compile(r"https://127\.0\.0\.1:([0-9]{4,5})")
ROLE_ARN = re.compile(r"arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}")
SERVER_KEYS = ("istio/ca-key.pem", "gateway/tls.key", "webhook/tls.key")
KEY_PAIRS = (("istio/ca-cert.pem", "istio/ca-key.pem"), ("gateway/tls.crt", "gateway/tls.key"),
             ("client/tls.crt", "client/tls.key"), ("webhook/tls.crt", "webhook/tls.key"))
SAFE_OUTPUT = re.compile(r'secret/[a-z0-9.-]+ (serverside-applied|created|configured|unchanged)'
                         r'|secret "[a-z0-9.-]+" deleted( from [a-z0-9.-]+ namespace)?|namespace/[a-z0-9.-]+')
LONG_TOKEN = re.compile(r"[A-Za-z0-9+/=_-]{40,}")


class CertError(Exception):
    """A check failed; the message never contains key or certificate material."""


def check_project(project):
    if not isinstance(project, str) or not PROJECT.fullmatch(project) or re.search("aws|amazon|cognito", project):
        raise CertError("project_name")
    return project


def secret_names(project):
    return {"gateway_tls_secret": project + "-gateway-tls",
            "gateway_client_ca_secret": project + "-gateway-client-cacert",
            "webhook_tls_secret": "aws-load-balancer-controller-tls",
            "istio_ca_secret": "cacerts"}


def inside_repository(path):
    path = Path(path).expanduser().resolve()
    return path == preflight.REPOSITORY or preflight.REPOSITORY in path.parents


def redact(text):
    """Keep only lines that cannot carry material: no PEM blocks, no long tokens."""
    lines = []
    for line in str(text).splitlines():
        if "BEGIN" in line or "PRIVATE" in line or LONG_TOKEN.search(line):
            lines.append("[redacted]")
        else:
            lines.append(line[:200])
    return lines


class OpenSSL:
    def __init__(self, binary="openssl"):
        self.binary = binary
        version = self.run(["version"], "openssl_version").strip()
        if not version.startswith("OpenSSL 3."):
            raise CertError("openssl_version: OpenSSL 3 is required (pass --openssl)")

    def run(self, args, step, cwd=None):
        try:
            process = subprocess.run([self.binary] + args, capture_output=True, text=True, check=False, cwd=cwd,
                                     env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "OPENSSL_CONF": "/dev/null"})
        except OSError:
            raise CertError("openssl_unavailable") from None
        if process.returncode != 0:
            # OpenSSL's stderr is never echoed: it could quote its input.
            raise CertError("openssl_failed:" + step)
        return process.stdout

    def key(self, path, rsa=False):
        algorithm = ["-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:4096"] if rsa else \
            ["-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256"]
        self.run(["genpkey"] + algorithm + ["-out", str(path)], "genpkey:" + path.name)

    def self_signed(self, key, cert, subject, extensions, days, work):
        config = work / (cert.stem + ".cnf")
        config.write_text("[req]\ndistinguished_name=dn\nprompt=no\n[dn]\n" + subject + "\n[ext]\n" + extensions + "\n")
        self.run(["req", "-x509", "-new", "-sha256", "-key", str(key), "-config", str(config), "-extensions", "ext",
                  "-days", str(days), "-set_serial", "0x" + secrets.token_hex(16), "-out", str(cert)], "root:" + cert.name)

    def signed(self, key, cert, subject, extensions, days, ca_cert, ca_key, work):
        config = work / (cert.parent.name + "-" + cert.stem + ".cnf")
        request = work / (cert.parent.name + "-" + cert.stem + ".csr")
        config.write_text("[req]\ndistinguished_name=dn\nprompt=no\n[dn]\n" + subject + "\n[ext]\n" + extensions + "\n")
        self.run(["req", "-new", "-sha256", "-key", str(key), "-config", str(config), "-out", str(request)],
                 "csr:" + cert.name)
        self.run(["x509", "-req", "-sha256", "-in", str(request), "-CA", str(ca_cert), "-CAkey", str(ca_key),
                  "-set_serial", "0x" + secrets.token_hex(16), "-days", str(days), "-extfile", str(config),
                  "-extensions", "ext", "-out", str(cert)], "sign:" + cert.name)

    def verify(self, ca, cert, purpose=None):
        args = ["verify", "-x509_strict", "-CAfile", str(ca)] + (["-purpose", purpose] if purpose else []) + [str(cert)]
        self.run(args, "verify:" + Path(cert).name)

    def public_key(self, path, private=False):
        args = ["pkey", "-pubout", "-in", str(path)] if private else ["x509", "-noout", "-pubkey", "-in", str(path)]
        return self.run(args, "public_key:" + Path(path).name)

    def dates(self, cert):
        """(notBefore, notAfter) as aware UTC datetimes."""
        text = self.run(["x509", "-noout", "-startdate", "-enddate", "-in", str(cert)], "dates:" + Path(cert).name)
        values = dict(line.split("=", 1) for line in text.strip().splitlines() if "=" in line)
        try:
            return tuple(datetime.datetime.strptime(values[k], "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=datetime.timezone.utc) for k in ("notBefore", "notAfter"))
        except (KeyError, ValueError):
            raise CertError("certificate_dates:" + Path(cert).name) from None

    def not_after(self, cert):
        return timestamp(self.dates(cert)[1])

    def dns_names(self, cert):
        """The certificate's subjectAltName entries; every entry must be a DNS name."""
        text = self.run(["x509", "-noout", "-ext", "subjectAltName", "-in", str(cert)], "san:" + Path(cert).name)
        lines = text.strip().splitlines()
        entries = [x.strip() for x in " ".join(lines[1:]).split(",") if x.strip()] if lines else []
        if any(not x.startswith("DNS:") for x in entries):
            raise CertError("san_not_dns:" + Path(cert).name)
        return sorted(x[4:] for x in entries)


def timestamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def spki_pin(public_pem):
    """Envoy's verifyCertificateSpki: base64 SHA-256 of the DER SubjectPublicKeyInfo."""
    body = "".join(line for line in public_pem.splitlines() if line and not line.startswith("-----"))
    return base64.b64encode(hashlib.sha256(base64.b64decode(body)).digest()).decode()


ROOT_CA = "basicConstraints=critical,CA:true\nkeyUsage=critical,keyCertSign,cRLSign,digitalSignature\n" \
          "subjectKeyIdentifier=hash"


def leaf(usage, san=None):
    text = "basicConstraints=critical,CA:false\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=" + usage + \
           "\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid"
    return text + ("\nsubjectAltName=" + ",".join("DNS:" + x for x in san) if san else "")


def generate(project, backend_hostname, trust_domain, out, days=30, openssl="openssl", out_fn=print):
    check_project(project)
    for value in (backend_hostname, trust_domain):
        if not isinstance(value, str) or len(value) > 253 or not DNS.fullmatch(value):
            raise CertError("dns_name")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_DAYS:
        raise CertError("validity_days: 1 to " + str(MAX_DAYS))
    target = Path(out).expanduser().resolve()
    if inside_repository(target):
        raise CertError("material_inside_repository")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise CertError("material_directory_not_empty")
    tool = OpenSSL(openssl)
    previous = os.umask(0o077)
    work = target / ".ca"
    try:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.chmod(0o700)
        for name in ("istio", "gateway", "client", "webhook", ".ca"):
            (target / name).mkdir(mode=0o700)
        istio, gateway, client, webhook = (target / x for x in ("istio", "gateway", "client", "webhook"))
        revision = project + "-v1"

        tool.key(work / "istio-root.key", rsa=True)
        tool.self_signed(work / "istio-root.key", istio / "root-cert.pem",
                         "O=" + project + "\nCN=" + project + " DEV Istio root CA", ROOT_CA, days + 1, work)
        tool.key(istio / "ca-key.pem", rsa=True)
        tool.signed(istio / "ca-key.pem", istio / "ca-cert.pem", "O=" + project + "\nCN=" + project +
                    " DEV Istio intermediate CA",
                    "basicConstraints=critical,CA:true,pathlen:0\n"
                    "keyUsage=critical,digitalSignature,nonRepudiation,keyEncipherment,keyCertSign\n"
                    "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid\n"
                    "subjectAltName=DNS:istiod.istio-system.svc,DNS:istiod-" + revision + ".istio-system.svc",
                    days, istio / "root-cert.pem", work / "istio-root.key", work)
        (istio / "cert-chain.pem").write_text((istio / "ca-cert.pem").read_text() + (istio / "root-cert.pem").read_text())
        tool.verify(istio / "root-cert.pem", istio / "ca-cert.pem")

        tool.key(work / "server-ca.key")
        tool.self_signed(work / "server-ca.key", gateway / "server-ca.crt",
                         "O=" + project + "\nCN=" + project + " DEV gateway server CA", ROOT_CA, days + 1, work)
        tool.key(gateway / "tls.key")
        tool.signed(gateway / "tls.key", gateway / "tls.crt", "O=" + project + "\nCN=" + backend_hostname,
                    leaf("serverAuth", [backend_hostname]), days, gateway / "server-ca.crt", work / "server-ca.key", work)
        tool.verify(gateway / "server-ca.crt", gateway / "tls.crt", "sslserver")

        tool.key(work / "client-ca.key")
        tool.self_signed(work / "client-ca.key", gateway / "client-ca.crt",
                         "O=" + project + "\nCN=" + project + " DEV gateway client CA", ROOT_CA, days + 1, work)
        tool.key(client / "tls.key")
        tool.signed(client / "tls.key", client / "tls.crt", "O=" + project + "\nCN=" + project + "-dev-client",
                    leaf("clientAuth"), days, gateway / "client-ca.crt", work / "client-ca.key", work)
        tool.verify(gateway / "client-ca.crt", client / "tls.crt", "sslclient")

        tool.key(work / "webhook-ca.key")
        tool.self_signed(work / "webhook-ca.key", webhook / "ca.crt",
                         "O=" + project + "\nCN=" + project + " DEV controller webhook CA", ROOT_CA, days + 1, work)
        tool.key(webhook / "tls.key")
        service = WEBHOOK_SERVICE + ".kube-system.svc"
        tool.signed(webhook / "tls.key", webhook / "tls.crt", "O=" + project + "\nCN=" + service,
                    leaf("serverAuth", [service, service + ".cluster.local"]), days, webhook / "ca.crt",
                    work / "webhook-ca.key", work)
        tool.verify(webhook / "ca.crt", webhook / "tls.crt", "sslserver")
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        # Root and issuing CA keys never outlive the signing step.
        shutil.rmtree(work, ignore_errors=True)
        os.umask(previous)
    runtime = {"project": project, "backend_hostname": backend_hostname, "trust_domain": trust_domain,
               "expected_client_spki": [spki_pin(tool.public_key(client / "tls.crt"))],
               "webhook_ca_bundle": base64.b64encode((webhook / "ca.crt").read_bytes()).decode()}
    runtime.update(secret_names(project))
    public = {
        "format": FORMAT, "project": project,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime": runtime,
        "secrets": public_layout(project),
        "not_after": {name: tool.not_after(target / path) for name, path in DATED},
    }
    previous = os.umask(0o077)
    try:
        (target / "public.json").write_text(json.dumps(public, indent=2) + "\n")
    finally:
        os.umask(previous)
    out_fn("Wrote DEV certificate material to " + str(target) + " (directory 0700, files 0600).")
    out_fn("Public runtime values for the renderer: " + str(target / "public.json"))
    out_fn("Certificates expire " + min(public["not_after"].values()) + ". Private keys are never printed.")
    return public


def secret_layout(project, material):
    """The four Secrets; with material=None only names, types and keys (data values empty)."""
    def data(mapping):
        if material is None:
            return {key: "" for key in mapping}
        return {key: base64.b64encode((material / path).read_bytes()).decode() for key, path in mapping.items()}
    labels = {"app.kubernetes.io/part-of": project, "app.kubernetes.io/managed-by": "k8s_certs.py"}
    names = secret_names(project)

    def secret(name, namespace, kind, mapping):
        return {"apiVersion": "v1", "kind": "Secret", "type": kind,
                "metadata": {"name": name, "namespace": namespace, "labels": labels}, "data": data(mapping)}
    return [
        secret(names["istio_ca_secret"], "istio-system", "Opaque", {k: "istio/" + k for k in ISTIO_FILES}),
        secret(names["webhook_tls_secret"], "kube-system", "kubernetes.io/tls",
               {"ca.crt": "webhook/ca.crt", "tls.crt": "webhook/tls.crt", "tls.key": "webhook/tls.key"}),
        secret(names["gateway_tls_secret"], project + "-ingress", "kubernetes.io/tls",
               {"tls.crt": "gateway/tls.crt", "tls.key": "gateway/tls.key"}),
        secret(names["gateway_client_ca_secret"], project + "-ingress", "Opaque", {"ca.crt": "gateway/client-ca.crt"}),
    ]


def public_layout(project):
    return [{"namespace": s["metadata"]["namespace"], "name": s["metadata"]["name"], "type": s["type"],
             "keys": sorted(s["data"])} for s in secret_layout(project, None)]


def webhook_names():
    service = WEBHOOK_SERVICE + ".kube-system.svc"
    return sorted([service, service + ".cluster.local"])


def check_material(project, material, tool, now=None):
    """Refuse material that is incomplete, exposed, foreign, expired or inconsistent."""
    material = Path(material).expanduser().resolve()
    if inside_repository(material):
        raise CertError("material_inside_repository")
    if not material.is_dir() or stat.S_IMODE(material.stat().st_mode) & 0o077:
        raise CertError("material_directory_mode: expected 0700")
    for path in MATERIAL:
        file = material / path
        if not file.is_file():
            raise CertError("material_incomplete:" + path + " (generate new material)")
        if stat.S_IMODE(file.stat().st_mode) & 0o077:
            raise CertError("material_file_mode:" + path)
    try:
        public = json.loads((material / "public.json").read_text())
    except ValueError:
        raise CertError("public_json") from None
    if not isinstance(public, dict) or public.get("format") != FORMAT or public.get("project") != project \
            or not isinstance(public.get("runtime"), dict) or public["runtime"].get("project") != project:
        raise CertError("material_project_mismatch")
    # What register sends must be exactly the layout public.json records.
    if public.get("secrets") != public_layout(project):
        raise CertError("secret_layout_mismatch")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    recorded = public.get("not_after")
    if not isinstance(recorded, dict) or set(recorded) != {name for name, _ in DATED}:
        raise CertError("not_after_mismatch")
    for name, path in DATED:
        start, end = tool.dates(material / path)
        if start > now:
            raise CertError("material_not_yet_valid:" + path)
        if end - start > datetime.timedelta(days=MAX_DAYS + 1):
            raise CertError("validity_too_long:" + path)
        if end < now + datetime.timedelta(days=1):
            raise CertError("material_expires_within_a_day:" + path)
        if recorded[name] != timestamp(end):
            raise CertError("not_after_mismatch:" + name)
    host = public["runtime"].get("backend_hostname")
    if not isinstance(host, str) or len(host) > 253 or not DNS.fullmatch(host):
        raise CertError("backend_hostname_invalid")
    if tool.dns_names(material / "gateway/tls.crt") != [host]:
        raise CertError("gateway_san_mismatch: the gateway certificate is not for " + host)
    if tool.dns_names(material / "webhook/tls.crt") != webhook_names():
        raise CertError("webhook_san_mismatch")
    for cert, key in KEY_PAIRS:
        if tool.public_key(material / cert) != tool.public_key(material / key, private=True):
            raise CertError("key_mismatch:" + cert)
    tool.verify(material / "istio/root-cert.pem", material / "istio/ca-cert.pem")
    tool.verify(material / "gateway/server-ca.crt", material / "gateway/tls.crt", "sslserver")
    tool.verify(material / "gateway/client-ca.crt", material / "client/tls.crt", "sslclient")
    tool.verify(material / "webhook/ca.crt", material / "webhook/tls.crt", "sslserver")
    if (material / "istio/cert-chain.pem").read_text() != \
            (material / "istio/ca-cert.pem").read_text() + (material / "istio/root-cert.pem").read_text():
        raise CertError("istio_chain_mismatch")
    runtime = public["runtime"]
    if runtime.get("expected_client_spki") != [spki_pin(tool.public_key(material / "client/tls.crt"))] \
            or runtime.get("webhook_ca_bundle") != base64.b64encode((material / "webhook/ca.crt").read_bytes()).decode() \
            or any(runtime.get(k) != v for k, v in secret_names(project).items()):
        raise CertError("public_values_mismatch")
    return material


def workstation(project, context, env):
    refusal = preflight.automation_refusal(env)
    if refusal:
        return "Refused (" + refusal + "): Secrets are registered only from the operator's workstation."
    if context != project + "-dev-eks":
        return "Refused (context_mismatch): the context must be " + project + "-dev-eks, as eks_tunnel.py writes it."
    return None


def check_kubeconfig(view, context, platform):
    """Refuse a context that is not the eks_tunnel.py kubeconfig of the applied platform cluster."""
    def fail(reason):
        raise CertError("kubeconfig_mismatch:" + reason)
    if not isinstance(platform, dict) or platform.get("cluster_name") != context:
        fail("platform_cluster: the applied platform cluster is not " + context)
    try:
        host = eks_tunnel.endpoint_host(platform)
    except preflight.PreflightError:
        fail("platform_endpoint")
    if not isinstance(view, dict) or view.get("current-context") not in (None, "", context):
        fail("shape")
    sections = [view.get(k) for k in ("clusters", "contexts", "users")]
    if not all(isinstance(x, list) and len(x) == 1 and isinstance(x[0], dict) for x in sections):
        fail("not_a_single_context")
    clusters, contexts, users = (x[0] for x in sections)
    binding = contexts.get("context") or {}
    if contexts.get("name") != context or clusters.get("name") != context or users.get("name") != context \
            or binding.get("cluster") != context or binding.get("user") != context:
        fail("context_binding")
    cluster = clusters.get("cluster")
    # Only the three fields eks_tunnel.py writes: no insecure-skip-tls-verify, CA file, proxy or extension.
    if not isinstance(cluster, dict) or set(cluster) != {"server", "certificate-authority-data", "tls-server-name"}:
        fail("cluster_fields")
    port = LOOPBACK_SERVER.fullmatch(str(cluster["server"]))
    if not port or not 1024 <= int(port.group(1)) <= 65535:
        fail("server: the API server must be the local tunnel https://127.0.0.1:<port>")
    if cluster["tls-server-name"] != host:
        fail("tls_server_name: not the applied cluster's endpoint")
    if cluster["certificate-authority-data"] != platform.get("certificate_authority_data"):
        fail("certificate_authority: not the applied cluster's CA")
    user = users.get("user")
    if not isinstance(user, dict) or set(user) != {"exec"} or not isinstance(user["exec"], dict):
        fail("user_credentials: only aws eks get-token is accepted")
    command = user["exec"]
    if set(command) - {"apiVersion", "command", "args", "env", "provideClusterInfo", "interactiveMode", "installHint"} \
            or command.get("apiVersion") != "client.authentication.k8s.io/v1beta1" or command.get("command") != "aws" \
            or command.get("env") or command.get("provideClusterInfo"):
        fail("exec")
    expected = ["eks", "get-token", "--cluster-name", context, "--region", preflight.REGION, "--output", "json"]
    args = command.get("args")
    if not (args == expected or isinstance(args, list) and len(args) == 10 and args[:8] == expected
            and args[8] == "--role-arn" and isinstance(args[9], str) and ROLE_ARN.fullmatch(args[9])):
        fail("cluster_identity: get-token is not for " + context)


def verified_context(context, kubectl_binary, terraform, services, environment):
    """Compare the context with the platform root's output before any Secret leaves the workstation."""
    platform = handoff.terraform_output(terraform, Path(services) / "platform", "platform", environment)
    process = kubectl(kubectl_binary, context, ["config", "view", "--minify", "--raw", "-o", "json"], environment)
    if process.returncode != 0:
        raise CertError("kubeconfig_mismatch:context_unavailable (run eks_tunnel.py kubeconfig)")
    try:
        view = json.loads(process.stdout)
    except ValueError:
        raise CertError("kubeconfig_mismatch:shape") from None
    check_kubeconfig(view, context, platform)


def kubectl(binary, context, args, env, stdin=None):
    try:
        return subprocess.run([binary, "--context", context] + args, input=stdin, capture_output=True, text=True,
                              check=False, env=env)
    except OSError:
        raise CertError("kubectl_unavailable") from None


def report(process, out_fn, label):
    for line in process.stdout.splitlines():
        out_fn(line if SAFE_OUTPUT.fullmatch(line.strip()) else "[redacted kubectl output]")
    if process.returncode != 0:
        for line in redact(process.stderr):
            out_fn(line)
        raise CertError(label + " (kubectl exit " + str(process.returncode) + ")")


def register(project, material, context=None, kubectl_binary="kubectl", openssl="openssl", keep_material=False,
             env=None, out_fn=print, terraform="terraform", services=preflight.SERVICES):
    check_project(project)
    environment = dict(os.environ if env is None else env)
    context = context or project + "-dev-eks"
    refusal = workstation(project, context, environment)
    if refusal:
        out_fn(refusal)
        return 1
    material = check_material(project, material, OpenSSL(openssl))
    verified_context(context, kubectl_binary, terraform, services, environment)
    namespaces = ["istio-system", "kube-system", project + "-ingress"]
    process = kubectl(kubectl_binary, context, ["get", "namespace"] + namespaces + ["-o", "name"], environment)
    if process.returncode != 0 or sorted(process.stdout.split()) != sorted("namespace/" + n for n in namespaces):
        for line in redact(process.stderr):
            out_fn(line)
        raise CertError("namespaces_missing: apply the runtime's namespaces stage first (" + ", ".join(namespaces) + ")")
    manifest = json.dumps({"apiVersion": "v1", "kind": "List", "items": secret_layout(project, material)})
    process = kubectl(kubectl_binary, context, ["apply", "--server-side", "--field-manager=" + project + "-k8s-certs",
                                                "-f", "-"], environment, stdin=manifest)
    report(process, out_fn, "secret_apply_failed")
    out_fn("Registered 4 Secrets in " + context + ".")
    if not keep_material:
        for path in SERVER_KEYS:
            (material / path).unlink()
        out_fn("Deleted the server private keys from " + str(material) + "; client/tls.key stays for testing. "
               "Delete the directory when you no longer need it.")
    return 0


DELETE_RETIRED = ("Refused (name_based_delete_retired): k8s_certs.py no longer deletes Secrets by name. Cleanup "
                  "needs the registration UID receipt, metadata-only checks and a UID-precondition DELETE "
                  "(k8s_certs_receipt.cleanup, G9), whose real transport is not implemented.")


def delete(project, context=None, kubectl_binary="kubectl", env=None, out_fn=print, terraform="terraform",
           services=preflight.SERVICES):
    """Retired name-based delete (G9): refuses on every path; no kubeconfig read, no kubectl, no fallback."""
    check_project(project)
    environment = dict(os.environ if env is None else env)
    context = context or project + "-dev-eks"
    refusal = workstation(project, context, environment)
    if refusal:
        out_fn(refusal)
        return 1
    out_fn(DELETE_RETIRED)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="create new DEV material outside the repository (offline)")
    gen.add_argument("--project", required=True)
    gen.add_argument("--backend-hostname", required=True)
    gen.add_argument("--trust-domain", required=True)
    gen.add_argument("--out", required=True, help="new or empty directory outside the repository")
    gen.add_argument("--days", type=int, default=30, help="certificate validity, 1 to 90 days (default 30)")
    gen.add_argument("--openssl", default="openssl")
    reg = sub.add_parser("register", help="apply the four Secrets (workstation only)")
    reg.add_argument("--project", required=True)
    reg.add_argument("--material", required=True)
    reg.add_argument("--context", help="kubectl context (must be <project>-dev-eks)")
    reg.add_argument("--kubectl", default="kubectl")
    reg.add_argument("--openssl", default="openssl")
    reg.add_argument("--keep-material", action="store_true", help="keep the server private keys afterwards")
    reg.add_argument("--terraform", default="terraform", help="reads the applied platform root's output")
    rem = sub.add_parser("delete", help="retired: name-based Secret deletion is refused (G9)")
    rem.add_argument("--project", required=True)
    rem.add_argument("--context", help="kubectl context (must be <project>-dev-eks)")
    rem.add_argument("--kubectl", default="kubectl")
    rem.add_argument("--terraform", default="terraform", help="reads the applied platform root's output")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            generate(args.project, args.backend_hostname, args.trust_domain, args.out, args.days, args.openssl)
            return 0
        if args.command == "register":
            return register(args.project, args.material, args.context, args.kubectl, args.openssl, args.keep_material,
                            terraform=args.terraform)
        return delete(args.project, args.context, args.kubectl, terraform=args.terraform)
    except (CertError, preflight.PreflightError, OSError, json.JSONDecodeError) as error:
        # CertError and PreflightError messages are fixed codes; other errors show only their type.
        message = str(error) if isinstance(error, (CertError, preflight.PreflightError)) else type(error).__name__
        print("Stopped: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
