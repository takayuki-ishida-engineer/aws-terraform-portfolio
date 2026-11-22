#!/usr/bin/env python3
"""Offline deployment plan for the Kubernetes runtime (Step 1 item 6c-A).

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

``status``, ``apply`` and ``destroy`` are not implemented (item 6c-B onward). The
TargetGroupBinding's actor is the binding-writer ServiceAccount. How the operator
acts as it is not approved, and impersonation on the current EKS cluster is
NOT_TESTED, so that step is shown as BLOCKED.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k8s_certs  # noqa: E402
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
        "not_implemented": ["status", "apply", "destroy"],
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
    lines.append("Plan only: nothing was applied and no cluster or AWS API was contacted. status, apply and destroy "
                 "are not implemented. NOT_TESTED: " + "; ".join(report["not_tested"]) + ".")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    plan_parser = sub.add_parser("plan", help="render, validate and show the staged plan; executes nothing")
    plan_parser.add_argument("--input", required=True, type=Path)
    plan_parser.add_argument("--helm", required=True)
    plan_parser.add_argument("--fixture", action="store_true", help="the synthetic fixture input")
    plan_parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    try:
        report = plan(args.input, args.helm, args.fixture)
    except (PlanError, ValueError, KeyError, TypeError, IndexError, OSError, subprocess.CalledProcessError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.format == "json" else text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
