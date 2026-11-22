#!/usr/bin/env python3
"""Offline tests for k8s_runtime_input.py and k8s_runtime.py (Step 1 item 6c-A).

No cluster, no kubectl and no AWS API are used:

- the input builder reads Terraform outputs from a fake ``terraform`` that serves a
  JSON file and records every call, and ``public.json`` from a synthetic material
  directory whose private key files hold a marker that must never be read or shown;
- the plan renders with the pinned Helm (``K8S_RUNTIME_HELM``; required, the
  tests fail without it) and the existing renderer and validator, and may start no
  other process.

``MutationTests`` applies source mutations to both scripts, each removing one guard,
and requires the matching scenario to detect it.
"""
import base64
import contextlib
import copy
import datetime
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_certs  # noqa: E402
import k8s_runtime  # noqa: E402
import k8s_runtime_input  # noqa: E402
import preflight  # noqa: E402

import common  # noqa: E402  (kubernetes/tools, added to sys.path by k8s_runtime)
import render  # noqa: E402

HELM = os.environ.get("K8S_RUNTIME_HELM", "")
PROJECT = "acme"
ACCOUNT = "444455556666"
MARKER = "SYNTHETIC-PRIVATE-KEY-MARKER-0b5c"
# Built at run time so that no tracked file carries a PEM private key header.
KEY_HEADER = "-----BEGIN " + "PRIVATE KEY-----"
TARGET_GROUP = "arn:aws:elasticloadbalancing:ca-central-1:" + ACCOUNT + ":targetgroup/acme-dev-tg-gw/0123456789abcdef"
ISSUER = "https://oidc.eks.ca-central-1.amazonaws.com/id/ACMEISSUER"
VPC = "vpc-0a1b2c3d4e5f60718"
WEBHOOK_CA = b"-----BEGIN CERTIFICATE-----\nU1lOVEhFVElDIFdFQkhPT0sgQ0E=\n-----END CERTIFICATE-----\n"
SCOPE = {"environment": "dev", "partition": "aws", "region": "ca-central-1", "account_id": ACCOUNT}
RESOURCES = common.parse((preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json").read_text())["runtime"]["resources"]
STAGES = common.parse((preflight.REPOSITORY / "kubernetes/tests/expected-stages.json").read_text())["stages"]
ALLOWED_TERRAFORM = {("platform", "controller_identity"), ("platform", "platform"), ("platform", "private_ingress"),
                     ("network", "network")}

FAKE_TERRAFORM = textwrap.dedent("""\
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_TF_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    if len(args) != 4 or not args[0].startswith("-chdir=") or args[1:3] != ["output", "-json"]:
        sys.exit(64)
    root = os.path.basename(args[0][len("-chdir="):])
    outputs = json.load(open(os.environ["FAKE_TF_STATE"]))
    if args[3] not in outputs.get(root, {}):
        sys.exit(1)
    print(json.dumps(outputs[root][args[3]]))
""")


def outputs():
    cluster = PROJECT + "-dev-eks"
    return {
        "platform": {
            "controller_identity": {
                "interface_version": 1, "scope": dict(SCOPE),
                "role_arn": "arn:aws:iam::" + ACCOUNT + ":role/" + PROJECT + "-dev-role-lbc",
                "oidc_issuer": ISSUER,
                "oidc_provider_arn": "arn:aws:iam::" + ACCOUNT + ":oidc-provider/" + ISSUER[len("https://"):],
                "namespace": "kube-system", "service_account": "aws-load-balancer-controller",
                "target_group_arn": TARGET_GROUP, "cluster_name": cluster, "kubernetes_version": "1.35",
                "active_workload_az": "ca-central-1a"},
            "platform": {
                "scope": dict(SCOPE), "cluster_name": cluster,
                "cluster_arn": "arn:aws:eks:ca-central-1:" + ACCOUNT + ":cluster/" + cluster,
                "endpoint": "https://ABCDEF.gr7.ca-central-1.eks.amazonaws.com",
                "certificate_authority_data": base64.b64encode(b"synthetic cluster CA").decode(),
                "oidc_issuer": ISSUER,
                "oidc_provider_arn": "arn:aws:iam::" + ACCOUNT + ":oidc-provider/" + ISSUER[len("https://"):]},
            "private_ingress": {
                "interface_version": 1, "scope": dict(SCOPE), "target_group_arn": TARGET_GROUP, "vpc_id": VPC,
                "backend_target_port": 8443,
                # Real output fields the renderer input must not carry.
                "nlb_arn": "arn:aws:elasticloadbalancing:ca-central-1:" + ACCOUNT + ":loadbalancer/net/acme-dev-nlb/0a",
                "listener_arn": "arn:aws:elasticloadbalancing:ca-central-1:" + ACCOUNT + ":listener/net/acme/0a/0b",
                "target_group_name": "acme-dev-tg-gw", "private_subnet_ids": {"private1": "subnet-0a1b2c3d4e5f60711"}},
        },
        "network": {"network": {"interface_version": 1, "scope": dict(SCOPE), "vpc_id": VPC,
                                "endpoint_ids": {"gateway": {}, "interface": {"elasticloadbalancing": "vpce-0a"}}}},
    }


def public_json(now):
    runtime = {"project": PROJECT, "backend_hostname": "backend.acme.invalid", "trust_domain": "acme.invalid",
               "expected_client_spki": [base64.b64encode(bytes([7]) * 32).decode()],
               "webhook_ca_bundle": base64.b64encode(WEBHOOK_CA).decode()}
    runtime.update(k8s_certs.secret_names(PROJECT))
    end = (now + datetime.timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"format": k8s_certs.FORMAT, "project": PROJECT, "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runtime": runtime, "secrets": k8s_certs.public_layout(PROJECT),
            "not_after": {name: end for name, _ in k8s_certs.DATED}}


class Fixture:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="k8s-runtime-test-")).resolve()
        self.now = datetime.datetime(2026, 11, 22, 9, 0, tzinfo=datetime.timezone.utc)
        self.services = self.tmp / "services"
        for name in ("platform", "network"):
            (self.services / name).mkdir(parents=True)
        self.material = self.tmp / "material"
        old = os.umask(0o077)
        try:
            for sub in ("istio", "gateway", "client", "webhook"):
                (self.material / sub).mkdir(parents=True)
            for path in k8s_certs.MATERIAL:
                if path.endswith((".key", "ca-key.pem")):
                    (self.material / path).write_text(KEY_HEADER + "\n" + MARKER + "\n")
            (self.material / "webhook/ca.crt").write_bytes(WEBHOOK_CA)
            self.write_public(public_json(self.now))
        finally:
            os.umask(old)
        self.material.chmod(0o700)
        self.selections = self.tmp / "selections.json"
        self.write_selections({"format": "k8s-runtime-selections-v1", "project": PROJECT, "resources": RESOURCES})
        self.state = self.tmp / "terraform.json"
        self.write_outputs(outputs())
        self.log = self.tmp / "terraform.log"
        self.terraform = self.tmp / "terraform"
        self.terraform.write_text("#!" + sys.executable + "\n" + FAKE_TERRAFORM)
        self.terraform.chmod(0o755)
        self.out = self.tmp / "out" / "runtime"

    def write_public(self, data):
        path = self.material / "public.json"
        if path.exists():
            path.chmod(0o600)
        path.write_text(json.dumps(data, indent=2))
        path.chmod(0o600)

    def write_selections(self, data):
        self.selections.write_text(json.dumps(data))

    def write_outputs(self, data):
        self.state.write_text(json.dumps(data))

    def edit_outputs(self, edit):
        data = json.loads(self.state.read_text())
        edit(data)
        self.write_outputs(data)

    def edit_public(self, edit):
        data = json.loads((self.material / "public.json").read_text())
        edit(data)
        self.write_public(data)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def env(self, **extra):
        env = {key: value for key, value in os.environ.items()
               if key not in preflight.CI_MARKERS + preflight.CLOUD_SESSION_MARKERS + preflight.CREDENTIAL_VARIABLES
               and not key.startswith("AWS_ENDPOINT_URL")}
        env.update(FAKE_TF_STATE=str(self.state), FAKE_TF_LOG=str(self.log), **extra)
        return env

    def cleanup(self):
        for path in [self.tmp] + list(self.tmp.rglob("*")):
            with contextlib.suppress(OSError):
                path.chmod(0o700)
        shutil.rmtree(self.tmp, ignore_errors=True)


def build(module, fixture, project=PROJECT, account=ACCOUNT, out=None, env=None, selections=None):
    """(code, output, error code or None, files read under the material directory)."""
    lines, read = [], []
    real_read_bytes, real_read_text, real_open = Path.read_bytes, Path.read_text, open

    def note(path):
        path = Path(path).resolve()
        if fixture.material in path.parents:
            read.append(str(path.relative_to(fixture.material)))

    def read_bytes(self):
        note(self)
        return real_read_bytes(self)

    def read_text(self, *args, **kwargs):
        note(self)
        return real_read_text(self, *args, **kwargs)

    def opened(file, *args, **kwargs):
        if isinstance(file, (str, Path)):
            note(file)
        return real_open(file, *args, **kwargs)
    with mock.patch.object(Path, "read_bytes", read_bytes), mock.patch.object(Path, "read_text", read_text), \
            mock.patch("builtins.open", opened):
        try:
            code = module.build(project, account, str(fixture.material), str(selections or fixture.selections),
                                str(out or fixture.out), terraform=str(fixture.terraform), services=fixture.services,
                                env=env if env is not None else fixture.env(), now=fixture.now, out_fn=lines.append)
            error = None
        except Exception as raised:  # noqa: BLE001 - mutants raise their own InputError class
            code, error = 2, str(raised)
    return code, "\n".join(lines), error, read


def expected_document():
    data = outputs()
    identity = data["platform"]["controller_identity"]
    ingress = data["platform"]["private_ingress"]
    runtime = {k: public_json(datetime.datetime.now(datetime.timezone.utc))["runtime"][k]
               for k in k8s_runtime_input.PUBLIC_RUNTIME_FIELDS}
    return {"interface_version": 2, "fixture": False, "controller_identity": identity,
            "private_ingress": {k: ingress[k] for k in k8s_runtime_input.INGRESS_FIELDS},
            "runtime": dict(runtime, resources=RESOURCES)}


def mode(path):
    return stat.S_IMODE(Path(path).stat().st_mode)


@contextlib.contextmanager
def fixture_for(case):
    fixture = Fixture()
    try:
        yield fixture
    finally:
        fixture.cleanup()


def assert_refused(case, module, edit, reason, **kwargs):
    with fixture_for(case) as fixture:
        edit(fixture)
        code, output, error, read = build(module, fixture, **kwargs)
        case.assertEqual(code, 2, reason)
        case.assertIsNotNone(error, reason)
        case.assertIn(reason, error)
        case.assertFalse(fixture.out.exists(), "nothing is written when a check fails")
        case.assertNotIn(MARKER, output + error)


# ----------------------------------------------------------------- input scenarios
def scenario_build(case, module):
    with fixture_for(case) as fixture:
        code, output, error, read = build(module, fixture)
        case.assertEqual((code, error), (0, None))
        case.assertEqual(mode(fixture.out), 0o700)
        document = json.loads((fixture.out / "runtime-input.json").read_text())
        provenance = json.loads((fixture.out / "provenance.json").read_text())
        case.assertEqual(mode(fixture.out / "runtime-input.json"), 0o600)
        case.assertEqual(mode(fixture.out / "provenance.json"), 0o600)
        case.assertEqual(sorted(p.name for p in fixture.out.iterdir()), ["provenance.json", "runtime-input.json"])
        case.assertEqual(document, expected_document())
        case.assertEqual(sorted(document["private_ingress"]), sorted(k8s_runtime_input.INGRESS_FIELDS))
        case.assertEqual(provenance["input_sha256"], k8s_runtime_input.canonical_sha256(document))
        # Each Terraform output is recorded by root, output name and canonical SHA-256 of its full value.
        served = outputs()
        case.assertEqual(provenance["terraform_outputs"], [
            {"root": root, "output": name,
             "sha256": hashlib.sha256(json.dumps(served[root][name], sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()}
            for root, name in (("platform", "controller_identity"), ("platform", "platform"),
                               ("platform", "private_ingress"), ("network", "network"))])
        case.assertTrue(provenance["state_freshness"].startswith("NOT_VERIFIED"))
        # Certificate validity comes only from public.json not_after, and the record says so.
        case.assertTrue(any("only the not_after dates recorded in public.json" in item
                            and "not read or verified" in item for item in provenance["not_verified"]))
        case.assertIn("public_json_not_after", provenance["cross_checks"])
        case.assertNotIn("certificate_expiry", provenance["cross_checks"])
        common.metadata(document, fixture=False)
        # Only public files were read; no key, Secret value or token reached any output.
        case.assertEqual(sorted(set(read)), ["public.json", "webhook/ca.crt"])
        for text in (output, json.dumps(document), json.dumps(provenance)):
            case.assertNotIn(MARKER, text)
            case.assertNotIn("PRIVATE KEY", text)
        case.assertNotIn(document["runtime"]["webhook_ca_bundle"], output)
        calls = fixture.calls()
        case.assertEqual(len(calls), 4)
        for call in calls:
            case.assertEqual(call[1:3], ["output", "-json"])
            case.assertIn((Path(call[0][len("-chdir="):]).name, call[3]), ALLOWED_TERRAFORM)


def scenario_refused_in_ci(case, module):
    for marker in preflight.CI_MARKERS + preflight.CLOUD_SESSION_MARKERS:
        with fixture_for(case) as fixture:
            code, output, error, _ = build(module, fixture, env=fixture.env(**{marker: "1"}))
            case.assertEqual((code, error), (1, None), marker)
            case.assertIn("Refused (live_refused_", output)
            case.assertEqual(fixture.calls(), [], "no tool starts when refused")
            case.assertFalse(fixture.out.exists())
    with fixture_for(case) as fixture:
        code, output, error, _ = build(module, fixture, env=fixture.env(AWS_ACCESS_KEY_ID="proxy-injected"))
        case.assertEqual(code, 1)
        code, output, error, _ = build(module, fixture, env=fixture.env(AWS_ENDPOINT_URL="http://127.0.0.1:1"))
        case.assertEqual(code, 1)
        case.assertEqual(fixture.calls(), [])


def scenario_account_mismatch(case, module):
    other = "777788889999"
    edits = {
        "controller_identity": lambda d: d["platform"]["controller_identity"]["scope"].update(account_id=other),
        "platform": lambda d: d["platform"]["platform"]["scope"].update(account_id=other),
        "private_ingress": lambda d: d["platform"]["private_ingress"]["scope"].update(account_id=other),
        "network": lambda d: d["network"]["network"]["scope"].update(account_id=other),
    }
    for label, edit in edits.items():
        assert_refused(case, module, lambda f, e=edit: f.edit_outputs(e), "scope_mismatch:" + label)
    assert_refused(case, module, lambda f: f.edit_outputs(lambda d: d["platform"]["platform"].update(
        cluster_arn=d["platform"]["platform"]["cluster_arn"].replace(ACCOUNT, other))), "cluster_arn_mismatch")
    assert_refused(case, module, lambda f: f.edit_outputs(lambda d: d["platform"]["controller_identity"].update(
        role_arn=d["platform"]["controller_identity"]["role_arn"].replace(ACCOUNT, other))), "controller_role_mismatch")

    def foreign_target_group(data):
        arn = TARGET_GROUP.replace(ACCOUNT, other)
        data["platform"]["controller_identity"]["target_group_arn"] = arn
        data["platform"]["private_ingress"]["target_group_arn"] = arn
    assert_refused(case, module, lambda f: f.edit_outputs(foreign_target_group), "target_group_arn_scope")
    assert_refused(case, module, lambda f: None, "scope_mismatch:", account=other)


def scenario_region_mismatch(case, module):
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["network"]["network"]["scope"].update(region="us-east-1")), "scope_mismatch:network")
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["platform"]["platform"]["scope"].update(environment="prod")), "scope_mismatch:platform")


def scenario_project_mismatch(case, module):
    assert_refused(case, module, lambda f: f.edit_public(lambda d: d.update(project="other")),
                   "public_json_project_mismatch")
    assert_refused(case, module, lambda f: f.write_selections(
        {"format": "k8s-runtime-selections-v1", "project": "other", "resources": RESOURCES}),
        "selections_project_mismatch")
    assert_refused(case, module, lambda f: None, "public_json_project_mismatch", project="other")


def scenario_cluster_mismatch(case, module):
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["platform"]["platform"].update(cluster_name="other-dev-eks")), "cluster_name_mismatch")
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["platform"]["controller_identity"].update(cluster_name="other-dev-eks")), "cluster_name_mismatch")
    assert_refused(case, module, lambda f: f.edit_outputs(lambda d: d["platform"]["platform"].update(
        cluster_arn="arn:aws:eks:ca-central-1:" + ACCOUNT + ":cluster/other-dev-eks")), "cluster_arn_mismatch")
    assert_refused(case, module, lambda f: f.edit_outputs(lambda d: d["platform"]["platform"].update(
        oidc_issuer=ISSUER + "X")), "oidc_mismatch")


def scenario_target_group_mismatch(case, module):
    assert_refused(case, module, lambda f: f.edit_outputs(lambda d: d["platform"]["private_ingress"].update(
        target_group_arn=TARGET_GROUP.replace("0123456789abcdef", "fedcba9876543210"))), "target_group_arn_mismatch")


def scenario_vpc_mismatch(case, module):
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["network"]["network"].update(vpc_id="vpc-0ffffffffffffffff")), "vpc_id_mismatch")


def scenario_output_fields(case, module):
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["platform"]["controller_identity"].update(extra="x")), "controller_identity_fields")
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["platform"]["controller_identity"].pop("active_workload_az")), "controller_identity_fields")
    assert_refused(case, module, lambda f: f.edit_outputs(
        lambda d: d["platform"]["private_ingress"].pop("vpc_id")), "private_ingress_fields")


def scenario_public_expiry(case, module):
    def soon(data):
        data["not_after"]["webhook"] = "2026-11-22T20:00:00Z"
    assert_refused(case, module, lambda f: f.edit_public(soon), "material_expires_within_a_day:webhook")

    def expired(data):
        data["not_after"]["istio_root"] = "2026-11-01T00:00:00Z"
    assert_refused(case, module, lambda f: f.edit_public(expired), "material_expires_within_a_day:istio_root")


def scenario_public_layout(case, module):
    assert_refused(case, module, lambda f: f.edit_public(lambda d: d["secrets"][0].update(name="other")),
                   "secret_layout_mismatch")
    assert_refused(case, module, lambda f: f.edit_public(lambda d: d["runtime"].update(gateway_tls_secret="x-tls")),
                   "public_secret_names_mismatch")
    assert_refused(case, module, lambda f: f.edit_public(lambda d: d["runtime"].update(extra="x")),
                   "public_runtime_fields")


def scenario_webhook_ca(case, module):
    assert_refused(case, module, lambda f: (f.material / "webhook/ca.crt").write_bytes(WEBHOOK_CA + b"\n"),
                   "webhook_ca_mismatch")


def scenario_private_key_in_public(case, module):
    assert_refused(case, module, lambda f: f.edit_public(
        lambda d: d.update(note=KEY_HEADER)), "public_json_contains_private_key")


def scenario_selections(case, module):
    example = preflight.REPOSITORY / "kubernetes/environments/dev/runtime-selections.example.json"
    assert_refused(case, module, lambda f: None, "selections_placeholder", selections=example)
    bad = copy.deepcopy(RESOURCES)
    bad["gateway"]["requests"]["cpu"] = "4"
    assert_refused(case, module, lambda f: f.write_selections(
        {"format": "k8s-runtime-selections-v1", "project": PROJECT, "resources": bad}), "renderer_input_contract")


def scenario_output_location(case, module):
    # A stand-in repository root inside the temporary directory: even a build without
    # the guard can never write into the real checkout.
    with fixture_for(case) as fixture:
        fake_repository = fixture.tmp / "repository"
        (fake_repository / ".git").mkdir(parents=True)
        with mock.patch.object(preflight, "REPOSITORY", fake_repository):
            code, _, error, _ = build(module, fixture, out=fake_repository / "k8s-runtime-input")
        case.assertEqual(code, 2)
        case.assertIn("output_inside_repository", str(error))
        case.assertFalse((fake_repository / "k8s-runtime-input").exists())
    with fixture_for(case) as fixture:
        fixture.out.mkdir(parents=True, mode=0o700)
        (fixture.out / "old.json").write_text("{}")
        code, _, error, _ = build(module, fixture)
        case.assertEqual(code, 2)
        case.assertIn("output_directory_not_empty", error)
    with fixture_for(case) as fixture:
        fixture.out.mkdir(parents=True)
        fixture.out.chmod(0o755)
        code, _, error, _ = build(module, fixture)
        case.assertEqual(code, 2)
        case.assertIn("output_directory_mode", error)
        case.assertEqual(list(fixture.out.iterdir()), [])


def scenario_material_mode(case, module):
    assert_refused(case, module, lambda f: f.material.chmod(0o755), "material_directory_mode")
    assert_refused(case, module, lambda f: (f.material / "public.json").chmod(0o644), "public_json_mode")


def scenario_terraform_guard(case, module):
    with fixture_for(case) as fixture:
        with case.assertRaises(Exception) as raised:
            module.read_output(str(fixture.terraform), fixture.services, "platform", "kubeconfig", fixture.env())
        case.assertIn("terraform_output_not_allowed", str(raised.exception))
        case.assertEqual(fixture.calls(), [])
    assert_refused(case, module, lambda f: f.edit_outputs(lambda d: d["network"].pop("network")),
                   "terraform_output_failed:network")


def scenario_placeholders(case, module):
    assert_refused(case, module, lambda f: None, "placeholder_account", account="123456789012")
    assert_refused(case, module, lambda f: None, "placeholder_project", project="project")


# ------------------------------------------------------------------ plan scenarios
_RENDERED = {}


def rendered():
    """One real render of the synthetic fixture with the pinned Helm, reused by the tamper cases."""
    if not _RENDERED:
        if not HELM or not Path(HELM).is_file():
            raise AssertionError("K8S_RUNTIME_HELM must point to the pinned Helm binary (install_helm.py)")
        document = common.parse((preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json").read_text())
        objects, evidence = render.render(document, HELM, True)
        _RENDERED.update(document=document, objects=objects, evidence=evidence)
    return copy.deepcopy(_RENDERED["document"]), copy.deepcopy(_RENDERED["objects"]), \
        copy.deepcopy(_RENDERED["evidence"])


def reseal(objects, evidence):
    evidence["manifest_sha256"] = common.sha(json.dumps(objects, sort_keys=True, separators=(",", ":")).encode())
    return evidence


def split(module, objects, evidence, document):
    table = module.load_stage_table(document["runtime"]["project"])
    module.check_evidence(objects, evidence, document)
    return module.split_stages(objects, evidence, table)


def assert_plan_refused(case, module, objects, evidence, document, reason):
    with case.assertRaises(Exception) as raised:
        split(module, objects, evidence, document)
    case.assertIn(reason, str(raised.exception))


def scenario_stage_identity(case, module):
    document, objects, evidence = rendered()
    stages = split(module, objects, evidence, document)
    case.assertEqual([(name, len(chunk)) for name, chunk in stages], list(k8s_runtime.STAGE_COUNTS))
    # Same counts, different content: swap one object across a stage boundary.
    swapped = copy.deepcopy(objects)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    assert_plan_refused(case, module, swapped, reseal(swapped, copy.deepcopy(evidence)), document,
                        "stage_identity_mismatch:namespaces")
    # The TargetGroupBinding moved into the binding_writer stage, counts unchanged.
    moved = copy.deepcopy(objects)
    moved[-1], moved[-3] = moved[-3], moved[-1]
    assert_plan_refused(case, module, moved, reseal(moved, copy.deepcopy(evidence)), document,
                        "stage_identity_mismatch:binding_writer")
    for label, edit in (("apiVersion", lambda o: o.update(apiVersion="v2")),
                        ("namespace", lambda o: o["metadata"].update(namespace="default")),
                        ("name", lambda o: o["metadata"].update(name="acme-extra"))):
        changed = copy.deepcopy(objects)
        edit(changed[40])
        assert_plan_refused(case, module, changed, reseal(changed, copy.deepcopy(evidence)), document,
                            "stage_identity_mismatch:istiod")


def scenario_stage_order(case, module):
    document, objects, evidence = rendered()
    split(module, objects, evidence, document)
    # Two objects swapped inside one stage: counts and identity sets are unchanged.
    for stage, first, second in (("base", 2, 3), ("istiod", 31, 40), ("ingress", 60, 61)):
        swapped = copy.deepcopy(objects)
        swapped[first], swapped[second] = swapped[second], swapped[first]
        case.assertEqual({validate_identity(o) for o in swapped}, {validate_identity(o) for o in objects})
        case.assertNotEqual(swapped, objects)
        assert_plan_refused(case, module, swapped, reseal(swapped, copy.deepcopy(evidence)), document,
                            "stage_identity_order:" + stage)


def validate_identity(obj):
    return (obj["apiVersion"], obj["kind"], obj["metadata"].get("namespace", ""), obj["metadata"]["name"])


def scenario_forbidden_objects(case, module):
    document, objects, evidence = rendered()
    table = module.load_stage_table(document["runtime"]["project"])
    chunk_objects = copy.deepcopy(objects)
    binding = next(o for o in chunk_objects if o["kind"] == "ClusterRoleBinding")
    binding["roleRef"]["name"] = "cluster-admin"
    with case.assertRaises(Exception) as raised:
        module.split_stages(chunk_objects, evidence, table)
    case.assertIn("cluster_admin_binding", str(raised.exception))
    # A Secret disguised with a reviewed identity is still refused by kind.
    disguised = copy.deepcopy(objects)
    disguised[0]["kind"] = "Secret"
    table_with_secret = [(name, [("v1", "Secret", "", "istio-system") if row == ("v1", "Namespace", "", "istio-system")
                                 else row for row in rows]) for name, rows in table]
    with case.assertRaises(Exception) as raised:
        module.split_stages(disguised, evidence, table_with_secret)
    case.assertIn("forbidden_kind:Secret", str(raised.exception))


def scenario_evidence(case, module):
    document, objects, evidence = rendered()
    edits = {
        "stage_evidence": lambda e: e["stages"].update(namespaces=3, base=15),
        "manifest_evidence": lambda e: e.update(manifest_sha256="0" * 64),
        "runtime_contract_version": lambda e: e.update(runtime_contract_version=3),
        "image_lock_evidence": lambda e: e.update(image_lock_sha256="0" * 64),
        "input_evidence": lambda e: e.update(input_sha256="0" * 64),
        "render_evidence_status": lambda e: e.update(actual_helm_renders=3),
        "pinned_artifact_evidence": lambda e: e.update(helm_sha256="0" * 64),
    }
    for reason, edit in edits.items():
        tampered = copy.deepcopy(evidence)
        edit(tampered)
        assert_plan_refused(case, module, objects, tampered, document, reason)
    shorter = copy.deepcopy(objects)[:-1]
    assert_plan_refused(case, module, shorter, reseal(shorter, copy.deepcopy(evidence)), document, "resource_count")


def scenario_stage_table(case, module):
    original = common.parse(k8s_runtime.STAGE_TABLE.read_text())
    edits = {
        "stage_table_counts": lambda t: t["stages"][0]["objects"].pop(),
        "stage_table_duplicate": lambda t: t["stages"][1]["objects"].__setitem__(0, t["stages"][1]["objects"][1]),
        "stage_table_inventory_mismatch": lambda t: t["stages"][0]["objects"][0].__setitem__(3, "other"),
        "stage_table_format": lambda t: t.update(format="k8s-runtime-stages-v0"),
    }
    with tempfile.TemporaryDirectory() as tmp:
        for reason, edit in edits.items():
            table = copy.deepcopy(original)
            edit(table)
            path = Path(tmp) / (reason + ".json")
            path.write_text(json.dumps(table))
            with mock.patch.object(module, "STAGE_TABLE", path), case.assertRaises(Exception) as raised:
                module.load_stage_table(PROJECT)
            case.assertIn(reason, str(raised.exception))


def scenario_plan_report(case, module):
    document, objects, evidence = rendered()
    with mock.patch.object(module.render, "render", return_value=(copy.deepcopy(objects), copy.deepcopy(evidence))):
        report = module.plan(preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json", HELM or "unused", True)
    project = document["runtime"]["project"]
    case.assertEqual((report["status"], report["executed"], report["kubernetes_api_calls"], report["aws_api_calls"]),
                     ("planned", False, 0, 0))
    case.assertEqual([(s["name"], s["count"]) for s in report["stages"]], list(k8s_runtime.STAGE_COUNTS))
    for stage, reviewed in zip(report["stages"], STAGES):
        case.assertEqual([[o["apiVersion"], o["kind"], o["namespace"], o["name"]] for o in stage["objects"]],
                         common.fill(reviewed["objects"], project), stage["name"])
    writer = "system:serviceaccount:" + project + "-ingress:" + project + "-binding-writer"
    actors = {(o["kind"], o["actor"]) for s in report["stages"] for o in s["objects"]}
    case.assertIn(("TargetGroupBinding", writer), actors)
    case.assertEqual({a for k, a in actors if k != "TargetGroupBinding"}, {"operator"})
    case.assertEqual(report["stages"][-1]["execution"], "BLOCKED (binding-writer method not approved)")
    case.assertTrue(all(s["execution"] == "not executed" for s in report["stages"][:-1]))
    secrets = {s["name"]: [(x["namespace"], x["name"]) for x in s["required_secrets"]] for s in report["stages"]}
    case.assertEqual(secrets["controller"], [("kube-system", "aws-load-balancer-controller-tls")])
    case.assertEqual(secrets["istiod"], [("istio-system", "cacerts")])
    case.assertEqual(secrets["gateway"], [(project + "-ingress", project + "-gateway-tls"),
                                          (project + "-ingress", project + "-gateway-client-cacert")])
    case.assertEqual(secrets["namespaces"], [])
    case.assertIn("NOT_TESTED", report["actors"]["binding_writer_method"])
    case.assertEqual(report["not_implemented"], ["status", "apply", "destroy"])
    case.assertTrue(any("elasticloadbalancing" in x for x in report["stages"][-1]["prerequisites"]))


def scenario_plan_runs_validator(case, module):
    document, objects, evidence = rendered()
    service = next(o for o in objects if o["kind"] == "Service" and o["metadata"]["name"].endswith("-gateway"))
    service["spec"]["type"] = "LoadBalancer"
    with mock.patch.object(module.render, "render", return_value=(objects, reseal(objects, evidence))), \
            case.assertRaises(Exception) as raised:
        module.plan(preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json", HELM or "unused", True)
    case.assertIn("private ClusterIP only", str(raised.exception))


class InputTests(unittest.TestCase):
    def test_builds_the_input_from_outputs_public_json_and_selections(self):
        scenario_build(self, k8s_runtime_input)

    def test_refused_in_ci_cloud_sessions_and_with_placeholder_credentials(self):
        scenario_refused_in_ci(self, k8s_runtime_input)

    def test_account_mismatches_are_refused(self):
        scenario_account_mismatch(self, k8s_runtime_input)

    def test_region_and_environment_mismatches_are_refused(self):
        scenario_region_mismatch(self, k8s_runtime_input)

    def test_project_mismatches_are_refused(self):
        scenario_project_mismatch(self, k8s_runtime_input)

    def test_cluster_and_oidc_mismatches_are_refused(self):
        scenario_cluster_mismatch(self, k8s_runtime_input)

    def test_target_group_mismatch_is_refused(self):
        scenario_target_group_mismatch(self, k8s_runtime_input)

    def test_vpc_mismatch_is_refused(self):
        scenario_vpc_mismatch(self, k8s_runtime_input)

    def test_output_field_sets_are_exact(self):
        scenario_output_fields(self, k8s_runtime_input)

    def test_expiring_material_is_refused(self):
        scenario_public_expiry(self, k8s_runtime_input)

    def test_public_layout_and_secret_names(self):
        scenario_public_layout(self, k8s_runtime_input)

    def test_webhook_ca_must_match_the_public_file(self):
        scenario_webhook_ca(self, k8s_runtime_input)

    def test_private_key_in_public_json_is_refused(self):
        scenario_private_key_in_public(self, k8s_runtime_input)

    def test_selections_placeholders_and_contract(self):
        scenario_selections(self, k8s_runtime_input)

    def test_output_location_and_modes(self):
        scenario_output_location(self, k8s_runtime_input)

    def test_material_modes(self):
        scenario_material_mode(self, k8s_runtime_input)

    def test_only_the_reviewed_terraform_outputs_are_read(self):
        scenario_terraform_guard(self, k8s_runtime_input)

    def test_placeholder_account_and_project(self):
        scenario_placeholders(self, k8s_runtime_input)


class PlanTests(unittest.TestCase):
    def test_fixture_plan_with_the_pinned_helm_starts_only_helm(self):
        real_run = subprocess.run
        started = []

        def guarded(args, *rest, **kwargs):
            started.append(args[0])
            if args[0] != HELM:
                raise AssertionError("plan may start only the pinned Helm, not " + str(args[0]))
            return real_run(args, *rest, **kwargs)
        buffer = io.StringIO()
        with mock.patch.object(subprocess, "run", guarded), contextlib.redirect_stdout(buffer):
            code = k8s_runtime.main(["plan", "--input", str(preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json"),
                                     "--helm", HELM, "--fixture", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertTrue(started and set(started) == {HELM})
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["resource_count"], 62)
        self.assertEqual([(s["name"], s["count"]) for s in report["stages"]], list(k8s_runtime.STAGE_COUNTS))

    def test_built_input_plans_with_the_pinned_helm(self):
        fixture = Fixture()
        try:
            code, _, error, _ = build(k8s_runtime_input, fixture)
            self.assertEqual((code, error), (0, None))
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = k8s_runtime.main(["plan", "--input", str(fixture.out / "runtime-input.json"), "--helm", HELM])
            self.assertEqual(code, 0)
            output = buffer.getvalue()
            self.assertIn("Kubernetes runtime plan for project acme", output)
            self.assertIn("Stage 9 ingress (2 objects, BLOCKED (binding-writer method not approved))", output)
            self.assertIn("Plan only: nothing was applied", output)
            self.assertNotIn(MARKER, output)
            with contextlib.redirect_stderr(io.StringIO()) as error_output:
                self.assertEqual(k8s_runtime.main(["plan", "--input", str(fixture.out / "runtime-input.json"),
                                                   "--helm", HELM, "--fixture"]), 2)
            self.assertIn("manifest/fixture boundary", error_output.getvalue())
        finally:
            fixture.cleanup()

    def test_stage_identities_are_exact(self):
        scenario_stage_identity(self, k8s_runtime)

    def test_stage_order_is_exact(self):
        scenario_stage_order(self, k8s_runtime)

    def test_forbidden_objects_are_refused(self):
        scenario_forbidden_objects(self, k8s_runtime)

    def test_render_evidence_is_rechecked(self):
        scenario_evidence(self, k8s_runtime)

    def test_stage_table_is_reviewed(self):
        scenario_stage_table(self, k8s_runtime)

    def test_plan_report(self):
        scenario_plan_report(self, k8s_runtime)

    def test_plan_runs_the_validator(self):
        scenario_plan_runs_validator(self, k8s_runtime)

    def test_fixture_input_without_flag_and_missing_helm_are_refused(self):
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(k8s_runtime.main(["plan", "--input", str(preflight.REPOSITORY /
                                               "kubernetes/tests/fixtures/runtime.json"), "--helm", HELM]), 2)
            self.assertEqual(k8s_runtime.main(["plan", "--input", str(preflight.REPOSITORY /
                                               "kubernetes/tests/fixtures/runtime.json"), "--helm", "/nonexistent",
                                               "--fixture"]), 2)
        self.assertIn("manifest/fixture boundary", error.getvalue())


# Each mutation removes one guard; the scenario must fail. (file, old, new, scenario)
INPUT = "k8s_runtime_input.py"
PLAN = "k8s_runtime.py"
MUTATIONS = [
    ("automation_not_refused", INPUT, "    refusal = preflight.automation_refusal(environment)\n",
     "    refusal = None\n", scenario_refused_in_ci),
    ("scope_unchecked", INPUT, '    require(scope == expected, "scope_mismatch:" + label)\n', "    pass\n",
     scenario_account_mismatch),
    ("region_unchecked", INPUT, '    require(scope == expected, ',
     '    require({k: v for k, v in scope.items() if k != "region"} == {k: v for k, v in expected.items() if k != "region"}, ',
     scenario_region_mismatch),
    ("cluster_name_unchecked", INPUT, 'identity["cluster_name"] == cluster and platform.get("cluster_name") == cluster',
     "True", scenario_cluster_mismatch),
    ("cluster_arn_unchecked", INPUT, '    require(platform.get("cluster_arn") == ', '    require(True or platform.get("cluster_arn") == ',
     scenario_cluster_mismatch),
    ("oidc_unchecked", INPUT, 'identity["oidc_issuer"] == platform.get("oidc_issuer")', 'True', scenario_cluster_mismatch),
    ("role_unchecked", INPUT, '    require(identity["role_arn"] == ', '    require(True or identity["role_arn"] == ',
     scenario_account_mismatch),
    ("target_group_unchecked", INPUT, 'identity["target_group_arn"] == ingress["target_group_arn"]', "True",
     scenario_target_group_mismatch),
    ("target_group_scope_unchecked", INPUT, '    require(str(ingress["target_group_arn"]).startswith(',
     '    require(True or str(ingress["target_group_arn"]).startswith(', scenario_account_mismatch),
    ("vpc_unchecked", INPUT, 'ingress["vpc_id"] == network.get("vpc_id")', "True", scenario_vpc_mismatch),
    ("controller_fields_loose", INPUT, "set(identity) == set(CONTROLLER_FIELDS)", "set(CONTROLLER_FIELDS) <= set(identity)",
     scenario_output_fields),
    ("ingress_not_projected", INPUT, "    private_ingress = {key: ingress[key] for key in INGRESS_FIELDS}\n",
     "    private_ingress = dict(ingress)\n", scenario_build),
    ("expiry_unchecked", INPUT, '        require(end >= now + datetime.timedelta(days=1), ', '        require(True or end >= now, ',
     scenario_public_expiry),
    ("layout_unchecked", INPUT, '    require(public.get("secrets") == k8s_certs.public_layout(project), ',
     '    require(True or public.get("secrets") == k8s_certs.public_layout(project), ', scenario_public_layout),
    ("webhook_ca_unchecked", INPUT, 'ca.is_file() and runtime["webhook_ca_bundle"] == ', 'ca.is_file() or runtime["webhook_ca_bundle"] == ',
     scenario_webhook_ca),
    ("private_key_unchecked", INPUT, '    require(b"PRIVATE KEY" not in raw, ', '    require(True or b"PRIVATE KEY" not in raw, ',
     scenario_private_key_in_public),
    ("placeholders_allowed", INPUT, '    require(not placeholder(selections), ', '    require(True or not placeholder(selections), ',
     scenario_selections),
    ("renderer_contract_skipped", INPUT, "        common.metadata(document, fixture=False)\n", "        pass\n",
     scenario_selections),
    ("output_in_repository_allowed", INPUT, '    require(not k8s_certs.inside_repository(target), "output_inside_repository")\n',
     "", scenario_output_location),
    ("output_directory_mode_unchecked", INPUT,
     '        require(stat.S_IMODE(target.stat().st_mode) == 0o700, "output_directory_mode: expected 0700")\n', "",
     scenario_output_location),
    ("output_file_world_readable", INPUT, "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)",
     "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644); os.chmod(target / name, 0o644)", scenario_build),
    ("material_mode_unchecked", INPUT, '    require(material.is_dir() and not stat.S_IMODE(material.stat().st_mode) & 0o077,',
     '    require(material.is_dir() or not stat.S_IMODE(material.stat().st_mode) & 0o077,', scenario_material_mode),
    ("terraform_outputs_unrestricted", INPUT, "    if (root_name, name) not in ALLOWED_OUTPUTS:\n", "    if False:\n",
     scenario_terraform_guard),
    ("placeholder_account_allowed", INPUT, '    require(account_id not in preflight.PLACEHOLDER_ACCOUNTS, ', '    require(True, ',
     scenario_placeholders),
    ("stage_order_unchecked", PLAN, '        require(identities == list(expected), ', '        require(True, ',
     scenario_stage_order),
    ("output_digests_missing", INPUT, '"sha256": canonical_sha256(value)}', '"sha256": "0" * 64}', scenario_build),
    ("certificate_boundary_hidden", INPUT, "                         CERTIFICATE_BOUNDARY],", "                         ],",
     scenario_build),
    ("stage_identity_unchecked", PLAN, '        require(set(identities) == set(expected), ', '        require(True, ',
     scenario_stage_identity),
    ("forbidden_kinds_allowed", PLAN, '            require(kind not in FORBIDDEN_KINDS, ', '            require(True, ',
     scenario_forbidden_objects),
    ("cluster_admin_allowed", PLAN, '            require(obj.get("roleRef", {}).get("name") != "cluster-admin", ',
     '            require(True, ', scenario_forbidden_objects),
    ("stage_evidence_unchecked", PLAN, '    require(list((evidence.get("stages") or {}).items()) == list(STAGE_COUNTS), ',
     '    require(True, ', scenario_evidence),
    ("manifest_evidence_unchecked", PLAN, '    require(evidence.get("manifest_sha256") == ', '    require(True or evidence.get("manifest_sha256") == ',
     scenario_evidence),
    ("contract_version_unchecked", PLAN, 'and evidence["runtime_contract_version"] == CONTRACT_VERSION', "",
     scenario_evidence),
    ("image_lock_evidence_unchecked", PLAN, '    require(evidence.get("image_lock_sha256") == ',
     '    require(True or evidence.get("image_lock_sha256") == ', scenario_evidence),
    ("input_evidence_unchecked", PLAN, '    require(evidence.get("input_sha256") == ', '    require(True or evidence.get("input_sha256") == ',
     scenario_evidence),
    ("stage_table_inventory_unchecked", PLAN, '    require(set(rows) == inventory, ', '    require(True, ',
     scenario_stage_table),
    ("validator_skipped", PLAN, "    validate.verify(objects, document, fixture)\n", "", scenario_plan_runs_validator),
    ("writer_actor_hidden", PLAN, '    if obj["kind"] == "TargetGroupBinding":\n', "    if False:\n",
     scenario_plan_report),
    ("ingress_not_blocked", PLAN, '"BLOCKED (binding-writer method not approved)" if name == "ingress" else ', "",
     scenario_plan_report),
]


def mutant(filename, old, new):
    source = (HERE / filename).read_text()
    if source.count(old) != 1:
        raise AssertionError("mutation target not found exactly once: " + filename + ": " + old.strip())
    spec = importlib.util.spec_from_loader(filename[:-3] + "_mutant", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(HERE / filename)
    exec(compile(source.replace(old, new), module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


class MutationTests(unittest.TestCase):
    def test_each_guard_mutation_is_detected(self):
        self.assertEqual(len(MUTATIONS), 39)
        undetected = []
        for name, filename, old, new, scenario in MUTATIONS:
            module = mutant(filename, old, new)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, module)
            except AssertionError:
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
