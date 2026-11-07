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

## Current phase only: Phase 3-3 Secrets Manager metadata

Phase 3-CI is merged and its main run succeeded. Use a new
`feat/module-secrets-manager` branch from latest `main`. This task authorizes the
new `infra/modules/secrets_manager/` child module, necessary IAM policies/tests/
checker/documentation extensions, CI coverage, repository README and this section.
Preserve the permanent rules above, VPC module, dev root and existing root lock.

- Use Approach A only: exactly one secret metadata container, optional existing
  KMS key reference, and non-sensitive resource references. No secret versions,
  payload inputs/data sources, password generation, provisioners, ephemeral or
  write-only alternatives. Values are initialized/updated outside Terraform.
- Use a stable validated name and required Project tag, safe tag ownership and
  integer recovery days 7–30 (default 30). Never enable immediate force deletion.
  Omit reader/resource-policy management in this phase; prefer workload identity
  policies. Do not add KMS keys, policies, roles, roots or application integration.
- Keep provider/account/region/backend ownership in roots. External CMKs require
  independently verified existence, symmetry, account/region, key policy, cost,
  lifecycle and permissions. Do not grant KMS Decrypt to human profiles.
- Research Secrets Manager actions, ARNs and conditions against official HTML and
  its linked machine-readable reference. Preserve EC2/SSO checks and all prior
  test cases. Do not invent secret-payload, create-context or deletion conditions.
- Document CreateSecret's residual initial-value-write capability. Withhold
  UpdateSecret, policy writes, retrieval, rotation and unnecessary recovery or
  listing privileges; explain human-profile lifecycle gaps. Access Admin remains
  unchanged; Operator gains only scoped DescribeSecret metadata access.
- Preserve existing EC2 action/resource/condition semantics during any equivalent
  compaction needed by the non-adjustable inline-policy quota. Keep association
  ARNs separate and enforce the generated Developer policy size limit.
- Keep all native tests mocked with explicit `command = plan`. Use Terraform
  1.17.0 / AWS Provider 6.72.0, transient child lock seeds, current public reference
  downloads and actual test-result/inventory checks. Preserve CI trigger/token/
  action-pin/credential boundaries and fail on errors or skipped tests.
- Never request or use AWS credentials or authenticated AWS APIs, real plans,
  apply, destroy, deployment or policy simulation. Documentation examples alone
  may contain replacement labels; active inputs contain no invalid placeholders.
- Record actual local and independent GitHub results. Observe completed/success
  before claiming CI passed; live AWS authorization remains incomplete. If a
  required public source is blocked, record exact host/URL/status, preserve work,
  push an incomplete checkpoint when safe, then stop without bypassing controls.

Commit, push and open a PR to `main`; observe CI, report results and stop for
external review. Do not merge, delete the branch, integrate into a service root,
change permanent rules or start Phase 3-4.
