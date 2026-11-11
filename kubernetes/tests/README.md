# Independent V5 runtime checks

Run `python3 kubernetes/tests/check_runtime.py --helm /path/to/verified/helm` from
the repository. The [installer](../tools/install_helm.py) verifies the locked Helm
archive against its official published SHA-256 and its extracted executable hash.
All four vendored chart hashes and Python dependency hashes are verified at use.

Two actual positive renders (Kubernetes1.34/1.35, distinct backend ports/hostnames/
client pins) invoke four complete pinned Helm charts each. The independently
implemented validator checks exact61-object ownership inventory and122 schema
objects, using pinned core OpenAPI plus actual chart CRDs. It verifies IRSA SA,
RBAC/bindings/admission, TGB refs, private Services, selectors/ports, pinned images,
resource profiles, external CA dependencies, TLS MUTUAL/clientSPKI and STRICT/
default-deny policies. CRDs are canonical-hash pinned, not assumed from strings.

58 unsafe rendered mutations are actually submitted to validation, including
TLS downgrades/identity removal/plaintext, wrong TGB target/type/VPC/networking,
LoadBalancer Service, port/selector/ref mistakes, broad RBAC/cluster-admin binding,
missing guards, controller flags, CA fallback, privilege/image/AZ changes and
missing/duplicate/forbidden objects. 18 invalid minimal inputs are rejected.
19 evidence faults reject missing/failed/partial/fabricated artifacts, hash/count
mismatch, malformed/duplicate/nonfinite JSON. Individual labels are emitted in
the JSON report. Counts derive from executed cases; they are not native Terraform
passes, simulated communications or a replacement for the153 toolkit tests.

`complete_runtime=true` means these runtime checks passed. Render/runtime reports
retain `complete_v5=false`; only final affected-local acceptance after Terraform,
workflow, docs, integrity and secret checks may mark the full offline handoff
complete. It never authorizes deployment, merge or final independent acceptance.
No external schema references, API discovery, Helm cluster operations, kubeconfig
or AWS calls occur. API-server defaulting/CEL/admission and actual injection,
handshakes/registration/capacity are external verification obligations.

Fixtures and expected inventories are explicit non-secret offline data. Do not
copy fixture account IDs, CIDRs, keys/pins or allocations into operational inputs.
