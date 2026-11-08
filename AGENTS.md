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

### Codex execution efficiency and verification

- Justify local verification by actual change impact. Test new or modified
  components, directly affected existing components, and relevant security,
  negative and mutation cases. Run appropriate formatting, initialization,
  validation and static checks for affected files and modules.
- Skip unrelated, previously verified local regressions when GitHub Actions runs
  the complete suite. Do not repeat successful tests without relevant changes or
  new failure evidence. Inspect detailed logs when investigating failures; avoid
  repeatedly analyzing large successful logs.
- Never reduce necessary verification for IAM permissions, policies, trust or
  authorization boundaries; resource exposure or network security; Secrets
  Manager or KMS; provider, state, backend or account restrictions; cross-module
  dependencies or resource ownership; destructive lifecycle behavior; or GitHub
  Actions security controls. Run affected tests and security checks locally before
  opening a PR. If impact is uncertain, use the broader relevant test scope.
- Preserve every existing GitHub Actions test and security check. Never remove,
  disable, skip, weaken or reduce CI coverage for efficiency. Codex Cloud owns
  implementation, affected local validation, relevant security checks and PR
  creation. GitHub Actions owns complete regression testing, including Terraform
  mocks, Python tests, IAM references, mutations and independent guardrails.
  Independent reviewers verify completed PR CI, implementation and security, and
  authorize merge. Local success does not establish complete regression success.
- After required affected local verification, commit, push and open the PR. Report
  its URL, exact HEAD SHA, changed files, actual local checks/results and relevant
  tests intentionally delegated to GitHub Actions. Confirm the expected workflow
  was triggered only if immediately observable, then end the task. Do not poll CI
  repeatedly or wait for completed/success. Never claim pending/running CI passed.
- Investigate subsequent CI failures in a separate follow-up task using the actual
  failed step and relevant logs. Continue on the existing open PR branch, make the
  smallest justified correction, rerun affected local tests and relevant security
  checks, push to the same PR and stop without waiting for CI completion. Do not
  rerun unrelated tests or introduce speculative fixes.
- Use the minimum tool calls and analysis needed for reliable work. Avoid repeated
  reads of unchanged files, unnecessary full local suites, redundant successful
  test runs, repeated CI polling, excessive diagnostic logs, repeated analysis
  already supported by reliable current evidence, and unnecessary subagents or
  parallel work for simple tasks. Never sacrifice correctness, security or
  required verification to shorten execution.

## Current phase only: Phase 3-9 development serverless API integration

Use `feat/dev-serverless-api-integration` from verified healthy latest `main`.
Integrate only the existing dev/ca-central-1/serverless-api root, focused root
mock tests and actual-plan checker, documentation and one offline CI step.
Preserve all permanent rules above.

- Compose exactly seven instances: artifact_bucket, secret_metadata, lambda_logs,
  api_access_logs, lambda_execution_role, lambda_function and http_api. Complete
  positive configurations contain exactly 17 managed resources and no data sources.
  Keep VPC, Identity Center and human/account IAM modules outside this workload.
- Preserve fixed dev/ca-central-1/serverless-api/aws-terraform-portfolio identity,
  root-owned provider default tags and allowed_account_ids guard, local backend,
  Terraform 1.17.0, AWS Provider 6.72.0 and the committed dependency lock.
- Require explicit non-secret bucket name, artifact key, immutable non-null object
  version, runtime and matching handler. Never package, upload, discover or inspect
  an artifact. An empty bucket cannot supply the required ZIP: separately approved
  artifact bootstrap/publication and state ownership remain external prerequisites.
- Use stable distinct names and actual child outputs for ARN/name/ID connections.
  Preserve S3 security/versioning ordering, log-group references, role/policy
  readiness before Lambda, and existing API route/permission/stage dependencies.
  Configuration ordering does not prove service propagation or operational readiness.
- Keep two separate 30-day, deletion-protected STANDARD Log Groups, no explicit
  CMKs and skip_destroy=false. Access-log destination references do not prove
  actual API Gateway log delivery.
- Use Secrets Manager approach A metadata only. Default enable_secret_read=false:
  null role secret reference, no secret/KMS permissions or Lambda secret variable.
  When enabled, use only the actual exact secret ARN for reviewed read actions and
  the non-secret SECRET_ARN reference; keep CMK decrypt disabled. Flag changes
  require real plan review outside Codex Cloud. Values/AWSCURRENT/runtime retrieval
  remain separately owned and unverified.
- Preserve non-VPC Lambda defaults and the AWS_IAM HTTP API, payload 2.0, exact
  Lambda invoke permission, metadata-only access logs and 10/20 throttling. Keep
  human deployment, workload execution and API invocation authorization separate.
  No human identities, PassRole grants, artifact IAM grants or extra resources.
- Test actual child implementations with offline command=plan mocked providers;
  use coherent synthetic computed attributes without whole-module replacements.
  Check exact 17-resource plans, bindings, outputs and permissions; independently
  classify input rejection, unsafe mutations and missing/malformed capture evidence.
- Preserve every child module/test, IAM policy/reference/guardrail check, provider
  and backend file, version and lock, all 379 existing native/153 Python tests,
  and the HTTP API's 17 security mutations/19 capture-failure injections.
- Preserve pinned actions, runner cleanup, shared job-local TF_PLUGIN_CACHE_DIR,
  disk/cache measurements, read-only permissions, triggers and concurrency. Reuse
  initialized locked root; add no credentials, OIDC deployment or artifact uploads.
- Never use/request AWS credentials, account APIs, authenticated plans, apply or
  destroy in Codex Cloud/CI. No live deployment, real artifact or secret values,
  Organizations Management Account testing, remote state, production or next phase.

Commit, push, and open a PR. Perform the required affected local verification,
report the PR URL and HEAD SHA, confirm CI was triggered if immediately observable,
and stop without waiting for CI completion. Independent review and completed CI
verification occur separately. Do not merge or delete the feature branch.
