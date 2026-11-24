# Portfolio verification policy — evidence and operating boundaries

> **Current authority.** The latest Owner-approved MASTER_POLICY, identified under the
> rule in [AGENTS.md](../AGENTS.md), is the sole controlling policy. Sections below
> that cite a specific policy version (v10 to v14.5), the v14.2 alignment record,
> optional DEV Live, G01–G07, the JPY 10,000 limit or 72-hour teardown are historical
> records, not current rules. Under the controlling MASTER_POLICY §15,
> real AWS/EKS Live verification and enabling real Apply/Destroy are outside the
> current scope. The current CI rules are in the
> [CI execution policy](#ci-execution-policy--owner-decision-2026-11-23) below.

## Representative Emulator workflow — AWS EMULATOR DEMONSTRATED for the VPC scenario

[Phase 3 implementation](../scripts/emulator-verification/README.md) supplies an owner-confirmed, merged-main-only manual
workflow, isolated single-VPC adapter and offline security contracts. Existing
required Full CI is unchanged; a separate static-only check exercises the new
contracts without Docker, Emulator or resource operations. Owner-dispatched
[Run 43791639228](#representative-emulator-run-43791639228) on merged main
`5c62dba517c7eb97394f77aaff6479a1315c524e` measured all fourteen controls, the
disposable `aws_vpc.proof` Create/Read/Update/No-op/Destroy lifecycle, independent
API checks and cleanup as PASS. After independent AI evidence review (PASS) and
Owner acceptance on 2026-11-16, AWS EMULATOR DEMONSTRATED is declared for that
representative VPC lifecycle scenario only. Other representative scenarios remain
NOT_TESTED; CORE PORTFOLIO COMPLETE and PORTFOLIO COMPLETE are not declared.
Codex namespace remains known environment BLOCKED.


Historical (superseded by later releases): operating requirements were the Master Policy v14.2
[alignment record](policy-v14-2-alignment.md). Core Implementation and mandatory
portfolio-level representative Emulator demonstration have separate acceptance
gates. Historical v10–v14.1 design and evidence stay scoped.
See [policy authority and PDF limitations](architecture-v2.md#authority-evidence-and-status).
No unavailable PDF contents or new implementation/Live approvals are inferred.

<a id="official-aws-emulator--policy-v13"></a>

## Official AWS Emulator — safety boundary

The legacy v13 anchor above preserves historical links, not old policy authority.

The approved permanent [AGENTS rules](../AGENTS.md#mandatory-official-aws-emulator-safety-controls)
are the mandatory lifecycle safety checklist. Real AWS credentials/SSO,
authenticated real APIs and real AWS Plan/Apply/Destroy/Import remain prohibited
in Codex Cloud. Isolated official Emulator Plan/Apply/Read/Refresh/Update/Destroy
is permitted only under all fourteen controls. Representative demonstration is
mandatory at portfolio level; lifecycle for every resource is not a blanket
implementation PR prerequisite. No real AWS fallback is permitted.

For every Terraform implementation, require affected offline/security checks,
PR Safety CI on every PR and Full CI under the
[CI execution policy](#ci-execution-policy--owner-decision-2026-11-23), independent
review and user approval. For separately approved
Emulator work, identify supported operations, establish isolation, exercise the
approved lifecycle, independently verify identity/cleanup and record evidence.
The mandatory controls include pinned signature-verified Emulator, loopback HTTPS,
generated credentials/CA, verified TLS, telemetry off, network namespace without
external routes, independent external-AWS denial, local STS account `000000000000`,
explicit endpoints/account guard, disposable adapter Root/State, reviewed plans,
exact ownership, independent create/delete checks and full temporary-file cleanup.
Never weaken production security or alter operational Roots/State for the emulator.

Preserve every existing Native/Mock Plan/Python/Security/Negative/Mutation check.
Emulator execution is separate from the required CI (PR Safety CI and Full CI). A dedicated workflow_dispatch
workflow may be designed in a separately approved PR and run only after its merge,
on standard public GitHub-hosted Ubuntu runners without additional charges.
No such workflow is introduced here. Documentation changes require documentation
checks and PR Safety CI on every PR, without lifecycle replay.
PASS means directly demonstrated; PARTIAL means partial evidence; PARTIAL-SKIP
requires actual evidence of the specific unimplemented API (for example HTTP 501).
FAIL is a Terraform/configuration defect requiring correction/retest; BLOCKED is
an unmet installation/network/isolation/runtime prerequisite; NOT_TESTED means
unexecuted. Never count unsupported APIs, skipped behavior or failed setup as PASS.
Stop for user permission on any new external download domain, without mirrors or
policy bypass. Significant verification gaps require explicit residual risk and
options; real AWS verification is outside the current scope (MASTER_POLICY §15) and is
never proposed as a fix or fallback.

### Historical feasibility proof — limited to aws_vpc

The owner-authorized, one-time experiment was reported against reference main
`e1cdbce78ba11959093a99ffd9300b8c0f9e52e0`, with official Emulator 1.0.322,
Terraform 1.17.0, AWS Provider 6.72.0 and CLI 2.35.0. It used only disposable
`aws_vpc.proof`, synthetic account `000000000000` and Region ca-central-1.

| Historical operation/control | Reported outcome |
| --- | --- |
| Terraform Create, Read/Refresh and no-op Plan | PASS |
| In-place Name tag Update and subsequent no-op Plan | PASS |
| Terraform Destroy | PASS |
| Independent API deletion verification | PASS; HTTP 400 InvalidVpcID.NotFound |
| Temporary State/credential cleanup and external isolation | PASS |

Saved create/destroy plans contained only the test VPC. Independent CLI checks
confirmed the created ID/CIDR, updated tag, subsequent absence and preservation
of pre-existing VPCs. SDK HTTP evidence was captured at service level; individual
SDK operation/status mapping was not retained. This is previously reported
experiment evidence, not a replay or CI result from this documentation PR.
No Subnet, NAT, EKS, IAM, Cognito, RDS, other-service or full VPC-module lifecycle
compatibility is established. No real AWS IAM/network/cost/availability/recovery
claim follows from it. Original historical acceptance records remain unchanged.

<a id="representative-emulator-run-43791639228"></a>

### Representative Emulator workflow evidence — Run 43791639228

This records the measured, owner-dispatched lifecycle of the merged
[representative workflow](../.github/workflows/aws-emulator-verification.yml) and
its [isolated adapter](../scripts/emulator-verification/README.md). It states only
what was actually exercised. After the independent evidence review and Owner
acceptance recorded below, AWS EMULATOR DEMONSTRATED is declared for this
representative VPC lifecycle scenario only. CORE PORTFOLIO COMPLETE and
PORTFOLIO COMPLETE are not declared.

| Item | Recorded value |
| --- | --- |
| Run / job | [43791639228](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43791639228) / job 133051177443, attempt 1, conclusion success |
| Tested SHA | Merged main `5c62dba517c7eb97394f77aaff6479a1315c524e` |
| Dispatch | `workflow_dispatch` by the repository owner; Owner check `2026-11-16T02:21:02Z`; run 02:21:12–02:23:23 UTC |
| Runner | GitHub-hosted standard `ubuntu-24.04`, image 20261111.127.1; no Larger or self-hosted runner |
| Billing | Owner-attested, **not API-audited** (receipt `owner-attested-not-api-audited`) |
| Emulator | 1.0.385 (package 1.0.385-1), SHA-256 `5344b39e76089633f3cc2d8795e5554ff0a89f4c26bc316fa748b3909423d3f5`, publisher `98BCF336A3BE53B734E967C52E5BF49BD940F624` |
| AWS CLI | 2.35.0, SHA-256 `339009d6ad0ad5d1448922ede4d07bf0ba44b6a91d9412610a8e745da9aca04b`, publisher `FB5DB77FD5C118B80511ADA8A6310ACC4672475C` |
| Terraform / Provider | 1.17.0, SHA-256 `c168cab7c637a8769fdb90089ddd19de701bc6ff8aca64dc2e2185fe46f59f67` / hashicorp/aws 6.72.0, lock file SHA-256 `1540d34f8637649be6ff4b742df969bbf024797aa48f240e36b16f7e6644e5a3` |
| Resource | Disposable `aws_vpc.proof` `vpc-0000000000000009b`, CIDR 10.238.0.0/16, synthetic account `000000000000`, ca-central-1 |

All 97 sanitized receipts in the job log are PASS. There are no FAIL, BLOCKED,
NOT_TESTED, PARTIAL-SKIP or `recovery-*` receipts, so the normal path ran without
recovery. The host summary validator (`host_evidence.py`) accepted the report.
The 70 report receipts were also re-validated offline with the same
`host_evidence.complete()` at the tested SHA: every one of the 32 required
receipts appears exactly once and the last receipt is `host-cleanup`.

| Control | Result | Measured in this run |
| --- | --- | --- |
| 1 | PASS | Signed official packages, exact publishers, artifact hashes and runtime versions |
| 2 | PASS | HTTPS endpoint bound to 127.0.0.1:9297 only |
| 3 | PASS | Generated credentials, `--auth on`; wrong secret, unknown key and unsigned STS all refused |
| 4 | PASS | Generated CA with strict hostname/TLS validation; system trust rejects the private CA |
| 5 | PASS | Telemetry off |
| 6 | PASS | Docker `--network none`; separate netns with loopback-only links and routes |
| 7 | PASS | Pre-resolved public STS/EC2 addresses unreachable by direct TCP |
| 8 | PASS | Signed local STS identity: account `000000000000`, `user/emulator` ARN |
| 9 | PASS | Offline provider init/validate with loopback endpoints, account guard and CA; lock file unchanged |
| 10 | PASS | Disposable adapter Root and temporary State on fresh tmpfs, initially empty |
| 11 | PASS | Saved Create plan reviewed: one `aws_vpc.proof`, CIDR, run tags, hash rechecked before Apply |
| 12 | PASS | State ID matches the independently described VPC; pre-existing VPCs preserved |
| 13 | PASS | Independent create, update and absence checks; State empty |
| 14 | PASS | Reviewed Destroy, separate resource/process/material/host cleanup receipts |

| Operation | Result | Evidence |
| --- | --- | --- |
| Initial State empty | PASS | Temporary State held no resource before Plan |
| Plan | PASS | Reviewed saved Create plan (control 11) |
| Create | PASS | Reviewed plan applied after hash recheck |
| Independent API create | PASS | CLI `DescribeVpcs`: ID, CIDR and tags match; baseline preserved |
| Read / Refresh | PASS | `plan -refresh-only -detailed-exitcode` exit 0 (no drift); refreshed `prior_state` identity, CIDR and tags |
| Update | PASS | Reviewed tag-only plan (`Phase` create → updated) applied |
| Independent API update | PASS | CLI `DescribeVpcs` shows `Phase=updated`; baseline preserved |
| No-op | PASS | Following plan holds a single no-op change |
| Destroy plan | PASS | Reviewed delete plan for the owned ID only |
| Destroy | PASS | Terraform Destroy applied |
| State empty | PASS | State no longer holds the VPC |
| Independent API absence | PASS | CLI `DescribeVpcs` returns `InvalidVpcID.NotFound` (exit 254) |
| Baseline preserved | PASS | Pre-existing VPC snapshot unchanged |
| Material cleanup | PASS | Private HOME, generated credentials/CA, State and plans removed |

Directly exercised through independent checks: STS `GetCallerIdentity` (signed;
wrong secret → `SignatureDoesNotMatch`; unknown key → `InvalidClientTokenId`;
unsigned → HTTP 403 `InvalidClientTokenId`) and EC2 `DescribeVpcs` (baseline,
create, update, absence). Exercised through AWS Provider 6.72.0: account guard,
Create, Refresh, tag Update, No-op and Delete of `aws_vpc`. The individual EC2
calls and HTTP statuses the provider issued are not retained; only Terraform exit
codes and reviewed plan/State content are. No unsupported Emulator API was observed.

These earlier merged-main runs each stopped fail-closed with host cleanup PASS.
Runs before 43723761085 are covered by
[CONTRACTS.md](../scripts/emulator-verification/CONTRACTS.md) and
[AUDIT.md](../scripts/emulator-verification/AUDIT.md).

| Run | Stopped at | Root cause | Fix |
| --- | --- | --- | --- |
| [43723761085](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43723761085), [43733987794](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43733987794) | `auth-invalid-signature` | AWS CLI 2.35.0 prefixes errors with `aws: [ERROR]: `; the envelope parser refused it | [#49](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/49) |
| [43741028022](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43741028022) | `auth-unsigned-sts` | Emulator awsQuery refusals carry no `xmlns`; the predicate required the STS namespace | [#50](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/50) |
| [43778833950](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43778833950) | `provider-init` (validate) | Docker `--tmpfs` defaults to `noexec`; the provider plugin could not execute from `/work` | [#51](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/51) |
| [43786507720](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43786507720) | `read` | Refresh-only plan JSON keeps the object in `prior_state`, not `planned_values` | [#52](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/52) |

PRs #49–#52 were merged on explicit Owner instruction after exact-HEAD Full CI
and offline-contract CI passed; separate independent code review did not precede
those merges. #51 is an Owner-accepted trade-off: `/work` is writable and
executable, while `/tmp` stays `noexec` and every other isolation flag is unchanged.
The later evidence review below examined this run and, as reported, the code at
the tested SHA; it does not change the fact that those merges were not
independently reviewed beforehand.

Limitations and residual risk:

- Scope is one disposable `aws_vpc` through the isolated adapter. No Subnet, NAT,
  EKS, IAM, Cognito, RDS, API Gateway, other service, the portfolio VPC module or
  any operational Root/State lifecycle is established.
- This is Emulator 1.0.385 behavior only, not real AWS deployment, IAM
  enforcement, networking, cost, availability or recovery. A known divergence:
  unsigned requests are refused `InvalidClientTokenId` where AWS answers
  `MissingAuthenticationToken` (upstream Emulator issue); the gate accepts the
  Emulator's documented code.
- Only allowlisted receipts are retained by policy; no raw API response, State,
  plan or credential exists. PASS rests on the gate logic, which is covered by the
  67 offline contract tests and mutation checks.
- One successful run on one runner image. A change to any pinned version or the
  runner environment needs a new run; reproducibility is not otherwise shown.
- The structured STS fallback path was not reached and remains unexercised.

Independent evidence review and Owner acceptance:

| Item | Recorded value |
| --- | --- |
| Reviewer | OpenAI ChatGPT; model reported by the Owner as GPT-6 |
| Review type | Independent AI evidence review. Not a submitted GitHub pull-request approval and not a human code review |
| Review date | 2026-11-16 (JST) |
| Review decision | PASS |
| Reviewed run / tested SHA | [43791639228](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43791639228) / `5c62dba517c7eb97394f77aaff6479a1315c524e` |
| Review scope | One disposable `aws_vpc.proof`: Create, Read/Refresh, Update, No-op, Destroy, independent API verification, all fourteen controls and full cleanup |
| Owner acceptance | 2026-11-16, by Owner instruction in the implementation session, not a GitHub review: accepted this evidence, then approved declaring AWS EMULATOR DEMONSTRATED limited to this scenario |

The review and the acceptance are recorded here as reported by the Owner. Neither
exists as a GitHub review on the related pull requests.

| Acceptance status | Current |
| --- | --- |
| Measured representative lifecycle (this run) | PASS |
| AWS EMULATOR DEMONSTRATED — representative VPC lifecycle scenario | **Declared** 2026-11-16, limited to the review scope above |
| Other representative scenarios (for example V7 REST/Cognito) | Not demonstrated; NOT_TESTED |
| Portfolio-level Emulator requirement as a whole | Not settled by this record; decided when PORTFOLIO COMPLETE is assessed |
| CORE PORTFOLIO COMPLETE / PORTFOLIO COMPLETE | Not declared |

### Default portfolio completion path

Real AWS deployment is not a completion condition and is outside the current scope
(MASTER_POLICY §15). Core Implementation uses correct source and
architecture, affected offline/security/mutation/evidence checks, credential-free
PR Safety CI on every PR and complete Full CI at milestones and on high-risk changes,
with independent review and user approval.
Representative Emulator lifecycle remains a separate portfolio-level requirement,
not a blanket per-resource PR gate. CORE PORTFOLIO COMPLETE independently requires all approved Core scope implemented,
reviewed, owner-approved and merged with offline/security quality, Full CI and
unverified scope explicit, without requiring Emulator demonstration.
AWS EMULATOR DEMONSTRATED separately requires actual representative lifecycle and
cleanup under all fourteen controls. PORTFOLIO COMPLETE requires both statuses;
no individual PR or historical VPC result declares completion. Real AWS/EKS Live
verification is outside the current scope (MASTER_POLICY §15) and is not a completion
condition; the earlier optional Live conditions (G01–G07, cumulative JPY 10,000,
teardown within 72 hours) are historical. Emulator success never becomes actual AWS
deployment evidence.

## V6 Cognito source foundation

Accepted post-V5 main `97f870753926398368733c39da722d5d7b792fa5` passed
[push CI43109394809](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43109394809)
(686 native/153 toolkit/13 configurations). V6 adds [cognito_auth](../infra/modules/cognito_auth/README.md) and
DEV ca-central-1/api Root, five resources: protected email User Pool, prefix domain
managed-login2, Resource Server, public code-only client and default branding.
Future REST belongs in the same API State; historical HTTP API remains unchanged.
Google IdP/Secret, actual users, email delivery, browser PKCE, real authentication,
REST integration and backend tenant/owner authorization are not complete.
Local Child49/Root46 native plus independent safety/evidence checks supplement
existing686; expected full CI781/153 and15 shared-provider configurations requires
independent exact-HEAD review. No AWS/State/Live execution or unavailable PDF claim.
G01–G07, JPY10,000/72-hour removal, paid-plan/callback/account approvals and the
Secrets recovery blocker remain OPEN. Historical status sections retain their scope.

## Evidence states and completion boundary

The approved [Architecture v2 target](architecture-v2.md) is documentation, not
implementation or Live authorization. Label each component/environment separately:

| Evidence state | Required evidence | Limitation |
| --- | --- | --- |
| Defined, not deployed | Approved architecture/environment contract | Does not establish implemented source or a passed test |
| Core Implementation — offline tested | Source revision, affected fmt/init/validate/Native/Mock/Negative/Security/Mutation/Evidence, exact-HEAD PR Safety CI PASS (and Full CI PASS where the CI execution policy requires it), independent review and user approval | Not whole-portfolio completion, deployed identity, authorization or service operation |
| EMULATOR DEMONSTRATED | Pinned versions, all fourteen controls, actual representative lifecycle, independent identity/cleanup evidence | Limited to successfully measured resource/API behavior; not real AWS deployment or security effectiveness |
| DEV Live tested with explicit approved evidence | Separately authorized scenario, actual outcomes and redacted evidence | Applies only to scenarios/resources/revisions actually verified |
| OPEN / awaiting approval | Explicit unresolved decision, scenario or approval | No assumption of implementation, authorization or success |

The implemented **post-R2** HTTP API baseline is main
`df5ef4b2e03bd55109b0490b1e63d1d4199b663b`: eight reusable modules, four DEV instances,
17 managed resources, eight outputs and five exact resource moves. Its
[successful CI 42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148) records **491 native / 153 Python** tests.
The pre-R1 nine-module/seven-instance **384/153**
[acceptance](offline-mvp-acceptance.md) at main
`89755c30508b78527fd46fa18593d5d5b11150f1` stays historical and unchanged;
R1 main `87f415f5290e2cab63696e1850a6c362eef97292` records 438/153.
17 is not a v2 Live inventory. REST/NLB/Istio/mTLS and new delivery/admin components
remain defined or OPEN. No DEV Live outcome or actual state migration is claimed.
All G01–G07 in the [readiness document](dev-live-validation-readiness.md) stay OPEN.
R3 documentation completion cannot replace exact post-R3 main/R4 regression review.

### V4 source/evidence boundary

Accepted V3 main `6b185820c806a0c96410a145106b9f103db14d89` has successful
[push CI42720431920](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42720431920)
(641 native/153 Python). V4's [static private ingress](../infra/modules/private_ingress/README.md)
is a candidate implementation with local Child28/Root38 native evidence and
independent actual-plan/security/source/evidence-fault checks. Full CI expectation
678 native/153 Python/13 configurations still needs exact-HEAD independent review.
Internal TCP/IP ownership and paired SG rules do not prove registered targets,
webhook/controller effectiveness, TLS/mTLS or application authorization. TGB
RBAC/IAM, AWS-managed SG/Pod SG assumptions, actual connectivity and all G01–G07
remain OPEN. Earlier post-R2/pre-R1 evidence above is preserved history.

## V5 private runtime source and offline evidence

Accepted post-V4 main `a4f0a9b8b0a810976c7ab305001729463443b27b` passed
[CI42757339642](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42757339642)
with678 native/153 toolkit and13 initialized configurations. V5 extends the same
Platform/private_ingress owner with exact EKS IRSA Role+registration-only policy
and four scoped Istio webhook/XDS SG rules. There are still10 children/three DEV
Roots/13 configurations; basic Platform has54 resources (EKS37+ingress17).
Existing NLB/TG/static SG/provider/state interfaces remain owned as before.

The [runtime foundation](../kubernetes/README.md) renders pinned LBC3.6.2 and Istio1.32.0 using
verified Helm3.22.1. Its61 objects implement ClusterIP Gateway, exact guarded TGB,
external CA/Secret references, MUTUAL TLS>=1.2 with client SPKI, STRICT mesh and
namespace default deny. No application or authenticated deployment is performed.
Actual local checks: Child36/Root38/EKS52 native; runtime8 Helm renders,
122 schema objects,58 security mutations,18 invalid inputs,19 evidence faults.
Current totals are in the latest Full CI job summary ("Summarize actual validation results");
this section is not a completed CI claim. Historical V3/V4 snapshots retain their original scope.

Registration-only IAM excludes ModifyTargetGroup/Attributes and SG writes. LBC
has no universal TGB-only switch; layered flags/RBAC/admission/IAM and clean
existing-resource inventory are mandatory. Effective admission, CA custody,
application sidecar CNI under restricted PSS, real AWS references/output publication,
capacity/connectivity and future REST backend TLS/SNI compatibility remain OPEN.
Offline schemas do not prove handshakes, IAM, controller effectiveness or Live.
G01–G07, cumulative JPY10,000, complete72-hour removal and the Secrets Manager
30-day recovery conflict remain unchanged. No State/AWS/Kubernetes Live authority.

## All environments — applicable offline implementation gate

For new/changed implemented modules and environment configurations require:

- Terraform formatting, credential-free initialization/validation and reviewed
  locks; root-owned providers/account restrictions, env/Region/service state and
  single authoritative resource owner, backups/locking and lifecycle safeguards.
- Actual mock-plan/resource inventories, outputs, cross-module identities,
  dependencies and resource ownership; no wholesale module substitution to hide
  incompatibility. Known/unknown plan fields and evidence errors fail closed.
- Proportionate positive, negative/input-boundary and security mutation cases.
  Mutations must detect deliberate unsafe changes; missing, malformed, skipped,
  failed or incomplete evidence is never a pass. Intentional rejected inputs do
  not count as successfully planned resource configurations.
- IAM trust/permissions and permission boundaries, scoped PassRole, OIDC audience/
  subject, ServiceAccount rights/RBAC, separation of human/deploy/upload/workload/
  client identities, secret avoidance in inputs/data/plans/state/logs and outputs.
- Network exposure/private routing/egress, state and data confidentiality,
  immutable artifacts/image digests/provenance, release ownership and rollback/
  recovery/lifecycle contracts; secret marking alone is not a persistence control.
- Environment-specific capacity/topology verification, including safe DEV system/
  mesh/monitoring fit and STG/PROD remaining-AZ peak CPU/memory/Pod/IP/DB-connection
  capacity, topology spread/PDB/readiness/update headroom and bounded HPA + Cluster
  Autoscaler. No concurrent Karpenter ownership or resilience inferred from counts.
- Full GitHub Actions regression including Terraform/Python, IAM reference,
  equivalence/negative/mutation tests and independent security guardrails.

### Target security verification categories

| Category | Required affected offline contracts and deliberate unsafe/negative cases |
| --- | --- |
| CloudFront / REST inbound mTLS | Origin clientAuth certificate/Region, Regional custom-domain versioned truststore, minimal CA scope/issuance, edge/Regional WAF and default execute-api bypass prevention; reject missing/invalid/untrusted/expired or unexpected certificate identities as applicable; do not claim mock checks perform live TLS |
| Certificate identity / revocation | API Gateway checks supported certificate properties/chain/validity but does not automatically check revocation. Verify that trusted-CA siblings cannot be assumed authorized as the expected CloudFront client. Review unauthorized identity rejection, compromise response, rotation/expiry monitoring and revocation-equivalent controls; mechanism feasibility, ownership, fail behavior and evidence remain OPEN |
| Cognito coexistence | Preserve Cognito User Pool Authorizer and method OAuth scopes; do not assume a Lambda Authorizer can be added alongside Cognito on the same REST method. Additional certificate authorization/revocation checks require compatibility/security/operational review, not selection in this PR |
| REST VPC Link V2 / NLB / Gateway | Internal NLB TCP:443 passthrough, target group/controller ownership, Pod IP/health/subnet/SG constraints, API backend client certificate and Gateway server chain/name/SNI; reject TLS termination at wrong boundary, insecureSkipVerification, unrestricted trust and plaintext fallback |
| Istio STRICT mesh | SPIFFE principal/SAN mapping, short-lived workload certs and AuthorizationPolicy; deny missing client cert, invalid CA, wrong SAN/identity, unauthorized principal, disallowed plaintext and expired certificates. Review selected PKI rotation/revocation-equivalent behavior; never invent automatic managed-service revocation |
| Cognito / backend user authorization | Valid access token and scope acceptance; missing/invalid/expired/wrong-scope denials; wrong-owner and cross-tenant denial independent of transport. ID tokens do not substitute for scoped authorization |
| EKS / DB / network | Private exposure/egress, RBAC/NetworkPolicy/default deny as appropriate, topology/capacity; PostgreSQL CA/hostname TLS verification plus approved DB auth, backup/PITR/reconnection/schema recovery. Do not impose custom client-cert mTLS on browser/managed AWS APIs/standard RDS/local same-Pod/control-plane traffic |
| Delivery / notifications | Version/digest pinning, scoped OIDC/CodeBuild IAM and private access, single release/controller owners, release health and verified rollback identity, correlated build/deploy/rollback success/failure events and independently handled notification failures |
| EC2 scheduling / watchdog | America/Toronto weekday START 08:00 / STOP 19:00 (no holiday calendar, DST-aware); Scheduler→SQS→Controller→EC2 and separate Watchdog. Detect failed/non-executed START/STOP, stale commands/retries/DLQ, state/SSM-readiness mismatch, unexpected running, Watchdog and SNS failures; thresholds remain OPEN |

TLS encryption, server verification, client certificate authentication/identity,
revocation response, Cognito user authentication and backend authorization are
distinct contracts. Minimum trust is not a proven single-client allowlist.

### Historical floor and responsibility

Keep all existing HTTP API, Terraform, Python, IAM, negative, mutation and security
checks intact. Recorded **384 Terraform native tests / 153 Python tests** are
historical pre-R1 acceptance evidence, not an upper limit or new mTLS coverage.
The verified post-R2 491/153 result above has separate categories: root 12 input
rejections/35 mutations/22 capture faults; API 28 mutations/25 capture faults/4
source mutations; retained R1 source mutations 3 and exact move-set negatives 6.
Historical HTTP API 17/19 and R1 438/153 remain tied to their earlier revisions,
not current counts. New security behavior needs its own tests.
Never remove/disable/skip/weaken CI checks for efficiency or migration: Full CI keeps
every check, and PR Safety CI selects Full CI steps by impact (Owner decision 2026-11-23).

Codex performs affected local checks and opens the PR; PR Safety CI runs the
impact-scoped regression on every PR, Full CI runs complete regression at milestones
and on high-risk changes, and independent review verifies completed CI and merge
authorization. Documentation-only changes use consistency/links/scope/secret/diff
checks, not unrelated full local regression. Do not repeatedly inspect successful logs.
Verify the required CI on the exact HEAD for every PR before the
independent-review/owner-approval handoff. V5 extends CI with actual pinned runtime validation without weakening existing checks.

## CI execution policy — Owner decision 2026-11-23

The Owner changed how CI runs; the checks themselves are unchanged. History above
(runs, counts and acceptance records) keeps its original wording.

| Workflow | Check name | Runs | Content |
| --- | --- | --- | --- |
| PR Safety CI (`pr-safety-ci.yml`, generated) | `PR Safety CI` | Every pull request to `main`, no path filter | Always-on: hygiene, credential and secret scan, `terraform fmt`, workflow and CI execution safety, CI tooling tests, real AWS/EKS operation guards, syntax of changed files. Impact-selected Full CI steps, copied byte for byte, with prerequisites |
| Full CI (`terraform-offline-ci.yml`) | `Credential-free Terraform validation` | A pull request changing a high-risk path; an Owner `workflow_dispatch` for a milestone. Never a push to `main` | Every check, count, mutation, security check and evidence contract; 60-minute timeout |
| AWS Emulator offline contracts | `static-contracts` | Unchanged: every pull request and push to `main` | Offline emulator, rehearsal-gate and evidence-ledger contracts |

**Impact map.** `scripts/ci/impact.py` maps each changed file to Full CI steps through
its Terraform configuration, every configuration that sources it, step inputs (paths
named in step commands, imported and literally named Python, read data) and the
explicit rules in `scripts/ci/impact_map.json`. The job summary prints the mapping.
An unmapped path, an undeterminable dependency, an unparsable workflow or Python
file, an unsupported module source or more than 300 changed files fails the check.
Every tracked file must map; `impact.py check` enforces that on every run.

**Expected counts.** Every pinned count is reviewed data in `tests/expected-counts.json`,
read by both CIs (`scripts/ci/expected_counts.py`). A count change selects only the
steps of the changed suites and needs no workflow change; missing, unknown or invalid
values fail closed; a decrease needs an `approved_reductions` record and is high-risk;
values are never generated from observed run counts.

**Full CI verdict.** PR Safety CI reports NOT REQUIRED, REQUIRED - STARTED
AUTOMATICALLY (a high-risk path, including every Terraform file that declares a
security-boundary resource) or REQUIRED - OWNER DISPATCH NEEDED (security-sensitive
Terraform lines, real-operation guard lines or a recorded count decrease). For both
REQUIRED verdicts, merge approval waits for Full CI PASS on the exact HEAD.

**Statuses.** They are never interchangeable.

| Status | Meaning |
| --- | --- |
| PR Safety CI PASS | PR Safety CI completed successfully on the exact pull request HEAD (its merge commit with current `main`), and its last step confirmed that exactly the selected and always-on steps ran. Never reported as Full CI PASS |
| Full CI PASS | Full CI completed successfully on the exact pull request HEAD, through the high-risk path filter or an Owner dispatch for that HEAD. A result for an earlier HEAD is never reused; cancelled, skipped, pending or running is not success |
| FULL CI NOT RUN | Full CI did not run on the exact HEAD; reports say so in these words |

**Milestone completion.** Claude's Owner-designated final task, Codex Root completion
and Owner-designated milestones are complete only with Full CI PASS and PR Safety CI
PASS on the exact HEAD, Offline Contracts success, independent review and explicit
Owner approval. A high-risk pull request also needs Full CI PASS before merge
approval. A Full CI failure stops milestone completion and merge approval.

**Full CI trigger and SHA management.** The Owner dispatches Full CI on the pull
request branch with `pull_request_number`, `expected_head_sha` (exact 40 hex) and a
`reason`. The trigger step refuses the run unless the event is `pull_request` to `main`
(merge commit whose second parent is the event HEAD) or a dispatch by the Owner as
actor and triggering actor, on a branch other than `main`, whose HEAD equals the
expected SHA and contains the current `main`. A dispatch also binds the pull request
number to the branch, HEAD and base `main` through the read-only public API; a mismatch
refuses the run, and an unanswered API is recorded NOT_VERIFIED_BY_WORKFLOW, leaving
the match to the reviewer and the Owner on GitHub. The job summary records the pull
request, HEAD, base `main`, tested tree and binding. A new HEAD needs a new run.
`workflow_dispatch` is available only once this workflow is on the default branch;
until then Full CI runs through the path filter, which includes `.github/**`.

**Review and Owner approval.** Unchanged: independent ChatGPT review and explicit
Owner approval for every pull request, then Squash Merge. Before merge: the HEAD
equals the reviewed SHA, base `main` is unchanged, the required CI succeeded on that
HEAD and Full CI PASS exists where required.

**CI failure.** Stop, read the failed step and its logs, make the smallest correction
on the same branch, re-run affected local checks, push only when no run of that
workflow is queued or in progress, and verify the required CI again on the new HEAD.

**After merge.** No Full CI re-run on the same tree. `scripts/ci/merge_check.py`
confirms that the squash commit's only parent is the reviewed base `main`, that its
tree equals the tree CI recorded as verified (`tested_tree`), and that this tree
belongs to the reviewed HEAD; a mismatch stops further merges for investigation. Offline Contracts and, on its trigger paths, the Emulator rehearsal
still run on the push to `main`.

**Branch Protection.** `main` is protected; its only required check is `PR Safety CI`
(GitHub Actions, enforcement everyone), as independently confirmed for the Owner by
ChatGPT. The migration from `Credential-free Terraform validation` is complete; the
add-then-remove steps in
[scripts/ci/README.md](../scripts/ci/README.md#branch-protection-migration) are a
historical record (that file sits on a high-risk CI path and is corrected with the
next approved CI change). Full CI is not a required check but stays mandatory by rule
where this policy requires it. Only the Owner changes Branch Protection.

**`infra/README.md`.** Its "Independent offline Terraform CI" section (every pull
request and push, a 20-minute timeout, cancelled runs) is not a current rule. It will
be corrected with the next approved `infra/` change, because editing `infra/**` starts
the Emulator rehearsal.

**v14.5 alignment (2026-11-23).** v14.5 §12 adopts this CI execution policy as the
controlling CI rule. The first normal pull request under it (the v14.5 documentation
alignment) demonstrates PR Safety CI alone. The Owner dispatch path has since been
used: Full CI runs 45358186407 (PR #99, HEAD `3b081f8`) and 45398955069 (PR #100,
HEAD `bcb196d`) succeeded on the exact pull request HEADs. PR #101 merged with FULL CI
NOT RUN under a one-time Owner exception. The 6c-B5 audit is Claude's Owner-designated
final task, with Full CI dispatched by the Owner (reason `claude-final-task`): run
45453872145 succeeded on PR #102's exact HEAD `b9edba4`.

**CI-PERF-01 (Full CI performance, MASTER_POLICY §12.5.1).** Before the Codex handover,
Full CI is shortened without removing anything: target within 40 minutes, ideally
within 35, about 50–55 minutes at the final portfolio stage (targets, not guarantees),
hard timeout unchanged at 60 minutes. Every test, mutation ID, expected count,
assertion and safety contract is kept. Parallelization, persistent caches, paid
runners and production safety changes need separate approval. Profiling and design
precede implementation approval, and the implementation is a high-risk CI change with
Full CI. The responsibilities for CI-PERF-01 are in
[AGENTS.md](../AGENTS.md#ci-perf-01-full-ci-performance-master_policy-1251).

## Historical: DEV Live limits (not current)

> Superseded by MASTER_POLICY §15 (since v14.5): real AWS/EKS Live verification is outside the
> current scope, the JPY 10,000 limit and G01–G07 authorize nothing, and the past Live
> budget is not reused. The text below is kept as a historical record.

No real AWS Live operation is authorized by this PR. Actual external execution
requires all applicable gate evidence, independent approval and explicit scope outside Codex
Cloud. Never request/use real AWS credentials, authenticated real AWS APIs/plans,
operational State operations or real AWS apply/destroy/deployments in Codex Cloud.
Isolated emulator verification follows the unchanged fourteen controls above and is not Live.
No workload/destructive testing in the Organizations Management Account.

**Actual cumulative DEV Live spending must stay within JPY 10,000 across the
approved validation period. All testing and verified complete teardown must finish
within 72 hours from approved Live start.** Prefer shorter execution where possible.
Older monthly examples are not spending limits or sizing approvals.

Before paid resources, independently review actual pricing/Region/runtime, tax,
FX, fixed/usage charges, retained charges, certificate lifecycle, contingency and
teardown. **CloudFront Origin mTLS supports Business, Premium and Pay-as-you-go,
not Free.** Review applicable plan/feature availability and all other service costs
before implementation or Live; no plan is selected/purchased here. A 72-hour run
does not guarantee compliance. If validated cost plus contingency/teardown cannot
fit the cap, the scenario is not authorized and stays OPEN or Offline-only.
Budgets/alerts are not real-time enforcement or guaranteed billing cutoff. Assign
manual stop authority, monitoring, inventory and a reviewed execution timeline;
stop early enough to remain under both limits.

Prioritize only feasible approved evidence:

| Priority | Scenario | Required actual record |
| --- | --- | --- |
| 1 | Approved Terraform creation and inventory | Exact revision, approved account/Region/state/identity, reviewed complete scenario plan, actual creation and full managed/external inventory; unexpected changes stop execution |
| 2 | Istio STRICT mTLS positive/negative communication | Expected identities/trust/authorization and actual permitted/denied cases; no assumed encryption or revocation results |
| 3 | REST API → VPC Link V2 → NLB → Istio backend certificate authentication | Actual passthrough and Gateway server-name/trust/client-certificate verification, positive/negative outcomes and redacted correlation |
| 4 | Deployment, rollback and notifications | Only remaining approved affordable scope: pinned build/version/digest, actual health and rollback identity, success/failure event delivery and independent delivery-failure handling |

CloudFront-origin mTLS, Cognito, RDS and full delivery integration are future
scenario candidates, not a mandatory simultaneous stack if limits cannot be met.
Any executed protected-route scenario still requires the relevant token/scope/
owner negatives and live certificate-boundary checks. Do not weaken a selected
scenario's security to fit cost. Unexecuted scenarios stay OPEN or Offline-only,
never passed; offline definition remains required for the full portfolio target.

Record expected/actual outcomes including failures, revision/build, approvals,
redacted resource references, timings, certificate identities/trust revisions,
image digest/object version, correlation and follow-up. No secret/token/private
key/payload/state or unredacted plan in Git/public logs. Preserve approved redacted
audit evidence outside AWS before cleanup. Infrastructure recovery, application
rollback and DB recovery are separate, not inferred from each other's success.

### Complete teardown is an acceptance condition

Delete and independently verify removal of **all AWS resources created for the
exercise**, Terraform-managed and external/service-managed dependencies. Reconcile
actual AWS inventory with state and external records; neither stopped instances
nor a successful terraform destroy alone establishes completion. Never delete
pre-existing shared resources. Inventory applicable EKS/control planes/nodes,
ENIs/EBS, NLB, NAT/EIPs/endpoints, RDS/backups/snapshots, S3 versions/delete markers,
ECR images, logs, secrets, API/custom domains, ACM, WAF, KMS and related dependencies.
Review AMIs, retained backups, deletion protection, secret recovery windows, delayed
deletion and external retention before approving Live. Avoid newly created CMKs or
other unavoidable delays incompatible with the deadline; start teardown early.

The historical secret module's 30-day recovery means the full unchanged MVP is not
a feasible 72-hour actual-deletion scenario. Resolve applicable lifecycle/scenario
blockers in separately reviewed work before creation; no bypass is authorized here.
After cleanup no exercise resources should remain generating ongoing charges.
Delayed billing, historical usage and FX may still produce later invoices; do not
promise literally zero subsequent billing. Administration EC2 scheduling does not
replace this deadline or stop other-service billing.

## STG / PROD — offline-only portfolio acceptance

Require implemented credential-free offline contracts for two active AZs, per-AZ
NAT/node capacity, redundant Istiod/Gateway/apps, HPA + Cluster Autoscaler,
spread/PDB/readiness and remaining-AZ capacity model, and Aurora Provisioned
writer/reader placement. No apply, authenticated plan, or live failover/load/
penetration/monitoring/recovery test is required for portfolio completion.
Never label unexecuted tests passed or counts as measured SLA/RTO/RPO.

Real production work would separately require reviewed threat/penetration/load,
observability/alerting, expiry/rotation/compromise, AZ/node/DB failover/reconnection,
backup/PITR/schema/state recovery, revocation, cost and teardown exercises with
actual evidence and approved objectives. No cross-region DR/cold standby or
long-running production operations are introduced. All missing approvals and live
outcomes remain OPEN; independent review verifies this PR's completed CI separately.
