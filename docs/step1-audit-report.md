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
  items resolve findings (item 3: F1, F12, F14; new finding F16. Item 4: new finding
  F17 and the Owner decisions of 2026-11-17 in section 6. 2026-11-18: F8, F9, F13,
  F15 and F16 resolved. Item 5: F3 resolved. Item 6a: F2, F5 and F19 resolved,
  F6 documented; new finding F18. Item 6b-A, 2026-11-20: F4 and F11 resolved; F18
  stays open. Item 6b-B2, 2026-11-20: F18 method decided and the images pinned by
  digest; F18 stays open until the registry root, the mirror script and Live
  verification; new improvement candidate F20. Item 6b-B1: the registry root and
  `ecr_repository` module, code only. Item 6b-B3: the image mirror script, code only.
  2026-11-21: new finding F21, resolved in code by the Elastic Load Balancing
  interface endpoint. Item 6c-A, 2026-11-22: the runtime input builder and the
  offline staged plan, code only. Item 6c-B1: the read-only runtime status and its
  preflight safety gate, code only. Item 6c-B2: the apply and destroy design record
  and new findings F22 and F23, documentation only. Item 6c-B3a: the receipt,
  journal, crash reconciliation and transport contract, code only; F22 and F23 stay
  open. Item 6c-B3b-C1: F23 resolved in code (renderer contract 5, Owner decision
  D23), Live NOT_VERIFIED; F22 stays open. Item 6c-B3b-Apply-A: the fake-only apply
  engine for the namespaces and base stages, code only. Item 6c-B3b-Apply-B1: the
  same engine for the controller and istiod stages, code only. Item 6c-B3b-Apply-B2:
  the gateway stage behind its pre-apply gate, which stops every run today
  (base validator serving unverified), code only. Item 6c-B3b-Apply-B3: the
  mesh_security stage behind the same gate, code only. Item 6c-B3b-Apply-B4: the
  admission stage behind the same stop, code only. Item 6c-B3b-Apply-B5: the
  binding_writer stage behind the same stop, D1 items NOT_TESTED, code only. G9 and
  D19 (Owner decision, 2026-11-24): F22 resolved in Source/Offline code (the
  registration UID receipt, the metadata-only cleanup with UID-precondition DELETE
  through the Fake-only D19 transport, and the retired name-based `delete`); real
  Secret cleanup stays NOT_TESTED and namespace deletion stays BLOCKED. 6c-B4a
  (Owner decisions D3, D5, D6, D11, D12 and D19, 2026-11-24): the Fake-only destroy
  transport, discovery, LIST and receipt/journal destroy-state foundation, code only,
  merged as PR #100. 6c-B4b (Owner authorization 2026-11-24): the Fake-only destroy
  engine, Source/Offline only, merged as PR #101 (Full CI NOT RUN under a one-time
  Owner exception); the real `destroy` command, real transport, target deregistration
  and namespace cascade on a real API server stay NOT_TESTED or NOT_VERIFIED. 6c-B5
  (Owner instruction 2026-11-24): the Source/Offline final audit of item 6c in
  [section 7](#7-item-6c-sourceoffline-final-audit-6c-b5), merged as PR #102 with
  Full CI; it declares no completion. 2026-11-24: the Owner approved OD-01 to OD-13,
  closing Step 1 (SOURCE / OFFLINE COMPLETE) and Step 2 (limited Emulator evidence);
  see [section 7.14](#714-subsequent-owner-decisions-and-policy-release-post-audit)).

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
| F2 | serverless-api cannot be applied the first time: Lambda needs a ZIP in a bucket the same root creates | **Resolved**: #61 committed the handler and `function.zip`; item 6a adds `run.py serverless-api publish-artifact` (confirmed targeted bucket plan, upload, version recorded) | — |
| F3 | The private EKS endpoint is unreachable from a workstation | **Resolved** in item 5: the `developer-access` root (Session Manager only, no SSH or public IP) and the network root's `ssm`, `ssmmessages`, `ec2messages` endpoints; port forwarding to the private endpoint is documented. Connectivity is verified only on a real deployment | — |
| F4 | The Kubernetes runtime needs certificates and keys with no tooling | **Resolved** in item 6b-A: [`k8s_certs.py`](../scripts/local-workflow/README.md#kubernetes-certificates-k8s_certspy) `generate` creates the Istio plug-in CA, the gateway server and client certificates and the webhook certificate with OpenSSL 3 outside the repository (0700/0600, root and issuing CA keys deleted after signing, at most 90 days). `register` first checks the material against `public.json` (hostname and SANs, validity, Secret layout, keys and chains) and the kubectl context against the applied platform output (loopback tunnel, the cluster's CA and endpoint host, `get-token` for that cluster), then applies the four Secrets with `kubectl apply --server-side` through stdin, from the workstation only, and deletes the server keys locally. Nothing enters Git, Terraform or CI logs. Offline tests with real OpenSSL and a fake `kubectl` run in Full CI. Registration against a real cluster is not yet exercised (F18 blocks the runtime) | — |
| F5 | Destroy and immediate rebuild fails while a deleted secret is in its recovery window | **Resolved**: 7-day window since item 3 (F12); the restore and import procedure is in the [runbook](dev-runbook.md#7-teardown) (item 6a) | — |
| F6 | `iam_access` and `iam_account_policies` are used by no root; operator permissions and the EKS bootstrap admin role are undefined | **Documented** in the [runbook](dev-runbook.md#0-prerequisites) (item 6a): operator permissions by service and the pre-existing bootstrap admin role. A least-privilege operator root stays deferred to Step 3 (with F10) | Step 3 |
| F7 | Names and tags differed per root; `aws-terraform-portfolio` was hard-coded and too long for load balancer names and invalid in Cognito domains | **Resolved** in #57–#62 | — |

## 3. New findings

| ID | Finding | Evidence | Recommendation | Owner |
| --- | --- | --- | --- | --- |
| F8 | In `per_az` routing the shared private route table `<prefix>-rtb-private` is still created but has no association | `infra/modules/vpc/main.tf` (`aws_route_table.private` has no `count`; per-AZ subnets use `private_by_az`) | Create it only in shared mode. Harmless and free today, but it misleads operators. Nothing is deployed, so no state move is needed | **Resolved** 2026-11-18: `count = local.per_az ? 0 : 1` with a `moved` block to `aws_route_table.private[0]`; the legacy tests changed only that address (pinned hash re-baselined) |
| F9 | The standalone `cloudwatch_logs` module is used by no root and still passes caller tags through without `Name`/`service` | `git grep 'modules/cloudwatch_logs"' infra/services` finds nothing; `lambda_workload` and `api_gateway_http` own their log groups | Align it when a root first uses it, or retire it; keep its tests until then | **Resolved** on the Owner's instruction of 2026-11-18: module-owned `Name` (log group name, `#` replaced) and `service` (new required input) tags; caller `Name`/`service` rejected; tests and CI counts updated |
| F10 | IAM Identity Center names do not follow the naming rule: permission sets `Portfolio-Access-Admin`, `Portfolio-Developer`, `Portfolio-Operator` and the managed policy `Portfolio-Developer-SecretsManager`; no `service` tag | `infra/modules/iam_access/main.tf`, `infra/modules/iam_account_policies/policies.tf` | Permission sets are organization-level, not per environment. Decide the organization-level pattern (for example `<project>-<purpose>`) together with F6's root in Step 3 | Step 3 (with F6) |
| F11 | Kubernetes object names do not follow `<project>-<purpose>`: `portfolio-app`, `portfolio-application`, `portfolio-binding-writer` | `kubernetes/` manifests | Rename with the runtime hand-off; keep upstream-mandated names (`istio-system`, `aws-load-balancer-controller`, …) | **Resolved** in item 6b-A: a required `runtime.project` input (renderer input version 2, evidence contract 3) names all 22 project-created objects `<project>-<purpose>`, including `<project>-ingress` and revision `<project>-v1`, and must match the platform's `<project>-dev-eks` cluster and `<project>-dev-role-lbc` role. Upstream names stay. Independent naming check, 11 new rendered mutations and 16 new input negatives; [mapping](../kubernetes/README.md#step-1-item-6b-a-project-derived-names-and-dev-certificates) |
| F12 | The secret's recovery window is still the module default of 30 days, not the decided 7 days | `secrets_manager` default `recovery_window_in_days = 30`; the serverless-api root does not set it and its checker expects 30 | Set `recovery_window_in_days = 7` in the root (Root Override) and update the root checker | **Resolved** in item 3 |
| F13 | Aggregate test totals quoted in older READMEs and docs are stale and inconsistent (641, 678, 686 native) | `README.md`, `docs/architecture-v2.md`, `docs/portfolio-verification-policy.md`, `docs/repository-structure-strategy.md`, `kubernetes/README.md`, module READMEs | Replace current-state totals with a pointer to the Full CI summary step; keep historical records as history | **Resolved** 2026-11-18: present-tense "expected full CI" totals now point to the Full CI job summary; totals tied to a named CI run stay as dated history |
| F14 | The api root repeats `"dev"` in both `expected_scope` blocks instead of using `local.environment` | `infra/services/dev/ca-central-1/api/main.tf` | Use `local.environment`; behaviour is unchanged | **Resolved** in item 3 |
| F15 | Full CI runs 17–23 minutes against a 30-minute job timeout; one `main` push run was cancelled at the limit on a slow runner | Run [43988955998](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43988955998) cancelled at 30 min after steps 1–29 passed; later runs 17–23 min | Raise `timeout-minutes` (for example to 45) or split the job; never reduce coverage. A Full CI change | **Resolved** 2026-11-18: job timeout raised to 45 minutes (the PR #65 run took 27 minutes); no step removed. 2026-11-23: raised to 60 minutes (Owner approval, PR #95) after run 45225177432 was cancelled at 45 minutes on a slow runner; no step, test or mutation removed |
| F16 | EKS nodes cannot reach ECR, S3 or STS: the node security group allows HTTPS only to `node_https_egress_cidrs`, which rejects `0.0.0.0/0`, and the network root creates no interface endpoints. With the committed in-VPC value `10.40.0.0/16`, image pulls for the managed add-ons fail, so nodes would not become Ready | `infra/services/dev/ca-central-1/platform/variables.tf` (`node_https_egress_cidrs` validation), `infra/modules/eks_platform` node egress rules, no `aws_vpc_endpoint` of type Interface in `infra/modules/vpc` | Add interface endpoints (`ecr.api`, `ecr.dkr`, `sts`, `logs`, `ec2`) in the network root, enable the existing S3 gateway endpoint (omitted in the committed values) and add a node egress rule to the S3 managed prefix list, keeping all egress inside the VPC; alternatively allow reviewed AWS IP ranges, which change over time | **Resolved** 2026-11-18: `vpc` module `interface_endpoints` (ec2, ecr.api, ecr.dkr, logs, sts in `private1`, private DNS, VPC-CIDR-only HTTPS security group) and an EKS node egress rule to the S3 managed prefix list `pl-7da54014`, verified by the live preflight. The S3 gateway endpoint stays off: ECR layer downloads use presigned URLs that the module's mandatory role-ARN policy condition would deny, so S3 traffic goes through the NAT gateway. Residual: other runtime images or AWS APIs the Kubernetes runtime needs are reviewed in item 6 |
| F17 | The Claude Code cloud session that works on this repository exposes `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to shell commands, both with the placeholder value `proxy-injected`. They are not real credentials and are not stored in the cloud environment's settings (no environment variables, network secrets or setup script); the session runtime injects them for its egress proxy, which has no AWS secret to substitute. An AWS SDK or CLI started there would still try to sign requests with them, and a network secret for an AWS host added later would turn them into working credentials, which AGENTS.md forbids | Found 2026-11-17 while running the item 3 checks (values compared without printing them). All Terraform tests use mock providers, which never authenticate, and no root configures provider credentials. The required-input checkers, the committed-values check and the tfstate root checker also start Terraform with `AWS_*` removed; older module checkers do not, which is harmless under mocks | **Mitigated** in item 4: the local workflow refuses live checks, `run.py` and `migrate-state` in CI, in Claude Code or Codex cloud sessions and whenever an AWS credential variable holds `proxy-injected`. Keep the cloud environment free of AWS network secrets and variables | Done; nothing to remove from the environment settings |
| F18 | The Kubernetes runtime images (Istio 1.32, AWS Load Balancer Controller 3.6.2) come from public registries, but node egress is limited to the VPC and the S3 prefix list (F16), so the nodes cannot pull them | `kubernetes/vendor` charts; F16 node egress | ECR pull-through cache rules (ECR Public, Quay) or mirrored images in a private ECR repository, referenced by the Helm values; keep node egress closed. Allowing HTTPS to the internet would undo F16 | **Open, in progress**. Owner decision 2026-11-20: a private ECR mirror in the DEV account, filled with `skopeo copy --all --preserve-digests` (all platforms, `linux/amd64` required), with no pull-through cache. A changed upstream tag, a digest mismatch or an unsupported manifest type stops the copy. Node egress stays closed, and node IAM and admission are unchanged. B2 delivered the [image lock](../kubernetes/images.lock.json) with the raw upstream index manifests, and the renderer and validator now pin the three images to `<account>.dkr.ecr.ca-central-1.amazonaws.com/<project>-dev-ecr-<purpose>@<digest>` and remove the unused injection templates (see the [Kubernetes README](../kubernetes/README.md#step-1-item-6b-b2-digest-pinned-private-images-f18)). B1 delivered the [`registry` root](../infra/services/dev/ca-central-1/registry/README.md) and the `ecr_repository` module: one private repository per locked purpose (immutable tags, AES-256, `force_delete = false` except through the teardown switch, no repository or lifecycle policy), as code only. B3 delivered [`mirror_images.py`](../scripts/local-workflow/README.md#image-mirror-mirror_imagespy), as code only: an offline plan by default, and a workstation-only `mirror` that copies by the locked digest and verifies the index bytes, platforms and child manifests in ECR afterwards, never creating or deleting a repository or image. Pending: Live verification of the repositories, of the mirror and of the pull through the ECR endpoints and S3 over NAT (NOT_TESTED). Residual: `skopeo copy` does not copy OCI referrers (signatures, SBOMs, attestations) |
| F20 | No admission control restricts Pod images. A Pod may name any image, an injection template the renderer removed, or a `sidecar.istio.io/proxyImage` annotation. Only the closed node egress keeps such a pull from succeeding | Offline validation covers the rendered bundle only (F18, item 6b-B2); a real cluster accepts other Pods | An image allowlist ValidatingAdmissionPolicy, scoped to the runtime namespaces, that admits only the locked private references and refuses the proxy image annotation | **Security improvement candidate** (Owner, 2026-11-20): separate from F18, not implemented |
| F19 | Teardown could not finish with `terraform destroy`: Cognito deletion protection was fixed to `ACTIVE` in the module and the serverless-api log groups' deletion protection had no root switch | `cognito_auth` `deletion_protection = "ACTIVE"`; `lambda_workload`/`api_gateway_http` log protection Module Default only | Root switches that default to protected and are turned off as the first teardown step | **Resolved** in item 6a: `cognito_auth.deletion_protection` (default `ACTIVE`), api root `deletion_protection`, serverless-api root `log_deletion_protection`; tests and runbook |
| F21 | The AWS Load Balancer Controller has no network path to the Elastic Load Balancing (ELBv2) API. Terraform (`private_ingress` in the platform root) creates and manages the NLB, its listener and the target group. The controller does not create them: through TargetGroupBinding it registers and deregisters Pod IPs in that existing target group and calls the Describe APIs it needs. Its pods run on the nodes, whose HTTPS egress is limited to the VPC CIDR and the S3 managed prefix list (F16), and the network root had no `elasticloadbalancing` interface endpoint, so TargetGroupBinding reconciliation may fail | Found 2026-11-21 in the item 6c design review. `infra/modules/vpc/variables.tf` (`interface_endpoints.services` allowlist without `elasticloadbalancing`), the committed network values (eight services), `infra/modules/eks_platform` node egress rules; `infra/modules/private_ingress` owns the NLB, listener and target group (its README's Kubernetes ownership boundary) | Provide the path as IaC: add `elasticloadbalancing` to the reviewed allowlist and to the DEV network values, with private DNS and the existing endpoint security group. Keep node egress, IAM, the endpoint policy, NAT and the S3 gateway endpoint unchanged; do not open node egress to the internet. The ownership stays as it is: the controller must not modify the Terraform-owned NLB, listener, target group attributes or security group rules | **Resolved in code** 2026-11-21 (Owner-approved scope): the endpoint provides the path as IaC; the actual communication is NOT_TESTED. `aws_vpc_endpoint.interface["elasticloadbalancing"]` (`com.amazonaws.ca-central-1.elasticloadbalancing`) in `private1`, private DNS, the existing `<project>-dev-sg-vpce` group (TCP 443 from the VPC CIDR only), the AWS default endpoint policy, Name `<project>-dev-vpce-elasticloadbalancing`. A mock plan of the committed values (`network/tests/committed.tftest.hcl`) verifies all nine endpoints. The Terraform endpoint is not proof of ELB API connectivity: the controller's target registration, deregistration and Describe calls through it are Live NOT_TESTED and Emulator NOT_TESTED (the formal `network` scenario has no interface endpoints). Residual: the `network-full` harness still lists only the eight earlier services, so a dispatch would stop at plan inspection until a separately reviewed harness change; other AWS APIs the controller may call are reviewed in item 6c; one more endpoint-hour plus per GB from the network apply until destroy |
| F22 | `k8s_certs.py delete` deletes the four Secrets by name with `--ignore-not-found`. It has no UID precondition, no ownership check and no absence check afterwards. A same-named Secret created by someone else would be deleted, and deleting a namespace would delete its Secrets without any of these checks | Found 2026-11-22 in the item 6c-B2 design review (G9). `scripts/local-workflow/k8s_certs.py` `delete` | Add a safe cleanup:<br>• metadata-only read;<br>• the label and `<project>-k8s-certs` manager check;<br>• a UID recorded at registration;<br>• deletion with a UID precondition (decision D19);<br>• confirmed absence.<br>Recommended as its own pull request before 6c-B4. Until then:<br>• the runtime destroy must not use the current `delete`;<br>• namespace deletion is BLOCKED;<br>• deleting a namespace that still holds a Secret needs a separate Owner approval | **Resolved in Source/Offline code (G9, Owner decision 2026-11-24)**: `k8s_certs_receipt.py` records the registration UID receipt and cleans up each Secret only after the receipt, fingerprint, label, manager and UID checks, with a UID-precondition DELETE and confirmed NotFound, through the Fake-only D19 transport; `k8s_certs.py delete` refuses on every path. Real transport, real DELETE and a real cleanup stay NOT_TESTED. A real namespace deletion stays BLOCKED (the real `destroy` and the real transport refuse). The Fake-only 6c-B4b engine (PR #101) deletes a namespace only under D3, D6, D18 and the Fake-only atomic namespace gate ([section 7.5](#75-f06-r-fake-only-atomic-namespace-safety-pr-101)). D18 stays in force: never while a Secret remains. See the [design record](k8s-runtime-apply-destroy-design.md#g9-safe-secret-cleanup-finding-f22) |
| F23 | Istio webhook `caBundle` ownership. The three Istio webhooks (`istiod-default-validator`, `istio-validator-<project>-v1-istio-system`, `istio-sidecar-injector-<project>-v1`) must never carry a `caBundle` in the bundle, because istiod writes it at run time and a runtime server-side apply would otherwise own or conflict with it on fail-closed webhooks. Correction (6c-B3b-C1): the pinned charts already omit the field, because they render it only for a non-empty value; the original finding said the validators render `caBundle: ""`, which was wrong. The risk was latent (a changed value or chart default) | Found 2026-11-22 in the item 6c-B2 design review (C1). Vendored `base` and `istiod` 1.32.0 webhook templates (`{{- if .Values.base.validationCABundle }}`, `{{- if .caBundle }}`) | Pin the values empty, refuse any Istio webhook `caBundle` in the renderer and the validator, keep the controller webhook public CA, never force a conflict (decision D23, renderer contract 5) | **Resolved in code (Source/Offline)** 2026-11-22 in 6c-B3b-C1 (Owner decision D23): contract 5, renderer and validator guards, 10 semantic mutations, 3 renderer refusals and a contract-4 evidence fault. Live istiod field manager, CA rotation and webhook serving NOT_VERIFIED. The real `apply` stays BLOCKED (the command refuses); the Fake-only apply engine (6c-B3b-Apply-A to Apply-B5) implements the contract-5 handling against fakes only |

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
- Collisions of globally unique names: S3 buckets `<project>-dev-s3-artifact` and
  `<project>-dev-s3-tfstate` and Cognito domain prefix `<project>-dev-auth`. The
  placeholder `project` will collide and must be replaced before a real deployment.
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
| F18 | Source of the Kubernetes runtime images while node egress stays closed? | ECR pull-through cache for ECR Public and Quay plus a private ECR mirror where needed, in item 6b; no internet egress for nodes. Superseded on 2026-11-20 by the Owner's decision: a private ECR mirror only, no pull-through cache |

All five recommendations above were approved by the Owner on 2026-11-17. On
2026-11-18 the Owner asked for all five now: F9, F13 and F15 were delivered in one
pull request, F8 and F16 (network, VPC and EKS changes) in the next.

Everything else is owned by Step 1 items 3–6 or Step 3 as listed above.

## 7. Item 6c Source/Offline final audit (6c-B5)

> **Audit-time record.** Sections 7.1 to 7.13 are kept as written for the 6c-B5 audit
> (PR #102). Their policy references (v14.5) and "decided later" items reflect that
> time. The later Owner decisions, the PR #102 evidence and the MASTER_POLICY v14.6
> release are in [section 7.14](#714-subsequent-owner-decisions-and-policy-release-post-audit).

Owner instruction of 2026-11-24 (6c-B5). This section is the closure audit of the
Kubernetes runtime item 6c in Source/Offline terms. It declares neither Portfolio
Complete, Live Ready, Step 1 or 2 Complete nor a Codex handover. The Step 1/2 closure
decision and the handover are separate steps (Master Policy v14.5 §19.3).

- **Baseline:** `main` at `0ed2c1660463d9f88df9d63481059676ccadf357`, tree
  `7c6319b2fcd5201420f7ad8b7e7e3cc5dc3e0c3f` (after PR #101), 2026-11-24.
- **Method:** the merged source and tests, the [design record](k8s-runtime-apply-destroy-design.md),
  the [runbook](dev-runbook.md#7-teardown), the
  [local workflow README](../scripts/local-workflow/README.md) and the pull request and
  run metadata read through the GitHub API on 2026-11-24.
- **Not used:** no cluster, AWS account, credential, Terraform plan or apply, Emulator
  run or Full CI dispatch. The Master Policy PDF itself is not in the repository; this
  audit applies v14.5 as [AGENTS.md](../AGENTS.md) records it.

Vocabulary: **BLOCKED** means stopped by design or by a missing prerequisite.
**NOT_VERIFIED** means a precondition that no evidence source has proven, which fails
closed. **NOT_TESTED** means an operation never executed. **OPEN** means an Owner
decision not yet made. None of the three status words is a PASS. A design that exists
is never evidence that the behavior works.

### 7.1 Sub-items, pull requests and CI evidence

Each pull request below was merged with a squash commit. Before PR #97 (2026-11-23) the
CI policy ran Full CI (check `Credential-free Terraform validation`) on every pull
request. The run listed is the one on the pull request's final HEAD. Offline Contracts
(check `static-contracts`) succeeded on each final HEAD as well.

| Item | Pull request | Squash commit | CI on the final HEAD | Source/Offline result |
| --- | --- | --- | --- | --- |
| 6c-A input builder and offline plan | [#86](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/86) | `dc96e91` | Full CI 45009726291 success | Merged |
| 6c-B1 read-only status and preflight gate | [#87](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/87) | `c96ec9d` | Full CI 45019585732 success | Merged |
| 6c-B2 design record (docs) | [#88](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/88) | `ef6a35e` | Full CI 45030591141 success | Merged |
| 6c-B3a receipt, journal, recovery, transport boundary | [#89](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/89) | `eb79578` | Full CI 45048562368 success | Merged |
| 6c-B3b-C1 `caBundle` ownership, contract 5 (F23, D23) | [#90](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/90) | `30511b2` | Full CI 45054979298 success | Merged |
| Apply-A namespaces and base | [#91](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/91) | `8ef8dcd` | Full CI 45120874862 success | Merged |
| Apply-B1 controller and istiod | [#92](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/92) | `2539d7a` | Full CI 45150009319 success | Merged |
| Apply-B2 gateway behind its pre-apply gate | [#93](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/93) | `99a7a04` | Full CI 45172056362 success | Merged |
| Apply-B3 mesh_security | [#94](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/94) | `ba61741` | Full CI 45196405851 success | Merged |
| Apply-B4 admission | [#95](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/95) | `789e371` | Full CI 45241040553 success | Merged |
| Apply-B5 binding_writer | [#96](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/96) | `135dc96` | Full CI 45260835463 success | Merged |
| G9 and D19 Secret transport (F22) | [#99](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/99) | `403b5f1` | PR Safety CI 45354933988 success; Owner-dispatched Full CI 45358186407 success on `3b081f8` | Merged |
| 6c-B4a destroy safety foundation | [#100](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/100) | `060de91` | PR Safety CI 45396378485 success; Owner-dispatched Full CI 45398955069 success on `bcb196d` | Merged |
| 6c-B4b Fake-only destroy engine | [#101](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/101) | `0ed2c16` | PR Safety CI 45442264744 success and Offline Contracts 45442264960 success on `2a127c2`; **FULL CI NOT RUN** (historical one-time Owner exception); `merge_check.py` passed; `main` Offline Contracts 45446997899 success | Merged |

**Item 6c overall:** the planned Source/Offline pull requests 6c-A to 6c-B4b are merged
with the CI evidence above. The runtime itself is not deployable: real `apply` and
`destroy` stay BLOCKED (section 7.8). The Fake-only results below are never Live
evidence.

### 7.2 Audit by area

| Area | Source/Offline evidence | Not established |
| --- | --- | --- |
| Architecture and renderer | Renderer contract 5 (`CONTRACT_VERSION = 5`); the reviewed stage table [`expected-stages.json`](../kubernetes/tests/expected-stages.json): 9 stages and 62 objects (namespaces 2, base 16, controller 13, istiod 12, gateway 5, mesh_security 5, admission 4, binding_writer 3, ingress 2), 17 CRDs (15 Istio, 2 controller) and 45 non-CRD objects. Images pinned by upstream index digest to the private ECR mirror ([image lock](../kubernetes/images.lock.json), B2). C1 and D23: no Istio webhook `caBundle` in the bundle, enforced by the renderer and the validator. RBAC, admission policies and NetworkPolicies are rendered and checked by the offline validator. Terraform owns the NLB, listener, target group, IAM and endpoints; the runtime owns only the 62 objects | Live admission, RBAC, NetworkPolicy and webhook behavior; istiod's real `caBundle` writes and CA rotation |
| Runtime plan and status | `plan` renders with the pinned Helm and checks the required inputs and the reviewed stage identities (plan 29 tests, 39 mutations). `status` is read-only, checks the mandatory preconditions and the D17 fingerprint (cluster ARN plus `kube-system` UID), and fails closed on NOT_VERIFIED (status 21 tests, 32 mutations) | `status` on a real cluster |
| Apply and receipt | Receipt FORMAT 1: UID and field ownership (D7, D13), durable write-ahead INTENT and RESULT, crash recovery, QUARANTINE (no automatic release, D16) and stage completion; the Fake-only apply engine (apply 58 tests, 163 mutations; receipt suite section 7.10) | Any real apply; real managedFields; real field managers |
| G9 and destroy | G9: registration UID receipt for the four Secrets (`cacerts` in `istio-system`, `aws-load-balancer-controller-tls` in `kube-system`, `<project>-gateway-tls` and `<project>-gateway-client-cacert` in `<project>-ingress`), fingerprint binding, metadata-only cleanup with a UID-precondition DELETE through the Fake-only D19 transport, registration pinning under the cleanup lock. Destroy: discovery and metadata-only inventory (D3), the reverse teardown order with the TargetGroupBinding, admission and webhook dependency gates (D12), CRDs kept with ZERO_INSTANCES or CRD_NOT_CREATED (D5), namespace ownership and inventory classes (D6), D18, the Fake-only atomic namespace safety gate and the delayed-cascade recheck (section 7.5), the 3600 s deadline and local waits (D11), finalizer waits without stripping, and crash recovery | Real transport, real DELETE, real namespace cascade, garbage collection, finalizer removal and target deregistration (section 7.8) |

### 7.3 What the Fake apply actually reaches

| Stages | Objects | How far a Fake apply run gets |
| --- | --- | --- |
| namespaces, base, controller, istiod | 43 | Applied by the Fake engine in a run. A run through `istiod` ends with exit 6 `APPLIED_WITH_DEFERRED`: `base` final acceptance is `DEFERRED` (the istiod-default-validator serving) and runtime final acceptance is `NOT_REACHED`, never PASS |
| gateway, mesh_security, admission, binding_writer | 17 | Never reached by a run. Every run through them stops before any dry-run, INTENT or write at `deferred_readiness_unresolved:base_validator_serving`, because no fake can supply Live probe F (D20) or a confirmed istiod manager (D13). A rerun stops earlier at `ownership_not_verified`. Their stage contracts are tested directly behind the gate only |
| ingress | 2 | Refused: ingress is BLOCKED (D1, D14) |

### 7.4 Synthetic destroy evidence

The destroy tests cannot start from a Fake apply, because that apply stops before the
gateway. Their positive fixtures use synthetic ownership evidence (journal and
managedFields written by the test):
- **Full synthetic receipt:** 45 non-CRD objects deleted, the 4 Secrets cleaned through
  G9, the 17 CRDs ZERO_INSTANCES and retained, and the namespaces accepted through the
  Fake-only atomic gate. The result is a Fake COMPLETE.
- **Partial apply (`namespaces` and `base`):** 3 deleted, 42 never created, and the 2
  controller CRDs CRD_NOT_CREATED.

Neither fixture is an apply-to-destroy end-to-end result, and neither is evidence of a
real apply or destroy.

### 7.5 F06-R: Fake-only atomic namespace safety (PR #101)

On 2026-11-24 the Owner authorized, as a Fake-only addition within D6, D18 and D19:
- **Single-use evidence:** the destroy transport issues a single-use capability bound to
  the namespace and its UID, from its own complete inventory and validated Namespace
  metadata. The capability is consumed when the DELETE is attempted.
- **Atomic acceptance:** at DELETE acceptance the fake compares current ownership,
  discovery and all contents with that evidence.
- **Delayed cascade:** before the cascade runs, the accepted snapshot is checked again
  and unsafe changes are refused.
- **No bypass:** the generic metadata and G9 transport refuses a Namespace DELETE, and a
  raw send without the current capability and the exact request is refused.
- **No fallback:** without the capability there is no fallback to an ordinary Namespace
  DELETE and no real API option. A known conflict closes the INTENT `failed`; an unknown
  outcome keeps it open.
- **Difference from the real API:** Kubernetes has no equivalent atomic primitive. A
  namespace UID precondition does not freeze the namespace's contents. Real cascade
  atomicity is NOT_VERIFIED, and nothing here claims it.

Evidence, from the local verification of PR #101 (not a formal run):

| HEAD | Race: an object added between the last inventory and the DELETE | Outcome |
| --- | --- | --- |
| `9e9530d` (before F06-R) | Secret added after the final Secret LIST, or ConfigMap added just before DELETE acceptance | Fake COMPLETE, with the added objects deleted by the cascade: the unsafe behavior |
| `2a127c2` (merged) | The same two races | BLOCKED `namespace_atomic_conflict`; the namespace and the added objects are kept; the journal records only `failed` |

RC-1 (`2a127c2`) isolated four namespace scenarios:
- `scenario_namespace_runtime_object`: BLOCKED `runtime_object:istio-system:stray`;
- `scenario_namespace_certs_secret`: BLOCKED `k8s_certs_secret:istio-system:cacerts`, with
  no istio-system DELETE or INTENT;
- `scenario_namespace_d13`: BLOCKED `foreign_field:test-ingress`, with no INTENT;
- `scenario_namespace_cross_g9_atomic`: BLOCKED `delete:namespace_atomic_conflict:test-ingress`,
  with only `failed` recorded.

RC-2 ran each of three mutations (`certs_secret_blocks`, `namespace_d13`,
`runtime_object_class`) against its own scenario. Each baseline passed outside the
mutation handler, and each mutation was detected by an assertion, not by a crash.

### 7.6 F01–F07, RC-1 and RC-2 closure

| ID | Correction | Closed at | Status |
| --- | --- | --- | --- |
| F01 | The reviewed stage table is the only stage layout; contract version checked | `9e9530d` | Closed (Source/Offline) |
| F02 | `receipt.Store(existing_only=True)`: destroy never creates or repairs a receipt; locked revalidation | `9e9530d` | Closed (Source/Offline) |
| F03 | G9 registration and fingerprint binding; fingerprint checked again before every runtime DELETE; G9 pinning under its lock | `9e9530d`, residual `7d6c664` | Closed (Source/Offline) |
| F04 | No TargetGroupBinding anywhere (cluster-wide); fresh dependency evidence before each admission, controller, webhook and Deployment DELETE; exact admission binding absence | `9e9530d`, residual `7d6c664` | Closed (Source/Offline) |
| F05 | Discovery keeps every mapping and the `list` verb; CRDs judged by exact group, version, plural, kind and scope | `9e9530d`, residual `7d6c664` | Closed (Source/Offline) |
| F06 | Namespace final gate; F06-R atomic acceptance and delayed-cascade recheck (section 7.5) | `9e9530d`, `7d6c664` | Closed in the Fake; real atomicity NOT_VERIFIED |
| F07 | A terminating object resumes under its INTENT without a new DELETE; strict local wait deadlines; separated CRD counts | `9e9530d`, residual `7d6c664` | Closed (Source/Offline) |
| RC-1 | Namespace regressions isolated into four scenarios | `2a127c2` | Closed |
| RC-2 | Mutation baselines validated outside the detection handler | `2a127c2` | Closed |

`7d6c664` and `2a127c2` were written by ChatGPT and verified by Claude under the Owner's
one-time exception for PR #101. That exception ended with the merge. ChatGPT
independently confirmed the result "MERGED — 6c-B4b SOURCE / OFFLINE COMPLETE".

### 7.7 Decisions and findings

| Decision | Status | Implemented as |
| --- | --- | --- |
| D2 | Approved 2026-11-22 | Secrets metadata-only, NOT_VERIFIED fails closed; no full Secret read |
| D3 | Approved in parts (2026-11-22 fingerprint and apply reads; 2026-11-24 destroy discovery and metadata LIST) | Fake-only |
| D5, D6, D12 | Approved 2026-11-24 | Fake-only destroy engine |
| D7, D8, D10, D16, D17 | Approved 2026-11-22 | Receipt, journal and gate |
| D9 | Approved 2026-11-22, fakes only | Probe classification; Live use needs D20 |
| D11 | Approved (apply 2026-11-22, destroy 2026-11-24) | Fake clock |
| D13 | Approved as a Source/Offline allowlist | Live manager names unconfirmed; fails closed |
| D18 | Approved 2026-11-24 | No namespace DELETE while a Secret remains |
| D19 | Approved for the interface and fake, the four Secrets and the remaining destroy scope | Fake transport only; the real HTTPS client and token retrieval are not approved |
| D23 | Approved 2026-11-22 | Renderer contract 5 |
| D1, D4, D15, D20, D21, D22 | OPEN (Category 2, before any Live verification) | Not implemented |
| D14, D22 archive part | OPEN (Category 3) | Not implemented |

| Finding | Source/Offline status | Still unverified |
| --- | --- | --- |
| F18 | Open, in progress: registry root (B1), digest pins (B2), mirror script (B3) as code | Repositories, mirror and image pull: Live NOT_TESTED; OCI referrers not copied |
| F20 | Improvement candidate, not implemented | — |
| F21 | Resolved in code (ELBv2 interface endpoint) | ELBv2 connectivity, registration and deregistration: Live NOT_TESTED, Emulator NOT_TESTED; `network-full` harness lists eight services |
| F22 | Resolved in Source/Offline code (G9) | Real Secret cleanup NOT_TESTED |
| F23 | Resolved in code (contract 5) | istiod field manager, CA rotation, webhook serving NOT_VERIFIED |

Every other finding keeps its status in sections 2 and 3. F19 (teardown deletion
protection) stays Resolved in item 6a.

### 7.8 Remaining risk register

Every item below is outside the current scope under v14.5 §15 (Live) or is a paused
feature, so none is a Core completion condition. Each must still be listed as unverified
scope at acceptance. Opening any of them needs a new Owner decision; for Live items that
means a new cost and execution decision and independent review.

| ID | Function | State | Source/Offline evidence | Not established | Stop condition today | Prerequisite for future verification |
| --- | --- | --- | --- | --- | --- | --- |
| Real apply and destroy | `k8s_runtime.py apply` / `destroy` | BLOCKED | Fake engines | Any real run | Both commands refuse | Real transport, D1 and D20 decisions, Live scope |
| Real transport and authentication | D19 HTTPS client, token | BLOCKED (not implemented) | Interface and fake only | TLS, token handling, request bodies on a real API server | No real client exists | Owner approval of the real client |
| D1 | Binding-writer method | OPEN | Stage contract behind the gate | Impersonation, effective permissions | Ingress BLOCKED | Owner decision D1 |
| Live D13 managers | istiod and controller field managers | NOT_VERIFIED | Allowlist with fail-closed tests | Real manager names and paths | `ownership_not_verified` | Live observation (D20) |
| Effective RBAC | Service account and access-policy permissions | NOT_VERIFIED | Rendered RBAC checked offline | Effective permissions, `impersonate`, destroy inventory reads | Not executed | Live scope |
| Base validator serving | istiod-default-validator | NOT_VERIFIED | Deferred-readiness gate | Live probe F | Every run stops before the gateway | D20 and D13 |
| Istio CA and webhook serving | `cacerts`, injector and validators | NOT_VERIFIED | C1/D23 guards, G9 registration contract | Real CA rotation, `caBundle` writes, serving | Gate | Live scope, D21 |
| EKS discovery completeness | Discovery for destroy | NOT_VERIFIED | Every advertised group version read, UNKNOWN fails closed | Completeness on EKS | UNKNOWN blocks | Live scope |
| Real namespace cascade atomicity | Namespace DELETE | NOT_VERIFIED | Fake-only atomic gate (section 7.5) | No real atomic primitive; races | Fake only | A real design decision (no equivalent primitive asserted) |
| Real GC, finalizers, target deregistration | Owned children, TGB finalizer | NOT_VERIFIED / NOT_TESTED | Fake waits, never strip | Real timing, controller finalizer removal, deregistration | Fake only | Live scope, D4 |
| ECR mirror and image pull | F18 | NOT_TESTED | B1, B2, B3 code | Repositories, copy, pull through endpoints and NAT | Not executed | Live scope |
| ELBv2 endpoint connectivity | F21 | NOT_TESTED (Live and Emulator) | Endpoint in code, mock plan | Calls through the endpoint | Not executed | Live scope; a reviewed `network-full` harness change for the Emulator |
| TargetGroupBinding reconciliation | Controller | NOT_TESTED | Destroy gates only | Registration and reconcile | Ingress BLOCKED | D1, D15, Live scope |
| NetworkPolicy effectiveness | Default-deny policies | NOT_TESTED | Offline validator | Enforcement | Not executed | Live scope |
| NP-2B / NP-3 | Network policy flow | PAUSED (v14.5 §19), not implemented | [NP-2 contract](np2-network-policy-flow-contract.md) | — | Paused until Steps 1 and 2 close | Owner authorization |
| Live E2E | Apply to destroy on EKS | NOT_TESTED (outside scope, §15) | Fake and synthetic only | Everything Live | Not executed | New Owner Live scope |
| Emulator gaps | DEV roots and the runtime | See section 7.9 | Formal ledger | Roots outside `all`; no Kubernetes or EKS scenario | — | Separate Owner approval per scenario |

### 7.9 Emulator evidence reconciliation

- **Representative run:** run 43791639228, attempt 1, was accepted by the Owner on
  2026-11-16 for the disposable `aws_vpc.proof` only. Its acceptance scope is unchanged.
- **Ledger:** 18 entries, one per run and attempt (12 representative, 6 rehearsal).
  The committed snapshot `actions-runs.json` was retrieved at 2026-11-22T07:38:44Z.
- **Live run list on 2026-11-24:** read through the GitHub connector. It still shows 12
  representative and 6 rehearsal runs, the latest being 44988721098. No run is
  unregistered, duplicated, in progress or missing an attempt.
- **Trigger paths:** since `a3cf9bc` (run 44988721098), only
  `scripts/emulator-verification/README.md` changed among them, which is not a trigger
  path.
- **Ledger changes:** no new entry and no snapshot update are needed. The live
  comparison is recorded here, not in the ledger.

| Root or scenario | Status |
| --- | --- |
| network (16 resources, no interface endpoints) | Formal PASS in 44279751946, 44664010985, 44765057461, 44859280239 and 44988721098 |
| api (7 resources) | Formal PASS in 44765057461, 44859280239 and 44988721098 |
| `network-full` | EMULATOR_COMPATIBILITY_BLOCKED (default egress revoke gap). Since F21 the harness lists eight services against nine committed, so it would stop at plan inspection |
| tfstate | EMULATOR_COMPATIBILITY_BLOCKED (S3 Control host prefix under strict TLS) |
| serverless-api, platform, developer-access | NOT_TESTED |
| registry | NOT_TESTED; outside `all` and outside the ledger's `DEV_ROOTS` |
| Kubernetes runtime | NOT_TESTED; no scenario exists |

Every PASS entry records all 14 controls PASS, the per-root operations, independent API
IDs and the resource, material, process and host cleanup PASS. Details are in the
[Step 2 record](step2-emulator-rehearsals.md) and the
[ledger](evidence/emulator-runs/index.md).

### 7.10 Expected counts at the baseline

| Suite | Tests / mutations |
| --- | --- |
| Runtime receipt (`k8s_runtime_receipt_tests`) | 144 / 382 |
| of which destroy engine | 42 / 113 |
| of which destroy foundation | 36 / 144 |
| Runtime plan | 29 / 39 |
| Runtime status | 21 / 32 |
| Runtime apply | 58 / 163 |
| Certificates | 29 |
| CI policy | 31 / 73 |

6c-B5 changes no count.

### 7.11 Inputs for the Step 1/2 closure decision (not decided here)

*Audit-time input. The Owner decided these on 2026-11-24 (OD-01 to OD-13); see
[section 7.14](#714-subsequent-owner-decisions-and-policy-release-post-audit).*

The Owner decides the following after independent review:
1. Acceptance of this audit, with Full CI PASS on its exact HEAD (Claude's
   Owner-designated final task) and PR Safety CI and Offline Contracts success.
2. How each root outside `all` is treated at closure (section 7.9): accepted as a
   documented gap or given more rehearsal scope.
3. The `network-full` harness gap after F21, and the ledger's `DEV_ROOTS` limitation for
   `registry`: accepted as residual risk or addressed by separately reviewed changes.
4. Whether the Step 2 end-to-end apply and destroy stays NOT_TESTED at closure.
5. Confirmation that real apply and destroy stay BLOCKED and Live stays outside scope.

### 7.12 Inputs for the Codex handover (not started)

A handover instruction needs:
- the baseline SHA;
- this register (sections 7.7 to 7.9);
- the open decisions (D1, D4, D14, D15, D20, D21, D22);
- the approved contracts, which are not to be widened;
- the rule that the Fake-only engines and the atomic namespace gate are not Live
  procedures;
- the expected counts and the CI execution policy;
- the paused features (V7-B/C/D, NP-2B/NP-3 and others);
- the Step 3 items already assigned (F6 and F10).

### 7.13 MASTER_POLICY revision assessment (§21)

*Audit-time assessment against v14.5. MASTER_POLICY v14.6 was issued afterwards; see
[section 7.14](#714-subsequent-owner-decisions-and-policy-release-post-audit).*

This assessment is limited by one fact: the Master Policy v14.5 PDF is not in the
repository, and this audit could not read it. The findings below compare the merged
evidence with v14.5 as [AGENTS.md](../AGENTS.md) records it. They are inputs for
ChatGPT and the Owner, who decide any PDF revision. The PDF is not changed here.

| Topic | Assessment |
| --- | --- |
| §19.2 Owner Decision Gate | The gate works as written: D3, D5, D6, D11, D12, D18 and D19 were approved through it for scoped Fake-only work and are recorded in the [design record](k8s-runtime-apply-destroy-design.md#13-owner-decision-matrix-d1d23). The open decisions (D1, D4, D14, D15, D20, D21, D22) stay behind it. **No revision needed.** If the PDF lists 6c decisions as undecided, that list is a status snapshot, not a rule |
| Fake-only atomic namespace safety gate (F06-R) | An implementation contract inside the approved D6, D18 and D19 scope, recorded in the design record, the script README and section 7.5. It asserts no real API primitive. **Repository evidence only; no revision needed** |
| G9 registration pinning | An integration guard inside the existing G9 and D19 contracts, recorded in the script README. **Repository evidence only; no revision needed** |
| Remaining steps after 6c-B4b | The §19.3 order (6c-B5, then the Step 1/2 closure decision and the handover, then Step 3 and Step 4) still matches the work. Completed items are status, not rules. **No revision needed** for completed items, SHAs, pull requests, run IDs or counts |
| One-time operational exceptions | PR #101 ran under a one-time Owner exception: roles swapped and Full CI waived. **Revision candidate (conditional):** if v14.5 has no rule for recording such exceptions, §21 could state that an exception is named, scoped to one pull request, recorded in repository evidence, ends with that pull request and is never precedent |
| Norms to align before the Codex handover | **Revision candidate (conditional), in §19.4 or in the handover instruction:** the stop conditions that apply to Codex. Real apply and destroy stay BLOCKED. The Fake-only engines and the atomic gate are not Live procedures. The approved contracts are not widened. The open decisions need the Owner |

### 7.14 Subsequent Owner decisions and policy release (post-audit)

**PR #102 final evidence** (checked on GitHub, 2026-11-24):

| Item | Value |
| --- | --- |
| Reviewed HEAD | `b9edba4920a257a91c6bdd26c7f8eca66d532a4d` |
| Reviewed base | `0ed2c1660463d9f88df9d63481059676ccadf357` |
| Verified tree | `0d6bc58cc696ae8bffc017ce561e83e3e358c922` |
| PR Safety CI | 45452026201, attempt 1, success |
| Offline Contracts | 45452026074, attempt 1, success |
| Full CI | 45453872145, attempt 1, success; job 138657958447; dispatch reason `claude-final-task`; evidence `dispatch`; pull request binding `VERIFIED_BY_PUBLIC_API`; tested tree equal to the PR Safety CI tested tree |
| Squash commit on `main` | `c42c6cc0e0618f0cbffee78e29fc3fd297f59859` (single parent `0ed2c16`, tree `0d6bc58`, `merge_check.py` passed with `--evidence dispatch`) |
| Post-merge Offline Contracts | 45464497212, attempt 1, success |

PR #102's Full CI is a regression result for the integrated tree. It does not change
PR #101's own record: PR #101 merged with FULL CI NOT RUN under a one-time Owner
exception, which has ended and is not a precedent.

**Step 1/2 closure (Owner decision 2026-11-24, OD-01 to OD-13).** Step 1 is closed as
SOURCE / OFFLINE COMPLETE. Step 2 is closed with the accepted, explicitly limited
Emulator evidence. The residual risks of sections 7.8 and 7.9 are accepted as such:
- network-full and tfstate stay EMULATOR_COMPATIBILITY_BLOCKED;
- the F21 harness gap (eight against nine services) is accepted;
- serverless-api, platform, developer-access and registry stay NOT_TESTED;
- the Kubernetes runtime E2E and the Step 2 end-to-end apply and destroy stay
  NOT_TESTED;
- D1, D4, D14, D15, D20, D21 and D22 stay OPEN;
- real Apply and Destroy stay BLOCKED and Live stays out of scope;
- NP-2B and NP-3 stay PAUSED;
- no further Emulator demonstration runs before the Codex handover;
- CI-PERF-01 runs before the handover.

No unverified item becomes PASS. CORE PORTFOLIO COMPLETE and PORTFOLIO COMPLETE are
not declared. The closure does not start any paused feature: section 7.8's "Paused
until Steps 1 and 2 close" for NP-2B and NP-3 is superseded by OD-11.

**MASTER_POLICY v14.6 (issued 2026-11-24).** It answers the section 7.13 candidates.
It records:
- the approved runtime decisions, with G9 registration pinning and the Fake-only
  atomic namespace gate in the approved scope (§19.2);
- the Step 1/2 closure, the residual risks and OD-01 to OD-13 (§13.3.1, §19.3);
- the handover gate (§19.3);
- CI-PERF-01 (§12.5.1);
- PR #101 as a historical one-time exception that is not a precedent.

After the release, the Owner assigned CI-PERF-01's design and implementation to
ChatGPT, with Claude for profiling, independent review and benchmarks (see
[AGENTS.md](../AGENTS.md#ci-perf-01-full-ci-performance-master_policy-1251)). The
repository now refers to the controlling policy without a version number
([AGENTS.md](../AGENTS.md#repository-guidance)).
