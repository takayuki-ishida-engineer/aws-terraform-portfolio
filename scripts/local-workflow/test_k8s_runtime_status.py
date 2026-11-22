#!/usr/bin/env python3
"""Offline tests for ``k8s_runtime.py status`` and its preflight safety gate (Step 1 item 6c-B1).

No cluster, no real kubectl and no AWS API are used. A fake ``kubectl`` serves a
synthetic cluster from a JSON file and records every call; a fake ``terraform``
serves the applied outputs (from ``test_k8s_runtime``). The bundle comes from one
real render with the pinned Helm (``K8S_RUNTIME_HELM``; required), reused by every
scenario.

``MutationTests`` applies source mutations to ``k8s_runtime.py``, each removing one
status or preflight guard, and requires the matching scenario to detect it.
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eks_tunnel  # noqa: E402
import k8s_runtime  # noqa: E402
import k8s_runtime_input  # noqa: E402
import preflight  # noqa: E402
import test_k8s_runtime as base  # noqa: E402

import common  # noqa: E402  (kubernetes/tools, on sys.path through k8s_runtime)
import render  # noqa: E402

TOKEN_MARKER = "SYNTHETIC-TOKEN-MARKER-7f31"
FAKE_KUBECTL = textwrap.dedent("""\
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_KUBE_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    state = json.load(open(os.environ["FAKE_KUBE_STATE"]))
    if args[:2] != ["--context", state["context"]] or not args[2].startswith("--request-timeout="):
        print("error: context " + args[1] + " does not exist", file=sys.stderr)
        sys.exit(1)
    rest = args[3:]
    if rest[:2] == ["config", "view"]:
        print(json.dumps(state["kubeconfig"]))
        sys.exit(0)
    if rest[:1] == ["version"]:
        if state.get("version_error"):
            print(state["version_error"], file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"clientVersion": {"major": "1", "minor": "35"}, "serverVersion": state["version"]}))
        sys.exit(0)
    if rest[:1] == ["get"]:
        namespace = rest[4] if rest[3:4] == ["-n"] else ""
        key = rest[1] + "|" + namespace + "|" + rest[2]
        if key in state.get("errors", {}):
            print(state["errors"][key], file=sys.stderr)
            sys.exit(1)
        if key in state.get("raw", {}):
            print(state["raw"][key])
            sys.exit(0)
        if key in state["objects"]:
            print(json.dumps(state["objects"][key]))
        sys.exit(0)
    sys.exit(64)
""")


def key_of(row):
    return k8s_runtime.resource_argument(row["apiVersion"], row["kind"]) + "|" + row["namespace"] + "|" + row["name"]


def make_ready(obj):
    """A synthetic object as an applied, healthy cluster would return it."""
    obj = copy.deepcopy(obj)
    obj["metadata"]["generation"] = 1
    obj["metadata"]["uid"] = "00000000-0000-0000-0000-000000000001"
    obj["metadata"].setdefault("annotations", {})["synthetic/token"] = TOKEN_MARKER
    kind = obj["kind"]
    if kind == "Namespace":
        obj["status"] = {"phase": "Active"}
    elif kind == "CustomResourceDefinition":
        obj["status"] = {"conditions": [{"type": "NamesAccepted", "status": "True"},
                                        {"type": "Established", "status": "True"}]}
    elif kind == "Deployment":
        replicas = obj["spec"]["replicas"]
        obj["status"] = {"observedGeneration": 1, "replicas": replicas, "updatedReplicas": replicas,
                         "readyReplicas": replicas, "availableReplicas": replicas,
                         "conditions": [{"type": "Available", "status": "True"},
                                        {"type": "Progressing", "status": "True"}]}
    elif kind == "ValidatingAdmissionPolicy":
        obj["status"] = {"observedGeneration": 1, "typeChecking": {}}
    elif kind == "TargetGroupBinding":
        obj["status"] = {"observedGeneration": 1}
    elif kind == "ConfigMap":
        obj.setdefault("data", {})["synthetic-token"] = TOKEN_MARKER
    return obj


class Cluster:
    """A built input, fake terraform outputs, a fake kubectl and a synthetic cluster."""
    _bundle = {}

    def __init__(self):
        self.base = base.Fixture()
        code, _, error, _ = base.build(k8s_runtime_input, self.base)
        if (code, error) != (0, None):
            raise AssertionError("input fixture failed: " + str(error))
        self.input = self.base.out / "runtime-input.json"
        self.base.log.unlink()  # count only the terraform calls status makes
        self.document = common.parse(self.input.read_text())
        self.project = self.document["runtime"]["project"]
        self.context = self.project + "-dev-eks"
        objects, evidence = self.bundle(self.document)
        self.rows = [{"apiVersion": o["apiVersion"], "kind": o["kind"], "namespace": o["metadata"].get("namespace", ""),
                      "name": o["metadata"]["name"]} for o in objects]
        platform = base.outputs()["platform"]["platform"]
        self.state = {"context": self.context, "kubeconfig": eks_tunnel.kubeconfig_document(platform, 8443),
                      "version": {"major": "1", "minor": "35+", "gitVersion": "v1.35.2-eks-synthetic"},
                      "objects": {key_of(r): make_ready(o) for r, o in zip(self.rows, objects)
                                  if o["kind"] != "TargetGroupBinding"},
                      "errors": {}, "raw": {}}
        self.state_file = self.base.tmp / "cluster.json"
        self.log = self.base.tmp / "kubectl.log"
        self.kubectl = self.base.tmp / "kubectl"
        self.kubectl.write_text("#!" + sys.executable + " -S\n" + FAKE_KUBECTL)
        self.kubectl.chmod(0o755)
        self.save()

    @classmethod
    def bundle(cls, document):
        key = json.dumps(document, sort_keys=True)
        if key not in cls._bundle:
            if not base.HELM or not Path(base.HELM).is_file():
                raise AssertionError("K8S_RUNTIME_HELM must point to the pinned Helm binary (install_helm.py)")
            cls._bundle[key] = render.render(document, base.HELM, False)
        objects, evidence = cls._bundle[key]
        return copy.deepcopy(objects), copy.deepcopy(evidence)

    def save(self):
        self.state_file.write_text(json.dumps(self.state))

    def edit(self, edit):
        edit(self.state)
        self.save()

    def row(self, kind, name_suffix=""):
        return next(r for r in self.rows if r["kind"] == kind and r["name"].endswith(name_suffix))

    def object(self, kind, name_suffix=""):
        return self.state["objects"][key_of(self.row(kind, name_suffix))]

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def gets(self):
        return [c for c in self.calls() if c[3:4] == ["get"]]

    def env(self, **extra):
        return self.base.env(FAKE_KUBE_STATE=str(self.state_file), FAKE_KUBE_LOG=str(self.log), **extra)

    def cleanup(self):
        self.base.cleanup()


@contextlib.contextmanager
def cluster_for(case):
    cluster = Cluster()
    try:
        yield cluster
    finally:
        cluster.cleanup()


def run(module, cluster, context=None, env=None, input_path=None):
    """(code, report or None, printed lines, error code or None, number of renders)."""
    lines, renders = [], []
    real = Cluster.bundle

    def fake_render(document, helm, fixture):
        renders.append(fixture)
        return real(document)
    with mock.patch.object(render, "render", side_effect=fake_render):
        try:
            code, report = module.status(input_path or cluster.input, base.HELM or "unused", context,
                                         str(cluster.kubectl), str(cluster.base.terraform), cluster.base.services,
                                         env if env is not None else cluster.env(), 20, lines.append)
            error = None
        except Exception as raised:  # noqa: BLE001 - mutants raise their own StatusError class
            code, report, error = 2, None, str(raised)
    return code, report, lines, error, len(renders)


def by_name(report):
    return {s["name"]: s for s in report["stages"]}


def find(report, kind, name_suffix=""):
    return next(o for s in report["stages"] for o in s["objects"] if o["kind"] == kind and o["name"].endswith(name_suffix))


def assert_stopped(case, module, cluster, reason, **kwargs):
    code, report, lines, error, _ = run(module, cluster, **kwargs)
    case.assertEqual(code, 2, reason)
    case.assertIsNone(report)
    case.assertIsNotNone(error, reason)
    case.assertIn(reason, error)
    case.assertEqual(cluster.gets(), [], "no object is read when the gate refuses")
    return error


# ----------------------------------------------------------------------------- scenarios
def scenario_ready(case, module):
    with cluster_for(case) as cluster:
        code, report, lines, error, renders = run(module, cluster)
        case.assertEqual((code, error), (0, None))
        stages = by_name(report)
        case.assertEqual([s["name"] for s in report["stages"]], [n for n, _ in k8s_runtime.STAGE_COUNTS])
        for name, _ in k8s_runtime.STAGE_COUNTS[:-1]:
            case.assertEqual(stages[name]["state"], "APPLIED_READY", name)
        case.assertEqual(stages["ingress"]["state"], "BLOCKED")
        case.assertEqual((report["status"], report["changes_made"], report["runtime_ready"], report["functional"]),
                         ("collected", False, False, "NOT_TESTED"))
        case.assertEqual(report["summary"], {"objects": 62, "present": 61, "missing": 1, "unknown": 0, "ready": 25,
                                             "not_ready": 0, "existence_only": 36, "not_verifiable": 0})
        case.assertEqual(report["server_version"], "1.35")
        # Every object carries its identity, stage, actor, presence, generations, readiness and reasons.
        for stage in report["stages"]:
            for row in stage["objects"]:
                case.assertEqual(set(row), {"apiVersion", "kind", "namespace", "name", "stage", "actor", "presence",
                                            "generation", "observed_generation", "observed", "readiness", "reasons"})
                case.assertEqual(row["stage"], stage["name"])
        tgb = find(report, "TargetGroupBinding")
        case.assertEqual((tgb["presence"], tgb["actor"]),
                         ("MISSING", "system:serviceaccount:acme-ingress:acme-binding-writer"))
        deployment = find(report, "Deployment", "-gateway")
        case.assertEqual((deployment["generation"], deployment["observed_generation"], deployment["observed"],
                          deployment["readiness"]), (1, 1, True, "READY"))
        case.assertEqual(find(report, "ConfigMap", "values-acme-v1")["readiness"], "NOT_APPLICABLE")
        case.assertTrue(all(not s["secrets_checked"] for s in report["stages"]))
        # Only the reviewed read-only kubectl commands, in order; 62 gets with exact arguments.
        calls = cluster.calls()
        case.assertEqual([c[3:] for c in calls[:2]], [["config", "view", "--minify", "--raw", "-o", "json"],
                                                      ["version", "-o", "json"]])
        expected_gets = [["get", k8s_runtime.resource_argument(r["apiVersion"], r["kind"]), r["name"]] +
                         (["-n", r["namespace"]] if r["namespace"] else []) + ["--ignore-not-found", "-o", "json"]
                         for r in cluster.rows]
        case.assertEqual([c[3:] for c in calls[2:]], expected_gets)
        case.assertTrue(all(c[:2] == ["--context", cluster.context] and c[2] == "--request-timeout=20s" for c in calls))
        case.assertEqual(renders, 1)
        text = module.status_text(report)
        for output in (json.dumps(report), text, "\n".join(lines)):
            case.assertNotIn(TOKEN_MARKER, output)
            case.assertNotIn("certificate-authority-data", output)
        case.assertIn("Application and network behaviour: NOT_TESTED", text)


def scenario_empty(case, module):
    with cluster_for(case) as cluster:
        cluster.edit(lambda s: s["objects"].clear())
        code, report, _, error, _ = run(module, cluster)
        case.assertEqual((code, error), (0, None))
        states = {s["name"]: s["state"] for s in report["stages"]}
        case.assertEqual(states.pop("ingress"), "BLOCKED")
        case.assertEqual(set(states.values()), {"NOT_APPLIED"})
        case.assertEqual(report["summary"]["missing"], 62)


def scenario_refused(case, module):
    for marker in preflight.CI_MARKERS + preflight.CLOUD_SESSION_MARKERS:
        with cluster_for(case) as cluster:
            code, report, lines, error, renders = run(module, cluster, env=cluster.env(**{marker: "1"}))
            case.assertEqual((code, report, error, renders), (1, None, None, 0), marker)
            case.assertIn("Refused (live_refused_", "\n".join(lines))
            case.assertEqual(cluster.calls(), [])
            case.assertEqual(cluster.base.calls(), [])
    with cluster_for(case) as cluster:
        for extra in ({"AWS_SECRET_ACCESS_KEY": "proxy-injected"}, {"AWS_ENDPOINT_URL_EKS": "http://127.0.0.1:1"}):
            code, _, _, _, _ = run(module, cluster, env=cluster.env(**extra))
            case.assertEqual(code, 1, extra)
        case.assertEqual(cluster.calls(), [])


def scenario_context(case, module):
    with cluster_for(case) as cluster:
        code, report, lines, error, renders = run(module, cluster, context="other-dev-eks")
        case.assertEqual((code, report), (2, None))
        case.assertIn("context_mismatch", error)
        case.assertEqual((renders, cluster.calls(), cluster.base.calls()), (0, [], []),
                         "a foreign context is refused before rendering or any tool")
    variants = {
        "insecure": lambda k: k["clusters"][0]["cluster"].update({"insecure-skip-tls-verify": True}),
        "public_server": lambda k: k["clusters"][0]["cluster"].update(server="https://ABCDEF.gr7.ca-central-1.eks.amazonaws.com"),
        "other_ca": lambda k: k["clusters"][0]["cluster"].update({"certificate-authority-data": "b3RoZXI="}),
        "other_host": lambda k: k["clusters"][0]["cluster"].update({"tls-server-name": "other.eks.amazonaws.com"}),
        "static_token": lambda k: k["users"][0].update(user={"token": TOKEN_MARKER}),
        "other_cluster_token": lambda k: k["users"][0]["user"]["exec"]["args"].__setitem__(3, "other-dev-eks"),
    }
    for label, edit in variants.items():
        with cluster_for(case) as cluster:
            cluster.edit(lambda s, e=edit: e(s["kubeconfig"]))
            error = assert_stopped(case, module, cluster, "kubeconfig_mismatch:")
            case.assertNotIn(TOKEN_MARKER, error, label)


def scenario_outputs(case, module):
    with cluster_for(case) as cluster:
        cluster.base.edit_outputs(lambda d: d["platform"]["platform"]["scope"].update(account_id="777788889999"))
        assert_stopped(case, module, cluster, "applied_outputs:scope_mismatch:platform")
    with cluster_for(case) as cluster:
        # The applied cluster now asks for another Kubernetes version than the input carries.
        cluster.base.edit_outputs(lambda d: d["platform"]["controller_identity"].update(kubernetes_version="1.36"))
        assert_stopped(case, module, cluster, "input_differs_from_applied_outputs")
    with cluster_for(case) as cluster:
        cluster.base.edit_outputs(lambda d: d["network"].pop("network"))
        assert_stopped(case, module, cluster, "applied_outputs:terraform_output_failed:network")


def scenario_server_version(case, module):
    with cluster_for(case) as cluster:
        cluster.edit(lambda s: s["version"].update(minor="34"))
        assert_stopped(case, module, cluster, "server_version_mismatch")
    with cluster_for(case) as cluster:
        cluster.edit(lambda s: s.update(version_error="Unable to connect to the server: dial tcp 127.0.0.1:8443"))
        assert_stopped(case, module, cluster, "server_unreachable")


def scenario_missing(case, module):
    with cluster_for(case) as cluster:
        cluster.edit(lambda s: s["objects"].pop(key_of(cluster.row("Deployment", "istiod-acme-v1"))))
        code, report, _, error, _ = run(module, cluster)
        case.assertEqual((code, error), (0, None))
        row = find(report, "Deployment", "istiod-acme-v1")
        case.assertEqual((row["presence"], row["readiness"], row["reasons"]), ("MISSING", "NOT_READY", ["missing"]))
        case.assertEqual(by_name(report)["istiod"]["state"], "PARTIAL")


def scenario_identity(case, module):
    edits = {"name": lambda o: o["metadata"].update(name="other"),
             "namespace": lambda o: o["metadata"].update(namespace="default"),
             "apiVersion": lambda o: o.update(apiVersion="apps/v1beta1"),
             "kind": lambda o: o.update(kind="StatefulSet")}
    for label, edit in edits.items():
        with cluster_for(case) as cluster:
            edit(cluster.object("Deployment", "-gateway"))
            cluster.save()
            code, report, _, error, _ = run(module, cluster)
            case.assertEqual((code, error), (3, None), label)
            row = find(report, "Deployment", "-gateway")
            case.assertEqual((row["presence"], row["readiness"], row["reasons"]),
                             ("UNKNOWN", "UNKNOWN", ["identity_mismatch"]), label)
            case.assertEqual(by_name(report)["gateway"]["state"], "UNKNOWN")
            case.assertEqual((report["status"], report["summary"]["unknown"]), ("incomplete", 1))


def scenario_generation(case, module):
    with cluster_for(case) as cluster:
        cluster.object("Deployment", "-gateway")["metadata"]["generation"] = 2
        cluster.save()
        code, report, _, error, _ = run(module, cluster)
        case.assertEqual(code, 0)
        row = find(report, "Deployment", "-gateway")
        case.assertEqual((row["generation"], row["observed_generation"], row["observed"], row["readiness"]),
                         (2, 1, False, "NOT_READY"))
        case.assertIn("generation_not_observed", row["reasons"])
        case.assertEqual(by_name(report)["gateway"]["state"], "NOT_READY")


def scenario_deployment(case, module):
    with cluster_for(case) as cluster:
        cluster.object("Deployment", "aws-load-balancer-controller")["status"]["conditions"][0]["status"] = "False"
        cluster.save()
        code, report, _, _, _ = run(module, cluster)
        row = find(report, "Deployment", "aws-load-balancer-controller")
        case.assertEqual((code, row["readiness"], row["reasons"]), (0, "NOT_READY", ["deployment_not_available"]))
        case.assertEqual(by_name(report)["controller"]["state"], "NOT_READY")
    with cluster_for(case) as cluster:
        cluster.object("Deployment", "aws-load-balancer-controller")["status"]["readyReplicas"] = 0
        cluster.save()
        _, report, _, _, _ = run(module, cluster)
        row = find(report, "Deployment", "aws-load-balancer-controller")
        case.assertEqual((row["readiness"], row["reasons"]), ("NOT_READY", ["deployment_replicas_not_ready"]))


def scenario_crd(case, module):
    with cluster_for(case) as cluster:
        crd = cluster.object("CustomResourceDefinition", "targetgroupbindings.elbv2.k8s.aws")
        crd["status"]["conditions"][1]["status"] = "False"
        cluster.save()
        code, report, _, _, _ = run(module, cluster)
        row = find(report, "CustomResourceDefinition", "targetgroupbindings.elbv2.k8s.aws")
        case.assertEqual((code, row["readiness"], row["reasons"]), (0, "NOT_READY", ["crd_not_established"]))
        case.assertEqual(by_name(report)["controller"]["state"], "NOT_READY")


def scenario_namespace_policy(case, module):
    with cluster_for(case) as cluster:
        cluster.object("Namespace", "acme-ingress")["status"]["phase"] = "Terminating"
        policy = cluster.object("ValidatingAdmissionPolicy", "acme-target-registration")
        policy["status"]["typeChecking"] = {"expressionWarnings": [{"fieldRef": "spec.validations[0]",
                                                                    "warning": "synthetic"}]}
        cluster.object("ValidatingAdmissionPolicy", "acme-no-lb-service").pop("status")
        cluster.save()
        _, report, _, _, _ = run(module, cluster)
        case.assertEqual(find(report, "Namespace", "acme-ingress")["reasons"], ["namespace_not_active"])
        case.assertEqual(find(report, "ValidatingAdmissionPolicy", "acme-target-registration")["reasons"],
                         ["policy_type_checking_warnings"])
        unobserved = find(report, "ValidatingAdmissionPolicy", "acme-no-lb-service")
        case.assertEqual((unobserved["observed"], unobserved["readiness"]), (False, "NOT_READY"))
        case.assertEqual({by_name(report)[s]["state"] for s in ("namespaces", "admission")}, {"NOT_READY"})


def scenario_api_errors(case, module):
    cases = {
        "api_forbidden": ("errors", 'Error from server (Forbidden): deployments.apps "x" is forbidden: User "u" cannot '
                                    'get resource "deployments" token=' + TOKEN_MARKER),
        "api_unreachable": ("errors", "Unable to connect to the server: net/http: request canceled (Client.Timeout "
                                      "exceeded while awaiting headers)"),
        "api_error": ("errors", "error: the server doesn't have a resource type " + TOKEN_MARKER),
        "incomplete_response": ("raw", '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name"'),
    }
    for reason, (where, text) in cases.items():
        with cluster_for(case) as cluster:
            cluster.edit(lambda s, w=where, t=text: s[w].update({key_of(cluster.row("Deployment", "-gateway")): t}))
            code, report, lines, error, _ = run(module, cluster)
            case.assertEqual((code, error), (3, None), reason)
            row = find(report, "Deployment", "-gateway")
            case.assertEqual((row["presence"], row["readiness"], row["reasons"]), ("UNKNOWN", "UNKNOWN", [reason]))
            case.assertEqual(report["status"], "incomplete")
            for output in (json.dumps(report), module.status_text(report), "\n".join(lines)):
                case.assertNotIn(TOKEN_MARKER, output)
                case.assertNotIn("Error from server", output)
    with cluster_for(case) as cluster:
        real = subprocess.run

        def slow(command, *args, **kwargs):
            if "get" in command:
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
            return real(command, *args, **kwargs)
        with mock.patch.object(subprocess, "run", slow):
            code, report, _, error, _ = run(module, cluster)
        case.assertEqual((code, error), (3, None))
        case.assertEqual(report["summary"]["unknown"], 62)
        case.assertEqual(set(r for s in report["stages"] for o in s["objects"] for r in o["reasons"]), {"api_timeout"})


def scenario_target_group_binding(case, module):
    with cluster_for(case) as cluster:
        objects, _ = Cluster.bundle(cluster.document)
        binding = next(o for o in objects if o["kind"] == "TargetGroupBinding")
        cluster.state["objects"][key_of(cluster.row("TargetGroupBinding"))] = make_ready(binding)
        cluster.save()
        code, report, _, _, _ = run(module, cluster)
        row = find(report, "TargetGroupBinding")
        case.assertEqual((code, row["presence"], row["observed"], row["readiness"]),
                         (0, "PRESENT", True, "NOT_VERIFIABLE"))
        case.assertIn("target_registration_and_health_not_tested", row["reasons"])
        case.assertEqual(by_name(report)["ingress"]["state"], "UNVERIFIED")
        case.assertFalse(report["runtime_ready"])


def scenario_guard(case, module):
    refused = [["apply", "-f", "-"], ["delete", "deployment", "x"], ["patch", "deployment", "x", "-p", "{}"],
               ["create", "token", "acme-binding-writer"], ["auth", "can-i", "--list"],
               ["get", "secret", "cacerts", "-n", "istio-system", "--ignore-not-found", "-o", "json"],
               ["get", "deployment.v1.apps", "x", "--ignore-not-found", "-o", "yaml"],
               ["get", "deployment.v1.apps", "x", "--as=system:serviceaccount:acme-ingress:acme-binding-writer",
                "--ignore-not-found", "-o", "json"],
               ["get", "deployment.v1.apps", "x", "--token=abc", "--ignore-not-found", "-o", "json"],
               ["get", "deployment.v1.apps", "x", "--server=https://evil", "--ignore-not-found", "-o", "json"],
               ["config", "view", "-o", "json"], ["version"],
               # Valid shapes carrying a forbidden argument where the name or namespace belongs.
               ["get", "deployment.v1.apps", "x", "-n", "--as=system:serviceaccount:acme-ingress:acme-binding-writer",
                "--ignore-not-found", "-o", "json"],
               ["get", "deployment.v1.apps", "--token=abc", "--ignore-not-found", "-o", "json"],
               ["get", "namespace", "--server=https://evil", "--ignore-not-found", "-o", "json"],
               ["get", "namespace", "x", "-n", "--insecure-skip-tls-verify", "--ignore-not-found", "-o", "json"]]
    for args in refused:
        with case.assertRaises(Exception, msg=str(args)):
            module.check_kubectl_command(args)
    module.check_kubectl_command(["get", "namespace", "istio-system", "--ignore-not-found", "-o", "json"])


def scenario_fixture_input(case, module):
    with cluster_for(case) as cluster:
        code, report, _, error, renders = run(module, cluster,
                                              input_path=preflight.REPOSITORY / "kubernetes/tests/fixtures/runtime.json")
        case.assertEqual((code, report), (2, None))
        case.assertIn("manifest/fixture boundary", error)
        case.assertEqual((renders, cluster.calls()), (0, []))


class StatusTests(unittest.TestCase):
    def test_ready_cluster(self):
        scenario_ready(self, k8s_runtime)

    def test_empty_cluster(self):
        scenario_empty(self, k8s_runtime)

    def test_refused_in_ci_cloud_and_with_placeholder_credentials(self):
        scenario_refused(self, k8s_runtime)

    def test_context_and_kubeconfig(self):
        scenario_context(self, k8s_runtime)

    def test_account_and_input_against_applied_outputs(self):
        scenario_outputs(self, k8s_runtime)

    def test_server_version(self):
        scenario_server_version(self, k8s_runtime)

    def test_missing_object(self):
        scenario_missing(self, k8s_runtime)

    def test_identity_mismatch(self):
        scenario_identity(self, k8s_runtime)

    def test_generation_not_observed(self):
        scenario_generation(self, k8s_runtime)

    def test_deployment_not_available(self):
        scenario_deployment(self, k8s_runtime)

    def test_crd_not_established(self):
        scenario_crd(self, k8s_runtime)

    def test_namespace_and_policy_readiness(self):
        scenario_namespace_policy(self, k8s_runtime)

    def test_api_errors_timeouts_and_incomplete_responses(self):
        scenario_api_errors(self, k8s_runtime)

    def test_target_group_binding_is_never_ready(self):
        scenario_target_group_binding(self, k8s_runtime)

    def test_only_read_only_kubectl_commands(self):
        scenario_guard(self, k8s_runtime)

    def test_fixture_input_is_refused(self):
        scenario_fixture_input(self, k8s_runtime)

    def test_command_line_refusal_in_ci(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, mock.patch.dict(os.environ, {"CI": "true"}):
            code = k8s_runtime.main(["status", "--input", "/nonexistent", "--helm", "/nonexistent",
                                     "--kubectl", "/nonexistent", "--terraform", "/nonexistent"])
        self.assertEqual(code, 1)
        self.assertIn("Refused (live_refused_in_ci)", output.getvalue())


# Each mutation removes one status or preflight guard; the scenario must fail.
MUTATIONS = [
    ("automation_not_refused", "    refusal = preflight.automation_refusal(environment)\n    if refusal:\n        "
     "out_fn(\"Refused (\" + refusal + \"): status", "    refusal = None\n    if refusal:\n        "
     "out_fn(\"Refused (\" + refusal + \"): status", scenario_refused),
    ("context_checked_late", '    context = context or project + "-dev-eks"\n    need(context == project + "-dev-eks", ',
     '    context = context or project + "-dev-eks"\n    need(True, ', scenario_context),
    ("kubeconfig_unchecked", "        k8s_certs.check_kubeconfig(common.parse(view.stdout), context, outputs[\"platform\"])\n",
     "        common.parse(view.stdout)\n", scenario_context),
    ("applied_outputs_uncompared", '    need(controller == document["controller_identity"] and ingress == document["private_ingress"],',
     "    need(True,", scenario_outputs),
    ("server_version_uncompared", '    need(observed == document["controller_identity"]["kubernetes_version"], ',
     "    need(True, ", scenario_server_version),
    ("identity_unchecked", "    if identity != (row[\"apiVersion\"], row[\"kind\"], row[\"namespace\"], row[\"name\"]):\n",
     "    if False:\n", scenario_identity),
    ("missing_unclassified", "    if not process.stdout.strip():\n", "    if False:\n", scenario_missing),
    ("returncode_ignored", "    if process.returncode != 0:\n        error = process.stderr", "    if False:\n        error = process.stderr",
     scenario_api_errors),
    ("forbidden_unclassified", '.append("api_forbidden" if API_FORBIDDEN.search(error) else\n', '.append(\n',
     scenario_api_errors),
    ("timeout_unhandled", "    except subprocess.TimeoutExpired:\n        return None\n", "", scenario_api_errors),
    ("observed_generation_ignored",
     '        result["observed"] = result["generation"] is not None and result["observed_generation"] >= result["generation"]',
     '        result["observed"] = True', scenario_generation),
    ("deployment_available_ignored", '        if conditions_of(obj).get("Available") != "True":\n', "        if False:\n",
     scenario_deployment),
    ("deployment_replicas_ignored", '        if not isinstance(spec_replicas, int) or any(', "        if False and any(",
     scenario_deployment),
    ("crd_conditions_ignored", '        missing = [c for c in ("Established", "NamesAccepted") if conditions.get(c) != "True"]',
     "        missing = []", scenario_crd),
    ("namespace_phase_ignored", '        if status.get("phase") == "Active":\n', "        if True:\n",
     scenario_namespace_policy),
    ("policy_warnings_ignored", "        if warnings:\n", "        if False:\n", scenario_namespace_policy),
    ("unknown_not_first", '    if "UNKNOWN" in presence:\n        return "UNKNOWN"\n', "", scenario_identity),
    ("unknown_exit_zero", '    return (3 if counts["unknown"] else 0), report', "    return 0, report", scenario_identity),
    ("ingress_not_blocked",
     '    if name == "ingress" and any(o["kind"] == "TargetGroupBinding" and o["presence"] != "PRESENT" for o in objects):\n'
     '        return "BLOCKED"\n', "", scenario_ready),
    ("binding_claimed_ready", '        reasons.append("target_registration_and_health_not_tested")\n        return "NOT_VERIFIABLE"',
     '        return "READY"', scenario_target_group_binding),
    ("functional_claimed", '"functional": "NOT_TESTED"', '"functional": "PASS"', scenario_ready),
    ("mutating_commands_allowed", '    else:\n        raise StatusError("kubectl_command_not_read_only")\n',
     "    else:\n        return\n", scenario_guard),
    ("forbidden_arguments_allowed", '        need(not FORBIDDEN_KUBECTL.fullmatch(argument), "kubectl_argument_refused")\n',
     "        pass\n", scenario_guard),
    ("secret_reads_allowed", '        need(args[1].split(".")[0] != "secret", "kubectl_secret_read_refused")\n', "",
     scenario_guard),
]


def mutant(old, new):
    source = (HERE / "k8s_runtime.py").read_text()
    if source.count(old) != 1:
        raise AssertionError("mutation target not found exactly once: " + old.strip()[:80])
    spec = importlib.util.spec_from_loader("k8s_runtime_status_mutant", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(HERE / "k8s_runtime.py")
    exec(compile(source.replace(old, new), module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


class MutationTests(unittest.TestCase):
    def test_each_status_guard_mutation_is_detected(self):
        self.assertEqual(len(MUTATIONS), 24)
        undetected = []
        for name, old, new, scenario in MUTATIONS:
            module = mutant(old, new)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    scenario(self, module)
            except AssertionError:
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
