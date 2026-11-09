# Portfolio verification policy — evidence and operating boundaries

Current approved operating policy is Master Policy v11 (2026-11-09), per user
approval; the target/security text retains recorded historical v10 provenance.
See [policy authority and PDF limitations](architecture-v2.md#authority-evidence-and-status).
No unavailable PDF contents or new implementation/Live approvals are inferred.

## Evidence states and completion boundary

The approved [Architecture v2 target](architecture-v2.md) is documentation, not
implementation or Live authorization. Label each component/environment separately:

| Evidence state | Required evidence | Limitation |
| --- | --- | --- |
| Defined, not deployed | Approved architecture/environment contract | Does not establish implemented source or a passed test |
| Implemented and tested offline | Source revision plus actual mock/static/security and successful CI evidence | Does not establish deployed identity, authorization or service operation |
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
unrelated full local regression. Do not repeatedly inspect successful logs or
poll/wait for CI. No CI implementation is changed here.

## DEV Live — approved limits, scenario details OPEN

No operation is authorized by this PR. Actual external execution requires all
applicable gate evidence, independent approval and explicit scope outside Codex
Cloud. Never request/use AWS credentials, authenticated APIs/plans, state
operations, apply/destroy or deployments in Codex Cloud. No workload/destructive
testing in the Organizations Management Account.

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
