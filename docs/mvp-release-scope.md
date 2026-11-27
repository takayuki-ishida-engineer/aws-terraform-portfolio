# Initial Career Portfolio Scope

The initial release presents the AWS Terraform and Kubernetes work in the
[source baseline](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/tree/1a5e3d41da208407caaf8ac9a4702c3458367a18)
at commit `1a5e3d41da208407caaf8ac9a4702c3458367a18`, Tree
`b91ef273126464718b5b541c79b8bc5483665138`. That tree contains 15 Child Modules,
7 DEV Roots and 5 workflow definitions. All Roots listed here are in
`dev/ca-central-1`. Shared modules and fixtures illustrate the intended STG and
PROD reuse boundary.

## Scenario Boundaries

| Scenario | Implemented source | Evidence boundary |
| --- | --- | --- |
| **AWS Foundation** | VPC and route/endpoint configuration; private EKS, EC2 managed nodes and internal TCP NLB; IAM; DEV State bootstrap; private ECR repositories; scoped DEV access | The Step 1 audit records offline verification for the DEV scope. The Emulator demonstrated the network Root without interface endpoints. EKS, access, registry use and operational State access are untested in live environments. |
| **API and Serverless** | The `api` Root composes a Cognito User Pool with a Regional REST API and Authorizer. The separate `serverless-api` Root composes an IAM-authenticated HTTP API v2, Lambda receiving code from a versioned S3 artifact, and CloudWatch Logs. | The Step 2 Emulator rehearsed the REST Core and Cognito resource lifecycle. Login, invocation and the serverless Root lifecycle remain outside Emulator evidence. The REST source has no methods, deployments, stages or VPC Link integration. |
| **Kubernetes and Operations** | Pinned Helm rendering for the AWS Load Balancer Controller and Istio; scoped RBAC and admission; TargetGroupBinding, Gateway TLS, mesh policies and default-deny NetworkPolicy declarations. The operations contract includes offline planning, read-only status, and Fake-only apply/destroy flows and receipts. | Offline render, schema, guardrail, negative and mutation checks are recorded under their tested commits. Runtime traffic, target registration, live policy enforcement and real cluster lifecycle are untested. |

The [DEV runbook](dev-runbook.md) documents operator sequences and stop
conditions. The [Kubernetes design record](k8s-runtime-apply-destroy-design.md)
covers the Fake-only behavior and its prerequisites. The existing
[architecture](architecture-v2.md) shows the wider target and its gates.

## Actual Child Modules (15)

| Responsibility | Modules |
| --- | --- |
| Networking and platform | [vpc](../infra/modules/vpc/README.md), [eks_platform](../infra/modules/eks_platform/README.md), [private_ingress](../infra/modules/private_ingress/README.md) |
| API and application infrastructure | [api_gateway_rest](../infra/modules/api_gateway_rest/README.md), [cognito_auth](../infra/modules/cognito_auth/README.md), [api_gateway_http](../infra/modules/api_gateway_http/README.md), [lambda_workload](../infra/modules/lambda_workload/README.md) |
| Identity and access | [developer_access](../infra/modules/developer_access/README.md), [iam_access](../infra/modules/iam_access/README.md), [iam_account_policies](../infra/modules/iam_account_policies/README.md) |
| State, storage, registry, secrets and logs | [tfstate_bucket](../infra/modules/tfstate_bucket/README.md), [s3_artifact_bucket](../infra/modules/s3_artifact_bucket/README.md), [ecr_repository](../infra/modules/ecr_repository/README.md), [secrets_manager](../infra/modules/secrets_manager/README.md), [cloudwatch_logs](../infra/modules/cloudwatch_logs/README.md) |

The IAM modules have their own source contracts. The directory count does not
imply every module is composed directly by a DEV Root.

## Actual DEV Roots (7)

| Root | Owns source configuration for |
| --- | --- |
| [network](../infra/services/dev/ca-central-1/network/README.md) | VPC, subnets, routing and selected endpoints |
| [platform](../infra/services/dev/ca-central-1/platform/README.md) | Private EKS and internal NLB/target group; Kubernetes runtime owns dynamic registration |
| [api](../infra/services/dev/ca-central-1/api/README.md) | Cognito and Regional REST Core with Authorizer |
| [serverless-api](../infra/services/dev/ca-central-1/serverless-api/README.md) | Independent IAM-authenticated HTTP API, Lambda, artifact storage and logs |
| [tfstate](../infra/services/dev/ca-central-1/tfstate/README.md) | Optional DEV State-bucket bootstrap |
| [registry](../infra/services/dev/ca-central-1/registry/README.md) | Private ECR repositories; image publication is a separate operation |
| [developer-access](../infra/services/dev/ca-central-1/developer-access/README.md) | Scoped DEV access infrastructure |

Roots own their provider configuration and separate State by environment,
Region and service. Tracked DEV backends are local. Kubernetes runtime and
external release processes retain their own ownership boundaries. See
[deployment configuration](deployment-configuration.md).

## Actual Workflows (5)

| Workflow | Role |
| --- | --- |
| [PR Safety CI](../.github/workflows/pr-safety-ci.yml) | Required on every PR to main. Runs always-on and impact-selected checks under the existing CI contract. |
| [Terraform offline CI](../.github/workflows/terraform-offline-ci.yml) | Full credential-free regression for applicable milestones and high-risk changes. |
| [AWS Emulator offline contracts](../.github/workflows/aws-emulator-contracts.yml) | Offline verifier, rehearsal-gate and evidence-ledger checks. |
| [AWS Emulator representative verification](../.github/workflows/aws-emulator-verification.yml) | Separately authorized representative Emulator lifecycle. |
| [AWS Emulator Step 2 rehearsal](../.github/workflows/aws-emulator-rehearsal.yml) | Limited rehearsals under the existing trigger and authorization boundary. |

## Evidence and Open Work

| Status | Scope |
| --- | --- |
| **Source only** | Operational use of the private ECR mirror, real Kubernetes access and certificate registration, and live DEV deployment paths. Source and local contracts exist; actual infrastructure or runtime behavior remains unverified. |
| **Offline verified within cited runs** | DEV Source/Offline acceptance, Terraform mock plans, pinned renders, policy validators and Fake-only operations tests. Counts refer to the exact records in the [verification evidence](mvp-release-evidence.md). |
| **Emulator demonstrated within cited runs** | Disposable single-VPC proof and the Step 2 network and API lifecycles in their measured configurations. |
| **Emulator compatibility blocked** | `network-full` and `tfstate`; see the [Step 2 limits](step2-emulator-rehearsals.md#closure-owner-decision-2026-11-24). |
| **Not tested** | Emulator lifecycles for `serverless-api`, `platform`, `developer-access` and `registry`; Step 2 end-to-end lifecycle; Kubernetes runtime E2E, real network flows and real TLS/mTLS handshakes. |
| **Design or later implementation** | RDS PostgreSQL, the REST method/integration/stage path, CloudFront/WAF and the broader delivery and operations scope. NP-2B and NP-3 remain paused. |

## Security Hardening and Full Architecture Roadmap

Remaining work includes runtime network enforcement, artifact and scanner
qualification, certificate custody and rotation, dependency and release
evidence, and the approved telemetry, recovery and operational capabilities.
The [approved architecture](architecture-v2.md#revision-6-approved-target),
[CI and verification policy](portfolio-verification-policy.md#revision-6-verification-and-acceptance)
and [current governance record](../AGENTS.md#current-work-and-remaining-order-master_policy-19)
retain the gates and sequencing. The [REST feasibility record](v7-rest-private-integration-feasibility.md)
and [NetworkPolicy flow contract](np2-network-policy-flow-contract.md) describe
the outstanding integration and policy questions. The
[readiness record](dev-live-validation-readiness.md) preserves constraints for
any future, separately approved live scope.

This is a documentation release for presenting the existing implementation.
Technical acceptance, release of security gates and new implementation remain
subject to their own approvals. CORE PORTFOLIO COMPLETE and PORTFOLIO COMPLETE
remain undeclared.
