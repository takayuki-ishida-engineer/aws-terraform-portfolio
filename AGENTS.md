# Repository guidance

**Controlling policy.** AWS Terraform Portfolio Master Policy **v14.5** (2026-11-23,
America/Toronto, 21 pages, Owner-adopted) is the only current controlling policy. It is
self-contained: earlier Master Policy PDFs (v14.4 and before), the alignment records
written for them and earlier operating instructions are historical records, not
current rules, and never fill a gap in v14.5. Where this file or another repository
document still describes an older rule, v14.5 applies and the difference goes to the
Owner. Historical approvals, implementations and verification results stay as records.

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

### Resource naming and tags

- Name AWS resources `<project>-<env>-<type>[-<purpose>]`, or
  `<project>-<env>-<az>-<type>[-<purpose>]` for per-AZ resources, in lowercase with
  hyphens. `type` is the documented resource-type token. When more than one resource
  of a type exists, every one gets an abbreviated `purpose`.
- Exceptions only as documented: AWS-mandated prefixes, the path form for log groups
  and secrets, underscores where hyphens are invalid, and generated `name_prefix`
  suffixes only where low-risk create-before-destroy replacement needs them. Globally
  unique names get no uniqueness suffix. See
  [deployment configuration](docs/deployment-configuration.md#4-resource-naming).
- Name objects outside AWS (Kubernetes, Helm and other tools) `<project>-<purpose>`,
  keeping names that upstream tools mandate.
- Tag every taggable resource with `project`, `env`, `service` (the resource-type
  token) and `managed` (`terraform` here), plus `Name`. Roots set `project`, `env` and
  `managed` through provider `default_tags`; modules set `service` and `Name`. See
  [tags](docs/deployment-configuration.md#5-tags).

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
- Review the Offline (mock) plan for every change that affects existing
  infrastructure, including address changes, `moved` blocks and replace/destroy
  risk. A real AWS plan is not a current acceptance condition and is not obtained
  (v14.5 §1.3, §15). Emulator plans follow the isolated verification rules below and
  do not establish real infrastructure migration safety or authorize real AWS access.

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
  Never fall back to real AWS when emulator verification fails.
- **Real AWS/EKS Live verification is outside the current scope (v14.5 §15)**: no
  operator or agent runs real AWS/EKS verification, and enabling real Apply/Destroy is
  not part of the remaining work. A future Live scope would need a new Owner cost and
  execution decision and independent review; it is not a current permission. The
  earlier G01–G07 gates and the JPY 10,000 DEV Live limit are historical records and
  give no current authorization.
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
  credentials or secret values in any tfvars file. Terraform creates secret metadata
  only, with no value or dummy; operators register values manually from a local CLI
  or the console before consumers use them. See
  [deployment configuration](docs/deployment-configuration.md#1-where-values-live).
- The local workflow and runbook keep the technical design for a future real
  deployment (operator workstation only, never Codex Cloud or CI/CD), but they are
  Source/Offline designs, not a current execution approval: no one, the Owner and
  operators included, plans or runs real AWS/EKS operations in the current portfolio
  (v14.5 §15). GitHub Actions runs offline checks only.

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
tests. Master Policy v14.5 (§01, §13, §20) separates mandatory Core Implementation
quality from portfolio-level representative AWS Emulator demonstration. The earlier
[alignment record](docs/policy-v14-2-alignment.md) for v14.2 and v14.4 is historical.
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

Core implementation PRs require all affected offline/security checks, PR Safety CI on
every PR and Full CI where the [CI execution policy](#ci-execution-policy-owner-decision-2026-11-23)
requires it, independent ChatGPT review and explicit user approval before merge.
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
An Emulator workflow never changes the required checks or Branch Protection. Docker namespace
isolation is a proposed method, not proof: all fourteen controls above still apply.
Documentation-only changes do not require lifecycle replay, but still run PR Safety CI.

Limited standing authorization (Owner decision 2026-11-20, PR #74, adopted by
Master Policy v14.4 §13.2, carried into v14.5 §13.2): the Step 2 rehearsal workflow
`.github/workflows/aws-emulator-rehearsal.yml` may run automatically, with no
further per-run approval, on a push to `main` that changes its exact trigger paths:
`infra/**`, `scripts/emulator-rehearsal/**`, the named shared
`scripts/emulator-verification` inputs and the workflow itself. It covers only the
independently reviewed scenarios listed in `all`, in a pull request whose exact HEAD
the Owner reviewed and explicitly approved for Squash Merge.
- `all` is the complete set of selected targets. It does not mean every DEV root
  or every AWS resource. A merge approval never waives the fourteen controls or
  any other safety gate.
- Adding a path, trigger, root or scenario needs its own pull request with
  workflow contract and offline tests, independent review and Owner merge
  approval. Docs-only merges are outside the trigger paths.
- Outside the standing authorization, each run needs a separate Owner approval:
  a manual `workflow_dispatch`, any local or cloud run, the representative
  `aws-emulator-verification.yml` (which keeps per-run attestation), an unapproved
  scenario and any additional API trial. Real AWS is never covered.

The billing basis is the Owner's standing configuration: a public repository on
GitHub Free, standard GitHub-hosted runners and $0 Budgets with usage blocking for
Actions, Codespaces, Packages, Git LFS and AI Credits. It is Owner-reported, not a
run-time Billing API audit. If a premise fails, is withdrawn or becomes uncertain,
the Owner stops automatic runs and reconfirms the settings or revises the policy.

At run time the workflow still requires all of the following, and otherwise fails
closed before any resource operation:
- `main` at the exact SHA, with the Owner as actor and triggering actor;
- a public repository and the first attempt;
- a standard `ubuntu-24.04` runner with enough capacity and a local Docker daemon;
- verified packages and CA, an isolated namespace and proven real-AWS
  unreachability.

A run is PASS only when resource IDs, independent API checks and cleanup are
measured. No code or workflow change widens the boundary. The workflow stays
non-required and read-only (`contents: read`), with no secrets, artifacts,
persistent caches, registry pushes, or larger or self-hosted runners. Full CI and
the required checks never gain an Emulator lifecycle.

Evidence ledger (v14.5 §13.4): every formal Emulator workflow run is recorded per
Run ID and Attempt in `docs/evidence/emulator-runs/` as
`<run_id>-attempt-<n>.json`, listed in `index.md`. This covers Step 2 automatic and
manual runs and the representative workflow, whether the run passes, fails or
stops early.
- **Content.** Each entry holds:
  - the workflow, run, attempt, head SHA, event and timestamps;
  - script and input hashes and tool versions;
  - the rehearsed roots and their Terraform resource addresses, and the
    out-of-scope roots;
  - each of the 14 controls and every per-operation lifecycle result;
  - the independent API IDs and deletion checks, and every cleanup receipt;
  - the failing step and its cause, and the residual risk;
  - the source log and job summary URL, and any evidence gap with its provenance.
- **Honesty.** A value that was not actually observed is never recorded. A run
  with no `summary-record` is recorded as BLOCKED, FAIL or INSUFFICIENT_EVIDENCE
  from its GitHub metadata, job steps and logs, and never as a 14-control PASS.
- **Data safety.** `harvest.py` accepts only trusted run metadata and allowlisted
  structured records. It rejects:
  - unknown fields and oversized data;
  - newline or control characters;
  - values that look like secrets or personal data;
  - State, plan, token or private-key forms;
  - root or account mismatches.

  The allowlist, size limits and anomaly rejection get negative, mutation and
  tamper tests in the offline contracts. The ledger is a sanitized,
  third-party-traceable audit record. It is never a permanent copy of the full
  logs.
- **Reconciliation.** The Actions run list is reconciled against the ledger to
  catch unregistered runs, duplicates, missing attempts and log fetch failures.
  Here the comparison uses `actions-runs.json`, a static snapshot committed with
  the entries. It is only as current as that snapshot, and never claims to match
  the live GitHub API.
  Each entry is submitted in its own pull request before the next `main` change
  or within 7 days of the run, whichever comes first. Anything late or
  unrecoverable is recorded EVIDENCE_GAP and never inferred as success. Entries
  are append-only; a correction keeps its reason, review and history.
- **Authority.** The workflow never pushes or opens pull requests. Ledger entries
  go through the normal pull request, its required CI, independent review and Owner
  merge approval.
- **Retention.** Logs, job summaries and run records expire under GitHub
  retention: at most 90 days on a public repository, with the actual setting
  confirmed by the Owner. A README badge, a run URL or a job summary is never
  permanent evidence.
- **Local runs.** Container diagnostics are recorded separately as LOCAL
  PRELIMINARY and never treated as formal runs.

The ledger is [`docs/evidence/emulator-runs/`](docs/evidence/emulator-runs/index.md),
maintained with [`scripts/emulator-evidence/harvest.py`](scripts/emulator-evidence/README.md).
Its tests and `harvest.py check` run in the `AWS Emulator offline contracts`
workflow. Neither path triggers the rehearsal workflow.

Classify results precisely:

- **PASS**: operation actually demonstrated.
- **PARTIAL**: only part of the required behavior demonstrated.
- **PARTIAL-SKIP**: a specific emulator API is unimplemented, supported by actual
  evidence such as HTTP 501; skip only that operation and record untested behavior.
- **FAIL**: Terraform code or configuration defect; correct it and retest.
- **BLOCKED**: installation, connectivity, isolation or runtime prerequisite unmet.
- **EMULATOR_COMPATIBILITY_BLOCKED**: a known emulator fidelity gap (API,
  provider, host or TLS mismatch), recorded with its reason. It is not a
  Terraform defect and never justifies weakening Terraform security.
- **NOT_TESTED**: operation not executed.
- **EVIDENCE_GAP** / **INSUFFICIENT_EVIDENCE**: a formal run whose ledger entry
  is late or unrecoverable, or whose evidence cannot support a result. Neither is
  ever success.
- **LOCAL PRELIMINARY**: a local or container diagnostic run, recorded separately
  from formal GitHub Actions runs.

Unsupported APIs and failed setup are never successful tests. If another external
download domain is required, stop and request user permission; no unapproved
mirrors or network-policy bypass. If compatibility prevents a significant check,
report residual risk and verification options. Real AWS testing is outside the
current scope (v14.5 §15) and is never proposed as a fix or fallback; no agent or
operator initiates it.

### Portfolio completion and historical emulator evidence

Real AWS deployment is not a completion condition and is outside the current scope
(v14.5 §15). Core Implementation
requires approved architecture/ownership, fmt, locked init, validate, affected
Native/Mock/Negative/Security/Mutation/Evidence checks, secret-free State, PR Safety
CI on every PR and Full CI under the CI execution policy, independent review and user
approval. Representative Emulator
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

Real AWS/EKS Live verification is outside the current scope (v14.5 §15) and is not a
completion condition. Emulator evidence is never Live evidence. The earlier optional
Live conditions (G01–G07, the cumulative JPY 10,000 DEV Live limit, teardown within 72
hours) are historical records, not a current permission.

### Git workflow and verification

- For each new development task, create a new working branch from the latest
  `main`. Never commit directly to `main`.
- Follow branch -> commit -> push -> PR -> exact-HEAD PR Safety CI (and Full CI where
  the CI execution policy requires it) -> independent ChatGPT review -> explicit Owner
  approval -> Squash merge (v14.5 §12.6). Commit
  and push changes before creating a PR. Continue review corrections on the
  existing open PR branch.
- Require PR review and approval before merge. Do not merge automatically; merge
  only when explicitly authorized, using **Squash and merge** by default.
- Preserve working branches after merge; do not delete them. Do not reuse a merged
  branch for new development; start a new branch from updated `main`.
- Follow `.editorconfig`, inspect the diff and changed file scope, check for
  secrets, and run `git diff --check` before finishing.
- Never start a CI run while another run of the same workflow is queued or in
  progress, and never accept a cancelled run as a result. Full CI no longer runs on
  a push to `main`; after a merge, run the post-merge tree check and wait for the
  push runs that remain (Offline Contracts and, on its trigger paths, the Emulator
  rehearsal) to finish before pushing or merging the next change. Do not push to a
  pull request while its CI is running. The workflows do not cancel in-progress
  runs (Owner, 2026-11-18).

### CI execution policy (Owner decision 2026-11-23)

Every pull request to `main` runs **PR Safety CI** (check name `PR Safety CI`,
`.github/workflows/pr-safety-ci.yml`, generated from Full CI by
`scripts/ci/pr_safety_workflow.py`). Its always-on steps check repository hygiene,
credential and secret prevention, `terraform fmt`, workflow and CI execution
safety, the CI tooling tests and the existing real AWS/EKS operation guards; it also
parses every changed file. Its impact step maps each changed file to the Full CI
steps that verify it through Terraform configurations, module sources (cross-module
dependents), step inputs and the explicit rules in `scripts/ci/impact_map.json`, and
prints that mapping. Selected steps run exactly as in Full CI, with their
prerequisites; the last step checks that exactly those steps ran. An unmapped path,
an undeterminable dependency or more than 300 changed files fails closed. See
[scripts/ci/README.md](scripts/ci/README.md).

**Full CI** (`Terraform offline CI`, check name `Credential-free Terraform validation`)
keeps every check, count, mutation, security check and evidence contract and its
60-minute timeout. Expected counts live in `tests/expected-counts.json`, read by both
CIs through `scripts/ci/expected_counts.py`; a count change is data only, selects the
steps of the changed suites, never comes from observed run counts, and a decrease
needs an `approved_reductions` record and is high-risk. It runs only:
- automatically on a pull request that changes a high-risk path: CI, credential
  prevention, IAM, RBAC and the Kubernetes supply chain, security boundaries,
  provider, State, backend or account settings, and every Terraform file that declares
  a security-boundary resource (`high_risk` in the map);
- by an Owner `workflow_dispatch` on the pull request branch, naming the pull request,
  its exact 40-hex HEAD SHA and the reason: Claude's Owner-designated final task, Codex
  Root completion, an Owner-designated milestone, or a high-risk change the Owner
  designates. The branch must contain the current `main`.

It never runs on a push to `main`, and a squash-merged HEAD is not re-run. Statuses
are never interchangeable:
- **PR Safety CI PASS**: PR Safety CI completed successfully on the exact pull request
  HEAD. It is never reported as Full CI PASS.
- **Full CI PASS**: Full CI completed successfully on the exact pull request HEAD. A
  result for an earlier HEAD is never reused; cancelled, skipped, pending or running
  is never success.
- **FULL CI NOT RUN**: Full CI did not run on the exact HEAD; report it in these words.

Rules:
- PR Safety CI prints a Full CI verdict: NOT REQUIRED, REQUIRED - STARTED
  AUTOMATICALLY, or REQUIRED - OWNER DISPATCH NEEDED (security-sensitive Terraform
  lines, real-operation guard lines or a recorded count decrease, which the path filter
  cannot see). Fake-only implementation and count increases are NOT REQUIRED.
- A normal pull request needs PR Safety CI PASS. A pull request whose verdict is
  REQUIRED also needs Full CI PASS on its exact HEAD; the reviewer does not approve and
  the Owner does not merge on PR Safety CI PASS alone. A milestone (Owner-designated, Claude's designated final task, Codex
  Root completion) is complete only with Full CI PASS and PR Safety CI PASS on its
  exact HEAD, Offline Contracts success, independent review and Owner approval.
- Reports name the pull request URL, exact HEAD SHA, the PR Safety CI result, the Full
  CI result or FULL CI NOT RUN, and the Offline Contracts result.
- On a CI failure: stop, read the failed step and its logs, make the smallest
  correction on the same branch, re-run the affected local checks, push only when no
  run of that workflow is queued or in progress, and verify the required CI again on
  the new exact HEAD. A Full CI failure stops milestone completion and merge approval.
- Before merge: the pull request HEAD equals the reviewed SHA, base `main` is
  unchanged since review, the required CI succeeded on that HEAD, and Full CI
  succeeded on that exact HEAD where required.
- A Full CI dispatch binds the pull request number to the branch, exact HEAD and base
  `main` through the read-only public API; when the API cannot answer, the record says
  NOT_VERIFIED_BY_WORKFLOW and the reviewer and the Owner match them on GitHub.
- After an Owner-approved squash merge, run `scripts/ci/merge_check.py` with the squash
  commit, the reviewed HEAD, the reviewed base `main` and the `tested_tree` that CI
  recorded: the only parent must be that base, the squash tree must equal the verified
  tree, and that tree must belong to the reviewed HEAD. On a mismatch, stop and
  investigate.
- Branch Protection (v14.5 §03, §12.1, §12.7): `main` is protected and its only required
  check is `PR Safety CI` (GitHub Actions, enforcement everyone), as independently
  confirmed for the Owner by ChatGPT. The migration from `Credential-free Terraform
  validation` is complete; the add-then-remove procedure in `scripts/ci/README.md` is
  a historical record. Full CI is not a required check, but it stays mandatory by rule
  where this policy requires it. Only the Owner changes Branch Protection; never use an
  admin bypass, a force merge or disabled protection.
- Changing the map, the generator or a workflow is a CI change: high-risk, Full CI
  required. The Emulator rehearsal trigger paths, the fourteen controls, the evidence
  ledger, Offline Contracts, credential-free CI, SHA-pinned least-privilege Actions,
  non-cancelling runs and $0 cost are unchanged.

### Codex execution efficiency and verification

- Justify local verification by actual change impact. Test new or modified
  components, directly affected existing components, and relevant security,
  negative and mutation cases. Run appropriate formatting, initialization,
  validation and static checks for affected files and modules.
- Skip unrelated, previously verified local regressions when CI runs them. Do not repeat successful tests without relevant changes or
  new failure evidence. Inspect detailed logs when investigating failures; avoid
  repeatedly analyzing large successful logs.
- Never reduce necessary verification for IAM permissions, policies, trust or
  authorization boundaries; resource exposure or network security; Secrets
  Manager or KMS; provider, state, backend or account restrictions; cross-module
  dependencies or resource ownership; destructive lifecycle behavior; or GitHub
  Actions security controls. Run affected tests and security checks locally before
  opening a PR. If impact is uncertain, use the broader relevant test scope.
- Preserve every existing Full CI test and security check. Never remove, disable,
  skip or weaken them, and never narrow the PR Safety CI impact map to save time.
  Codex Cloud owns implementation, affected local validation, relevant security
  checks and PR creation. PR Safety CI owns impact-scoped regression on every PR;
  Full CI owns complete regression testing (Terraform mocks, Python tests, IAM
  references, mutations and independent guardrails) at milestones and on high-risk
  changes.
  Independent reviewers verify completed PR CI, implementation and security, and
  authorize merge. Local success does not establish complete regression success.
- After required affected local verification, commit, push and open the PR. Report
  its URL, exact HEAD SHA, changed files, actual local checks/results and relevant
  tests intentionally delegated to GitHub Actions. Confirm PR Safety CI (and Full CI
  where required) completed on that exact PR HEAD before stopping for independent
  review and owner approval. This applies to every PR, including docs/policy-only PRs.
  Never claim pending/running CI passed.
- Investigate subsequent CI failures in a separate follow-up task using the actual
  failed step and relevant logs. Continue on the existing open PR branch, make the
  smallest justified correction, rerun affected local tests and relevant security
  checks, push to the same PR, verify the required CI on the exact HEAD and stop. Do not
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

Master Policy v14.5, all permanent rules above and all fourteen Emulator safety controls remain fully
effective and unchanged. This includes strict isolation, TLS/authentication,
synthetic account guards, no real AWS credentials or authenticated real AWS access
(including real AWS Plan/Apply/Destroy/Import) in Codex Cloud, no paid fallback or
unauthorized spending, no Terraform/repository secret values, architecture and
Module/Root/State ownership, required Native/Mock/Negative/Security/Mutation/Evidence
checks, the required CI under the CI execution policy, Branch Protection and independent
review/Owner approval.

Future work requires explicit Owner authorization of the next task or phase.
For each newly authorized task, start from latest main on a new working branch,
follow its approved scope, complete affected local validation and required CI,
open a dedicated PR, then stop for independent review and explicit Owner merge
approval. Nothing here authorizes V7-B, new infrastructure implementation, Live AWS
testing or another Emulator execution.

AWS EMULATOR DEMONSTRATED applies only to the tested disposable `aws_vpc.proof`
lifecycle recorded above. It does not establish the complete portfolio VPC module,
other AWS services/resources, V7 REST/Cognito runtime behavior, actual AWS deployment
or security effectiveness, or portfolio-wide completion. CORE PORTFOLIO COMPLETE
and PORTFOLIO COMPLETE remain undeclared. Version changes or materially different
representative scenarios require their own applicable verification evidence before
claiming compatibility; preserve the accepted record's limitations and residual risks.

## Current work and remaining order (Master Policy v14.5 §19)

Step 1 (DEV deploy-ready brush-up, Owner-approved 2026-11-16) and Step 2 (Emulator
rehearsals) are the current steps; DEV only, STG/PROD deferred. Their history (items
1 to 6, including the completed item 6b, item 6c-A to 6c-B3b, the evidence ledger,
PR #75 and the CI policy change of PR #97) is recorded in
[deployment configuration](docs/deployment-configuration.md#8-step-plan) and the
[audit report](docs/step1-audit-report.md). V7-B/C/D, NP-2B/NP-3, DB, Delivery,
CloudFront and other new features stay paused until Steps 1 and 2 are closed.

The v14.5 §19.3 order. Each item starts only on the Owner's explicit instruction, on
its own branch from latest `main`, and stops for independent review and Owner merge
approval. Listing an item here is not an implementation approval:
1. The D19 limited-transport Fake contract and G9 (Secret cleanup and the
   registration UID receipt), as separate pull requests or one combined pull request
   the Owner approves. The Owner approved one combined Source/Offline pull request on
   2026-11-24 (Fake metadata GET, UID-precondition DELETE and the four `k8s_certs.py`
   Secret identities only).
2. 6c-B4 Fake-only Destroy, split by the Owner (2026-11-24) into two pull requests:
   - 6c-B4a: the destroy transport, discovery, metadata LIST and the receipt/journal
     destroy-state foundation (authorized 2026-11-24);
   - 6c-B4b: the Fake-only destroy engine, inventory classification, finalizer,
     namespace, CRD and G9 integration and the runbook (authorized 2026-11-24 after
     6c-B4a merged as PR #100; implemented Source/Offline, pending review).
3. 6c-B5 Source/Offline final audit: every NOT_TESTED, BLOCKED and NOT_VERIFIED item
   listed. Full CI runs as Claude's Owner-designated final task (the first real
   Owner dispatch is planned here). The 6c audit alone never declares Portfolio
   Complete.
4. The Step 1/2 closure decision and the Codex handover: accepted Emulator evidence,
   out-of-scope roots, gaps and risks evaluated independently.
5. Step 3: the remaining Core services by approved functional unit, by Codex. Full
   CI at each Root completion; normal pull requests follow §12.
6. Step 4: final Core acceptance (Full CI required), independent confirmation of the
   representative Emulator evidence and the Owner's final approval.

Owner decisions of 2026-11-24 for 6c-B4 (design record section 13): D3 (Fake-only
discovery of every advertised group version, metadata-only LIST of the three runtime
namespaces and the 17 CRD plurals, separate scopes), D5 (17 CRDs kept, no CRD DELETE,
a specialised Fake CRD read), D6 (namespaces in a final namespace phase), D11 (the
destroy timeouts, page limits and a 3600 s deadline), D12 (the section 12 order and a
specialised Service type read) and the remaining D19 scope. 6c-B4a is merged (PR #100,
Source/Offline complete); 6c-B4b was authorized on 2026-11-24 as a Fake-only engine within
these decisions and the existing G9, D13, D18 and receipt contracts, with Full CI as an
Owner-designated safety milestone. The real CLI `destroy`, real transport and Live stay
refused; 6c-B5 and the Codex handover are not authorized.

D1 (the binding-writer method), Live probes, manager and effective-permission checks
and real transport authentication stay undecided and unverified and are not part of
the remaining work. Approved contracts (D7, D8, D10, D16, D17, the D19 limited
transport interface and fake, D3 fingerprint and apply-limited reads, D23 C1, D2, D9,
D11 default read timeouts, D13 allowlist, and of 2026-11-24 the D19 Fake GET/UID
DELETE scope for the four Secrets, D18: no namespace deletion while a Secret
remains, and the 6c-B4 decisions D3, D5, D6, D11, D12 and the remaining D19 scope)
are not widened. Step 2 rehearsals run
automatically on merged `main` only within the limited standing authorization above.
Step 3 onward is handed to Codex with a separate instruction. All permanent rules
above remain in force.
