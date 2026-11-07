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

## Current phase only: Phase 3-3.5 IAM scalability and validation readiness

Phase 3-3 is merged and main CI succeeded. Work only on
`fix/iam-policy-scalability-validation` from latest `main`. This task authorizes
the per-account IAM policy module, Developer service-policy composition and
attachment, actual-policy regression/export/validation toolkit, offline CI and
relevant documentation. Preserve all permanent rules above, existing VPC and
Secrets Manager resources, dev root, provider constraints and root lock.

- Preserve exactly Portfolio-Access-Admin, Portfolio-Developer and
  Portfolio-Operator. Access Admin and Operator policies stay unchanged. Developer
  retains exact reviewed EC2 permissions inline; move only the reviewed six
  Secrets Manager actions into an account-owned customer-managed policy.
- Use fixed policy identity Portfolio-Developer-SecretsManager, path /. Each
  workload account's owning root must select/restrict its provider and create
  its matching policy before the Identity Center reference is provisioned.
  The reference creates no account policy and auto-provisions assigned accounts.
- Add no users, roles, groups, keys, assignments, KMS resources, roots, workload
  permissions, arbitrary policy injection, speculative services or deployment.
  Preserve all existing tag, region/account, creation and recovery safeguards;
  explicitly document intentional owning-account scope tightening.
- Enforce separate inline and managed-policy quotas and the reviewed attachment
  budget. Compare actual rendered policy unions with the generated approved
  synthetic baseline; do not replace meaningful authorization tests with counts.
- Prepare the stdlib/AWS CLI validation toolkit with actual mocked-plan exports,
  reviewed cases, private outputs, accurate findings/result parsing and deterministic
  offline tests. Default execution must make zero AWS CLI/API or credential calls.
- Authenticated toolkit execution requires an explicit user flag in a later
  authorized CloudShell/local session, and is refused in Codex Cloud and CI.
  Only ValidatePolicy, SimulateCustomPolicy and GetContextKeysForCustomPolicy are
  prepared; do not execute them here, call STS, discover/request credentials or
  provision an execution identity. No new IAM user, keys, secrets or OIDC.
- Treat missing context, unsupported simulation, partial multi-resource results
  and incomplete/API-error responses honestly. Unexpected grants fail; warnings
  require review. Synthetic policy context is not an assumed session or proof of
  effective authorization, propagation, KMS access or live infrastructure safety.
- Preserve all prior native cases, with actual cross-module policies where the
  source moved. Use only mock AWS providers and explicit plan commands with
  Terraform 1.17.0 / AWS Provider 6.72.0. CI remains read-only and credential-free,
  uploads no plans/state/raw results and fails on errors/skips or changed counts.
- Document migration order, rollback, drift, customer-policy ownership and all
  inherent residual risks. Distinguish code resolution, offline evidence and
  unperformed manual AWS/live verification. Never suggest routine root usage.
- If an essential public source is blocked, record exact host/URL/status, preserve
  valid work, push an explicitly incomplete checkpoint if safe and stop for the
  user to publish an allowlist update. Do not bypass or fabricate evidence.

Commit, push, open a PR, observe completed/success GitHub CI and stop for external
review. Do not merge, delete the branch, perform CloudShell validation, integrate
service roots or begin Phase 3-4.
