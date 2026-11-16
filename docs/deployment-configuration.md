# DEV deployment configuration, values, state and naming

Status: conventions approved by the Owner on 2026-11-16 for Step 1, the DEV
deploy-ready brush-up. This document defines the rules. Per-root value files,
the local workflow, the state bucket bootstrap and the renaming of existing
resources are implemented by later Step 1 pull requests. Nothing here authorizes
real AWS access in Codex Cloud or through CI/CD.

## 1. Where values live

| Category | Examples | Location | Tracked |
| --- | --- | --- | --- |
| Non-secret configuration | CIDR ranges, versions, sizes, ports, scopes | `terraform.tfvars` in each root | Yes |
| Feature flags | Optional functionality switches | `features.auto.tfvars` in a root | Yes |
| Environment-specific, not secret | AWS account ID, operator IP/CIDR, notification email, domain names, pre-existing IAM role ARNs | Placeholders in `terraform.tfvars`; real values only in `local.auto.tfvars` in the same root | Template only (`local.auto.tfvars.example`) |
| Secret values | Passwords, tokens, private keys, client secrets | AWS Secrets Manager only, registered before the consumer is built | Never |

Environment-specific values are not credentials, but a public repository should
not disclose them: they identify a person or an account and help reconnaissance.

Secret values follow Secrets Manager approach A. Terraform manages secret metadata
only; the value is set outside Terraform. No secret value may appear in any tfvars
file, variable, output, plan or State, including `local.auto.tfvars`. Where AWS can
own a credential itself, prefer that, for example RDS-managed master passwords.

### Placeholders

Committed `terraform.tfvars` files use reserved documentation values, so a reader
can see every input while no real environment is disclosed:

| Value | Placeholder |
| --- | --- |
| AWS account ID | `123456789012` |
| Operator IPv4 CIDR | `203.0.113.10/32` (RFC 5737 documentation range) |
| Email address | `ops@example.com` (RFC 2606 reserved domain) |
| Domain name | `example.com` |
| IAM role ARN | `arn:aws:iam::123456789012:role/example-role` |

The local workflow must refuse to plan or apply against real AWS while any
placeholder remains (implemented in a later Step 1 pull request).

### Load order

Terraform loads `terraform.tfvars` first and then `*.auto.tfvars` files in lexical
order, with later values taking precedence. An untracked `local.auto.tfvars`
therefore overrides committed placeholders without editing a tracked file. Real
use is: copy `local.auto.tfvars.example` to `local.auto.tfvars`, replace the
placeholders and run the local workflow. Verified offline with Terraform 1.17.0.

### Guard

`scripts/repository-hygiene/check_tracked_files.py` runs in Full CI. It fails when
Git tracks any of these, even when they were force-added past `.gitignore`:

- `local.auto.tfvars`, `*.local.tfvars` and their JSON forms
- `*.tfbackend`, `backend_override.tf` and other Terraform override files
- State, lock info and saved plans
- Anything under a `.terraform/` working directory
- Any other `*.tfvars` file except `terraform.tfvars` and `features.auto.tfvars`

It checks paths only, never file contents, and makes no AWS call.

## 2. Local-only real deployment

- Real AWS plan, apply and destroy run only from the operator's local workstation,
  by the Owner or an operator, outside Codex Cloud and never through CI/CD.
- GitHub Actions runs offline checks only: formatting, validation, mock plans,
  security checks and the repository guard. It holds no AWS credentials.
- An optional real deployment remains subject to G01–G07, the cumulative JPY 10,000
  DEV limit and complete verified teardown within 72 hours.
- The apply/destroy order, cross-root hand-off and preflight checks are delivered
  by later Step 1 pull requests.

## 3. Terraform state

- **Default for DEV:** local State per root. Tracked `backend.tf` files keep
  `backend "local" {}`, so CI and default use never need a bucket.
- **Optional DEV S3 backend for handover:** a dedicated bootstrap root (a later
  Step 1 pull request) creates one state bucket with versioning, server-side
  encryption with AWS managed keys (no customer managed KMS keys), all public
  access blocked and a TLS-only bucket policy. Locking uses the S3 native lock file
  (`use_lockfile = true`); no DynamoDB table is needed. The bootstrap root itself
  keeps local State.
- **Switching a root to S3 is local-only:** copy the tracked
  `backend_override.tf.example` to an untracked `backend_override.tf`, which declares
  `backend "s3" {}`; put the bucket, key and region in an untracked
  `backend.s3.tfbackend`; then run
  `terraform init -backend-config=backend.s3.tfbackend -migrate-state`. Terraform
  replaces the tracked backend with the override file's backend (verified offline
  with Terraform 1.17.0).
- **State keys:** one per root, `<project>/<env>/<region>/<service>/terraform.tfstate`.
- **STG/PROD:** remote backends remain a later phase.

## 4. Resource naming

Pattern: `<project>-<env>-<service>[-<purpose>]`, lowercase, hyphen-separated.

| Part | Rule |
| --- | --- |
| `project` | Short project identifier; a committed, non-secret value |
| `env` | `dev` (STG/PROD later) |
| `service` | Short AWS service token, for example `vpc`, `eks`, `ec2`, `rds`, `s3`, `lambda`, `apigw`, `cognito`, `nlb`, `sqs`, `sns` |
| `purpose` | Only when more than one resource of that service exists, for example `ingress`, `tfstate`, `artifacts`, `devaccess` |

Examples with project `acme`: `acme-dev-eks`, `acme-dev-nlb-ingress`,
`acme-dev-ec2-devaccess`, `acme-dev-subnet-private-a`.

Exceptions, kept minimal and documented where used:

- **Globally unique names** such as S3 buckets append the AWS account ID, for
  example `acme-dev-s3-tfstate-123456789012`. The account ID is a local value.
- **Length limits:** load balancer and target group names allow 32 characters;
  IAM role and Lambda function names 64; S3 bucket names 3–63. Keep `project`
  short and abbreviate `purpose` where needed.
- **AWS-mandated names** keep the AWS prefix, for example `/aws/lambda/<function>`
  or `/aws/eks/<cluster>/cluster`. Other CloudWatch log groups use the path form
  `/<project>/<env>/<service>/<purpose>`.
- **Renaming existing resources** happens in a later Step 1 pull request. Nothing is
  deployed, so no migration is needed, but tests and move guards must be updated
  deliberately.

## 5. Target portfolio scope (Owner, 2026-11-16)

The finished DEV portfolio should present a realistic project configuration that a
recruiter can evaluate. Target services:

VPC, SQS, SNS, Lambda, EC2, EKS, RDS, S3, IAM, Secrets Manager, KMS (AWS managed
keys only), Route 53, ACM, API Gateway, GitHub Actions, Terraform, Ansible, Packer,
load balancers, WAF, CloudFront, Cognito, EventBridge, CloudWatch, Inspector,
GuardDuty, Shield and CloudTrail.

Shield Standard is automatic and free. Terraform resources exist only for the paid
Shield Advanced, so Shield is documented rather than provisioned. The Kubernetes
runtime is in scope at a minimal development level.

## 6. Step plan

| Step | Work | Executor |
| --- | --- | --- |
| 1 | Make the existing DEV roots and the minimal Kubernetes runtime deploy-ready, without new features except those needed to deploy | Claude Code |
| 2 | Emulator rehearsals of the real modules, then an end-to-end apply and destroy; each run needs Owner authorization | Claude Code |
| 3 | Add the remaining target services | Codex, after a handover document |
| 4 | Core acceptance audit | Independent reviewer and Owner |

Step 1 items, each as its own pull request that stops for review and Owner merge
approval. The Owner may reorder them.

1. These rules and the repository guard (this document).
2. Naming alignment and a consistency audit of the existing code.
3. Per-root placeholder `terraform.tfvars`, `local.auto.tfvars.example`, a local
   workflow with preflight checks and CI validation using the committed values.
4. DEV state bucket bootstrap root and the optional S3 backend override.
5. SSM developer-access EC2: local workstation → Session Manager port forwarding →
   private EKS endpoint (443), and later private RDS (5432). No SSH and no public IP.
6. Cross-root hand-off automation and the local apply/destroy runbook, including
   the Kubernetes runtime through the developer-access tunnel.

V7-B/C/D, NP-2B/NP-3 and other new features stay paused until Steps 1 and 2 are
complete.
