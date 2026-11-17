# S3 artifact bucket

This child module manages a private, versioned general-purpose S3 bucket for
externally built Lambda ZIP artifacts. It manages bucket configuration only.
It creates no objects, uploads, deployment identities, Lambda functions, KMS
resources, lifecycle rules, replication, notifications, logging resources or
remote Terraform backend. Providers and backends remain root-owned.

## Resource inventory and effective configuration

The complete managed inventory is exactly:

| Address | Module Fixed configuration |
| --- | --- |
| `aws_s3_bucket.this` | Shared namespace `global`; `force_destroy = false` |
| `aws_s3_bucket_versioning.this` | Versioning `Enabled` |
| `aws_s3_bucket_public_access_block.this` | All four Public Access Block settings `true` |
| `aws_s3_bucket_ownership_controls.this` | `BucketOwnerEnforced`; ACLs disabled |
| `aws_s3_bucket_server_side_encryption_configuration.this` | Explicit SSE-S3 default encryption, `AES256` |
| `aws_s3_bucket_policy.this` | Exactly one scoped non-HTTPS Deny; no Allow |

| Configuration | Source | Effective behavior |
| --- | --- | --- |
| `bucket_name` | Root Override, required | Caller-supplied stable name; no generated suffix |
| `tags` | Module Default `{}` / Root Override | Visible, non-secret caller tags; the module adds `Name` (the bucket name) and `service = s3`, which win (Module Fixed) |
| Provider, Region, account and provider `default_tags` | Root Override, outside this interface | Root selects and restricts the provider; Region is not a module input |
| Namespace and every security setting above | Module Fixed | No public-access, versioning, encryption, ACL or deletion override |

There are exactly two inputs and three outputs. No arbitrary bucket-policy JSON,
KMS, upload, lifecycle, provider-credential or Region interface is exposed.

## Inputs and validation

`bucket_name` is a required string with no default. Names must be 3–63 characters,
start and end with a lowercase ASCII letter or digit, and contain only lowercase
ASCII letters, digits and hyphens. Periods are deliberately excluded for DNS/TLS
compatibility; this also excludes IP-address names and `.mrap` aliases.

Reserved prefixes `xn--`, `sthree-` and `amzn-s3-demo-` are rejected. Reserved
suffixes `-s3alias`, `--ol-s3`, `.mrap`, `--x-s3`, `--table-s3` and `-an` are
rejected. The `-an` suffix belongs to the account regional namespace, which this
module does not support. A syntactically valid name does not prove availability
or ownership. The shared namespace is unique across accounts within an AWS
partition. Bucket name and Region cannot be changed in place.

`tags` is `map(string)`, defaults to `{}` and has `nullable = false`. Terraform
uses the default for an explicitly null map. Values must be non-null and at most
256 characters; keys must contain 1–128 characters and cannot use the reserved
`aws:` prefix (checked without case sensitivity). Together with the module-owned
`Name` and `service` keys at most 50 entries are allowed, so callers can supply 48
other tags. Tags and names are not suitable for sensitive information. Tag keys and
the module-owned tags follow [deployment configuration](../../../docs/deployment-configuration.md#5-tags).

The bucket's `tags_all` postcondition also checks the effective tag set, including
root-owned provider `default_tags`. Resource tags override matching provider
keys. The combined set must fit the same limits; checking `var.tags` alone would
miss excessive provider defaults. If a computed value is unknown during planning,
Terraform can defer the postcondition until after creation; a failed check is not
an automatic rollback. The future root must review its defaults before deployment.

## Bucket policy and encryption

The policy uses language version `2012-10-17` and one statement,
`DenyInsecureTransport`:

| Element | Fixed value |
| --- | --- |
| Effect / Principal | `Deny` / `*` |
| Action | `s3:*` |
| Resources | Actual provider-returned bucket ARN and that ARN followed by `/*` |
| Bool | `aws:SecureTransport = "false"` and `aws:PrincipalIsAWSService = "false"` |

Both conditions must match. The AWS-service-principal exception follows AWS's
guidance because service-to-service calls can redact network context. It adds no
Allow permission. HTTPS requests and exempt service principals still require
separate authorization. Plain `Bool` conditions do not turn absent context keys
into matching false values; this is not a general IAM evaluator or proof of all
request contexts. No minimum TLS version or additional access exception is added.

The policy is a restriction, not an access grant. It grants no deployment-user,
Lambda-service, public or cross-account access. Identity policies, resource
policies, SCPs and other applicable controls determine actual effective access.
Public Access Block and ownership controls are managed separately and remain
fixed; do not replace this policy with caller-supplied documents.

SSE-S3 is the explicit **default** encryption setting. An external upload that
specifies encryption headers can request a different supported mode; this policy
does not require every object to use AES256. Existing objects are not re-encrypted
by changing a default. No SSE-KMS/DSSE-KMS, KMS grants or encryption-enforcement
extension is implemented. The approved uploader must verify the actual object
encryption and any additional read prerequisites.

## Outputs and future Lambda composition

| Output | Actual resource attribute |
| --- | --- |
| `bucket_name` | `aws_s3_bucket.this.bucket` |
| `bucket_arn` | `aws_s3_bucket.this.arn` |
| `versioning_status` | `aws_s3_bucket_versioning.this.versioning_configuration[0].status` |

All three outputs explicitly depend on versioning, Public Access Block,
ownership controls, encryption and bucket policy. They order future Terraform
consumers after those resources. They do not report uploaded content, authorization,
S3 propagation or deployment readiness. ARNs are provider-derived; this module
does not infer a partition, account or Region from a predicted ARN.

Future root composition, shown for documentation only:

```hcl
module "artifact_bucket" {
  source = "../../../../modules/s3_artifact_bucket"

  bucket_name = var.artifact_bucket_name
  tags        = var.tags
}

# In a separately reviewed Lambda module call:
# s3_bucket         = module.artifact_bucket.bucket_name
# s3_key            = var.approved_artifact_key
# s3_object_version = var.approved_artifact_object_version
```

The root must configure the correct provider, Region and account restrictions,
verify actual bucket ownership, and review the real plan outside Codex Cloud.
Lambda requires the artifact bucket to be in the function's Region. An approved
external process builds the ZIP, uploads it over HTTPS without an incompatible
ACL, records its actual non-null S3 version ID, and supplies its exact key and
version to the existing Lambda module. No key or version is invented here.
An **S3 object version** identifies a stored deployment package; it is different
from a **Lambda published function version**.

After first enabling versioning, AWS recommends waiting 15 minutes before object
PUT/DELETE operations; propagation can temporarily cause `NoSuchKey` responses.
Terraform dependency ordering does not implement that waiting period. Verify
versioning externally before the first approved upload and verify the recorded
version can be read before deployment. This module cannot establish that the
deployment principal or Lambda service has the required object-read permissions.
Human Identity Center access and workload execution-role permissions are separate.

## Operations, imports and teardown

Current and noncurrent artifact versions accumulate and incur storage charges.
Requests and data transfer can also incur charges. There is no automatic retention
or expiration, including for incomplete multipart uploads. A future retention
strategy must separately review rollback requirements, costs and deletion risks.

Reconcile drift through a reviewed real plan outside Codex Cloud. Terraform
manages the listed configuration, not continuous enforcement against out-of-band
changes. Before import, inventory ownership, ACL dependencies, all object versions,
encryption, bucket policy and other existing settings. Import/reconcile each of
the six corresponding resources under one owner; importing only the bucket does
not adopt all the separate security resources. Applying fixed settings can change
existing access. Additional existing configurations and object contents are not
made safe or adopted by this module.

No real deletion is authorized in this phase. A future approved teardown must:

1. Stop uploads/deployments, review rollback and retention obligations, and preserve
   any required artifacts outside the deletion target.
2. Review the full Terraform deletion plan and any external permissions required
   to remove every current/noncurrent object version and delete marker. Ordinary
   deletion without a version ID can merely add a delete marker. Review incomplete
   multipart uploads and applicable external retention controls as well.
3. Perform any explicitly approved content deletion outside this module and only
   then proceed with the separately authorized bucket teardown.

`force_destroy = false` prevents Terraform from silently emptying a nonempty
bucket, including its historical versions. It is not a deletion lock: an empty
bucket can still be deleted. A failed destroy is not atomic; Terraform can remove
security configurations or suspend versioning before the bucket deletion fails.
The provider documents that deleting the versioning resource suspends versioning.
Keep writers stopped during an approved teardown and recover configuration after
an interrupted attempt. Deleting a shared-namespace bucket can permit another
account to claim its name and receive stale requests; retaining the empty bucket
may be preferable after a separate operational review.

## Offline evidence and real prerequisites

The repository baseline is Terraform 1.17.0 / AWS Provider 6.72.0, reusing the
committed dev-root provider lock. Native tests use `mock_provider "aws" {}` and
explicit `command = plan`. Positive plans and rejected-input partial plans are
classified separately. The independent standard-library checker consumes actual
Terraform JSONL and generated policy JSON, checks the complete six-resource
inventory and fixed values, and exercises focused unsafe mutations and malformed
captures. The native suite has **37 passing runs**: seven complete six-resource
plans, 27 empty rejected-input plans and three bucket-only effective-tag
postcondition rejections. A missing required bucket name separately fails before
any plan and is not counted as a passing configuration. The checker rejects
**17 unsafe security mutations** and **18 capture/process faults**, by checking
the actual violated invariants rather than changed hashes. Existing 295 native
and 153 Python regressions are retained; the new native total is **332**.
Completed GitHub run evidence is recorded on the PR.

Mocks/static checks do not prove name availability, actual ownership, provider
account/Region, upload integrity, object encryption, version propagation or real
AWS authorization. Before any future deployment, an independently authorized
workflow must check those prerequisites and test HTTPS/HTTP and service access,
positive/negative artifact reads, the recorded object version, and recovery.
No AWS credentials, authenticated AWS account APIs, live plans, apply/destroy,
objects or deployments are used in this phase. No service-root integration occurs.

## References

- [AWS bucket naming rules and namespaces](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html)
- [AWS S3 policy keys and service-principal exception](https://docs.aws.amazon.com/AmazonS3/latest/userguide/amazon-s3-policy-keys.html)
- [AWS versioning and propagation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/manage-versioning-examples.html)
- [AWS default encryption behavior](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html)
- [AWS bucket tags](https://docs.aws.amazon.com/AmazonS3/latest/userguide/CostAllocTagging.html)
- [AWS Object Ownership](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html)
- [AWS emptying a versioned bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/empty-bucket.html)
- [AWS Lambda artifact inputs](https://docs.aws.amazon.com/lambda/latest/api/API_FunctionCode.html)
- [AWS Provider 6.72.0 bucket documentation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/s3_bucket.html.markdown)
- [AWS Provider 6.72.0 versioning documentation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/s3_bucket_versioning.html.markdown)
