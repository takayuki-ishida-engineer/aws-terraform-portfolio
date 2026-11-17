# Local DEV workflow

Tools for a real DEV plan, apply or destroy from the operator's workstation
([deployment configuration §1–§2](../../docs/deployment-configuration.md#2-local-only-real-deployment)).
Never run them with real AWS credentials in CI, Codex Cloud or other automation.
They refuse to start when `CI`, `GITHUB_ACTIONS`, `CLAUDE_CODE_REMOTE`,
`CODEX_SANDBOX` or `CODEX_SANDBOX_NETWORK_DISABLED` is set, or when an AWS
credential variable holds the cloud session placeholder `proxy-injected`. These
markers are a safety net, not the boundary: the rule itself is in `AGENTS.md`.

| File | Purpose |
| --- | --- |
| `preflight.py` | Offline checks of a root's input values; with `--live`, read-only AWS checks |
| `run.py` | `init` → preflight (offline and live) → saved plan → typed confirmation → apply of that plan; `migrate-state` moves local State into the optional S3 backend |
| `test_local_workflow.py` | Offline self-tests with fake `terraform` and `aws` executables (Full CI) |
| `check_committed_values.py` | Full CI check of the committed values and the preflight against every DEV root |

## Prepare a root

1. Copy the root's `local.auto.tfvars.example` to `local.auto.tfvars` (ignored by Git)
   and replace every value. It overrides the placeholders in `terraform.tfvars`.
   Never put a credential or secret value in any tfvars file.
2. Sign in with your own AWS CLI profile for the DEV account, for example
   `export AWS_PROFILE=<your-dev-profile>`. Unset any `AWS_ENDPOINT_URL*` variable.
3. Run the preflight, then the wrapper:

```bash
python3 scripts/local-workflow/preflight.py network --live
```

```bash
python3 scripts/local-workflow/run.py network plan
```

```bash
python3 scripts/local-workflow/run.py network apply
```

Apply in the order `tfstate` (only for the optional S3 backend), `network`,
`platform`, then `serverless-api` and `api`; destroy in the reverse order. The platform root needs the network output in its
`local.auto.tfvars` (`terraform -chdir=infra/services/dev/ca-central-1/network output -json network`).
Step 1 item 6 automates that hand-off and the serverless-api artifact upload, and
adds the full runbook.

## What the preflight checks

Offline (no AWS call):

- `local.auto.tfvars` exists in the root, is ignored by Git and is not tracked.
- It assigns every environment-specific input of that root:

  | Root | Environment-specific inputs |
  | --- | --- |
  | network | `project`, `aws_account_id` |
  | platform | `project`, `aws_account_id`, `bootstrap_admin_role_arn`, `network_reference` |
  | serverless-api | `project`, `aws_account_id`, `artifact_object_version` |
  | api | `project`, `aws_account_id`, `callback_urls`, `logout_urls`, `default_redirect_uri` |
  | tfstate | `project`, `aws_account_id` |

- No effective value of those inputs is a documented placeholder, an unedited
  example value or the Emulator's synthetic account `000000000000`, and every
  account ID inside them equals `aws_account_id`. Effective values come from
  `terraform console`, so Terraform's own precedence applies; the root must be
  initialized first (`run.py` does this).
- With the optional S3 backend: `backend_override.tf` and `backend.s3.tfbackend` are
  both ignored and untracked, the override holds only an empty `backend "s3" {}`,
  and the settings are exactly `bucket = "<project>-dev-s3-tfstate"`,
  `key = "<project>/dev/ca-central-1/<root>/terraform.tfstate"`,
  `region = "ca-central-1"`, `use_lockfile = true` and `encrypt = true`, with no
  profile, role or credential. The tfstate root must stay local.

Live (`--live`, read-only, workstation only):

- Refused in CI or a cloud session (see above) or when an `AWS_ENDPOINT_URL*` override exists.
- `aws sts get-caller-identity` must return `aws_account_id`.
- With the S3 backend: `aws s3api get-bucket-versioning` must report `Enabled` and
  `aws s3api get-public-access-block` all four settings `true` for the State bucket.
- platform: `aws eks describe-addon-versions` must list each pinned add-on version as
  compatible with `kubernetes_version`, and the SSM public parameter for the pinned
  AL2023 node AMI release must exist.

Only `sts get-caller-identity`, `s3api get-bucket-versioning`,
`s3api get-public-access-block`, `eks describe-addon-versions` and
`ssm get-parameter` can be called. The scripts never read, print or store a
credential or secret value.

## Optional S3 backend

1. Apply the bootstrap root: `python3 scripts/local-workflow/run.py tfstate apply`.
2. In a root, copy `backend_override.tf.example` to `backend_override.tf` and
   `backend.s3.tfbackend.example` to `backend.s3.tfbackend`, and replace `project`
   with your project (compare with
   `terraform -chdir=infra/services/dev/ca-central-1/tfstate output -json backend_settings`).
3. Move the root's State:

```bash
python3 scripts/local-workflow/run.py network migrate-state
```

It checks the files, the caller account and the bucket, then runs
`terraform init -backend-config=backend.s3.tfbackend -migrate-state`; Terraform
asks before copying. From then on `run.py` passes the backend settings on every init.

Back to local State: delete both files, then run
`terraform -chdir=<root> init -migrate-state` and confirm. Teardown of the bucket:
every root back on local State (or destroyed), every object version deleted
(`force_destroy` is `false`), then `python3 scripts/local-workflow/run.py tfstate destroy`.

## Saved plans

`run.py` writes the plan to `dev-local.tfplan` inside the root (ignored by Git,
checked before writing), applies exactly that plan after you type the root name,
and deletes it afterwards, because a saved plan can contain sensitive values.
