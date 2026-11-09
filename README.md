# AWS Terraform Infrastructure Portfolio

An AWS-first infrastructure portfolio demonstrating reusable Terraform design,
least-privilege access, explicit ownership boundaries and independent security
verification. AWS Terraform is the primary portfolio; AWS CloudFormation and
Azure Terraform are separate, smaller supporting portfolios, not implementations
claimed by this repository.

## What is implemented

The accepted **offline serverless API MVP** includes nine reusable Terraform
modules and a development root composing seven module instances into 17 managed
resource definitions. It connects a versioned S3 ZIP reference, metadata-only
Secrets Manager, separate CloudWatch Log Groups, a least-privilege execution role,
Lambda and an AWS_IAM-authorized HTTP API.

Recorded successful offline evidence includes **384 Terraform native mock tests**,
**153 Python tests**, root security mutations, negative cases and independent IAM
guardrails. These are verified historical results, not a limit on future coverage.
See the [acceptance evidence](docs/offline-mvp-acceptance.md) for provenance and
limitations. No AWS deployment or live connectivity validation is claimed.

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

## Current limitations

The Master Policy v10 REST/NLB/Istio/mTLS, Cognito, EKS/database and delivery
architecture is an approved design target with implementation details OPEN; it has not replaced the tested HTTP API MVP. No suitable
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
