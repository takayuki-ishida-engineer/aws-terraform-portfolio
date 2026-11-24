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
  credentials or secret values in any tfvars file. Terraform creates secret metadata
  only, with no value or dummy; operators register values manually from a local CLI
  or the console before consumers use them. See
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
tests. Master Policy v14.4 (2026-11-20, the current master; it keeps v14.2's
separation) separates mandatory Core Implementation quality from
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
Master Policy v14.4 §13.2): the Step 2 rehearsal workflow
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

Evidence ledger (v14.4 §13.4): every formal Emulator workflow run is recorded per
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
report residual risk and verification options. Real AWS testing remains optional
and requires a separate user decision; Codex must not initiate it.

### Portfolio completion and historical emulator evidence

Real AWS deployment is not mandatory for portfolio completion. Core Implementation
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

Optional real AWS verification remains separately authorized, outside Codex Cloud:
G01–G07 gates, cumulative JPY 10,000 DEV Live limit, complete verified teardown
within 72 hours and the unresolved Secrets Manager recovery-window conflict
remain unchanged. No Live gate is closed by emulator evidence.

### Git workflow and verification

- For each new development task, create a new working branch from the latest
  `main`. Never commit directly to `main`.
- Follow branch -> commit -> push -> PR -> exact-HEAD PR Safety CI (and Full CI where
  the CI execution policy requires it) -> independent ChatGPT review -> explicit Owner
  approval -> Squash merge (v14.4 §12.2, CI per the Owner decision of 2026-11-23). Commit
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
- Only the Owner changes Branch Protection: add `PR Safety CI` as a required check
  first, then remove `Credential-free Terraform validation`. Never use an admin
  bypass, a force merge or disabled protection.
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

Master Policy v14.4 and its [approved alignment](docs/policy-v14-2-alignment.md),
all permanent rules above and all fourteen Emulator safety controls remain fully
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
[deployment configuration](docs/deployment-configuration.md#8-step-plan): make the
existing DEV roots and a minimal Kubernetes runtime deployable from a local
workstation without unverified errors, before any new feature work. DEV only;
STG/PROD are deferred.

Step 1 items 1 and 2 are authorized. Item 2 is delivered as several pull requests
(2a rules, 2b network, 2c platform, 2d api and serverless-api, 2e the audit report;
2d starts with the IAM tag keys, pulled forward from 2e because the secret's project
tag is their ABAC key); roots may be split where real-project practice favors it. Each
later item starts on the Owner's instruction, uses its own branch from latest main
and its own pull request, and stops for independent review and Owner merge approval.
Owner-approved additions needed to deploy are the SSM developer-access EC2 for
local access to the private EKS endpoint (and later RDS) and the DEV state bucket
bootstrap with an optional S3 backend. V7-B/C/D, NP-2B/NP-3 and other new features
stay paused until Steps 1 and 2 are complete. Step 2 rehearsals run automatically
on merged `main` only within the limited standing authorization above; adding a
root or scenario still needs a reviewed pull request and Owner merge approval.
The v14.4 order (§19.2) is:
1. this policy alignment;
2. the evidence ledger pull request (`harvest.py`, reconciliation, tests and the
   backfill);
3. bringing PR #75 up to latest main, with `all` limited to `network` and `api`.
   PR #75 itself adds `harvest.py` support for its multi-root `summary-record`
   and pins its harness version, so the automatic run its merge starts can be
   registered in its own pull request within the §13.4 deadline. See the
   [Step 2 record](docs/step2-emulator-rehearsals.md#how-to-read-the-evidence).

Each is its own pull request that stops for Owner approval. Merging PR #75, new
Emulator runs and Step 1 Item 6b are not authorized yet. Step 3
onward is handed to Codex with a separate instruction. All permanent rules above
remain in force.
