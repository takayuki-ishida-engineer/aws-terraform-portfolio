# Approved Terraform repository structure and migration strategy — R0

## 1. Decision, status and source authority

**APPROVED DESIGN:** maintainability-first functional child modules, shallow
Root → Child composition, and migration-first R0 → R1 → R2 → R3 → R4 before new
Architecture v2 features. This instruction approves the strategy, not a Terraform
migration, resource name, AWS operation or completed Live gate. Module count is
not an optimization target or acceptance condition. Master Policy v10 (2026-11-08)
remains authoritative for architecture/security/environment/Live requirements.

Current source: main `9bfb4bf9146d85744ab88fef117007851ba29346`, with matching
[successful CI 42585657162](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42585657162).
The [technical history](../infra/README.md), [MVP acceptance](offline-mvp-acceptance.md),
[Architecture v2](architecture-v2.md), [foundation design](architecture-v2-foundation-design.md)
and [verification policy](portfolio-verification-policy.md) remain evidence/design
references. No historical result is rewritten as post-refactor or v2 evidence.

R0 changes documentation only. No directory below is created, renamed or removed;
all nine existing modules and the seven-instance/17-resource HTTP API MVP remain
unchanged. The external Master Policy PDF will be revised separately after review
and merge; it is not generated or edited here.

## 2. Child modules: coherent functionality and lifecycle

Use infra/modules/ for reusable, environment-independent child modules. Group
resources implementing one understandable responsibility when deployment,
dependencies, change/review patterns, lifecycle and ownership are tightly coupled.
A module may contain multiple resource types and many .tf files. Do not wrap each
AWS resource in its own module. Separate a related resource only for a materially
independent state owner, security/administration boundary, lifecycle or reuse need,
with explicit review of that exception. Do not add speculative wrappers/stacks or
symmetrical empty directories. Nested children are exceptional and need a clear
maintenance/reuse justification. Providers/backends remain root-owned.

Within a module, files separate readable responsibilities, not execution stages.
All .tf files in the directory share module scope; Terraform uses expression
references and narrowly justified depends_on, not file order. Putting gateways.tf
after subnets.tf does not order deployment. Example eventual VPC organization:

```text
infra/modules/vpc/
├── main.tf
├── subnets.tf
├── gateways.tf
├── routing.tf
├── endpoints.tf
├── security.tf
├── variables.tf
├── outputs.tf
├── versions.tf
├── README.md
└── tests/
```

Approved VPC ownership includes VPC/subnets/IGW/public NAT/EIP, tables/routes/
associations and compatible endpoints. Detailed extension must preserve current
private-only defaults, stable keys and 16 VPC tests. The current shared private
table with route=[] and singular output cannot be treated as already per-AZ;
future inputs, routing ownership and address compatibility require review. One
module owns explicit routes/associations; gateway-endpoint-managed routes still
need compatible association semantics, not competing inline/standalone control.
No independent nat_gateway/network_core/private_routing modules by default.

Document effective values as Root Override, Module Default and Module Fixed.
Consolidation must not hide security defaults or turn required inputs into flags.

## 3. Root modules and other technologies

Roots remain infra/services/<env>/<region>/<service>/ and independently own
provider/account restrictions, state, deployment and lifecycle. Compose several
coherent children when their lifecycle justifies it. Avoid both one root per
resource and an enormous environment-wide root. Candidate future ownership layout:

```text
infra/services/
├── dev/
│   ├── ca-central-1/
│   │   ├── network/
│   │   ├── platform/
│   │   ├── api/
│   │   ├── database/
│   │   ├── delivery/
│   │   ├── db-access/
│   │   └── serverless-api/  # existing historical HTTP API MVP
│   └── us-east-1/
│       └── edge/
├── stg/
│   ├── ca-central-1/
│   │   ├── network/
│   │   ├── platform/
│   │   ├── api/
│   │   ├── database/
│   │   └── delivery/
│   └── us-east-1/
│       └── edge/
└── prod/
    ├── ca-central-1/
    │   ├── network/
    │   ├── platform/
    │   ├── api/
    │   ├── database/
    │   └── delivery/
    └── us-east-1/
        └── edge/
```

These are intended boundaries, not empty directories to create or approval to
deploy. Global/edge provider/certificate Regions and exact state ownership need
future verification. DEV state stays local, STG/PROD remote; each env/Region/service
has separate authoritative state and a single authorized writer. Backend selection,
output publication/consumer access and any real-state migration stay OPEN.

Identity Center administration and workload-account customer-managed policies
must not automatically enter an ordinary DEV root: organization/delegated-admin,
workload account, home Region and administrative scope need separate design.
Keep Kubernetes, apps, Packer, Ansible, workflows, scripts and evidence outside
Terraform child modules. Terraform owns internal NLB/listeners/target groups;
Kubernetes owns Gateway Pod registration through the approved future controller
mechanism. No duplicate Istio/AuthorizationPolicy/controller/resource owner.

## 4. Approved target functional-module inventory

All rows are intended ownership, not implemented future capability. Existing names
below remain directories today; new names are not created in R0.

| Intended child module | Intended responsibility | Current / future distinction |
| --- | --- | --- |
| vpc | VPC, keyed subnets, IGW/NAT/EIP, routing and compatible endpoints | Existing base retained; new features only after R4 |
| lambda_workload | Function, dedicated execution role/policy and dedicated Lambda log resources | New consolidation target in R1; no application feature changes |
| api_gateway_http | Historical HTTP API and dedicated API access logging | Existing five API/permission resources; log ownership migrates in R2 |
| api_gateway_rest | Regional REST methods, Cognito authorizer references, VPC Link V2, custom-domain mTLS, Regional WAF and logs | Future, subject to compatibility/security review |
| cognito_auth | User Pool, App Client, non-secret federation and AWS-managed login domain | Future; no plaintext Google secrets in Terraform |
| cloudfront_edge | Distribution/origin, edge WAF and approved origin-mTLS references | Future; PKI, pricing and global scope still reviewed separately |
| eks_platform | EKS cluster/managed nodes and cluster-specific IAM/security/access | Future; no workload/controller double ownership |
| private_ingress | Internal NLB, TCP:443 listener, target groups and ingress security | Future; Kubernetes target registration remains separate |
| rds_postgres | DEV Single-AZ RDS PostgreSQL | Future |
| aurora_postgres | STG/PROD Provisioned PostgreSQL writer/reader across AZs | Future |
| delivery | ECR/CodeBuild/deployment infrastructure, scoped IAM and related notifications where lifecycle permits | Future; shared-resource exceptions need justification |
| rds_ssm_access | DEV developer DB-access EC2, schedule/SQS/controller/watchdog/monitoring and scoped IAM | Future; not generic administration |
| s3_artifact_bucket | Independent versioned artifact bucket/security/ownership | Existing retained |
| secrets_manager | Metadata-only container; external value/rotation ownership | Existing retained |
| iam_access | Human Identity Center Permission Sets | Existing independent administration boundary retained |
| iam_account_policies | Workload-account-owned customer-managed IAM policies | Existing separate account boundary retained |

This is not a quota. Closely coupled resources may have multiple .tf files, while
shared resources/certificates/identity/state boundaries can justify a specifically
approved exception. Seven existing-functionality modules after consolidation is
possible, not required for acceptance.

## 5. DEV RDS SSM access: corrected purpose

This is **Local developer workstation → AWS Systems Manager Session Manager port
forwarding → private EC2 → private RDS PostgreSQL**, not a generic administrator
server or management-account jump host. Intended module: infra/modules/rds_ssm_access/;
initial root: infra/services/dev/ca-central-1/db-access/. Do not replicate it into
STG/PROD automatically. No broad AWS admin or public SSH/RDP is required.

Keep America/Toronto START cron(0 8 ? * MON-FRI *) and STOP
cron(0 19 ? * MON-FRI *), weekends stopped, no special holiday calendar, DST-aware.
EventBridge Scheduler → SQS → Controller Lambda → EC2, with independent Watchdog
and CloudWatch/SNS failure detection, remains the target. Exact thresholds and
permissions are not selected. Future review covers least-privilege developer/SSM
identity, endpoint/NAT connectivity, DB SG access, image/config provenance and
session control. Port-forwarding session logs must not be assumed to capture SQL
traffic. Weekday STOP is not verified full DEV Live teardown. No instance/controller
is implemented here.

## 6. Existing nine modules and call sites

The following inventory is derived from current .tf declarations and the DEV root,
not directory-name assumptions. Resource addresses in this table are relative to
a module instance; count/for_each instances in VPC vary by approved inputs.

| Current module / source | Actual relative managed resource declarations | Current call sites | Approved disposition |
| --- | --- | --- | --- |
| [`api_gateway_http`](../infra/modules/api_gateway_http/README.md) | `aws_apigatewayv2_api.this`, `aws_apigatewayv2_integration.this`, `aws_apigatewayv2_route.this`, `aws_lambda_permission.this`, `aws_apigatewayv2_stage.this` | module.http_api | Retain HTTP API; add dedicated log ownership (R2) |
| [`cloudwatch_logs`](../infra/modules/cloudwatch_logs/README.md) | `aws_cloudwatch_log_group.this` | module.lambda_logs, module.api_access_logs | Dedicated Lambda logs → lambda_workload (R1); API logs → api_gateway_http (R2); remove only after no legitimate consumers and verified coverage |
| [`iam_access`](../infra/modules/iam_access/README.md) | `aws_ssoadmin_customer_managed_policy_attachment.developer`, `aws_ssoadmin_permission_set.access_admin`, `aws_ssoadmin_permission_set.developer`, `aws_ssoadmin_permission_set.operator`, `aws_ssoadmin_permission_set_inline_policy.access_admin`, `aws_ssoadmin_permission_set_inline_policy.developer`, `aws_ssoadmin_permission_set_inline_policy.operator` | No service-root call | Retain independent Identity Center administration |
| [`iam_account_policies`](../infra/modules/iam_account_policies/README.md) | `aws_iam_policy.developer_secrets_manager` | No service-root call; IAM access test run account_policy_fixture uses source ../iam_account_policies | Retain workload-account policy ownership |
| [`lambda`](../infra/modules/lambda/README.md) | `aws_lambda_function.this` | module.lambda_function | Consolidate into lambda_workload (R1) |
| [`lambda_execution_role`](../infra/modules/lambda_execution_role/README.md) | `aws_iam_role.this`, `aws_iam_role_policy.this` | module.lambda_execution_role | Consolidate into lambda_workload (R1) |
| [`s3_artifact_bucket`](../infra/modules/s3_artifact_bucket/README.md) | `aws_s3_bucket.this`, `aws_s3_bucket_versioning.this`, `aws_s3_bucket_public_access_block.this`, `aws_s3_bucket_ownership_controls.this`, `aws_s3_bucket_server_side_encryption_configuration.this`, `aws_s3_bucket_policy.this` | module.artifact_bucket | Retain independent artifact lifecycle/state ownership |
| [`secrets_manager`](../infra/modules/secrets_manager/README.md) | `aws_secretsmanager_secret.this` | module.secret_metadata | Retain metadata-only container/external value boundary |
| [`vpc`](../infra/modules/vpc/README.md) | `aws_vpc.this`, `aws_subnet.private (keyed/counted where declared)`, `aws_subnet.public (keyed/counted where declared)`, `aws_internet_gateway.this (keyed/counted where declared)`, `aws_route_table.private (keyed/counted where declared)`, `aws_route_table.public (keyed/counted where declared)`, `aws_route_table_association.private (keyed/counted where declared)`, `aws_route_table_association.public (keyed/counted where declared)` | No service-root call | Retain and extend after R4 |

All seven production-code module calls are in
[DEV main.tf](../infra/services/dev/ca-central-1/serverless-api/main.tf). README
examples are not implemented roots; the IAM test fixture is not a human/workload
integration. The generic logs module has two root consumers, not an assumed shared
log group. No service root currently calls VPC or either IAM module.

Keep IAM modules separate: Identity Center Permission Sets/references require
organization/delegated administration in the correct home Region/account;
customer-managed policies must exist in their owning workload accounts. Same IAM
domain does not imply same provider, privilege or lifecycle. Keep Secrets Manager
separate because metadata/recovery/value ownership is not the function lifecycle;
keep artifact storage separate because publication/version retention/bootstrap
state may outlive releases/functions. Neither should merge merely to reduce count.

## 7. Concrete 17-resource migration matrix

Each current address below exists as a configured resource at this baseline;
plan-computed IDs do not establish actual AWS resources/state. “Unchanged” means
an exact address-preservation requirement for retained instances, contingent on
future implementation. No new internal resource label or consolidated root instance
name has been approved. OPEN destinations must be resolved in R1/R2 before code or
move declarations are accepted. Target module source plus resource type is known;
the exact destination address is not invented here.

| Current full managed address | Intended module/type and future address | Move/compatibility disposition |
| --- | --- | --- |
| `module.artifact_bucket.aws_s3_bucket.this` | `module.artifact_bucket.aws_s3_bucket.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_versioning.this` | `module.artifact_bucket.aws_s3_bucket_versioning.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_public_access_block.this` | `module.artifact_bucket.aws_s3_bucket_public_access_block.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_ownership_controls.this` | `module.artifact_bucket.aws_s3_bucket_ownership_controls.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_server_side_encryption_configuration.this` | `module.artifact_bucket.aws_s3_bucket_server_side_encryption_configuration.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_policy.this` | `module.artifact_bucket.aws_s3_bucket_policy.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.secret_metadata.aws_secretsmanager_secret.this` | `module.secret_metadata.aws_secretsmanager_secret.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.lambda_logs.aws_cloudwatch_log_group.this` | lambda_workload / aws_cloudwatch_log_group; exact instance/internal label OPEN (R1) | Address changes; future resource-level moved declaration or separately approved handling required |
| `module.api_access_logs.aws_cloudwatch_log_group.this` | api_gateway_http / aws_cloudwatch_log_group; exact internal label OPEN (R2), retained API instance preferred | Address changes; future moved declaration or separately approved handling required |
| `module.lambda_execution_role.aws_iam_role.this` | lambda_workload / aws_iam_role; exact instance/internal label OPEN (R1) | Address changes; future resource-level moved declaration or separately approved handling required |
| `module.lambda_execution_role.aws_iam_role_policy.this` | lambda_workload / aws_iam_role_policy; exact instance/internal label OPEN (R1) | Address changes; future resource-level moved declaration or separately approved handling required |
| `module.lambda_function.aws_lambda_function.this` | lambda_workload / aws_lambda_function; exact instance/internal label OPEN (R1) | Address changes; future resource-level moved declaration or separately approved handling required |
| `module.http_api.aws_apigatewayv2_api.this` | `module.http_api.aws_apigatewayv2_api.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.http_api.aws_apigatewayv2_integration.this` | `module.http_api.aws_apigatewayv2_integration.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.http_api.aws_apigatewayv2_route.this` | `module.http_api.aws_apigatewayv2_route.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.http_api.aws_lambda_permission.this` | `module.http_api.aws_lambda_permission.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.http_api.aws_apigatewayv2_stage.this` | `module.http_api.aws_apigatewayv2_stage.this` (retain) | Precise identity mapping if retained as required; no move then needed |

Total remains **17 existing functional resources**, not seven module instances as
a permanent invariant: R1 groups the function, role, inline policy and application
log group (four resources); R2 groups five existing API/permission resources plus
its dedicated log (six); artifact bucket remains six and secret metadata one.
No implicit REST/Cognito replacement, new resource, log merge or recreate is allowed.

### Output compatibility, dependencies and security

Inventory below records every current child output, not a promise all public names
are already defined in the future module. Resolve destination signatures, any
compatibility exports and all consumers before retiring an old source.

| Current module | Current output contracts | Future compatibility / dependencies |
| --- | --- | --- | --- |
| api_gateway_http | `api_id`, `invoke_url`, `execution_arn` | Preserve actual API/stage invoke URL/execution ARN with route/permission/stage ordering; add actual dedicated-log references for root compatibility, names OPEN. |
| cloudwatch_logs | `log_group_name`, `log_group_arn`, `retention_in_days`, `deletion_protection_enabled`, `log_group_class`, `kms_key_arn` | R1/R2: owning module exports required actual group name/bare ARN and lifecycle/security evidence; keep all retention/protection/class/KMS assertions. Exact compatibility signature OPEN. |
| iam_access | `access_admin_permission_set_arn`, `developer_permission_set_arn`, `operator_permission_set_arn`, `developer_customer_managed_policy_references`, `developer_inline_policy_quota`, `developer_managed_attachment_quota` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |
| iam_account_policies | `policy_arn`, `policy_name`, `policy_path`, `policy_json`, `policy_non_whitespace_characters`, `policy_headroom_characters` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |
| lambda | `function_arn`, `function_name`, `invoke_arn`, `version`, `execution_role_arn`, `runtime`, `architecture`, `vpc_configuration`, `log_group_name` | R1: preserve equivalent function/role/runtime/security scope semantics in lambda_workload; exact output signature OPEN. Log→policy→function order must remain. |
| lambda_execution_role | `execution_role_arn`, `execution_role_name`, `inline_policy_name`, `log_group_arn`, `secret_read_enabled`, `permission_scope` | R1: preserve equivalent function/role/runtime/security scope semantics in lambda_workload; exact output signature OPEN. Log→policy→function order must remain. |
| s3_artifact_bucket | `bucket_name`, `bucket_arn`, `versioning_status` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |
| secrets_manager | `secret_arn`, `secret_name`, `secret_id`, `kms_configuration`, `resource_policy_managed` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |
| vpc | `vpc_id`, `vpc_cidr`, `private_subnet_ids`, `public_subnet_ids`, `private_route_table_id`, `public_route_table_id`, `internet_gateway_id` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |

Root outputs must retain equivalent api_invoke_url, api_id, lambda_function_name,
lambda_function_arn, artifact_bucket_name, secret_metadata_arn, lambda_log_group_name
and api_access_log_group_name from actual resource outputs, with no secret values,
environment maps or fabricated ARNs. Root call/argument names may change after
review; preserve their values and consumer contract. Provider account restrictions,
local DEV backend, Terraform 1.17.0/AWS 6.72.0 lock behavior and state owner remain.

Preserve the following actual contracts in every migration PR:

- Lambda-only role trust; exact CreateLogStream/PutLogEvents group-stream scope;
  default secret reads off/null ARN/empty secret environment; enabled exact actual
  secret ARN with GetSecretValue/DescribeSecret only and no CMK permission in this
  root. The reusable role's separately tested scoped KMS behavior must not disappear
  unnoticed when consolidation changes its public contract; preserve/retarget its
  cases and documented conditions, no privilege expansion.
- Log group before role policy/function; role and inline policy readiness before
  Lambda. Preserve separate API/application groups, 30-day retention, deletion
  protection, STANDARD, skip_destroy=false, default no explicit CMK and bare log
  ARN versus log-stream ARN semantics. Preserve all tested optional lifecycle/KMS
  validation behavior during migration; do not silently retire those contracts.
- Exact approved bucket/key/immutable version and runtime/handler; existing compute,
  environment, layer/VPC-reference validations remain covered, without adding VPC
  attachment to this root. Preserve publish=false/no new aliases or app features.
- S3 versioning/AES256/public-access/ownership/HTTPS policy and protected deletion;
  secret metadata only and recovery safeguards; no secret values in any Terraform
  input/data/plan/state/output, source or CI artifact. Approach A remains mandatory.
- HTTP API, AWS_PROXY POST payload 2.0, AWS_IAM $default route, auto-deploy stage,
  throttling 10/20, exact function/principal and actual API /$default/$default invoke
  scope, metadata-only separate access logging, API-derived statement ID and the
  current stage-after-route/permission ordering. Historical public endpoint behavior
  is not silently changed into the future REST/mTLS architecture.

Internalization also changes reference ownership: Lambda currently accepts
execution_role_arn/log_group_name, its role accepts log_group_arn, and HTTP API
requires access_log_group_arn. R1/R2 must decide owned-resource inputs and any
compatibility contract before removing these caller references. Negative cases
for formerly external ARNs must map to equivalent ownership/identity/resource
checks rather than disappearing because a variable was removed. Existing external
consumers are not assumed absent merely because the repository has one root.

### State move and verification limitations

Five resource addresses necessarily change under intended consolidation; the other
12 must remain stable unless a separately reviewed mapping explains otherwise.
Do not assume moving directories or a module source automatically moves state.
Merging three old modules into one may need resource-level rather than one whole-
module move; exact legal source/destination scopes, retained declarations/chains,
provider addresses and supported Terraform semantics require future review.

A future R1/R2 PR must complete each OPEN mapping and compare actual old/new mock
plans after applying its documented address correspondence: same resource types,
settings, policies, outputs and dependencies, no unexplained create/delete/replace.
Retain reviewed move compatibility declarations as required for prior users; removal
is a breaking change, not automatic cleanup. Source/mock comparison and moved-block
syntax checks are not proof of real-state identity preservation. No deployed state
is assumed; if real state/users exist, separately authorized identity/state evidence
and an appropriate external plan review are needed. Stop on ambiguous ownership or
unexpected replacement; never import/reset/manipulate state to force a green test.
No such operation, authenticated plan or migration is authorized in R0/Codex Cloud.

## 8. Test, fixture, script and CI migration obligations

The following are implementation-readiness dependencies, not files changed here:

| Existing evidence / path | Address/interface impact and required verification |
| --- | --- |
| [Lambda tests](../infra/modules/lambda/tests/lambda.tftest.hcl), [role tests](../infra/modules/lambda_execution_role/tests/lambda_execution_role.tftest.hcl), [logs tests](../infra/modules/cloudwatch_logs/tests/cloudwatch_logs.tftest.hcl) | R1/R2 must relocate/retarget applicable 70/64/51 historical native cases and their assertions, overrides and fixtures; no lost optional boundaries or superficial source-text substitute |
| [Role checker](../infra/modules/lambda_execution_role/tests/check_execution_policy.py) | Preserve exact generated trust/policy JSON, official references, permission matrix, negatives/mutations and malformed/reference-fault rejection under the new owning module/address |
| [API native tests](../infra/modules/api_gateway_http/tests/api_gateway_http.tftest.hcl), [API checker](../infra/modules/api_gateway_http/tests/check_api_gateway_configuration.py) | R2 changes five-resource module inventory to include dedicated logs; update actual-plan address/count and invalid-input/partial-plan classification explicitly; retain 47 historical native cases, 17 mutations/19 capture failures and log/security checks |
| [Root native tests](../infra/services/dev/ca-central-1/serverless-api/tests/root_integration.tftest.hcl), [root checker](../infra/services/dev/ca-central-1/serverless-api/tests/check_root_integration.py) | Seven instance/type maps, full resource paths, computed overrides, output bindings, exact role/log/env/API assertions and mutation targets require R1/R2 adaptation; preserve four complete 17-resource plans and intentional invalid-account rejection |
| [Root input checker](../infra/services/dev/ca-central-1/serverless-api/tests/check_required_inputs.py) | Uses native fixture header and root inputs; retained 12 rejection cases must remain real failed mock processes with complete diagnostics, not silently skip after interface changes |
| [Offline workflow](../.github/workflows/terraform-offline-ci.yml) | Module working directories, copied root lock, test capture paths, checker invocations, native counts and summary outputs, official-reference steps and shared provider-cache topology/initialized-config expectations need reviewed updates. Preserve pinned actions, credential isolation, locks, storage checks, read-only security and full suite |
| [IAM test fixture](../infra/modules/iam_access/tests/iam_access.tftest.hcl), [IAM references](../infra/modules/iam_access/tests/check_authorization_reference.py), [equivalence](../infra/modules/iam_access/tests/check_authorization_equivalence.py), [toolkit](../scripts/aws-policy-validation/README.md) | Independent modules retained; full policy/export/toolkit/guardrail regression still required. Update any discovered path/address dependency by explicit mapping, never waive unaffected security evidence |
| VPC, S3 and secret tests/checkers under their retained modules | Preserve VPC 16, S3 37 and secret 31 historical cases and their resource/security/fixture contracts; no network/secret/artifact feature implementation during R1/R2 |

Historical baseline is 384 native Terraform and 153 Python tests plus independent
checks; not an upper limit. Preserve all existing Terraform/Python/IAM/guardrail/
negative/mutation/evidence coverage. A reviewed case/address inventory must reconcile
old and new suites, including cases redistributed from removed modules. Any changed
count must be explained by actual reorganized evidence without dropped/skipped/
weakened assertions; do not pass by changing only constants or deleting tests.
Retire generic cloudwatch_logs only after scanning every actual root/module/test
consumer, migrating legitimate uses and demonstrating equivalent coverage.

A concrete compatibility review is still OPEN: generic CloudWatch KMS references
accept aws-cn, while existing execution-role and HTTP API scopes do not. Independent
log validation cases cannot simply be called positive whole-workload cases after
consolidation. R1/R2 must map every prior assertion to its valid layer, preserving
behavior/coverage; if a legitimate independent contract cannot be retained, keep
the old module and seek an explicitly justified exception rather than weakening
validation or deleting cases. No generic-module removal is approved on assumptions.

Each intermediate implementation PR requires affected local native/actual-plan/
negative/mutation/security checks and complete GitHub Actions regression. R4 is
additional final verification, never permission to postpone those checks. R0 itself
uses documentation-only consistency, source/link/scope/secret/diff checks and does
not rerun unrelated Terraform/Python regressions.

## 9. Required sequence and acceptance gates

| Stage | Scope / entry | Required acceptance and evidence | Authorization boundary |
| --- | --- | --- | --- |
| R0 — current PR | Document approved grouping, existing inventory/mappings and roadmap | Four-file documentation scope; source consistency; permanent AGENTS unchanged | No implementation or state/AWS work |
| R1 — Lambda workload consolidation | Separately authorize new lambda_workload and migrate dedicated function/role/log ownership | Resolve R1 destination labels/output signatures/moves; preserve four resources, security/effective settings and root outputs; adapt tests/CI/docs; affected local plus full independent CI | No new Lambda application, code delivery or network features |
| R2 — HTTP API dedicated logging | Separately authorize API access-log ownership within api_gateway_http | Resolve R2 destination/moves and API/log outputs; retain six resources together, separate logs and exact auth/permission/log contract; remove generic logs only after all consumers/coverage reconciled | No REST/Cognito substitution or new ingress |
| R3 — stabilization if required | Reconcile remaining root/output/address/documentation/evidence differences | No unresolved compatibility mapping or lost coverage, minimal justified corrections, affected local plus full CI | Not an unnecessary rewrite or deferred security fix |
| R4 — final structural baseline | R1/R2 and applicable R3 individually reviewed, CI-passed and merged with authorization | Rerun full Terraform/Python/IAM/guardrail/negative/mutation/evidence regression on exact final main; independent review of actual complete success and post-refactor inventory/case mapping | Source-text checks are insufficient; no new features before this accepted baseline |
| New Architecture v2 features — only after R4 | Separately authorized focused VPC extensions then later approved functional modules | Preserve private-only VPC behavior/current 16 tests; add actual NAT/EIP/per-AZ/endpoint/security contracts and affected tests/full CI; approved account/IP/backend/provider/cost details still required | No default standalone NAT/core/private-routing wrappers; later EKS/REST/Cognito/edge/mTLS/DB/delivery/DEV access tasks remain separate |

**R0 → R1 → R2 → R3 → R4 → new Architecture v2 features.** R3 is conditional:
if stabilization is not needed, record that evidence before R4 rather than inventing
work. Only independent review confirms exact-head CI and merge authorization;
Codex still stops after opening each PR without waiting/polling for CI. For R4,
its separately authorized task/process must trigger/reuse the complete regression
at final main and hand off the exact SHA/run for independent completed-result
verification. It cannot declare R4 passed while evidence is pending or infer it
from individual earlier branch runs. R0 does not execute or open R1–R4 PRs.

## 10. Approved versus OPEN and preserved Live boundaries

| Approved design | Still OPEN before corresponding implementation |
| --- | --- |
| Coherent functional grouping, integrated vpc ownership and shallow composition | Safe per-AZ routing inputs/addresses, endpoints/security compatibility and resource lifecycle edge cases |
| lambda_workload consolidation and API-owned dedicated logs | Exact new instance/resource names, public output contracts, moved declarations, real-state/user inventory and test/CI address adaptations |
| Migration-first order and final full baseline before features | Each separate PR's scope/review, actual complete test outcomes and accepted R4 main baseline |
| Candidate lifecycle-root/target-module responsibilities | Exact provider/global/certificate/state ownership, remote backend, downstream output distribution, account/IAM and legitimate shared-resource exceptions |
| DEV RDS developer-access purpose and existing schedule | SSM/DB/endpoint/network permissions, SQL audit expectations, image/controller settings, timing and costs |

G01–G07 remain OPEN. No AWS credentials/authenticated APIs/plans/imports/state
operations/apply/destroy or infrastructure creation is authorized. Secrets Manager
Approach A only; no actual secret values or customer/legacy ZIP/source reuse.
DEV Live needs separate approval, actual cumulative spending at most JPY 10,000
and independently verified complete removal of all exercise-created resources
within 72 hours; stopping EC2 or running destroy alone is insufficient. The existing
30-day secret recovery is a separate blocker if created unchanged for that Live
scenario; do not weaken safeguards to hide it. STG/PROD portfolio completion remains
credential-free offline validation only. No completed real-state migration, new
functionality or Live validation is claimed by this R0 approval document.
