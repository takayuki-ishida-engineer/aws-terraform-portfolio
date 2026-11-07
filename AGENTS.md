# Repository guidance

## Current scope: Phase 0

This repository currently contains its foundation only. Infrastructure is not yet
implemented. Preserve existing files and content wherever possible, keep changes
within the requested phase, and stop after completing that phase.

For Phase 0, create only the requested root documentation and configuration files
and `.gitkeep` placeholders in `.github/`, `infra/`, `tests/`, and `docs/`. Do not
create nested Terraform directories, modules, providers, resources, or workflows.
Implementation requires a later explicit request.

## Agreed Terraform architecture

- Maintain separate `dev`, `stg`, and `prod` environments.
- Locate root modules at `infra/services/<env>/<region>/<service>/`.
- Build reusable modules with safe defaults. Root modules provide explicit
  environment-specific overrides.
- Define provider configurations in root modules and pass them to reusable modules
  as needed. Do not configure providers inside reusable modules.
- Use local state for `dev` and remote state for `stg` and `prod`. Remote backend
  selection and setup are future work, not part of Phase 0.
- Manage AWS Secrets Manager metadata with Terraform. Manage actual secret values
  outside Terraform; do not put them in Terraform configuration, variables,
  outputs, plans, or state.
- Prioritize maintainability and operational clarity. Keep module boundaries,
  environment differences, and operational responsibilities easy to understand.

These rules describe future implementation; they do not authorize creating
infrastructure during Phase 0.

## Working rules

- Do not add or use cloud credentials or perform cloud deployments as part of this
  phase. Do not run `terraform apply` or `terraform destroy`.
- Never commit state, plan files, local secrets, private keys, credentials, or
  environment files. Keep `.terraform.lock.hcl` trackable.
- Track future `features.auto.tfvars` files only for non-secret feature settings.
  Do not use this exception to store credentials or secret values.
- Avoid unrelated changes and automatic merges.
- Follow `.editorconfig` and run `git diff --check` before finishing.
- Report the resulting directory tree and changed files, then stop at Phase 0.
