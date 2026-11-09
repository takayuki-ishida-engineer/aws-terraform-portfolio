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
API Gateway REST API. Requests route to Lambda or through VPC Link V2 and an
internal ALB to EC2-backed EKS. PostgreSQL, ECR, private deployment automation,
observability and shared event notifications complete the target.

| Environment | Target workload capacity | Target database | Completion evidence |
| --- | --- | --- | --- |
| DEV | One active workload AZ, one NAT, one initial minimal EKS worker and one app replica; additional service-required AZ subnets | Single-AZ RDS PostgreSQL | Offline checks plus limited live integration/delivery/rollback evidence only after separate external authorization |
| STG | Two active workload AZs, two NATs, managed nodes and at least two replicas distributed across AZs | Aurora PostgreSQL Provisioned writer/reader across AZs | Offline verification; no deployment or authenticated plan required |
| PROD | Two active workload AZs, two NATs, managed nodes and at least two replicas distributed across AZs | Aurora PostgreSQL Provisioned writer/reader across AZs | Offline verification; no deployment or authenticated plan required |

Configured AZ coverage can exceed active worker/database AZs. These targets make
no measured availability or disaster recovery guarantee.

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

The REST/Cognito, EKS/database and live delivery architecture remains defined or
awaiting design approval; it has not replaced the tested HTTP API MVP. No suitable
Lambda runtime application/build artifact is currently provided. Account/state
ownership, artifact bootstrap, secret-safe federation provisioning, edge-origin
protection and deployment permissions still require decisions and verification.

No credentials, authenticated AWS operations, deployments or secret values are
introduced here. Offline acceptance does not authorize live validation. Real
production delivery would require operational, security, performance and recovery
validation beyond this portfolio's completion scope.
