# tfstate_bucket

Private, versioned S3 bucket for Terraform State, used by the optional DEV S3
backend ([deployment configuration §3](../../../docs/deployment-configuration.md#3-terraform-state)).
State can contain sensitive values, so every protection is fixed in the module.
Locking uses the S3 native lock file (`use_lockfile = true` in each root's backend
settings); no DynamoDB table is created. The calling root owns the provider.

## Resources

| Resource | Purpose |
| --- | --- |
| `aws_s3_bucket.this` | The State bucket |
| `aws_s3_bucket_versioning.this` | Keeps every earlier State version |
| `aws_s3_bucket_public_access_block.this` | Blocks all public access |
| `aws_s3_bucket_ownership_controls.this` | Disables ACLs (bucket owner enforced) |
| `aws_s3_bucket_server_side_encryption_configuration.this` | Default encryption |
| `aws_s3_bucket_lifecycle_configuration.this` | Expires old State versions, aborts stale uploads |
| `aws_s3_bucket_policy.this` | Denies non-TLS and pre-TLS-1.2 requests |

## Effective configuration

| Setting | Value | Source |
| --- | --- | --- |
| Bucket name | `bucket_name` (required, no default) | Caller input |
| Namespace | `global` | Module Fixed |
| `force_destroy` | `false`: a bucket that still holds State or versions cannot be deleted by Terraform | Module Fixed |
| Versioning | `Enabled` | Module Fixed |
| Public access block | All four settings `true` | Module Fixed |
| Object ownership | `BucketOwnerEnforced` (ACLs disabled) | Module Fixed |
| Encryption | SSE-S3 (`AES256`, Amazon S3 managed keys); no customer managed KMS key | Module Fixed |
| Lifecycle | One rule `state-history` for all objects: noncurrent versions expire after `noncurrent_version_retention_days`; incomplete multipart uploads abort after 7 days; current State never expires | Module Fixed rule, retention Module Default `90` |
| Bucket policy | `DenyInsecureTransport` (`aws:SecureTransport = false`) and `DenyOutdatedTls` (`s3:TlsVersion < 1.2`) for the bucket and its objects, no service exception | Module Fixed |
| Tags | Caller `tags` plus module-owned `Name = <bucket_name>` and `service = s3` | Module Default `{}` for `tags`; `Name`/`service` Module Fixed |

The root's provider `default_tags` add `project`, `env` and `managed`.

## Inputs and validation

| Input | Type | Default | Validation |
| --- | --- | --- | --- |
| `bucket_name` | string | required | 3–63 lowercase letters, digits or hyphens; starts and ends with a letter or digit; ends in `-s3-tfstate`; no `xn--`, `sthree-` or `amzn-s3-demo-` prefix; no periods |
| `noncurrent_version_retention_days` | number | `90` | Whole days from 30 through 365 |
| `tags` | map(string) | `{}` | No `Name`, `service` or `aws:` key; with `Name`/`service` at most 50 tags; keys 1–128 and values up to 256 characters |

## Outputs

| Output | Description |
| --- | --- |
| `bucket_name` | Bucket name for each root's untracked `backend.s3.tfbackend` |
| `bucket_arn` | Bucket ARN for reviewed IAM policies that grant State access |
| `versioning_status` | Always `Enabled` |

## Verification (offline)

`tests/tfstate_bucket.tftest.hcl` runs 14 mock-provider plans: 3 positive plans
(default, custom retention and tags, maximum retention) and 11 rejected inputs.
`tests/check_tfstate_bucket.py` independently checks the actual planned resource
set and values and, with `--self-test`, requires 23 semantic mutations and 12
capture failures to be rejected. Full CI runs both. No bucket is created and no
AWS API is called; global name availability, IAM access and real encryption
behaviour are verified only on a real deployment.

## Teardown

Because `force_destroy` is `false` and versioning keeps every State version,
deleting the bucket first needs every root moved back to local State (or destroyed)
and every object version removed by the operator. See the local workflow README.
