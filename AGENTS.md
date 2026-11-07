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

## Current phase only: Phase 3-2 offline authorization hardening

Phases 0, 1, 2, 3-1 and the Phase 3-2 baseline are merged. This task authorizes
hardening `infra/modules/iam_access/`, its mock tests, a lightweight offline
authorization-reference checker, necessary README updates and a short operations
runbook. Preserve all permanent rules above and all 21 existing mock tests.

- Define exactly Access Admin, Developer, and Operator Permission Sets and their
  reviewed custom inline policies. No IAM users, groups, keys, passwords, identity
  store identities, account assignments, organization instances, or workload roles.
- Scope assignment administration to exact Developer/Operator ARNs, approved
  workload accounts, and the existing instance. Require an explicit management or
  registered delegated-administrator operating account; do not equate ordinary
  member-account assignment with functioning administration.
- Keep all privilege grants explicit. No administrator policies, administrative
  action wildcards, arbitrary policy inputs, speculative service writes, PassRole,
  secret plaintext or general data-plane access. Operator is metadata-only.
- Verify all action/resource/condition support using official AWS documentation
  and machine-readable authorization references. Add only researched operations
  needed by the existing VPC implementation; do not invent attribute-value,
  recipient or main-association conditions. Document self-assignment, delegation,
  attribute/routing capabilities, metadata and effective-access limitations.
- Distinguish IAM and Identity Center enforcement from procedural approval and
  detective monitoring. Explain that enforced independent assignment approval
  would require removing direct human assignment writes and a separately approved
  controlled executor; do not silently change the approved Access Admin profile.
- Keep deployment identifiers as required inputs. Documentation-only placeholder
  labels must never enter active Terraform/tfvars; mock identifiers stay synthetic.
- Keep provider/backend/state ownership in roots. Do not change the VPC module or
  dev root, integrate this module into a root, or commit a child dependency lock.
- Preserve the 21 existing mock tests and add real policy-JSON security
  regressions. Every run must explicitly use `command = plan` and a mock AWS
  provider. Never weaken assertions merely to make a failing test pass.
- Never use AWS credentials or account APIs, including Access Analyzer. No real
  AWS plan, apply, destroy, provisioning or deployment; only native mocked plans.
- Run formatting, backend-disabled initialization, validation, tests, independent
  generated-policy/reference inspection, and scope/secret/whitespace checks.
  Separate Offline Design Readiness from incomplete Live Authorization Readiness;
  mocks/static checks do not establish live AWS authorization.
- Read public documentation only. If a required source domain is blocked, record
  the exact host/URL/status, preserve valid work, push an explicitly incomplete
  checkpoint if possible, and stop without a completion PR or allowlist bypass.

Use `fix/iam-vpc-authorization` from latest `main`, not a merged working branch.
Commit, push, and create a PR to `main` for external review, then stop. Do not
merge, delete the working branch, integrate a module, or begin Phase 3-3.
