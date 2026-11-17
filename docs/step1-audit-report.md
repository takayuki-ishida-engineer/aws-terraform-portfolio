# Step 1 consistency audit report (item 2e)

This report closes Step 1 item 2 of the [step plan](deployment-configuration.md#8-step-plan).
It records the consistency audit of the existing DEV roots, what items 2a–2d
resolved, and what remains open with its owning item or the Owner decision it needs.

- **Baseline:** `main` at `839803c` (after PR #62), 2026-11-17 (Asia/Tokyo).
- **Method:** source inspection plus the offline verification run for each PR
  (Terraform 1.17.0, AWS provider 6.72.0 mocks, the repository checkers and Full CI).
- **Not used:** no AWS account, credentials, real Terraform plan or Emulator run.
  Nothing here is evidence of a real deployment.
- **Status updates:** the Status columns below are kept current as later Step 1
  items resolve findings (item 3: F1, F12, F14; new finding F16).

## 1. Delivered in item 2

| PR | Scope |
| --- | --- |
| [#56](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/56) | Rules for values, state and local-only deployment; tracked-files guard |
| [#57](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/57) | 2a: naming, tag and Step 1 operational decisions |
| [#58](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/58) | 2b: network root and `vpc` module |
| [#59](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/59) | 2c: platform root, `eks_platform`, `private_ingress` |
| [#60](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/60) | 2d-1: authorization tag keys (`secrets_manager`, IAM ABAC, offline policy toolkit) |
| [#61](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/61) | 2d-2: serverless-api root, its four modules and the committed Lambda package |
| [#62](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/62) | 2d-3: api root, `cognito_auth`, `api_gateway_rest` |

All four DEV roots now take a single `project` input, derive every name from
`<project>-dev`, set only `project`, `env` and `managed` through provider
`default_tags`, reject those keys and `Name`/`service` in caller `tags`, and leave
`Name` and `service` to the modules.

## 2. Findings from the original audit

| ID | Finding | Status | Owner |
| --- | --- | --- | --- |
| F1 | Required input values exist nowhere, so no root can be planned as is | **Resolved** in item 3: committed placeholder `terraform.tfvars` and `local.auto.tfvars.example` per root, the local workflow preflight, and Full CI mock plans with the committed values | — |
| F2 | serverless-api cannot be applied the first time: Lambda needs a ZIP in a bucket the same root creates | **Partly resolved** in #61: the handler, a reproducible build and `function.zip` are committed and drift-checked. The upload-then-apply sequence is still open; since item 3 the preflight refuses a placeholder `artifact_object_version` | Item 6 |
| F3 | The private EKS endpoint is unreachable from a workstation | Open | Item 5 (SSM developer-access EC2) |
| F4 | The Kubernetes runtime needs certificates and keys with no tooling | Open; approach decided (§9: local script, nothing in Git or State) | Item 6 |
| F5 | Destroy and immediate rebuild fails while a deleted secret is in its recovery window | Open; approach decided (§9: 7-day window, restore and import procedure). The 7-day window is set since item 3 (F12); the restore and import procedure is open | Item 6 |
| F6 | `iam_access` and `iam_account_policies` are used by no root; operator permissions and the EKS bootstrap admin role are undefined | Open; approach decided (§9: documented prerequisites, a root deferred to Step 3) | Item 6 (runbook) |
| F7 | Names and tags differed per root; `aws-terraform-portfolio` was hard-coded and too long for load balancer names and invalid in Cognito domains | **Resolved** in #57–#62 | — |

## 3. New findings

| ID | Finding | Evidence | Recommendation | Owner |
| --- | --- | --- | --- | --- |
| F8 | In `per_az` routing the shared private route table `<prefix>-rtb-private` is still created but has no association | `infra/modules/vpc/main.tf` (`aws_route_table.private` has no `count`; per-AZ subnets use `private_by_az`) | Create it only in shared mode. Harmless and free today, but it misleads operators. Nothing is deployed, so no state move is needed | **Owner decision**, then a small PR |
| F9 | The standalone `cloudwatch_logs` module is used by no root and still passes caller tags through without `Name`/`service` | `git grep 'modules/cloudwatch_logs"' infra/services` finds nothing; `lambda_workload` and `api_gateway_http` own their log groups | Align it when a root first uses it, or retire it; keep its tests until then | **Owner decision** |
| F10 | IAM Identity Center names do not follow the naming rule: permission sets `Portfolio-Access-Admin`, `Portfolio-Developer`, `Portfolio-Operator` and the managed policy `Portfolio-Developer-SecretsManager`; no `service` tag | `infra/modules/iam_access/main.tf`, `infra/modules/iam_account_policies/policies.tf` | Permission sets are organization-level, not per environment. Decide the organization-level pattern (for example `<project>-<purpose>`) together with F6's root in Step 3 | Step 3 (with F6) |
| F11 | Kubernetes object names do not follow `<project>-<purpose>`: `portfolio-app`, `portfolio-application`, `portfolio-binding-writer` | `kubernetes/` manifests | Rename with the runtime hand-off; keep upstream-mandated names (`istio-system`, `aws-load-balancer-controller`, …) | Item 6 |
| F12 | The secret's recovery window is still the module default of 30 days, not the decided 7 days | `secrets_manager` default `recovery_window_in_days = 30`; the serverless-api root does not set it and its checker expects 30 | Set `recovery_window_in_days = 7` in the root (Root Override) and update the root checker | **Resolved** in item 3 |
| F13 | Aggregate test totals quoted in older READMEs and docs are stale and inconsistent (641, 678, 686 native) | `README.md`, `docs/architecture-v2.md`, `docs/portfolio-verification-policy.md`, `docs/repository-structure-strategy.md`, `kubernetes/README.md`, module READMEs | Replace current-state totals with a pointer to the Full CI summary step; keep historical records as history | Docs cleanup PR (**Owner decision** on timing) |
| F14 | The api root repeats `"dev"` in both `expected_scope` blocks instead of using `local.environment` | `infra/services/dev/ca-central-1/api/main.tf` | Use `local.environment`; behaviour is unchanged | **Resolved** in item 3 |
| F15 | Full CI runs 17–23 minutes against a 30-minute job timeout; one `main` push run was cancelled at the limit on a slow runner | Run [43988955998](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43988955998) cancelled at 30 min after steps 1–29 passed; later runs 17–23 min | Raise `timeout-minutes` (for example to 45) or split the job; never reduce coverage. A Full CI change | **Owner decision**, then a separate PR |
| F16 | EKS nodes cannot reach ECR, S3 or STS: the node security group allows HTTPS only to `node_https_egress_cidrs`, which rejects `0.0.0.0/0`, and the network root creates no interface endpoints. With the committed in-VPC value `10.40.0.0/16`, image pulls for the managed add-ons fail, so nodes would not become Ready | `infra/services/dev/ca-central-1/platform/variables.tf` (`node_https_egress_cidrs` validation), `infra/modules/eks_platform` node egress rules, no `aws_vpc_endpoint` of type Interface in `infra/modules/vpc` | Add interface endpoints (`ecr.api`, `ecr.dkr`, `sts`, `logs`, `ec2`) in the network root, enable the existing S3 gateway endpoint (omitted in the committed values) and add a node egress rule to the S3 managed prefix list, keeping all egress inside the VPC; alternatively allow reviewed AWS IP ranges, which change over time | **Owner decision**, then a PR before Step 2 |

## 4. Confirmed consistent

- Terraform `~> 1.17.0` and AWS provider `~> 6.72.0` with the same committed lock in every root.
- The network outputs contain every field the platform root requires.
- EKS waits for its log group; KMS uses AWS managed keys unless a customer key is explicitly selected.
- Names, tags and reserved-key guards are uniform across the four DEV roots.
- The IAM ABAC tag keys, the secret's module-owned `project` tag, the equivalence
  baseline projection and the offline policy toolkit agree.
- No state, plan, `local.auto.tfvars`, `*.tfbackend` or `backend_override.tf` is
  tracked (repository guard in Full CI).
- The committed Lambda ZIP equals a reproducible rebuild of its source.

## 5. Residual risks that cannot be verified offline

- EKS version and add-on version compatibility. Item 3 selects Kubernetes 1.35 (standard support until 2027-03-27), the latest Amazon EKS add-on versions listed for 1.35 in the EKS User Guide source (`awsdocs/amazon-eks-user-guide`, read 2026-11-17) and node AMI release `1.35.9-20261112` (`awslabs/amazon-eks-ami` v20261112). The rendered AWS documentation site could not be reached from this environment; the live preflight re-checks every value against the account's EKS catalog before an apply.
- Collisions of globally unique names: S3 bucket `<project>-dev-s3-artifact` and
  Cognito domain prefix `<project>-dev-auth`. The placeholder `project` will collide
  and must be replaced before a real deployment.
- Root-to-root value hand-off is manual until item 6.
- How much of each service the official AWS Emulator implements is unknown until the Step 2 rehearsals (unimplemented APIs are recorded as PARTIAL-SKIP).

## 6. Decisions requested from the Owner

| ID | Question | Recommendation |
| --- | --- | --- |
| F8 | Create the shared private route table only in shared routing mode? | Yes, in a small PR before Step 2 |
| F9 | Align `cloudwatch_logs` with the tag rule now, or when a root first uses it? | When a root first uses it |
| F13 | Clean up stale aggregate totals now? | Yes, docs-only PR before the Codex handover |
| F15 | Raise the Full CI timeout or split the job? | Raise to 45 minutes first; split only if runtime keeps growing |
| F16 | Give nodes AWS service reachability through interface endpoints or reviewed IP ranges? | Interface endpoints in the network root, in a small PR before Step 2 |

Everything else is owned by Step 1 items 3–6 or Step 3 as listed above.
