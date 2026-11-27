# AWS Terraform and Kubernetes Portfolio

## Project Overview

An infrastructure and platform engineering portfolio focused on reusable
Terraform, private AWS networking, and verifiable Kubernetes operations. The
implementation includes **15 Terraform Child Modules, 7 DEV Roots in
`ca-central-1`, and 5 GitHub Actions workflow definitions**. The evidence covers
source, offline tests, and selected AWS Emulator lifecycles. Live AWS and EKS
behavior is outside the verified scope.

[Release scope and inventory](docs/mvp-release-scope.md) ·
[Verification evidence](docs/mvp-release-evidence.md) ·
[Architecture v2](docs/architecture-v2.md)

## Architecture

The three scenarios illustrate separate design and verification boundaries.
Solid arrows show relationships declared in source. Dashed arrows identify
partial implementation or future design. A line does not represent measured
network traffic.

```mermaid
flowchart TB
    subgraph Foundation["AWS Foundation · Terraform source"]
        VPC["VPC and private subnets"] --> EKS["Private EKS and managed nodes"]
        VPC --> NLB["Internal Network Load Balancer"]
        IAM["Scoped IAM"] --> EKS
        State["State bootstrap"]
        Registry["Private ECR registry"]
        Access["DEV developer access"]
    end
    subgraph APIs["API and Serverless · two independent Roots"]
        Cognito["Cognito User Pool"] --> REST["Regional REST core and authorizer"]
        REST -.-> Integration["Future REST methods and private integration"]
        HTTP["HTTP API with IAM authorization"] --> Lambda["Lambda"]
        HTTP --> Logs["CloudWatch Logs"]
        Lambda --> Logs
    end
    subgraph Operations["Kubernetes and Operations · offline"]
        Helm["Pinned Helm and Istio configuration"] --> Render["Offline render and validation"]
        Policy["RBAC and NetworkPolicy declarations"] --> Render
        Render --> Plan["Offline plan and stage checks"]
        Plan --> Fake["Fake-only operation and receipt tests"]
        Runbook["DEV runbook"]
    end
    Roadmap["Future design: RDS PostgreSQL"]

    classDef source fill:#e8f5e9,stroke:#2e6b3f,color:#18251b
    classDef partial fill:#fff1cc,stroke:#9a6000,color:#302000
    classDef design fill:#edf1f7,stroke:#52647b,stroke-dasharray:5 3,color:#202b3a
    class VPC,EKS,NLB,IAM,State,Registry,Access,Cognito,HTTP,Lambda,Logs,Helm,Render,Plan,Fake,Runbook source
    class REST,Policy partial
    class Integration,Roadmap design
```

**Green** indicates source implemented for the shown scope. **Amber** indicates
a partial capability. The REST Root has a core and authorizer, and Kubernetes
policies have declarations and offline checks. **Dashed grey** indicates design
or future work. There is no deployed end-to-end path between these scenarios.
[Ownership and verification boundaries](docs/mvp-release-scope.md#scenario-boundaries)

## Technical Stack

| Layer | In this repository |
| --- | --- |
| Infrastructure | Terraform 1.17.0 workflow pin, AWS Provider 6.72.0 DEV locks, VPC, EKS, IAM, API Gateway, Cognito, Lambda, S3, ECR and CloudWatch Logs |
| Kubernetes | Helm and Istio, AWS Load Balancer Controller, TargetGroupBinding, RBAC and NetworkPolicy. Versions and hashes are in the [dependency lock](kubernetes/dependencies.lock.json) |
| Verification | Terraform Native mock plans, Python validators, render and schema checks, negative and mutation cases, and credential-free GitHub Actions |

## Engineering Highlights

- **Reusable infrastructure with explicit owners.** DEV Roots own provider,
  account and State configuration. Child Modules own resource behavior and
  validation. Terraform owns static load-balancer resources. The controller
  design owns dynamic target registration.
- **Security contracts in source.** Private endpoints and scoped IAM constrain
  access. Terraform manages Secrets Manager metadata. Secret values stay
  outside Terraform. Runtime source declares default-deny policies, restricted
  admission and separate Gateway and service-mesh TLS controls.
- **Operational checks with traceable evidence.** Offline plan, status, and
  Fake-only apply and destroy tests exercise preconditions, failure paths and
  receipts. The [runbook](docs/dev-runbook.md) distinguishes offline operations
  from future operator procedures that require separate approval.

## Repository Structure

| Path | Contents |
| --- | --- |
| [`infra/modules/`](infra/modules/) | Reusable Terraform Child Modules |
| [`infra/services/dev/ca-central-1/`](infra/services/dev/ca-central-1/) | Seven separately owned DEV Roots |
| [`kubernetes/`](kubernetes/) | Runtime configuration, dependency locks and render tests |
| [`scripts/`](scripts/) and [`tests/`](tests/) | Offline validators, operational tooling, CI policy and expected test counts |
| [`.github/workflows/`](.github/workflows/) | PR Safety CI, Full CI, Offline Contracts and two Emulator workflows |
| [`docs/`](docs/) | Architecture, verification records, runbooks and remaining decisions |

## Verification Results

| Evidence | Verified scope |
| --- | --- |
| [Terraform offline CI, run 43347607972](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43347607972), attempt 1, [`be79be6`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/commit/be79be6a64a6ef2e78f76e920afb335c59bbd49d) | Historical success: 781 Terraform Native tests, 153 Python toolkit tests and eight pinned Helm renders across two configurations. Counts apply to that commit. |
| [Step 2 Emulator rehearsal, run 44988721098](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44988721098), attempt 1, [`a3cf9bc`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/commit/a3cf9bcf4de277656c9664bb1a8bf91b57ee6b24) | Lifecycle and cleanup passed for 16 network resources without interface endpoints and seven API resources in the official AWS Emulator. |
| [Offline Contracts, run 45910291601](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/45910291601), attempt 1, [`1a5e3d4`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/commit/1a5e3d41da208407caaf8ac9a4702c3458367a18) | Static, negative, mutation and evidence-ledger checks passed on the release source baseline. The run did not exercise a resource lifecycle. |

The [evidence record](docs/mvp-release-evidence.md) lists exact commits, tested
scope and limits, including Step 1 acceptance and the separately accepted
single-VPC demonstration. The [sanitized Emulator ledger](docs/evidence/emulator-runs/index.md)
retains run/attempt records beyond the lifetime of GitHub logs. Every PR uses
PR Safety CI. Full CI applies to the designated milestones and high-risk changes
defined in the [verification policy](docs/portfolio-verification-policy.md).

<a id="current-limitations"></a>

## Limitations and Roadmap

- Real AWS/EKS deployment, effective IAM, controller registration, Kubernetes
  packet enforcement, Cognito sign-in, REST invocation and end-to-end mTLS are
  unverified. `network-full` and `tfstate` have documented Emulator compatibility
  blockers. Kubernetes operations evidence covers the Fake-only engines.
- **After the initial release:** RDS PostgreSQL, the remaining REST methods and
  private integration, CloudFront/WAF, and the approved wider security,
  observability and operations scope. NP-2B and NP-3 remain paused.
- The initial release describes the existing implementation and its evidence.
  CORE PORTFOLIO COMPLETE and PORTFOLIO COMPLETE remain undeclared.

<a id="current-controlling-policy--master-policy-v145"></a>
<a id="current-controlling-policy"></a>
<a id="current-operating-and-completion-policy"></a>
<a id="historical-dev-live-restrictions-not-current-live-is-out-of-scope-under-v145-15"></a>

The [repository rules](AGENTS.md#repository-guidance), [Step 1 audit](docs/step1-audit-report.md)
and [Step 2 closure](docs/step2-emulator-rehearsals.md#closure-owner-decision-2026-11-24)
record the governing policy, decisions and residual risks. The
[previous README at the fixed baseline](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/1a5e3d41da208407caaf8ac9a4702c3458367a18/README.md)
preserves the original engineering history and historical verification snapshots.
