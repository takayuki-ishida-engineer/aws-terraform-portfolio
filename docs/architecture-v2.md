# Architecture v2 — approved target and implementation status

See the [approved functional-module repository strategy](repository-structure-strategy.md): R0 → R1 → R2 → R3 → R4 migration/revalidation precedes new v2 features; coherent modules own coupled functionality rather than individual-resource wrappers.

See the [Network / State / Identity foundation design](architecture-v2-foundation-design.md) for proposed implementation ownership and staged PR boundaries.

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

## V7-0 technical contract — implementation not started

See the [REST/private integration feasibility contract](v7-rest-private-integration-feasibility.md)
for pinned Provider6.72.0/AWS specification findings and staged V7-A/B/C/D gates.
The NLB-versus-listener integration target wording is P0 OPEN, as are backend
server trust/SNI, ACM client-certificate verification and approved minimal output
handoff. This does not change Regional REST/Cognito/VPC Link V2/internal NLB TCP443/
Istio MUTUAL/STRICT architecture or resource/State writers. Only the historical
single-VPC lifecycle has direct emulator proof; no REST/mTLS runtime PASS is claimed.

See the [NP-2A NetworkPolicy flow/port compatibility design](np2-network-policy-flow-contract.md)
for CNI prerequisites and approval-dependent port alternatives. Existing TCP443,
TLS/identity, resource ownership and NP-1 implementation remain unchanged.

## Authority, evidence and status

Current operating requirements are the owner-authorized **Master Policy v14.2**
[alignment record](policy-v14-2-alignment.md): mandatory Core offline quality,
separate portfolio-level representative Emulator demonstration, optional external
Live and unchanged architecture/security controls. The v14.2 PDF/full text/hash
is unavailable; no original-PDF verification or unprovided clause is claimed.
The earlier complete v14 text and v14.1 34-page extraction were user-supplied;
their original PDFs were not independently verified. See the current
[verification policy](portfolio-verification-policy.md).
Earlier policy versions are historical implementation/design provenance only.
The design below retains its recorded v10 (2026-11-08) provenance and approved
clarifications/subsequent repository decisions. R3 infers no undocumented v11
contents or blanket v10/v11 equivalence and changes no approved architecture.
Repository source and exact-revision CI establish implemented behavior, not Live
permission. Any policy detail not established by accessible approved records
requires clarification before its implementation.
AWS Terraform is the primary portfolio; CloudFormation and Azure Terraform are
separate, smaller supporting portfolios, not implementations claimed here.

Historical post-R2 HTTP API source at main `df5ef4b2e03bd55109b0490b1e63d1d4199b663b` has eight
reusable modules, four DEV instances, 17 resource definitions, eight root outputs
and five source-level moved declarations. Lambda workload owns four resources;
HTTP API owns six including its access log. Generic logging remains independently
tested without a DEV consumer; that application root does not call VPC and Lambda remains outside a VPC.
[Post-R2 CI 42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148) passed 491 native/153 Python tests.

The nine-module/seven-instance layout and 384/153 acceptance describe the pre-R1
historical MVP, preserved in [technical history](../infra/README.md) and the
[acceptance audit](offline-mvp-acceptance.md). Historical main
`9a17e54b5842e05633c730510a2d46eda4f1e18a` passed
[baseline CI 42546954252](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42546954252).
Neither historical nor current HTTP API evidence proves REST/NLB/Istio/mTLS,
deployed AWS behavior or actual state migration. The target below remains
a deployment target; the R3/R4 chronology below is historical, not V3 evidence.

## Historical V2 baseline and V3 platform candidate

The approved V3 entry is post-V2 main
`da1af5c4eed15f5c9145799409d53c1db7508c94`, matching successful
[push CI 42688811654](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42688811654)
(560 native / 153 Python, 10 initialized configurations). The coherent VPC module
and separate [DEV Network Root](../infra/services/dev/ca-central-1/network/README.md)
now implement opt-in per-AZ routes, zonal NAT/EIP and reviewed optional S3 Gateway
Endpoint; legacy private-only defaults and the HTTP API MVP remain independent.

V3 adds the candidate [eks_platform child](../infra/modules/eks_platform/README.md)
and [DEV Platform Root](../infra/services/dev/ca-central-1/platform/README.md):
private-only IPv4 API, multi-AZ control-plane subnets, one explicitly selected
DEV worker AZ, EC2 Managed Nodes, separate Cluster/Node/CNI roles, explicit access
entries and three managed add-ons. The typed minimal network reference validates
scope/relationships but does not prove AWS existence or publish/read whole state.
Publication/integrity/consumer access and actual state ownership remain OPEN.

Local V3 evidence is 52 child / 29 Root native passes plus independent actual-plan,
IAM/SG/access, negative and mutation checks documented in those READMEs. Complete
PR CI is required independently; expected coverage is 641 native / 153 Python and
12 initialized configurations, not a claim that V3 CI already passed. There are now
nine children and three DEV roots; serverless-api still has its original four
calls/17 resources/eight outputs/five moves. No runtime mesh, ingress, application,
autoscaler, STG/PROD platform or AWS deployment is implemented. Actual AWS-managed
Cluster SG residual rules, namespace Edit/Pod identity boundaries, connectivity,
versions/capacity/cost and safe teardown require external review. G01–G07, Live
limits and the Secrets Manager recovery blocker remain OPEN.

## V4 private ingress source candidate

Accepted post-V3 main `6b185820c806a0c96410a145106b9f103db14d89` has successful
[push CI42720431920](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42720431920)
(641 native/153 Python, 12 configurations). V4 adds the coherent
[private_ingress child](../infra/modules/private_ingress/README.md) directly to
[DEV Platform](../infra/services/dev/ca-central-1/platform/README.md) in the same
State: internal IPv4 NLB, TCP443 → required IP target port, dedicated NLB/client
SGs and six scoped target/client/webhook rules. No existing resource changes owner.
DEV selects one private subnet in the active worker AZ, cross-zone=false; no HA
claim. Static source has no registered Pod targets or controller deployment.

VPC Link client SG is Platform-owned for future API ENI attachment, preventing
reverse Root dependencies. Later runtime owns restricted TargetGroupBinding and
registration, not NLB creation, TG attributes or SG rule reconciliation. AWS-
managed Cluster SG residual exposure, Pod SG assumptions, webhook/API/data paths,
controller IAM/RBAC and trusted minimal output publication remain OPEN. TCP health
is not TLS/mTLS or application authorization; Gateway TLS/client verification and
API server-chain/hostname/SNI compatibility are future work, with no insecure fallback.

V4 local native counts are Child28/Root38; expected full CI678/153 and13 initialized
configurations requires independent exact-HEAD review, not assumed success. All
G01–G07/cost/72-hour teardown/Secrets recovery limits persist. The V2/V3 counts
above remain historical implementation evidence, not current V4 totals.

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

## Approved target topology

```mermaid
flowchart TD
  Browser[Browser: standard HTTPS, no user client certificate] --> Edge[CloudFront + Edge WAF]
  Browser -. authorization code + PKCE S256 / OIDC .-> Cognito[Cognito User Pool + Google Federation]
  Edge -->|Origin mTLS| API[Regional REST API custom domain + mTLS truststore]
  Cognito -. access token / method OAuth scopes .-> API
  API --- RWAF[Regional WAF]
  API --> AppLambda[Lambda application integration]
  API --> Link[REST VPC Link V2]
  Link --> NLB[Internal NLB: TCP 443 passthrough]
  NLB --> Gateway[Istio Ingress Gateway: backend mTLS verification]
  Gateway --> Mesh[Istio mesh: STRICT mTLS / SPIFFE / AuthorizationPolicy]
  Mesh --> EKS[EKS application workloads]
  EKS -->|PostgreSQL TLS + approved DB authentication| DB[RDS / Aurora PostgreSQL]
```

NLB replaces the previous proposed ALB ingress. Historical ALB discussion is not
the current approved target. No TLS terminates or authenticates a certificate at
the TCP NLB; Gateway terminates backend TLS. The diagram states intended boundaries,
not proven provider capability, connectivity or issuance.

## Transport, identity and authorization contracts

| Boundary | Approved target | OPEN implementation/evidence obligations |
| --- | --- | --- |
| Browser → CloudFront / Cognito | Standard HTTPS server authentication; ordinary users need no client certificates; Authorization Code + PKCE S256 / OIDC; environment-specific User Pools and Google federation | Exact callbacks/logout URLs, clients/scopes, claims, expiry/session/replay controls; distinguish browser PKCE from upstream Google federation |
| Viewer and login domains | AWS-provided *.cloudfront.net viewer domain permitted; keep Cognito AWS-managed login domain, no Cognito custom domain | No purchased viewer domain required; environment-specific callbacks must match actual endpoints |
| CloudFront → Regional REST API | Mandatory origin mTLS; ACM client certificate stored in us-east-1; publicly trusted API origin server certificate; ca-central-1 Regional custom domain with S3-versioned truststore | ClientAuth EKU/issuance, minimal trust, certificate identity/rotation, origin configuration, DNS compatibility and pricing feasibility; disable/prevent default execute-api endpoint bypass and review stage deployment behavior |
| REST API → Istio Gateway | Approved backend client certificate; ACM-backed REST stage certificate preferred subject to provider/private-integration verification; API verifies Gateway server chain and expected server name | Suitable client-auth certificate, backend trust/SNI/hostname mapping, rotation/expiry and endpoint validation; no insecureSkipVerification, unrestricted trust or plaintext fallback |
| VPC Link V2 → internal NLB → Gateway | Private integration; NLB TCP:443 passthrough; Gateway presents server certificate and verifies backend client certificate | Provider/link/NLB compatibility, subnet/SG rules, target mode, health checks and end-to-end TLS identity evidence |
| Controlled workload → workload | Istio STRICT mTLS, SPIFFE identities, short-lived workload certs, AuthorizationPolicy, restrictive RBAC/NetworkPolicy and appropriate default deny | Istio CA is initial candidate only; roots/intermediates, renewal/rotation/expiry, revocation-equivalent controls, ServiceAccount rights and principal boundaries require review |
| EKS → RDS/Aurora | PostgreSQL server TLS with CA and hostname verification; IAM DB auth or another explicitly approved scheme | Actual DB auth/credentials, trust, connections, failover/reconnection, backups/PITR and schema recovery |
| EKS/Lambda → AWS-managed APIs | Standard validated TLS with appropriate IAM/SigV4 | Scoped workload identity/permissions and actual service access; no custom certificate mTLS imposed |

Do not impose custom client-certificate mTLS on browser users, RDS standard
interfaces, local same-Pod communication or managed control planes. Transport
encryption, server authentication, client authentication, user authentication and
application authorization are separate. Encryption alone is not authenticated mTLS.

### API inbound certificate identity and revocation — OPEN

[API Gateway inbound mTLS documentation](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-mutual-tls.html)
describes supported certificate/chain/validity checks, but **API Gateway does not
automatically check certificate revocation status**. Trusting a CA does not restrict
access to the one expected CloudFront origin client certificate: other certificates
issued under that trust may validate. TLS handshake validation, certificate identity
authorization, revocation handling and Cognito user authorization must stay separate.

Before implementation, review the minimum necessary CA trust/issuance boundaries,
how the expected certificate is distinguished from other trusted-CA clients,
unauthorized-certificate denial, compromise response, rotation, expiry monitoring
and revocation-equivalent controls. Define any additional authorization mechanism's
owner, evidence, failure/availability behavior and coexistence with the approved
Cognito/scopes model. Do not assume a Lambda Authorizer alongside a Cognito User Pool Authorizer
can run on the same REST method. Although AWS describes Lambda authorizers as a
possible place for certificate checks, that is not approval or proof of compatibility
with this method model. No mechanism is selected; feasibility/security/operations
remain OPEN for its implementation PR. Short lifetimes or rotation alone must not
be advertised as an already implemented revocation control.

Protected methods use Cognito User Pool Authorizers with explicit OAuth scopes and
access tokens; ID tokens do not substitute for scoped API authorization. Backends
independently enforce user/tenant ownership, with wrong-owner and cross-tenant
negative cases. Regional WAF and edge WAF have separate scopes. The default
execute-api endpoint must not bypass custom-domain mTLS; disabling/redeployment,
custom domain mappings and direct-origin adversarial tests remain implementation
contracts. An obscured hostname or trusted CA alone is not origin protection.

### DNS, certificates and secrets — OPEN feasibility gates

API Gateway inbound mTLS requires a Regional custom domain. Prefer a suitable free
subdomain only after DNS control, validation, renewability, terms and technical
suitability are verified. No FQDN/provider is chosen; Route 53 need not own every
record. No domains/certificates are purchased or created here. If free-domain or
certificate feasibility fails, stop the relevant PR and obtain revised approval;
do not weaken TLS. Root-owned regional/global certificate/state boundaries remain
explicit; do not configure providers in children.

[CloudFront client-certificate requirements](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/origin-certificate-management-certificate-manager.html)
require clientAuth EKU and import into ACM us-east-1; issuance/renewal is not assumed
automatic. [API Gateway ACM backend certificates](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-acm-client-certificates.html)
require a suitable imported/private client-auth certificate in the API Region;
ordinary ACM public certificates must not be assumed usable. Actual provider and
VPC Link V2 integration support, truststore ownership and PKI are OPEN; no command
or certificate material is supplied here.

Google OAuth client secrets, DB credentials, keys and all actual secret values stay
outside Terraform inputs/data sources/plans/state/outputs, CI logs and repository
artifacts. Terraform manages Secrets Manager metadata only; approved external
processes own values/rotation. Sensitive marking or loading secrets through Terraform
does not prevent persistence. Secret-safe federation configuration and drift ownership
remain OPEN; no secret provisioning or ephemeral/write-only workaround is implemented.

## Infrastructure ownership and environment contract

Terraform owns VPC Link, internal NLB/listeners/target groups and network/subnet/
security resources. Kubernetes-side control owns Gateway Pod target registration.
TargetGroupBinding, controller permissions, Pod IP target mode, health checks and
NLB compatibility are OPEN. No independent Terraform/controller ownership of the
same load balancer is permitted. HPA owns replica scaling and Cluster Autoscaler
owns managed-node scaling under bounded policies; no concurrent Karpenter ownership.

| Property | DEV | STG / PROD |
| --- | --- | --- |
| Active application workload AZs | One to minimize cost; updates/worker failure downtime may be accepted | Two; separate Managed Node Group capacity per active AZ |
| Configured AZ subnets | Additional subnets wherever EKS, NLB, DB subnet groups or service constraints require them | Service-compliant subnets and IP headroom; configured AZ coverage is not workload capacity |
| NAT / egress | One NAT; private workloads; cost-reviewed endpoint selection | One NAT per active AZ (two); stronger private exposure and egress restrictions |
| Initial EC2-backed EKS capacity | One minimal worker only if Istiod, Gateway, sidecars, system pods, monitoring and application safely fit; increase if demonstrably insufficient | Redundant Istiod/Gateway/apps; adequate remaining-AZ capacity for defined peak after AZ loss, including CPU, memory, Pods, IPs and DB connections |
| Scaling / placement | Carefully bounded HPA + Cluster Autoscaler | HPA + Cluster Autoscaler, topology spread, PDBs, readiness and safe update headroom |
| Replica/node counts | One app replica initially if safe; resource sizing remains cost/capacity review | Two workers/replicas per AZ are candidates only, not fixed approved counts or resilience proof |
| Database | Single-AZ RDS PostgreSQL, validated TLS, backup and reviewed auth | Aurora PostgreSQL Provisioned writer/reader across AZs; failover/reconnection, backup/PITR, recovery and schema migration contracts |
| Observability | Limited CloudWatch/Fluent Bit/Datadog collection with retention/redaction/cost bounds | Strengthened monitoring/audit/retention and secret redaction |
| State/provider | Root-owned account restriction and local DEV state | Separate env/Region/service roots; separately reviewed remote state; providers root-owned |
| Portfolio evidence | Offline plus only feasible separately authorized limited DEV Live scenarios | Credential-free offline implementation verification only; no authenticated plan/apply or live tests required |

EKS cluster subnet coverage and DB subnet groups require multiple AZs even when
DEV application/database activity is Single-AZ; NLB subnet/target design must be
reviewed for its actual capabilities, not inherited ALB assumptions. No old ALB
/27 or two-subnet rule is used as a target acceptance criterion. Actual subnet,
node, controller, engine and service quotas remain OPEN. Two nodes/replicas alone
do not prove availability, safe updates or recovery. No measured SLA/RTO/RPO,
cross-region DR, cold standby or long-running production operations are in scope.
Older monthly environment budget examples are neither hard limits nor sizing approvals.

## Delivery, operations and shared notifications

- ECR releases pin immutable image digests and reviewed source/build provenance.
  GitHub Actions OIDC trust constrains audience/subject and repository/environment.
  CodeBuild deploys to private EKS using scoped IAM/RBAC and reviewed DNS/network
  connectivity; Helm/equivalent owns app releases, Terraform owns infrastructure.
- Lambda versions/aliases and code delivery need explicit single ownership between
  Terraform and release pipelines; the current publish=false MVP is not that flow.
  Review artifact digest, S3 version, provenance and ownership before bootstrap.
  User-provided dummy.zip is only a candidate, not an approved artifact. Never
  reuse/import/copy code or private information from the legacy customer-project ZIP.
- Verify release health and rollback to the known digest/version/alias. Database
  schema/connection recovery, infrastructure recovery and application rollback are
  distinct. Build/deploy/rollback successes and failures need correlated events;
  GitHub events do not automatically become EventBridge events.
- EventBridge routes defined events to notification Lambda; at least one destination
  is eventually verified within approved feasible DEV scope. Handle notification
  delivery failures independently through reviewed retry/redrive/alerting ownership.
  Telemetry includes CloudWatch, Fluent Bit and Datadog with scoped IAM, redaction,
  egress, retention and cost controls; no destination/key is invented here.
- Packer/Ansible own reviewed image/configuration provenance. The DEV RDS SSM
  developer-access EC2 is for local workstation → Session Manager port forwarding
  → private EC2 → private RDS PostgreSQL, not generic administration or a management
  jump server. Intended module rds_ssm_access and initial dev/ca-central-1/db-access
  root are future only; do not replicate into STG/PROD automatically. No broad admin
  or public SSH/RDP; developer identity, least-privilege SSM, endpoint/NAT connectivity
  and DB SG permissions require review. Port-forwarding session logs must not be
  assumed to capture SQL traffic.

### DEV RDS developer-access EC2 schedule and failure handling

```text
Timezone: America/Toronto
START: cron(0 8 ? * MON-FRI *)
STOP:  cron(0 19 ? * MON-FRI *)
```

Weekends remain stopped, with no special holiday calendar. Timezone-aware scheduling
handles daylight saving changes. Target flow: **EventBridge Scheduler → SQS Command
Queue → Controller Lambda → EC2 Start/Stop**. A separate Watchdog Lambda checks
expected versus actual state according to the local schedule.

Use CloudWatch detection and SNS notification for Scheduler delivery failures or
missing heartbeat, SQS retries/DLQ accumulation/stale commands, Controller errors/
timeouts/idempotency, EC2 API failures, failure to reach running/SSM-ready or stopped,
unexpected running outside schedule, and Watchdog/notification failures. Detect
both failure and non-execution of START and STOP. Thresholds, redrive counts,
permissions and precise recovery actions are OPEN; no implementation is selected.
This schedule is independent of the absolute DEV Live 72-hour complete-teardown
limit. Stopping EC2 does not stop EKS, NLB, NAT, RDS or other service billing.

## DEV Live feasibility and spending boundary

The limited Live policy is approved; specific execution, accounts, certificates,
scenarios and approvals are not. No AWS operations are authorized here. Actual
cumulative spending across the approved DEV validation period must stay within
**JPY 10,000**, and all testing plus independently verified complete teardown must
finish within **72 hours from approved live start**. A shorter run is preferable.

CloudFront Origin mTLS is supported on **Business, Premium and Pay-as-you-go**, not
Free; plan/feature availability is a mandatory pre-implementation/Live feasibility
gate. Review [plan feature availability](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/flat-rate-pricing-plan.html),
actual applicable fixed/usage charges, certificate issuance/renewal and all other
service costs. No plan is selected or purchased. Estimate Region/runtime, tax,
currency conversion, retained charges, contingency and teardown implications.
A 72-hour window does not guarantee affordability. If a validated estimate cannot
fit the cap, do not authorize that scenario: leave it OPEN or Offline-only.
Budgets/alerts are not real-time enforcement or guaranteed billing cutoff; use
monitoring, resource inventory, manual stop authority and a reviewed timeline.

Prioritize feasible creation/resource inventory, positive/negative Istio STRICT
mTLS, then REST VPC Link V2/NLB/Gateway backend certificate authentication. Delivery,
rollback and notifications run only in remaining approved scope/budget. Do not
mandate full simultaneous CloudFront/Cognito/RDS/delivery integration if infeasible.
Unexecuted scenarios never pass. All seven readiness gates remain OPEN; see the
[Live readiness assessment](dev-live-validation-readiness.md) and
[verification policy](portfolio-verification-policy.md) for complete deletion criteria.

## Migration register — approved target, implementation OPEN

| Existing offline baseline / earlier design | Required migration | Preserve / independently verify |
| --- | --- | --- |
| HTTP API AWS_IAM | New REST/Cognito scopes, two mTLS boundaries, WAF and custom domain | Keep HTTP API module/tests; new trust/identity/revocation/bypass and user/tenant authorization evidence |
| Earlier proposed ALB ingress | Internal NLB TCP:443 → Istio Gateway → STRICT mesh | New VPC Link/provider/target ownership, TLS/SNI, SPIFFE and PKI verification; no ALB substitution |
| S3-versioned ZIP, publish=false | Reviewed bootstrap then single-owned code/version/alias release flow | Keep artifact/execution security contracts and exact version requirement until approved migration; dummy.zip not approved |
| Independent VPC; no workload mesh/database | New environment network/EKS/mesh and RDS/Aurora | New scoped modules and offline security/capacity/recovery contracts; no historical test count implies coverage |
| Offline-only CI | OIDC/ECR/private CodeBuild, notifications, EC2 Scheduler/SQS/Controller/Watchdog/SNS | Keep complete offline suite; separately scoped delivery/developer-access roles and failure evidence |
| DEV local state, root account guard; STG/PROD placeholders | Env/Region/service state/provider boundaries and reviewed STG/PROD remote state | Exclusive resource ownership and migration; no backend change here |
| Metadata/log/IAM modules and accepted 17-resource MVP | Reuse only compatible parts after review | Keep all history/tests; 17 is not v2's resource inventory or a cost/teardown guarantee |

Implementation blockers remain OPEN: provider/integration support; PKI/issuance
and identity/revocation feasibility compatible with Cognito; free DNS and truststore
ownership; TargetGroupBinding/permissions; sizing; state/IAM; artifact provenance;
monitoring thresholds; plan pricing and full deletion within 72 hours. The current
secret module's 30-day recovery is incompatible with actual complete deletion in
72 hours if that unchanged resource is created for Live. Do not execute the full
historical root unchanged under the new limit; an approved feasible scenario/lifecycle
design is needed first, without silently weakening existing guards. Avoid new CMKs
or other unavoidable deletion delays. Prior [bootstrap proposals](dev-bootstrap-decision-plan.md)
remain historical decision inputs, not authorization or current ingress overrides.
