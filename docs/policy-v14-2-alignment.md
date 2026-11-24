# Master Policy — owner-authorized alignment record (v14.4, built on v14.2)

> **Historical record, superseded.** Master Policy **v14.5** (2026-11-23,
> America/Toronto, 21 pages) is the only current controlling policy and is
> self-contained; it is not read through this record. [AGENTS.md](../AGENTS.md) applies
> v14.5 in the repository. This page keeps the v14.2 and v14.4 alignment as history:
> its orders (for example §19.2 of v14.4), Live conditions (G01–G07, JPY 10,000) and
> authority statements are not current rules. The file name stays for existing links.

## Master Policy v14.4 alignment (2026-11-20)

On 2026-11-20 (Asia/Tokyo) the Owner adopted Master Policy v14.4, a 19-page
integrated revision of v14.3. Its evidence baseline is main `70a5868`. All 19
pages were reviewed. The PDF binary's hash was not independently verified. v14.4
keeps Architecture v2, the Terraform and security boundaries, zero additional cost
and the quality and acceptance model below. It formalizes two things:
- the limited automatic Step 2 rehearsal;
- the evidence ledger for every formal run.

The PDF's issue authorizes no PR #75 merge, no extra Emulator run, no real AWS
operation and no new AWS service. The file name of this record stays as it is
so that existing links keep working. Other documents that cite v14.2 as current
authority mean this record, as amended by v14.4.

**Owner decision 2026-11-23 (CI execution).** For §12.2 and the Full CI wording
below, every pull request now needs PR Safety CI on its exact HEAD, and Full CI runs
at Owner-designated milestones (Claude's designated final task, Codex Root
completion, Owner milestones) and on high-risk changes, never on a push to `main`.
Full CI keeps all of its checks. Review, Owner approval and Squash Merge are
unchanged. See the [CI execution policy](../AGENTS.md#ci-execution-policy-owner-decision-2026-11-23).
The Master Policy PDF itself is not changed.

| v14.4 | Aligned in |
| --- | --- |
| §12.2 PR order: latest main, new branch, approved change, affected checks, commit/push/PR, exact-HEAD Full CI, independent ChatGPT review, explicit Owner approval, Squash Merge | [AGENTS.md](../AGENTS.md#git-workflow-and-verification) |
| §13.2 limited standing authorization: automatic runs only for reviewed `all` scenarios in an Owner merge-approved PR. `all` is not every DEV root. New paths, triggers, roots or scenarios need their own PR. Manual dispatch, local or cloud runs, the representative workflow, unapproved scenarios and API trials need separate approval each time. Real AWS is never covered | [AGENTS.md](../AGENTS.md#emulator-verification-workflow-and-evidence), [amendment below](#owner-amendment-2026-11-20-automatic-step-2-rehearsals) |
| §13.2 result categories: `EMULATOR_COMPATIBILITY_BLOCKED` for a known API, provider, host or TLS mismatch; `PARTIAL-SKIP` only for an operation actually observed as unsupported, such as HTTP 501 | AGENTS.md result classification |
| §13.3 lifecycle evidence snapshot and per-root status | [Step 2 emulator rehearsals](step2-emulator-rehearsals.md) |
| §13.4 evidence ledger: every formal run per Run ID and Attempt in `docs/evidence/emulator-runs/`; allowlisted `harvest.py`; reconciliation; EVIDENCE_GAP and INSUFFICIENT_EVIDENCE; LOCAL PRELIMINARY kept separate; README badge, run URL and job summary not permanent | AGENTS.md (obligation). The implementation follows in its own PR (§19.2 item 3) |
| §14 billing basis of automatic runs: the Owner's standing configuration, not a real-time Billing API audit. The Owner stops automatic runs when a premise fails or becomes uncertain | AGENTS.md, [amendment below](#owner-amendment-2026-11-20-automatic-step-2-rehearsals) |
| §19.2 order: this docs-only PR; the evidence ledger PR; PR #75 brought up to latest main with `all` = `network` + `api`; then the Step 1 Item 6b and Step 2 completion decision; then Step 3 with Codex | AGENTS.md current authorized task |

§16 to §18 (reference material Day 01–10, the improvement register REF-A01 to
REF-A06, and rejected options) register improvement candidates only. They
authorize no new resource, CI permission, real AWS operation or pull request.

## Master Policy v14.2 alignment (2026-11-15)

The owner supplied the full 43-page Master Policy v14.2 text on 2026-11-15
(Asia/Tokyo); all pages were reviewed, including priority provisions A–T and the
34-page v14.1 archive. A–T override conflicting archived clauses. This record
aligns repository rules with that supplied text. The PDF binary was not inspected;
neither its hash nor the supplied archived-v14.1 SHA-256 was independently verified.
The previously supplied v14.1 34-page extraction remains historical provenance;
its architecture, ownership, security, Public governance and Live boundaries remain
in force except for the expressly revised quality/Emulator acceptance model below.
Earlier editions and historical evidence do not supersede these current rules.

### Quality and acceptance model

| Track | Required evidence and gate | Limitation |
| --- | --- | --- |
| Core Implementation | Approved architecture and Root/Child/State ownership; fmt, locked backend-disabled init, validate; affected Native/Mock/Negative/Security/Mutation/Evidence; secret-free State, IAM/TLS guards; unchanged Full CI on every PR; independent review and user approval | Per-resource Emulator lifecycle is not a blanket PR prerequisite. Offline evidence does not establish actual AWS behavior |
| AWS Emulator Demonstrated | Mandatory portfolio-level representative scenarios; fixed official version/publisher/signature, all fourteen AGENTS controls, actual lifecycle and independent identity/cleanup checks, tested SHA and limitations | EMULATOR DEMONSTRATED covers successful measured operations only; it does not imply all resources or real AWS are verified |
| AWS Live | Optional, separately authorized outside Codex Cloud, applicable G01–G07, cumulative JPY 10,000 and verified complete teardown within 72 hours | No real AWS credentials, authenticated APIs, STS identity checks or operational State access in Codex Cloud |

The historical single aws_vpc.proof experiment retains only its recorded scope;
it is not a new run, proof of REST/Cognito compatibility or automatic acceptance
of future representative scenarios. CORE PORTFOLIO COMPLETE independently requires
all approved Core scope implemented, offline/security checks, exact-HEAD Full CI,
independent review, owner approval and merge, with unverified scope explicit;
Emulator demonstration is not a prerequisite for that Core status.
AWS EMULATOR DEMONSTRATED requires an actual representative lifecycle and cleanup
under all fourteen controls. PORTFOLIO COMPLETE requires both statuses, independently
reviewed and accepted by the owner. This PR declares
neither V7-A nor the portfolio complete.

An unexecuted Emulator lifecycle is NOT_TESTED. An unavailable isolation prerequisite
is environment BLOCKED; it is not evidence of an unsupported API. PARTIAL-SKIP needs
observed operation-specific unsupported behavior. Neither label becomes PASS.
Offline failures must be fixed and retested, never waived by changing this model.
All fourteen [Emulator controls](../AGENTS.md#mandatory-official-aws-emulator-safety-controls)
remain mandatory whenever an Emulator operation is attempted. No namespace bypass,
TLS/authentication weakening, real AWS fallback or secret-value Terraform is allowed.

### Separate PR and approval gates

1. **Policy Alignment:** dedicated branch from latest main; governance documents
   only. Run documentation checks, commit/push/open the PR, observe exact-HEAD Full
   CI completion and report. Stop for independent review and owner Squash Merge
   approval; do not auto-merge or start Phase 2.
2. **V7-A:** only after the owner resumes work and the Phase 1 merge is observed
   on main, create a new branch from latest main. Scope is api_gateway_rest with
   Regional REST API core and Cognito User Pool Authorizer, actual existing User
   Pool ARN reference, disable_execute_api_endpoint=true and unchanged Cognito
   resources/outputs. No REST Method, Integration, Deployment/Stage, VPC Link,
   Backend or Custom Domain. Require all affected offline tests and existing
   regressions, then exact-HEAD Full CI, independent review and owner approval.
   Emulator is not required for this implementation PR: report lifecycle NOT_TESTED
   and known namespace isolation BLOCKED. Stop after reporting CI; do not merge.
3. **Representative Emulator verification:** separate authorization and separate
   workflow PR, with independent review/owner approval before merge. Execute only
   after workflow merge and within the separately approved scope. No workflow or
   Emulator execution is authorized by this alignment PR.

### Future optional Emulator workflow constraints

Use workflow_dispatch with ubuntu-24.04 on a standard GitHub-hosted runner only,
under GitHub Free in this Public Repository. No spending beyond the existing Codex
subscription is authorized. Larger runners, paid self-hosted runners and external
paid services are prohibited. Maintain $0 Budgets and usage-blocking settings for
Actions, Codespaces, Packages, Git LFS and AI Credits. Before every Emulator run,
confirm current free eligibility, Public visibility, runner label, Budgets and stop
settings. Unknown costs, expired/unverifiable controls or insufficient free CPU,
memory, disk or time require fail-closed stopping for owner judgment; never resolve
capacity shortages by moving to a paid environment or automatic plan expansion.

The new Emulator workflow must not upload Artifacts, create persistent caches,
push to registries, use Git LFS or GitHub Packages, or depend on paid Codespaces,
AI credits/add-ons or external paid services. Owner-reported $0 Budgets and Usage
blocked observations are historical evidence, not proof of run-time verification
or a mathematical guarantee of zero future charges. This PR performs no Billing
audit or settings change; inaccessible Billing information must not be presented
as verified through an invented API. Preserve Full CI and its coverage (run under the
Owner's CI execution policy of 2026-11-23), PR Safety CI, read-only permissions,
allowed pinned Actions and Branch Protection. Review any
new Action or permission separately under Public repository governance.

#### Owner amendment (2026-11-20): automatic Step 2 rehearsals

The Step 2 rehearsal workflow `aws-emulator-rehearsal.yml` is an exception to the
per-run confirmation above. It runs automatically on pushes to `main` that change
Terraform under `infra/` or the rehearsal code, and on the Owner's manual dispatch,
with no per-run billing attestation. The Owner relies on the standing
configuration: a public repository on GitHub Free, standard runners, and $0
Budgets with usage blocking. That configuration is Owner-reported and not
API-audited.

Every other constraint in this section still applies to that workflow: no
artifacts, caches, registry pushes, Git LFS, Packages, paid add-ons or larger or
self-hosted runners; a read-only token; not a required check; and fail-closed
run-time checks of `main`, the Owner, public visibility, the runner and its
capacity. The representative workflow keeps per-run confirmation. See
[AGENTS.md](../AGENTS.md#emulator-verification-workflow-and-evidence).

v14.4 §13.2 narrows this amendment to a limited standing authorization. It covers
only the independently reviewed scenarios in `all` of a pull request whose exact
HEAD the Owner explicitly approved for Squash Merge. Each manual dispatch, local
run or unapproved scenario needs the Owner's separate approval. Every formal run,
automatic or manual, enters the evidence ledger (§13.4).

Docker's independent Network Namespace is a proposed implementation to verify,
not an existing capability or exemption. Prove no external routes and independent
real-AWS unreachability; use loopback-only HTTPS, generated credentials/CA, enabled
authentication/TLS verification and telemetry off. Verify the official pinned
Emulator's signature/publisher. Use disposable Terraform Root/State, inspect plans,
exercise representative VPC Plan/Apply/Read/Update/Destroy, independently inspect
resource identity/deletion with non-Terraform APIs, and verify complete cleanup.
Do not log/upload credentials, private keys, raw State or saved plans. Fail closed
on any unmet safety condition. Do not claim a merged workflow demonstrates lifecycle
until an actual successful run and cleanup are independently reviewed.

### Preserved technical OPEN items

V7 P0-01–P0-04 and applicable P1 decisions remain open for their dependent stages.
No integration-target ARN, certificate/SNI, manifest publication, DNS, account,
backend or resource allocation is selected. The [V7 contract](v7-rest-private-integration-feasibility.md)
retains technical findings and historical evidence under this current acceptance
model. Secrets Manager's 30-day recovery versus 72-hour Live removal remains OPEN.
