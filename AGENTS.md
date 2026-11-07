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

## Current phase only: Phase 3-CI offline validation

Phase 3-2 hardening is merged. This task authorizes only
`.github/workflows/terraform-offline-ci.yml`, removal of `.github/.gitkeep`,
minimal repository README updates and this phase-specific section. Preserve all
permanent rules above and all existing Terraform source, policies, tests,
backends, provider restrictions, dependency locks and the Python checker.

- Use `ci/terraform-offline-validation` from latest `main`. Validate PRs targeting
  `main` and pushes to `main`, without path filters or privileged trigger types.
- Use GitHub-hosted Ubuntu, a bounded timeout, concurrency cancellation, only
  `contents: read`, full verified upstream action SHAs and checkout without
  persisted credentials. Install Terraform 1.17.0 with its wrapper disabled.
- Use the committed root lock unchanged and read-only for dev validation. Seed
  transient child locks from it to retain AWS Provider 6.72.0; never commit child
  locks or introduce caching or uploaded test/plan/state artifacts.
- Run repository formatting, backend-disabled init/validate for dev and both
  modules, all 16 VPC and 25 IAM native mock-plan tests, current official public
  EC2/SSO reference checks and all nine checker negative self-tests. Fail on any
  command error, skipped/failed test, malformed/missing reference or checker error.
- Keep IAM verbose JSONL and reference downloads under `RUNNER_TEMP`. Preserve
  Terraform failure status and report actual outcomes in logs and job summaries.
  Do not weaken existing tests or rewrite the checker to make CI pass.
- Never bind AWS credentials, credential-bearing variables, GitHub secrets or
  AWS OIDC. No AWS identities, account APIs, real plans, apply, destroy or deploy.
  Only native tests with mocked AWS providers and `command = plan` are permitted.
- Distinguish local checks from independent GitHub-hosted execution. Observe an
  actual successful GitHub run before calling this CI phase complete. Mock/static
  success does not establish effective AWS permissions or live authorization;
  Access Admin self-assignment and other documented residual risks remain.
- If CI exposes an existing implementation defect, document it and stop for
  review. If a required official source is blocked, record host/URL/status,
  preserve work, push an incomplete checkpoint when safe and stop without bypass.

Commit, push, create a PR to `main`, report local checks and the actual GitHub
Actions run URL/status, then stop for external review. Do not merge, delete the
branch, change existing infrastructure definitions, integrate modules or begin
Phase 3-3.
