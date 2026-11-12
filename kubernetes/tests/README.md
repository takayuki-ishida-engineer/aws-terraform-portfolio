# Independent runtime and NP-1 checks

Run `python3 kubernetes/tests/check_runtime.py --helm /path/to/verified/helm` from
the repository. The [installer](../tools/install_helm.py) verifies the locked Helm
archive against its official published SHA-256 and its extracted executable hash.
All four vendored chart hashes and Python dependency hashes are verified at use.

Two actual positive renders (Kubernetes1.34/1.35, distinct backend ports/hostnames/
client pins) invoke four complete pinned Helm charts each. The independently
implemented validator checks exact62-object ownership inventory and124 schema
objects, using pinned core OpenAPI plus actual chart CRDs. It verifies IRSA SA,
RBAC/bindings/admission, TGB refs, private Services, selectors/ports, pinned images,
resource profiles, external CA dependencies, TLS MUTUAL/clientSPKI and STRICT/
default-deny policies. CRDs are canonical-hash pinned, not assumed from strings.

77 unsafe rendered mutations are actually submitted to validation: the existing
58 cases plus19 NP-1 cases. Existing cases include
TLS downgrades/identity removal/plaintext, wrong TGB target/type/VPC/networking,
LoadBalancer Service, port/selector/ref mistakes, broad RBAC/cluster-admin binding,
missing guards, controller flags, CA fallback, privilege/image/AZ changes and
missing/duplicate/forbidden objects. 18 invalid minimal inputs are rejected.
21 evidence faults reject missing/failed/partial/fabricated artifacts, hash/count
mismatch, malformed/duplicate/nonfinite JSON. Individual labels are emitted in
the JSON report. Counts derive from executed cases; they are not native Terraform
passes, simulated communications or a replacement for the153 toolkit tests.

NP-1 validates the actual NetworkPolicy in both rendered configurations: exact
namespace/API, all-Pod selector, both policyTypes, empty ingress/egress, namespace
ordering and unchanged STRICT/empty-ALLOW Istio declarations. `mesh_security`
contains five objects instead of four. The19 policy mutations remove or mis-scope
the policy, narrow selectors, omit a policy direction or rule list, add allow-all,
public IPv4 or all-namespace rules in either direction, change the API/namespace,
or insert another additive allow policy. Each is rejected by both the independent
policy-semantic check and full-bundle validation; inventory equality is not the
only protection. The extra two evidence faults reject an old mesh-stage count and
an omitted mesh stage. The schema subset adds the same pinned Kubernetes1.34.1
NetworkPolicy definition/reference closure, retaining all existing definitions.

These checks do not test packet filtering, CNI activation, application startup or
live admission/RBAC enforcement. Other installed policies may broaden traffic:
bundle validation cannot inspect or constrain an unconnected real Cluster.
Emulator: NOT_APPLICABLE. Kubernetes Live communications: NOT_TESTED.

`complete_runtime=true` means these runtime checks passed. Render/runtime reports
retain `complete_v5=false`; only final affected-local acceptance after Terraform,
workflow, docs, integrity and secret checks may mark the full offline handoff
complete. It never authorizes deployment, merge or final independent acceptance.
No external schema references, API discovery, Helm cluster operations, kubeconfig
or AWS calls occur. API-server defaulting/CEL/admission and actual injection,
handshakes/registration/capacity are external verification obligations.

Fixtures and expected inventories are explicit non-secret offline data. Do not
copy fixture account IDs, CIDRs, keys/pins or allocations into operational inputs.
