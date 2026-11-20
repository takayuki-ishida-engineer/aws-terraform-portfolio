# AWS Terraform and Kubernetes Portfolio

## Step 2 emulator rehearsal — network root PASS in GitHub Actions

[![AWS Emulator Step 2 rehearsal](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/workflows/aws-emulator-rehearsal.yml/badge.svg?branch=main&event=push)](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/workflows/aws-emulator-rehearsal.yml?query=branch%3Amain+event%3Apush)

The badge shows only the latest automatic run. Automatic runs cover only the
reviewed scenarios of an Owner merge-approved pull request (Master Policy v14.4
§13.2); `all` is not every DEV root. GitHub keeps run logs and job summaries for
at most 90 days. The badge, run URLs and job summaries are therefore not permanent
evidence. The durable record is the [Step 2 record](docs/step2-emulator-rehearsals.md),
and from the next pull request it is the sanitized evidence ledger
`docs/evidence/emulator-runs/`, with one entry per run and attempt.

| Item | Value |
| --- | --- |
| What | The real DEV network root (`vpc` module, committed values without interface endpoints, 16 resources) through Plan, Create, Read, Update, No-op and Destroy in the official AWS Emulator, under all fourteen isolation controls |
| CI runs | [44279751946](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44279751946) (Owner-dispatched, 2026-11-18, tested SHA `0a16e486`) and [44664010985](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44664010985) (automatic on main, 2026-11-20, tested SHA `70a58682`), `aws-emulator-rehearsal.yml`. The earlier dispatch 44279371023 stopped BLOCKED at the billing gate before checkout and created nothing |
| Result | **PASS**: all 14 controls, all 13 lifecycle operations, independent API checks and cleanup |
| Record | [Step 2 emulator rehearsals](docs/step2-emulator-rehearsals.md): every formal run, status per root, versions, harness hash, the emulator gaps, untested items and residual risk |
| Other roots | api NOT_TESTED in Actions (local preliminary only); network with interface endpoints and tfstate EMULATOR_COMPATIBILITY_BLOCKED; serverless-api, platform and developer-access NOT_TESTED |

Measured in the emulator only; not evidence of real AWS behavior. Acceptance needs
independent review and an Owner decision.

## Representative Emulator workflow — AWS EMULATOR DEMONSTRATED for the VPC scenario

[Phase 3 implementation](scripts/emulator-verification/README.md) supplies an owner-confirmed, merged-main-only manual
workflow, isolated single-VPC adapter and offline security contracts. Existing
required Full CI is unchanged; a separate static-only check exercises the new
contracts without Docker, Emulator or resource operations. Owner-dispatched
[Run 43791639228](docs/portfolio-verification-policy.md#representative-emulator-run-43791639228) on merged main
`5c62dba517c7eb97394f77aaff6479a1315c524e` measured all fourteen controls, the
disposable `aws_vpc.proof` Create/Read/Update/No-op/Destroy lifecycle, independent
API checks and cleanup as PASS. After independent AI evidence review (PASS) and
Owner acceptance on 2026-11-16, AWS EMULATOR DEMONSTRATED is declared for that
representative VPC lifecycle scenario only. Other representative scenarios remain
NOT_TESTED; CORE PORTFOLIO COMPLETE and PORTFOLIO COMPLETE are not declared.
Codex namespace remains known environment BLOCKED.


## V7-A source update — runtime not demonstrated

V7-A adds [api_gateway_rest](infra/modules/api_gateway_rest/README.md) and composes Regional REST core plus Cognito
Authorizer with the actual existing authentication contract in the DEV API Root.
The source now has 12 Child Modules and four DEV Roots. Exactly two REST resources
are added; five Cognito resources/authentication remain.
REGIONAL and disable_execute_api_endpoint=true are fixed. No Method, path,
Integration, Deployment/Stage, VPC Link, Backend or Custom Domain is included.
Emulator Lifecycle NOT_TESTED; namespace isolation environment BLOCKED. No real
API invocation, Cognito enforcement or TLS communication is claimed. P0-01–04,
P1-02 and Runtime NP-2B/NP-3 remain OPEN. Earlier implementation-status statements
below are historical snapshots; their evidence is not a new V7-A test result.


An AWS-first infrastructure and platform engineering portfolio built with reusable
Terraform modules, Kubernetes runtime configuration, Python security validators and
GitHub Actions. The focus is private infrastructure, least-privilege identity,
clear resource ownership and reproducible verification.

**Verified implementation baseline (before this documentation change):** main
[`be79be6`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/commit/be79be6a64a6ef2e78f76e920afb335c59bbd49d),
[successful credential-free CI run 43347607972](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43347607972):
**781 Terraform Native tests, 153 Python toolkit tests**, and Kubernetes checks
covering **8 pinned Helm renders across 2 configurations**. The repository contains
**11 reusable Terraform modules and 4 DEV Root configurations**.

**Maturity:** implemented source and offline verification. No live AWS/EKS deployment,
Kubernetes packet-enforcement result or end-to-end mTLS handshake is claimed.

## Implementation status

| Area | Current status |
| --- | --- |
| AWS infrastructure | Terraform source for DEV networking, private EKS, internal NLB, controller IAM, Cognito and an independent serverless HTTP API |
| Kubernetes runtime | Pinned controller/Istio rendering, guarded TargetGroupBinding, Gateway TLS configuration and application-namespace default-deny policies |
| NetworkPolicy work | NP-1 default-deny and NP-2P Gateway backend-port alignment implemented; NP-2B allow policies and NP-3 CNI enablement remain unimplemented |
| Architecture v2 integration | V7-A REST core and Cognito Authorizer source; Methods, VPC Link integration, CloudFront, database, delivery and application/backend remain future work |

## Technical stack

| Layer | Technologies and controls present in source |
| --- | --- |
| Infrastructure | AWS, Terraform 1.17.0, locked AWS Provider 6.72.0; VPC, EKS EC2 Managed Node Groups, NLB, Cognito, Lambda, HTTP API, IAM, S3 and Secrets Manager metadata |
| Kubernetes runtime | Helm 3.22.1, AWS Load Balancer Controller 3.6.2, Istio 1.32.0 sidecar-mode configuration, TargetGroupBinding and Kubernetes security policies |
| Verification | Python 3, Terraform Native mock plans, independent plan/render validators, negative and mutation tests, pinned schema validation and credential-free GitHub Actions |
| Security | Scoped IAM/IRSA, account guards, restricted Pod Security, RBAC, fail-closed admission, Gateway MUTUAL TLS, mesh STRICT mTLS and default-deny NetworkPolicy declarations |

Pins and package hashes are recorded in the
[runtime dependency lock](kubernetes/dependencies.lock.json) and committed Terraform
provider locks. Test fixtures do not approve a live Kubernetes version or capacity.

## Architecture

The approved **Architecture v2 target** places CloudFront and Edge WAF ahead of a
Regional REST API custom domain with inbound mTLS and Regional WAF. Cognito method
scopes protect API access; private integration uses REST VPC Link V2 and an internal
NLB with TCP:443 passthrough to Istio Gateway. Backend client-certificate verification,
STRICT mesh mTLS, workload authorization and PostgreSQL TLS have separate trust
and ownership contracts. This complete path is not implemented or deployed.

The existing `serverless-api/` HTTP API remains independent of the future REST
`api/` Root. DEV Roots own provider/account restrictions and local State, separated
by environment, Region and service. Reusable children own resources; Kubernetes
runtime owns dynamic Pod registration. No whole-State consumer is introduced.

See the [architecture and implementation record](docs/architecture-v2.md),
[Network / State / Identity foundation](docs/architecture-v2-foundation-design.md),
[REST/private integration contract](docs/v7-rest-private-integration-feasibility.md)
and [NetworkPolicy flow contract](docs/np2-network-policy-flow-contract.md).

## Implemented components

These are source implementations with offline evidence, not deployed services.
The eleven reusable children are grouped below by responsibility.

| Capability | Child modules and source ownership |
| --- | --- |
| Network | [vpc](infra/modules/vpc/README.md): legacy private-only defaults, opt-in per-AZ routing, NAT/EIP and scoped optional S3 Gateway Endpoint |
| EKS platform | [eks_platform](infra/modules/eks_platform/README.md): private cluster API, multi-AZ cluster subnets, EC2 Managed Nodes, dedicated IAM/SGs, access entries and managed add-ons |
| Private ingress | [private_ingress](infra/modules/private_ingress/README.md): internal NLB, TCP listener, IP target group, static SG rules and target-registration-only controller IAM |
| Authentication | [cognito_auth](infra/modules/cognito_auth/README.md): protected email User Pool, public code-only client, Resource Server/scopes, prefix domain and managed-login branding |
| Serverless API | [lambda_workload](infra/modules/lambda_workload/README.md) and [api_gateway_http](infra/modules/api_gateway_http/README.md): Lambda/execution IAM/application logs and AWS_IAM HTTP API/access logs |
| Storage and metadata | [s3_artifact_bucket](infra/modules/s3_artifact_bucket/README.md), [secrets_manager](infra/modules/secrets_manager/README.md) and [cloudwatch_logs](infra/modules/cloudwatch_logs/README.md): private versioned artifacts, metadata-only secrets and reusable logging |
| Administrative IAM | [iam_access](infra/modules/iam_access/README.md) and [iam_account_policies](infra/modules/iam_account_policies/README.md): separately scoped Identity Center access and workload-account policies |

The four DEV Roots are [network](infra/services/dev/ca-central-1/network/README.md),
[platform](infra/services/dev/ca-central-1/platform/README.md),
[api](infra/services/dev/ca-central-1/api/README.md) and
[serverless-api](infra/services/dev/ca-central-1/serverless-api/README.md), all under
`dev/ca-central-1/`. The API Root currently composes Cognito only.

The [Kubernetes runtime](kubernetes/README.md) supplies controller and Istio chart
configuration, a ClusterIP Gateway Service, restricted TargetGroupBinding,
external certificate/CA references, admission guards and namespace security.
NP-2P derives Service, Pod, binding, Gateway and admission backend ports from one
reviewed input while preserving the NLB TCP:443 listener.

## Security engineering

- **Identity:** dedicated roles, exact OIDC audience/subject trust and scoped
  registration permissions. Controller IAM excludes load-balancer creation,
  target-group modification and security-group writes.
- **Ownership and secrets:** Terraform owns static AWS resources; the controller
  owns dynamic target registration. Terraform manages Secrets Manager metadata,
  never secret values, private keys or Google OAuth secrets.
- **Runtime authorization:** restricted Pod Security, scoped RBAC and fail-closed
  admission guards constrain runtime objects. `portfolio-app` has both-direction
  default-deny NetworkPolicy, STRICT PeerAuthentication and a default-deny
  Istio AuthorizationPolicy. Their live enforcement has not been demonstrated.
- **Transport:** the NLB passes TCP through to a Gateway configured for MUTUAL TLS,
  TLS 1.2 or newer and expected-client SPKI verification. Certificate custody,
  rotation, revocation response and REST backend compatibility remain open.

## Validation and CI

At main **`be79be6a64a6ef2e78f76e920afb335c59bbd49d`**,
[Terraform offline CI run 43347607972](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43347607972)
was a **completed/success push run, attempt 1**, with every job step successful.
The following dated snapshot was checked against its actual logs; every Full CI run
reports the current totals in its job summary ("Summarize actual validation results").
CI runs never cancel each other: one run per workflow at a time, and each push or
merge waits until the previous run has finished successfully:

| Verification layer | Observed result |
| --- | --- |
| Terraform Native mock tests | 781 passing across affected Roots and reusable children |
| Python policy-validation toolkit | 153 passing tests; export and offline dry-run steps successful |
| Provider storage | 15 initialized configurations sharing one locked AWS 6.72.0 provider binary |
| Kubernetes positives | 2 configurations, 8 pinned Helm renders, 62 resources per configuration and 124 schema-checked objects |
| Kubernetes security/evidence rejection | 97 rendered mutations, 38 invalid inputs and 26 evidence faults rejected |

Kubernetes counts are separate from Terraform Native and Python toolkit totals.
Independent validators inspect actual mock-plan JSON and Helm-rendered resources;
negative, mutation and malformed-evidence checks exercise unsafe variants. See the
[workflow](.github/workflows/terraform-offline-ci.yml),
[runtime test contract](kubernetes/tests/README.md) and
[verification policy](docs/portfolio-verification-policy.md).

AWS Emulator lifecycle demonstration is required for representative portfolio
scenarios, separately from Core Implementation's mandatory offline quality gates.
It is not a blanket per-resource PR prerequisite or a current required CI stage.
A future optional workflow needs separate approval and its own merged PR before
execution; all fourteen safety controls remain mandatory. The historical proof covers a disposable single
`aws_vpc.proof` lifecycle only; it does not validate the complete VPC module or
other AWS services. CI success does not establish real IAM enforcement, network
reachability, controller registration or TLS/mTLS communication.

## Repository navigation

| Review goal | Entry points |
| --- | --- |
| Terraform design and resource contracts | [Modules](infra/modules/), [DEV Roots](infra/services/dev/ca-central-1/), [infrastructure guide](infra/README.md) |
| Runtime source and rendering | [Kubernetes guide](kubernetes/README.md), [renderer](kubernetes/tools/render.py), [independent validator](kubernetes/tools/validate.py) |
| Security and evidence checks | [Runtime checker](kubernetes/tests/check_runtime.py), [IAM reference checks](infra/modules/iam_access/tests/), [offline policy toolkit](scripts/aws-policy-validation/README.md) |
| Design decisions and outstanding gates | [Architecture v2](docs/architecture-v2.md), [repository strategy](docs/repository-structure-strategy.md), [REST contract](docs/v7-rest-private-integration-feasibility.md), [NetworkPolicy contract](docs/np2-network-policy-flow-contract.md) |
| Governance and historical acceptance | [AGENTS](AGENTS.md), [verification policy](docs/portfolio-verification-policy.md), [original MVP acceptance](docs/offline-mvp-acceptance.md), [Live readiness](docs/dev-live-validation-readiness.md), [bootstrap decisions](docs/dev-bootstrap-decision-plan.md) |

## Limitations and open decisions

- No live AWS/EKS deployment, Kubernetes packet enforcement, controller registration
  or end-to-end mTLS handshake is claimed. VPC CNI NetworkPolicy enablement and
  strict enforcement remain unimplemented and unverified.
- NP-2P resolves Gateway port consistency in source. **P0-WEBHOOK** port translation
  and **P0-CNI** version/bootstrap compatibility remain OPEN before NP-3; NP-2B
  communication allow policies are not implemented.
- V7-A REST core source is implemented; integration/runtime are not. **P0-01–P0-04** retain unresolved
  integration-target ARN, backend server trust/SNI, client-certificate lifecycle
  and trusted minimal output-handoff decisions. CloudFront, database, delivery and
  application/backend architecture are incomplete; no application workload or
  tenant/owner authorization is demonstrated.
- Cognito Google federation, browser PKCE/state/nonce behavior and real login are
  external or future work. Source configuration does not prove authentication.
- Actual account, State custody, output authenticity, capacity, certificates,
  callback domains, pricing and teardown require separate review and approval.

The owner-authorized **MASTER POLICY v14.4** (2026-11-20) is the current master.
It builds on v14.2, adding the limited automatic Step 2 rehearsal and the evidence
ledger for every formal Emulator run. Both are recorded in the
[policy alignment record](docs/policy-v14-2-alignment.md). Mandatory offline quality,
Full CI on every PR, independent review/user approval and separate representative
Emulator demonstration are retained; Core Portfolio Complete is a separate scope
assessment without an Emulator prerequisite; PORTFOLIO COMPLETE requires both
Core completion and representative Emulator demonstration. Neither is claimed here.
The supplied v14.2 text was reviewed in full (43 pages, including A–T); the PDF
binary and its hash were not independently verified. Earlier policy labels in historical
documents are not current authority; the
[architecture authority record](docs/architecture-v2.md#authority-evidence-and-status)
records the available policy provenance and limits.
Real AWS deployment is optional for portfolio completion and prohibited in Codex
Cloud. Optional external DEV Live work requires separate approval through all
**G01–G07** gates, at most **JPY 10,000** cumulative actual spending and verified
complete removal within **72 hours**. All gates remain OPEN, including the
unresolved Secrets Manager 30-day recovery-window conflict.

Older v14/v14.1 references below are historical snapshots; current requirements
are the owner-authorized alignment record (v14.4, built on v14.2).

## Detailed engineering history

The sections below preserve phase-specific implementation and acceptance evidence,
including their original commits, counts and expected-CI wording. They are historical
snapshots; use the verified main baseline above for current counts and maturity.

<a id="current-operating-and-completion-policy"></a>

### Historical v14 operating and completion policy

Master Policy v14 (2026-11-12) is the sole current policy authority. Its complete
24-page user-supplied text was reviewed with user approval; the original PDF was
unavailable and its SHA-256 remains unverified. Apply v14 and the permanent
[AGENTS](AGENTS.md) controls. Stale earlier-version labels in the
[verification policy](docs/portfolio-verification-policy.md#official-aws-emulator--policy-v13)
are tracked in the V7-0 contract and do not make earlier policies current.
Real AWS access remains prohibited in Codex Cloud. Strictly isolated official AWS
Emulator lifecycle validation is permitted for supported resources and supplements
all existing credential-free CI/security tests. Real AWS deployment is optional,
not mandatory for portfolio completion; unsupported/untested behavior must remain
explicit and independent review is required. No emulator CI requirement is added.
V6 has merged at main `e1cdbce78ba11959093a99ffd9300b8c0f9e52e0`.
Historical phase snapshots below retain their original evidence scope.
See [V7-0 REST/private integration contract](docs/v7-rest-private-integration-feasibility.md)
for static Provider6.72.0 findings, P0 OPEN gates and proposed implementation order;
no V7 resource implementation or end-to-end feasibility approval is claimed.

### V6 Cognito source foundation

Accepted post-V5 main `97f870753926398368733c39da722d5d7b792fa5` passed
[push CI43109394809](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43109394809)
(686 native/153 toolkit/13 configurations). V6 adds [cognito_auth](infra/modules/cognito_auth/README.md) and
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

### What is implemented

The **post-R2 offline serverless API snapshot** has **eight reusable Terraform
modules repository-wide at that revision**, **four DEV root module instances**, **17 managed resource definitions**
and **eight root outputs**. The root composes artifact_bucket (6), secret_metadata
(1), lambda_workload (4) and http_api (6): Lambda owns its execution IAM/application
logs, and HTTP API owns its separate access log. The workload still uses versioned
S3 ZIP references, metadata-only Secrets Manager and an AWS_IAM HTTP API; no REST
or workload VPC migration is implied. Five exact resource-level moved
declarations preserve R1/R2 source address correspondence; no actual state
migration has been executed or verified. Generic cloudwatch_logs remains available
and independently tested, with no current DEV root consumer.

Verified main `df5ef4b2e03bd55109b0490b1e63d1d4199b663b` passed
[post-R2 CI 42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148) with **491 Terraform native tests / 153 Python tests**.
This is the R3 starting baseline, not R4 acceptance or AWS deployment evidence.

The **historical pre-R1 MVP acceptance** (2026-11-08, main
`89755c30508b78527fd46fa18593d5d5b11150f1`) recorded **384 native / 153 Python**
tests for nine modules and seven root instances. Its original
[acceptance evidence](docs/offline-mvp-acceptance.md) remains unchanged. R1 later
established 438/153; see the [milestones and R4 handoff](docs/repository-structure-strategy.md#r3-stabilization-and-r4-handoff).
No historical result is relabeled as current execution or Live connectivity.

Historical V3 development snapshot: the approved post-V2 main `da1af5c4eed15f5c9145799409d53c1db7508c94` passed
[CI 42688811654](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42688811654)
(560 native / 153 Python, 10 configurations). V2 added opt-in VPC routing/NAT/S3
endpoint support and a separate DEV Network Root. V3 adds the candidate
[private EKS module](infra/modules/eks_platform/README.md) and
[DEV Platform Root](infra/services/dev/ca-central-1/platform/README.md), using a
typed minimal network reference; no whole-state access or runtime integration.
The candidate library has nine children and three DEV roots. Local V3 child/Root
native evidence is 52/29; complete PR regression remains independently required
(expected 641 native / 153 Python, 12 configurations). No AWS resource is deployed.
The historical HTTP API contract and acceptance records above remain unchanged.

Accepted post-V3 main `6b185820c806a0c96410a145106b9f103db14d89` passed
[CI42720431920](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42720431920)
(641 native/153 Python,12 configurations). V4 adds the candidate
[private ingress child](infra/modules/private_ingress/README.md) beside EKS in the
existing Platform Root: internal NLB TCP443 passthrough, explicit IP backend port,
dedicated client/NLB SGs and scoped rules. No targets/controller/PKI are deployed.
There are10 children, three Roots; expected full CI678/153 and13 configurations
await independent review. Local new Child28/updated Root38 native tests passed;
all runtime/TLS/output-publication/Live gates remain OPEN.

### Target architecture — defined, not deployed

The next design combines Route 53, CloudFront, WAF and ACM with a Cognito-protected
API Gateway REST API. CloudFront origin mTLS protects the Regional custom domain;
REST VPC Link V2 routes through an internal NLB (TCP:443) to Istio Gateway and
STRICT mTLS/SPIFFE-protected EC2 EKS workloads. PostgreSQL, ECR, private deployment automation,
observability and shared event notifications complete the target.

| Environment | Target workload capacity | Target database | Completion evidence |
| --- | --- | --- | --- |
| DEV | One active workload AZ, one NAT, capacity-reviewed minimal EC2 EKS worker(s) for mesh/system/app, bounded HPA + Cluster Autoscaler; extra required AZ subnets | Single-AZ RDS PostgreSQL | Offline checks; only feasible separately approved limited DEV Live scenarios |
| STG | Two active workload AZs, per-AZ NAT/managed capacity, redundant Istiod/Gateway/apps, HPA + Cluster Autoscaler and reviewed remaining-AZ peak capacity | Aurora PostgreSQL Provisioned writer/reader across AZs | Offline verification; no deployment or authenticated plan required |
| PROD | Two active workload AZs, per-AZ NAT/managed capacity, redundant Istiod/Gateway/apps, HPA + Cluster Autoscaler and reviewed remaining-AZ peak capacity | Aurora PostgreSQL Provisioned writer/reader across AZs | Offline verification; no deployment or authenticated plan required |

Configured AZ coverage can exceed active worker/database AZs. These targets make
no measured SLA/RTO/RPO or disaster recovery guarantee; replica counts alone do not prove resilience.

### Engineering highlights

- **Infrastructure:** Terraform modules, environment/Region/service root ownership,
  account-restricted providers, secure defaults and explicit state boundaries.
- **Identity and security:** least-privilege IAM, metadata-only secret management,
  private resource safeguards and independently checked authorization contracts.
- **Verification:** credential-free GitHub Actions, mock plans, input rejection,
  mutation tests, malformed-evidence checks and complete regression coverage.
- **Planned delivery and operations:** GitHub Actions AWS OIDC, immutable ECR image
  digests, CodeBuild/private EKS deployment, Lambda versions/aliases, EventBridge
  notifications, Fluent Bit/Datadog and SSM-only Packer/Ansible administration.

### Technical documentation

- [Architecture v2 and migration decisions](docs/architecture-v2.md)
- [Portfolio Definition of Done and evidence policy](docs/portfolio-verification-policy.md)
- [Implemented modules, technical history and offline CI details](infra/README.md)
- [Current development root contract](infra/services/dev/ca-central-1/serverless-api/README.md)
- [Offline MVP acceptance](docs/offline-mvp-acceptance.md)
- [Live-readiness approval gates](docs/dev-live-validation-readiness.md)
- [Account, state and artifact bootstrap decision plan](docs/dev-bootstrap-decision-plan.md)

### V5 private runtime source and offline evidence

Accepted post-V4 main `a4f0a9b8b0a810976c7ab305001729463443b27b` passed
[CI42757339642](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42757339642)
with678 native/153 toolkit and13 initialized configurations. V5 extends the same
Platform/private_ingress owner with exact EKS IRSA Role+registration-only policy
and four scoped Istio webhook/XDS SG rules. There are still10 children/three DEV
Roots/13 configurations; basic Platform has54 resources (EKS37+ingress17).
Existing NLB/TG/static SG/provider/state interfaces remain owned as before.

The [runtime foundation](kubernetes/README.md) renders pinned LBC3.6.2 and Istio1.32.0 using
verified Helm3.22.1. Its61 objects implement ClusterIP Gateway, exact guarded TGB,
external CA/Secret references, MUTUAL TLS>=1.2 with client SPKI, STRICT mesh and
namespace default deny. No application or authenticated deployment is performed.
Actual local checks: Child36/Root38/EKS52 native; runtime8 Helm renders,
122 schema objects,58 security mutations,18 invalid inputs,19 evidence faults.
Current totals are in the latest Full CI job summary ("Summarize actual validation results");
this section is not a completed CI claim. Historical V3/V4 snapshots retain their original scope.

Registration-only IAM excludes ModifyTargetGroup/Attributes and SG writes. LBC
has no universal TGB-only switch; layered flags/RBAC/admission/IAM and clean
existing-resource inventory are mandatory. Effective admission, CA custody,
application sidecar CNI under restricted PSS, real AWS references/output publication,
capacity/connectivity and future REST backend TLS/SNI compatibility remain OPEN.
Offline schemas do not prove handshakes, IAM, controller effectiveness or Live.
G01–G07, cumulative JPY10,000, complete72-hour removal and the Secrets Manager
30-day recovery conflict remain unchanged. No State/AWS/Kubernetes Live authority.

<a id="current-limitations"></a>

### Historical v14 limitations

Current operating policy is Master Policy v14 (2026-11-12), per user instruction.
The complete user-supplied v14 text was reviewed; original PDF/hash verification
was not possible. The [architecture authority record](docs/architecture-v2.md#authority-evidence-and-status)
preserves historical provenance without treating earlier policies as current.

The full REST/mTLS/Cognito/database/delivery architecture is not deployed. V4/V5
provide NLB and runtime source, not an operational Cluster or runtime workloads; actual capacity, private access and AWS-managed Cluster SG residual
permissions require external review. It has not replaced the tested HTTP API MVP. No suitable
Lambda runtime application/build artifact is currently provided. Account/state
ownership, artifact bootstrap, secret-safe federation, certificate identity/revocation
feasibility compatible with Cognito, provider support and deployment permissions
still require decisions and verification. API Gateway does not automatically check
client-certificate revocation; CA trust does not authorize only one client.
CloudFront viewer *.cloudfront.net and Cognito managed login domains are allowed;
API inbound mTLS needs a suitable Regional custom domain, with free DNS feasibility
reviewed before implementation. No domain or certificate is selected here.

No credentials, authenticated AWS operations, deployments or secret values are
introduced here. Offline acceptance does not authorize live validation. Real
production delivery would require operational, security, performance and recovery
validation beyond this portfolio's completion scope.

### DEV Live restrictions — all seven gates OPEN

No Live operation is authorized here. Actual cumulative DEV Live spending must
stay within **JPY 10,000**, and testing plus verified complete teardown must finish
within **72 hours from approved Live start**. Prioritize feasible resource creation,
Istio positive/negative mTLS and REST/NLB/Gateway backend authentication; delivery,
rollback and notifications only within remaining approved scope/budget. Full
simultaneous CloudFront/Cognito/RDS/delivery testing is not mandatory if infeasible.

CloudFront Origin mTLS supports Business, Premium and Pay-as-you-go, not Free.
Plan/feature, certificate lifecycle, fixed/usage costs, tax/FX and contingency/
teardown review are mandatory; no plan is purchased or selected. A 72-hour window
does not guarantee affordability and Budgets/alerts are not a billing cutoff.
Unexecuted scenarios remain OPEN or Offline-only. Complete removal includes all
exercise-created managed/external resources; stopped EC2 or successful destroy
alone is insufficient. Historical/delayed billing can still arrive afterward.
Administration EC2's Toronto weekday 08:00–19:00 schedule does not replace this
deadline or stop other service charges. See the detailed readiness/verification
documents before any separately authorized execution.
