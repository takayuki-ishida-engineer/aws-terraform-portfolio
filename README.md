# AWS Terraform Infrastructure Portfolio

An AWS-first infrastructure portfolio demonstrating reusable Terraform design,
least-privilege access, explicit ownership boundaries and independent security
verification. AWS Terraform is the primary portfolio; AWS CloudFormation and
Azure Terraform are separate, smaller supporting portfolios, not implementations
claimed by this repository.

## What is implemented

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

## Target architecture — defined, not deployed

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

## Engineering highlights

- **Infrastructure:** Terraform modules, environment/Region/service root ownership,
  account-restricted providers, secure defaults and explicit state boundaries.
- **Identity and security:** least-privilege IAM, metadata-only secret management,
  private resource safeguards and independently checked authorization contracts.
- **Verification:** credential-free GitHub Actions, mock plans, input rejection,
  mutation tests, malformed-evidence checks and complete regression coverage.
- **Planned delivery and operations:** GitHub Actions AWS OIDC, immutable ECR image
  digests, CodeBuild/private EKS deployment, Lambda versions/aliases, EventBridge
  notifications, Fluent Bit/Datadog and SSM-only Packer/Ansible administration.

## Technical documentation

- [Architecture v2 and migration decisions](docs/architecture-v2.md)
- [Portfolio Definition of Done and evidence policy](docs/portfolio-verification-policy.md)
- [Implemented modules, technical history and offline CI details](infra/README.md)
- [Current development root contract](infra/services/dev/ca-central-1/serverless-api/README.md)
- [Offline MVP acceptance](docs/offline-mvp-acceptance.md)
- [Live-readiness approval gates](docs/dev-live-validation-readiness.md)
- [Account, state and artifact bootstrap decision plan](docs/dev-bootstrap-decision-plan.md)

## V5 private runtime source and offline evidence

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

## Current limitations

Current operating policy is Master Policy v11 (2026-11-09), per user approval.
The external PDF is unavailable here; the [architecture authority record](docs/architecture-v2.md#authority-evidence-and-status) preserves historical v10 provenance without claiming full v11 review.

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

## DEV Live restrictions — all seven gates OPEN

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
