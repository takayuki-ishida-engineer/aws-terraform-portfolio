#!/usr/bin/env python3
"""Offline deployment plan and read-only status for the Kubernetes runtime (Step 1 items 6c-A, 6c-B1).

``plan`` renders the runtime input with the pinned Helm and the existing
renderer, runs the existing validator, re-checks the render evidence and splits
the 62-object bundle into the 9 reviewed apply stages of
``kubernetes/tests/expected-stages.json``. Every stage must hold exactly the
reviewed apiVersion, kind, namespace and name of its objects, in the reviewed order,
not merely the same count or set, and the stages together must equal
``kubernetes/tests/expected-inventory.json``.

For each stage it shows the objects, the actor that would apply them, the Secrets
that must exist first, the prerequisites and the readiness conditions. It executes
nothing: no kubectl, no cluster, no AWS API. The only process it starts is the
pinned Helm binary that the renderer verifies by SHA-256.

``status`` (item 6c-B1, workstation only) reads the state of the same 62 objects
from the cluster with ``kubectl get`` and changes nothing. Before any kubectl call it
passes a preflight safety gate: it is refused in CI, cloud sessions, with the
placeholder credentials and with an AWS endpoint override; the renderer input must
be operational (not the fixture), render and split exactly like ``plan``, and equal
the applied platform and network outputs; the context must be ``<project>-dev-eks``
and exactly the ``eks_tunnel.py`` kubeconfig of the applied cluster (loopback
tunnel, cluster CA, endpoint host, ``aws eks get-token``); and the server version
must equal the input's Kubernetes version. Only allowlisted read-only kubectl
commands run. Object bodies, Secrets, tokens and kubectl error text are never
printed. Every object is reported as present, missing or unknown, with its
generation, observedGeneration and readiness; a state that cannot be determined is
never reported as success. Existing, observed and ready are reported separately, and
none of them is evidence that the application or network works (NOT_TESTED).

``apply`` and ``destroy`` are not implemented. The TargetGroupBinding's actor is the
binding-writer ServiceAccount. How the operator acts as it is not approved, and
impersonation on the current EKS cluster is NOT_TESTED, so that step is shown as
BLOCKED.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_certs  # noqa: E402
import k8s_runtime_input  # noqa: E402
import preflight  # noqa: E402

TOOLS = preflight.REPOSITORY / "kubernetes/tools"
sys.path.insert(0, str(TOOLS))
import common  # noqa: E402
import render  # noqa: E402
import validate  # noqa: E402

STAGE_TABLE = preflight.REPOSITORY / "kubernetes/tests/expected-stages.json"
INVENTORY = preflight.REPOSITORY / "kubernetes/tests/expected-inventory.json"
STAGES_FORMAT = "k8s-runtime-stages-v1"
CONTRACT_VERSION = 4
# Written independently of the renderer's evidence and of the stage table file.
STAGE_COUNTS = (("namespaces", 2), ("base", 16), ("controller", 13), ("istiod", 12), ("gateway", 5),
                ("mesh_security", 5), ("admission", 4), ("binding_writer", 3), ("ingress", 2))
RESOURCE_COUNT = 62
# Kinds that only the named stages may hold. Secrets are never part of the bundle.
KIND_STAGES = {"TargetGroupBinding": {"ingress"}, "Gateway": {"ingress"},
               "CustomResourceDefinition": {"base", "controller"},
               "ValidatingAdmissionPolicy": {"admission"}, "ValidatingAdmissionPolicyBinding": {"admission"},
               "MutatingWebhookConfiguration": {"controller", "istiod"},
               "ValidatingWebhookConfiguration": {"base", "controller", "istiod"},
               "Namespace": {"namespaces", "mesh_security"}}
FORBIDDEN_KINDS = {"Secret", "Certificate", "Issuer", "Ingress"}
OPERATOR = "operator (platform bootstrap admin role through eks_tunnel.py and aws eks get-token)"
WRITER_METHOD = ("not approved; impersonation on the current EKS cluster is NOT_TESTED and TokenRequest is not "
                 "approved, so this step is BLOCKED in 6c-A")
# Which k8s_certs Secret each stage needs before it starts (names from secret_names).
STAGE_SECRETS = {"controller": ("webhook_tls_secret",), "istiod": ("istio_ca_secret",),
                 "gateway": ("gateway_tls_secret", "gateway_client_ca_secret"),
                 "ingress": ("gateway_tls_secret", "gateway_client_ca_secret")}
PREREQUISITES = {
    "namespaces": ["context <project>-dev-eks is the eks_tunnel.py kubeconfig (loopback tunnel, cluster CA, get-token)",
                   "account in the input, the platform output and the cluster ARN agree",
                   "server version equals controller_identity.kubernetes_version",
                   "a Ready node in active_workload_az"],
    "base": [],
    "controller": ["the webhook Secret's public ca.crt equals public.json webhook_ca_bundle",
                   "the private ECR repositories hold the mirrored images (mirror_images.py)"],
    "istiod": ["the controller stage is ready"],
    "gateway": ["the istiod stage is ready (revision injection)"],
    "mesh_security": ["istiod validation webhook is ready"],
    "admission": [],
    "binding_writer": [],
    "ingress": ["the network output lists the elasticloadbalancing interface endpoint (finding F21)",
                "an approved way for the operator to act as the binding-writer ServiceAccount"],
}
READINESS = {
    "namespaces": ["both Namespaces Active with the restricted Pod Security and istio.io/rev labels"],
    "base": ["15 Istio CRDs Established and NamesAccepted", "istiod-default-validator present"],
    "controller": ["2 CRDs Established", "Deployment Available with the locked image digest",
                   "webhook Service has a ready endpoint on 9443", "ServiceAccount IRSA annotation equals role_arn"],
    "istiod": ["Deployment Available with the locked image digest", "istiod endpoints ready on 15017 and 15012",
               "server-side dry-run: a valid PeerAuthentication is accepted and an invalid one refused"],
    "gateway": ["Deployment Available", "Pod carries sidecar.istio.io/status (revision injection)",
                "proxy image digest locked, readiness on 15021"],
    "mesh_security": ["5 objects present, kubectl diff empty"],
    "admission": ["policy type checking without warnings, bindings Deny",
                  "server-side dry-run: a TargetGroupBinding in <project>-app and a LoadBalancer Service in "
                  "<project>-ingress are both refused by the policies"],
    "binding_writer": ["3 objects present", "writer RBAC: create targetgroupbindings yes, other verbs and names no"],
    "ingress": ["dry-run: operator create refused, writer create accepted, writer with another ARN refused",
                "TargetGroupBinding status.observedGeneration current, no controller failure event",
                "target registration and health are NOT_TESTED (not shown by observedGeneration)"],
}


# What the operator does between stages, outside this tool.
AFTER = {"namespaces": ["register the four Secrets with k8s_certs.py register before the next stage"]}


class PlanError(Exception):
    """The bundle or its evidence does not match the reviewed plan."""


def require(condition, code):
    if not condition:
        raise PlanError(code)


def load_stage_table(project):
    table = common.parse(STAGE_TABLE.read_text(encoding="utf-8"))
    require(isinstance(table, dict) and set(table) == {"format", "description", "stages"}
            and table["format"] == STAGES_FORMAT, "stage_table_format")
    stages = [(item.get("name"), item.get("objects")) for item in table["stages"]]
    require([(name, len(objects)) for name, objects in stages] == list(STAGE_COUNTS), "stage_table_counts")
    filled = [(name, [tuple(row) for row in common.fill(objects, project)]) for name, objects in stages]
    rows = [row for _, objects in filled for row in objects]
    require(len(rows) == len(set(rows)) == RESOURCE_COUNT, "stage_table_duplicate")
    inventory = {tuple(row) for row in common.fill(common.parse(INVENTORY.read_text(encoding="utf-8")), project)}
    require(set(rows) == inventory, "stage_table_inventory_mismatch")
    return filled


def check_evidence(objects, evidence, document):
    require(evidence.get("status") == "rendered" and evidence.get("complete_v5") is False
            and evidence.get("actual_helm_renders") == 4, "render_evidence_status")
    require(type(evidence.get("runtime_contract_version")) is int
            and evidence["runtime_contract_version"] == CONTRACT_VERSION, "runtime_contract_version")
    require(evidence.get("image_lock_sha256") == common.sha((preflight.REPOSITORY / "kubernetes/images.lock.json")
                                                             .read_bytes()), "image_lock_evidence")
    require(evidence.get("helm_sha256") == common.LOCK["helm"]["binary_sha256"]
            and evidence.get("charts") == {k: v["sha256"] for k, v in common.LOCK["charts"].items()},
            "pinned_artifact_evidence")
    require(evidence.get("input_sha256") == common.sha(json.dumps(document, sort_keys=True,
                                                                  separators=(",", ":")).encode()), "input_evidence")
    require(evidence.get("manifest_sha256") == common.sha(json.dumps(objects, sort_keys=True,
                                                                     separators=(",", ":")).encode()),
            "manifest_evidence")
    require(evidence.get("resource_count") == len(objects) == RESOURCE_COUNT, "resource_count")
    require(list((evidence.get("stages") or {}).items()) == list(STAGE_COUNTS), "stage_evidence")


def split_stages(objects, evidence, table):
    """Cut the ordered bundle by the evidence counts; each stage must equal the table."""
    result, start = [], 0
    for (name, expected), (evidence_name, count) in zip(table, evidence["stages"].items()):
        require(name == evidence_name, "stage_order:" + name)
        chunk = objects[start:start + count]
        start += count
        identities = [validate.identity(obj) for obj in chunk]
        require(len(identities) == len(set(identities)), "stage_duplicate:" + name)
        require(set(identities) == set(expected), "stage_identity_mismatch:" + name)
        # The reviewed order is the apply order within the stage too, not only the set.
        require(identities == list(expected), "stage_identity_order:" + name)
        for obj in chunk:
            kind = obj["kind"]
            require(kind not in FORBIDDEN_KINDS, "forbidden_kind:" + kind)
            require(name in KIND_STAGES.get(kind, {name}), "kind_in_wrong_stage:" + kind + "/" + name)
            require(obj.get("roleRef", {}).get("name") != "cluster-admin", "cluster_admin_binding")
        result.append((name, chunk))
    require(start == len(objects), "stage_coverage")
    return result


def actor(obj, project):
    if obj["kind"] == "TargetGroupBinding":
        return "system:serviceaccount:" + project + "-ingress:" + project + "-binding-writer"
    return "operator"


def required_secrets(stage, project):
    names = k8s_certs.secret_names(project)
    layout = {item["name"]: item for item in k8s_certs.public_layout(project)}
    return [layout[names[key]] for key in STAGE_SECRETS.get(stage, ())]


def plan(input_path, helm, fixture=False):
    document = common.parse(Path(input_path).read_text(encoding="utf-8"))
    common.metadata(document, fixture)
    project = document["runtime"]["project"]
    table = load_stage_table(project)
    objects, evidence = render.render(document, helm, fixture)
    validate.verify(objects, document, fixture)
    check_evidence(objects, evidence, document)
    stages = split_stages(objects, evidence, table)
    writer = actor({"kind": "TargetGroupBinding"}, project)
    report = {
        "status": "planned", "executed": False, "kubernetes_api_calls": 0, "aws_api_calls": 0,
        "fixture": fixture, "project": project, "resource_count": len(objects),
        "manifest_sha256": evidence["manifest_sha256"], "input_sha256": evidence["input_sha256"],
        "runtime_contract_version": evidence["runtime_contract_version"],
        "actors": {"operator": OPERATOR, "binding_writer": writer, "binding_writer_method": WRITER_METHOD},
        "stages": [],
        "not_implemented": ["apply", "destroy"],
        "not_tested": ["any cluster operation", "impersonation of the binding-writer ServiceAccount",
                       "Elastic Load Balancing API reachability (finding F21)", "target registration and health",
                       "admission, RBAC and webhook behaviour on a real cluster", "image pulls from the private ECR"],
    }
    for index, (name, chunk) in enumerate(stages, start=1):
        rows = [{"apiVersion": o["apiVersion"], "kind": o["kind"], "namespace": o["metadata"].get("namespace", ""),
                 "name": o["metadata"]["name"], "actor": actor(o, project)} for o in chunk]
        report["stages"].append({
            "index": index, "name": name, "count": len(rows), "objects": rows,
            "required_secrets": required_secrets(name, project),
            "prerequisites": [x.replace("<project>", project) for x in PREREQUISITES[name]],
            "readiness": [x.replace("<project>", project) for x in READINESS[name]],
            "after": AFTER.get(name, []),
            "execution": "BLOCKED (binding-writer method not approved)" if name == "ingress" else "not executed",
        })
    return report


def text(report):
    lines = ["Kubernetes runtime plan for project " + report["project"] +
             (" (synthetic fixture, never an operational manifest)" if report["fixture"] else ""),
             "Bundle: " + str(report["resource_count"]) + " objects, manifest sha256 " + report["manifest_sha256"] +
             ", input sha256 " + report["input_sha256"],
             "Operator: " + report["actors"]["operator"],
             "Binding writer: " + report["actors"]["binding_writer"] + " - " + report["actors"]["binding_writer_method"]]
    for stage in report["stages"]:
        lines.append("")
        lines.append("Stage " + str(stage["index"]) + " " + stage["name"] + " (" + str(stage["count"]) + " objects, " +
                     stage["execution"] + ")")
        for row in stage["objects"]:
            where = row["namespace"] + "/" if row["namespace"] else ""
            lines.append("  " + row["apiVersion"] + " " + row["kind"] + " " + where + row["name"] +
                         ("" if row["actor"] == "operator" else "  [actor " + row["actor"] + "]"))
        for secret in stage["required_secrets"]:
            lines.append("  needs Secret " + secret["namespace"] + "/" + secret["name"] + " (" + secret["type"] +
                         ", keys " + ", ".join(secret["keys"]) + ")")
        for item in stage["prerequisites"]:
            lines.append("  before: " + item)
        for item in stage["readiness"]:
            lines.append("  ready when: " + item)
        for item in stage["after"]:
            lines.append("  then: " + item)
    lines.append("")
    lines.append("Plan only: nothing was applied and no cluster or AWS API was contacted. apply and destroy "
                 "are not implemented. NOT_TESTED: " + "; ".join(report["not_tested"]) + ".")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- status (6c-B1)
class StatusError(Exception):
    """The preflight safety gate refused; the message is a fixed code, never kubectl output."""


def need(condition, code):
    if not condition:
        raise StatusError(code)


STATUS_TIMEOUT_SECONDS = 20
# Read-only kubectl commands only; every call is checked before it starts.
FORBIDDEN_KUBECTL = re.compile(r"--(as|as-group|as-uid|as-user-extra|token|server|insecure-skip-tls-verify|kubeconfig|"
                               r"username|password|client-key|client-certificate|user|cluster)(=.*)?")
API_FORBIDDEN = re.compile(r"\bforbidden\b|cannot (get|list) resource", re.IGNORECASE)
API_UNREACHABLE = re.compile(r"unable to connect|timeout|timed out|deadline exceeded|connection refused|"
                             r"i/o timeout|no route to host|TLS handshake", re.IGNORECASE)
NOT_CHECKED = ["presence and contents of the four k8s_certs Secrets (Secrets are never read)",
               "image digests of running Pods", "webhook serving and admission behaviour on the cluster",
               "binding-writer RBAC and impersonation (NOT_TESTED)",
               "target registration and health (finding F21)", "application and network behaviour"]


def check_kubectl_command(args):
    """Refuse anything but the three read-only command shapes this tool uses."""
    need(isinstance(args, list) and all(isinstance(a, str) for a in args), "kubectl_command_shape")
    if args[:2] == ["config", "view"]:
        need(args == ["config", "view", "--minify", "--raw", "-o", "json"], "kubectl_command_not_read_only")
    elif args[:1] == ["version"]:
        need(args == ["version", "-o", "json"], "kubectl_command_not_read_only")
    elif args[:1] == ["get"]:
        need(len(args) in (6, 8) and args[-3:] == ["--ignore-not-found", "-o", "json"]
             and (len(args) == 6 or args[3] == "-n"), "kubectl_command_not_read_only")
        need(args[1].split(".")[0] != "secret", "kubectl_secret_read_refused")
    else:
        raise StatusError("kubectl_command_not_read_only")
    for argument in args:
        need(not FORBIDDEN_KUBECTL.fullmatch(argument), "kubectl_argument_refused")


def run_kubectl(binary, context, args, env, timeout=STATUS_TIMEOUT_SECONDS):
    """Run one allowlisted read-only kubectl command; None when it did not finish in time."""
    check_kubectl_command(args)
    command = [binary, "--context", context, "--request-timeout=" + str(timeout) + "s"] + args
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=timeout + 15)
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        raise StatusError("kubectl_unavailable") from None


def resource_argument(api_version, kind):
    """kind.version.group for kubectl get; the core group has no suffix."""
    if "/" in api_version:
        group, version = api_version.split("/", 1)
        return kind.lower() + "." + version + "." + group
    return kind.lower()


def preflight_gate(document, context, kubectl_binary, terraform, services, environment, timeout):
    """Fail closed before any object is read: identity, outputs, kubeconfig and server version."""
    project = document["runtime"]["project"]
    account = document["controller_identity"]["scope"]["account_id"]
    need(context == project + "-dev-eks", "context_mismatch: the context must be " + project + "-dev-eks")
    need(project not in preflight.PLACEHOLDER_PROJECTS and account not in preflight.PLACEHOLDER_ACCOUNTS,
         "placeholder_input")
    try:
        outputs = {name: k8s_runtime_input.read_output(terraform, services, root, name, environment)
                   for root, name in (("platform", "controller_identity"), ("platform", "platform"),
                                      ("platform", "private_ingress"), ("network", "network"))}
        controller, ingress = k8s_runtime_input.check_outputs(project, account, outputs["controller_identity"],
                                                              outputs["platform"], outputs["private_ingress"],
                                                              outputs["network"])
    except k8s_runtime_input.InputError as error:
        raise StatusError("applied_outputs:" + str(error)) from None
    need(controller == document["controller_identity"] and ingress == document["private_ingress"],
         "input_differs_from_applied_outputs")
    view = run_kubectl(kubectl_binary, context, ["config", "view", "--minify", "--raw", "-o", "json"], environment,
                       timeout)
    need(view is not None and view.returncode == 0, "kubeconfig_mismatch:context_unavailable")
    try:
        k8s_certs.check_kubeconfig(common.parse(view.stdout), context, outputs["platform"])
    except (ValueError, k8s_certs.CertError) as error:
        raise StatusError(str(error) if isinstance(error, k8s_certs.CertError) else "kubeconfig_mismatch:shape") \
            from None
    version = run_kubectl(kubectl_binary, context, ["version", "-o", "json"], environment, timeout)
    need(version is not None and version.returncode == 0, "server_unreachable: start eks_tunnel.py start")
    try:
        server = common.parse(version.stdout)["serverVersion"]
        minor = re.match(r"[0-9]+", server["minor"]).group(0)
        observed = server["major"] + "." + minor
    except (ValueError, KeyError, TypeError, AttributeError):
        raise StatusError("server_version_unreadable") from None
    need(observed == document["controller_identity"]["kubernetes_version"], "server_version_mismatch")
    return observed


def conditions_of(obj):
    found = {}
    for item in (obj.get("status") or {}).get("conditions") or []:
        if isinstance(item, dict) and isinstance(item.get("type"), str):
            found[item["type"]] = item.get("status")
    return found


def readiness_of(row, obj, reasons):
    """READY, NOT_READY, NOT_APPLICABLE (existence only) or NOT_VERIFIABLE; reasons are appended."""
    kind = row["kind"]
    status = obj.get("status") or {}
    if kind == "Namespace":
        if status.get("phase") == "Active":
            return "READY"
        reasons.append("namespace_not_active")
        return "NOT_READY"
    if kind == "CustomResourceDefinition":
        conditions = conditions_of(obj)
        missing = [c for c in ("Established", "NamesAccepted") if conditions.get(c) != "True"]
        reasons.extend("crd_not_" + c.lower() for c in missing)
        return "NOT_READY" if missing else "READY"
    if kind == "Deployment":
        spec_replicas = (obj.get("spec") or {}).get("replicas")
        problems = []
        if conditions_of(obj).get("Available") != "True":
            problems.append("deployment_not_available")
        if not isinstance(spec_replicas, int) or any(status.get(f) != spec_replicas for f in
                                                     ("replicas", "updatedReplicas", "readyReplicas",
                                                      "availableReplicas")):
            problems.append("deployment_replicas_not_ready")
        reasons.extend(problems)
        return "NOT_READY" if problems else "READY"
    if kind == "ValidatingAdmissionPolicy":
        warnings = (status.get("typeChecking") or {}).get("expressionWarnings")
        if warnings:
            reasons.append("policy_type_checking_warnings")
            return "NOT_READY"
        return "READY" if "observedGeneration" in status else "NOT_READY"
    if kind == "TargetGroupBinding":
        reasons.append("target_registration_and_health_not_tested")
        return "NOT_VERIFIABLE"
    return "NOT_APPLICABLE"


def object_status(row, stage, process):
    """The state of one object from one kubectl get; unknown is never reported as success."""
    result = {"apiVersion": row["apiVersion"], "kind": row["kind"], "namespace": row["namespace"],
              "name": row["name"], "stage": stage, "actor": row["actor"], "presence": "UNKNOWN",
              "generation": None, "observed_generation": None, "observed": None, "readiness": "UNKNOWN",
              "reasons": []}
    if process is None:
        result["reasons"].append("api_timeout")
        return result
    if process.returncode != 0:
        error = process.stderr or ""
        result["reasons"].append("api_forbidden" if API_FORBIDDEN.search(error) else
                                 "api_unreachable" if API_UNREACHABLE.search(error) else "api_error")
        return result
    if not process.stdout.strip():
        result.update(presence="MISSING", readiness="NOT_READY")
        result["reasons"].append("missing")
        return result
    try:
        obj = common.parse(process.stdout)
        identity = (obj["apiVersion"], obj["kind"], obj["metadata"].get("namespace", ""), obj["metadata"]["name"])
    except (ValueError, KeyError, TypeError, AttributeError):
        result["reasons"].append("incomplete_response")
        return result
    if identity != (row["apiVersion"], row["kind"], row["namespace"], row["name"]):
        result["reasons"].append("identity_mismatch")
        return result
    result["presence"] = "PRESENT"
    generation = obj["metadata"].get("generation")
    observed = (obj.get("status") or {}).get("observedGeneration")
    result["generation"] = generation if isinstance(generation, int) else None
    result["observed_generation"] = observed if isinstance(observed, int) else None
    if result["observed_generation"] is not None:
        result["observed"] = result["generation"] is not None and result["observed_generation"] >= result["generation"]
        if not result["observed"]:
            result["reasons"].append("generation_not_observed")
    elif row["kind"] in ("Deployment", "ValidatingAdmissionPolicy", "TargetGroupBinding"):
        result["observed"] = False
        result["reasons"].append("generation_not_observed")
    result["readiness"] = readiness_of(row, obj, result["reasons"])
    if result["observed"] is False and result["readiness"] == "READY":
        result["readiness"] = "NOT_READY"
    return result


def stage_state(name, objects):
    presence = [o["presence"] for o in objects]
    if "UNKNOWN" in presence:
        return "UNKNOWN"
    if name == "ingress" and any(o["kind"] == "TargetGroupBinding" and o["presence"] != "PRESENT" for o in objects):
        return "BLOCKED"
    if all(p == "MISSING" for p in presence):
        return "NOT_APPLIED"
    if "MISSING" in presence:
        return "PARTIAL"
    if any(o["readiness"] == "NOT_VERIFIABLE" for o in objects):
        return "UNVERIFIED"
    if any(o["readiness"] == "NOT_READY" or o["observed"] is False for o in objects):
        return "NOT_READY"
    return "APPLIED_READY"


def status(input_path, helm, context=None, kubectl_binary="kubectl", terraform="terraform",
           services=preflight.SERVICES, env=None, timeout=STATUS_TIMEOUT_SECONDS, out_fn=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out_fn("Refused (" + refusal + "): status reads the cluster only from the operator's workstation.")
        return 1, None
    document = common.parse(Path(input_path).read_text(encoding="utf-8"))
    common.metadata(document, fixture=False)
    project = document["runtime"]["project"]
    context = context or project + "-dev-eks"
    need(context == project + "-dev-eks", "context_mismatch: the context must be " + project + "-dev-eks")
    bundle = plan(input_path, helm, False)
    server = preflight_gate(document, context, kubectl_binary, terraform, services, environment, timeout)
    report = {"status": "collected", "changes_made": False, "project": project, "context": context,
              "server_version": server, "manifest_sha256": bundle["manifest_sha256"],
              "input_sha256": bundle["input_sha256"], "stages": [], "runtime_ready": False,
              "functional": "NOT_TESTED", "binding_writer_method": WRITER_METHOD, "not_checked": NOT_CHECKED}
    counts = {"objects": 0, "present": 0, "missing": 0, "unknown": 0, "ready": 0, "not_ready": 0, "existence_only": 0,
              "not_verifiable": 0}
    readiness_counter = {"READY": "ready", "NOT_READY": "not_ready", "NOT_APPLICABLE": "existence_only",
                         "NOT_VERIFIABLE": "not_verifiable"}
    for stage in bundle["stages"]:
        rows = []
        for row in stage["objects"]:
            args = ["get", resource_argument(row["apiVersion"], row["kind"]), row["name"]]
            args += (["-n", row["namespace"]] if row["namespace"] else []) + ["--ignore-not-found", "-o", "json"]
            rows.append(object_status(row, stage["name"], run_kubectl(kubectl_binary, context, args, environment,
                                                                      timeout)))
        state = stage_state(stage["name"], rows)
        report["stages"].append({"index": stage["index"], "name": stage["name"], "state": state, "objects": rows,
                                 "required_secrets": [s["namespace"] + "/" + s["name"] for s in
                                                      stage["required_secrets"]],
                                 "secrets_checked": False})
        for row in rows:
            counts["objects"] += 1
            counts[{"PRESENT": "present", "MISSING": "missing"}.get(row["presence"], "unknown")] += 1
            if row["presence"] == "PRESENT":
                counts[readiness_counter[row["readiness"]]] += 1
    report["summary"] = counts
    if counts["unknown"]:
        report["status"] = "incomplete"
    return (3 if counts["unknown"] else 0), report


def status_text(report):
    lines = ["Kubernetes runtime status for " + report["context"] + " (server " + report["server_version"] +
             "; read-only, nothing was changed)",
             "Bundle: manifest sha256 " + report["manifest_sha256"] + ", input sha256 " + report["input_sha256"]]
    for stage in report["stages"]:
        lines.append("")
        lines.append("Stage " + str(stage["index"]) + " " + stage["name"] + ": " + stage["state"])
        for row in stage["objects"]:
            where = row["namespace"] + "/" if row["namespace"] else ""
            observed = "" if row["observed_generation"] is None else \
                " generation " + str(row["generation"]) + " observed " + str(row["observed_generation"])
            lines.append("  " + row["kind"] + " " + where + row["name"] + ": " + row["presence"] + ", " +
                         row["readiness"] + observed + (" (" + ", ".join(row["reasons"]) + ")" if row["reasons"] else ""))
        for secret in stage["required_secrets"]:
            lines.append("  Secret " + secret + ": NOT_CHECKED (never read)")
    summary = report["summary"]
    lines.append("")
    lines.append("Objects: " + ", ".join(k + " " + str(v) for k, v in summary.items()) + ". Status: " +
                 report["status"] + ". Runtime ready: no. Application and network behaviour: NOT_TESTED.")
    lines.append("Binding writer: " + report["binding_writer_method"] + ".")
    lines.append("Not checked: " + "; ".join(report["not_checked"]) + ".")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    plan_parser = sub.add_parser("plan", help="render, validate and show the staged plan; executes nothing")
    plan_parser.add_argument("--input", required=True, type=Path)
    plan_parser.add_argument("--helm", required=True)
    plan_parser.add_argument("--fixture", action="store_true", help="the synthetic fixture input")
    plan_parser.add_argument("--format", choices=["text", "json"], default="text")
    status_parser = sub.add_parser("status", help="read-only state of the 62 objects (workstation only)")
    status_parser.add_argument("--input", required=True, type=Path)
    status_parser.add_argument("--helm", required=True)
    status_parser.add_argument("--context", help="default <project>-dev-eks; no other context is accepted")
    status_parser.add_argument("--kubectl", default="kubectl")
    status_parser.add_argument("--terraform", default="terraform")
    status_parser.add_argument("--timeout", type=int, default=STATUS_TIMEOUT_SECONDS, choices=range(5, 121),
                               metavar="SECONDS")
    status_parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    if args.mode == "status":
        try:
            code, report = status(args.input, args.helm, args.context, args.kubectl, args.terraform,
                                  timeout=args.timeout)
        except (StatusError, PlanError, k8s_runtime_input.InputError, preflight.PreflightError, ValueError, KeyError,
                TypeError, IndexError, OSError, subprocess.CalledProcessError) as error:
            print("Stopped: " + str(error), file=sys.stderr)
            return 2
        if report is not None:
            print(json.dumps(report, indent=2) if args.format == "json" else status_text(report))
        return code
    try:
        report = plan(args.input, args.helm, args.fixture)
    except (PlanError, ValueError, KeyError, TypeError, IndexError, OSError, subprocess.CalledProcessError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.format == "json" else text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
