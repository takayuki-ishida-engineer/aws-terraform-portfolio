# Locked offline dependencies

Chart .tgz files are intentional source artifacts downloaded from the official
repositories, not executable tool binaries. Versions, URLs and published package
SHA-256 values are in [dependencies.lock.json](../dependencies.lock.json).
Istio package GETs used the official blob.istio.io → istio-release.r2.istio.io path.
Helm is downloaded to temporary storage and checked against upstream and locked
archive/executable hashes; no remote installer is executed.

pyyaml6.0.3 and fastjsonschema2.21.2 are pure-Python source subsets from
the exact upstream commits in the lock, with original and whitespace-normalized source hashes and
LICENSE files retained. No pip installation or external runtime dependency fetch
is needed. The schema subset contains the192-definition dependency closure of the
15 core kinds used here from Kubernetes v1.34.1 official OpenAPI; upstream Git blob
and full-source/subset hashes are recorded. Custom CRD schemas come from the
pinned charts. Nothing fetches schema refs over the network during validation.
These are structural/semantic offline checks, not a Kubernetes API server.
