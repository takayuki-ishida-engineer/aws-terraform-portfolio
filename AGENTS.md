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

## Current phase only: Phase 3-3.6 simulator context classification

Phase 3-3.5 is merged and main CI succeeded. Use the new
`fix/iam-simulator-context-classification` branch from latest `main`. This task
authorizes a narrow toolkit request/classification correction, deterministic
regressions, the toolkit README, minimal CI/test-count documentation and this
section. Preserve approved Terraform policies/architecture and permanent rules.

- Derive projections only from actual rendered policy documents. Omit only
  provably action-nonmatching statements; independently verify semantic structure
  for the tested action. Preserve every relevant Allow/Deny, resource and condition.
- Do not resource-filter or build a generic evaluator. Uncertain action selectors
  cannot justify dropping a statement or proving absent authorization.
- Keep missing context from potentially applicable statements inconclusive. Never
  invent values or erase intentional Null/IfExists absence to force a result.
  Preserve unexpected-Allow, explicit/implicit deny, pagination, malformed-response
  and complete multi-resource safeguards.
- Label static action absence separately from AWS simulation evidence. Preserve
  all four intentionally unsupported protections as inconclusive. Bind new request
  evidence to original/projected hashes and case; do not relabel legacy captures.
- Record the owner's prior 21/29 supported result counts accurately, without raw
  reports/session identifiers, and require a human AWS rerun before claiming any
  previously inconclusive case resolved. Codex performs no authenticated AWS calls.
- Preserve all previous tests and add meaningful classification/semantic-mutation
  regressions. Keep Terraform 1.17.0, Provider 6.72.0, mock plan tests, read-only CI,
  action pins, no-credentials/no-OIDC/no-artifact boundaries and Approach A.
- Do not create or use credentials, users or keys; no AWS APIs, real plans, apply,
  destroy, deployment, policy changes, roots or next infrastructure phase.

Commit, push, open a PR, report actual checks and CI status, then stop for
independent review. Do not merge or delete the working branch.
