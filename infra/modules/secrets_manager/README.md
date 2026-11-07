# Secrets Manager metadata container

This reusable child module implements **Secret Management Approach A**. It
defines exactly one `aws_secretsmanager_secret.this` container with a stable
caller-supplied name, visible metadata, an encryption-key reference and a
recoverable deletion window. It defines no secret version, value input, value
data source, generator, provisioner, rotation function, KMS key or workload role.
It is not integrated into any service root and nothing has been deployed.

Terraform never receives, reads, generates, initializes, updates or outputs actual
secret material. Metadata creation does **not** establish an `AWSCURRENT` version
or a usable application credential. A separately authorized operational process
outside Terraform and Codex Cloud must initialize values after a future deployment,
own subsequent value updates/rotation and verify application readiness. Do not
place even test passwords, tokens or credential payloads in this module.

The calling root owns account/region selection, provider configuration, state,
backend, environment-specific names and reviewed overrides. The module does not
query an AWS account or accept credentials. VPC and service-root configuration
remain unchanged. Cross-region replication, disaster recovery, rotation, VPC
endpoints, deployment identities and application integrations are outside scope.

## Inputs

All names, descriptions and tags are visible metadata. Never include credentials,
confidential connection information or secret values in them.

| Input | Type / default | Validation and responsibility |
| --- | --- | --- |
| `name` | Required `string`, no default | Non-null, 1-512 characters matching `[A-Za-z0-9/_+=.@-]`; no ending `-` followed by six alphanumeric characters; stable caller identity |
| `description` | `string`, `null` | Optional non-sensitive description, at most 2048 characters |
| `project_tag` | Required `string`, no default | Non-null, 1-63 lowercase letters/digits/hyphens starting with a letter; authorization ownership supplied by the root |
| `tags` | `map(string)`, `{}` | Non-null map, keys 1-128 characters, values non-null and at most 256 characters, no reserved `aws:` prefix, at most 50 merged tags |
| `recovery_window_in_days` | `number`, `30` | Whole days only, 7-30 inclusive; zero-day force deletion is rejected |
| `kms_key_arn` | `string`, `null` | Optional existing key ARN in `aws`, `aws-us-gov` or `aws-cn`, explicit region/account, UUID or `mrk-` key ID; aliases, wildcards and incomplete identifiers are rejected |

`name` and `project_tag` reject null through their custom input validation. The
optional tags/recovery inputs use their defaults when null is supplied.
Module-owned canonical `Name` and `Project` tags override the same caller keys.
Noncanonical case variants such as `name`, `NAME` or `project` are rejected to
avoid ambiguous authorization/inventory metadata. Other service tag restrictions
and organization tagging policies still require external verification.

The secret name supports 512 characters but an AWS tag value supports only 256.
The module fixes `Name` to the first 256 characters of the supplied secret name;
the actual secret name and `secret_name` output remain complete. Use the full ARN
or name for identity, not the potentially truncated inventory tag.

## Outputs

| Output | Source / meaning |
| --- | --- |
| `secret_arn` | `aws_secretsmanager_secret.this.arn`, including the AWS-assigned ARN suffix |
| `secret_name` | `aws_secretsmanager_secret.this.name`, the complete stable name |
| `secret_id` | `aws_secretsmanager_secret.this.id`; AWS Provider 6.72.0 uses the actual ARN as the ID |
| `kms_configuration` | Requested encryption mode plus the resource's configured `kms_key_id` reference; no key lookup or permission grant |
| `resource_policy_managed` | Fixed `false`; no resource policy or reader grant is managed |

The KMS mode is `aws-managed` when the input is null and `customer-managed` when
an existing key ARN is supplied. Its configured reference can be null/unset for
the service default; the module does not invent the AWS-managed key's ARN. The
mode describes the requested configuration, not verified key ownership, type or
effective authorization. All outputs are references/configuration, never values,
sessions, version payloads or runtime credentials.

Future Lambda/ECS modules may accept `secret_arn` as a runtime reference. Their
reviewed execution role and application retrieve values at runtime through the
appropriate service integration or SDK. Terraform must not retrieve a value to
pass it to a workload module.

## Effective configuration sources

| Category | Configuration |
| --- | --- |
| Root Override | Required stable name and Project identity; optional description, tags, 7-30-day recovery choice and existing CMK ARN |
| Module Default | No description, additional tags `{}`, recovery 30 days, no explicit KMS reference (service-managed default selection) |
| Module Fixed | One metadata container; module-owned canonical Name/Project tags; Name inventory value bounded to 256 characters; no values, replicas, resource policy, KMS resources, rotation or execution roles |

There are no arbitrary JSON policy inputs, secret-value options, generic feature
flags or caller-selected Terraform resources. Adding a supported capability
requires a separate reviewed change rather than bypassing these boundaries.

## Encryption and KMS ownership

With `kms_key_arn = null`, the provider omits an explicit key reference and
Secrets Manager uses the AWS-managed `aws/secretsmanager` KMS key. The module
does not create a customer-managed key or alias.

A supplied CMK ARN is passed to the container. Format validation cannot verify
key existence, symmetric encryption support, account/region compatibility,
enabled state, policy, grants or operational ownership. Before external use,
independently verify all of those, required creation/update/runtime KMS access,
additional KMS costs, deletion safeguards and key-rotation ownership. An ARN alone
does not grant permission to encrypt or decrypt anything.

No KMS permission is added to Access Admin, Developer or Operator. A future
reviewed workload policy may need `kms:Decrypt` on the exact CMK ARN alongside
secret-read authorization, constrained with `kms:ViaService` and suitable
Secrets Manager encryption context where supported. Key-policy authorization and
account/region compatibility must also be reviewed. A metadata-only encryption
configuration does not validate those policies or provision a deployment identity.

## Resource policies and human permissions

The module deliberately uses the ordinary same-account identity-policy model.
It creates no `aws_secretsmanager_secret_policy`, accepts no reader principals
or JSON policy and exposes `resource_policy_managed = false`. No concrete reader
roles or verified account context are available to this reusable module, so the
optional resource-policy path is omitted rather than adding account lookups or
an approval framework. This does not claim that secure same-account resource
policies are impossible; such support needs its own concrete use case and review.
No cross-account, wildcard-principal or public grant is introduced.

A separately reviewed workload execution role needs narrowly scoped
`secretsmanager:GetSecretValue` on the actual ARN, plus `DescribeSecret` only if
its runtime client requires it and CMK permissions where applicable. No workload
role or secret-read policy is implemented here. Existing external resource
policies, SCPs and other identity policies still affect effective access.

The [human-access module](../iam_access/README.md) documents the exact permissions
and residual capabilities. The module accepts other valid non-sensitive tags,
but the human Developer creation policy allows only canonical Environment,
ManagedBy, Name, Project and Service keys. Other creation tags require a
separately reviewed execution identity rather than weakening that policy. AWS Provider 6.72.0 reads `GetResourcePolicy` while
refreshing this metadata resource even when this module owns no policy. That
read does not require granting human policy-editing rights.

`CreateSecret` can accept an initial value at the AWS API level; a metadata-only
Terraform resource does not make that IAM action payload-free. `UpdateSecret`
can also write values and is intentionally withheld from the human Developer
profile. Consequently, not every description/CMK metadata update can be completed
using that profile. A future controlled deployment identity must be independently
designed and reviewed. Secret initialization and value updates remain outside
Terraform; there is no unsupported IAM claim that direct API value writes are
technically prevented by this module.

## Deletion, replacement and naming

The default recovery period is 30 days; a root can choose an integer from 7 to 30.
There is no immediate deletion option. Scheduling deletion makes the secret
unavailable during recovery, and the name remains unavailable for ordinary reuse
while deletion is pending. Final deletion is asynchronous, so expiry does not
guarantee immediate recreation. Recovery requires a separately authorized
operational decision and the necessary external permissions; it is not performed
by this module or a Codex command.

Changing the explicit name causes resource replacement. Review the Terraform
plan outside Codex Cloud before a future authorized change, including name reuse,
application references, externally initialized values and the old container's
scheduled deletion. Do not assume replacements transfer values or maintain
application availability. Provider retries are not a name-reuse guarantee.

Secrets Manager adds a hyphen and six random characters to the **ARN**, not the
configured stable name. Inputs ending in a similar suffix are rejected because
partial-ARN lookup can become ambiguous. The module returns the actual provider
ARN and never constructs or predicts that suffix. Prefer full ARN references.

## Future root example — not integrated

```hcl
module "application_secret" {
  source      = "../../../../modules/secrets_manager"
  name        = "${var.project}/${var.environment}/${var.service}/configuration"
  project_tag = var.project
  description = "Application configuration metadata"

  # null selects the AWS-managed default; verify an existing CMK externally.
  kms_key_arn = var.existing_kms_key_arn

  tags = {
    Environment = var.environment
    Service     = var.service
    ManagedBy   = "Terraform"
  }
}
```

This call is documentation only; no service root calls the module. A future root
must supply verified identifiers through its approved external binding process.
The following labels are documentation placeholders, never active Terraform or
automatically loaded tfvars content:

| Documentation label | Meaning |
| --- | --- |
| `REPLACE_WITH_EXISTING_KMS_KEY_ARN` | Existing verified symmetric CMK when overriding the service-managed default |
| `REPLACE_WITH_12_DIGIT_AWS_ACCOUNT_ID` | Verified target/provider account owned by the future root |
| `REPLACE_WITH_APPROVED_WORKLOAD_ROLE_ARN` | Existing reviewed workload execution role; not an input to this module |

Never supply AWS credentials to Codex Cloud or put invalid placeholder strings
into active `.tf`, `.tfvars` or `*.auto.tfvars` files.

## Runtime networking, costs and operational prerequisites

Applications must be able to reach the regional Secrets Manager endpoint. The
existing private VPC configuration has neither NAT nor Secrets Manager interface
endpoints; a workload in such a subnet cannot rely on that VPC alone to retrieve
values. Networking, DNS, endpoint/security policies and runtime execution-role
permissions need a later reviewed integration. This module adds none of them.

Budget for Secrets Manager storage/API usage and any customer-managed KMS costs;
review current pricing and regional requirements before deployment. Separate
owners must track value initialization/rotation, key lifecycle, application
references, recovery/deletion approvals, audit evidence and removal of obsolete
access. Secret metadata and policy references are visible state/plan metadata
and must also be handled through the approved state and review process.

## Offline verification and remaining limits

Requires Terraform `>= 1.17.0, < 2.0.0` and AWS Provider
`>= 6.72.0, < 7.0.0`. The repository CI fixes verification to Terraform 1.17.0 /
AWS Provider 6.72.0 using a transient copy of the committed root dependency lock.
No child lock is committed.

Local verification with Terraform 1.17.0 / AWS Provider 6.72.0 passed formatting,
backend-disabled initialization, validation and **31 mock-plan tests, zero failed
or skipped**. Initialization used the unchanged root lock as a transient checksum
seed; the generated child lock was removed afterward. No AWS credential or
account API was used.

```sh
cd infra/modules/secrets_manager
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Run `terraform fmt -check -recursive` from the repository root. Tests use only
`mock_provider "aws" {}` with explicit `command = plan`, format-valid synthetic
references and metadata-only inputs. They cover defaults/overrides, outputs,
name/tag boundaries, KMS reference validation, recovery safeguards and rejected
null/invalid required inputs. The CI also inspects the actual planned managed
resource inventory to reject versions, policies, keys and other unexpected types.

Offline syntax, mock plans and IAM static-reference checks do not prove live AWS
authorization, account/key correctness, quotas, actual lifecycle behavior,
workload connectivity, valid `AWSCURRENT` material or operational governance.
Live authorization readiness remains incomplete. No account API, real AWS plan,
credential, deployment, apply or destroy is authorized or performed in Codex Cloud.

## Official evidence

- [AWS CreateSecret API: name, tags, encryption and value omission](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_CreateSecret.html)
- [AWS DeleteSecret API: recovery period and asynchronous deletion](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DeleteSecret.html)
- [Secrets Manager Tag constraints](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_Tag.html)
- [Tag limits and reserved prefixes](https://docs.aws.amazon.com/secretsmanager/latest/userguide/managing-secrets_tagging.html)
- [Secrets Manager encryption and KMS](https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html)
- [KMS key concepts](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html)
- [Secrets Manager VPC endpoints](https://docs.aws.amazon.com/secretsmanager/latest/userguide/vpc-endpoint-overview.html)
- [AWS Provider v6.72.0 secret lifecycle implementation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/secretsmanager/secret.go)
- [Secrets Manager Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html)
