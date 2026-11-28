---
name: evidence-package
description: Build and publish a sanitized formal evidence package (original logs, derived copies, manifests) to the evidence branch under a scoped publication decision, following MASTER_POLICY EB01-12, LC01-06 and EP01-04. Use only when a task asks for an evidence package.
disable-model-invocation: true
effort: low
---

# Evidence package

1. Scratch is temporary preparation and retention only, never the formal delivery
   channel; do not ask the Owner to download and re-upload scratch files.
2. Keep original logs and derived sanitized copies separate. Failed-attempt logs stay,
   labelled with their cause. For an unpublishable original, record its exact
   URI/path, size, SHA-256 and the exclusion reason.
3. Redact signed URL query strings and record each redaction. Fail closed on a secret
   scan of the staged tree. Never include State, plans, credentials, environment
   values or private account data; record credential variables by name only.
4. Required members: `MANIFEST.json` (decision IDs, actor, branch, base, HEAD, tree, PR,
   run, attempt, action identity, required check App, result, hashes, failures and
   limitations; `N/A - <reason>` where a field does not apply, never an unobserved
   value), `SHA256SUMS`, `REDISTRIBUTION_INVENTORY.json`, reproduction details and a
   Mandatory Self Review.
5. Publish only under the exact publication decision: `evidence` branch, a new dated
   path, an appended `EVIDENCE_INDEX.json` record, earlier blobs and records
   unchanged, fast-forward push only (no force, no deletion, no merge with `main`).
6. Re-read the published bytes from the remote and verify size, SHA-256, ZIP CRC,
   manifest, member hashes, inventory and preservation of earlier evidence.
7. Classify only what was observed: PASS, PARTIAL, HOLD, BLOCKED, NOT_TESTED,
   NOT_RECOVERED, NOT_VERIFIED. No overall PASS unless every mandatory condition holds.
