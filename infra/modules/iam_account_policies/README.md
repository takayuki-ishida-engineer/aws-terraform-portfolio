# Workload-account customer-managed policies

This child module defines exactly one customer-managed policy:
`aws_iam_policy.developer_secrets_manager`. Its reviewed identity is fixed to
**`Portfolio-Developer-SecretsManager`**, path **`/`**. It contains only the six
previously reviewed Secrets Manager actions; it defines no users, roles, groups,
access keys, workloads, account assignments, KMS keys or secret resources/values.
No policy or AWS account resource has been deployed by this task.

The module is intended for an independently authorized owning root in **one
workload account**. That root selects its provider, account/region, state and
backend, and must restrict the provider to the intended account (for example
through the root's `allowed_account_ids`). `account_id` constrains the policy's
permissions; it does **not** choose or authenticate the provider. This module
performs no account lookup and contains no provider/backend configuration. Use one
owning root per workload account for this global fixed policy identity; do not
instantiate competing copies per application, environment or region in the same
account. Its region and project contract must match the reviewed human-access
configuration.

The separate [IAM access module](../iam_access/README.md) adds a customer-managed
policy **reference** to Portfolio-Developer. That reference does not create this
policy in workload accounts. Before provisioning the Permission Set into an
account, that account must already contain a policy with the exact name and path.
AWS Identity Center does not require matching names/paths to imply identical
policy content; this portfolio requires the same reviewed template with explicit
account-specific ARN and caller-account scope.

## Inputs and configuration sources

| Input | Type / default | Validation and responsibility |
| --- | --- | --- |
| `account_id` | Required `string`, no default | Non-null, exactly 12 decimal digits; one approved workload account selected independently by the owning root |
| `region` | Required `string`, no default | Non-null explicit region syntax, no wildcard; existence and partition compatibility verified outside this module |
| `project_tag` | Required `string`, no default | Non-null, 1–63 lowercase letters/digits/hyphens starting with a letter; matches the reviewed secret project identity |
| `partition` | `string`, `aws` | Only `aws`, `aws-us-gov` or `aws-cn`; this does not configure the provider |
| `tags` | `map(string)`, `{}` | Additional non-sensitive policy inventory tags; canonical module-owned Name and project take precedence |

The policy accepts no arbitrary JSON, action list, resource list, policy name,
path, managed-policy ARN or future-service feature flag. Root account/region/
project values must be verified before external use; format validation cannot
establish account ownership, existing resources or effective authorization.
Names, descriptions and tags must contain no credential or confidential values.

| Category | Effective configuration |
| --- | --- |
| Root Override | Explicit workload account, Secrets Manager region, project identity, optional partition and non-sensitive inventory tags |
| Module Default | Partition `aws`; additional inventory tags `{}` |
| Module Fixed | Policy name `Portfolio-Developer-SecretsManager`, path `/`, the reviewed six actions/five statements and all authorization safeguards; 6,144-character quota guard |

## Outputs

| Output | Meaning |
| --- | --- |
| `policy_arn` | Actual `aws_iam_policy.developer_secrets_manager.arn` from the selected provider account |
| `policy_name` | Actual resource name; must match the Identity Center reference |
| `policy_path` | Actual resource path; must match the Identity Center reference |
| `policy_json` | Actual Terraform-rendered resource policy document, for controlled offline export/validation |
| `policy_non_whitespace_characters` | Character count of the actual compact ASCII policy document |
| `policy_headroom_characters` | Remaining characters below the 6,144-character customer-managed-policy limit |

These are references and non-secret authorization metadata. Do not commit
rendered policies containing future real account identifiers or raw AWS
validation/session results. The validation toolkit uses clearly synthetic
mock-plan exports; operational output belongs in an external temporary location.

## Reviewed authorization matrix

Every row uses only
`arn:<partition>:secretsmanager:<region>:<account_id>:secret:*`, with
`aws:PrincipalAccount = account_id` and `aws:RequestedRegion = region`.
This is intentionally narrower than the previous multi-account inline document:
this policy must be created and used in its one owning workload account.
A session in account A no longer uses this policy to authorize Secret ARNs in
account B merely because B appeared in the old target set; cross-account access
would need a separate explicitly reviewed design.

| Actions | Additional conditions / purpose |
| --- | --- |
| `secretsmanager:CreateSecret` | Required request project; canonical Name/env/managed/project/service tag keys; no requested replica regions; no replica overwrite |
| `secretsmanager:TagResource` with project supplied | Both resource and requested project match; the same canonical tag keys; no request-tag-only adoption of unrelated resources |
| `secretsmanager:DescribeSecret`, `secretsmanager:GetResourcePolicy` | Existing matching project resource; the provider reads both during secret-container refresh |
| `secretsmanager:TagResource`, `secretsmanager:UntagResource` for other tags | Matching resource project; exclude every case variant of project and require a tag-key list |
| `secretsmanager:DeleteSecret` | Matching project; explicit recovery period 7–30 days; `BoolIfExists` rejects true ForceDeleteWithoutRecovery while permitting omission/false |

The ARN includes the service-assigned suffix and permits valid secret names with
`/`; the module does not fabricate secret ARNs or create containers. There are
no resource or action wildcards beyond the reviewed terminal secret-name pattern.
Creation-tag semantics follow the published AWS Secrets Manager ABAC example,
not a fabricated create-context key.

**CreateSecret can initialize a value through its API.** IAM provides no
reliably documented condition enforcing the absence of initial payloads. The
metadata-only Terraform module never handles them, but this policy is not a
technical prohibition on human value initialization. UpdateSecret remains
withheld because it can overwrite values; some description/CMK updates therefore
need a separately reviewed controlled deployment identity and payload-free
execution process.

The policy also withholds GetSecretValue, BatchGetSecretValue, PutSecretValue,
UpdateSecretVersionStage, rotation, RestoreSecret, ListSecrets, resource-policy
administration, KMS operations, IAM administration and PassRole. It adds no
workload runtime permissions. Externally attached policies, SCPs, tag editors,
key policies and the actual caller context still affect effective access.
Access Admin self-assignment and other documented human-access risks remain.

## Quotas and future extension

IAM customer-managed policy documents are limited to **6,144 non-whitespace
characters**, independently of the Identity Center inline-policy limit. Every
policy-bound input is constrained to ASCII and `jsonencode` emits compact JSON,
so the native precondition measures the relevant character count exactly.
Oversized documents fail before provisioning; it never broadens resource scope
or removes conditions to fit. Outputs expose the actual count and headroom.

Account-specific generation avoids repeating all workload account ARNs in every
service document. Native cases cover different accounts/regions/partitions,
maximum project length and an oversized synthetic region that must be rejected
by the policy-size precondition. Format-valid synthetic data does not prove a
real region/account exists.

Future Lambda/ECS or other service policies require their own reviewed document,
resource, independent size guard, output identity, security regressions and
Identity Center reference. Do not concatenate new services back into this Secret
policy or indefinitely grow the Developer inline document. Add no speculative
future actions or generic arbitrary-policy injection interface. Permission Set
and target-role attachment quotas must still be reviewed and enforced separately
by the access module and future deployment owner.

## Future root example and migration prerequisites

This example is documentation only; no existing service root calls this module.
Use a future owning root at `infra/services/<env>/<region>/<service>/` with its
provider explicitly selected/restricted to the workload account:

```hcl
module "developer_account_policies" {
  source      = "../../../../modules/iam_account_policies"
  account_id  = var.workload_account_id
  region      = var.portfolio_region
  project_tag = var.project
  partition   = var.aws_partition

  # project, env and managed come from the root's provider default_tags.
  tags = {
    Team = var.team
  }
}
```

Supply verified identifiers only through a separately approved external process.
Documentation label `REPLACE_WITH_12_DIGIT_WORKLOAD_ACCOUNT_ID` describes that
future binding; do not put invalid placeholders or AWS credentials in active
Terraform or automatically loaded variable files.

Safe migration order:

1. Review the rendered per-account document and provider account restriction;
   create the matching name/path policy in **every** approved workload account
   through each account's separately authorized owning root.
2. Verify those policies and matching identities before adding the Developer
   Permission Set reference. Attachment changes automatically re-provision the
   Permission Set into already assigned accounts; the reference itself never
   creates a missing workload policy.
3. Add the reviewed attachment while the old approved inline policy still covers
   its Secret permissions, then remove those statements from the inline policy
   and re-provision. The access module must serialize that transition.
4. Verify the effective union, policy versions/content, account/region/project
   scope, reference identity, assigned-account provisioning and external drift.

Rollback must retain the target policies until no reference requires them.
Restore a known reviewed managed-policy version/content and re-provision first.
Only restore the old monolithic inline document before detaching if its size and
actual target scope still fit the inline quota; never bypass a size guard.
Review cross-root state ownership and dependencies explicitly—Terraform cannot
infer readiness of independently managed workload accounts from name/path alone.
See the [operations runbook](../../../docs/iam-access-operations.md) for the full
approval, migration, rollback, validation and drift process.

## Offline validation

Use Terraform 1.17.0 and AWS Provider 6.72.0. The repository CI seeds a transient
child dependency lock from the unchanged dev-root lock; do not commit child locks.
All native runs use `mock_provider "aws" {}` and explicit `command = plan`.

Local verification passed with Terraform 1.17.0 / AWS Provider 6.72.0: formatting,
backend-disabled initialization, validation and **24 native tests passed, zero
failed/errors/skipped**, including a fresh verbose JSON event run. Actual planned
inventory contained exactly one managed IAM policy creation. The default synthetic
fixture rendered **2,346 non-whitespace characters**, leaving **3,798** below the
managed-policy quota. The generated child lock was removed and the root lock was
unchanged. No AWS credentials or account API calls were used.

```sh
cd infra/modules/iam_account_policies
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Run repository-wide `terraform fmt -check -recursive` as well. The toolkit and
static checker consume actual rendered plan policies, not hand-rewritten policy
samples, and inspect the managed-resource inventory independently.

Offline checks do not prove live IAM evaluation, effective permissions, correct
provider account selection, matching remote policy existence, Identity Center
propagation, KMS access or workload behavior. Actual AWS validation remains a
separate explicit user action in an authorized CloudShell/local session; Codex
Cloud and GitHub Actions never call authenticated AWS validation APIs or deploy.

## Official evidence

- [IAM Identity Center customer-managed policy references](https://docs.aws.amazon.com/singlesignon/latest/userguide/howtocmp.html)
- [Permission Set custom policies](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetcustom.html)
- [Identity Center quotas](https://docs.aws.amazon.com/singlesignon/latest/userguide/limits.html)
- [IAM quotas and policy characters](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
- [Secrets Manager Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html)
- [Secrets Manager ABAC example](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_attribute-based-access-control.html)
- [Provider 6.72.0 IAM policy resource](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/iam/policy.go)
