# ecr_repository

Private Amazon ECR repositories for the digest-pinned Kubernetes runtime image
mirror (finding F18, Step 1 item 6b-B1). The operator copies each pinned upstream
index into its repository with `skopeo copy --all --preserve-digests` (B3). The nodes
pull through the existing `ecr.api`/`ecr.dkr` interface endpoints, with image layers
from S3 over the existing NAT gateway. The calling root owns the provider.

## Resources

| Resource | Purpose |
| --- | --- |
| `aws_ecr_repository.this[<purpose>]` | One private repository per purpose |

Deliberately absent:
- **No repository or registry policy.** Same-account IAM governs access, and no public
  or cross-account access is granted.
- **No lifecycle policy.** No image is ever expired automatically, so no
  multi-architecture index, child manifest or older digest kept for a rollback can
  disappear. A rule that only expires untagged images would be safe for referenced
  child manifests, which ECR does not expire while their index exists. But it would
  remove an index pushed without a tag, and that cannot be ruled out until the mirror
  script (B3) proves it always tags.
- **No pull through cache rule, Secrets Manager secret, KMS key, IAM role, NAT gateway
  or VPC endpoint.**

## Effective configuration

| Setting | Value | Source |
| --- | --- | --- |
| Repository name | `<name_prefix>-ecr-<purpose>` for each of `purposes` | Caller input, Module Fixed pattern |
| Visibility | Private (`aws_ecr_repository`; ECR Public is a different service) | Module Fixed |
| `image_tag_mutability` | `IMMUTABLE`, no exclusion filter: a tag can never point to another image | Module Fixed |
| Encryption | `AES256` (Amazon ECR managed); no customer managed KMS key | Module Fixed |
| `force_delete` | `false`: Terraform will not delete a repository that still holds images | Module Default `false`; the root's teardown switch may set `true` |
| Repository-level scan on push | `scan_on_push = false`. It does not guarantee that no image is scanned or that scanning is free; see [Image scanning](#image-scanning) | Module Fixed (repository setting only) |
| Registry-level scanning | Not managed or read; the account's existing configuration applies | Outside this module (NOT_TESTED) |
| Account and Region guard | Postcondition: the repository's Region, registry ID, ARN and URL must match `expected_scope` | Module Fixed |
| Tags | Caller `tags` plus module-owned `Name = <repository name>` and `service = ecr` | Module Default `{}` for `tags`; `Name`/`service` Module Fixed |

The root's provider `default_tags` add `project`, `env` and `managed`.

## Image scanning

- **Repository setting only.** `scan_on_push = false` is the only scanning setting
  here. It does not guarantee that scanning is off in real AWS, or that no scanning
  charge arises.
- **Registry-wide configuration.** Amazon ECR configures scanning per registry, which
  means per account and Region. The configuration selects basic or enhanced scanning,
  with scan rules and repository filters.
  - Enhanced scanning uses Amazon Inspector and may add Inspector charges.
  - Where a registry-level configuration applies, the repository setting may not be
    the one that takes effect.
- **Not managed here.** This module neither manages nor reads the registry scanning
  configuration (`aws_ecr_registry_scanning_configuration`), and its offline checks
  reject any resource other than the repositories.
- **Separate decision.** Whether to use basic scanning, and any change to the
  registry-wide setting, is a separate security decision.
- **NOT_TESTED.** The registry's effective scanning configuration and the Amazon
  Inspector billing conditions, to confirm in a future Live verification.

## Inputs and validation

| Input | Type | Default | Validation |
| --- | --- | --- | --- |
| `name_prefix` | string | required | `<project>-<env>`: a 1–10 character lowercase project token starting with a letter, then `-dev`, `-stg` or `-prod` |
| `purposes` | set(string) | required | 1–10 lowercase hyphenated tokens of at most 40 characters, starting with a letter (no `/`) |
| `expected_scope` | object(`account_id`, `region`) | required | 12-digit account ID and an AWS Region name |
| `force_delete` | bool | `false` | Teardown switch only |
| `tags` | map(string) | `{}` | No `Name`, `service` or `aws:` key; with `Name`/`service` at most 50 tags; keys 1–128 and values up to 256 characters |

## Outputs

| Output | Description |
| --- | --- |
| `repositories` | Per purpose: `name`, `arn` and `repository_url` (`<account>.dkr.ecr.<region>.amazonaws.com/<name>`). No credentials |

## Verification (offline)

`tests/ecr_repository.tftest.hcl` runs 16 mock-provider plans:
- 2 positive plans: the three locked purposes, and the teardown switch with caller
  tags;
- 2 postcondition failures: a foreign account and another Region;
- 12 rejected inputs.

`tests/check_ecr_repository.py` independently checks the actual planned resource set
and values. With `--self-test` it requires 23 semantic mutations and 12 capture
failures to be rejected. The mutations include:
- mutable tags or an exclusion filter, forced deletion by default, KMS encryption,
  scan on push;
- another name, account or Region, or a public URL;
- an extra repository, a repository or registry policy, a lifecycle policy or a pull
  through cache rule.

Full CI runs both. No repository is created and no AWS API is called.
