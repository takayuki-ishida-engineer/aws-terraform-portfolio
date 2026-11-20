# Master Policy v14.2 — owner-authorized alignment record

The owner supplied the full 43-page Master Policy v14.2 text on 2026-11-15
(Asia/Tokyo); all pages were reviewed, including priority provisions A–T and the
34-page v14.1 archive. A–T override conflicting archived clauses. This record
aligns repository rules with that supplied text. The PDF binary was not inspected;
neither its hash nor the supplied archived-v14.1 SHA-256 was independently verified.
The previously supplied v14.1 34-page extraction remains historical provenance;
its architecture, ownership, security, Public governance and Live boundaries remain
in force except for the expressly revised quality/Emulator acceptance model below.
Earlier editions and historical evidence do not supersede these current rules.

## Quality and acceptance model

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

## Separate PR and approval gates

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

## Future optional Emulator workflow constraints

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
as verified through an invented API. Preserve the existing required Full CI, its coverage,
read-only permissions, allowed pinned Actions and Branch Protection. Review any
new Action or permission separately under Public repository governance.

### Owner amendment (2026-11-20): automatic Step 2 rehearsals

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

## Preserved technical OPEN items

V7 P0-01–P0-04 and applicable P1 decisions remain open for their dependent stages.
No integration-target ARN, certificate/SNI, manifest publication, DNS, account,
backend or resource allocation is selected. The [V7 contract](v7-rest-private-integration-feasibility.md)
retains technical findings and historical evidence under this current acceptance
model. Secrets Manager's 30-day recovery versus 72-hour Live removal remains OPEN.
