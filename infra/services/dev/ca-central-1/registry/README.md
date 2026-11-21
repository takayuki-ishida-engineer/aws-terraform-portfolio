# DEV private ECR registry

Creates the private ECR repositories that the Kubernetes runtime pulls its images
from, so node egress stays closed (finding F18, Step 1 item 6b-B1). The renderer
already references `<account>.dkr.ecr.ca-central-1.amazonaws.com/<project>-dev-ecr-<purpose>@<digest>`
(item 6b-B2). The operator copies the pinned images in with the mirror script (B3,
not delivered yet). Nothing here is created in AWS until an operator applies the root
from a workstation, under the separately approved Live controls.

## Selected infrastructure

| Item | Value | Source |
| --- | --- | --- |
| Module | [`ecr_repository`](../../../../modules/ecr_repository/README.md) | Root selection |
| Repositories | One per purpose in [`kubernetes/images.lock.json`](../../../../../kubernetes/images.lock.json), the only image inventory: `<project>-dev-ecr-istio-pilot`, `<project>-dev-ecr-istio-proxy`, `<project>-dev-ecr-lbc` | Root Override (`purposes`, read from the lock) |
| Private visibility, `IMMUTABLE` tags, `AES256`, no scanning, no repository or lifecycle policy | Fixed protections | Module Fixed |
| `force_delete` | `false`; `true` only through the teardown switch | Root Override (`force_delete`, default `false`) of the Module Default `false` |
| Account and Region guard | `allowed_account_ids = [aws_account_id]`, Region `ca-central-1`, and the module's postcondition on each repository's Region, registry ID, ARN and URL | Root Fixed, Module Fixed |
| Image lock contract | Output precondition: lock version 1, registry `ca-central-1`, repository `${project}-dev-ecr-${purpose}`, digest references, each purpose once | Root Fixed |
| Extra tags | `var.tags`, default `{}` | Root Override (pass-through) |
| Provider | `ca-central-1`, `default_tags` `project`, `env = dev`, `managed = terraform` | Root Fixed |
| Backend | `local`; the optional S3 backend uses key `<project>/dev/ca-central-1/registry/terraform.tfstate` | Root Fixed (examples tracked) |
| Terraform / AWS provider | `~> 1.17.0` / `~> 6.72.0`, committed lock | Root Fixed |

## Input values

`terraform.tfvars` holds the placeholders `project = "project"` and
`aws_account_id = "123456789012"`. Copy `local.auto.tfvars.example` to the untracked
`local.auto.tfvars`, and use the same `project` and `aws_account_id` as the other DEV
roots. `tags` (optional) may not set `project`, `env`, `service`, `managed` or `Name`.
The repositories come from the image lock, not from a variable. The
[local workflow](../../../../../scripts/local-workflow/README.md) preflight refuses a
plan or apply while a placeholder remains, and refuses any live run in CI or a cloud
session.

## Outputs

| Output | Description |
| --- | --- |
| `registry` | `host` (`<account>.dkr.ecr.ca-central-1.amazonaws.com`) and `repositories`: per locked purpose, the repository `name`, `arn` and `repository_url`. No credentials or tokens |

## Use

Apply after `network` and before `platform`:

```bash
python3 scripts/local-workflow/run.py registry apply
```

Teardown ([runbook §7](../../../../../docs/dev-runbook.md#7-teardown)):
1. Set `force_delete = true` in `local.auto.tfvars`.
2. Apply:

   ```bash
   python3 scripts/local-workflow/run.py registry apply
   ```

3. Destroy:

   ```bash
   python3 scripts/local-workflow/run.py registry destroy
   ```

## Verification (offline)

`tests/registry.tftest.hcl` runs 7 mock-provider plans: 2 positive plans and 5
rejected inputs. `tests/check_root.py` does the following:
- checks the actual plans with the module's checks;
- re-proves `kubernetes/images.lock.json` with the Kubernetes validator's own lock
  check;
- requires the repositories and the output to be exactly the lock's purposes;
- rejects a run without `project` or `aws_account_id`.

With `--self-test` it requires 12 semantic mutations and 4 capture failures to be
rejected. The mutations include an extra, missing or renamed repository, a lock with
an extra or missing purpose or a tag-based contract, and a leaking output. Full CI
also mock-plans the committed values, checks the preflight and the backend examples,
and runs all of these. No AWS API is called.

Not tested: creating the repositories in real AWS, the pull through the ECR endpoints
and S3 over NAT, and the emulator lifecycle. This root is outside the Step 2
rehearsal's `all`.
