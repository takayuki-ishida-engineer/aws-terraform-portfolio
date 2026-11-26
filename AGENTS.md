# Repository guidance

**Controlling policy.** The Owner-issued **MASTER_POLICY v15.0 (2026-11-26)**
is the sole controlling policy. Part I prevails over conflicting Part II text.
Apply MASTER_POLICY v15.0, Revision 6 Final Conditional v1.30, Final Contracts,
M1 Handoff and Codex Task Packets, then historical designs and evidence, in that
order. The v1.30 package preserves pre-issuance labels as historical records.

- Use the current policy document explicitly designated by the Owner. Do not infer
  current authority from an older version, a file name, repository history or a
  historical alignment record.
- If the controlling policy is unavailable, or repository documentation conflicts with
  it, stop the affected work and request an Owner decision.
- Historical policy version references are retained for evidence and provenance only.
  A new policy release does not automatically authorize implementation, execution,
  scope expansion or changes to safety contracts.

This file is the repository's primary reference for that rule. Other repository
documents refer to "the controlling MASTER_POLICY" (with its section numbers, such as
§15) instead of a version number, so a new policy release needs no repository-wide
edit for the version number alone. Documents are still updated when a release
changes substance: rules, implementation status, technical contracts, stop conditions
or responsibilities. A version named elsewhere (for example v10 to v14.6, the v14.2 alignment
record, `infra/**` module READMEs naming v11, `infra/README.md`'s earlier CI text) is
a dated record of that time, not current authority. Historical approvals,
implementations and verification results stay as records.

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
  (MASTER_POLICY §1.3, §15). Emulator plans follow the isolated verification rules below and
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
- **Real AWS/EKS Live verification is outside the current scope (MASTER_POLICY §15)**: no
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
  (MASTER_POLICY §15). GitHub Actions runs offline checks only.

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
tests. The controlling MASTER_POLICY (§01, §13, §20) separates mandatory Core Implementation
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
Master Policy v14.4 §13.2 and carried into later releases as MASTER_POLICY §13.2): the
Step 2 rehearsal workflow
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

Evidence ledger (MASTER_POLICY §13.4): every formal Emulator workflow run is recorded per
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
current scope (MASTER_POLICY §15) and is never proposed as a fix or fallback; no agent or
operator initiates it.

### Portfolio completion and historical emulator evidence

Real AWS deployment is not a completion condition and is outside the current scope
(MASTER_POLICY §15). Core Implementation
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

Real AWS/EKS Live verification is outside the current scope (MASTER_POLICY §15) and is not a
completion condition. Emulator evidence is never Live evidence. The earlier optional
Live conditions (G01–G07, the cumulative JPY 10,000 DEV Live limit, teardown within 72
hours) are historical records, not a current permission.

### Git workflow and verification

- For each new development task, create a new working branch from the latest
  `main`. Never commit directly to `main`.
- Follow branch -> commit -> push -> PR -> exact-HEAD PR Safety CI (and Full CI where
  the CI execution policy requires it) -> independent ChatGPT review -> explicit Owner
  approval -> Squash merge (MASTER_POLICY §12.6). Commit
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

The checked-in workflows below remain operative. Under v15.0 CF-16–22 and
PD-10/12/16, CI-INT-01 specifies trusted Catalog and independent readback,
same-Run shard aggregation, and Integration Light + independent Offline Contracts
with a trusted pre-merge check. This design is pending implementation. Keep
the checked-in queue guard until the planned per-PR/per-workflow queue takes
effect through an approved change. Bind results to exact HEAD, Base, tested
Tree, Run and Attempt. Independent review and serial Owner merges remain required.
See [Revision 6 verification](docs/portfolio-verification-policy.md#revision-6-verification-and-acceptance).

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
- Branch Protection (MASTER_POLICY §03, §12.1, §12.7): `main` is protected and its only required
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

### CI-PERF-01: Full CI performance (MASTER_POLICY §12.5.1)

**Status: COMPLETE.** PR #104 was squash merged as `bab22ef` and verified after the
merge. The Owner decisions OD-PERF-02-A to F formally adopted the parallel offline
runtime execution (MASTER_POLICY §12.5.1, Appendices A and B). Full CI is shorter and
keeps every check:
- **Targets and result:** the targets were Full CI within 40 minutes, ideally within
  35 minutes, and about 50–55 minutes at the final portfolio stage (targets, not
  guarantees). Full CI took 53m43s on PR #102 (run 45453872145), 35m24s on PR #103
  (run 45473185925) and 28m18s on PR #104 (run 45525299922); its runtime step took
  1465 s, 921 s and 461 s. Hosted runner speed varies, so the whole difference is not
  attributed to parallelization. The hard timeout stays at 60 minutes.
- **Kept:** every test, mutation ID, expected count, assertion and safety contract, and
  the isolation evidence. Nothing is skipped or weakened for speed, and no timeout is
  extended.
- **Adopted runtime contract (OD-PERF-02-A, B):** `scripts/ci/runtime_test_runner.py`
  runs the offline Receipt and Apply tests under resource-bounded Linux fork-per-task
  process isolation. Full CI uses `--workers auto`: at most four workers, bounded by the
  CPU affinity, the cgroup quota and the memory budget. The command line defaults to one
  worker, and an explicit request over the budget fails with no silent fallback. Plan
  and Status stay serial.
  - Each task gets a fresh child, its own HOME, TMPDIR, XDG and Helm directories, a
    credential-free environment with `KUBECONFIG=/dev/null`, a private process group
    under a subreaper, bounded deadlines and checked cleanup.
  - The parent must have a single thread and no unexpected descriptor or lock. The
    coordinator and the `ci_policy` tests start behind a clean `close_fds=True`
    boundary; no descriptor number is allowlisted. The child's exit code or
    terminating signal is propagated, SIGKILL and blocked signals included.
  - Missing, duplicate, unknown, crashed or timed-out work, an invalid lifecycle or
    result, and a baseline or fixture failure fail closed.
  - All 252 runtime Test IDs and 616 mutation definitions, the 276 parallelized
    mutations, the 125 normal-code witnesses plus 5 explicit inline baselines, and both
    suite counts loaded with `load()` in the workflow step are kept.
  - Production Receipt/Journal code and contracts, real operations, the timeout, the
    runner type and the cache policy are unchanged.
  - Details are in [scripts/ci/README.md](scripts/ci/README.md#adopted-runtime-test-runner-ci-perf-01b-od-perf-02).
- **Evidence identifier:** the runner's evidence header `"runtime_runner": "candidate"`
  is a stable evidence-format identifier, read by `read_evidence` and its tests. It is
  not the adoption status: the runner is adopted.
- **Accepted residual risks (OD-PERF-02-C):** no direct test of the 64 KiB diagnostic
  limit; a malformed diagnostic can be reported before the original failure (still
  fail-closed); the resource type of the inherited descriptor 142 is unknown; hosted
  runner performance varies; full Production Receipt/Journal replay optimization and
  the Status subprocess cost are out of scope. None of these permits real AWS/EKS, real
  Apply/Destroy or an OPEN decision such as D1.
- **Further changes:** any further performance work (more parallelism, persistent
  caches, paid or larger runners, Receipt/Journal changes) is a new task under
  MASTER_POLICY §12.2–12.7 and needs its own Owner approval.

**History (records only).**
- CI-PERF-01A profiling and design came before the implementation approval.
- Under OD-PERF-01 the Owner approved the implementation and evaluation of offline
  Receipt/Apply process isolation as a candidate, with adoption left to a separate
  decision (OD-PERF-02) and no automatic adoption or fallback.
- PR #104's first CI failed (runs 45516671772 and 45516671756): an inherited
  descriptor 142 that was not close-on-exec caused 9 failures and 5 errors in 65
  `ci_policy` tests. The clean descriptor boundary and the BF-02/N-5 exit status
  corrections resolved it without allowlisting a descriptor or weakening the guard.
- The Owner then approved OD-PERF-02:
  - A adopts the parallel offline runtime tests;
  - B sets `--workers auto` with a maximum of four;
  - C accepts the residual risks above;
  - D approves the PR #104 squash merge (done);
  - E completes CI-PERF-01 after the post-merge verification (done);
  - F assigns the MASTER_POLICY revision and handover preparation to ChatGPT. The
    formal Codex handover and Step 3 implementation need separate approval.

PR #104 records (all attempt 1):

| Check | Run | Result |
| --- | --- | --- |
| PR Safety CI | 45525300626 (job 138907027995) | SUCCESS, 9m51s; 45 verified steps, Full CI required and started automatically |
| AWS Emulator Offline Contracts | 45525300472 (job 138907025924) | SUCCESS, 17s |
| Full CI | 45525299922 (job 138907024109) | SUCCESS, 28m18s; runtime step 461 s |
| `main` Offline Contracts after the merge | 45529485939 (job 138920947939) | SUCCESS, 15s |

Base `9fa3abc`, reviewed HEAD `bd707b1`, squash commit `bab22ef`, tested and merged
tree `1f51da75e7446d6b381b8e0d77e2dd49bc62bd53`; `merge_check.py` PASS. Counts: CI
Policy 72 tests / 97 mutations; Runtime 252 tests / 616 mutations (Plan 29/39, Status
21/32, Receipt 144/382, Apply 58/163); 276/276 parallelized mutations detected, none
crashed or undetected; 125 witnesses plus 5 inline baselines. No duplicate Full CI or
additional Emulator rehearsal ran.

**Responsibilities (closed, not precedents).** For CI-PERF-01 only, the Owner set a
temporary split after the MASTER_POLICY v14.6 release (2026-11-24): ChatGPT for
analysis, design, implementation and corrections; Claude for profiling, independent
review, local tests and the benchmark; joint CI verification; Owner merge approval.
By the Owner decision of 2026-11-25 the remaining PR #104 corrective work went to
Claude, with ChatGPT reviewing. Both arrangements and the one-time PR #101 exception
are closed and are not precedents (MASTER_POLICY Appendix B.4). The current
responsibilities are in
[Current work and remaining order](#current-work-and-remaining-order-master_policy-19).

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

The controlling MASTER_POLICY, all permanent rules above and all fourteen Emulator safety controls remain fully
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

<a id="current-work-and-remaining-order-master-policy-v145-19"></a>

## Current work and remaining order (MASTER_POLICY §19)

**Current record (2026-11-26, America/Toronto).** Step 1 Source/Offline acceptance
and Step 2 closure with accepted limited Emulator evidence stand. CI-PERF-01A/B,
DOC-ALIGN-02 (PR #105), CODEX-HO-01 and formal Codex handover are complete.
OD-HO-05 is accepted. M0 and the document handover are complete. The Owner
approved Revision 6 v1.30 and issued MASTER_POLICY v15.0 under M0-D01–04. The
same ChatGPT authored and self-reviewed the final plan; the Owner accepted
that independent plan review had not occurred. Implementation PRs still need
independent review.

| Item | Current status |
| --- | --- |
| EXA-01 A–D | APPROVED; EXA-01-D order amended and approved |
| M1 / GOV-01 and DES-01 | IN PROGRESS; one documentation PR with separate acceptance conditions |
| M1-TOOLS | Initial execution complete; Acceptance HOLD |
| CI-INT-01 | CONDITIONALLY AUTHORIZED / HOLD |
| EXA-02 and subsequent gates, including OD-HO-06 | NOT AUTHORIZED |
| Step 3 full implementation / Step 4 | NOT STARTED |
| 120 Technical Findings / NP-2B and NP-3 | OPEN / PAUSED |
| CORE PORTFOLIO COMPLETE / PORTFOLIO COMPLETE | NOT DECLARED |

**Owner-amended EXA-01-D.** GOV-01 / DES-01 precedes resolution of M1-TOOLS.
The combined documentation PR needs IMPACT + Offline Contracts, independent
review and Owner merge approval. Resolve M1-TOOLS evidence in separate,
limited work. CI-INT-01 needs both GOV/DES and M1-TOOLS acceptance, an exact
File Manifest and specific execution authority.

1. **M1:** CI-INT-01 Full + Offline Contracts and independent review precede
   EXA-02 Owner merge. EXA-03/04 cover Owner ruleset/branch readback and
   PROOF-01 P1–P7 for G-PROOF. After CI-INT merge, GUARD-01/EXA-11 binds the
   reviewed shared catalog. SYNC-GUARD, X01–X04 and G-PROOF feed INT-00.
   EXA-05 (OD-HO-06) requires D-03, accepted INT-00, actual G-PROOF, issued
   policy and Owner approval of the eligible FU, files and gates.
2. **M2:** Four initial Integration PRs in the individually approved scope.
3. **M3:** Focused verification, authorized fixes, RT-01 and SYNC. Applicable
   EMU-PARITY and actual run/attempt ledger work precede LAND.
4. **M4–M5:** LAND exact Full, independent review, Owner squash, parent/tree
   verification and actual run/attempt ledger entries.
5. **M6–M7:** ACC Core acceptance, independent representative Emulator evidence
   and final Owner acceptance. Mandatory blockers and original witnesses apply.

**Current roles.** Owner controls policy, scope, risk, cost, acceptance and merge.
Codex implements and verifies individually authorized work. ChatGPT manages
development governance and independently reviews it. Claude Code performs
additional work only with individual Owner approval.

**Historical sequence and prerequisites.** The following v14.7 status, order and
handover checklist record the state before formal handover.

**Status (MASTER_POLICY v14.7, issued 2026-11-25; §03, §19.3, Appendix C).** On
2026-11-24 the Owner approved OD-01 to OD-13, which closes the planned Step 1 and
Step 2 implementation and audit work and accepts the residual risks. CI-PERF-01 then
completed with PR #104 and the Owner decisions OD-PERF-02-A to F:

| Item | Status |
| --- | --- |
| Step 1 | SOURCE / OFFLINE COMPLETE (OD-01) |
| Step 2 | Closed with accepted, explicitly limited Emulator evidence (OD-02 to OD-07; see the [Step 2 record](docs/step2-emulator-rehearsals.md)) |
| CI-PERF-01A/B | COMPLETE ([CI-PERF-01](#ci-perf-01-full-ci-performance-master_policy-1251)) |
| OD-PERF-02-A to F | Approved |
| PR #104 | Merged (`bab22ef`) and post-merge verified |
| Codex formal handover | PENDING — DOCUMENTATION ALIGNMENT AND OWNER APPROVAL |
| Step 3 | NOT STARTED |
| Step 4 | NOT STARTED |
| CORE PORTFOLIO COMPLETE | NOT DECLARED |
| PORTFOLIO COMPLETE | NOT DECLARED |

The closure does not mark any unverified item PASS and is not portfolio completion.
OD-08 to OD-13 keep D1, D4, D14, D15, D20, D21 and D22 OPEN, real Apply and Destroy
BLOCKED, Live AWS/EKS verification out of scope, NP-2B and NP-3 PAUSED, no further
Emulator demonstration before the Codex handover, and CI-PERF-01 before the handover
(now done). V7-B/C/D, NP-2B/NP-3, DB, Delivery, CloudFront and other new features
stay paused; the closure alone does not make any of them startable. The history of
Steps 1 and 2 is in
[deployment configuration](docs/deployment-configuration.md#8-step-plan) and the
[audit report](docs/step1-audit-report.md) (6c-B5 final audit in section 7).

Remaining order (MASTER_POLICY §19.3 numbering in brackets). Each open item starts only
on the Owner's explicit instruction, on its own branch from latest `main`, and stops
for independent review and Owner merge approval. Listing is not approval:
1. D19/G9 (PR #99), 6c-B4a (PR #100) and 6c-B4b (PR #101; FULL CI NOT RUN under the
   ended one-time exception): completed [§19.3 items 1–3].
2. 6c-B5 final audit (PR #102, Full CI 45453872145 as Claude's Owner-designated final
   task): completed [§19.3 items 1–3].
3. Step 1/2 closure and residual risk acceptance (OD-01 to OD-13): completed [§19.3
   item 4].
4. MASTER_POLICY v14.6: issued 2026-11-24 [§19.3 item 4].
5. CI-PERF-01A and CI-PERF-01B, benchmark, independent review, required CI, Full CI,
   merge and post-merge verification ([CI-PERF-01](#ci-perf-01-full-ci-performance-master_policy-1251)):
   completed with PR #104 and OD-PERF-02-A to F; MASTER_POLICY v14.7 issued
   2026-11-25 [§19.3 item 5].
6. Next: the final handover baseline (latest `main` and tree, risk, CI contracts), the
   documentation alignment (DOC-ALIGN-02) and an explicit Owner-approved Codex
   handover [§19.3 item 6].
7. Step 3: the remaining Core services by individually approved functional unit, by
   Codex; Full CI at each Root completion; normal pull requests follow §12. Findings F6
   and F10 stay assigned to Step 3 [§19.3 item 7].
8. Step 4: final Core acceptance (Full CI required), independent confirmation of the
   representative Emulator evidence and the Owner's completion decision [§19.3 item 8].

**Handover gate (MASTER_POLICY §19.3, Appendix C).** Before the formal handover:
- CI-PERF-01 is merged with its benchmark, exact-HEAD Full CI, independent review and
  post-merge verification: met (PR #104, Appendix A).
- The repository's candidate and incomplete-status text is aligned with MASTER_POLICY
  v14.7 by an Owner-approved documentation-only pull request, keeping historical
  records distinct.
- The final merged baseline is independently verified and the Owner explicitly
  approves the formal handover.
- The handover instruction fixes the latest `main` and tree, the target roots and files,
  architecture and scope, residual risk, OPEN decisions, expected counts, CI and
  Emulator evidence and the stop conditions.

**Responsibilities after the formal handover (MASTER_POLICY §00, Appendix B.4, C.4).**
- Codex is the primary implementation agent for individually approved Step 3 tasks.
- ChatGPT performs independent review and governance oversight.
- The Owner keeps scope, risk, cost and merge authority.
- Claude performs additional implementation only when the Owner separately
  authorizes it.

The CI-PERF-01 responsibilities, the PR #104 corrective exception and the PR #101
exception are closed and are not precedents.

Codex implements nothing before the formal handover and an individual Owner scope
approval. Fake-only engines are never Live procedures. D1 and the other OPEN decisions
are never implemented on Codex's own judgment. Codex stops on any real operation,
contract widening, unapproved cost or missing required CI.

**Continuing runtime decisions (MASTER_POLICY §19.2, Source/Offline only).**
- **Approved:** D2, D3, D5, D6, D7, D8, D9, D10, D11, D12, D13, D16, D17, D18, D19 and
  D23. The approved scope includes G9 registration pinning and the Fake-only atomic
  namespace gate (PR #101; Fake-only, real cascade safety NOT_VERIFIED).
- **OPEN:** D1, D4, D14, D15, D20, D21 and D22. Live probes, managers, effective
  permissions, real transport authentication and real API atomicity are undecided and
  unverified and are not part of the remaining work.

Approved contracts are not widened. Step 2 rehearsals still run automatically on merged
`main` only within the limited standing authorization above; the Step 2 closure does
not disable it. All permanent rules above remain in force.
