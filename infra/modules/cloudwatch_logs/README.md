# Reusable CloudWatch Logs storage

This child module manages exactly one `aws_cloudwatch_log_group`: a stable name,
finite retention, service deletion protection, an optional existing KMS key
reference and caller-provided tags. It implements log storage and lifecycle
configuration only. No service root or Lambda module is integrated in this phase.

It creates no log streams, IAM roles/policies/attachments, KMS resources, Lambda
functions, subscription/metric filters, alarms, dashboards, API Gateway, network
resources, S3 artifacts or deployment pipelines. Roots own providers and backends.
There are no data-source lookups or random names.

## Inputs and effective Terraform configuration

| Input | Type | Effective source / default | Validation |
| --- | --- | --- | --- |
| `name` | string | Required **Root Override** | 1–512 ASCII letters/digits or `_ . / # -`; reject literal prefix `aws/`, allow `/aws/lambda/...` |
| `retention_in_days` | number | **Module Default** `30`; **Root Override** permitted | Only the 22 finite API/provider values below; no zero or indefinite retention |
| `deletion_protection_enabled` | bool | **Module Default** `true`; explicit **Root Override** permitted | Boolean; false is an intentional operational decision |
| `kms_key_arn` | string | **Module Default** `null`; **Root Override** references an existing key | Complete key ARN ≤256 characters, explicit supported partition/region/account and UUID or `mrk-` identifier; no aliases, bare IDs or wildcards |
| `tags` | map(string) | **Module Default** `{}`; **Root Override** permitted | ≤50 entries; keys 1–128 and values 0–256 Unicode characters; non-null values and no case-insensitive `aws:` prefix |

Finite retention days are **1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365,
400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653**. These match AWS
Provider 6.72.0 and the AWS PutRetentionPolicy API. Unsupported integers,
fractions, negatives and `0` are rejected with a variable-specific error.

Tags accept Unicode letters, separators and numbers plus `_.:/=+-@` as specified
by the TagResource API. Its value limit is 256 and it permits colons; a working
with log-groups guide contains older conflicting guidance, so validation follows
the normative API. Names, tags and other metadata must never contain secrets.
The module invents or overwrites no `Project` or `Name` tag. Root provider
`default_tags` remain root-owned; review the merged effective tags and total tag
count when composing a root.

These settings are **Module Fixed**, with no override switches:

| Setting | Value |
| --- | --- |
| Resource inventory | One CloudWatch Log Group |
| `log_group_class` | `STANDARD` |
| `skip_destroy` | `false`; no state-orphaning deletion shortcut |
| Naming | Explicit `name`; no generated prefix/suffix |
| IAM/KMS/streams/integration | Not managed by this module |

These are the configured Terraform values. Account-level retention policies can
override a group's configured period; this module does not inspect account
policies or prove the real effective retention policy.

## Retention, protection and intentional teardown

The default 30-day period bounds storage growth instead of silently retaining
events indefinitely. Shortening retention can irreversibly expire older events;
raising it later does not restore them. AWS expiry deletion can lag, typically up
to 72 hours. Service deletion protection guards log-group deletion; it does not
replace retention policy or preserve expired events.

An authorized owner must first set `deletion_protection_enabled = false`, obtain
the required plan review **outside Codex Cloud**, and apply that configuration.
Only a later authorized teardown can delete the group. Provider 6.72.0 does not
automatically disable protection during deletion. A destroy/replacement attempted
while protection remains enabled is expected to fail, preserving the resource.
Disposable dev environments can choose false explicitly; it is never the default.

`skip_destroy` stays false. The module does not remove a live group from state as
an alternative to deletion. A stable name avoids accidental replacement; name
changes or class changes in future implementations require review for replacement
and data loss. No `ignore_changes` hides retention, encryption, protection or tag
drift. A future authorized refreshed plan must review drift before restoring it.
An already existing same-named group needs a reviewed ownership/import decision,
not an attempted duplicate creation. No import or migration is performed here.

## KMS ownership and historical logs

With no explicit key, CloudWatch Logs uses its normal service-managed encryption
at rest. A non-null input references an existing customer-managed key; this module
creates no key, alias, grant, key policy or permissions.

Before real deployment, the owner must verify the key's region/account, enabled
status and symmetric suitability, regional CloudWatch Logs service authorization,
and caller permissions. The key policy must use the appropriate regional Logs
service principal and the correct `kms:EncryptionContext:aws:logs:arn` log-group
context; `kms:ViaService` restrictions require the appropriate execution design.
A syntactically valid ARN proves none of those prerequisites.

Keep access to keys used for historical events. Disassociating/changing a key
affects new ingestion; it does not re-encrypt old events. Disabling/deleting a key
or revoking its permissions can make historical logs unreadable. Key association
changes can take time to become effective. `mrk-` is accepted only as an existing
key identifier; no replication or disaster-recovery orchestration is introduced.

## Outputs and ARN semantics

All outputs read `aws_cloudwatch_log_group.this` attributes:

| Output | Resource source |
| --- | --- |
| `log_group_name` | `name` |
| `log_group_arn` | `arn`, unchanged from the provider |
| `retention_in_days` | `retention_in_days` |
| `deletion_protection_enabled` | `deletion_protection_enabled` |
| `log_group_class` | `log_group_class` |
| `kms_key_arn` | `kms_key_id`, the actual provider resource reference |

No ARN is predicted or constructed by the module. AWS exposes an ARN form ending
in `:*` and a bare `logGroupArn`; Provider 6.72.0 explicitly strips the API's
trailing `:*` from its resource `arn`. The output is a group identity reference,
**not an IAM grant and not a log-stream resource pattern**.

A later reviewed workload IAM module must scope `logs:CreateLogStream` and
`logs:PutLogEvents` to log streams using the documented form:

```text
arn:<partition>:logs:<region>:<account>:log-group:<group-name>:log-stream:<stream-name>
```

For this pinned provider's bare output, a future expression is
`"${module.log_storage.log_group_arn}:log-stream:*"`. Do not pass the bare group
ARN as though it were a stream ARN, or blindly reuse an API's `:*` suffix for
every operation. Other Logs actions can require different resource types; verify
their authorization reference when implementing IAM. This module grants nothing.

## Future Lambda contract — not implemented

In a later service root, provision the log group before deploying and invoking
the Lambda function. Pass `module.log_storage.log_group_name` to the existing
Lambda module's `log_group_name` input so the resource reference expresses the
normal Terraform dependency. No current root or Lambda implementation changes.

The separately reviewed execution role needs scoped `logs:CreateLogStream` and
`logs:PutLogEvents` permissions. Do not compensate for missing provisioning by
granting `logs:CreateLogGroup` or attaching `AWSLambdaBasicExecutionRole`. An
overprivileged role can let Lambda automatically create a missing custom group,
leaving storage untracked by Terraform. Preventing that fallback requires proper
integration order and IAM scope; this storage module cannot prove it by itself.

The following future root example is documentation only; its source path assumes
the repository's service-root depth. It adds no Phase 4 integration:

```hcl
module "log_storage" {
  source = "../../../../modules/cloudwatch_logs"
  name   = "/portfolio/dev/serverless-api" # Required Root Override.

  # Module Defaults: retention 30, protection true, no explicit CMK, no tags.
  retention_in_days = 60 # Root Override, chosen after lifecycle/cost review.
  tags              = { Project = "portfolio", Environment = "dev" }
}
```

## Cost, scope and mock verification

STANDARD ingestion, stored volume, queries and optional customer-managed KMS
operations can incur costs. Finite retention helps bound storage but does not
provide budgets, alarms, workload redaction or a guarantee that logs contain no
sensitive data. Those remain separate application and operational responsibilities.
Secrets Manager Approach A is unchanged; secret values never belong in logs,
Terraform metadata, plans, state or outputs.

Use Terraform 1.17.0 and AWS Provider 6.72.0. In a fresh module checkout, seed only
a transient child lock from the unchanged root lock; preserve/inspect any existing
child lock before doing so. With AWS credentials/configuration absent, shared
files set to `/dev/null` and metadata lookup disabled, run:

```sh
cp ../../services/dev/ca-central-1/serverless-api/.terraform.lock.hcl .terraform.lock.hcl
terraform fmt -check -recursive
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Tests use `mock_provider "aws" {}`, explicit `command = plan`, synthetic
references and deterministic computed ARN fixtures. CI inspects actual positive
plans for one log group and no unrelated resources, requires no resource changes
for rejected inputs, verifies defaults and checks complete unique summaries and
process status. Failure-injection checks exercise the checker itself. Verbose
mock output and transient locks are neither committed nor uploaded as artifacts.
The current suite passes **51 tests: 18 positive plans and 33 intended variable
validation failures**. The CI checker accepted that actual capture and rejected
all **30** injected process, completeness, count, inventory, default and lifecycle
faults for the intended reason. Existing regressions retain 180 native mocks and
153 Python tests, alongside policy-reference, negative/equivalence and independent
guardrail checks.

No actual logs, KMS operations, credentials, service API calls or deployment are
used. Mock evidence does not establish real retention enforcement, successful
ingestion, key usability or effective workload authorization.

Official references: [pinned provider resource](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/cloudwatch_log_group.html.markdown),
[CreateLogGroup](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_CreateLogGroup.html),
[retention](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_PutRetentionPolicy.html),
[deletion protection](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_PutLogGroupDeletionProtection.html),
[TagResource constraints](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_TagResource.html),
[KMS encryption](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html),
[Logs authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_logs.html).
