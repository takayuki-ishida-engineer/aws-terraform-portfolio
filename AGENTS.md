# Repository guidance

## Permanent repository-wide rules

These rules persist across phases. Preserve existing files and content wherever
possible, keep changes small and reviewable, and avoid unrelated modifications.
Work only within the explicitly authorized scope. Future phases are allowed when
explicitly authorized; phase-specific restrictions below do not permanently prohibit
future implementation.

### Terraform architecture and responsibility boundaries

- Maintain separate `dev`, `stg`, and `prod` environments.
- Locate root modules at `infra/services/<env>/<region>/<service>/`.
- Root modules own provider configurations, backend configurations, infrastructure
  selection, and environment-specific overrides. Pass providers to child modules
  as needed; do not configure providers inside reusable child modules.
- Reusable child modules live in `infra/modules/` and own resource implementation,
  secure defaults, input validation, and documented outputs.
- `infra/stacks/` is optional. Introduce it only when composition provides concrete
  reuse value; do not add a stack layer without that need.
- Prioritize maintainability and operational clarity. Keep module boundaries,
  environment differences, and operational responsibilities easy to understand.

### Effective configuration and feature flags

- Module READMEs and Root READMEs must document effective configuration values and
  their sources, using these categories:
  - **Root Override**: an explicit value supplied by a root module, overriding a
    child module default where one exists.
  - **Module Default**: the child module's declared default, used when the root
    supplies no override.
  - **Module Fixed**: a value fixed inside the child module with no root override.
- Module READMEs document defaults, fixed values, validation, and outputs. Root
  READMEs document the selected infrastructure and effective values, including
  overrides and inherited defaults or fixed values. Never document secret values.
- Use feature flags only for genuine optional functionality. Do not use flags to
  conceal breaking changes or replace required configuration.
- Require Terraform plan review for changes affecting existing infrastructure.
  Obtain such plans through an authorized workflow outside Codex Cloud; this
  requirement does not authorize AWS credentials or deployments in Codex Cloud.

### Terraform state and scope

- Separate state by environment, region, and service, matching the root module
  boundary. Do not share a state file across those boundaries.
- Use local state for `dev` and remote state for `stg` and `prod`. Remote backend
  selection and setup require a later implementation phase.
- Cross-region replication and disaster recovery orchestration are out of scope.

### Secrets and Codex Cloud boundaries

- Use **Secrets Manager approach A only**: Terraform manages Secrets Manager
  metadata; actual secret values are managed outside Terraform.
- Never read, pass, create, update, or output actual secret values through
  Terraform. Do not put them in configuration, variables, outputs, plans, or state.
- Do not implement ephemeral or write-only secret-value management alternatives.
- Never request, add, or use AWS credentials in Codex Cloud. Never deploy or
  destroy AWS infrastructure from Codex Cloud; do not run `terraform apply` or
  `terraform destroy` there. Future phase authorization does not relax this rule.
- Never commit state, plan files, local secrets, private keys, credentials, or
  environment files. Keep `.terraform.lock.hcl` trackable.
- Track `features.auto.tfvars` only for non-secret feature settings. Do not use
  this exception to store credentials or secret values.

### Git workflow and verification

- For each new development task, create a new working branch from the latest
  `main`. Never commit directly to `main`.
- Follow branch -> commit -> push -> PR -> review -> merge. Commit and push
  changes before creating a PR. Continue review corrections on the existing open
  PR branch.
- Require PR review and approval before merge. Do not merge automatically; merge
  only when explicitly authorized, using **Squash and merge** by default.
- Preserve working branches after merge; do not delete them. Do not reuse a merged
  branch for new development; start a new branch from updated `main`.
- Follow `.editorconfig`, inspect the diff and changed file scope, check for
  secrets, and run `git diff --check` before finishing.

## Current phase only: Phase 2

Phases 0 and 1 are complete and merged through PRs #1 and #2. Phase 2 authorizes
only the development root foundation at
`infra/services/dev/ca-central-1/serverless-api/`. Preserve all permanent rules.

- Keep environment `dev`, region `ca-central-1`, and service `serverless-api`
  fixed in the root. Do not create additional roots or reusable child modules.
- Add the requested Terraform foundation files, a comments-only
  `features.auto.tfvars`, and a practical root README. Remove only the obsolete
  `infra/services/dev/.gitkeep`; preserve module, staging, and production keeps.
- Require Terraform `~> 1.17.0` and `hashicorp/aws` `~> 6.72.0`. Generate and commit
  `.terraform.lock.hcl` only through successful initialization; never fabricate it.
- Keep provider configuration in the root, with a required, validated 12-digit
  account ID input and `allowed_account_ids`. Never hardcode a real account ID or
  disable provider credential validation or account restrictions.
- Use an explicit local backend. Do not add S3 backends, remote-state resources,
  bootstrap scripts, or state migration tools.
- Do not add AWS resources or data sources, real or placeholder child module
  calls, stacks, workflows, deployment scripts, or speculative module tests.
  Cross-region integrations and disaster recovery designs remain out of scope.
- Never use AWS credentials or call AWS APIs. Do not run `terraform plan`,
  `terraform apply`, or `terraform destroy` in Codex Cloud.
- Inspect configuration and run formatting, backend-disabled initialization, and
  validation when the required CLI and registry access are available. Report any
  blocked checks accurately; do not bypass security controls to make checks pass.
- Update the repository README and only this phase-specific section of AGENTS.
  Document actual validation results and distinguish current root-defined values
  from future Root Override, Module Default, and Module Fixed configuration.

Use `feat/phase-2-root-module` from the latest `main`, not a previous phase branch.
Inspect the full staged diff, check scope and secrets, and run `git diff --check`.
Commit, push, and open a PR for external manual review, then stop. Do not merge
the PR or delete the working branch. Require manual PR review and explicit
authorization before further implementation; do not begin Phase 3.
