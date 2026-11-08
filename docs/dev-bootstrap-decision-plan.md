# Development bootstrap decision plan

## A. Executive decision summary

**Proposed recommendation; no decision is approved. All seven readiness gates
remain OPEN. No live AWS operations are authorized by this document.**

Use this order: approve a dedicated non-management workload account and identity
boundary; assign one state custodian; choose an artifact bootstrap/ownership
strategy; approve scoped deployment/upload IAM and budget/stop conditions; then
consider externally built ZIP publication, complete plan review and separately
authorized live validation. Gates 4–7 remain independent approval requirements.

Conditionally prefer **Option A**, a separately reviewed bucket-only bootstrap
using the existing S3 module, when no compatible approved bucket is available and
reviewers accept a controlled six-resource ownership handoff. Prefer evaluating B
if a compatible approved bucket is later evidenced. Reserve C for an explicitly
reviewed exception where maintaining one state outweighs targeting risk. None is
implemented or authorized. State-transfer complexity is A's main cost; an approved
handoff and recovery design is a prerequisite, not work to improvise during execution.

Source evidence establishes the fixed root/account guard, local backend, six S3
resources and required immutable ZIP reference. It cannot establish account
ownership, a suitable existing bucket, deployment rights, a real artifact, budget
or operational readiness. Current blockers are missing external approvals for
these matters and absent workload application/build implementation. Defer all
AWS execution, imports/state operations, packaging/uploads and secret initialization.

Evidence baseline: main `06f73d8a89f8c5eaca915e7d0b818d0284cc4ba8` and its
[successful post-merge CI 42530079959](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42530079959).
Reuse the [accepted offline evidence](offline-mvp-acceptance.md),
[seven readiness gates](dev-live-validation-readiness.md) and
[root contract](../infra/services/dev/ca-central-1/serverless-api/README.md).
Historical acceptance decisions and CI evidence remain unchanged. This plan adds
recommendations, not live evidence; no external service fact is presumed verified.

## B. Gate dependency sequence

```text
Dedicated Workload Account Decision
               |
               v
Account / Region / Identity Boundary
               |
               v
Terraform State Ownership Decision
               |
               v
S3 Artifact Bootstrap Strategy
               |
               v
Deployment IAM and Budget Approval
               |
               v
Approved External ZIP Publication
               |
               v
Complete Terraform Plan Review
               |
               v
Separately Authorized Live Validation
```

This is a logical decision sequence, not an execution authorization. Account
requirements, state-storage alternatives, packaging design, IAM categories and
budget assumptions can be designed in parallel. Actual account/Region/identity
verification must precede binding state ownership and permission scope. Bucket
provisioning or state reconciliation must wait for approved strategy, state
custody, Gate 4 IAM and Gate 7 cost/recovery approvals; they precede publication.
Publication also requires the reviewed build and upload identity. A complete plan
must use the resulting actual key/version and reconcile all resource ownership.
Live invocation/secret/logging validation additionally requires Gates 5–6 and a
separate authorization. Closing Gates 1–3 would not close Gates 4–7.

## C. Gate 1 — Workload account architecture

| Topic | Confirmed repository configuration | Recommended architecture | Missing external evidence | Required approval |
| --- | --- | --- | --- | --- |
| Account boundary | Required aws_account_id; root allowed_account_ids restriction | Separate approved workload account; exclude Organizations Management Account from workload/destructive testing | Ownership, intended use, account identity and organization placement; no existing account assumed | Account owner and security approver |
| Region boundary | Workload ca-central-1 | Keep workload Region fixed; independently record IAM Identity Center home Region, without assuming it equals workload Region | Actual workload availability and Identity Center instance/home Region/administrative prerequisites | Account/platform owner |
| Human access | Independent human-access module; not composed into workload root | Reviewed temporary-role access, MFA and bounded sessions; avoid persistent credentials | Federation/MFA enforcement, session expiry/revocation, permission-set assignment and access evidence | Identity/security owner |
| Execution identities | Root creates Lambda execution role only; no deployment/upload/client identity | Distinct human, deployment, Lambda execution, artifact-upload and API-client responsibilities, independently scoped | Principal ownership, trust and access paths, separation enforcement | IAM/security owner |
| Effective controls | Provider guard is configuration, not identity verification | Evaluate SCPs, permission boundaries and session policies where applicable; no management-account testing | Actual inherited denials, session restrictions, allowed actions and emergency revocation ownership | Organization/account security approver |

Provider selection remains root-owned. No account ID/name, role name, Identity
Center home Region or approval is fabricated here. MFA/session-duration choices
must match the actual identity system and risk assessment; exact values remain
unapproved. Session expiry and revoked access must have an external verification
protocol before live work. Codex Cloud never requests or uses AWS credentials.

## D. Gate 2 — Terraform state architecture

**At any point in time, a managed resource must have exactly one authoritative
Terraform state owner.**

The [local backend](../infra/services/dev/ca-central-1/serverless-api/backend.tf)
remains unchanged. Recommend one designated custodian, one authorized writer and
one authoritative state location, with encrypted storage/backups, least-privilege
access, integrity/version records and a recovery rehearsal. State/plan files stay
out of Git and general CI artifacts; metadata, identifiers and future sensitive
fields still require confidentiality even though Terraform manages no secret values.
Local file locking cannot coordinate separate copies or independent runners.
Require an external writer lease/change freeze and explicit operator handoff;
local state alone is unsuitable for unconstrained collaboration/automation.

Before bootstrap, record each of the six S3 resource identities, authoritative
state/address, custodian, backup and approval record. Importing an existing object
is ownership reconciliation, not proof of configuration safety. Review plans for
policy replacement, ownership/encryption changes, existing objects and deletions.
Never let bootstrap and workload states both operate on the same resources.

Any transfer needs an independently reviewed non-destructive design: freeze all
writers; inventory/snapshot both scopes; prepare and verify destination mappings
for all six resources; explicitly designate the authoritative custody cutover;
retire source ownership; verify destination identity and a complete no-unexpected-
change plan before resuming one writer. These are review obligations, not command
steps. Do not assume Terraform offers an atomic cross-state transfer. The reviewer
must specify the safe transition, authority during any interruption, evidence and
rollback; stop if exclusive ownership cannot be demonstrated. Archived snapshots
are recovery records, not concurrently operable states. No execution may proceed
on ambiguity or a second state that still claims live ownership.

Configuration rollback, state recovery and actual infrastructure recovery differ.
**Restoring Terraform state does not necessarily roll back AWS resources.**
Reconcile reality before subsequent operations; preserve uploaded versions and
partial-operation evidence. Source rollback cannot recover deleted data. Define
custodian access recovery, corruption handling and restore evidence before live
work. A future remote backend/migration requires its own design and approval;
it is neither implemented nor assumed to solve this bootstrap in this phase.

## E. Gate 3 — S3 artifact bootstrap architecture

Actual contracts: [S3 resources](../infra/modules/s3_artifact_bucket/main.tf) and
[ordered outputs](../infra/modules/s3_artifact_bucket/outputs.tf) manage exactly
aws_s3_bucket, aws_s3_bucket_versioning, aws_s3_bucket_public_access_block,
aws_s3_bucket_ownership_controls,
aws_s3_bucket_server_side_encryption_configuration and aws_s3_bucket_policy
(each named this). Preserve Enabled versioning, four public-access blocks,
BucketOwnerEnforced, AES256, reviewed HTTPS Deny and force_destroy=false.
Outputs wait for security/versioning configuration, not service propagation.

The [Lambda interface](../infra/modules/lambda/variables.tf) requires an existing
bucket/key and explicit immutable version, rejecting the null-version sentinel.
The [root](../infra/services/dev/ca-central-1/serverless-api/main.tf) passes the
actual bucket output and caller-supplied key/version. An empty new bucket cannot
satisfy that artifact contract. No flag, invented version or placeholder ZIP may
bypass it. Compatibility below means compatibility with source contracts, not
verified provider import behavior or live authorization.

### Option A — Independent bucket bootstrap configuration

| Criterion | Assessment |
| --- | --- |
| State ownership | Bootstrap state initially owns all six; explicit exclusive handoff to integrated root required; never dual active owners |
| Operational complexity | Higher: separate future reviewed configuration plus address mapping, cutover and retirement; clear provisioning/publication boundary |
| Risk of unintended infrastructure changes | Duplicate creation, stale ownership or mismatched policies at transfer; stop on replacement/deletion or unexplained full-plan changes |
| Recovery from partial failure | Retain protected bucket/objects, frozen writer and authoritative snapshots; reconcile failed publication or transfer before resuming; no automatic destroy |
| Compatibility with existing modules | Reuse existing six-resource S3 module; root still consumes actual output and real version; no child changes required by this proposal |
| Reproducibility | Pin existing Terraform/provider/lock and reviewed module revision; capture six identities and transfer evidence; state work remains an external controlled process |
| Required IAM boundaries | Scoped bootstrap deployment, separately scoped uploader, later workload deployment/PassRole; Lambda role gains no artifact rights |
| Required external evidence | Account/bucket ownership, approved bootstrap design, IAM/budget, effective versioning/security, artifact manifest, all-six-resource handoff and complete plan |

**Conditional preference:** A if no approved compatible bucket is available and
reviewers can approve exclusive transfer/recovery. It provides an understandable
bootstrap boundary but is unacceptable without a reliable handoff. Its future
configuration is a separate implementation task, not a file added here.

### Option B — Import a separately approved existing bucket

| Criterion | Assessment |
| --- | --- |
| State ownership | Establish existing owner first; release any prior authoritative management through approved custody transfer before workload control |
| Operational complexity | Discovery/import mapping for all six resources, existing object/policy review and reconciliation; suitable bucket existence is unverified |
| Risk of unintended infrastructure changes | Applying reviewed defaults could alter existing encryption, ownership, public access or policies; object/data impact and replacement/deletion must be reviewed |
| Recovery from partial failure | Preserve prior configuration/object inventory, backups and authoritative custody record; stop on identity mismatch or partial import; do not recreate/delete bucket |
| Compatibility with existing modules | Only acceptable if region, global namespace/name and six security/versioning contracts are compatible; import support/identifiers need external verification |
| Reproducibility | Document exact verified import mappings and reconciled configuration; repeatability depends on preexisting conditions, not just source |
| Required IAM boundaries | Authorized metadata discovery/import/refresh and narrowly reviewed configuration rights; separate object read/upload; assess existing access grants |
| Required external evidence | Approved bucket, Region/ownership, state owner, all six resource settings/identities, existing objects/versions/policies and full change-impact plan |

B can avoid provisioning and a new bootstrap state only when compatible ownership
is proved. Do not assume an available bucket or silently change its protections.

### Option C — Staged execution using integrated configuration

| Criterion | Assessment |
| --- | --- |
| State ownership | One eventual integrated state; avoids a cross-state handoff if exclusive custody is maintained throughout |
| Operational complexity | Fewer configurations but more demanding staged review and dependency awareness; exceptional operator procedure |
| Risk of unintended infrastructure changes | Selective targeting can omit dependencies, leave incomplete changes or exclude security resources; not a routine deployment strategy |
| Recovery from partial failure | Preserve same authoritative state and partial resource inventory; stop, reconcile and review complete configuration before continuing |
| Compatibility with existing modules | Source supports bucket output ordering, but exact staged resource/dependency behavior must be independently reviewed; no selective operation authorized |
| Reproducibility | Requires a separately reviewed procedure/revision and recorded evidence; targeting is not a replacement for a complete plan |
| Required IAM boundaries | Staged deployment rights scoped to approved scope, later workload/PassRole rights and distinct uploader; no broad grant to simplify staging |
| Required external evidence | Account/state approval, all-six security coverage, dependency analysis, stage stop points, artifact manifest and complete post-bootstrap plan |

C is an exception candidate, not a selected fallback or executable runbook. If A's
handoff cannot be approved, reopen the decision instead of silently executing C.

## F. Artifact publication contract

Tracked-file inspection at the baseline found Terraform modules/tests and Python
validation tools, with only the offline Terraform workflow. **No suitable Lambda
application implementation, ZIP artifact, packaging script or packaging/upload
workflow was found.** Synthetic runtime/handler strings in tests are not application
code. A reviewed application/build implementation is a future requirement.

| Responsibility | Future deliverable and acceptance evidence |
| --- | --- |
| Application owner | Approved source revision and behavior; selected nodejs22.x, python3.13 or java21 runtime and real matching handler; payload 2.0 compatibility |
| Build owner | Deterministic/reproducible ZIP packaging design; controlled dependencies/toolchain and build provenance; compatible x86_64 architecture (current module default), native libraries and runtime |
| Artifact reviewer | Reviewable cryptographic digest, source/build linkage and repeat-build or explained reproducibility evidence; no artifact version invented here |
| Bucket custodian | Verified ownership/Region, all six security controls and effective versioning/propagation evidence before publication; Terraform ordering alone is insufficient |
| Upload identity owner | Approved temporary upload identity with narrow bucket/key rights, bounded session/MFA controls as applicable and auditable publication; not the Lambda execution role |
| Publisher | Exact S3 key, immutable non-null object version ID and digest tied to approved ZIP; verify uploaded version identity/integrity through a later authorized process, not an assumed ETag checksum |
| Deployment reviewer | Approved artifact manifest supplied outside tracked private-account tfvars; matching bucket output, exact key/version, runtime/handler/architecture and complete plan |
| Recovery owner | Retained known-good source/build/manifests/object versions, rollback compatibility evidence and response to failed publication/deployment; never overwrite the record of a published version |

Object versions identify a version but do not prove code integrity or prevent an
authorized deletion. Retention/deletion rights and rollback lifetime need Gate 7
approval. No Object Lock or additional lifecycle resource is implied. Application
secrets remain external; packaging must not embed credentials or plaintext secrets.

## G. Required approvals — decision register

Recommendations below are separate from decisions. Owners are unassigned role
placeholders. Every entry is OPEN; all seven live-readiness gates remain OPEN.

| Decision ID | Topic | Recommended option | Evidence needed | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| D01 | Dedicated workload account | Approved separate non-management account, ca-central-1 | Ownership/use/identity and organization boundary evidence | Account owner — unassigned | OPEN |
| D02 | IAM identity/access boundary | Distinct temporary human/deployment/execution/upload/client roles; MFA/session controls | Identity Center home Region/prerequisites, trust, SCP/boundary/session review and revocation plan | Identity/security owner — unassigned | OPEN |
| D03 | State custodian/storage | Single custodian/writer, secured local authoritative state and backups | Storage/access/lease/recovery design and restore evidence | State owner — unassigned | OPEN |
| D04 | Artifact bootstrap strategy | A conditionally; evaluate B if suitable bucket proved; C exception only | Comparison acceptance, transition/recovery feasibility and dependency review | Infrastructure reviewer — unassigned | OPEN |
| D05 | Bucket/resource ownership | Exclusive owner for all six resources; reviewed cutover | Bucket identities, mappings, prior ownership, no-dual-owner evidence and full plan | State and bucket owners — unassigned | OPEN |
| D06 | Packaging/provenance | Separately reviewed application/build work | Source ownership, runtime/handler/architecture, reproducibility, digest/manifest and rollback artifact | Application/build owner — unassigned | OPEN |
| D07 | Upload/deployment permissions (Gate 4) | Scoped separate publication/deployment and reviewed PassRole | Exact actions/resources/conditions, artifact read/version rights and effective policy review | IAM/security approver — unassigned | OPEN |
| D08 | Budget/stop conditions (Gate 7) | Explicit budget/cost owner/alerts and halt criteria | Approved usage/pricing assumptions, alert routing, time/cost stop thresholds | Cost owner — unassigned | OPEN |
| D09 | Rollback/teardown | Retain recovery evidence; controlled deletion/revocation | Object-version handling, secret recovery, log deletion protection, ownership/recovery and retention plan | Operations owner — unassigned | OPEN |
| D10 | Remaining live gates 5–6 | Separate secret/KMS and API/logging approval | External value initialization/runtime retrieval, SigV4/invoke/deny and independent log delivery protocols | Application/security/operations reviewers — unassigned | OPEN |

## H. Implementation sequence after approval

These are proposed future work packages with review deliverables, not commands.
No work package grants execution authority; actual AWS operations require a
separately scoped authorization outside Codex Cloud. Design may progress without
AWS access; execution stops at every missing approval or contradictory evidence.

| Work package / kind | Prerequisites | Expected deliverable | Verification evidence | Security considerations | Stop condition | Approval dependency |
| --- | --- | --- | --- | --- | --- | --- |
| WP1 — Account/identity design | Existing root/account requirements | Recorded account boundary and five identity responsibilities | External owner/Region/identity-system confirmation | No management-account workloads; preserve provider account guard and MFA/session controls | Ownership, home Region or effective restrictions unresolved | D01–D02; any account operations separately authorized |
| WP2 — State and bootstrap design | Approved account boundary; state custodian candidate | Selected A/B/C proposal, six-resource ownership map, custody/cutover/recovery design | Independent architecture review, exclusive-owner model, backup/restore protocol | No concurrent writers, no unreviewed imports or migration | Transfer/recovery cannot demonstrate exclusive authority | D03–D05 |
| WP3 — Application/build implementation | Source owner and approved runtime contract | Separately reviewed runtime code, reproducible packaging design and candidate manifest | Code/build/security review, digest and compatibility/recovery evidence | No embedded secrets; no uploads in design/build authorization alone | Missing provenance or handler/architecture mismatch | D06; separately scoped implementation task |
| WP4 — IAM/cost/operations design | Selected bootstrap and identities; workload inventory | Scoped permission review and budget/alert/stop/teardown approvals | Effective-policy review and assigned recovery/cost owners | Separate upload/deploy/execution rights, scoped PassRole, preserve data | Unapproved permissions, costs or recovery plan | D07–D09; Gates 4 and 7 remain OPEN until evidenced |
| WP5 — Authorized external bucket bootstrap/reconciliation | Approved strategy, custodian, IAM, budget and recovery design | Compatible protected bucket under one authoritative owner | Actual six-resource identity/security/versioning and custody evidence | No targeting/import/state operations without explicit scope; preserve existing objects | Identity drift, dual ownership, missing protection or unexpected destructive change | D01–D05, D07–D09 plus explicit AWS execution authorization |
| WP6 — Authorized external artifact publication | Reviewed application/build and approved bucket/versioning/upload identity | Published approved ZIP with exact key/version/digest manifest | Actual version/integrity/provenance and rollback artifact verification | Least-privilege uploader; no plaintext secrets; immutable reference retained | Null/missing version, digest mismatch, expired access or incomplete propagation | D06–D09 plus publication authorization |
| WP7 — Complete plan review | Approved artifact manifest, exclusive workload state ownership and IAM scope | Full integrated plan reviewed against 17-resource intent and existing ownership | Actual account/Region and resource/reference/lifecycle review outside Codex Cloud | No invented version, bypass flag or unreviewed replacement; protect plan/state | Drift, unexplained deletions/replacements, missing IAM/cost approval | D01–D09 and separate authenticated-plan authorization |
| WP8 — Separately authorized live validation | Complete approved plan and all required live gate decisions | Scoped deployment/validation proposal and redacted operational evidence | Actual invoke/deny, exact permission, secret and separate log-delivery evidence | No implied authority from offline acceptance; approved costs/rollback/teardown | Any gate lacks approval or stop threshold reached | D10, applicable Gates 1–7 and new explicit live authorization |

Closing a design decision does not authorize its execution work package. Secret
initialization, API/log delivery, cost controls and teardown remain independent
obligations. No AWS credentials, account APIs, state manipulation, authenticated
plans, provisioning, uploads, secret initialization or live validation occurred.
