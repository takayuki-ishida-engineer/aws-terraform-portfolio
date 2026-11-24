# CI policy tooling — PR Safety CI and Full CI (Owner decision 2026-11-23)

Every pull request to `main` runs **PR Safety CI**: always-on safety checks plus the
Full CI steps that its changed files select. **Full CI** runs only at Owner-designated
milestones and on high-risk changes, never on a push to `main`. The policy itself is
in [AGENTS.md](../../AGENTS.md#ci-execution-policy-owner-decision-2026-11-23) and the
[verification policy](../../docs/portfolio-verification-policy.md#ci-execution-policy--owner-decision-2026-11-23).
Everything here is offline: no AWS, Kubernetes or network access, except the public
AWS service-reference downloads that the existing Full CI steps already make.

| File | Purpose |
| --- | --- |
| `impact_map.json` | Step classes, prerequisites, configurations, explicit rules, high-risk paths and content rules |
| `expected_counts.py` | Loads and validates the reviewed expected counts (`load(suite)`); its `SCHEMA` fixes every suite and key |
| `../../tests/expected-counts.json` | The reviewed expected test, mutation and evidence counts (data, not CI logic) |
| `impact.py` | Maps changed files to Full CI steps (`select`), checks the map and that every tracked file maps (`check`), explains one path (`explain`), verifies step outcomes (`verify`) |
| `pr_safety_workflow.py` | Generates `.github/workflows/pr-safety-ci.yml` from Full CI (`--write`), and fails when the committed file is stale (`--check`) |
| `full_ci_trigger.py` | First Full CI step after checkout: refuses any trigger except a high-risk pull request or an Owner milestone dispatch for an exact HEAD |
| `merge_check.py` | Post-merge tree check: squash parent is the reviewed base and the squash tree equals the tree CI verified |
| `safety_checks.py` | `workflows`, `secrets`, `guards` (always-on) and `changed` (syntax and `git diff --check` of the changed files) |
| `test_ci.py` | 31 unit and negative tests and 73 source mutations, run in the `ci_policy` step |

## PR Safety CI

Check name: **`PR Safety CI`** (workflow and job), on every pull request to `main`, no
path filter, 60-minute timeout, `contents: read`, the same credential-free job
environment as Full CI. Steps:

1. Checkout of the pull request merge commit with full history.
2. **Impact** (`impact.py select`): verifies that the checkout is the merge commit whose
   second parent is the event's exact HEAD, diffs it against its first parent (the
   current `main`), maps every changed file and writes the mapping to the job summary.
3. **Changed files** (`safety_checks.py changed`): Python, JSON, YAML and shell files parse;
   `git diff --check` finds no whitespace error.
4. The Full CI steps, copied byte for byte. Always-on: `provider_cache`,
   `disk_cleanup` (self-conditional), `storage_after_cleanup`, `terraform`, `format`
   (`terraform fmt -check -recursive`), `hygiene`, `ci_policy`, `storage_final`.
   Selectable steps run only when selected. Full-CI-only steps are not copied:
   `checkout`, `trigger`, `storage_after_modules` (the twenty-two-configuration
   provider-sharing contract) and `summary`.
5. The four offline-contracts steps, selectable.
6. **Verify**: exactly the selected and always-on steps succeeded and every other copied
   step was skipped (`impact.py verify` over `toJSON(steps)`).

`ci_policy` runs `test_ci.py` (24 → 31 tests and 47 → 73 mutations, pinned in `tests/expected-counts.json`),
`pr_safety_workflow.py --check`, `impact.py check`, and `safety_checks.py workflows`,
`secrets` and `guards`:

- **workflows**: read-only token; no `secrets.` context, `GITHUB_TOKEN`, OIDC, cloud
  credentials, privileged triggers, caches, artifacts, registry logins or pushes;
  SHA-pinned actions; `ubuntu-24.04` only; a timeout of at most 60 minutes on every job;
  no job-level `if`; never-cancelling concurrency; checkout without persisted
  credentials; exactly the allowed triggers per workflow; the Emulator rehearsal
  trigger paths unchanged; the Full CI and PR Safety CI check names, timeouts and
  environment fixed; Full CI's high-risk paths equal to the map; the trigger step
  right after checkout.
- **secrets**: no tracked file holds an AWS access key ID, an AWS secret access key
  value, a private key, a GitHub, Slack, Anthropic or Google token, and no
  credential-like file name (`.env`, `*.pem`, `id_rsa`, `credentials`, kubeconfig and
  the like) is tracked.
- **guards**: fifteen real AWS/EKS entry points (`run.py` plan/apply/destroy,
  `handoff.py`, `eks_tunnel.py`, `empty_bucket.py`, `k8s_certs.py` register/delete,
  `k8s_runtime_input.py`, `k8s_runtime.py` status/receipt verify/apply/destroy and
  `mirror_images.py mirror`) must exit 1 with their exact refusal under CI markers.

## Expected counts (data, not workflow)

Every pinned count (native tests, plans, negative cases, mutations, evidence faults,
unittest totals) lives in [`tests/expected-counts.json`](../../tests/expected-counts.json).
Full CI steps, and therefore the PR Safety CI copies of them, read it with
`load("<suite>")`; the comparisons, statuses, evidence types and structural contracts
(the plan stages, the 22-configuration provider sharing, image lock purposes, the
runtime contract version) stay in the workflow. `safety_checks.py workflows` refuses
a hard-coded count in the Full CI workflow.

- **Same values in both CIs**: PR Safety CI copies the Full CI steps byte for byte.
- **A changed value runs its tests**: the impact step diffs the file against the base
  branch and selects exactly the steps that `load()` each changed suite (for example
  `k8s_runtime_apply_tests` selects the Kubernetes runtime steps). The file is never a
  whole-file input of every step.
- **Fail closed** (`expected_counts.py`): missing or unknown suites or keys, values that
  are not positive integers (booleans, strings, floats, zero), unknown top-level fields,
  a deleted file, and malformed `approved_reductions` records. Every `SCHEMA` suite
  must be loaded by a step and every loaded suite must exist.
- **Decreases**: a value lower than on the base branch fails PR Safety CI unless
  `approved_reductions` holds `{suite, key, from, to, reason}` for it. A recorded
  decrease is high-risk (`expected-count-reduction`): the Owner dispatches Full CI and
  the reviewer confirms the reason.
- **Never generated**: values are reviewed expectations, updated by hand with the tests
  they count; they are never copied from a run's observed counts.

A normal count update (G9, D19, Fake-only Destroy tests added to the existing suites,
receipt or certificate tests) therefore changes only `tests/expected-counts.json` and
the tests: no workflow change and no automatic Full CI. Adding a suite or key, or a new
test module with its own step, is a CI change (`expected_counts.py`, the workflow): high-risk.

### Extending for new Roots and Modules (Codex)

A new configuration needs, in one pull request (a CI change, so Full CI runs on it):

1. its Full CI step, which loads its counts with `load("<suite>")` instead of literals;
2. the suite in `expected_counts.SCHEMA` and its values in `tests/expected-counts.json`;
3. the step in `steps.selectable`, its configuration in `configurations` (and
   prerequisites if it reads another step's output);
4. `python3 scripts/ci/pr_safety_workflow.py --write` and `python3 scripts/ci/impact.py check`
   (which also lists any new security-boundary Terraform file for the path filter);
5. the twenty-two-configuration provider-sharing list in the Full CI measurement step.

Later count changes in that configuration are data-only, like the Kubernetes suites.

## The impact map

A changed file selects steps through four sources, all printed per file:

1. **Configuration.** A file in one of the 22 Terraform configurations selects that
   configuration's steps (Markdown excluded). A Terraform-relevant file (not `tests/`,
   `*.tftest.hcl` or Markdown) also selects every configuration that sources it,
   transitively, through module `source` and test `module { source }` blocks.
2. **Step inputs.** Paths a step names in its commands (relative to its working
   directory or `$GITHUB_WORKSPACE`), the Python it runs or imports and, transitively,
   what that Python imports or names by literal path. Imports match every tracked
   module of that name; a literal naming one `.py` file is followed; other files and
   directories named by a literal are inputs but not followed. A directory a step
   runs in (`cd`) is an input and its Python checkers are followed.
3. **Explicit rules** (`rules`), for dependencies that are not visible in code.
4. **Changed step definitions**: a Full CI or offline-contracts step whose text differs
   from the base workflow is selected.

Prerequisites (`prerequisites`) and companions (`companions`) are added, in Full CI
order. Over-approximation is deliberate: when in doubt a step runs.

| Configuration | Steps | Sourced by (adds those steps) |
| --- | --- | --- |
| `infra/services/dev/ca-central-1/serverless-api` | dev, root_integration, committed_values | - |
| `infra/services/dev/ca-central-1/network` | network, committed_values | - |
| `infra/services/dev/ca-central-1/platform` | platform, committed_values | - |
| `infra/services/dev/ca-central-1/api` | api, rest_core, committed_values | - |
| `infra/services/dev/ca-central-1/tfstate` | tfstate, committed_values | - |
| `infra/services/dev/ca-central-1/registry` | registry, committed_values | - |
| `infra/services/dev/ca-central-1/developer-access` | developer_access, committed_values | - |
| `infra/modules/eks_platform` | eks_platform | `platform` |
| `infra/modules/private_ingress` | private_ingress | `platform` |
| `infra/modules/vpc` | vpc | `network` |
| `infra/modules/secrets_manager` | secrets | `serverless-api` |
| `infra/modules/iam_account_policies` | account_policies, reference, toolkit | `iam_access` (test source) |
| `infra/modules/iam_access` | iam, reference, self_tests, toolkit | - |
| `infra/modules/cloudwatch_logs` | cloudwatch_logs | - |
| `infra/modules/lambda_workload` | lambda_workload | `serverless-api` |
| `infra/modules/s3_artifact_bucket` | artifact_bucket | `serverless-api` |
| `infra/modules/api_gateway_http` | http_api, r1_r2_guards | `serverless-api` |
| `infra/modules/cognito_auth` | cognito | `api` |
| `infra/modules/api_gateway_rest` | rest_core | `api` |
| `infra/modules/tfstate_bucket` | tfstate | `tfstate` |
| `infra/modules/ecr_repository` | registry | `registry` |
| `infra/modules/developer_access` | developer_access | `developer-access` |

| Rule | Paths | Steps |
| --- | --- | --- |
| kubernetes-runtime | `kubernetes/**` except Markdown | kubernetes_runtime, kubernetes_runtime_plan |
| ci-tooling | `scripts/ci/**`, Full CI and PR Safety workflows | always-on `ci_policy` (plus changed step definitions) |
| emulator-workflows | `.github/workflows/aws-emulator-*.yml` | emulator contracts (unit, rehearsal gate) |
| emulator-tooling | `scripts/emulator-{verification,rehearsal,evidence}/**`, `docs/evidence/**` | all four emulator contracts steps |
| repository-hygiene | `scripts/repository-hygiene/**` | always-on `hygiene` |
| gitignore | `.gitignore` | committed_values |
| terraform-testing | `scripts/terraform-testing/**` | root_integration, network, platform, tfstate, registry, developer_access |
| documentation | `**/*.md`, `.gitattributes`, `.editorconfig`, `**/.gitkeep` | always-on only, unless a test reads the file |

Prerequisites: `root_integration` and `storage_after_first_init` need `dev`;
`reference` and `toolkit` need `iam` and `account_policies`; `lambda_workload` needs
`reference`; `rest_core` needs `api`; `kubernetes_runtime_plan` needs
`kubernetes_runtime`; `committed_values` needs the seven DEV root steps.

**Fail closed.** The impact step fails when a changed file maps to nothing, when more
than 300 files changed (GitHub path filters evaluate at most 300, so Full CI's
high-risk trigger would be unreliable: split the pull request), when the checkout is
not the expected merge commit, when a workflow or Python file cannot be parsed, when a
module source is not a local configuration (registry, Git or other sources), and when
the map does not match the workflows (unclassified or unknown step, prerequisite out of
order, configuration set changed, contracts steps renamed). `impact.py check` also
requires every tracked file to map and every selectable step to be reachable.

To add a new configuration, module or script: add its Full CI step, classify the step
in `steps`, add the configuration or a rule, run `pr_safety_workflow.py --write` and
`impact.py check`. That is a CI change (high-risk), so Full CI runs on the pull request.

```bash
python3 scripts/ci/impact.py explain infra/modules/vpc/main.tf
```

```bash
python3 scripts/ci/impact.py select --base origin/main --head HEAD --report /tmp/impact.json
```

## High-risk determination and merge approval

PR Safety CI prints one verdict line, also repeated by its last step:

| Verdict | When | Before merge approval |
| --- | --- | --- |
| NOT REQUIRED | No high-risk path, content or changed line | PR Safety CI PASS (unless the Owner designates a milestone) |
| REQUIRED - STARTED AUTOMATICALLY | A changed path is in Full CI's path filter | Full CI PASS on this exact HEAD |
| REQUIRED - OWNER DISPATCH NEEDED | High-risk content the path filter cannot see | The Owner dispatches Full CI for this HEAD; Full CI PASS |

Sources of high risk:

1. **Paths** (`high_risk`, equal to Full CI's `paths`): CI and its tooling, credential
   prevention, IAM modules and `iam.tf`/`policies.tf`, the Kubernetes tree (RBAC and
   supply chain), `access.tf`, `security.tf`, `preflight.py`, provider, version, backend,
   lock and example files.
2. **Terraform content** (`terraform-security-boundary`): every Terraform file that
   declares a security-boundary resource or data source (IAM and SSO, security groups,
   VPC, subnets, routes, gateways and endpoints, load balancers, S3 bucket policy, public
   access block, encryption and versioning, KMS, Secrets Manager, EKS cluster and access,
   Lambda permissions, authorizers, Cognito, ECR, SSM) or a provider or backend block.
   `impact.py check` keeps the list equal to the files' actual content, so a new such
   resource in an unlisted file fails until the list (and the path filter) is updated.
   This covers, for example, `developer_access/main.tf` (IAM role, trust, security group),
   `tfstate_bucket/main.tf` (State bucket policy, public access block) and `vpc/routing.tf`.
3. **Changed Terraform lines** in other `infra/**` Terraform and tfvars files (tests
   excluded) that mention CIDRs, principals, policies, KMS, public access, encryption,
   ports, ingress or egress, IAM, TLS, secrets or deletion protection.
4. **Changed real-operation guard lines** in `scripts/local-workflow/*.py` (tests
   excluded): the CI and cloud-session refusals, operation gates, and any process,
   socket or HTTP call or `aws`, `kubectl`, `skopeo`, `terraform`, `helm` or `openssl`
   invocation. Fake-only engine logic and tests that touch none of these are normal
   changes and need no Full CI.
5. **Recorded expected-count decreases.**

Only sources 1 and 2 start Full CI by themselves. For 3 to 5 the verdict says OWNER
DISPATCH NEEDED: the reviewer must not approve and the Owner must not merge on PR
Safety CI PASS alone. The reviewer or the Owner may also designate any other change
for Full CI.

## Full CI

Workflow `Terraform offline CI`, check name **`Credential-free Terraform validation`**,
60-minute timeout, every check and pinned count unchanged. Triggers:

- `pull_request` to `main` changing a high-risk path (`high_risk` in the map, equal to
  the workflow's `paths`): `.github/**`, `scripts/ci/**`,
  `scripts/repository-hygiene/**`, `.gitignore`, the IAM modules, `infra/**/iam.tf`,
  `infra/**/policies.tf`, `scripts/aws-policy-validation/**`, `kubernetes/**`,
  `infra/**/access.tf`, `infra/**/security.tf`, `scripts/local-workflow/preflight.py`,
  `infra/**/providers.tf`, `infra/**/versions.tf`, `infra/**/backend.tf`,
  `infra/**/.terraform.lock.hcl`, `infra/**/*.example`, and every Terraform file listed in
  `terraform-security-boundary` (see below).
- `workflow_dispatch` by the Owner for a milestone: Actions → Terraform offline CI →
  Run workflow, **branch = the pull request branch**, `pull_request_number`,
  `expected_head_sha` = the exact 40-hex HEAD of that branch, `reason` =
  `owner-milestone`, `claude-final-task`, `codex-root-completion` or
  `high-risk-change`. The run's check attaches to that HEAD on the pull request.

The `trigger` step refuses a push or any other event; a dispatch by someone other
than the Owner (actor and triggering actor); a dispatch on `main` or a tag; an
expected SHA that is not the dispatched commit; a branch that does not contain the
current `main` (update it, then dispatch for the new HEAD); and a pull request run whose
merge commit lacks the event HEAD.

For a dispatch it also binds the pull request number through the public, read-only
GitHub REST API without a token: the pull request must exist, be open, target `main`
in this repository, and have the dispatched branch and the exact HEAD; any mismatch
refuses the run. If the API cannot answer (rate limit or network), the record says
`NOT_VERIFIED_BY_WORKFLOW` and the reviewer and the Owner must match the pull request,
branch, HEAD and base on GitHub themselves; the workflow never claims it checked.
The record (event, pull request, HEAD, base `main`, `tested_tree`, `evidence`,
`pull_request_binding`) is in the job summary and is printed again as "Full CI
evidence" by the Summarize step.

Migration note: GitHub offers `workflow_dispatch` only once the workflow file on the
default branch declares it. Until this change is merged, Full CI runs through the
path filter (this change touches `.github/**`). A label trigger was not used: labels
persist across pushes, `labeled` runs test the merge ref, and anyone with triage
rights can add one.

### Time optimization

Measured on main run 45271363139 (26 min 08 s): the allowlisted disk cleanup took
2 min 53 s, while the job used under 2 GB (one shared 0.8 GB provider binary; 114 GB
available at completion). The cleanup now runs only below 20 GiB available, and every
checkpoint still measures the disk. All 22 configurations are initialized exactly once
in their own steps, each reusing the job-local provider cache (about 0.6 s per init
with the cache). The remaining extra initializations are separate temporary working
directories, not the same configuration: the seven committed-values copies, which
initialize the local backend that the preflight and backend examples need, and the
Cognito root-rejection copy. They stay. The Kubernetes runtime step (5 min 25 s) is
dominated by its pinned mutation suites (apply 163, status 32, receipt 58, plan 39),
which stay unchanged. No matrix, parallel jobs, persistent cache or paid runner.

## Merge procedure

Before an Owner-approved squash merge: the pull request HEAD equals the reviewed SHA,
base `main` is unchanged since review, PR Safety CI succeeded on that HEAD, the
verdict line is honored (Full CI PASS on that exact HEAD where required), and the
verified tree is taken from the run record: Full CI's `tested_tree` and `evidence`, or
PR Safety CI's `tested_tree` (verify step log and job summary; evidence
`pull_request`). After the merge:

```bash
git fetch origin main
```

```bash
python3 scripts/ci/merge_check.py --squash <new main SHA> --reviewed-head <reviewed PR HEAD> --base <reviewed base main SHA> --verified-tree <tested_tree> --evidence pull_request
```

It passes only if the squash commit's single parent is the reviewed base, its tree
equals the tree CI verified, and that tree belongs to the reviewed HEAD: the merge of
that HEAD into that base for `pull_request` evidence, or the HEAD's own tree (with
the base as its ancestor) for `dispatch` evidence. A recomputed merge tree alone is
never accepted. On a mismatch, stop and investigate; no further merge until resolved.
Full CI is not re-run on main. If `main` moved after the run, the verified tree no
longer matches: update the branch and run CI again.

## Branch protection migration

Only the Owner changes Branch Protection, after independent review of this change, and
never through an admin bypass, a force merge or disabling protection.

1. Wait until PR Safety CI has completed on this pull request (GitHub lists only check
   names seen recently).
2. Settings → Branches (or Rules → Rulesets) → the `main` rule → Require status checks:
   **add `PR Safety CI`** (source GitHub Actions). Save.
3. Confirm `PR Safety CI` appears as Required on the next pull request.
4. Then **remove `Credential-free Terraform validation`** from the required checks. Save.
   Keep "Require a pull request before merging" and every other setting.

Until step 4, a pull request that changes no high-risk path never gets the old required
check, so it stays blocked (fail closed); the Owner can dispatch Full CI for it instead.

Rollback: re-add `Credential-free Terraform validation` as required (and remove `PR
Safety CI` if wanted), then revert this change in a new pull request, which restores
Full CI on every pull request and push. Reverting touches `.github/**`, so Full CI runs
on it.

## Residual risks

- Dependencies that code builds without any literal path fragment are not detected;
  configuration directories, explicit rules, over-approximation and Full CI at
  milestones mitigate this.
- A pull request may change its own PR Safety workflow; independent review and the
  automatic Full CI run on `.github/**` changes are the controls, as before.
- Whether a high-risk pull request got Full CI PASS is checked by the reviewer and the
  Owner; PR Safety CI cannot see another workflow's result. Its verdict line names the
  requirement and whether an Owner dispatch is needed.
- Keyword-based detection of changed lines over-approximates (some harmless edits need a
  dispatch) and cannot see a security effect expressed without any listed keyword.
- The pull request binding uses the unauthenticated public API; when it is rate-limited
  the binding is NOT_VERIFIED_BY_WORKFLOW and depends on the manual GitHub check.
- `infra/README.md` still describes the old Full CI triggers. It was not edited here,
  because any `infra/**` change starts the Emulator rehearsal on merge.
