# Reusable Lambda function

This child module manages **one `aws_lambda_function`** with a versioned S3 ZIP
artifact, explicit runtime/handler and existing execution-role/log-group
references. It is Phase 3 module development. No service root calls it yet.

It creates no IAM role/policy/attachment, log group, bucket, artifact, secret,
network resource, API Gateway, invocation permission, event source or pipeline.
Provider configuration and backends belong in roots. There are no data-source
lookups that claim to verify external resources during offline testing.

## Inputs and effective configuration

Only a reviewed runtime subset is supported: `nodejs22.x`, `python3.13`, `java21`.
Runtime and handler have no defaults. All three support the two exposed
architectures; binary dependencies and layer compatibility still require external
verification. Expanding runtime support requires review and appropriate tests.

Required inputs are **Root Override** values supplied by the future owning root:

| Input | Type | Contract |
| --- | --- | --- |
| `function_name` | string | Bare Lambda name, 1–64 letters/digits/underscore/hyphen; no ARN or qualifier |
| `execution_role_arn` | string | Existing IAM role ARN, including an explicit supported partition/account and optional role path; no STS session or wildcard |
| `s3_bucket` | string | Existing S3 bucket name; the external artifact owner enables versioning |
| `s3_key` | string | Explicit nonempty object key; a package reference, not a local filename or S3 URL |
| `s3_object_version` | string | Explicit immutable version ID; blank, null and the mutable literal `null` version are rejected |
| `runtime` | string | One of the reviewed runtimes above |
| `handler` | string | Explicit runtime-appropriate handler; Java supports class-only or `Class::method` forms |
| `log_group_name` | string | Existing log group, 1–512 supported characters; literal `aws/` prefix is forbidden, while `/aws/lambda/...` is valid |

Optional inputs use **Module Default** values unless the root supplies a
**Root Override**:

| Input | Type | Module Default | Validation / operational intent |
| --- | --- | --- | --- |
| `description` | string | `null` | Optional non-secret description, at most 256 characters |
| `architecture` | string | `x86_64` | `x86_64` or `arm64`; compiled packages/layers must match |
| `memory_size` | number | `128` | Whole MB, 128–10240; standard on-demand Lambda scope |
| `timeout` | number | `10` | Whole seconds, 1–900; downstream timeouts need separate design |
| `ephemeral_storage_size` | number | `512` | Whole MB, 512–10240 for `/tmp`; useful for legitimate temporary processing, never durable storage |
| `environment_variables` | map(string) | `{}` | Non-secret configuration/references only; valid keys, non-null values and bounded aggregate UTF-8 size |
| `layers` | list(string) | `[]` | Up to five distinct versioned Lambda layer ARNs; same partition as the role, no floating version |
| `reserved_concurrent_executions` | number | `null` | No configured override. Explicit integer 0–2147483647; actual account capacity must be verified separately. `0` blocks invocation |
| `subnet_ids` | list(string) | `[]` | At most 16 distinct format-valid subnet IDs; requires security groups |
| `security_group_ids` | list(string) | `[]` | At most five distinct format-valid security-group IDs; requires subnets |
| `tags` | map(string) | `{}` | Additional visible, non-secret tags; no module-owned Name/Project tags |

See [variables.tf](variables.tf) for exact validation expressions. Validation
checks input shape and known constraints; it cannot prove external existence,
trust, permissions, region, network reachability or application compatibility.

These settings are **Module Fixed**, with no override switch in this phase:

| Setting | Effective value |
| --- | --- |
| Resource inventory | One Lambda function |
| Package source/type | S3 bucket/key/object version; `Zip` |
| Lambda version publishing | `false`; no alias or published-version management |
| Logging format | `Text`, directed to the supplied existing log group |
| Tracing mode | `PassThrough`; no automatic X-Ray enablement or grant |
| Empty VPC/environment inputs | Omit the corresponding blocks |
| Secret handling | Names/ARNs only; no actual values and no Secrets Manager resources |

Root provider `default_tags` remain a root responsibility and can affect
provider-computed effective tags. The module passes its explicit `tags` map
without inventing environment, service or authorization metadata.

## Artifact ownership and versioning

The future deployment pipeline builds a compatible ZIP, uploads it to an existing
versioned S3 bucket and passes the exact bucket/key/version. Terraform neither
packages nor uploads code. Object versions are immutable references; updating
the version is an intentional code change requiring an authorized plan review
outside Codex Cloud. The S3 version ID is different from Lambda's function version.

Before any real deployment, an authorized owner must verify the bucket is in the
function's region, the object version exists, bucket access permits the deployment
operation, and the archive, handler, runtime, architecture and layers are
compatible. ZIP size/unpacked size, account quotas, deprecation dates and any
external encryption requirements also need verification. Inputs do not inspect
the artifact. Container images and local `filename` builds are outside this module.

## Workload execution role and secrets

The supplied role must already exist with an appropriate Lambda service trust
policy and separately reviewed least-privilege workload permissions. This module
does not create trust relationships or grant CloudWatch, VPC ENI, Secrets Manager,
KMS or X-Ray access. Deployment authorization, including a narrowly scoped
`iam:PassRole` if required, is also external. Human-access Permission Sets and
account policies remain unchanged by this phase.

Use environment entries such as `SECRET_ARN` or a secret name as non-secret
references. Applications retrieve values with the AWS SDK at runtime, subject to
separately reviewed IAM/KMS policies and connectivity. **Never supply an actual
secret value** in variables, environment maps, outputs or tags. Terraform stores
environment configuration in plans/state; declaring it sensitive would not stop
that storage. Validation cannot determine whether arbitrary text is a secret.
Review inputs for this contract. Secrets Manager Approach A remains unchanged.

## Logging and provisioning order

Provision the log group and its retention, encryption and operational policy in a
separately reviewed module before the function. The function configures the
provider-supported `logging_config.log_group` and fixed Text format; this module
does not manage retention or a log group.

The execution role needs narrowly scoped `logs:CreateLogStream` and
`logs:PutLogEvents` for that existing group's streams. Do not grant
`logs:CreateLogGroup` just to compensate for a missing dependency. Lambda can
automatically create a missing custom group on invocation when an overprivileged
role permits it, producing an externally untracked group. If the group is absent
and creation is denied, logging can fail. Offline mocks cannot prove existence
or delivery. Provisioning order, retention and role scope are external controls.

## Optional VPC attachment

Empty subnet/security-group lists mean no VPC attachment. Supply both lists to
enable attachment; incomplete lists are rejected. IDs alone cannot establish
ownership, same VPC/region, available IP capacity or network policy. The external
role needs reviewed Lambda VPC ENI permissions, and deployment must verify the
chosen subnets and security groups.

A private subnet does not automatically reach Secrets Manager or other public
AWS endpoints. Plan suitable NAT or service VPC endpoints, routing, DNS and
egress rules in separately reviewed modules. This module creates none of them.
Attaching to a public subnet does not itself give the function a public IP.

## Outputs

| Output | Source / meaning |
| --- | --- |
| `function_arn` | Actual function `arn` attribute |
| `function_name` | Actual function `function_name` attribute |
| `invoke_arn` | Actual provider `invoke_arn`; no API Gateway is created |
| `version` | Actual function `version`; normally `$LATEST` with publishing disabled |
| `execution_role_arn` | Configured function `role` reference |
| `runtime` / `architecture` | Configured resource runtime and single architecture |
| `vpc_configuration` | Configured subnet/security-group references, empty sets when detached |
| `log_group_name` | Configured logging destination |

These are operational metadata, not secret values or application payloads.
Provider-generated ARNs are read from resource attributes rather than constructed.

## Future root example — not implemented

The following is documentation for a potential future owning service root. It
does not modify the existing dev root, create dependencies, or authorize Phase 4
integration/deployment. Every referenced root variable is a future input.

```hcl
module "handler" {
  source = "../../../../modules/lambda"

  function_name      = "portfolio-api-handler"
  execution_role_arn = var.lambda_execution_role_arn
  s3_bucket          = var.lambda_artifact_bucket
  s3_key             = var.lambda_artifact_key
  s3_object_version  = var.lambda_artifact_version
  runtime            = "java21"
  handler            = "org.example.Handler::handleRequest"
  log_group_name     = var.lambda_log_group_name

  memory_size = 512 # Root Override; Module Default is 128 MB.
  environment_variables = {
    SECRET_ARN = var.application_secret_arn # Reference only; never a value.
  }
  tags = { Environment = "dev", Project = "portfolio" }
}
```

## Costs, risks and mock verification

Memory, duration, request volume and `/tmp` allocation above the included amount
affect Lambda costs. Logs, S3 artifact versions and externally provisioned NAT or
endpoints have separate costs. Reserved concurrency consumes account capacity;
zero disables invocation. This module adds no provisioned concurrency, retention
policy, alarms, retry strategy, trigger, alias or rollout/rollback pipeline.
Artifact rollback and operational readiness need later reviewed composition.

Use Terraform 1.17.0 with AWS Provider 6.72.0. Seed a transient child lock from the
unchanged dev-root lock, then run the following **credential-free mock checks**:

```sh
cp ../../services/dev/ca-central-1/serverless-api/.terraform.lock.hcl .terraform.lock.hcl
terraform fmt -check -recursive
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Run from this module with shared AWS configuration/credentials set to `/dev/null`
and metadata lookup disabled, as in the repository's offline CI. Native tests use
`mock_provider "aws" {}`, explicit `command = plan`, synthetic names/references
and deterministic computed-attribute overrides. All 70 tests cover 13 positive
plans and 57 intended input-validation failures. CI inspects every positive plan
for exactly one Lambda function, requires empty plans for input rejections, and
verifies the default artifact, role, logging, compute and omitted optional
settings. No ZIP, AWS credential, real
service plan, API call or deployment is needed. Mock success does not establish
real execution, external dependencies or effective deployed-role authorization.

Official references: [pinned provider resource](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/lambda_function.html.markdown),
[CreateFunction](https://docs.aws.amazon.com/lambda/latest/api/API_CreateFunction.html),
[quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html),
[runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html),
[environment configuration](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html),
[log groups](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs-loggroups.html),
[VPC connectivity](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html).
