# aws-terraform-portfolio

An AWS infrastructure portfolio built with Terraform, focused on maintainable
architecture and clear day-to-day operations.

## Current status

**Infrastructure is not yet implemented.** Phase 0 repository foundations are
complete. Phase 1 adds infrastructure directory placeholders and documentation
only. No Terraform root modules, child modules, provider configurations, backends,
resources, tests, or CI workflows have been implemented. No cloud credentials are
configured and no infrastructure has been deployed or tested in this phase.

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

These are design decisions for future work. The module library and environment
directories are placeholders only; region and service directories have not been
created.

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
│   │   └── .gitkeep
│   └── services/
│       ├── dev/
│       │   └── .gitkeep
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

`infra/modules/` will hold reusable AWS Terraform child modules.
`infra/services/` will hold independently managed Terraform root modules at
`<environment>/<region>/<service>/`. Its `dev/`, `stg/`, and `prod/` directories are
currently empty placeholders for development, staging, and production.

## Configuration and secrets

Terraform state, saved plans, local secrets, private keys, credentials, and local
environment files must stay out of version control. `.terraform.lock.hcl` remains
trackable. Future `features.auto.tfvars` files may be tracked only when they contain
non-secret feature settings; Terraform loads these files automatically.

Phase 1 requires no cloud access. Do not add cloud credentials or run deployments
as part of this foundation work.
