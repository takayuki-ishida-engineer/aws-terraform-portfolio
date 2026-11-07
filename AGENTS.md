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

## Current phase only: Phase 3-1

Phases 0, 1, and 2 are complete and merged. This task authorizes only the reusable
VPC child module in `infra/modules/vpc/`, its real native mock tests, and necessary
repository documentation updates. Preserve all permanent rules above.

- Implement one IPv4 VPC, explicitly keyed private subnets, optional keyed public
  subnets, one shared private route table, conditional IGW/public routing, and
  their associations. Keep private-only defaults and fixed IP/DNS safeguards.
- Require caller-supplied CIDRs, stable subnet keys, and explicit AZs; do not use
  AWS data sources for discovery. Validate inputs and document unchecked behavior.
- Keep provider/backend/authentication/region/account/state ownership in roots.
  Do not add provider or backend configuration to the child module, or commit a
  separate child-module lock file. Preserve the existing root lock unchanged.
- Remove only the obsolete `infra/modules/.gitkeep`. Do not change any existing
  service root or integrate the VPC module into one.
- Do not add other modules, NAT/EIP, endpoints, flow logs, IPv6, peering/transit,
  cross-region networking, private hosted zones, VPN/Direct Connect, firewalls,
  security groups, custom ACLs, remote backends, or workflows.
- Use `mock_provider "aws"` and explicit `command = plan` for every test run.
  Only these mocked test plans are authorized; never run an actual AWS plan,
  apply, destroy, deployment, or AWS API operation. Never use AWS credentials.
- Run formatting, backend-disabled initialization, validation, native mock tests,
  and scope/secret/whitespace checks. Investigate failures rather than weakening
  assertions, enabling real authentication, or silently skipping required tests.
- Update the repository README and only this phase-specific section of AGENTS.
  Document module sources/defaults/fixed settings, tests, and live-AWS limitations.

Use `feat/module-vpc` from the latest `main`, not a previous phase branch. Commit,
push, and open a PR for external review, then stop. Do not merge the PR or delete
the working branch. Further module development or root integration requires a
separate request and external PR review; do not begin Phase 3-2.
