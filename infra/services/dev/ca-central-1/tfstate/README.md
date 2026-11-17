# DEV Terraform State bucket bootstrap

Creates the one S3 bucket that the optional DEV S3 backend uses
([deployment configuration §3](../../../../../docs/deployment-configuration.md#3-terraform-state)).
Local State stays the default for every DEV root; this root is applied only when
the Owner wants State in S3, for example for a handover. The bootstrap root itself
always keeps local State, because it creates the bucket.

## Selected infrastructure

| Item | Value | Source |
| --- | --- | --- |
| Module | [`tfstate_bucket`](../../../../modules/tfstate_bucket/README.md) | Root selection |
| Bucket name | `<project>-dev-s3-tfstate` (global namespace, no uniqueness suffix) | Root Override (`bucket_name`) |
| Versioning, public access block, `BucketOwnerEnforced`, SSE-S3, TLS-only and TLS 1.2 policy, `force_destroy = false` | Fixed protections | Module Fixed |
| Noncurrent State versions | Expire after 90 days; incomplete uploads abort after 7 days | Module Default (`noncurrent_version_retention_days`), Module Fixed rule |
| Extra tags | `var.tags`, default `{}` | Root Override (pass-through) |
| Provider | `ca-central-1`, `allowed_account_ids = [aws_account_id]`, `default_tags` `project`, `env = dev`, `managed = terraform` | Root Fixed |
| Backend | `local` (never overridden) | Root Fixed |
| Terraform / AWS provider | `~> 1.17.0` / `~> 6.72.0`, committed lock | Root Fixed |

## Input values

`terraform.tfvars` holds the placeholders `project = "project"` and
`aws_account_id = "123456789012"`. Copy `local.auto.tfvars.example` to the untracked
`local.auto.tfvars` and use the same `project` and `aws_account_id` as the other
DEV roots. `tags` (optional) may not set `project`, `env`, `service`, `managed` or
`Name`. The [local workflow](../../../../../scripts/local-workflow/README.md)
preflight refuses a plan or apply while a placeholder remains.

## Outputs

| Output | Description |
| --- | --- |
| `bucket_name` | `<project>-dev-s3-tfstate` |
| `bucket_arn` | Bucket ARN for reviewed IAM policies |
| `backend_settings` | `bucket`, `region = ca-central-1`, `use_lockfile = true`, `encrypt = true` and `keys`: one `<project>/dev/ca-central-1/<root>/terraform.tfstate` per root (`network`, `platform`, `serverless-api`, `api`) |

Each root's `backend.s3.tfbackend.example` already has this shape; replace
`project` with your project after applying this root.

## Use

```bash
python3 scripts/local-workflow/run.py tfstate apply
```

```bash
terraform -chdir=infra/services/dev/ca-central-1/tfstate output -json backend_settings
```

Then, per root, copy `backend_override.tf.example` to `backend_override.tf` and
`backend.s3.tfbackend.example` to `backend.s3.tfbackend` (both untracked), fill in
the project and run `python3 scripts/local-workflow/run.py <root> migrate-state`.

## Teardown

Move every root back to local State (or destroy it) first. Then remove every
object version from the bucket, because `force_destroy` is `false` and versioning
keeps all State versions, and destroy this root with
`python3 scripts/local-workflow/run.py tfstate destroy`. The local workflow README
lists the steps.

## Verification (offline)

`tests/tfstate.tftest.hcl` runs 6 mock-provider plans (2 positive, 4 rejected
inputs). `tests/check_root.py` checks the actual planned module resources and
`backend_settings`, proves that omitting `project` or `aws_account_id` fails before
any plan, and requires 8 semantic mutations and 4 capture failures to be rejected.
Full CI also plans this root with its committed values and runs the preflight
against it. No bucket is created and no AWS API is called.
