# Lambda workload execution role

This child module owns exactly one `aws_iam_role` and one
`aws_iam_role_policy`. Its identity policy grants stream writes under one existing
log group, optionally reads one exact secret, and optionally decrypts that secret
through Secrets Manager with one exact customer-managed key. It does not create
Lambda, logs, secrets, keys, networking, deployment identities or human Permission
Sets. No service root is integrated in this phase.

## Inputs and effective configuration

| Input | Type | Source / contract |
| --- | --- | --- |
| `role_name` | string | Required **Root Override**; stable IAM name, 1–64 supported ASCII characters, no path/ARN/wildcard |
| `partition` | string | Required **Root Override**; `aws` or `aws-us-gov` |
| `account_id` | string | Required **Root Override**; expected 12-digit workload account |
| `region` | string | Required **Root Override**; explicit workload region consistent with the partition |
| `log_group_arn` | string | Required **Root Override**; exact existing bare ARN from the CloudWatch Logs module, matching partition/account/region |
| `enable_secret_read` | bool | **Module Default** `false`; **Root Override** true enables one secret's runtime read permissions |
| `secret_arn` | string | **Module Default** `null`; required when enabled and forbidden when disabled; actual full resource-generated ARN with six-character suffix, same scope |
| `secret_kms_key_arn` | string | **Module Default** `null`; optional exact existing UUID/MRK key ARN for the enabled secret, same scope, ≤256 characters |
| `tags` | map(string) | **Module Default** `{}`; caller-owned non-secret tags with IAM size/count/character constraints and no reserved `aws:` prefix |

The expected account/reference checks **do not select or authenticate the AWS
provider**. A future owning root must restrict its provider with the expected
`allowed_account_ids`, select the intended partition/region, and verify real
resource ownership. There are no caller-identity or other data-source lookups.
ARN consistency is not proof that the provider would create the role in that
account.

Commercial AWS and GovCloud are the reviewed scope. China (`aws-cn`) and other
partitions are explicitly rejected; the fixed Lambda trust contract there has
not been established by this implementation. KMS's documented ViaService rule
uses `.amazonaws.com` in **all partitions**; it is different from ordinary DNS
endpoint suffix selection and must not be inferred as `.amazonaws.com.cn`.

**Module Fixed** settings are the two-resource inventory, role path `/`, IAM
`max_session_duration = 3600`, inline policy name `LambdaWorkloadAccess`, exact
Lambda trust, approved action sets and resource/condition construction below.
The session-duration attribute is not a guarantee of Lambda service credential
lifetime. No arbitrary policy JSON, principal, managed-policy attachment or
generic service-permission inputs are exposed.

## Trust and complete permission matrix

The trust document is JSON-encoded IAM language version `2012-10-17`, with one
Allow for service principal **`lambda.amazonaws.com`** and action
**`sts:AssumeRole`**. It has no users/account principals, cross-account trust,
wildcards, self-assumption, OIDC or unverified SourceArn/SourceAccount conditions.
That trust is distinct from the role's identity permissions; it grants no ability
for function code to assume other roles.

| Mode | Identity actions | Resource | Conditions |
| --- | --- | --- | --- |
| Always | `logs:CreateLogStream`, `logs:PutLogEvents` | `<exact bare log-group ARN>:log-stream:*` | No additional condition; account/region/group are fixed in the ARN |
| Secret read enabled | `secretsmanager:GetSecretValue`, `secretsmanager:DescribeSecret` | Exact full `secret_arn` | No wildcard or additional secret |
| Secret read enabled and exact CMK supplied | `kms:Decrypt` | Exact `secret_kms_key_arn` | All three StringEquals conditions below |

The KMS conditions are:

- `kms:ViaService = secretsmanager.<region>.amazonaws.com`.
- `kms:EncryptionContext:SecretARN = <exact authorized secret ARN>`.
- `kms:CallerAccount = <expected workload account>`.

No other identity grants are generated: no CreateLogGroup, log deletion,
retention/protection/resource-policy administration, secret creation/writes,
tagging/listing/batch reads/replication, KMS Encrypt/GenerateDataKey/CreateGrant or
administration, IAM administration, PassRole, STS role chaining, S3 or EC2.
There is no `Resource = "*"` statement and no AWS-managed policy attachment.
The only resource wildcard is the documented stream-name suffix under one group.

With secret reading disabled, both secret/key inputs must be null and no Secrets
Manager or KMS statement exists. Enabling a secret without a customer-managed key
adds only the two read actions; the module does not infer key type or add CMK
permissions for the AWS-managed `aws/secretsmanager` key. GetSecretValue is scoped
to that secret, not to a particular version stage. A later stage-specific
restriction would need separate review.

## Resource references and external prerequisites

The CloudWatch Logs module's provider 6.72.0 output is a **bare group identity
ARN**; the execution policy deliberately appends `:log-stream:*`. An API ARN
ending `:*`, an existing stream ARN, a partial group name or a wildcard group
reference is rejected. A bare group identity is neither an IAM grant nor a stream
scope by itself. The log group must exist before invocation. This role cannot
compensate for a missing group by authorizing automatic CreateLogGroup, and it
does not attach `AWSLambdaBasicExecutionRole`.

Pass the existing Secrets Manager module's actual `secret_arn` output, not a
reconstructed name/partial ARN. Validation requires the generated suffix shape,
but cannot prove provenance/existence or distinguish every manually constructed
partial name that happens to end in six characters. Verify the real secret and
its key association externally. Applications retrieve values using the AWS SDK
at runtime; Terraform never obtains, stores, initializes, updates or outputs
secret plaintext. Secrets Manager Approach A is unchanged.

For a CMK, verify enabled symmetric-key suitability, region/account, key policy,
caller authorization, encryption context and regional service behavior. IAM Allow
alone does not prove decrypt access. Keep the key accessible for existing secret
versions. Resource policies, SCPs, boundaries, sessions and other role policies
can change real authorization; this module does not inspect them. Cross-account
secrets/keys and arbitrary additional services are outside this contract.

## Ownership, integration order and deployment authority

Use a dedicated workload role, separate from IAM Identity Center human-access
profiles and deployment identities. Existing human policies are unchanged.
Terraform owns this role/trust and one named inline policy, not exclusive
management of every possible externally attached policy. Audit other inline and
managed policies before adopting an existing role. A same-named existing role
requires a reviewed import/ownership decision; do not repurpose a human role.

A future deployment identity needs separately reviewed Lambda operations and
narrowly scoped `iam:PassRole` for the actual role ARN, with appropriate service
restrictions. This module grants none of those deployment permissions. Root
provider configuration, organizational permission-boundary requirements, state
ownership and account restrictions remain external responsibilities.
There is no permissions-boundary input in this interface. An organization that
requires a boundary on CreateRole needs a separately reviewed module extension;
root/provider settings alone do not make that requirement supported here.

The role ARN output references the role resource. **Referencing that ARN alone
does not guarantee the separate inline policy is attached and propagated.** A
future Lambda root must order the complete role module before deployment/first
invocation, for example with an explicit `depends_on = [module.execution_role]`
on its Lambda module or another reviewed policy-readiness dependency. IAM eventual
consistency still requires external deployment handling and runtime verification.
No composition is performed here.

### VPC is intentionally unsupported

This policy is intended initially for Lambda without VPC attachment. AWS documents
that Lambda ENI operations include EC2 actions requiring `Resource = "*"`, and
those identity permissions can also be available to function code. Their safe
design needs a separately reviewed contract, including supported
`lambda:SourceFunctionArn` conditions and deployment behavior. This module adds
no ENI actions and does not attach `AWSLambdaVPCAccessExecutionRole`. Do not use
it as evidence that the existing Lambda module's optional VPC mode is supported.

## Outputs and quotas

| Output | Meaning |
| --- | --- |
| `execution_role_arn` | Actual `aws_iam_role.this.arn`, never predicted from account metadata |
| `execution_role_name` | Actual role `name` |
| `inline_policy_name` | Actual inline policy `name` |
| `log_group_arn` | Configured existing bare log-group reference |
| `secret_read_enabled` | Configured enablement flag, not a deployed authorization result |
| `permission_scope` | Eight input-derived non-secret scope fields for independent verification, including role name and optional ARN references |

ARNs and account metadata are references, not secret values. The independent
checker reports hashes, action/resource-type metadata and static results without
printing account/ARN/session details.

IAM's role-inline-policy aggregate limit is 10240 non-whitespace characters,
including other inline policies on the role. The default trust limit is 2048
characters (adjustable quota currently up to 8192). This small generated policy
uses bounded inputs; the checker measures actual documents and enforces the
reviewed default limits. Existing policies consume quota too. Root ownership and
future extensions must review aggregate budgets rather than assuming an empty
role or replacing inline scope with broad managed permissions.

## Future root example — not implemented

All referenced roots/modules/variables below are future composition inputs. This
example creates no current integration and authorizes no Phase 4 or deployment.

```hcl
module "execution_role" {
  source = "../../../../modules/lambda_execution_role"

  role_name     = "portfolio-api-execution"
  partition     = var.aws_partition
  account_id    = var.aws_account_id
  region        = var.aws_region
  log_group_arn = module.log_storage.log_group_arn

  enable_secret_read = true # Root Override; Module Default is false.
  secret_arn         = module.application_secret.secret_arn
  secret_kms_key_arn = var.application_secret_kms_key_arn
  tags               = { Environment = "dev", Project = "portfolio" }
}
```

The future Lambda module would consume `execution_role_arn`, with the policy
dependency described above. Its environment contains only non-secret
configuration or secret references. No service-root file changes in this phase.

## Offline validation and residual limits

Use Terraform 1.17.0 and AWS Provider 6.72.0. Seed a transient child lock from the
unchanged dev-root lock, inspecting/preserving any existing child lock first.
With AWS credential/profile variables absent, shared files `/dev/null` and
metadata lookup disabled, run from this module:

```sh
cp ../../services/dev/ca-central-1/serverless-api/.terraform.lock.hcl .terraform.lock.hcl
terraform fmt -check -recursive
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Native tests use `mock_provider "aws" {}`, explicit `command = plan` and synthetic
references. The separate stdlib checker consumes actual successful native JSONL,
actual trust/identity documents and input-derived scope outputs, with current
official Logs, Secrets Manager and KMS authorization-reference JSON. Its strict
complete grant-set check is independent of its finite authorization matrix, so
off-sample grants cannot be ignored. Semantic mutations are made to actual
rendered documents; unrelated/administrative grants must be exposed by concrete
static witnesses, not merely changed checksums. Malformed capture/reference and
process-status faults must fail closed. CI preserves all prior validation.
The [offline workflow](../../../.github/workflows/terraform-offline-ci.yml) shows
the full capture/public-reference/checker command. Preserve the actual Terraform
exit status when passing `--terraform-exit-code`; never replace a failed process
status with zero. The checker is invoked with `--self-test` so its semantic and
malformed-input regressions execute alongside every native CI run.

Current evidence passes **64 native tests**: 15 complete positive role/policy plans
and 49 intended variable-validation failures. Terraform emits 13 empty plans and
36 role-only partial plans for the rejected inputs; every partial role retains
the exact safe trust, and none includes an identity policy. These are mock plans,
not applied resources or authorization positives. The checker verifies all 15
complete generated policies with **675** static authorization/trust cases,
detects **14** semantic unauthorized-Allow/trust mutations, and rejects **44**
capture/process/policy/JSON faults plus **five** reference faults. Existing
regressions preserve 231 native and 153 Python tests.

This evidence is **static reviewed-policy-set verification**, not AWS IAM
Simulator output or effective deployed-role authorization. No missing-context
response is relabeled. Before deployment, an authorized external workflow must
test Lambda assumption and propagation, log-stream writes, permitted secret reads,
negative unrelated-secret/key tests, key-policy behavior and absence of broad
external attachments. No real AWS API, credentials, authenticated plan,
apply/destroy or runtime payload is used by these tests.

Official references: [Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html),
[Logs authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_logs.html),
[Secrets Manager authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html),
[KMS authorization](https://docs.aws.amazon.com/service-authorization/latest/reference/list_kms.html),
[KMS ViaService/CallerAccount/context](https://docs.aws.amazon.com/kms/latest/developerguide/conditions-kms.html),
[Secrets Manager encryption](https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html),
[full Secret ARN guidance](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html),
[Lambda VPC permissions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html),
[IAM quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html).
