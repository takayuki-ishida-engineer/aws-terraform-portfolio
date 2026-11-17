# Lambda workload — R1 coherent ownership

This child owns exactly one aws_lambda_function.this, aws_iam_role.this,
aws_iam_role_policy.this and aws_cloudwatch_log_group.this. No nested helpers,
providers, backends, secret values, artifact objects or API/network resources.
It consolidates the previous independent Lambda/execution-role/dedicated logging
implementations for human maintainability, not new application functionality.
Generic [CloudWatch Logs](../cloudwatch_logs/README.md) remains independently tested
with no current DEV root consumer. Completed R2 places the API access log inside
[api_gateway_http](../api_gateway_http/README.md); generic logging retirement needs
separate review.

## Interface and effective configuration

Root Override is an explicit caller input; Module Default is an omitted optional
input's declared default; Module Fixed is a resource setting without an override.
Required scope inputs describe the expected account, not an authenticated identity.
The root must select/restrict the provider; mocks authenticate no AWS account.

| Input | Default / requirement |
| --- | --- |
| `function_name` | Required non-secret input |
| `description` | `null` |
| `s3_bucket` | Required non-secret input |
| `s3_key` | Required non-secret input |
| `s3_object_version` | Required non-secret input |
| `runtime` | Required non-secret input |
| `handler` | Required non-secret input |
| `architecture` | `"x86_64"` |
| `memory_size` | `128` |
| `timeout` | `10` |
| `ephemeral_storage_size` | `512` |
| `environment_variables` | `{}` |
| `layers` | `[]` |
| `reserved_concurrent_executions` | `null` |
| `subnet_ids` | `[]` |
| `security_group_ids` | `[]` |
| `log_group_name` | Required non-secret input |
| `tags` | `{}` |
| `policy_name` | Required non-secret input; name of the one inline workload policy, for example `<project>-<env>-policy-lambda` |
| `role_name` | Required non-secret input |
| `partition` | Required non-secret input |
| `account_id` | Required non-secret input |
| `region` | Required non-secret input |
| `enable_secret_read` | `false` |
| `secret_arn` | `null` |
| `secret_kms_key_arn` | `null` |
| `role_tags` | `{}` |
| `log_retention_in_days` | `30` |
| `log_deletion_protection_enabled` | `true` |
| `log_kms_key_arn` | `null` |
| `log_tags` | `{}` |

The dedicated owned group name is explicit; no external role ARN or group ARN is
accepted. Function role and logging references use actual internally owned resource
outputs. partition/account/Region support remains aws and reviewed GovCloud families,
not China/isolated partitions. Shape/range checks do not establish enabled Regions,
account ownership or service access. Layers remain same-partition version references.

Separate `tags` (function), `role_tags` and `log_tags` preserve each former caller
contract/validation; all default to empty maps. The module adds `Name` and `service`
(see [deployment configuration](../../../docs/deployment-configuration.md#5-tags)), so each map accepts 48 other
tags within the 50-tag limit. Root provider default_tags remain
separate and are not synthesized or replaced. Owned log CMK references must match
expected workload partition/Region/account. This integrated scope is deliberately
different from generic logging's broader independently tested aws-cn syntax; do not
weaken role scope to accept unsupported partitions. This scoped interface is not a
claim of cross-account/partition key usability. No KMS resources are created.

| Setting | Effective source |
| --- | --- |
| Explicit names, expected account/Region/partition, approved S3 key/version, runtime/handler | Root Override; no invented production artifact/account defaults |
| Compute, architecture, layers, environment/VPC/concurrency, log retention/protection/CMK and per-resource tags | Module Default unless caller explicitly overrides; preserve each variable's validation |
| ZIP, publish=false, Text logging, PassThrough tracing | Module Fixed |
| IAM role path=/, max session=3600 and Lambda-only trust | Module Fixed |
| Inline policy name | Root Override through required `policy_name` |
| `Name` and `service` tags: function `function_name`/`lambda`, role `role_name` (`,` replaced by `-`)/`role`, log group `log_group_name` (first 256 characters, `#` replaced by `-`)/`lambda` | Module Fixed, winning over caller tags |
| STANDARD log class, skip_destroy=false, owned-resource bindings, log→policy→function readiness | Module Fixed |
| Optional secret/CMK grants | Fixed exact least-privilege policy construction controlled by genuine enable_secret_read and exact reference inputs |

Function compute defaults: x86_64, 128 MB, 10 seconds, 512 MB ephemeral storage;
no layers/VPC/environment/reserved-concurrency override. Optional VPC references
retain syntax/count/pair validations but do not grant ENI permissions or prove
network connectivity. VPC-enabled use needs separately reviewed authorization;
the historical DEV workload remains outside a VPC.

Dedicated log defaults are 30 days, deletion protection true, no explicit CMK.
Finite supported retention ranges, explicit protection override, name/key/tag
validation and their boundaries are tested. A log CMK requires external key policy/
service authorization; it adds no secret-key Decrypt grant to the execution role.

| Validation boundary | Accepted configuration |
| --- | --- |
| Names/description | Function: 1–64 ASCII letters/digits/underscore/hyphen; role: 1–64 IAM name characters, no path; log: 1–512 supported characters, no literal aws/ prefix; description null or ≤256 characters |
| Artifact | Explicit DNS bucket name, literal nonblank key ≤1,024 UTF-8 bytes and printable immutable version ≤1,024 characters; null-version sentinel, URI and reserved bucket forms rejected |
| Runtime/handler | nodejs22.x, python3.13 or java21, with matching reviewed handler syntax; x86_64 or arm64 |
| Compute | Integer memory 128–10,240 MB, timeout 1–900 seconds, ephemeral storage 512–10,240 MB; reserved concurrency null or integer 0–2,147,483,647 (zero disables invocation; quotas remain external) |
| Environment | Non-null values, non-reserved keys of at least two characters starting with a letter; combined UTF-8 keys/values ≤4,096 bytes; validation cannot detect secret plaintext |
| Optional references | ≤5 distinct versioned same-partition layer ARNs; paired VPC lists with ≤16 distinct subnets and ≤5 distinct groups, valid legacy/current ID shapes |
| Tags | Each map ≤50 entries, keys 1–128 and non-null values ≤256 characters, no case-insensitive aws: prefix; role/log maps retain their narrower IAM/Logs Unicode character checks |
| Retention | Finite days: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653; zero/indefinite rejected |
| Scope/keys | Explicit 12-digit account and compatible reviewed partition/Region; full secret ARN with six-character suffix; exact UUID/mrk key ARN ≤256 characters, no aliases/wildcards; keys and secret must match expected scope |

## IAM, secrets and actual-reference ownership

Trust is only lambda.amazonaws.com / sts:AssumeRole. Default policy grants only
logs:CreateLogStream and logs:PutLogEvents beneath the actual bare owned log ARN
plus :log-stream:*. No CreateLogGroup, PassRole, administrative, S3 artifact or ENI
rights. Internal role/log ARN postconditions reject unexpected provider-computed
scope/identity; they may defer during a real plan and do not authenticate a provider.

Optional enable_secret_read grants only GetSecretValue/DescribeSecret on one exact
full externally managed metadata ARN, with reviewed partition/account/Region/suffix
validation. Disabled requires null secret/key and adds no Secrets Manager/KMS grant.
Optional secret_kms_key_arn grants only exact-key kms:Decrypt with StringEquals
kms:ViaService, kms:EncryptionContext:SecretARN and kms:CallerAccount. No broader
KMS access. Secret values/rotation stay outside Terraform (Approach A); neither
metadata nor permission initializes AWSCURRENT or implements application retrieval.

Non-secret environment references remain caller-controlled and are independent of
permission grants. The DEV root supplies only actual SECRET_ARN when secret reading
is enabled and no secret variable when disabled; generic environment configuration
never authorizes a secret or permits plaintext values.

The role/policy stream reference waits for the actual log group; function references
actual role ARN and log group name, with an explicit depends_on on the inline policy.
A role ARN alone would not order its policy. This source contract and actual plan
bindings are checked; no propagation, effective deployed permission or delivery proof.

## Outputs

`function_arn`, `function_name`, `invoke_arn`, `version`, `runtime`, `architecture`, `vpc_configuration`, `execution_role_arn`, `execution_role_name`, `inline_policy_name`, `log_group_arn`, `secret_read_enabled`, `permission_scope`, `log_group_name`, `log_retention_in_days`, `log_deletion_protection_enabled`, `log_group_class`, `log_kms_key_arn`.

Outputs read actual resource attributes or reviewed non-secret input scope; no
credential/value/environment-map outputs. Function version is provider metadata
with publish=false, not a new immutable release or alias. permission_scope carries
expected scope, actual owned log ARN and exact secret/key references only.

## R1 compatibility and verification

The R1 results below describe that migration snapshot. Current post-R2 root has
five cumulative moves and four module instances; see the
[current migration record](../../../docs/repository-structure-strategy.md).

Four root resource-level moved declarations map old function/role/policy/Lambda-log
addresses into module.lambda_workload with the same resource type and this label.
The other thirteen root addresses and eight public outputs are preserved. Terraform
1.17 backend-disabled init/validate and native tests accept these declarations;
no state move/import/apply/destroy was performed. Actual previously deployed state
and recreation avoidance need a separately authorized external real plan review.

[coverage.json](tests/coverage.json) maps every former 70 Lambda and 64 role case
one-to-one to the actual integrated module, including replaced external-reference
cases as owned ARN/identity/postcondition checks. The unchanged generic 51 logging
cases remain in their module; 51 additional integrated adaptations plus three new
log-key scope negatives and one invalid `policy_name` negative give **189 local
passing native cases**, 45 complete four-resource positives and 144 intentionally
rejected partial plans. Generic China
key acceptance remains independent; integrated China rejection is intentional.
These new counts do not rewrite historical 384/153 baseline evidence.

The [actual-plan checker](tests/check_execution_policy.py) inspects all four
resources and outputs, actual IAM/trust/reference JSON, 2,025 static authorization
witnesses, all 14 prior unsafe-Allow mutations, 44 capture faults and five reference
faults. It adds 15 actual-workload ownership/artifact/logging mutations, seven
capture faults and three source dependency mutations. Partial plans have reviewed
per-case shapes in [rejected_shapes.json](tests/rejected_shapes.json), validate all
present resources/grants and are never complete workload configurations.

The [move/ownership comparator](tests/check_r1_migration.py) checks four exact
moves/five root calls and compares old/new actual root plan pairs by address mapping.
Local comparison verified four 17-resource plan pairs and eight identical outputs,
with no unexplained configured-field differences. Only unconfigured SDK-computed
random mock metadata was excluded after checking provider schema and both source
attribute sets; no operational ARN or configured field was ignored. It does not
prove actual state migration. No test invokes AWS account APIs.

## Credential-free local commands

From this directory use Terraform 1.17.0 and the root's approved 6.72.0 lock/cache
strategy (a transient copied child lock is not committed):

```sh
terraform fmt -check -recursive
terraform init -backend=false -input=false -lockfile=readonly -no-color
terraform validate -no-color
terraform test -no-color -json -verbose > "$events"
```

Set events to a temporary path outside Git. Pass the actual Terraform exit code
and public Logs/Secrets Manager/KMS SAR JSON to check_execution_policy.py using
--test-events, --terraform-exit-code, --logs-reference, --secretsmanager-reference,
--kms-reference and --self-test. Failure/skip/incomplete evidence fails closed.
The root and checker run without AWS credentials; old standalone implementations
are retired only after relocated coverage succeeds. Full unchanged regression is
GitHub Actions' responsibility; no completed PR CI is claimed here.

## Artifacts, lifecycle, cost and limits

The S3 ZIP must already be externally published with exact immutable key/version;
this module packages/uploads/discovers nothing. Empty-bucket bootstrap remains a
separately approved staged/state-ownership problem. No dummy ZIP, runtime code,
alias/version delivery, API, new network or R2 functionality is introduced.

Log deletion protection must first be disabled through approved operations before
later deletion; skip_destroy is not a bypass. Log/compute/artifact/secret use can
incur costs. Secrets/keys/IAM/SCPs/key policies/service propagation and actual
connectivity/log delivery remain external. DEV Live needs all G01–G07 approvals,
cumulative actual JPY 10,000 and verified full cleanup within 72 hours; unchanged
30-day secret recovery is a separate Live blocker. This refactor authorizes no
Live operation and weakens no historical deletion safeguards.
