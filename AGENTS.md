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

## Current phase only: Phase 3-8 API Gateway HTTP API

Use `feat/api-gateway-http` from verified healthy latest `main`. Implement only
`infra/modules/api_gateway_http/`, native mocks, focused actual-plan verification,
module/repository documentation and one offline CI validation step. Preserve all
permanent rules above.

- Own exactly one HTTP API v2, Lambda AWS_PROXY integration, route, stage and
  Lambda invoke permission. No data sources or additional managed resources.
- Expose only api_name, actual unqualified lambda_function_arn, actual matching
  lambda_invoke_arn, existing bare access_log_group_arn and optional non-secret
  tags. Validate reviewed commercial/GovCloud syntax and scope consistency;
  provider account restrictions and Region selection remain root-owned.
- Fix POST integration and payload 2.0, $default route with AWS_IAM, $default
  auto-deploy stage, mandatory metadata-only JSON access logs, and default
  throttling of 10 requests/second with burst 20. No anonymous authorization.
- Scope lambda:InvokeFunction for apigateway.amazonaws.com to the exact function
  and actual API execution ARN followed by /$default/$default. Use a deterministic
  API-derived statement ID; no wildcard function or broad stage/route SourceArn.
- Order the stage after route and invoke permission. Return only actual api_id,
  stage invoke_url and execution_arn with stage/permission dependencies; outputs
  do not prove propagation, application compatibility, authorization or logging.
- Keep client execute-api:Invoke/SigV4 authorization, API Gateway's Lambda
  resource-policy permission and workload execution-role authorization separate.
  AWS_IAM does not make the internet-reachable endpoint private.
- Test actual plans, fixed values, permission fields and access-log JSON, with
  focused unsafe mutations and malformed capture faults. Planned permission
  fields are not a deployed Lambda policy JSON. Reject incomplete/skipped/error
  evidence and distinguish rejected-input partial plans from valid configurations.
- Preserve all eight existing modules, service roots, 332 native/153 Python
  tests and existing reference/equivalence/negative/independent guardrail checks.
- Keep Terraform 1.17.0 / AWS Provider 6.72.0, root lock reuse, pinned actions,
  runner/triggers/concurrency, read-only/no-credentials/no-OIDC/no-upload CI.
  Never use/request AWS credentials, account APIs, live plans, apply or destroy.
- No Lambda, execution/deployment role, log group, API deployment, authorizer,
  API key, CORS, custom domain, WAF, networking or additional routes. No payload,
  authorization-header, cookie or secret logging. No service-root integration,
  Phase 3-9 or Phase 4. Existing artifacts and permissions remain separately owned.

Commit, push, open a PR and confirm completed/success GitHub CI, then stop for
independent review. Do not merge or delete the feature branch.
