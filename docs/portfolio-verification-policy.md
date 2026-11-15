# Portfolio verification policy — evidence and operating boundaries

Current operating requirements are the owner-authorized Master Policy v14.2
[alignment record](policy-v14-2-alignment.md). Core Implementation and mandatory
portfolio-level representative Emulator demonstration have separate acceptance
gates. Historical v10–v14.1 design and evidence stay scoped.
See [policy authority and PDF limitations](architecture-v2.md#authority-evidence-and-status).
No unavailable PDF contents or new implementation/Live approvals are inferred.

<a id="official-aws-emulator--policy-v13"></a>

## Official AWS Emulator — safety boundary

The legacy v13 anchor above preserves historical links, not old policy authority.

The approved permanent [AGENTS rules](../AGENTS.md#mandatory-official-aws-emulator-safety-controls)
are the mandatory lifecycle safety checklist. Real AWS credentials/SSO,
authenticated real APIs and real AWS Plan/Apply/Destroy/Import remain prohibited
in Codex Cloud. Isolated official Emulator Plan/Apply/Read/Refresh/Update/Destroy
is permitted only under all fourteen controls. Representative demonstration is
mandatory at portfolio level; lifecycle for every resource is not a blanket
implementation PR prerequisite. No real AWS fallback is permitted.

For every Terraform implementation, require affected offline/security checks,
unchanged Full CI, independent review and user approval. For separately approved
Emulator work, identify supported operations, establish isolation, exercise the
approved lifecycle, independently verify identity/cleanup and record evidence.
The mandatory controls include pinned signature-verified Emulator, loopback HTTPS,
generated credentials/CA, verified TLS, telemetry off, network namespace without
external routes, independent external-AWS denial, local STS account `000000000000`,
explicit endpoints/account guard, disposable adapter Root/State, reviewed plans,
exact ownership, independent create/delete checks and full temporary-file cleanup.
Never weaken production security or alter operational Roots/State for the emulator.

Preserve every existing Native/Mock Plan/Python/Security/Negative/Mutation check.
Emulator execution is separate from required Full CI. A dedicated workflow_dispatch
workflow may be designed in a separately approved PR and run only after its merge,
on standard public GitHub-hosted Ubuntu runners without additional charges.
No such workflow is introduced here. Documentation changes require documentation
checks and existing Full CI on every PR, without lifecycle replay.
PASS means directly demonstrated; PARTIAL means partial evidence; PARTIAL-SKIP
requires actual evidence of the specific unimplemented API (for example HTTP 501).
FAIL is a Terraform/configuration defect requiring correction/retest; BLOCKED is
an unmet installation/network/isolation/runtime prerequisite; NOT_TESTED means
unexecuted. Never count unsupported APIs, skipped behavior or failed setup as PASS.
Stop for user permission on any new external download domain, without mirrors or
policy bypass. Significant verification gaps require explicit residual risk and
options; real AWS remains a separate optional user decision outside Codex Cloud.

### Historical feasibility proof — limited to aws_vpc

The owner-authorized, one-time experiment was reported against reference main
`e1cdbce78ba11959093a99ffd9300b8c0f9e52e0`, with official Emulator 1.0.322,
Terraform 1.17.0, AWS Provider 6.72.0 and CLI 2.35.0. It used only disposable
`aws_vpc.proof`, synthetic account `000000000000` and Region ca-central-1.

| Historical operation/control | Reported outcome |
| --- | --- |
| Terraform Create, Read/Refresh and no-op Plan | PASS |
| In-place Name tag Update and subsequent no-op Plan | PASS |
| Terraform Destroy | PASS |
| Independent API deletion verification | PASS; HTTP 400 InvalidVpcID.NotFound |
| Temporary State/credential cleanup and external isolation | PASS |

Saved create/destroy plans contained only the test VPC. Independent CLI checks
confirmed the created ID/CIDR, updated tag, subsequent absence and preservation
of pre-existing VPCs. SDK HTTP evidence was captured at service level; individual
SDK operation/status mapping was not retained. This is previously reported
experiment evidence, not a replay or CI result from this documentation PR.
No Subnet, NAT, EKS, IAM, Cognito, RDS, other-service or full VPC-module lifecycle
compatibility is established. No real AWS IAM/network/cost/availability/recovery
claim follows from it. Original historical acceptance records remain unchanged.

### Default portfolio completion path

Real AWS deployment is not mandatory. Core Implementation uses correct source and
architecture, affected offline/security/mutation/evidence checks and complete
credential-free Full CI on every PR, with independent review and user approval.
Representative Emulator lifecycle remains a separate portfolio-level requirement,
not a blanket per-resource PR gate. CORE PORTFOLIO COMPLETE independently requires all approved Core scope implemented,
reviewed, owner-approved and merged with offline/security quality, Full CI and
unverified scope explicit, without requiring Emulator demonstration.
AWS EMULATOR DEMONSTRATED separately requires actual representative lifecycle and
cleanup under all fourteen controls. PORTFOLIO COMPLETE requires both statuses;
no individual PR or historical VPC result declares completion. Optional real AWS verification
requires a separate user decision and G01–G07, cumulative actual JPY 10,000 and
complete verified teardown within 72 hours. Secrets Manager's 30-day recovery
conflict remains OPEN. Emulator success never becomes actual AWS deployment evidence.

## V6 Cognito source foundation

Accepted post-V5 main `97f870753926398368733c39da722d5d7b792fa5` passed
[push CI43109394809](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43109394809)
(686 native/153 toolkit/13 configurations). V6 adds [cognito_auth](../infra/modules/cognito_auth/README.md) and
DEV ca-central-1/api Root, five resources: protected email User Pool, prefix domain
managed-login2, Resource Server, public code-only client and default branding.
Future REST belongs in the same API State; historical HTTP API remains unchanged.
Google IdP/Secret, actual users, email delivery, browser PKCE, real authentication,
REST integration and backend tenant/owner authorization are not complete.
Local Child49/Root46 native plus independent safety/evidence checks supplement
existing686; expected full CI781/153 and15 shared-provider configurations requires
independent exact-HEAD review. No AWS/State/Live execution or unavailable PDF claim.
G01–G07, JPY10,000/72-hour removal, paid-plan/callback/account approvals and the
Secrets recovery blocker remain OPEN. Historical status sections retain their scope.

## Evidence states and completion boundary

The approved [Architecture v2 target](architecture-v2.md) is documentation, not
implementation or Live authorization. Label each component/environment separately:

| Evidence state | Required evidence | Limitation |
| --- | --- | --- |
| Defined, not deployed | Approved architecture/environment contract | Does not establish implemented source or a passed test |
| Core Implementation — offline tested | Source revision, affected fmt/init/validate/Native/Mock/Negative/Security/Mutation/Evidence, exact-HEAD Full CI, independent review and user approval | Not whole-portfolio completion, deployed identity, authorization or service operation |
| EMULATOR DEMONSTRATED | Pinned versions, all fourteen controls, actual representative lifecycle, independent identity/cleanup evidence | Limited to successfully measured resource/API behavior; not real AWS deployment or security effectiveness |
| DEV Live tested with explicit approved evidence | Separately authorized scenario, actual outcomes and redacted evidence | Applies only to scenarios/resources/revisions actually verified |
| OPEN / awaiting approval | Explicit unresolved decision, scenario or approval | No assumption of implementation, authorization or success |

The implemented **post-R2** HTTP API baseline is main
`df5ef4b2e03bd55109b0490b1e63d1d4199b663b`: eight reusable modules, four DEV instances,
17 managed resources, eight outputs and five exact resource moves. Its
[successful CI 42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148) records **491 native / 153 Python** tests.
The pre-R1 nine-module/seven-instance **384/153**
[acceptance](offline-mvp-acceptance.md) at main
`89755c30508b78527fd46fa18593d5d5b11150f1` stays historical and unchanged;
R1 main `87f415f5290e2cab63696e1850a6c362eef97292` records 438/153.
17 is not a v2 Live inventory. REST/NLB/Istio/mTLS and new delivery/admin components
remain defined or OPEN. No DEV Live outcome or actual state migration is claimed.
All G01–G07 in the [readiness document](dev-live-validation-readiness.md) stay OPEN.
R3 documentation completion cannot replace exact post-R3 main/R4 regression review.

### V4 source/evidence boundary

Accepted V3 main `6b185820c806a0c96410a145106b9f103db14d89` has successful
[push CI42720431920](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42720431920)
(641 native/153 Python). V4's [static private ingress](../infra/modules/private_ingress/README.md)
is a candidate implementation with local Child28/Root38 native evidence and
independent actual-plan/security/source/evidence-fault checks. Full CI expectation
678 native/153 Python/13 configurations still needs exact-HEAD independent review.
Internal TCP/IP ownership and paired SG rules do not prove registered targets,
webhook/controller effectiveness, TLS/mTLS or application authorization. TGB
RBAC/IAM, AWS-managed SG/Pod SG assumptions, actual connectivity and all G01–G07
remain OPEN. Earlier post-R2/pre-R1 evidence above is preserved history.

## V5 private runtime source and offline evidence

Accepted post-V4 main `a4f0a9b8b0a810976c7ab305001729463443b27b` passed
[CI42757339642](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42757339642)
with678 native/153 toolkit and13 initialized configurations. V5 extends the same
Platform/private_ingress owner with exact EKS IRSA Role+registration-only policy
and four scoped Istio webhook/XDS SG rules. There are still10 children/three DEV
Roots/13 configurations; basic Platform has54 resources (EKS37+ingress17).
Existing NLB/TG/static SG/provider/state interfaces remain owned as before.

The [runtime foundation](../kubernetes/README.md) renders pinned LBC3.6.2 and Istio1.32.0 using
verified Helm3.22.1. Its61 objects implement ClusterIP Gateway, exact guarded TGB,
external CA/Secret references, MUTUAL TLS>=1.2 with client SPKI, STRICT mesh and
namespace default deny. No application or authenticated deployment is performed.
Actual local checks: Child36/Root38/EKS52 native; runtime8 Helm renders,
122 schema objects,58 security mutations,18 invalid inputs,19 evidence faults.
Expected full CI686 native/153 toolkit remains for independent exact-HEAD review,
not a completed CI claim. Historical V3/V4 snapshots retain their original scope.

Registration-only IAM excludes ModifyTargetGroup/Attributes and SG writes. LBC
has no universal TGB-only switch; layered flags/RBAC/admission/IAM and clean
existing-resource inventory are mandatory. Effective admission, CA custody,
application sidecar CNI under restricted PSS, real AWS references/output publication,
capacity/connectivity and future REST backend TLS/SNI compatibility remain OPEN.
Offline schemas do not prove handshakes, IAM, controller effectiveness or Live.
G01–G07, cumulative JPY10,000, complete72-hour removal and the Secrets Manager
30-day recovery conflict remain unchanged. No State/AWS/Kubernetes Live authority.

## All environments — applicable offline implementation gate

For new/changed implemented modules and environment configurations require:

- Terraform formatting, credential-free initialization/validation and reviewed
  locks; root-owned providers/account restrictions, env/Region/service state and
  single authoritative resource owner, backups/locking and lifecycle safeguards.
- Actual mock-plan/resource inventories, outputs, cross-module identities,
  dependencies and resource ownership; no wholesale module substitution to hide
  incompatibility. Known/unknown plan fields and evidence errors fail closed.
- Proportionate positive, negative/input-boundary and security mutation cases.
  Mutations must detect deliberate unsafe changes; missing, malformed, skipped,
  failed or incomplete evidence is never a pass. Intentional rejected inputs do
  not count as successfully planned resource configurations.
- IAM trust/permissions and permission boundaries, scoped PassRole, OIDC audience/
  subject, ServiceAccount rights/RBAC, separation of human/deploy/upload/workload/
  client identities, secret avoidance in inputs/data/plans/state/logs and outputs.
- Network exposure/private routing/egress, state and data confidentiality,
  immutable artifacts/image digests/provenance, release ownership and rollback/
  recovery/lifecycle contracts; secret marking alone is not a persistence control.
- Environment-specific capacity/topology verification, including safe DEV system/
  mesh/monitoring fit and STG/PROD remaining-AZ peak CPU/memory/Pod/IP/DB-connection
  capacity, topology spread/PDB/readiness/update headroom and bounded HPA + Cluster
  Autoscaler. No concurrent Karpenter ownership or resilience inferred from counts.
- Full GitHub Actions regression including Terraform/Python, IAM reference,
  equivalence/negative/mutation tests and independent security guardrails.

### Target security verification categories

| Category | Required affected offline contracts and deliberate unsafe/negative cases |
| --- | --- |
| CloudFront / REST inbound mTLS | Origin clientAuth certificate/Region, Regional custom-domain versioned truststore, minimal CA scope/issuance, edge/Regional WAF and default execute-api bypass prevention; reject missing/invalid/untrusted/expired or unexpected certificate identities as applicable; do not claim mock checks perform live TLS |
| Certificate identity / revocation | API Gateway checks supported certificate properties/chain/validity but does not automatically check revocation. Verify that trusted-CA siblings cannot be assumed authorized as the expected CloudFront client. Review unauthorized identity rejection, compromise response, rotation/expiry monitoring and revocation-equivalent controls; mechanism feasibility, ownership, fail behavior and evidence remain OPEN |
| Cognito coexistence | Preserve Cognito User Pool Authorizer and method OAuth scopes; do not assume a Lambda Authorizer can be added alongside Cognito on the same REST method. Additional certificate authorization/revocation checks require compatibility/security/operational review, not selection in this PR |
| REST VPC Link V2 / NLB / Gateway | Internal NLB TCP:443 passthrough, target group/controller ownership, Pod IP/health/subnet/SG constraints, API backend client certificate and Gateway server chain/name/SNI; reject TLS termination at wrong boundary, insecureSkipVerification, unrestricted trust and plaintext fallback |
| Istio STRICT mesh | SPIFFE principal/SAN mapping, short-lived workload certs and AuthorizationPolicy; deny missing client cert, invalid CA, wrong SAN/identity, unauthorized principal, disallowed plaintext and expired certificates. Review selected PKI rotation/revocation-equivalent behavior; never invent automatic managed-service revocation |
| Cognito / backend user authorization | Valid access token and scope acceptance; missing/invalid/expired/wrong-scope denials; wrong-owner and cross-tenant denial independent of transport. ID tokens do not substitute for scoped authorization |
| EKS / DB / network | Private exposure/egress, RBAC/NetworkPolicy/default deny as appropriate, topology/capacity; PostgreSQL CA/hostname TLS verification plus approved DB auth, backup/PITR/reconnection/schema recovery. Do not impose custom client-cert mTLS on browser/managed AWS APIs/standard RDS/local same-Pod/control-plane traffic |
| Delivery / notifications | Version/digest pinning, scoped OIDC/CodeBuild IAM and private access, single release/controller owners, release health and verified rollback identity, correlated build/deploy/rollback success/failure events and independently handled notification failures |
| EC2 scheduling / watchdog | America/Toronto weekday START 08:00 / STOP 19:00 (no holiday calendar, DST-aware); Scheduler→SQS→Controller→EC2 and separate Watchdog. Detect failed/non-executed START/STOP, stale commands/retries/DLQ, state/SSM-readiness mismatch, unexpected running, Watchdog and SNS failures; thresholds remain OPEN |

TLS encryption, server verification, client certificate authentication/identity,
revocation response, Cognito user authentication and backend authorization are
distinct contracts. Minimum trust is not a proven single-client allowlist.

### Historical floor and responsibility

Keep all existing HTTP API, Terraform, Python, IAM, negative, mutation and security
checks intact. Recorded **384 Terraform native tests / 153 Python tests** are
historical pre-R1 acceptance evidence, not an upper limit or new mTLS coverage.
The verified post-R2 491/153 result above has separate categories: root 12 input
rejections/35 mutations/22 capture faults; API 28 mutations/25 capture faults/4
source mutations; retained R1 source mutations 3 and exact move-set negatives 6.
Historical HTTP API 17/19 and R1 438/153 remain tied to their earlier revisions,
not current counts. New security behavior needs its own tests.
Never remove/disable/skip/weaken CI checks for efficiency or migration.

Codex performs affected local checks and opens the PR; GitHub Actions runs complete
regression, and independent review verifies completed CI and merge authorization.
Documentation-only changes use consistency/links/scope/secret/diff checks, not
unrelated full local regression. Do not repeatedly inspect successful logs. Verify exact-HEAD Full CI completion
for every PR before the independent-review/owner-approval handoff. V5 extends CI with actual pinned runtime validation without weakening existing checks.

## DEV Live — approved limits, scenario details OPEN

No real AWS Live operation is authorized by this PR. Actual external execution
requires all applicable gate evidence, independent approval and explicit scope outside Codex
Cloud. Never request/use real AWS credentials, authenticated real AWS APIs/plans,
operational State operations or real AWS apply/destroy/deployments in Codex Cloud.
Isolated emulator verification follows the unchanged fourteen controls above and is not Live.
No workload/destructive testing in the Organizations Management Account.

**Actual cumulative DEV Live spending must stay within JPY 10,000 across the
approved validation period. All testing and verified complete teardown must finish
within 72 hours from approved Live start.** Prefer shorter execution where possible.
Older monthly examples are not spending limits or sizing approvals.

Before paid resources, independently review actual pricing/Region/runtime, tax,
FX, fixed/usage charges, retained charges, certificate lifecycle, contingency and
teardown. **CloudFront Origin mTLS supports Business, Premium and Pay-as-you-go,
not Free.** Review applicable plan/feature availability and all other service costs
before implementation or Live; no plan is selected/purchased here. A 72-hour run
does not guarantee compliance. If validated cost plus contingency/teardown cannot
fit the cap, the scenario is not authorized and stays OPEN or Offline-only.
Budgets/alerts are not real-time enforcement or guaranteed billing cutoff. Assign
manual stop authority, monitoring, inventory and a reviewed execution timeline;
stop early enough to remain under both limits.

Prioritize only feasible approved evidence:

| Priority | Scenario | Required actual record |
| --- | --- | --- |
| 1 | Approved Terraform creation and inventory | Exact revision, approved account/Region/state/identity, reviewed complete scenario plan, actual creation and full managed/external inventory; unexpected changes stop execution |
| 2 | Istio STRICT mTLS positive/negative communication | Expected identities/trust/authorization and actual permitted/denied cases; no assumed encryption or revocation results |
| 3 | REST API → VPC Link V2 → NLB → Istio backend certificate authentication | Actual passthrough and Gateway server-name/trust/client-certificate verification, positive/negative outcomes and redacted correlation |
| 4 | Deployment, rollback and notifications | Only remaining approved affordable scope: pinned build/version/digest, actual health and rollback identity, success/failure event delivery and independent delivery-failure handling |

CloudFront-origin mTLS, Cognito, RDS and full delivery integration are future
scenario candidates, not a mandatory simultaneous stack if limits cannot be met.
Any executed protected-route scenario still requires the relevant token/scope/
owner negatives and live certificate-boundary checks. Do not weaken a selected
scenario's security to fit cost. Unexecuted scenarios stay OPEN or Offline-only,
never passed; offline definition remains required for the full portfolio target.

Record expected/actual outcomes including failures, revision/build, approvals,
redacted resource references, timings, certificate identities/trust revisions,
image digest/object version, correlation and follow-up. No secret/token/private
key/payload/state or unredacted plan in Git/public logs. Preserve approved redacted
audit evidence outside AWS before cleanup. Infrastructure recovery, application
rollback and DB recovery are separate, not inferred from each other's success.

### Complete teardown is an acceptance condition

Delete and independently verify removal of **all AWS resources created for the
exercise**, Terraform-managed and external/service-managed dependencies. Reconcile
actual AWS inventory with state and external records; neither stopped instances
nor a successful terraform destroy alone establishes completion. Never delete
pre-existing shared resources. Inventory applicable EKS/control planes/nodes,
ENIs/EBS, NLB, NAT/EIPs/endpoints, RDS/backups/snapshots, S3 versions/delete markers,
ECR images, logs, secrets, API/custom domains, ACM, WAF, KMS and related dependencies.
Review AMIs, retained backups, deletion protection, secret recovery windows, delayed
deletion and external retention before approving Live. Avoid newly created CMKs or
other unavoidable delays incompatible with the deadline; start teardown early.

The historical secret module's 30-day recovery means the full unchanged MVP is not
a feasible 72-hour actual-deletion scenario. Resolve applicable lifecycle/scenario
blockers in separately reviewed work before creation; no bypass is authorized here.
After cleanup no exercise resources should remain generating ongoing charges.
Delayed billing, historical usage and FX may still produce later invoices; do not
promise literally zero subsequent billing. Administration EC2 scheduling does not
replace this deadline or stop other-service billing.

## STG / PROD — offline-only portfolio acceptance

Require implemented credential-free offline contracts for two active AZs, per-AZ
NAT/node capacity, redundant Istiod/Gateway/apps, HPA + Cluster Autoscaler,
spread/PDB/readiness and remaining-AZ capacity model, and Aurora Provisioned
writer/reader placement. No apply, authenticated plan, or live failover/load/
penetration/monitoring/recovery test is required for portfolio completion.
Never label unexecuted tests passed or counts as measured SLA/RTO/RPO.

Real production work would separately require reviewed threat/penetration/load,
observability/alerting, expiry/rotation/compromise, AZ/node/DB failover/reconnection,
backup/PITR/schema/state recovery, revocation, cost and teardown exercises with
actual evidence and approved objectives. No cross-region DR/cold standby or
long-running production operations are introduced. All missing approvals and live
outcomes remain OPEN; independent review verifies this PR's completed CI separately.
