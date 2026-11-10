# Approved repository structure — R0 strategy, migration evidence and V1 design

## 1. Decision, status and source authority

**APPROVED DESIGN:** maintainability-first functional child modules, shallow
Root → Child composition, and migration-first R0 → R1 → R2 → R3 → R4 before new
Architecture v2 features. R0 approved the strategy; R1/R2 subsequently implemented
source refactors with offline verification, not actual state migration or Live
approval. R3 only stabilizes documentation. Module count is not an acceptance goal.
Current user-approved operating policy is v11 (2026-11-09); R0 recorded historical
v10 (2026-11-08). See [policy provenance/PDF limits](architecture-v2.md#authority-evidence-and-status).
The unavailable external v11 PDF is not reproduced, edited or claimed fully reviewed.

Pre-R1/R0 source snapshot: main `9bfb4bf9146d85744ab88fef117007851ba29346`, with matching
[successful CI 42585657162](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42585657162).
The [technical history](../infra/README.md), [MVP acceptance](offline-mvp-acceptance.md),
[Architecture v2](architecture-v2.md), [foundation design](architecture-v2-foundation-design.md)
and [verification policy](portfolio-verification-policy.md) remain evidence/design
references. No historical result is rewritten as post-refactor or v2 evidence.

R0 changed documentation only and left all nine modules and the seven-instance/
17-resource HTTP API MVP unchanged. Historical R1/R2 development evidence and the
historical completed post-R2 baseline are distinguished below. The following V1
transition updates current status without rewriting those historical records.

## Historical V1 transition — accepted R4, proposed VPC contract

The user independently accepted R0–R4 at post-R3 main
`899f944c3887fa739dfb39f43617321a696c727b`, with matching successful
[push CI 42628851626](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42628851626).
Source still has eight children, four DEV calls, 17 resources, eight root outputs
and five moves; V1 changes none. The
[VPC extension decision proposal](vpc-extension-decision.md) retains coherent VPC
ownership and private-only defaults, recommends explicit per-AZ/zonal NAT opt-in,
and records the singular-output compatibility exception V1-C01 as OPEN.
V1 requires independent design approval before V2; no root, backend, AWS allocation
or Live decision is made. R3/R4 readiness wording below is retained historical
handoff evidence, not a claim that the accepted R4 baseline is still pending.

## Historical V2 baseline and V3 candidate transition

Approved main `da1af5c4eed15f5c9145799409d53c1db7508c94` passed
[post-V2 CI 42688811654](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42688811654)
with 560 native / 153 Python and 10 initialized configurations. V2 extended the
coherent VPC child and added the separate DEV Network Root. V3 adds a coherent
[eks_platform](../infra/modules/eks_platform/README.md) and separate
[DEV Platform Root](../infra/services/dev/ca-central-1/platform/README.md), bringing
the candidate library to nine children and three DEV roots without changing the
historical serverless-api four-call/17-resource/eight-output/five-move contract.
Platform does not own network state or runtime/ingress; a minimal typed V2
reference is an input, not an implemented output-publication mechanism.

V3 local evidence: 52 child / 29 Root native cases plus actual-plan/security/input/
mutation checks; complete PR CI remains independently required, with expected
641 native / 153 Python and 12 initialized configurations. No actual account,
state, connectivity/capacity, AWS-managed SG residual permissions, deployment or
Live approval follows. The following R0–R4 inventory/migration/evidence sections
are historical snapshots and are not repository-wide V3 counts.

## V4 candidate transition

Accepted V3 main `6b185820c806a0c96410a145106b9f103db14d89` passed
[CI42720431920](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42720431920)
with641 native/153 Python and12 configurations. V4 adds
[private_ingress](../infra/modules/private_ingress/README.md), bringing the library
to10 children with the same three DEV Roots. Platform now composes EKS and ingress
in one local State; source addresses remain with original owners. Ingress owns11
resources and its additional rules on existing custom EKS SGs; controller runtime
only later owns target registration. Local Child28/Root38 passes imply expected
678 native/153 Python,13 configurations for independent full CI, not prior evidence.
No Root/backend/publication service, Kubernetes controller, TLS/mTLS or Live
implementation/approval is inferred. Historical R0–V3 records below remain scoped
to their recorded revisions.

## R3 stabilization and R4 handoff

### Entry, evidence chronology and current inventory

PR [#26](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/26)
merged R1 into main on 2026-11-09; PR
[#27](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/27)
merged R2 on 2026-11-09. Exact-SHA post-merge CI below completed successfully.
The independent R3 assessment reported no outstanding implementation/test failures;
source and CI inspection here found none. Remaining R3 work is documentation.
This statement is scoped to accessible source/offline evidence, not a Live audit.

| Milestone | Applicable main / context | Verified offline native / Python | Successful CI |
| --- | --- | --- | --- |
| Pre-R1 MVP acceptance, 2026-11-08 | 89755c30508b78527fd46fa18593d5d5b11150f1; immutable [acceptance](offline-mvp-acceptance.md) | 384 / 153 | [42527556115](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42527556115) |
| R1 integrated baseline, 2026-11-09 | 87f415f5290e2cab63696e1850a6c362eef97292; PR #26 merge | 438 / 153 | [42610520450](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42610520450) |
| Current post-R2 / R3 entry, 2026-11-09 | df5ef4b2e03bd55109b0490b1e63d1d4199b663b; PR #27 merge | 491 / 153 | [42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148) |

Current source: eight reusable children; DEV calls artifact_bucket (6 resources),
secret_metadata (1), lambda_workload (4), http_api (6): **4 calls / 17 resources /
8 outputs / 5 exact resource-level moves**. CI initializes **9 configurations**.
Generic cloudwatch_logs and its 51 tests remain, with no current DEV root consumer.
Its retirement needs a separate reviewed decision, not automatic R3/R4 cleanup.

| Current native suite | Cases verified in post-R2 main CI |
| --- | ---: |
| DEV root | 5 |
| VPC | 16 |
| Secrets Manager | 31 |
| Account IAM policies | 24 |
| IAM access | 39 |
| Generic CloudWatch Logs | 51 |
| Lambda workload | 188 |
| S3 artifact bucket | 37 |
| HTTP API | 100 |
| **Total** | **491** |

Python toolkit: **153**. Additional post-R2 checks: API mutations/capture/source
28/25/4; root mutations/capture/input rejections 35/22/12; retained R1 source
mutations 3 and exact R1/R2 move-set negatives 6. IAM references/security/negative/
fail-closed and nine-config provider-cache identity/storage checks also passed in
that CI. R3 does not rerun or relabel these as local or new-HEAD/R4 test execution.

Source grounding: [DEV main](../infra/services/dev/ca-central-1/serverless-api/main.tf),
[outputs](../infra/services/dev/ca-central-1/serverless-api/outputs.tf),
[moved declarations](../infra/services/dev/ca-central-1/serverless-api/moved.tf),
[child implementations](../infra/modules/), API [main](../infra/modules/api_gateway_http/main.tf)/[logging](../infra/modules/api_gateway_http/logging.tf),
Lambda [main](../infra/modules/lambda_workload/main.tf)/[IAM](../infra/modules/lambda_workload/iam.tf)/[logging](../infra/modules/lambda_workload/logging.tf),
all eight children’s tests/*.tftest.hcl plus the five root runs,
[API case manifest](../infra/modules/api_gateway_http/tests/coverage.json),
[Lambda case manifest](../infra/modules/lambda_workload/tests/coverage.json),
[R1 guard](../infra/modules/lambda_workload/tests/check_r1_migration.py),
[R2 guard](../infra/modules/api_gateway_http/tests/check_r2_migration.py) and
[workflow](../.github/workflows/terraform-offline-ci.yml). Source counts describe
configured definitions/cases, not resources or tests created/executed by R3.

### Remediation and targeted stale-reference audit

| Document / finding | R3 correction or deliberate preservation |
| --- | --- |
| Root README: nine children/seven instances read as today | Current 8/4/17/8/five moves and completed 491/153; retain dated pre-R1 384/153 acceptance separately |
| Architecture: old layout and v10 presented as current authority | Post-R2 source/CI versus unimplemented target; current v11 per user, historical v10 design provenance, unavailable PDF/no inferred contents |
| Verification policy: old current inventory/floor-only counters | Current exact-SHA 491/153 and current mutation categories; historical floor preserved, security/DoD unchanged |
| Foundation: current inventory contradicted later R2 status | Correct current counts/provenance and merged status; retain original foundation baseline, all future network/state/identity and OPEN decisions |
| Strategy: previous moved.from called configured/current; R2 still future | Historical source columns versus current destinations, completed source interfaces and preserved local/CI chronology; retain every 17-resource matrix and all five exact mappings |
| infra/README: R1 five-call / not-yet-R2 prose | Explicit pre-R2 R1 snapshot with SHA/CI; preserve large technical history, add current post-R2 provenance |
| Live readiness: v10 current provenance | Current v11 versus historical v10 clarified; every gate, cost/deletion limit and missing approval preserved |
| Extra scope — lambda_workload README: generic logs still own API log / R2 absent | Minimum status correction justified by actual http_api logging.tf/root source; no DEV generic consumer; R1 compatibility text labeled historical |
| AGENTS current-phase instructions still R2 | R3 documentation-only scope and R4 handoff; permanent rules byte-identical |
| Original acceptance, older infra technical snapshots and DEV root’s labeled R1 section | Accurate historical evidence, preserved without retroactive counter/resource edits; old source links apply at recorded revisions |
| Future topology, bootstrap decisions, PKI/CloudFront pricing, Live gates | Preserve design/OPEN statements; no implementation or approval inferred |
| Complete v11 contents/relationship to historical v10 | Ambiguity disclosed: external PDF unavailable, no blanket equivalence or undocumented policy claim |

Audit terms include nine/seven layouts, 384/438/491, current implementation/source,
R2 future/deferred and v10/v11. Findings are classified as corrected current claims,
unchanged history, history needing a snapshot label, preserved future design or
disclosed ambiguity. Values are not globally replaced. Original acceptance stays
byte-identical. All real state migration, account/IAM/deployment/artifact and Live
approvals remain outside this remediation.

### R4 handoff — future, not accepted by R3

After independent exact-HEAD R3 CI review and separately authorized merge, obtain
the **actual final post-R3 main SHA** and independently verify its completed full
regression; an earlier branch/main run or documentation/source check is insufficient.
A separately authorized R4 task must reconcile and report:

- Four DEV calls, seventeen resources, eight root outputs and five unchanged exact
  R1/R2 moves; no new/conflicting owner or unaccounted address/interface change.
- Current native/Python suite counts and case mappings, IAM/reference/security,
  positive/negative/mutation/capture/fail-closed evidence; no skipped/lost checks.
- Root provider/account guard, local DEV backend, Terraform/provider versions,
  committed lock, state boundaries and nine-config cache identity/storage invariants.
- Preserved generic cloudwatch_logs/51 tests; no automatic retirement; no leaked
  credentials/secrets or unauthorized AWS/Live/state operations.
- Exact main/run provenance and limitations. Current 491/153 is the entry baseline,
  not a substitute for independent completed post-R3 main/R4 evidence.

R3 does **not** execute or accept R4. No actual state migration is verified. All
G01–G07 remain OPEN; DEV Live still needs separate approval, cumulative actual
JPY 10,000 and complete teardown within 72 hours. Secret 30-day recovery remains
an unresolved actual-deletion blocker; no safeguard is weakened. New Architecture
v2 implementation remains after accepted R4 and separate authorization.

## R2 implementation and historical local verification

The local-development record below applies to R2 PR #27 HEAD
439fc9084f88dd5c2d65bcc97efa3916285453bd before its merge. Then-pending-CI
wording is historical; completed R2 main evidence is recorded in the R3 table above.
Approved R1 starting baseline: 87f415f5290e2cab63696e1850a6c362eef97292;
[post-merge CI 42610520450](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42610520450)
completed successfully before this branch. Current source has four DEV module
instances and the same 17 resources/eight outputs; HTTP API now owns six resources.
Exactly one new address changes:

| Approved R1 address | Implemented R2 address |
| --- | --- |
| module.api_access_logs.aws_cloudwatch_log_group.this | module.http_api.aws_cloudwatch_log_group.this |


### Complete approved-R1 → R2 address correspondence

| R1 baseline address | R2 address |
| --- | --- |
| module.api_access_logs.aws_cloudwatch_log_group.this | module.http_api.aws_cloudwatch_log_group.this |
| module.artifact_bucket.aws_s3_bucket.this | module.artifact_bucket.aws_s3_bucket.this |
| module.artifact_bucket.aws_s3_bucket_ownership_controls.this | module.artifact_bucket.aws_s3_bucket_ownership_controls.this |
| module.artifact_bucket.aws_s3_bucket_policy.this | module.artifact_bucket.aws_s3_bucket_policy.this |
| module.artifact_bucket.aws_s3_bucket_public_access_block.this | module.artifact_bucket.aws_s3_bucket_public_access_block.this |
| module.artifact_bucket.aws_s3_bucket_server_side_encryption_configuration.this | module.artifact_bucket.aws_s3_bucket_server_side_encryption_configuration.this |
| module.artifact_bucket.aws_s3_bucket_versioning.this | module.artifact_bucket.aws_s3_bucket_versioning.this |
| module.http_api.aws_apigatewayv2_api.this | module.http_api.aws_apigatewayv2_api.this |
| module.http_api.aws_apigatewayv2_integration.this | module.http_api.aws_apigatewayv2_integration.this |
| module.http_api.aws_apigatewayv2_route.this | module.http_api.aws_apigatewayv2_route.this |
| module.http_api.aws_apigatewayv2_stage.this | module.http_api.aws_apigatewayv2_stage.this |
| module.http_api.aws_lambda_permission.this | module.http_api.aws_lambda_permission.this |
| module.lambda_workload.aws_cloudwatch_log_group.this | module.lambda_workload.aws_cloudwatch_log_group.this |
| module.lambda_workload.aws_iam_role.this | module.lambda_workload.aws_iam_role.this |
| module.lambda_workload.aws_iam_role_policy.this | module.lambda_workload.aws_iam_role_policy.this |
| module.lambda_workload.aws_lambda_function.this | module.lambda_workload.aws_lambda_function.this |
| module.secret_metadata.aws_secretsmanager_secret.this | module.secret_metadata.aws_secretsmanager_secret.this |

All sixteen other post-R1 addresses remain identical. The four R1 moves below
remain independently required alongside this fifth declaration, with missing or
substituted R1 mappings rejected even when a bad move set totals five. No whole-
module move, state operation or double owner is introduced. Stage uses the actual
owned bare ARN; its Route/Invoke Permission ordering and existing outputs retain
readiness dependencies. Lambda application logs stay independent.

Required access_log_group_name replaces the removed external ARN input.
Optional access_log_retention_in_days=30, access_log_deletion_protection_enabled=true,
access_log_kms_key_arn=null and separate access_log_tags={} preserve storage defaults
and reusable overrides. Existing API/Stage tags stay separate. New access_log_*
outputs expose actual group name/ARN/retention/protection/class/key; old three API
and eight root outputs keep their names and meanings. See [module interface](../infra/modules/api_gateway_http/README.md).

Generic cloudwatch_logs and its 51 tests remain unchanged without a DEV root
consumer. Its retirement is separately OPEN; it is not part of R2 acceptance.
R3 remains conditional stabilization; R4 still needs separately authorized final
main full-suite verification before new Architecture v2 features. No Live gate is
closed; unchanged 30-day secret recovery remains a 72-hour complete-teardown blocker.


## R2 local verification record

The actual 100 native API cases pass: 26 complete six-resource positive plans and
74 intentional variable/postcondition rejections. Original 47 cases map one-to-one
in [coverage.json](../infra/modules/api_gateway_http/tests/coverage.json); additional
51 integrated storage cases and two owned-ARN identity negatives add coverage.
Negative partial shapes are pinned per case, inspect all present resources and
never count as deployable workloads. Generic original 51 tests stay byte-identical.

API actual-plan checker passes all original 17 semantic mutation/19 capture-fault
families plus new cases: **28 semantic mutations, 25 capture faults**, four source
ordering/output mutations. Missing/duplicate/unexpected resources, wrong log scope,
Stage→Lambda/unrelated log destinations, weak retention/protection, sensitive headers,
anonymous authorization and broadened permission are rejected. New nullable key
output requires Terraform's actual known-null/no-op representation; other API
outputs still require create actions. Known-null fields may not disappear.

Root passes **5 native cases**, four complete 17-resource plans; **35 mutations,
22 capture faults and 12 rejected-input scenarios** remain effective. The unknown-
security-field fault now selects the owned API log's name by exact address instead
of assuming resource index zero has a name field. All four HTTP API mandatory
inputs are independently rejected when absent using the established CI fixture.

Retained R1 source mutations: three. R2 source mutations: four. Exact move-set
negatives: six, including four missing R1 mappings replaced by a fifth unrelated
move (same total count still rejected). The R1 guard preserves its historical
pre-R1 comparison purpose and can compare that snapshot cumulatively through all
five source moves; historical R1 evidence remains historical. The unchanged
Lambda IAM checker was revalidated with its existing actual full-resource capture
and genuine public SAR references against the updated source guard; its 188-case
native suite was not unnecessarily rerun for an unchanged workload implementation.

Four actual root plan pairs from approved R1 main to R2 preserve all configured
settings, policies, lifecycle and eight outputs under the single log-address map:
5→4 root calls, 17→17 resources, HTTP API 5→6, sixteen other addresses unchanged.
Only unconfigured random provider-computed metadata differences are excluded after
provider-schema/source checks. Configured resource fields and operational ARNs are
never excluded. A same-named local is not a resource configuration attribute; the
comparison extractor now scopes its inspection to actual resource bodies and tests
both exclusion of local Region and inclusion of an explicitly configured Region.
Root provider Region/account guard remain unchanged; owned ARN scope is checked.

Terraform 1.17.0 backend-disabled readonly-lock init/validate/fmt and source/scope/
secret/relative-link/diff checks are required before commit. Full unchanged
regression stays in GitHub Actions: expected native total **491** if all suites
succeed (previous R1 438 − old API 47 + new API 100), plus 153 Python tests and
unchanged independent IAM/reference/guardrail checks. This is not a completed
R2 CI claim. Nine initialized configurations and provider-cache identity/storage/
samefile/completeness guards remain unchanged. No authenticated AWS call, state
operation or actual deployed-state migration/authorization/delivery is verified.

## Historical R1 implementation status — offline source refactor

This local-development record applies to R1 PR #26 HEAD
539eaf486e1131b727838b1cd2b11dcc2869760a, before merge, from pre-R1 main
43adc3a827a265520ff822595355a91001e7e1af. Its expected/pending CI wording is
historical; completed R1 main 438/153 is recorded above, not re-executed by R3.

The four approved resource-level moves are now declared in
[DEV moved.tf](../infra/services/dev/ca-central-1/serverless-api/moved.tf):

| Previous address | Implemented destination address |
| --- | --- |
| module.lambda_function.aws_lambda_function.this | module.lambda_workload.aws_lambda_function.this |
| module.lambda_execution_role.aws_iam_role.this | module.lambda_workload.aws_iam_role.this |
| module.lambda_execution_role.aws_iam_role_policy.this | module.lambda_workload.aws_iam_role_policy.this |
| module.lambda_logs.aws_cloudwatch_log_group.this | module.lambda_workload.aws_cloudwatch_log_group.this |

Current [root main](../infra/services/dev/ca-central-1/serverless-api/main.tf) calls
artifact_bucket, secret_metadata, api_access_logs, lambda_workload and http_api.
The other thirteen full resource addresses and eight public output contracts are
unchanged. New [module](../infra/modules/lambda_workload/README.md) owns exactly
four resources. Old standalone lambda and lambda_execution_role source/tests are
retired after relocated coverage passes. Current library count is eight, not a
number-reduction acceptance target. Generic cloudwatch_logs and its original 51
cases remain unchanged for API logs and independent broader-partition validation.

Resolved interface: required function_name, role_name, partition, account_id,
region, log_group_name and versioned artifact/runtime/handler inputs; no externally
supplied role ARN or log ARN. Distinct function tags, role_tags and log_tags preserve
prior default/tag behavior. Owned log key validates integrated scope (aws/GovCloud);
generic aws-cn acceptance is independently retained. Role/log ARNs and function
bindings are actual resource references, with inline-policy readiness explicit.

The [coverage manifest](../infra/modules/lambda_workload/tests/coverage.json) maps
all old 70 Lambda and 64 role cases one-to-one; 51 additional integrated logging
adaptations and three new log-key scope negatives give 188 locally passing native
cases (45 complete four-resource positives, 143 rejected partial plans). No old
negative/mutation/reference family was deleted. Role verifier retains 14/44/5
mutation/capture/reference families, adds 15 workload/7 capture/3 source-ordering
checks and exercises 2,025 authorization witnesses. Root 5 native/35 mutations/22
capture faults and 12 input rejections pass locally. Unrelated full regression is
delegated to unchanged GitHub security suites; R1 completed CI/merge approval is
not claimed. Expected native total if all suites succeed is 438, not historical
384 rebranded. Exact PR-head CI is independently reviewed.

Four actual old/new positive root plan pairs retain 17 resource types/settings,
known bound identities and eight outputs after this mapping. Only random
unconfigured provider-computed mock metadata was ignored after schema/source
checks; no configured attribute or operational ARN was excluded. Terraform 1.17
init/validate/native plans accept the four move declarations, but empty-state mocks
do not prove actual state migration or absence of live recreation. No state/API/
plan/apply/import/destroy operation has been performed against AWS.

The following R0 design/history and R2–R4 obligations remain applicable, with this
R1 status resolving only the four destination/output decisions. API access-log
consolidation was deferred to R2 at the R1 snapshot; current R2 retains generic logging, with retirement requiring separate review.

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

All rows are intended ownership, not implemented future capability. Names/status
below distinguish historical pre-R1 source, current post-R2 ownership and future work;
R0 created no module directories.

| Intended child module | Intended responsibility | Current / future distinction |
| --- | --- | --- |
| vpc | VPC, keyed subnets, IGW/NAT/EIP, routing and compatible endpoints | V2 implements opt-in NAT/per-AZ/S3 endpoint; legacy defaults/addresses retained |
| lambda_workload | Function, dedicated execution role/policy and dedicated Lambda log resources | Implemented R1 source consolidation; no application feature changes |
| api_gateway_http | Historical HTTP API and dedicated API access logging | Six existing API/permission/log resources now owned together by R2 |
| api_gateway_rest | Regional REST methods, Cognito authorizer references, VPC Link V2, custom-domain mTLS, Regional WAF and logs | Future, subject to compatibility/security review |
| cognito_auth | User Pool, App Client, non-secret federation and AWS-managed login domain | Future; no plaintext Google secrets in Terraform |
| cloudfront_edge | Distribution/origin, edge WAF and approved origin-mTLS references | Future; PKI, pricing and global scope still reviewed separately |
| eks_platform | EKS cluster/managed nodes and cluster-specific IAM/security/access | V3 candidate private EC2 Cluster/MNG/IAM/SG/access/add-ons; no workload/controller ownership |
| private_ingress | Internal NLB, TCP:443 listener, target groups and ingress security | V4 candidate NLB/TCP/IP target group and dedicated rules in existing Platform Root; Kubernetes registration remains future |
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

## 6. Pre-R1 nine-module inventory and call sites

The following pre-R1 inventory is derived from the recorded source and DEV root,
not directory-name assumptions. Resource addresses in this table are relative to
a module instance; count/for_each instances in VPC vary by approved inputs.

| Pre-R1 module / source | Historical relative resource declarations | Pre-R1 call sites | Migration disposition / retained obligation |
| --- | --- | --- | --- |
| [`api_gateway_http`](../infra/modules/api_gateway_http/README.md) | `aws_apigatewayv2_api.this`, `aws_apigatewayv2_integration.this`, `aws_apigatewayv2_route.this`, `aws_lambda_permission.this`, `aws_apigatewayv2_stage.this` | module.http_api | Retain HTTP API; add dedicated log ownership (R2) |
| [`cloudwatch_logs`](../infra/modules/cloudwatch_logs/README.md) | `aws_cloudwatch_log_group.this` | module.lambda_logs, module.api_access_logs | Dedicated Lambda logs → lambda_workload (R1); API logs → api_gateway_http (R2); retain in R2; retirement requires separate review of legitimate consumers and verified coverage |
| [`iam_access`](../infra/modules/iam_access/README.md) | `aws_ssoadmin_customer_managed_policy_attachment.developer`, `aws_ssoadmin_permission_set.access_admin`, `aws_ssoadmin_permission_set.developer`, `aws_ssoadmin_permission_set.operator`, `aws_ssoadmin_permission_set_inline_policy.access_admin`, `aws_ssoadmin_permission_set_inline_policy.developer`, `aws_ssoadmin_permission_set_inline_policy.operator` | No service-root call | Retain independent Identity Center administration |
| [`iam_account_policies`](../infra/modules/iam_account_policies/README.md) | `aws_iam_policy.developer_secrets_manager` | No service-root call; IAM access test run account_policy_fixture uses source ../iam_account_policies | Retain workload-account policy ownership |
| [`lambda`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/43adc3a827a265520ff822595355a91001e7e1af/infra/modules/lambda/README.md) | `aws_lambda_function.this` | module.lambda_function | Consolidate into lambda_workload (R1) |
| [`lambda_execution_role`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/43adc3a827a265520ff822595355a91001e7e1af/infra/modules/lambda_execution_role/README.md) | `aws_iam_role.this`, `aws_iam_role_policy.this` | module.lambda_execution_role | Consolidate into lambda_workload (R1) |
| [`s3_artifact_bucket`](../infra/modules/s3_artifact_bucket/README.md) | `aws_s3_bucket.this`, `aws_s3_bucket_versioning.this`, `aws_s3_bucket_public_access_block.this`, `aws_s3_bucket_ownership_controls.this`, `aws_s3_bucket_server_side_encryption_configuration.this`, `aws_s3_bucket_policy.this` | module.artifact_bucket | Retain independent artifact lifecycle/state ownership |
| [`secrets_manager`](../infra/modules/secrets_manager/README.md) | `aws_secretsmanager_secret.this` | module.secret_metadata | Retain metadata-only container/external value boundary |
| [`vpc`](../infra/modules/vpc/README.md) | `aws_vpc.this`, `aws_subnet.private (keyed/counted where declared)`, `aws_subnet.public (keyed/counted where declared)`, `aws_internet_gateway.this (keyed/counted where declared)`, `aws_route_table.private (keyed/counted where declared)`, `aws_route_table.public (keyed/counted where declared)`, `aws_route_table_association.private (keyed/counted where declared)`, `aws_route_table_association.public (keyed/counted where declared)` | No service-root call | Retain and extend after R4 |

All seven pre-R1 production-code calls are in
[baseline DEV main.tf](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/43adc3a827a265520ff822595355a91001e7e1af/infra/services/dev/ca-central-1/serverless-api/main.tf). README
examples are not implemented roots; the IAM test fixture is not a human/workload
integration. At that pre-R1 snapshot generic logs had two root consumers, not a
shared log group. Current post-R2 DEV has no generic-log consumer and still calls
neither VPC nor either IAM module.

Keep IAM modules separate: Identity Center Permission Sets/references require
organization/delegated administration in the correct home Region/account;
customer-managed policies must exist in their owning workload accounts. Same IAM
domain does not imply same provider, privilege or lifecycle. Keep Secrets Manager
separate because metadata/recovery/value ownership is not the function lifecycle;
keep artifact storage separate because publication/version retention/bootstrap
state may outlive releases/functions. Neither should merge merely to reduce count.

## 7. Seventeen-resource migration matrix — R1/R2 source implemented

The left column preserves pre-R1 configured addresses at
43adc3a827a265520ff822595355a91001e7e1af. A moved.from entry is a historical
source address, **not** a currently configured resource. The destination column
records current post-R2 addresses; identity rows still exist under the same address.
The separate R2 table above maps all seventeen actual post-R1 addresses to post-R2.
No planned identifier establishes a live AWS resource/state or an executed move.

| Historical pre-R1 address | Current post-R2 configured address | Source compatibility disposition |
| --- | --- | --- |
| `module.artifact_bucket.aws_s3_bucket.this` | `module.artifact_bucket.aws_s3_bucket.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_versioning.this` | `module.artifact_bucket.aws_s3_bucket_versioning.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_public_access_block.this` | `module.artifact_bucket.aws_s3_bucket_public_access_block.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_ownership_controls.this` | `module.artifact_bucket.aws_s3_bucket_ownership_controls.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_server_side_encryption_configuration.this` | `module.artifact_bucket.aws_s3_bucket_server_side_encryption_configuration.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.artifact_bucket.aws_s3_bucket_policy.this` | `module.artifact_bucket.aws_s3_bucket_policy.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.secret_metadata.aws_secretsmanager_secret.this` | `module.secret_metadata.aws_secretsmanager_secret.this` (retain) | Precise identity mapping if retained as required; no move then needed |
| `module.lambda_logs.aws_cloudwatch_log_group.this` | `module.lambda_workload.aws_cloudwatch_log_group.this` (R1 implemented) | R1 moved declaration present; no real-state operation performed |
| `module.api_access_logs.aws_cloudwatch_log_group.this` | `module.http_api.aws_cloudwatch_log_group.this` (R2 implemented) | Fifth resource-level move declared; no real-state operation performed |
| `module.lambda_execution_role.aws_iam_role.this` | `module.lambda_workload.aws_iam_role.this` (R1 implemented) | R1 moved declaration present; no real-state operation performed |
| `module.lambda_execution_role.aws_iam_role_policy.this` | `module.lambda_workload.aws_iam_role_policy.this` (R1 implemented) | R1 moved declaration present; no real-state operation performed |
| `module.lambda_function.aws_lambda_function.this` | `module.lambda_workload.aws_lambda_function.this` (R1 implemented) | R1 moved declaration present; no real-state operation performed |
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

Inventory below records pre-R1 child outputs and their implemented R1/R2
mapping. Those source signatures are resolved; future migrations must resolve destination
signatures, compatibility exports and consumers before retiring an old source.

| Pre-R1 module | Pre-R1 output contracts | Implemented R1/R2 mapping / preservation obligation |
| --- | --- | --- |
| api_gateway_http | `api_id`, `invoke_url`, `execution_arn` | Preserve actual API/stage invoke URL/execution ARN with route/permission/stage ordering; R2 added actual dedicated-log access_log_* outputs as documented above. |
| cloudwatch_logs | `log_group_name`, `log_group_arn`, `retention_in_days`, `deletion_protection_enabled`, `log_group_class`, `kms_key_arn` | R1 owned Lambda logs: log_group_name/log_group_arn/log_group_class retained; retention_in_days→log_retention_in_days, deletion_protection_enabled→log_deletion_protection_enabled, kms_key_arn→log_kms_key_arn. Generic outputs stay reusable without a DEV root consumer; R2 resolved: corresponding access_log_group_name/group_arn/retention_in_days/deletion_protection_enabled/group_class/kms_key_arn outputs on http_api; generic outputs unchanged. |
| iam_access | `access_admin_permission_set_arn`, `developer_permission_set_arn`, `operator_permission_set_arn`, `developer_customer_managed_policy_references`, `developer_inline_policy_quota`, `developer_managed_attachment_quota` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |
| iam_account_policies | `policy_arn`, `policy_name`, `policy_path`, `policy_json`, `policy_non_whitespace_characters`, `policy_headroom_characters` | Retain current output semantics and actual references; any future contract change requires separate review, not R0 migration scope. |
| lambda | `function_arn`, `function_name`, `invoke_arn`, `version`, `execution_role_arn`, `runtime`, `architecture`, `vpc_configuration`, `log_group_name` | R1 resolved: all listed names/semantics are exported by lambda_workload from actual owned references; permission_scope binds actual group ARN. Log→policy→function ordering retained. |
| lambda_execution_role | `execution_role_arn`, `execution_role_name`, `inline_policy_name`, `log_group_arn`, `secret_read_enabled`, `permission_scope` | R1 resolved: all listed names/semantics are exported by lambda_workload from actual owned references; permission_scope binds actual group ARN. Log→policy→function ordering retained. |
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

Before R1/R2, Lambda accepted execution_role_arn/log_group_name, its role accepted
log_group_arn, and HTTP API required access_log_group_arn. Completed R1/R2 source
internalizes owned role/log references and resolves the documented input/output
contracts above. Former external-ARN cases map to equivalent owned-resource
identity/scope checks. This does not prove external consumers are absent or real
state can be migrated; user/state inventory and an authorized external plan remain
required before actual cutover.

### State move and verification limitations

R1 changes exactly four resource addresses and retains thirteen. The fifth address
change (API log) is now R2-implemented at module.http_api.aws_cloudwatch_log_group.this.
Do not assume moving directories or a module source automatically moves state.
Merging three old modules into one may need resource-level rather than one whole-
module move; exact legal source/destination scopes, retained declarations/chains,
provider addresses and supported Terraform semantics require future review.

R1 completed four mappings and R2 completed the fifth;
future migrations must compare actual old/new mock
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

The following retains pre-R1 evidence locations and continuing preservation
obligations. Retired links are immutable historical references. Current counterparts
are lambda_workload/tests/ and api_gateway_http/tests/, with explicit coverage
manifests; R1/R2 source migration is complete, while real-state migration is unverified:

| Existing evidence / path | Address/interface impact and required verification |
| --- | --- |
| [Lambda tests](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/43adc3a827a265520ff822595355a91001e7e1af/infra/modules/lambda/tests/lambda.tftest.hcl), [role tests](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/43adc3a827a265520ff822595355a91001e7e1af/infra/modules/lambda_execution_role/tests/lambda_execution_role.tftest.hcl), [logs tests](../infra/modules/cloudwatch_logs/tests/cloudwatch_logs.tftest.hcl) | R1 mapped 70/64 cases to its 188-case integrated suite; R2 retains 47 old API cases within 100. Generic 51 stay unchanged, with additional integrated storage adaptations. Preserve optional boundaries/assertions; no source-text substitute |
| [Role checker](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/43adc3a827a265520ff822595355a91001e7e1af/infra/modules/lambda_execution_role/tests/check_execution_policy.py) | Preserve exact generated trust/policy JSON, official references, permission matrix, negatives/mutations and malformed/reference-fault rejection under the new owning module/address |
| [API native tests](../infra/modules/api_gateway_http/tests/api_gateway_http.tftest.hcl), [API checker](../infra/modules/api_gateway_http/tests/check_api_gateway_configuration.py) | R2 completed six-resource inventory and deliberate partial-plan classifications: 100 native, 28 mutations/25 capture faults/4 source checks preserve the historical 47/17/19 purposes and add owned-log/security checks |
| [Root native tests](../infra/services/dev/ca-central-1/serverless-api/tests/root_integration.tftest.hcl), [root checker](../infra/services/dev/ca-central-1/serverless-api/tests/check_root_integration.py) | R1/R2 adapted the historical seven-instance map to four calls, full paths/overrides/bindings and mutation targets; retain five native cases, four complete 17-resource plans, intentional invalid-account rejection and 35/22 mutation/capture checks |
| [Root input checker](../infra/services/dev/ca-central-1/serverless-api/tests/check_required_inputs.py) | Uses native fixture header and root inputs; retained 12 rejection cases must remain real failed mock processes with complete diagnostics, not silently skip after interface changes |
| [Offline workflow](../.github/workflows/terraform-offline-ci.yml) | Module working directories, copied root lock, test capture paths, checker invocations, native counts and summary outputs, official-reference steps and shared provider-cache topology/initialized-config expectations were updated in R1/R2. Preserve pinned actions, credential isolation, locks, storage checks, read-only security and full suite |
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

The former KMS test-layer compatibility concern is resolved in source without
claiming AWS usability: generic Logs retains aws-cn syntax; Lambda workload key
references remain reviewed aws/GovCloud with expected account/Region/partition
validation; HTTP API workload scope remains aws/GovCloud while its optional log
key input preserves generic syntax-only checks. R1/R2 manifests distinguish these
layers; no China key syntax test proves a China workload or usable cross-partition
key. Real key policy/scope/service authorization remains external. Generic-module
retirement still requires a separate consumer/coverage review; none is inferred.

Each intermediate implementation PR requires affected local native/actual-plan/
negative/mutation/security checks and complete GitHub Actions regression. R4 is
additional final verification, never permission to postpone those checks. R0 itself
uses documentation-only consistency, source/link/scope/secret/diff checks and does
not rerun unrelated Terraform/Python regressions.

## 9. Required sequence and acceptance gates

| Stage | Scope / entry | Required acceptance and evidence | Authorization boundary |
| --- | --- | --- | --- |
| R0 — merged historical design | Document approved grouping, existing inventory/mappings and roadmap | Four-file documentation scope; source consistency; permanent AGENTS unchanged | No implementation or state/AWS work |
| R1 — merged source/CI (PR #26) | Previously authorized new lambda_workload and migrate dedicated function/role/log ownership | Resolve R1 destination labels/output signatures/moves; preserve four resources, security/effective settings and root outputs; adapt tests/CI/docs; affected local plus full independent CI | No new Lambda application, code delivery or network features |
| R2 — merged source/CI (PR #27) | Previously authorized API access-log ownership within api_gateway_http | Resolve R2 destination/moves and API/log outputs; retain six resources together, separate logs and exact auth/permission/log contract; retain generic logs/51 tests; retirement separately reviewed after consumers/coverage reconciled | No REST/Cognito substitution or new ingress |
| R3 — current documentation-only stabilization | Correct remaining documentation/status/provenance inconsistencies | No unresolved compatibility mapping or lost coverage, minimal justified corrections, affected local plus full CI | Not an unnecessary rewrite or deferred security fix |
| R4 — final structural baseline | R1/R2 and applicable R3 individually reviewed, CI-passed and merged with authorization | Rerun full Terraform/Python/IAM/guardrail/negative/mutation/evidence regression on exact final main; independent review of actual complete success and post-refactor inventory/case mapping | Source-text checks are insufficient; no new features before this accepted baseline |
| New Architecture v2 features — only after R4 | Separately authorized focused VPC extensions then later approved functional modules | Preserve private-only VPC behavior/current 16 tests; add actual NAT/EIP/per-AZ/endpoint/security contracts and affected tests/full CI; approved account/IP/backend/provider/cost details still required | No default standalone NAT/core/private-routing wrappers; later EKS/REST/Cognito/edge/mTLS/DB/delivery/DEV access tasks remain separate |

**R0 → R1 → R2 → R3 → R4 → new Architecture v2 features.** R3 was conditional
and is now authorized for the documentation inconsistencies recorded above; no
implementation stabilization is inferred. Only independent review confirms exact-head CI and merge authorization;
Codex still stops after opening each PR without waiting/polling for CI. For R4,
its separately authorized task/process must trigger/reuse the complete regression
at final main and hand off the exact SHA/run for independent completed-result
verification. It cannot declare R4 passed while evidence is pending or infer it
from individual earlier branch runs. R0 does not execute or open R1–R4 PRs.

## 10. Approved versus OPEN and preserved Live boundaries

| Approved design | Still OPEN before corresponding implementation |
| --- | --- |
| Coherent functional grouping, integrated vpc ownership and shallow composition | Safe per-AZ routing inputs/addresses, endpoints/security compatibility and resource lifecycle edge cases |
| lambda_workload consolidation and API-owned dedicated logs | R1/R2 source names/interfaces/five moves/test adaptations are resolved; actual real-state/user inventory, authorized cutover and deployed behavior remain OPEN |
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
functionality or Live validation is claimed by the retained R0 design, R1/R2 offline refactors or R3 documentation stabilization.
