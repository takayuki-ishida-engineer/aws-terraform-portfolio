# aws-terraform-portfolio

An AWS infrastructure portfolio built with Terraform, focused on maintainable
architecture and clear day-to-day operations.

## Current status

Phases 0, 1, 2, and 3-1 are complete. The representative development root at
`infra/services/dev/ca-central-1/serverless-api/`, with fixed identity, version
constraints, AWS provider account restrictions, and an explicit local backend,
retains its Phase 2 foundation. The reusable
[`VPC`](infra/modules/vpc/README.md),
[`IAM access`](infra/modules/iam_access/README.md) and
[`Secrets Manager`](infra/modules/secrets_manager/README.md) modules have native
mock tests.
Phase 3-2 defines three human-access Permission Sets and reviewed inline policies,
without account assignments. Its hardening completes the offline VPC authorization
design; live AWS authorization remains unverified.
Phase 3-3 adds one metadata-only secret container with no values or resource
policy. Human IAM extensions explicitly document the CreateSecret value-write
residual and withheld UpdateSecret/policy administration.
**No service root calls these modules yet.**
No AWS credentials were used and no
AWS infrastructure was deployed or tested against a live account.
The offline CI workflow below independently repeats validation on GitHub-hosted
runners; it never deploys infrastructure.

## Planned architecture

- Separate `dev`, `stg`, and `prod` environments.
- Place each root module at `infra/services/<env>/<region>/<service>/`.
- Use reusable modules with safe defaults; root modules supply
  environment-specific overrides and define provider configurations.
- Use local Terraform state for `dev` and remote state for `stg` and `prod`.
  Remote backend details will be decided in a later phase.
- Manage AWS Secrets Manager metadata with Terraform. Manage actual secret values
  outside Terraform so they do not enter configuration, plans, or state.
- Prioritize maintainability and operational clarity over unnecessary complexity.

The development root foundation and VPC module follow this layout. The staging
and production directories remain placeholders.

## Repository foundation

```text
.
├── .editorconfig
├── .github/
│   └── workflows/
│       └── terraform-offline-ci.yml
├── .gitignore
├── AGENTS.md
├── README.md
├── docs/
│   ├── .gitkeep
│   └── iam-access-operations.md
├── infra/
│   ├── modules/
│   │   ├── iam_access/
│   │   │   ├── README.md
│   │   │   ├── main.tf
│   │   │   ├── outputs.tf
│   │   │   ├── policies.tf
│   │   │   ├── tests/
│   │   │   │   ├── check_authorization_reference.py
│   │   │   │   └── iam_access.tftest.hcl
│   │   │   ├── variables.tf
│   │   │   └── versions.tf
│   │   ├── secrets_manager/
│   │   │   ├── README.md
│   │   │   ├── main.tf
│   │   │   ├── outputs.tf
│   │   │   ├── tests/
│   │   │   │   └── secrets_manager.tftest.hcl
│   │   │   ├── variables.tf
│   │   │   └── versions.tf
│   │   └── vpc/
│   │       ├── README.md
│   │       ├── main.tf
│   │       ├── outputs.tf
│   │       ├── tests/
│   │       │   └── vpc.tftest.hcl
│   │       ├── variables.tf
│   │       └── versions.tf
│   └── services/
│       ├── dev/
│       │   └── ca-central-1/
│       │       └── serverless-api/
│       │           ├── .terraform.lock.hcl
│       │           ├── README.md
│       │           ├── backend.tf
│       │           ├── features.auto.tfvars
│       │           ├── main.tf
│       │           ├── outputs.tf
│       │           ├── providers.tf
│       │           ├── variables.tf
│       │           └── versions.tf
│       ├── stg/
│       │   └── .gitkeep
│       └── prod/
│           └── .gitkeep
└── tests/
    └── .gitkeep
```

`AGENTS.md` records architecture and contributor guidance. Future architecture and
operational documentation belongs in `docs/`, Terraform code in `infra/`, and tests
in `tests/`. `.github/workflows/` contains the offline validation workflow.

`infra/modules/` contains independently tested VPC, human-access and secret-metadata modules,
not yet called by a service root.
`infra/services/` will hold independently managed Terraform root modules at
`<environment>/<region>/<service>/`. The `dev/ca-central-1/serverless-api/` root is
the only implemented root foundation; `stg/` and `prod/` are still placeholders.

## Phase 2 validation

From the development root, Terraform CLI 1.17.0 passed `terraform fmt -check
-recursive`, `terraform init -backend=false -input=false -no-color`, and
`terraform validate -no-color`. Initialization installed HashiCorp-signed AWS
Provider 6.72.0 and generated the committed dependency lock file. These checks
used no AWS credentials and made no AWS API calls; no plan, deployment, or live
account verification was performed. See the [root README](infra/services/dev/ca-central-1/serverless-api/README.md)
for file responsibilities, effective configuration, and validation boundaries.

## Phase 3-1 module validation

From `infra/modules/vpc/`, Terraform CLI 1.17.0 with AWS Provider 6.72.0 passed
formatting, backend-disabled initialization, validation, and native mock tests:
**16 passed, zero failed**. All test runs use mocked `command = plan`; no actual
AWS plan, API calls, credentials, deployments, or live integration tests were
used. The existing development root and its dependency lock remain unchanged.
See the [module README](infra/modules/vpc/README.md) for coverage, configuration
sources, networking defaults, and limitations.

## Phase 3-2 baseline human-access validation

Terraform 1.17.0 / AWS Provider 6.72.0 passed formatting, backend-disabled
initialization using retained verified provider files, validation, and **25
mock-plan tests with zero failures**. The eight WIP tests remain in the suite.
Actual generated IAM JSON and the six-resource plan inventory passed the
stdlib-only static checker against official EC2/SSO authorization JSON, with
HTML-reviewed required-resource markers and nine negative checker self-tests.
Existing VPC and dev root files,
including the root dependency lock, remain unchanged.

Access Admin requires an existing organization instance and an externally verified
management or registered delegated-administrator account. Developer has 27 explicit
EC2 actions representing the current VPC lifecycle, with Project/account/region
scope. Operator retains exactly five metadata actions. Offline Design Readiness
is complete; **Live Authorization Readiness is not complete**. Mock/static checks
do not prove runtime authorization, DNS/public-IP value restrictions or exclusion
of main-route-table replacement. Direct Access Admin rights cannot prevent
self-assignment; independent approval remains procedural unless a separately
reviewed executor design removes direct human assignment writes.
See the [IAM access README](infra/modules/iam_access/README.md) for the complete
action/resource/condition matrix and residual risks, and the
[operations runbook](docs/iam-access-operations.md) for external approval,
CloudTrail, reconciliation and replaceable identifier guidance. No real AWS access,
identities, account assignments, deployments or workload execution roles were
created.

## Phase 3-3 secret metadata

The [Secrets Manager module](infra/modules/secrets_manager/README.md) defines
exactly `aws_secretsmanager_secret.this`: stable metadata/name/tags, a 30-day
recovery default (integer 7–30 only), an optional existing CMK reference and actual
resource-reference outputs. No secret values, versions, rotation, KMS resources,
resource policies, reader roles or root integration are implemented. Values are
initialized/updated separately outside Terraform; metadata creation does not
establish an AWSCURRENT version. Private workloads also need an approved endpoint
or NAT/egress path, which the current isolated VPC does not provide.

Developer adds only CreateSecret, DescribeSecret, GetResourcePolicy, TagResource,
UntagResource and DeleteSecret under `secretsmanager:`, with approved account/
region, Project/tag-integrity and safe-deletion conditions. Operator adds only
scoped DescribeSecret. Access Admin and effective EC2 permissions stay unchanged.
`CreateSecret` can initialize a value through its API; IAM has no documented
payload-absence guard. `UpdateSecret` and resource-policy writes are withheld,
so human Developer alone cannot complete all description/CMK updates or policy
administration. See the [IAM matrix](infra/modules/iam_access/README.md) and
[operations runbook](docs/iam-access-operations.md) for the residual risks and
external execution responsibilities.

Local verification uses Terraform 1.17.0 / AWS Provider 6.72.0. Coverage is 16 VPC,
31 Secrets Manager and 34 IAM mock-plan tests, plus 17 checker negative self-tests
(the original nine retained). CI independently checks actual Secrets Manager
managed-resource inventory and actual test counts; expected counts are not a
substitute for an observed successful GitHub run. No AWS credentials, deployment
or live authorization verification is involved.

## Independent offline Terraform CI

[Terraform offline CI](.github/workflows/terraform-offline-ci.yml) runs on every
pull request targeting `main` and every push to `main`, without path filters.
GitHub-hosted Ubuntu 24.04 executes it independently of Codex Cloud. Obsolete
runs for the same PR/ref are cancelled; the job has a 20-minute timeout.

It installs **Terraform 1.17.0** with the CLI wrapper disabled. The unchanged dev
root lock selects **AWS Provider 6.72.0**; transient copies seed all three child-module
locks so their broader constraints do not select a newer provider. Those child
locks, provider files and captured test output are never committed or uploaded.

| Check | Initial required result |
| --- | --- |
| Repository `terraform fmt -check -recursive` | All Terraform configurations and native test files formatted |
| Dev root `init` / `validate` | Backend disabled, no account-ID input, committed lock read-only and unchanged |
| VPC module `init` / `validate` / native tests | 16 mock-plan tests pass, zero failures or skips |
| Secrets Manager module `init` / `validate` / native tests | 31 mock-plan tests pass, no failures/errors/skips; actual plan contains exactly one secret container |
| IAM module `init` / `validate` / native tests | 34 mock-plan tests pass, zero failures, errors or skips |
| Official authorization-reference check | Existing stdlib checker validates actual policies from the successful IAM JSONL stream against current public EC2/SSO/Secrets Manager JSON |
| Checker negative self-tests | All 17 unsafe mutations rejected; nine original cases retained |

Every command failure fails the job. Bash pipefail preserves the VPC test exit
status; IAM and Secrets Manager original Terraform exit statuses and structured
summaries are checked, alongside the Secrets Manager managed-resource inventory. Exact initial test counts guard against omitted/skipped coverage; an
intentional future coverage change requires reviewing these expectations too.
Malformed or unavailable official JSON fails validation without a stale fallback.
Temporary verbose mock plans/reference files stay under `RUNNER_TEMP`; only test
statuses and failure diagnostics are printed, with no artifact uploads.

The GitHub token has only `contents: read`; checkout does not persist it. Actions
are pinned to verified official release commits: checkout v7.0.1 and
setup-terraform v4.0.1. Terraform runs with metadata lookup disabled, shared AWS
configuration/credentials set to `/dev/null`, and no AWS keys, profiles, secrets,
credential-bearing inputs or OIDC. No real-account plan, AWS account API, apply,
destroy or deployment is authorized or executed by the workflow.

Inspect the repository's **Actions → Terraform offline CI** run, its individual
step logs and job summary, or the PR's **Checks** tab. A first successful run
must actually be observed on GitHub before this CI phase is considered complete;
local execution or YAML inspection alone does not establish GitHub CI success.
The PR records the observed run URL/status rather than asserting success early.

Dependencies include GitHub/action downloads, HashiCorp's Terraform release and
provider registry/release endpoints, and the current public documents at
`https://servicereference.us-east-1.amazonaws.com/v1/ec2/ec2.json` and
`https://servicereference.us-east-1.amazonaws.com/v1/sso/sso.json`, and
`https://servicereference.us-east-1.amazonaws.com/v1/secretsmanager/secretsmanager.json`.
The Secrets Manager endpoint was discovered from its official SAR page. Python 3 and
its standard library come from the runner; no Python packages, containers or
provider cache are added. Codex Cloud's domain allowlist and GitHub-hosted runner
networking are separate; changing one does not configure the other.

A successful run confirms HCL validation, mocked behavior and static reference
compatibility for the tested revision. It does not prove actual AWS authorization,
effective permissions, runtime topology or Identity Center prerequisites.
**Live Authorization Readiness remains incomplete.** Access Admin can still
self-assign approved profiles within its scope; approval/audit controls and the
controlled-executor trade-off remain as documented in the
[IAM module](infra/modules/iam_access/README.md) and
[operations runbook](docs/iam-access-operations.md). AWS credentials and deployment
remain prohibited in this CI and in Codex Cloud.

## Configuration and secrets

Terraform state, saved plans, local secrets, private keys, credentials, and local
environment files must stay out of version control. `.terraform.lock.hcl` remains
trackable. Future `features.auto.tfvars` files may be tracked only when they contain
non-secret feature settings; Terraform loads these files automatically.

Offline validation requires no AWS account access. Do not add cloud credentials
or run deployments as part of this work.
