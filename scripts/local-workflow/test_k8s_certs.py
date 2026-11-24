#!/usr/bin/env python3
"""Offline tests for k8s_certs.py (Step 1 item 6b-A, finding F4).

Real OpenSSL generates throwaway material in temporary directories outside the
repository, which are removed afterwards. A fake kubectl records its arguments
and stdin, so no cluster and no AWS API is contacted. The tests check that no
key or certificate material reaches arguments, output or the repository, that
the Secrets match what the Kubernetes renderer references, and that the
workstation-only commands are refused in automation.
"""
import base64
import copy
import datetime
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eks_tunnel  # noqa: E402
import k8s_certs  # noqa: E402

sys.path.insert(0, str(HERE.parents[1] / "kubernetes/tools"))
import common  # noqa: E402

FAKE_KUBECTL = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    data = sys.stdin.read() if "-f" in sys.argv else ""
    with open(os.environ["FAKE_KUBECTL_LOG"], "a") as log:
        log.write(json.dumps({"argv": sys.argv[1:], "stdin": data}) + "\\n")
    mode = os.environ.get("FAKE_KUBECTL_MODE", "ok")
    args = sys.argv[3:]
    if args[:2] == ["config", "view"]:
        if mode == "view_fails":
            sys.stderr.write('error: context "demo-dev-eks" does not exist\\n')
            sys.exit(1)
        print(open(os.environ["FAKE_KUBECONFIG_VIEW"]).read())
    elif args[:2] == ["get", "namespace"]:
        if mode == "missing_namespace":
            sys.stderr.write('Error from server (NotFound): namespaces "x-ingress" not found\\n')
            sys.exit(1)
        print("\\n".join("namespace/" + n for n in args[2:-2]))
    elif args[0] == "apply":
        if mode == "apply_fails":
            sys.stderr.write("error: rejected object: " + data + "\\n")
            sys.exit(1)
        if mode == "noisy":
            print(data)
        for item in json.loads(data)["items"]:
            print("secret/" + item["metadata"]["name"] + " serverside-applied")
    elif args[0] == "delete":
        print('secret "' + args[2] + '" deleted from ' + args[4] + " namespace")
    """)
FAKE_TERRAFORM = textwrap.dedent("""\
    #!/usr/bin/env python3
    import os, sys
    print(open(os.environ["FAKE_PLATFORM_OUTPUT"]).read())
    """)
WORKSTATION = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
# A synthetic applied platform output (no real cluster); eks_tunnel.py builds the kubeconfig from it.
PLATFORM = {"cluster_name": "demo-dev-eks",
            "endpoint": "https://0123456789ABCDEF0123456789ABCDEF.gr7.ca-central-1.eks.amazonaws.com",
            "certificate_authority_data": base64.b64encode(b"SYNTHETIC CLUSTER CA, NOT A CERTIFICATE").decode()}
ROLE = "arn:aws:iam::000000000000:role/demo-bootstrap-admin"


def kubectl_view(platform=PLATFORM, port=8443, role_arn=None):
    """What `kubectl config view --minify --raw -o json` prints for the kubeconfig eks_tunnel.py writes."""
    view = eks_tunnel.kubeconfig_document(platform, port, role_arn)
    view["users"][0]["user"]["exec"].update(env=None, provideClusterInfo=False)
    return view
PROJECT = "demo"
HOST = "backend.demo.invalid"
TRUST = "demo.invalid"


def material_text(directory):
    """Every line of every material file that carries key or certificate content."""
    lines = set()
    for path in Path(directory).rglob("*"):
        if path.is_file() and path.name != "public.json":
            lines.update(line for line in path.read_text().splitlines() if line and not line.startswith("-----"))
    return lines


class Material:
    """One generated material set, shared by the tests that only read it."""
    directory = None
    output = None

    @classmethod
    def create(cls):
        if cls.directory is None:
            cls.parent = Path(tempfile.mkdtemp(prefix="k8s-certs-test-"))
            cls.directory = cls.parent / "material"
            buffer = []
            cls.public = k8s_certs.generate(PROJECT, HOST, TRUST, cls.directory, days=30, out_fn=buffer.append)
            cls.output = "\n".join(buffer)
            cls.secret_lines = material_text(cls.directory)
        return cls

    @classmethod
    def copy(cls, target):
        shutil.copytree(cls.create().directory, target)
        return Path(target)

    @classmethod
    def remove(cls):
        if cls.directory is not None:
            shutil.rmtree(cls.parent, ignore_errors=True)


class OtherHost(Material):
    """A second, independent material set for another backend hostname."""
    directory = None
    host = "other.demo.invalid"

    @classmethod
    def create(cls):
        if cls.directory is None:
            cls.parent = Path(tempfile.mkdtemp(prefix="k8s-certs-other-"))
            cls.directory = cls.parent / "material"
            k8s_certs.generate(PROJECT, cls.host, TRUST, cls.directory, days=30, out_fn=lambda _: None)
        return cls


def openssl(*args):
    return subprocess.run(["openssl"] + list(args), capture_output=True, text=True, check=True).stdout


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.m = Material.create()

    def test_exact_material_layout_and_modes(self):
        files = sorted(str(p.relative_to(self.m.directory)) for p in self.m.directory.rglob("*") if p.is_file())
        self.assertEqual(files, sorted(k8s_certs.MATERIAL))
        self.assertEqual(stat.S_IMODE(self.m.directory.stat().st_mode), 0o700)
        for path in self.m.directory.rglob("*"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600, str(path))
        self.assertFalse((self.m.directory / ".ca").exists(), "root and issuing CA keys are deleted")

    def test_only_expected_private_keys_remain(self):
        keys = sorted(str(p.relative_to(self.m.directory)) for p in self.m.directory.rglob("*")
                      if p.is_file() and "PRIVATE KEY" in p.read_text())
        self.assertEqual(keys, ["client/tls.key", "gateway/tls.key", "istio/ca-key.pem", "webhook/tls.key"])

    def test_istio_plugin_ca(self):
        d = self.m.directory / "istio"
        openssl("verify", "-x509_strict", "-CAfile", str(d / "root-cert.pem"), str(d / "ca-cert.pem"))
        text = openssl("x509", "-noout", "-text", "-in", str(d / "ca-cert.pem"))
        self.assertRegex(text, r"CA:TRUE, pathlen:0")
        self.assertIn("Certificate Sign", text)
        self.assertIn("DNS:istiod.istio-system.svc", text)
        self.assertIn("DNS:istiod-demo-v1.istio-system.svc", text)
        self.assertEqual((d / "cert-chain.pem").read_text(), (d / "ca-cert.pem").read_text() + (d / "root-cert.pem").read_text())
        self.assertIn("rsaEncryption", text)

    def test_gateway_and_webhook_leaves(self):
        d = self.m.directory
        server = openssl("x509", "-noout", "-text", "-in", str(d / "gateway/tls.crt"))
        self.assertIn("DNS:" + HOST, server)
        self.assertIn("TLS Web Server Authentication", server)
        self.assertIn("CA:FALSE", server)
        client = openssl("x509", "-noout", "-text", "-in", str(d / "client/tls.crt"))
        self.assertIn("TLS Web Client Authentication", client)
        self.assertNotIn("TLS Web Server Authentication", client)
        webhook = openssl("x509", "-noout", "-text", "-in", str(d / "webhook/tls.crt"))
        service = "aws-load-balancer-controller-webhook-service.kube-system.svc"
        self.assertIn("DNS:" + service + ", DNS:" + service + ".cluster.local", webhook)
        for ca, leaf, purpose in [("gateway/server-ca.crt", "gateway/tls.crt", "sslserver"),
                                  ("gateway/client-ca.crt", "client/tls.crt", "sslclient"),
                                  ("webhook/ca.crt", "webhook/tls.crt", "sslserver")]:
            openssl("verify", "-x509_strict", "-purpose", purpose, "-CAfile", str(d / ca), str(d / leaf))
        # Separate CAs: the client CA cannot vouch for the server or the webhook.
        for ca, leaf in [("gateway/client-ca.crt", "gateway/tls.crt"), ("gateway/server-ca.crt", "client/tls.crt"),
                         ("gateway/client-ca.crt", "webhook/tls.crt")]:
            process = subprocess.run(["openssl", "verify", "-CAfile", str(d / ca), str(d / leaf)], capture_output=True)
            self.assertNotEqual(process.returncode, 0, ca + " must not verify " + leaf)

    def test_validity_bounded(self):
        for name, value in self.m.public["not_after"].items():
            self.assertRegex(value, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", name)
        end = openssl("x509", "-noout", "-enddate", "-in", str(self.m.directory / "gateway/tls.crt"))
        start = openssl("x509", "-noout", "-startdate", "-in", str(self.m.directory / "gateway/tls.crt"))
        self.assertTrue(end and start)

    def test_public_values_feed_the_renderer(self):
        public = json.loads((self.m.directory / "public.json").read_text())
        self.assertEqual(public, self.m.public)
        runtime = public["runtime"]
        pem = openssl("x509", "-noout", "-pubkey", "-in", str(self.m.directory / "client/tls.crt"))
        der = subprocess.run(["openssl", "pkey", "-pubin", "-outform", "DER"], input=pem.encode(), capture_output=True,
                             check=True).stdout
        digest = subprocess.run(["openssl", "dgst", "-sha256", "-binary"], input=der, capture_output=True, check=True).stdout
        self.assertEqual(runtime["expected_client_spki"], [base64.b64encode(digest).decode()])
        self.assertEqual(base64.b64decode(runtime["webhook_ca_bundle"]), (self.m.directory / "webhook/ca.crt").read_bytes())
        fixture = json.loads((HERE.parents[1] / "kubernetes/tests/fixtures/runtime.json").read_text())
        live = copy.deepcopy(fixture)
        live["fixture"] = False
        live["controller_identity"]["cluster_name"] = "demo-dev-eks"
        live["controller_identity"]["role_arn"] = "arn:aws:iam::000000000000:role/demo-dev-role-lbc"
        live["runtime"].update(runtime)
        common.metadata(live, False)  # the renderer's own live-input checks accept the generated values
        self.assertEqual({s["name"] for s in public["secrets"]},
                         {live["runtime"][k] for k in ("gateway_tls_secret", "gateway_client_ca_secret",
                                                       "webhook_tls_secret", "istio_ca_secret")})

    def test_public_json_and_output_hold_no_material(self):
        public = (self.m.directory / "public.json").read_text()
        output = self.m.output
        for text in (public, output):
            self.assertNotIn("PRIVATE KEY", text)
            self.assertNotIn("BEGIN CERTIFICATE", text)
            for line in self.m.secret_lines:
                self.assertNotIn(line, text)
        self.assertIn("Private keys are never printed", output)


class GenerateRefusalTests(unittest.TestCase):
    def test_refuses_inside_repository(self):
        # Even if the guard were broken, never leave material in the working tree.
        self.addCleanup(shutil.rmtree, HERE / "material-test", ignore_errors=True)
        with self.assertRaisesRegex(k8s_certs.CertError, "material_inside_repository"):
            k8s_certs.generate(PROJECT, HOST, TRUST, HERE / "material-test", out_fn=lambda _: None)
        self.assertFalse((HERE / "material-test").exists())

    def test_refuses_non_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "existing").write_text("x")
            with self.assertRaisesRegex(k8s_certs.CertError, "material_directory_not_empty"):
                k8s_certs.generate(PROJECT, HOST, TRUST, tmp, out_fn=lambda _: None)
            self.assertEqual(os.listdir(tmp), ["existing"])

    def test_refuses_bad_inputs_before_openssl(self):
        cases = [("project", "project_name", ["Demo", "demo-", "1demo", "myaws", "amazon", "cognito1", "abcdefghijk", "",
                                              7]),
                 ("host", "dns_name", ["*.demo.invalid", "demo", "Demo.invalid", "a..b", "a." + "b" * 64 + ".invalid",
                                       ("a" * 60 + ".") * 5 + "invalid"]),
                 ("days", "validity_days", [0, 91, -1, 365, True, 30.0])]
        with tempfile.TemporaryDirectory() as tmp:
            for field, code, values in cases:
                for value in values:
                    args = {"project": PROJECT, "host": HOST, "days": 30}
                    args[field] = value
                    # The exact code shows the input check refused it, not the missing OpenSSL.
                    with self.subTest(field=field, value=value), self.assertRaisesRegex(k8s_certs.CertError, code):
                        k8s_certs.generate(args["project"], args["host"], TRUST, Path(tmp) / "out", args["days"],
                                           openssl="/nonexistent/openssl", out_fn=lambda _: None)
            self.assertEqual(os.listdir(tmp), [])

    def test_failed_generation_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "openssl"
            # Reports OpenSSL 3, then fails while quoting its input on stderr.
            fake.write_text("#!/bin/sh\nif [ \"$1\" = version ]; then echo 'OpenSSL 3.0.13'; exit 0; fi\n"
                            "echo 'QUOTED-INPUT-MUST-NOT-APPEAR' >&2\nexit 1\n")
            fake.chmod(0o755)
            with self.assertRaises(k8s_certs.CertError) as caught:
                k8s_certs.generate(PROJECT, HOST, TRUST, Path(tmp) / "out", openssl=str(fake), out_fn=lambda _: None)
            self.assertRegex(str(caught.exception), "^openssl_failed:genpkey:")
            self.assertNotIn("QUOTED-INPUT", str(caught.exception))
            self.assertFalse((Path(tmp) / "out").exists(), "a failed generation removes its partial directory")

    def test_refuses_old_openssl(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "openssl"
            fake.write_text("#!/bin/sh\necho 'LibreSSL 3.3.6'\n")
            fake.chmod(0o755)
            with self.assertRaisesRegex(k8s_certs.CertError, "openssl_version"):
                k8s_certs.generate(PROJECT, HOST, TRUST, Path(tmp) / "out", openssl=str(fake), out_fn=lambda _: None)
            self.assertFalse((Path(tmp) / "out").exists())


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-certs-register-"))
        self.material = Material.copy(self.tmp / "material")
        self.log = self.tmp / "kubectl.log"
        self.kubectl = self.tmp / "kubectl"
        self.kubectl.write_text(FAKE_KUBECTL)
        self.kubectl.chmod(0o755)
        self.terraform = self.tmp / "terraform"
        self.terraform.write_text(FAKE_TERRAFORM)
        self.terraform.chmod(0o755)
        self.platform_file = self.tmp / "platform.json"
        self.platform_file.write_text(json.dumps(PLATFORM))
        self.view_file = self.tmp / "view.json"
        self.view_file.write_text(json.dumps(kubectl_view()))
        self.env = dict(WORKSTATION, FAKE_KUBECTL_LOG=str(self.log), FAKE_PLATFORM_OUTPUT=str(self.platform_file),
                        FAKE_KUBECONFIG_VIEW=str(self.view_file))
        self.output = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def register(self, **kwargs):
        options = dict(project=PROJECT, material=self.material, kubectl_binary=str(self.kubectl), env=self.env,
                       out_fn=self.output.append, terraform=str(self.terraform), services=self.tmp)
        options.update(kwargs)
        return k8s_certs.register(**options)

    def assert_no_material(self, text):
        self.assertNotIn("PRIVATE KEY", text)
        self.assertNotIn("BEGIN CERTIFICATE", text)
        for line in Material.create().secret_lines:
            self.assertNotIn(line, text)

    def test_applies_the_four_secrets_through_stdin(self):
        self.assertEqual(self.register(keep_material=True), 0)
        calls = self.calls()
        self.assertEqual([c["argv"][:4] for c in calls],
                         [["--context", "demo-dev-eks", "config", "view"],
                          ["--context", "demo-dev-eks", "get", "namespace"],
                          ["--context", "demo-dev-eks", "apply", "--server-side"]])
        self.assertEqual(calls[0]["argv"], ["--context", "demo-dev-eks", "config", "view", "--minify", "--raw", "-o",
                                            "json"])
        self.assertEqual(calls[2]["argv"], ["--context", "demo-dev-eks", "apply", "--server-side",
                                            "--field-manager=demo-k8s-certs", "-f", "-"])
        items = json.loads(calls[2]["stdin"])["items"]
        layout = {(i["metadata"]["namespace"], i["metadata"]["name"]): (i["type"], sorted(i["data"])) for i in items}
        self.assertEqual(layout, {
            ("istio-system", "cacerts"): ("Opaque", ["ca-cert.pem", "ca-key.pem", "cert-chain.pem", "root-cert.pem"]),
            ("kube-system", "aws-load-balancer-controller-tls"): ("kubernetes.io/tls", ["ca.crt", "tls.crt", "tls.key"]),
            ("demo-ingress", "demo-gateway-tls"): ("kubernetes.io/tls", ["tls.crt", "tls.key"]),
            ("demo-ingress", "demo-gateway-client-cacert"): ("Opaque", ["ca.crt"]),
        })
        for item in items:
            self.assertEqual(item["metadata"]["labels"], {"app.kubernetes.io/part-of": "demo",
                                                          "app.kubernetes.io/managed-by": "k8s_certs.py"})
        cacerts = next(i for i in items if i["metadata"]["name"] == "cacerts")["data"]
        self.assertEqual(base64.b64decode(cacerts["ca-key.pem"]), (self.material / "istio/ca-key.pem").read_bytes())
        client_ca = next(i for i in items if i["metadata"]["name"] == "demo-gateway-client-cacert")["data"]
        self.assertNotIn(b"PRIVATE KEY", base64.b64decode(client_ca["ca.crt"]))
        gateway = next(i for i in items if i["metadata"]["name"] == "demo-gateway-tls")["data"]
        self.assertNotIn("ca.crt", gateway)
        for call in calls:
            self.assert_no_material(json.dumps(call["argv"]))
        self.assert_no_material("\n".join(self.output))
        self.assertIn("secret/cacerts serverside-applied", self.output)
        self.assertTrue((self.material / "istio/ca-key.pem").exists(), "--keep-material keeps the keys")

    def test_deletes_server_keys_after_registering(self):
        self.assertEqual(self.register(), 0)
        for path in k8s_certs.SERVER_KEYS:
            self.assertFalse((self.material / path).exists(), path)
        self.assertTrue((self.material / "client/tls.key").exists())
        with self.assertRaisesRegex(k8s_certs.CertError, "material_incomplete"):
            self.register()

    def test_refused_in_automation(self):
        for extra in ({"CI": "true"}, {"GITHUB_ACTIONS": "true"}, {"CLAUDE_CODE_REMOTE": "true"},
                      {"CODEX_SANDBOX": "1"}, {"AWS_ACCESS_KEY_ID": "proxy-injected"},
                      {"AWS_ENDPOINT_URL": "https://127.0.0.1:4566"}):
            with self.subTest(extra=extra):
                self.env = dict(WORKSTATION, FAKE_KUBECTL_LOG=str(self.log), **extra)
                self.assertEqual(self.register(), 1)
                self.assertEqual(delete_with(self, extra), 1)
        self.assertEqual(self.calls(), [])
        self.assertTrue(all(line.startswith("Refused (live_refused_") for line in self.output))

    def test_refuses_other_context(self):
        for context in ("demo-eks", "other-dev-eks", "arn:aws:eks:ca-central-1:000000000000:cluster/demo-dev-eks"):
            self.assertEqual(self.register(context=context), 1)
        self.assertEqual(self.calls(), [])

    def test_refuses_foreign_or_exposed_material(self):
        with self.assertRaisesRegex(k8s_certs.CertError, "material_project_mismatch"):
            k8s_certs.register("other", self.material, kubectl_binary=str(self.kubectl), env=self.env,
                               out_fn=self.output.append)
        self.material.chmod(0o755)
        with self.assertRaisesRegex(k8s_certs.CertError, "material_directory_mode"):
            self.register()
        self.material.chmod(0o700)
        (self.material / "gateway/tls.key").chmod(0o644)
        with self.assertRaisesRegex(k8s_certs.CertError, "material_file_mode"):
            self.register()
        self.assertEqual(self.calls(), [])

    def test_refuses_tampered_material(self):
        def swap(a, b):
            data = (self.material / a).read_bytes()
            (self.material / a).write_bytes((self.material / b).read_bytes())
            (self.material / b).write_bytes(data)
        cases = [
            ("key_mismatch", lambda: swap("gateway/tls.key", "webhook/tls.key")),
            ("openssl_failed:verify", lambda: swap("gateway/server-ca.crt", "gateway/client-ca.crt")),
            ("istio_chain_mismatch", lambda: (self.material / "istio/cert-chain.pem").write_text(
                (self.material / "istio/ca-cert.pem").read_text())),
            ("public_values_mismatch", lambda: self.edit_public(lambda r: r.update(expected_client_spki=[
                base64.b64encode(bytes(32)).decode()]))),
            ("public_values_mismatch", lambda: self.edit_public(lambda r: r.update(gateway_tls_secret="demo-other"))),
            ("material_project_mismatch", lambda: self.edit_public(lambda r: r.update(project="other"))),
            ("material_project_mismatch", lambda: self.edit_public(lambda r: None, top={"project": "other"})),
            ("openssl_failed:verify", lambda: (self.material / "gateway/server-ca.crt").write_bytes(
                (self.material / "webhook/ca.crt").read_bytes())),
            # public.json must describe exactly the certificates and Secrets that register sends.
            ("backend_hostname_invalid", lambda: self.edit_public(lambda r: r.update(backend_hostname="*.demo.invalid"))),
            ("gateway_san_mismatch", lambda: self.edit_public(lambda r: r.update(backend_hostname="other.demo.invalid"))),
            ("gateway_san_mismatch", lambda: self.adopt_gateway_from(OtherHost)),
            ("not_after_mismatch:gateway_server", lambda: self.edit_public(lambda r: None, not_after={
                "gateway_server": "2099-01-01T00:00:00Z"})),
            ("not_after_mismatch", lambda: self.edit_public(lambda r: None, not_after={"webhook": None})),
            ("not_after_mismatch", lambda: self.edit_public(lambda r: None, top={"not_after": {}})),
            ("secret_layout_mismatch", lambda: self.edit_secrets(lambda x: x[2].update(name="other-gateway-tls"))),
            ("secret_layout_mismatch", lambda: self.edit_secrets(lambda x: x[0].update(namespace="default"))),
            ("secret_layout_mismatch", lambda: self.edit_secrets(lambda x: x[1].update(type="Opaque"))),
            ("secret_layout_mismatch", lambda: self.edit_secrets(lambda x: x[0]["keys"].remove("ca-key.pem"))),
            ("secret_layout_mismatch", lambda: self.edit_secrets(lambda x: x.append(dict(x[3], name="demo-extra")))),
            ("secret_layout_mismatch", lambda: self.edit_secrets(lambda x: x.pop())),
        ]
        for label, tamper in cases:
            with self.subTest(label=label):
                shutil.rmtree(self.material)
                Material.copy(self.material)
                tamper()
                with self.assertRaisesRegex(k8s_certs.CertError, label):
                    self.register()
        self.assertEqual(self.calls(), [])

    def edit_public(self, change, top=None, not_after=None):
        path = self.material / "public.json"
        public = json.loads(path.read_text())
        change(public["runtime"])
        public.update(top or {})
        for name, value in (not_after or {}).items():
            if value is None:
                public["not_after"].pop(name)
            else:
                public["not_after"][name] = value
        path.write_text(json.dumps(public))

    def edit_secrets(self, change):
        path = self.material / "public.json"
        public = json.loads(path.read_text())
        change(public["secrets"])
        path.write_text(json.dumps(public))

    def adopt_gateway_from(self, other):
        # A consistent server certificate, key and CA, but issued for another hostname.
        for name in ("gateway/tls.crt", "gateway/tls.key", "gateway/server-ca.crt"):
            (self.material / name).write_bytes((other.create().directory / name).read_bytes())
        # Record its real expiry too, so that only the hostname differs.
        expiry = json.loads((other.directory / "public.json").read_text())["not_after"]["gateway_server"]
        self.edit_public(lambda r: None, not_after={"gateway_server": expiry})

    def test_refuses_certificate_dates_and_sans_outside_bounds(self):
        tool = k8s_certs.OpenSSL()
        start, _ = tool.dates(self.material / "gateway/tls.crt")

        class Stub(k8s_certs.OpenSSL):
            dates_for, names_for = {}, {}

            def dates(self, cert):
                return self.dates_for.get(Path(cert).relative_to(cert.parents[1]).as_posix()) or super().dates(cert)

            def dns_names(self, cert):
                found = self.names_for.get(Path(cert).relative_to(cert.parents[1]).as_posix())
                return found if found is not None else super().dns_names(cert)
        cases = [
            ("validity_too_long:gateway/tls.crt", {"gateway/tls.crt": (start, start + datetime.timedelta(days=92))}, {}),
            ("webhook_san_mismatch", {}, {"webhook/tls.crt": ["aws-load-balancer-controller-webhook-service.default.svc"]}),
            ("webhook_san_mismatch", {}, {"webhook/tls.crt": []}),
            ("gateway_san_mismatch", {}, {"gateway/tls.crt": [HOST, "other.demo.invalid"]}),
            ("gateway_san_mismatch", {}, {"gateway/tls.crt": []}),
        ]
        for label, dates, names in cases:
            with self.subTest(label=label):
                stub = Stub()
                stub.dates_for, stub.names_for = dates, names
                with self.assertRaisesRegex(k8s_certs.CertError, label):
                    k8s_certs.check_material(PROJECT, self.material, stub)
        with self.assertRaisesRegex(k8s_certs.CertError, "material_not_yet_valid"):
            k8s_certs.check_material(PROJECT, self.material, tool, now=start - datetime.timedelta(hours=1))
        # Every subjectAltName entry must be a DNS name; an IP or URI entry is refused.
        fake = k8s_certs.OpenSSL()
        fake.run = lambda args, step, cwd=None: "X509v3 Subject Alternative Name: \n    DNS:a.invalid, IP Address:10.0.0.1\n"
        with self.assertRaisesRegex(k8s_certs.CertError, "san_not_dns"):
            fake.dns_names(self.material / "gateway/tls.crt")
        self.assertEqual(tool.dns_names(self.material / "gateway/tls.crt"), [HOST])
        k8s_certs.check_material(PROJECT, self.material, tool)  # the untouched material passes

    def test_kubeconfig_must_be_the_tunnel_to_the_applied_cluster(self):
        for role in (None, ROLE):
            k8s_certs.check_kubeconfig(kubectl_view(role_arn=role), "demo-dev-eks", PLATFORM)
        k8s_certs.check_kubeconfig(kubectl_view(port=1024), "demo-dev-eks", PLATFORM)

        def view(edit):
            v = kubectl_view()
            edit(v, v["clusters"][0]["cluster"], v["users"][0]["user"])
            return v
        other_endpoint = "FEDCBA9876543210FEDCBA9876543210.gr7.ca-central-1.eks.amazonaws.com"
        cases = [
            ("server", view(lambda v, c, u: c.update(server="https://10.40.1.20:443"))),
            ("server", view(lambda v, c, u: c.update(server=PLATFORM["endpoint"]))),
            ("server", view(lambda v, c, u: c.update(server="http://127.0.0.1:8443"))),
            ("server", view(lambda v, c, u: c.update(server="https://127.0.0.1:80"))),
            ("server", view(lambda v, c, u: c.update(server="https://127.0.0.1:8443/proxy"))),
            ("cluster_fields", view(lambda v, c, u: c.update({"insecure-skip-tls-verify": True}))),
            ("cluster_fields", view(lambda v, c, u: c.pop("tls-server-name"))),
            ("cluster_fields", view(lambda v, c, u: c.update({"proxy-url": "http://127.0.0.1:3128"}))),
            ("cluster_fields", view(lambda v, c, u: (c.pop("certificate-authority-data"),
                                                     c.update({"certificate-authority": "/tmp/ca.crt"})))),
            ("tls_server_name", view(lambda v, c, u: c.update({"tls-server-name": other_endpoint}))),
            ("certificate_authority", view(lambda v, c, u: c.update({"certificate-authority-data": "T1RIRVI="}))),
            ("cluster_identity", view(lambda v, c, u: u["exec"]["args"].__setitem__(3, "other-dev-eks"))),
            ("cluster_identity", view(lambda v, c, u: u["exec"]["args"].__setitem__(5, "us-east-1"))),
            ("cluster_identity", view(lambda v, c, u: u["exec"].update(args=u["exec"]["args"] + ["--role-arn", "x"]))),
            ("cluster_identity", view(lambda v, c, u: u["exec"].update(args=u["exec"]["args"][:4]))),
            ("exec", view(lambda v, c, u: u["exec"].update(command="/tmp/aws"))),
            ("exec", view(lambda v, c, u: u["exec"].update(env=[{"name": "AWS_PROFILE", "value": "other"}]))),
            ("exec", view(lambda v, c, u: u["exec"].update(provideClusterInfo=True))),
            ("user_credentials", view(lambda v, c, u: u.update(token="static"))),
            ("user_credentials", view(lambda v, c, u: (u.pop("exec"), u.update({"client-key-data": "S0VZ"})))),
            ("context_binding", view(lambda v, c, u: v["contexts"][0]["context"].update(cluster="other-dev-eks"))),
            ("context_binding", view(lambda v, c, u: v["clusters"][0].update(name="other-dev-eks"))),
            ("not_a_single_context", view(lambda v, c, u: v["clusters"].append(copy.deepcopy(v["clusters"][0])))),
            ("not_a_single_context", view(lambda v, c, u: v.update(users=[]))),
            ("shape", view(lambda v, c, u: v.update({"current-context": "other-dev-eks"}))),
        ]
        for reason, candidate in cases:
            with self.subTest(reason=reason, candidate=json.dumps(candidate)[:0]):
                with self.assertRaisesRegex(k8s_certs.CertError, "kubeconfig_mismatch:" + reason):
                    k8s_certs.check_kubeconfig(candidate, "demo-dev-eks", PLATFORM)
        for reason, platform in [("platform_cluster", dict(PLATFORM, cluster_name="other-dev-eks")),
                                 ("platform_endpoint", dict(PLATFORM, endpoint="https://evil.example.com"))]:
            with self.subTest(reason=reason), self.assertRaisesRegex(k8s_certs.CertError, "kubeconfig_mismatch:" + reason):
                k8s_certs.check_kubeconfig(kubectl_view(), "demo-dev-eks", platform)

    def test_other_cluster_receives_no_secret(self):
        # Register stops after reading the kubeconfig: no namespace read or apply follows. The retired delete
        # never reads the kubeconfig at all (test_delete_is_retired).
        bad_view = kubectl_view()
        bad_view["clusters"][0]["cluster"]["server"] = "https://10.40.1.20:443"
        for label, setup in [
                ("kubeconfig_mismatch:server", lambda: self.view_file.write_text(json.dumps(bad_view))),
                ("kubeconfig_mismatch:platform_cluster", lambda: self.platform_file.write_text(json.dumps(
                    dict(PLATFORM, cluster_name="other-dev-eks")))),
                ("kubeconfig_mismatch:context_unavailable", lambda: self.env.update(FAKE_KUBECTL_MODE="view_fails"))]:
            with self.subTest(label=label):
                self.view_file.write_text(json.dumps(kubectl_view()))
                self.platform_file.write_text(json.dumps(PLATFORM))
                self.env.pop("FAKE_KUBECTL_MODE", None)
                self.log.unlink(missing_ok=True)
                setup()
                with self.assertRaisesRegex(k8s_certs.CertError, label):
                    self.register()
                self.assertTrue(all(c["argv"][2] == "config" for c in self.calls()), self.calls())
                self.log.unlink(missing_ok=True)
                self.assertEqual(delete_with(self, {}), 1)
                self.assertEqual(self.calls(), [])
        self.assertTrue((self.material / "istio/ca-key.pem").exists())
        self.log.unlink(missing_ok=True)
        self.terraform.write_text("#!/bin/sh\nexit 1\n")
        with self.assertRaisesRegex(k8s_certs.preflight.PreflightError, "terraform_output_failed:platform"):
            self.register()
        self.assertEqual(self.calls(), [])

    def test_refuses_expired_material(self):
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=40)
        with self.assertRaisesRegex(k8s_certs.CertError, "material_expires_within_a_day"):
            k8s_certs.check_material(PROJECT, self.material, k8s_certs.OpenSSL(), now=later)

    def test_refuses_material_inside_repository(self):
        with self.assertRaisesRegex(k8s_certs.CertError, "material_inside_repository"):
            self.register(material=HERE)

    def test_missing_namespace_stops_before_apply(self):
        self.env["FAKE_KUBECTL_MODE"] = "missing_namespace"
        with self.assertRaisesRegex(k8s_certs.CertError, "namespaces_missing"):
            self.register()
        self.assertEqual([c["argv"][2] for c in self.calls()], ["config", "get"])
        self.assertTrue((self.material / "istio/ca-key.pem").exists())

    def test_failed_apply_output_is_redacted_and_keys_kept(self):
        for mode in ("apply_fails", "noisy"):
            with self.subTest(mode=mode):
                self.env["FAKE_KUBECTL_MODE"] = mode
                self.output.clear()
                if mode == "apply_fails":
                    with self.assertRaisesRegex(k8s_certs.CertError, "secret_apply_failed"):
                        self.register()
                    self.assertTrue((self.material / "gateway/tls.key").exists())
                else:
                    self.assertEqual(self.register(keep_material=True), 0)
                text = "\n".join(self.output)
                self.assert_no_material(text)
                self.assertIn("[redacted", text)

    def test_delete_is_retired(self):
        # G9: the name-based delete refuses on the workstation too: no kubeconfig read, no kubectl, no fallback.
        for context in (None, "demo-dev-eks"):
            with self.subTest(context=context):
                self.output.clear()
                self.assertEqual(k8s_certs.delete(PROJECT, context=context, kubectl_binary=str(self.kubectl),
                                                  env=self.env, out_fn=self.output.append,
                                                  terraform=str(self.terraform), services=self.tmp), 1)
                self.assertEqual(self.output, [k8s_certs.DELETE_RETIRED])
                self.assertTrue(self.output[0].startswith("Refused (name_based_delete_retired)"))
        self.assertEqual(self.calls(), [])
        self.assertEqual(delete_with(self, {}), 1)
        self.assertEqual(delete_with(self, {"CI": "true"}), 1)
        self.assertTrue(self.output[-1].startswith("Refused (live_refused_in_ci)"), self.output[-1])
        self.assertEqual(self.calls(), [])


def delete_with(test, extra):
    env = dict(test.env, **extra)
    return k8s_certs.delete(PROJECT, kubectl_binary=str(test.kubectl), env=env, out_fn=test.output.append,
                            terraform=str(test.terraform), services=test.tmp)


class CommandLineTests(unittest.TestCase):
    def test_cli_generate_and_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m"
            script = str(HERE / "k8s_certs.py")
            env = dict(WORKSTATION, PYTHONDONTWRITEBYTECODE="1")
            process = subprocess.run([sys.executable, script, "generate", "--project", PROJECT, "--backend-hostname",
                                      HOST, "--trust-domain", TRUST, "--out", str(out), "--days", "7"],
                                     capture_output=True, text=True, env=env)
            self.assertEqual(process.returncode, 0, process.stderr)
            for line in material_text(out):
                self.assertNotIn(line, process.stdout + process.stderr)
            refused = subprocess.run([sys.executable, script, "register", "--project", PROJECT, "--material", str(out),
                                      "--kubectl", "/nonexistent/kubectl"], capture_output=True, text=True,
                                     env=dict(env, CI="true"))
            self.assertEqual(refused.returncode, 1)
            self.assertIn("live_refused_in_ci", refused.stdout)
            again = subprocess.run([sys.executable, script, "generate", "--project", PROJECT, "--backend-hostname",
                                    HOST, "--trust-domain", TRUST, "--out", str(out)], capture_output=True, text=True,
                                   env=env)
            self.assertEqual(again.returncode, 2)
            self.assertIn("material_directory_not_empty", again.stderr)

    def test_cli_delete_refused(self):
        script = str(HERE / "k8s_certs.py")
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "kubectl.log"
            kubectl = Path(tmp) / "kubectl"
            kubectl.write_text(FAKE_KUBECTL)
            kubectl.chmod(0o755)
            env = dict(WORKSTATION, PYTHONDONTWRITEBYTECODE="1", FAKE_KUBECTL_LOG=str(log))
            for extra, reason in (({}, "name_based_delete_retired"), ({"CI": "true"}, "live_refused_in_ci")):
                with self.subTest(reason=reason):
                    process = subprocess.run([sys.executable, script, "delete", "--project", PROJECT, "--kubectl",
                                              str(kubectl), "--terraform", "/nonexistent/terraform"],
                                             capture_output=True, text=True, env=dict(env, **extra))
                    self.assertEqual(process.returncode, 1, process.stderr)
                    self.assertIn("Refused (" + reason + ")", process.stdout)
            self.assertFalse(log.exists(), "kubectl must never run")

    def test_no_material_in_repository(self):
        tracked = subprocess.run(["git", "-C", str(HERE.parents[1]), "ls-files"], capture_output=True, text=True,
                                 check=True).stdout.splitlines()
        for name in tracked:
            path = HERE.parents[1] / name
            if path.is_file() and path.stat().st_size < 1_000_000 and not name.startswith("kubernetes/vendor/"):
                text = path.read_bytes()
                self.assertNotRegex(text, re.compile(rb"-----BEGIN (RSA |EC )?PRIVATE KEY-----"), name)


def tearDownModule():
    Material.remove()
    OtherHost.remove()


if __name__ == "__main__":
    unittest.main(verbosity=1)
