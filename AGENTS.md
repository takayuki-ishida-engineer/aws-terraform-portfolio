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

## Current phase only: V5 private Kubernetes ingress runtime foundation

Continue feature/kubernetes-ingress-v5-runtime from accepted post-V4 main
`a4f0a9b8b0a810976c7ab305001729463443b27b`, successful push CI42757339642.
User-supplied Master Policy v11 requirements authorize offline source implementation;
the unavailable external PDF must not be claimed read. Preserve permanent rules.

- Extend private_ingress in the existing Platform State with exact-subject IRSA,
  owned-target registration only and scoped Istio15017/15012 rules. Preserve existing
  SG/NLB/TG ownership, provider/backend/locks and every prior security contract.
- Runtime owns pinned LBC/Istio sidecar configuration, Services, guarded TGB and
  dynamic registration; no second load balancer, Terraform Pod registration,
  Kubernetes/Helm provider, new Root/State or application release.
- Require actual pinned Helm rendering, package/dependency integrity, schema and
  independent IAM/RBAC/TGB/port/MUTUAL TLS/SPKI/STRICT/default-deny checks. External
  CA/Secret references only; no real key/certificate/Secret or fake communication.
- Layer TGB-only enforcement across IAM, controller flags, namespace/class,
  Kubernetes RBAC and admission. Do not add SG/TG setting writes to cure runtime
  AccessDenied; report any conflict for independent ownership review.
- Required minimal output inputs do not prove AWS existence/publication. Preserve
  external identity/state/capacity/connectivity/PKI/admission/teardown approvals.
- Complete affected local verification before one commit/push/PR handoff. Preserve
  all CI checks and30-minute timeout; observe trigger only, no CI completion polling.
- No AWS/Kubernetes credentials/authenticated calls, State, apply/destroy/import,
  real Helm/kubectl deployment or Live. G01–G07 remain OPEN, with cumulative
  JPY10,000/72-hour complete removal and unresolved Secrets recovery blocker.
- No merge, branch deletion, self-approval or V6; stop after review handoff.
