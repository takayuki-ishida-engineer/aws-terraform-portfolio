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

### Resource naming

- Name AWS resources `<project>-<env>-<service>[-<purpose>]` in lowercase with
  hyphens. Add `purpose` only when more than one resource of that service exists.
- Documented exceptions only: account-ID suffixes for globally unique names such as
  S3 buckets, abbreviations within AWS length limits, AWS-mandated prefixes and the
  CloudWatch log group path form. See
  [deployment configuration](docs/deployment-configuration.md#4-resource-naming).

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
  Obtain real AWS plans through a separately authorized workflow outside Codex
  Cloud. Emulator plans follow the isolated verification rules below and do not
  establish real infrastructure migration safety or authorize real AWS access.

### Terraform state and scope

- Separate state by environment, region, and service, matching the root module
  boundary. Do not share a state file across those boundaries.
- Use local state for `dev` by default and remote state for `stg` and `prod`.
  A DEV S3 backend is optional: it is switched on only locally through untracked
  `backend_override.tf` and `*.tfbackend` files and uses the state bucket of a
  dedicated DEV bootstrap root. Tracked backends stay `local`. STG/PROD backend
  setup requires a later phase. See
  [deployment configuration](docs/deployment-configuration.md#3-terraform-state).
- Cross-region replication and disaster recovery orchestration are out of scope.

### Secrets and Codex Cloud boundaries

- Use **Secrets Manager approach A only**: Terraform manages Secrets Manager
  metadata; actual secret values are managed outside Terraform.
- Never read, pass, create, update, or output actual secret values through
  Terraform. Do not put them in configuration, variables, outputs, plans, or state.
- Do not implement ephemeral or write-only secret-value management alternatives.
- **Real AWS is prohibited in Codex Cloud**: never request, add or use real AWS
  credentials, AWS SSO, authenticated real AWS APIs or real AWS infrastructure.
  Real AWS Terraform Plan, Apply, Destroy and Import remain prohibited here.
  Never fall back to real AWS when emulator verification fails. Optional real AWS
  verification requires a separate user decision and authorized execution outside
  Codex Cloud, with all applicable G01–G07, budget and teardown controls.
- **Official AWS Emulator is permitted under strict isolation**: Terraform Plan,
  Apply, Read/Refresh, Update and Destroy are allowed only under every mandatory
  control below. This is the standard approach for future supported resources,
  not a permission confined to the historical VPC experiment. It does not permit
  real credentials, application secret values, production data or real AWS calls.
- Never commit state, plan files, local secrets, private keys, credentials, or
  environment files. Keep `.terraform.lock.hcl` trackable.
- Track only non-secret values: `terraform.tfvars` in each root, with
  environment-specific values as documented placeholders; `features.auto.tfvars`
  for feature flags; and `*.example` templates. Keep real environment-specific
  values (AWS account ID, operator IP/CIDR, notification email, domain names,
  pre-existing IAM role ARNs) only in untracked `local.auto.tfvars`. Never put
  credentials or secret values in any tfvars file; register secret values in
  Secrets Manager before building their consumers. See
  [deployment configuration](docs/deployment-configuration.md#1-where-values-live).
- Real AWS deployment runs only from the operator's local workstation, outside
  Codex Cloud and never through CI/CD. GitHub Actions runs offline checks only.

### Mandatory official AWS Emulator safety controls

Before any emulator Terraform lifecycle operation, require all of the following:

1. Official version-pinned, signature-verified AWS Emulator; verify publisher identity.
2. Loopback-only local HTTPS endpoint.
3. Emulator-generated credentials and CA only, isolated from real profiles/credentials;
   keep emulator request authentication enabled.
4. Valid TLS certificate verification; never disable it.
5. Telemetry disabled.
6. An isolated network namespace without external routes.
7. Independent proof that real AWS endpoints cannot be contacted; endpoint variables
   alone are not an isolation boundary.
8. Verified local STS identity with synthetic account `000000000000`.
9. Explicit provider endpoint and synthetic account guard.
10. A disposable standalone Terraform Root and temporary local State, outside the
    repository and separate from every operational Root and State.
11. Plan inspection before Apply or Destroy; reject unexpected managed resources.
12. Exact resource identity verification; never delete pre-existing resources.
13. Independent API checks after creation and deletion.
14. Confirmed resource cleanup, followed by removal of temporary State, credentials,
    CA and plans. Never count emulator shutdown alone as successful Terraform Destroy.

Use a disposable verification adapter when needed. Never modify a production Root
or its State merely to configure emulator access. Never relax IAM, networking,
authentication, TLS or other production security requirements for emulator compatibility.
If any isolation control fails, stop before changing resources. A failed Apply can
leave resources/State; inspect and clean up only positively identified test-owned
resources through the verified emulator endpoint, and report any residual state.
Do not commit or upload raw State, credentials, private keys or saved plans.

### Emulator verification workflow and evidence

Preserve all Terraform Native, Mock Plan, Python, Security, Negative and Mutation
tests. Master Policy v14.2 separates mandatory Core Implementation quality from
portfolio-level representative AWS Emulator demonstration; see the
[owner-authorized alignment record](docs/policy-v14-2-alignment.md).
Every Terraform implementation requires affected offline/security verification.
Emulator lifecycle for every resource is not a blanket PR prerequisite.

For a separately approved Emulator demonstration:

1. Implement the approved change.
2. Run required affected offline and security tests.
3. Identify supported resources and API operations; distinguish fidelity reports
   from directly exercised behavior.
4. Establish and independently verify every isolation control above.
5. Exercise applicable Terraform Plan, Apply, Read, Update and Destroy operations.
6. Independently verify resource identity and cleanup.
7. Record actual evidence, unsupported operations, untested behavior and residual risk.
8. Record the tested SHA, exact operations, cleanup, limitations and residual risk.
   Only actually successful operations may be marked EMULATOR DEMONSTRATED.

Core implementation PRs require all affected offline/security checks, the existing
Full CI on every PR, independent review and explicit user approval before merge.
Report unexecuted Emulator lifecycle as NOT_TESTED and unmet isolation controls
as environment BLOCKED; neither is a resource-compatibility PASS or API skip.

A dedicated Emulator GitHub Actions workflow is optional to run only within a
separately user-approved scope. Its design/implementation requires a separate PR;
execute it only after that workflow is merged. Use workflow_dispatch and standard
GitHub-hosted ubuntu-24.04 runners under GitHub Free for the public repository.
Maintain $0 Budgets for Actions/Codespaces/Packages/Git LFS/AI Credits; verify free
eligibility, Budgets and stop settings before every run. Unknown/unverifiable cost
conditions or insufficient free capacity must fail closed, without paid fallback.
No Larger Runner, paid self-hosted/external service, Artifact upload, persistent
cache, registry push, Git LFS or Packages use in the new Emulator workflow.
Owner-reported Budget existence is not run-time verification or a Billing audit;
never claim inaccessible Billing data was verified. See the alignment record.
Do not change the existing required Full CI or Branch Protection. Docker namespace
isolation is a proposed method, not proof: all fourteen controls above still apply.
Documentation-only changes do not require lifecycle replay, but still run Full CI.

Classify results precisely:

- **PASS**: operation actually demonstrated.
- **PARTIAL**: only part of the required behavior demonstrated.
- **PARTIAL-SKIP**: a specific emulator API is unimplemented, supported by actual
  evidence such as HTTP 501; skip only that operation and record untested behavior.
- **FAIL**: Terraform code or configuration defect; correct it and retest.
- **BLOCKED**: installation, connectivity, isolation or runtime prerequisite unmet.
- **NOT_TESTED**: operation not executed.

Unsupported APIs and failed setup are never successful tests. If another external
download domain is required, stop and request user permission; no unapproved
mirrors or network-policy bypass. If compatibility prevents a significant check,
report residual risk and verification options. Real AWS testing remains optional
and requires a separate user decision; Codex must not initiate it.

### Portfolio completion and historical emulator evidence

Real AWS deployment is not mandatory for portfolio completion. Core Implementation
requires approved architecture/ownership, fmt, locked init, validate, affected
Native/Mock/Negative/Security/Mutation/Evidence checks, secret-free State, existing
Full CI on every PR, independent review and user approval. Representative Emulator
lifecycle demonstration remains mandatory at portfolio level, separately from
per-resource implementation PR acceptance. CORE PORTFOLIO COMPLETE is independently
assessed from all approved Core scope implemented, offline/security quality, Full
CI, independent review, owner approval and merge, with unverified scope explicit;
it does not require Emulator demonstration. AWS EMULATOR DEMONSTRATED requires
actual representative lifecycle and cleanup under all fourteen controls.
PORTFOLIO COMPLETE requires both statuses and separate owner/reviewer acceptance;
none is automatically declared by a single passing PR.
Emulator success is never evidence of actual AWS deployment, IAM enforcement,
networking, costs, availability or recovery.

The historical proof at main `e1cdbce78ba11959093a99ffd9300b8c0f9e52e0` used
Emulator 1.0.322, Terraform 1.17.0, AWS Provider 6.72.0, AWS CLI 2.35.0 and disposable
`aws_vpc.proof`. Create, Read/Refresh, Update, no-op Plan, Destroy, independent
absence, State/credential cleanup and external isolation were reported PASS.
It establishes only that tested VPC lifecycle, not Subnet, NAT, EKS, IAM, Cognito,
RDS, other services or the complete VPC module. See the
[verification policy](docs/portfolio-verification-policy.md#official-aws-emulator--policy-v13).

Optional real AWS verification remains separately authorized, outside Codex Cloud:
G01–G07 gates, cumulative JPY 10,000 DEV Live limit, complete verified teardown
within 72 hours and the unresolved Secrets Manager recovery-window conflict
remain unchanged. No Live gate is closed by emulator evidence.

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
  tests intentionally delegated to GitHub Actions. Confirm the expected workflow's
  Full CI completed on that exact PR HEAD before stopping for independent review
  and owner approval. This applies to every PR, including docs/policy-only PRs.
  Never claim pending/running CI passed.
- Investigate subsequent CI failures in a separate follow-up task using the actual
  failed step and relevant logs. Continue on the existing open PR branch, make the
  smallest justified correction, rerun affected local tests and relevant security
  checks, push to the same PR, verify exact-HEAD Full CI completion and stop. Do not
  rerun unrelated tests or introduce speculative fixes.
- Use the minimum tool calls and analysis needed for reliable work. Avoid repeated
  reads of unchanged files, unnecessary full local suites, redundant successful
  test runs, repeated CI polling, excessive diagnostic logs, repeated analysis
  already supported by reliable current evidence, and unnecessary subagents or
  parallel work for simple tasks. Never sacrifice correctness, security or
  required verification to shorten execution.

## Completed Phase 3 and authorization for future development

Phase 3 implementation, runtime verification, independent AI evidence review
(PASS), Owner acceptance and scoped declaration were completed on 2026-11-16
(Asia/Tokyo). See the [accepted evidence record](docs/portfolio-verification-policy.md#representative-emulator-run-43791639228)
and [PR #54](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/54).
Historical starting point: PR #42 merged as
`acdef93d07a2e8957af00199b3682d7c57066891` before Phase 3 source-only authorization.

The former Phase 3 implementation-PR restrictions on Docker/Emulator startup,
Terraform lifecycle execution, manual dispatch and subsequent feature development
are retired as current task instructions. Their expiration does not authorize a
new Emulator run, infrastructure operation or development phase.

Master Policy v14.2 and its [approved alignment](docs/policy-v14-2-alignment.md),
all permanent rules above and all fourteen Emulator safety controls remain fully
effective and unchanged. This includes strict isolation, TLS/authentication,
synthetic account guards, no real AWS credentials or authenticated real AWS access
(including real AWS Plan/Apply/Destroy/Import) in Codex Cloud, no paid fallback or
unauthorized spending, no Terraform/repository secret values, architecture and
Module/Root/State ownership, required Native/Mock/Negative/Security/Mutation/Evidence
checks, existing Full CI, Branch Protection and independent review/Owner approval.

Future work requires explicit Owner authorization of the next task or phase.
For each newly authorized task, start from latest main on a new working branch,
follow its approved scope, complete affected local validation and required CI,
open a dedicated PR, then stop for independent review and explicit Owner merge
approval. This update does not authorize V7-B, new infrastructure implementation,
Live AWS testing or another Emulator execution.

AWS EMULATOR DEMONSTRATED applies only to the tested disposable `aws_vpc.proof`
lifecycle recorded above. It does not establish the complete portfolio VPC module,
other AWS services/resources, V7 REST/Cognito runtime behavior, actual AWS deployment
or security effectiveness, or portfolio-wide completion. CORE PORTFOLIO COMPLETE
and PORTFOLIO COMPLETE remain undeclared. Version changes or materially different
representative scenarios require their own applicable verification evidence before
claiming compatibility; preserve the accepted record's limitations and residual risks.

## Current authorized task: Step 1 DEV deploy-ready brush-up

On 2026-11-16 (Asia/Tokyo) the Owner approved the Step plan in
[deployment configuration](docs/deployment-configuration.md#6-step-plan): make the
existing DEV roots and a minimal Kubernetes runtime deployable from a local
workstation without unverified errors, before any new feature work. DEV only;
STG/PROD are deferred.

Step 1 item 1 (these rules and the repository guard) is authorized. Each later
item starts on the Owner's instruction, uses its own branch from latest main and
its own pull request, and stops for independent review and Owner merge approval.
Owner-approved additions needed to deploy are the SSM developer-access EC2 for
local access to the private EKS endpoint (and later RDS) and the DEV state bucket
bootstrap with an optional S3 backend. V7-B/C/D, NP-2B/NP-3 and other new features
stay paused until Steps 1 and 2 are complete. Each Step 2 Emulator run needs its
own Owner authorization. Step 3 onward is handed to Codex with a separate
instruction. All permanent rules above remain in force.
