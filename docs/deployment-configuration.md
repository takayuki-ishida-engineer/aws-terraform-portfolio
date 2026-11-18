# DEV deployment configuration, values, state and naming

Status: conventions approved by the Owner on 2026-11-16 for Step 1, the DEV
deploy-ready brush-up. This document defines the rules. Names and tags (item 2),
the per-root value files and the local workflow (item 3) and the State bucket
bootstrap with the optional S3 backend (item 4) are implemented; the remaining
items follow in later Step 1 pull requests. Nothing here authorizes real AWS access in Codex Cloud or through CI/CD.

## 1. Where values live

| Category | Examples | Location | Tracked |
| --- | --- | --- | --- |
| Non-secret configuration | CIDR ranges, versions, sizes, ports, scopes | `terraform.tfvars` in each root | Yes |
| Feature flags | Optional functionality switches | `features.auto.tfvars` in a root | Yes |
| Environment-specific, not secret | AWS account ID, operator IP/CIDR, notification email, domain names, pre-existing IAM role ARNs | Placeholders in `terraform.tfvars`; real values only in `local.auto.tfvars` in the same root | Template only (`local.auto.tfvars.example`) |
| Secret values | Passwords, tokens, private keys, client secrets | AWS Secrets Manager only, registered before the consumer is built | Never |

Environment-specific values are not credentials, but a public repository should
not disclose them: they identify a person or an account and help reconnaissance.

Secret values follow Secrets Manager approach A. Terraform creates secret metadata
only, with no value and no dummy value; operators register the value manually from
a local CLI or the console before a consumer uses it. No secret value may appear in
any tfvars file, variable, output, plan or State, including `local.auto.tfvars`.
Where AWS can own a credential itself, prefer that, for example RDS-managed master
passwords.

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

The local workflow refuses to plan or apply against real AWS while any
placeholder remains: [`scripts/local-workflow/preflight.py`](../scripts/local-workflow/README.md)
also rejects unedited `local.auto.tfvars.example` values (project `myproj`, account
`111122223333`, `your-domain.test`) and the Emulator's synthetic account
`000000000000`.

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
- The [local workflow](../scripts/local-workflow/README.md) runs `init`, the offline
  and live preflight, a saved plan, a typed confirmation and the apply of exactly
  that plan, for one root at a time. Apply `tfstate` (only for the optional S3
  backend), `network`, `platform`, then `serverless-api` and `api`; destroy in the
  reverse order. The live preflight makes
  only read-only calls (caller account, State bucket versioning and public access
  block, EKS add-on catalog, node AMI parameter) and is refused in CI, in Claude
  Code or Codex cloud sessions and with the cloud session's placeholder credentials.
- Full CI plans every root with its committed values under mocks and proves the
  preflight refuses them and accepts synthetic local values. It never runs the live
  preflight.
- Cross-root hand-off automation, the serverless-api artifact upload sequence and
  the full runbook are delivered by Step 1 item 6.

## 3. Terraform state

- **Default for DEV:** local State per root. Tracked `backend.tf` files keep
  `backend "local" {}`, so CI and default use never need a bucket.
- **Optional DEV S3 backend for handover:** the bootstrap root
  `infra/services/dev/ca-central-1/tfstate/` (module `tfstate_bucket`) creates one
  State bucket with versioning, server-side encryption with Amazon S3 managed keys
  (SSE-S3, no customer managed KMS key), all public access blocked, ACLs disabled,
  a bucket policy that denies non-TLS and pre-TLS-1.2 requests, `force_destroy =
  false` and a lifecycle rule that expires noncurrent State versions after 90 days.
  Locking uses the S3 native lock file (`use_lockfile = true`); no DynamoDB table is
  needed. The bootstrap root itself keeps local State.
- **Switching a root to S3 is local-only:** copy the tracked
  `backend_override.tf.example` to an untracked `backend_override.tf`, which declares
  an empty `backend "s3" {}`; copy `backend.s3.tfbackend.example` to an untracked
  `backend.s3.tfbackend` and fill in the project (bucket, key, region,
  `use_lockfile = true`, `encrypt = true`, nothing else); then run
  `python3 scripts/local-workflow/run.py <root> migrate-state`, which checks the
  files, the caller account and the bucket before running
  `terraform init -backend-config=backend.s3.tfbackend -migrate-state`. Terraform
  replaces the tracked backend with the override file's backend (verified offline
  with Terraform 1.17.0). Afterwards `run.py` passes the backend settings on every
  init.
- **Back to local State or teardown:** delete both untracked files and run
  `terraform init -migrate-state` in the root. Before destroying the bootstrap root,
  every root must be back on local State (or destroyed) and every object version
  removed, because `force_destroy` is `false`.
- **Bucket name:** `<project>-<env>-s3-tfstate`, following section 4 without a
  uniqueness suffix.
- **State keys:** one per root, `<project>/<env>/<region>/<service>/terraform.tfstate`.
- **STG/PROD:** remote backends remain a later phase.

## 4. Resource naming

Applies to every AWS resource, and with the adaptation under "Names outside AWS"
to Kubernetes and other tool objects.

### Pattern

| Case | Pattern | Example |
| --- | --- | --- |
| General | `<project>-<env>-<type>[-<purpose>]` | `project-dev-role-eks-cluster` |
| Per-AZ resource | `<project>-<env>-<az>-<type>[-<purpose>]` | `project-dev-a-subnet-private1` |

- Lowercase letters, digits and hyphens only.
- `project`: the placeholder is `project`, which makes the value to replace obvious.
  A real value has at most 10 characters, starts with a letter and contains none of
  `aws`, `amazon` or `cognito` (reserved words of Cognito domains). This keeps load
  balancer and target group names within 32 characters.
- `env`: `dev` (`stg` and `prod` later).
- `az`: the Availability Zone letter (`a`, `b`, ...), placed right after `env`.
- `type`: the resource-type token below.
- `purpose`: see "Purposes".

### Resource-type tokens

A service's main resource uses the service's common AWS abbreviation; a service with
several resource types uses the type. New tokens follow the same principle.

| Area | Tokens |
| --- | --- |
| Network | `vpc` VPC, `subnet` subnet, `rtb` route table, `igw` internet gateway, `nat` NAT gateway, `eip` Elastic IP, `vpce` VPC endpoint, `sg` security group |
| Compute | `ec2` instance, `lt` launch template, `eks` EKS cluster, `ng` EKS node group, `lambda` function |
| IAM | `role` role, `policy` managed or inline policy, `profile` instance profile, `oidc` OIDC identity provider |
| Load balancing and API | `nlb` Network Load Balancer, `alb` Application Load Balancer, `tg` target group, `apigw` API Gateway API |
| Identity | `cognito` user pool, `client` app client, `auth` Cognito domain prefix |
| Secrets, keys, certificates | `secret` secret, `kms` key, `acm` certificate |
| Data and messaging | `s3` bucket, `rds` DB instance or cluster, `sqs` queue, `sns` topic, `rule` EventBridge rule |
| Edge and monitoring | `cloudfront` distribution, `waf` web ACL, `r53` hosted zone, `alarm` CloudWatch alarm, `trail` CloudTrail trail |

Sub-resources without a name of their own (listeners, add-ons, associations, rules
inside a web ACL) need no name. When such a sub-resource is taggable (security group
rules, EKS add-ons and access entries, listeners), its `Name` tag is the parent's
name plus a purpose and its `service` tag is the parent's token, for example
`project-dev-sg-eks-node-in-cluster-kubelet` (service `sg`) or `project-dev-eks-cni`
(service `eks`). Security group rule purposes read `<in or out>-<peer>-<flow>`.

### Purposes

- Add a purpose only when the environment holds more than one resource of a type;
  then every resource of that type gets one, never a bare name next to purposed ones.
- Per-AZ copies of the same resource are told apart by the AZ letter, not by a purpose.
- Join multi-word purposes with hyphens: `eks-cluster`.
- Always abbreviate a purpose as far as a person still understands it.
- A repeated identical purpose takes a two-digit sequence: `-01`, `-02`.
- Subnet tiers carry a number that counts that tier across the VPC, as the AWS VPC
  console does: AZ `a` holds `private1` and `public1`, AZ `b` holds `private2` and
  `public2`.

| Word | Abbreviation |
| --- | --- |
| application | `app` |
| gateway | `gw` |
| controller | `ctrl` |
| database | `db` |
| management | `mgmt` |
| operations | `ops` |
| AWS Load Balancer Controller | `lbc` |
| Amazon VPC CNI | `cni` |
| Terraform state | `tfstate` |

Words that are already short or have no widely understood abbreviation stay as
they are, for example `private`, `public`, `node`, `cluster`, `artifact`, `bastion`.

### Examples

| Resource | Name |
| --- | --- |
| VPC | `project-dev-vpc` |
| Subnets | `project-dev-a-subnet-private1`, `project-dev-a-subnet-public1`, `project-dev-b-subnet-private2`, `project-dev-b-subnet-public2` |
| NAT gateways and their EIPs | `project-dev-a-nat`, `project-dev-a-eip-nat` |
| Route tables | `project-dev-a-rtb-private1`, `project-dev-b-rtb-private2`, `project-dev-rtb-public` |
| EKS cluster and node group | `project-dev-eks`, `project-dev-ng` |
| IAM roles | `project-dev-role-eks-cluster`, `project-dev-role-eks-node`, `project-dev-role-lbc`, `project-dev-role-lambda` |
| NLB and target group | `project-dev-nlb`, `project-dev-tg-gw` |
| Lambda function | `project-dev-lambda` |
| API Gateway APIs | `project-dev-apigw-http`, `project-dev-apigw-rest` |
| Cognito | user pool `project-dev-cognito`, app client `project-dev-client`, domain `project-dev-auth` |
| S3 buckets | `project-dev-s3-artifact`, `project-dev-s3-tfstate` |
| VPC endpoints and their security group | `project-dev-vpce-ecr-api`, `project-dev-vpce-sts`, `project-dev-sg-vpce` |
| Secret | `/project/dev/secret/app` |
| Log groups | `/aws/lambda/project-dev-lambda`, `/aws/eks/project-dev-eks/cluster`, `/project/dev/apigw/http` |

### Exceptions

- **AWS-mandated prefixes stay**, for example `/aws/lambda/<function>` and
  `/aws/eks/<cluster>/cluster`.
- **Path form** for CloudWatch log groups and Secrets Manager secrets:
  `/<project>/<env>/<type>/<purpose>`.
- **Generated suffixes** (`name_prefix`) only where a resource must be replaced
  create-before-destroy to stay low risk, currently security groups and launch
  templates. The prefix still follows the pattern, for example `project-dev-sg-nlb-`.
  Each use is documented in the module README.
- **Underscores** where hyphens are invalid, for example database names
  `project_dev_app`.
- **No uniqueness suffix** for globally unique names such as S3 buckets and the
  Cognito domain prefix. Name collisions are handled case by case at deployment.
  The placeholder `project` will collide in real AWS, so replace it first.
- **Length limits:** load balancer and target group names 32 characters, IAM role
  and Lambda function names 64, S3 bucket names 3–63.

### Names outside AWS

- Kubernetes namespaces, workloads, service accounts and project-created ConfigMaps
  and Secrets, Helm releases and other tool objects (for example Ansible groups and
  Packer builds) use `<project>-<purpose>` with an abbreviated purpose, for example
  `project-app`.
- Names that upstream tools mandate stay unchanged, for example `kube-system`,
  `istio-system`, the Istio CA Secret `cacerts`, `aws-load-balancer-controller` and
  its webhook Secret `aws-load-balancer-controller-tls`.

### Name tag

Resources without a name attribute (VPC, subnets, route tables, NAT gateways, EIPs)
get a `Name` tag that follows the same pattern.

## 5. Tags

| Key | Value |
| --- | --- |
| `project` | Project name; placeholder `project` |
| `env` | `dev` |
| `service` | The resource-type token used in the resource's name, for example `role` or `subnet` |
| `managed` | How the resource was built: `terraform`, `cloudformation` or `hands-on` (manual). Everything in this repository uses `terraform` |
| `Name` | The resource name, used by the AWS console |

- Tag keys are case-sensitive; use exactly these lowercase keys and `Name`.
- Each root sets `project`, `env` and `managed` through provider `default_tags`.
  Modules set `service` and `Name` on each resource, because those differ per resource.
- Resources that `default_tags` does not reach, such as EC2 instances and volumes
  launched by EKS managed node groups, get the tags through launch template tag
  specifications; the root passes its default tags to the module for this. Instances
  launched by one Auto Scaling group share one `Name`, for example
  `project-dev-ec2-eks-node`.
- Log groups take the token in their path as `service`, for example `eks` for
  `/aws/eks/project-dev-eks/cluster`.
- These keys replace the previous `Environment`, `Service`, `Project` and `ManagedBy`.
- IAM policies that restrict tag keys at resource creation (`iam_access`,
  `iam_account_policies`) must allow exactly these keys.

## 6. Root granularity

Roots may be split further where real projects would: separate lifecycles,
ownership or blast radius, so that independently buildable parts can be applied
first instead of waiting for a whole design to settle. Each split keeps one State
per root under `infra/services/<env>/<region>/<service>/`. Concrete splits are
proposed in the consistency audit. Example: a Lambda function needs its package in
the artifact bucket before it can be created (finding F2), so the bucket can live in
a root that is built first.

## 7. Target portfolio scope (Owner, 2026-11-16)

The finished DEV portfolio should present a realistic project configuration that a
recruiter can evaluate. Target services:

VPC, SQS, SNS, Lambda, EC2, EKS, RDS, S3, IAM, Secrets Manager, KMS (AWS managed
keys only), Route 53, ACM, API Gateway, GitHub Actions, Terraform, Ansible, Packer,
load balancers, WAF, CloudFront, Cognito, EventBridge, CloudWatch, Inspector,
GuardDuty, Shield and CloudTrail.

Shield Standard is automatic and free. Terraform resources exist only for the paid
Shield Advanced, so Shield is documented rather than provisioned. The Kubernetes
runtime is in scope at a minimal development level.

## 8. Step plan

| Step | Work | Executor |
| --- | --- | --- |
| 1 | Make the existing DEV roots and the minimal Kubernetes runtime deploy-ready, without new features except those needed to deploy | Claude Code |
| 2 | Emulator rehearsals of the real modules, then an end-to-end apply and destroy; each run needs Owner authorization | Claude Code |
| 3 | Add the remaining target services | Codex, after a handover document |
| 4 | Core acceptance audit | Independent reviewer and Owner |

Step 1 items, each as its own pull request that stops for review and Owner merge
approval. The Owner may reorder them.

1. These rules and the repository guard (this document).
2. Naming and tag alignment and a consistency audit of the existing code, delivered
   as 2a rules (this document), 2b network, 2c platform, 2d api and serverless-api,
   2e the audit report. 2d starts with the IAM tag-key policies, pulled forward from
   2e because the secret's `project` tag is their ABAC key (2d-1 authorization tag
   keys, 2d-2 serverless-api, 2d-3 api). Root splits may be included where
   section 6 applies. Delivered: 2a–2d in PRs #57–#62; the
   [audit report](step1-audit-report.md) (2e) lists the open findings, their owning
   items and the Owner decisions they need.
3. Per-root placeholder `terraform.tfvars`, `local.auto.tfvars.example`, a local
   workflow with preflight checks and CI validation using the committed values.
   Delivered, together with audit findings F1, F12 and F14.
4. DEV state bucket bootstrap root and the optional S3 backend override.
   Delivered: the `tfstate` root, the `tfstate_bucket` module, per-root backend
   examples and `run.py migrate-state`.
5. SSM developer-access EC2: local workstation → Session Manager port forwarding →
   private EKS endpoint (443), and later private RDS (5432). No SSH and no public IP.
6. Cross-root hand-off automation and the local apply/destroy runbook, including
   the Kubernetes runtime through the developer-access tunnel.

V7-B/C/D, NP-2B/NP-3 and other new features stay paused until Steps 1 and 2 are
complete.

## 9. Step 1 operational decisions (Owner, 2026-11-16)

| Topic | Decision |
| --- | --- |
| Lambda package (finding F2) | The function package is committed as a ZIP file, together with its source, in a folder inside the Lambda root, so the repository visibly contains a deployable function. The local workflow uploads that ZIP to the artifact bucket before the function is created. Starting point: the Owner's minimal handler, which returns HTTP 200 `ok` |
| Kubernetes certificates (finding F4) | A local script creates DEV certificates and registers them directly in the cluster. Nothing goes into the repository or Terraform State. The current mTLS design stays |
| Secrets Manager values and recovery (finding F5) | Terraform creates metadata only, with no value or dummy; operators register values manually. Recovery window 7 days. Rebuilding inside the window means restoring the secret and importing it into Terraform |
| Deployment permissions and EKS bootstrap admin role (finding F6) | Prepared as prerequisites before deployment and documented in the runbook. A root that creates them is deferred to Step 3 or later |
