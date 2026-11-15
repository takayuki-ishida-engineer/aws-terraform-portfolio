# Owner-dispatched representative Emulator verification

Phase 3 supplies implementation and offline contracts only. **Lifecycle NOT_TESTED**:
no container, Emulator server, Terraform Apply/Destroy or workflow_dispatch has run
in this PR. A merged workflow is not AWS EMULATOR DEMONSTRATED or Portfolio Complete.
Operational Terraform, the existing required Full CI and Branch Protection are unchanged.

## Reviewed sources and fixed tools

Sources read on 2026-11-15: [Linux installation/signatures](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-linux.html),
[versioned packages](https://docs.aws.amazon.com/emulator/latest/userguide/versioning.html),
[Docker guidance](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html),
[CLI and generated files](https://docs.aws.amazon.com/emulator/latest/userguide/cli-reference.html),
[telemetry](https://docs.aws.amazon.com/emulator/latest/userguide/telemetry.html),
[AWS CLI signature guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
AWS does not publish a finished Emulator image. `Dockerfile` installs the signed
Linux package into a digest-pinned official Ubuntu image; no image is pushed.
Ubuntu amd64 digest provenance: [Docker Official Images metadata](https://github.com/docker-library/repo-info/blob/master/repos/ubuntu/remote/24.04.md).

`versions.json` fixes Emulator **1.0.385-1 amd64** (runtime version 1.0.385), Terraform
**1.17.0**, AWS Provider **6.72.0**, AWS CLI **2.35.0** and Ubuntu's image digest.
The Emulator DEB was actually downloaded from its versioned official URL and its
GPG signature checked against **98BCF336A3BE53B734E967C52E5BF49BD940F624**. Its SHA-256
is **5344b39e76089633f3cc2d8795e5554ff0a89f4c26bc316fa748b3909423d3f5**.
Package metadata confirms aws-emulator / 1.0.385-1 / amd64, libc6>=2.17; the reviewed
postinst only creates the binary symlink. It was not installed or started here.
This is new package evidence, not reuse of unverified historical 1.0.322 compatibility.
The AWS CLI archive was downloaded and verified using the official guide's key
**FB5DB77FD5C118B80511ADA8A6310ACC4672475C** and the locked SHA-256 in versions.json.
The checked-in ASC is its **public** verification key, not a credential/private key.
Terraform uses its fixed official release ZIP/checksum. Terraform's signed registry
installation and the existing committed network Root lock seed an offline provider
mirror. All downloads/install dependencies finish before isolation; runtime init
uses only the image's filesystem mirror with readonly lock. No init -upgrade.

## Owner gate and exact run order

1. Independent review and explicit Owner Squash Merge approval of this PR.
2. Confirm merge on main and successful exact-main Full CI.
3. Owner rechecks GitHub Free/Public visibility, standard ubuntu-24.04 eligibility,
   $0 Actions/Codespaces/Packages/Git LFS/AI Credits Budgets and usage blocking,
   current billing/free/storage conditions and sufficient free capacity.
   These are Owner attestations, **not an API Billing audit**. Unknown/inaccessible
   conditions stop execution; historical Budget existence is not current verification.
4. Owner starts `AWS Emulator representative verification` on main, supplies that
   exact 40-hex main SHA, checks the explicit confirmation and supplies the RFC3339
   timezone-aware timestamp of the just-completed checks (e.g. +09:00 or UTC).
   The confirmation expires after 30 minutes. Both actor and triggering actor must
   be the Owner; attempt must be 1. Use a fresh checked dispatch instead of rerun.
   Queue delays causing expiration are BLOCKED; do not waive freshness.
5. Checkout must equal the supplied SHA and workflow main SHA. Current implementation
   deliberately rejects PR/unreviewed/non-main targets. No arbitrary PR code execution.
6. Host verifies signatures/checksums/versions, prefetches the locked provider,
   resolves STS/EC2 public probe addresses and records the host netns identifier.
   Preparation does not make real AWS API requests or read AWS identities.
7. Build one temporary local image. No Artifacts, persistent caches, Packages, Git
   LFS, registry push, paid add-ons/Larger/self-hosted runners or paid fallback.
8. Run a nonroot, read-only container with network none, no port/bind/socket mounts,
   all capabilities dropped, no-new-privileges, 3 GiB memory/no swap, 2 CPUs and
   private tmpfs (2 GiB work + 64 MiB temp). Preparation requires >=2 CPUs,
   >=6 GiB available memory and >=10 GiB free disk; failures stop, never upgrade.
9. Independently inspect safe logs/summary and cleanup. Formal milestone acceptance
   still requires independent review/Owner decision; only measured operations count.

The manual workflow has only workflow_dispatch, contents:read, ubuntu-24.04,
25-minute timeout and a concurrency group that does not cancel a running lifecycle.
There is no AWS OIDC/Secrets input. Checkout uses the already approved full SHA,
persist-credentials=false, no submodules/LFS. No host authentication, token, profile,
home, Docker socket or operational checkout is mounted into the container.

`aws-emulator-contracts.yml` is a **separate static-only PR/main check**: it runs the
offline test suite, never prepare.py/lifecycle.py, Docker or resource operations.
This gives these new security contracts CI coverage without editing the existing
`terraform-offline-ci.yml` or changing its Required Check. Its read-only standard
runner uses no paid feature, Artifact or persistent cache.

## Safety matrix: implementation versus evidence

All runtime rows below are **NOT_TESTED** in this PR; Codex Cloud's known namespace
restriction stays environment **BLOCKED** and is not bypassed. Package signatures
were verified separately as described above, not an actual isolated run.

| Control | Implemented guard / evidence produced only during actual dispatch |
| --- | --- |
| 1 | Fixed signed official DEB, exact publisher fingerprint, artifact hashes, package/runtime versions; bad/expired/revoked signature rejected |
| 2 | Bind exactly 127.0.0.1:9297, require exact HTTPS startup endpoint; no Docker port publication |
| 3 | Fresh private HOME, generated credentials/CA only, default generated profile, --auth on, unsigned EC2 must return 403; 404 is insufficient |
| 4 | Generated CA + strict hostname/TLS validation; system trust must reject private CA; no verification-disable flag |
| 5 | --telemetry off and EMULATOR_TELEMETRY=off, no external routes |
| 6 | Docker network none; actual netns differs from host; only lo, IPv4/IPv6 all-table routes loopback only |
| 7 | Pre-resolved public STS/EC2 IPs fail direct TCP with ENETUNREACH/EHOSTUNREACH; timeout/refusal/DNS failure alone insufficient |
| 8 | Signed local STS account 000000000000 and exact user/emulator ARN |
| 9 | Literal loopback EC2/STS endpoints, ca-central-1, account guard, CA; credentials validation remains enabled |
| 10 | Image contains only adapter + public tool material; Root/State/private files on fresh tmpfs, no operational Root/State |
| 11 | Saved Plan JSON/version/configuration/change inventory checks, exact single aws_vpc.proof, CIDR/run tags/action/owned ID, hash recheck before apply |
| 12 | State ID must match independently described VPC, exact CIDR/run tags; pre-existing VPC snapshot preserved |
| 13 | Independent API creation/update/absence checks; InvalidVpcID.NotFound required, baseline unchanged and State empty before shutdown |
| 14 | Destroy via reviewed saved destroy plan; private State/backups/plans/credentials/CA/logs removed, only own image/container/context cleaned |

The adapter uses 10.238.0.0/16 as **synthetic test data**, never an operational
allocation; a pre-existing VPC with that CIDR stops before create. No module-wide
AWS compatibility, actual IAM/network/mTLS/availability/cost behavior is established.
State/credentials/CA/private log/plan material is never printed or uploaded.
Only safe gate/status/exit codes, package metadata, SHA and verified VPC IDs leave
the container. Summary cannot turn partial evidence into successful completion.

## Lifecycle and failure cleanup

Reviewed create Plan -> Apply -> State/API ID/CIDR/run-tag match -> refresh-only
no-change Plan -> reviewed tag-update Plan/Apply -> independent API match -> no-op
Plan -> reviewed destroy Plan/Apply -> State empty + independent ID NotFound +
pre-existing inventory unchanged -> process/material cleanup. Applying a saved
`plan -destroy` artifact is the Terraform Destroy operation; no unreviewed destroy
command or broad API deletion is substituted.

If a resource operation fails, recovery can destroy only the single newly owned
ID that matches State/API/baseline/run marker/CIDR. An ambiguous ID or foreign
resource stops cleanup and fails the job. A partial create with no State may use
strictly identified API cleanup; it is labeled separately and never counts as
Terraform Destroy or a complete demonstrated lifecycle. Actual 501 with an API
operation name is recorded only for that operation; unrelated setup/configuration
errors are not PARTIAL-SKIP. Missing evidence, stopped Emulator, timeout/OOM,
failed Destroy or incomplete cleanup cannot produce a successful milestone.
Emulator shutdown loses memory but does not count as independent Destroy proof.

## Offline PR checks

Run `PYTHONDONTWRITEBYTECODE=1 python3 scripts/emulator-verification/tests/test_verification.py`.
Nineteen test methods execute explicit negative/mutation subcases, including real
GPG rejection of an invalid signature, actual initial consent script execution,
route/reachability/STS/Plan/ID/evidence mutations, changed saved-plan refusal,
strict TLS configuration, failed cleanup coordination and secret-output suppression.
Fixtures and mocked lifecycle calls are synthetic; they are never run evidence.
The adapter separately passed backend-disabled readonly-lock init/validate and fmt
in an external temporary directory. This does not start Emulator or apply resources.
Future runtime/cleanup compatibility, Docker execution and cost eligibility remain
unproven until the separately authorized merged-main dispatch.
