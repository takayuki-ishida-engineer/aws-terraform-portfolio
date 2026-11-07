# aws-terraform-portfolio

An AWS infrastructure portfolio built with Terraform, focused on maintainable
architecture and clear day-to-day operations.

## Current status

Phases 0, 1, and 2 are complete. The representative development root at
`infra/services/dev/ca-central-1/serverless-api/`, with fixed identity, version
constraints, AWS provider account restrictions, and an explicit local backend,
retains its Phase 2 foundation. Phase 3-1 adds the reusable
[`infra/modules/vpc/`](infra/modules/vpc/README.md) module and native mock tests.
**No service root calls this module yet.** No AWS credentials were used and no
AWS infrastructure was deployed or tested against a live account. There are no
CI workflows.

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
│   └── .gitkeep
├── .gitignore
├── AGENTS.md
├── README.md
├── docs/
│   └── .gitkeep
├── infra/
│   ├── modules/
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
in `tests/`. `.github/` is a placeholder; it contains no workflows.

`infra/modules/` contains the independently tested VPC child module, not yet called
by a service root.
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

## Configuration and secrets

Terraform state, saved plans, local secrets, private keys, credentials, and local
environment files must stay out of version control. `.terraform.lock.hcl` remains
trackable. Future `features.auto.tfvars` files may be tracked only when they contain
non-secret feature settings; Terraform loads these files automatically.

Phase 3-1 requires no AWS access. Do not add cloud credentials or run deployments
as part of this foundation work.
