# Architecture v2 foundation design — Network / State / Identity

This is an implementation-readiness proposal, not implementation or execution
approval. Current operating policy is user-approved Master Policy v11 (2026-11-09);
this design retains historical v10 (2026-11-08) provenance. See
[authority/PDF limitations](architecture-v2.md#authority-evidence-and-status); no
unavailable v11 contents or new approval is inferred. The user **APPROVED**
maintainability-first functional module grouping
and migration-first priority in the [R0 repository strategy](repository-structure-strategy.md).
This supersedes the former standalone NAT/core/routing recommendation. Detailed
AWS/state/migration decisions below remain **OPEN**. No account, CIDR, AZ allocation,
operational resource name, backend or principal is selected. All G01–G07 Live gates
remain OPEN. Do not create the future PRs described here during this task.

Historical foundation-design evidence baseline: main `7876bdbf6cef7f1cb171521352e69a43cc14113e` and successful
[post-merge offline CI 42569910881](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42569910881).
The [verification policy](portfolio-verification-policy.md),
[readiness gates](dev-live-validation-readiness.md),
[bootstrap proposal](dev-bootstrap-decision-plan.md) and
[technical history](../infra/README.md) retain their existing authority/evidence.
Mocks never establish actual AWS reachability, ownership, permission or availability.

## Historical V1 transition after accepted R4

The user independently accepted R0–R4 at main
`899f944c3887fa739dfb39f43617321a696c727b`, with matching successful
[push CI 42628851626](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42628851626).
The implementation below is unchanged from post-R2. The
[V1 VPC extension decision proposal](vpc-extension-decision.md) now evaluates
legacy/per-AZ routing, zonal NAT/EIP and endpoint contracts inside the existing
VPC module. Its singular-output compatibility exception V1-C01 and the detailed
D01–D05/D07–D08/D11–D12 approvals remain OPEN; this is documentation, not V2 or
AWS/state/Live authorization. Earlier R3/R4 handoff statements are historical.

## V2 source baseline and V3 ownership update

The approved V3 starting main is `da1af5c4eed15f5c9145799409d53c1db7508c94`,
with successful [post-V2 push CI 42688811654](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42688811654)
(560 native / 153 Python, 10 configurations). The historical inventory and OPEN
register below retain their recorded design provenance; they are not claims that
V2 NAT/per-AZ routing/endpoints or its Network Root are still unimplemented.
The [VPC README](../infra/modules/vpc/README.md) and
[Network Root contract](../infra/services/dev/ca-central-1/network/README.md) describe
that source; no AWS deployment or real state migration is inferred.

V3 adds one [eks_platform child](../infra/modules/eks_platform/README.md) and
[DEV Platform Root](../infra/services/dev/ca-central-1/platform/README.md). Platform
owns Cluster/MNG/LT, dedicated IAM/OIDC, custom SGs/rules, access/logs and three
managed add-ons; Network retains all VPC/subnet/route/NAT/endpoint ownership.
No cross-root state reader/writer is added. Only an explicit versioned minimal
V2 output subset is accepted, with actual provenance, distribution, custody and
live resource reconciliation still OPEN. Child/Root local native evidence is
52/29; full PR CI is independently required (expected 641/153, 12 configurations).

Multi-AZ Cluster coverage is separate from DEV's one worker AZ. All operational
versions, subnet selections, capacity and identities require supplied reviewed
values. AWS-managed control-plane SG residual permissions, private connectivity,
namespace Edit/Pod Security and real IAM/KMS effects remain deployment review
items. Future runtime/ingress/delivery and STG/PROD roots are not implemented.
No G01–G07, state/backend/account, Live budget/teardown or Secrets recovery gate
is closed by these source additions. Earlier roadmap entries are historical,
not authorization to repeat completed V2 work or begin a later phase.

## A. Historical post-R2 implementation inventory

Post-R2 snapshot source: main df5ef4b2e03bd55109b0490b1e63d1d4199b663b,
[successful CI 42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148).
Earlier nine-module/seven-instance/384-native descriptions apply only to the
historical snapshots above and the unchanged pre-R1 acceptance record.

| Source evidence | Implemented contract | Missing / limitation |
| --- | --- | --- |
| [VPC resources](../infra/modules/vpc/main.tf) | IPv4 VPC with DNS support/hostnames; keyed private/public subnets and associations; no automatic public IPv4/IPv6 assignment | No NAT/EIP, endpoints, per-AZ private routing, SG/custom ACL hardening or EKS integration |
| Same VPC source | One shared private route table with route=[]; optional IGW and one public table/IGW default route only when public subnet map is nonempty | Private route table has no configured internet path; implicit AWS VPC-local routing is not isolation enforcement. AWS-created default SG/ACL/main table are not hardened |
| [VPC inputs](../infra/modules/vpc/variables.tf), [outputs](../infra/modules/vpc/outputs.tf), [README](../infra/modules/vpc/README.md) | Required prefix/VPC CIDR/nonempty keyed private subnets; empty public map default; canonical IPv4/range/containment/nonoverlap and AZ syntax validation; actual VPC/subnet/table/IGW references | Syntax does not prove enabled AZs, account/Region membership, quotas or available IPs. Shared private_route_table_id is a singular compatibility contract, not per-AZ output |
| [VPC native tests](../infra/modules/vpc/tests/vpc.tftest.hcl) | 16 historical mocked plan runs: private defaults, public/private routing/associations, stable keys, tags, outputs and input/precondition rejection | These tests do not verify NAT, endpoints, new topology or live network behavior; no new test results claimed here |
| [DEV root](../infra/services/dev/ca-central-1/serverless-api/main.tf) | dev / ca-central-1 / serverless-api; eight reusable modules repository-wide, four workload instances, 17 resource definitions, eight outputs and five exact resource moves; Lambda workload 4 / HTTP API 6 resources | Root does not call VPC; Lambda remains outside a VPC. Historical HTTP API MVP stays independent from REST/NLB/Istio target |
| [Provider](../infra/services/dev/ca-central-1/serverless-api/providers.tf), [backend](../infra/services/dev/ca-central-1/serverless-api/backend.tf), [versions](../infra/services/dev/ca-central-1/serverless-api/versions.tf) | Root AWS provider, fixed workload Region, allowed_account_ids=[var.aws_account_id], default tags; local state; Terraform ~>1.17.0 / AWS ~>6.72.0 and committed root lock | No live account verified. STG/PROD roots/backend operation are not implemented; remote-state selection remains OPEN |
| [Offline workflow](../.github/workflows/terraform-offline-ci.yml), historical acceptance | Post-R2 main CI passes 491 Terraform native and 153 Python tests, IAM reference/equivalence/negative/mutation/independent guardrails and fail-closed evidence checks | Historical counts are neither future coverage nor a ceiling. Root 12 rejected inputs/35 mutations/22 capture faults and HTTP API 28 mutations/25 capture faults/4 source mutations are separate evidence categories |

## B. Approved functional network ownership

The [approved repository strategy](repository-structure-strategy.md) selects one
coherent vpc module for VPC, keyed subnets, IGW/NAT/EIP, public/private tables,
routes/associations and compatible endpoints. Internal files such as subnets.tf,
gateways.tf, routing.tf, endpoints.tf and security.tf improve readability without
creating separate child resource wrappers. All files share scope; references and
narrow depends_on determine order, not file placement. Root owns provider/backend,
account restrictions, environment overrides and lifecycle selection.

This grouping decision is APPROVED. At this historical design snapshot, NAT/
per-AZ/endpoint behavior was absent. V2 now implements the opt-in contract documented
in its README while preserving legacy addresses/defaults and 16 original tests.
Do not mix competing route/association owners or infer live migration success;
refer to the current VPC contract rather than applying this snapshot as code.

Network roots own the coherent module's state. EKS platform roots consume approved
outputs and own cluster-specific controls; private_ingress owns Terraform internal
NLB TCP:443/listeners/target groups, while Kubernetes-side control owns Gateway Pod
registration. Controller/TargetGroupBinding/health/cross-zone details remain OPEN.
No ALB substitution or duplicate load-balancer ownership is allowed. Workload SGs,
RBAC/NetworkPolicy and custom NACL responsibilities need approved flow/rule ownership,
not duplicated reconcilers. A genuinely separate lifecycle/security/state owner can
justify an explicit module exception, not default NAT/route/endpoint wrappers.

The former separate nat_gateway/network_core/private_routing path is superseded,
not an alternative first implementation recommendation. Only after R4 may focused
feature PRs extend existing vpc; no separate wrappers merely for AWS resource types.

## C. Proposed root and state boundaries

Evaluate a dedicated network-service root at
`infra/services/<env>/<region>/<service>/`, separate from application/EKS/ingress
roots. The strategy lists intended network/platform/api/database/delivery and edge root
boundaries; exact operational naming, provider/state ownership and interfaces still
need implementation review. This can
clarify lifecycle and shared network ownership, at the cost of explicit publication,
ordering and compatibility operations. A single larger root would make references
simpler but couple application deletion/change to shared network lifecycle; it is
an alternative requiring approval, not the recommended default for shared network.

DEV retains local state; STG/PROD use remote state with implementation and custodian
approval still OPEN. Every root owns its account-restricted provider and backend.
One authoritative state owner and one authorized writer per resource; do not use
Terraform workspaces alone as a substitute for approved env/Region/service isolation.
No concrete backend, remote-state data source or cross-root access is implemented.

| Output-distribution candidate | Exposure / operational trade-off | Approval required |
| --- | --- | --- |
| Explicit versioned, minimal non-secret manifest passed as consumer inputs | Preferred candidate: publishes only approved references plus env/Region/account scope, keyed subnet/AZ and interface revision; integrity/freshness/provenance still need controls. IDs are operational metadata, not automatically public | Publication store, access, integrity/versioning, scope validation and release/rollback owner |
| Approved parameter/configuration service | Can separate output-read permissions from state storage but adds service/IAM/cost/dependency/teardown obligations | Service selection, read/write principals, schema, consistency, DNS/connectivity and recovery |
| Direct state output consumption | Couples consumers to state availability/schema and may expose full state snapshot, not merely outputs [S7]; a sensitive flag is not access isolation | Explicit security acceptance, backend/read access, leakage and recovery review; not selected |

Publish only actual provider-returned VPC/subnet/NAT/endpoint references and approved
metadata; never fabricated IDs, credentials or whole state. Version the output
interface, preserve stable keys and validate consumer env/Region/account expectations.
No consumer writes the network state. Model foundation creation → approved output
publication → consumer plan as external orchestration, not a shared state writer.
No lookup mechanism is chosen here. Replacements/removals require downstream impact
review, consumer migration and ordering before foundation teardown; cycles reopen
the root split. Reject stale, wrong-scope or incomplete interfaces before deployment.

Before backend/root implementation approve encryption/access, state custodian,
writer coordination, locking support/failure behavior, backup/integrity/restore,
retention and migrations. Local backend OS locking covers the shared local state,
not independent copies/runners [S5–S6]; require a single writer and external handoff.
Not all remote backends lock. Never bypass locks to resolve contention. Import and
ownership transfer require verified identities, frozen writers, snapshots, address
maps, independently reviewed cutover and recovery; no dual management or unsafe
imports. Restoring state does not roll back AWS resources. Future remote migration
is a separate approval, not authority to create backend resources in this PR.

## D. DEV / STG / PROD comparison

| Dimension | DEV | STG / PROD |
| --- | --- | --- |
| Workload AZs / configured coverage | One active workload AZ; additional EKS cluster/other service-required AZ subnets. Do not confuse one worker AZ with cluster subnet requirements [S1] | Two active workload AZs with supported additional service-required coverage |
| Subnets | Private nodes/Pods/DB/ingress as approved; public subnets support the public NAT/IGW path, not public workers | Segregated approved subnet responsibilities, per-AZ IP budgets and no automatic public worker IPs |
| NAT and route separation | One NAT; explicit mapping for extra configured subnet AZs must consider cross-AZ cost/failure and not imply redundant egress | One NAT per active AZ; private tables route via intended same-AZ NAT; never one shared default route pretending per-AZ resilience [S2] |
| Endpoints / egress | Cost-reviewed endpoint set plus restricted NAT paths; private DNS/SG/policy and service dependencies reviewed | Per-AZ availability/cost/endpoint placement, restricted egress and appropriate private DNS/policies; endpoints are not universal internet replacements |
| EKS capacity | Minimal worker only if system/mesh/monitoring/application fit; bounded HPA + Cluster Autoscaler; increase if inadequate | Redundant Istiod/Gateway/apps; surviving-AZ peak CPU/memory/Pod/IP/DB-connection headroom, spread/PDB/readiness/update capacity; no fixed count guarantees |
| NLB / Gateway | Internal NLB TCP passthrough to Gateway backend mTLS; subnet/targets/cross-zone design OPEN; one active app AZ is not end-to-end HA | Reviewed NLB/Gateway target distribution and cross-zone behavior, health/drain/failure paths; not assumed from two replicas |
| State / accounts | Local network/application states, one custodian/writer each, root account guard; dedicated non-management Live account not yet approved | Remote backend and account separation strategy require approval; independent env/Region/service ownership and account guards |
| Failure assumptions | Update/worker or NAT-AZ failure downtime can be accepted only with explicit scope; extra subnets do not provide spare compute | Define actual peak and remaining-AZ capacity including failover/reconnection; no measured availability percentage/RTO/RPO |
| Verification / Live | Complete offline checks; Live only after G01–G07, cumulative JPY 10,000 and complete removal within 72 hours | Credential-free offline implementation verification for portfolio completion; no authenticated plans, deployment or Live resilience tests required |

Subnet/AZ/CIDR/IP allocation remains OPEN: account-specific AZ support/mapping,
EKS control-plane ENI and upgrade headroom, CNI node/Pod addresses and surge,
endpoint ENIs, NLB target/health paths and future DB connections must be budgeted.
No concrete CIDR, subnet ID, AZ assignment, account ID or operational name is supplied.
Private EKS API access and node/workload AWS-service egress are separate problems
[S4]. Image pulls may need ECR API/DKR plus S3 connectivity; review STS, EC2,
logging, SSM, controllers and other actual callers, not a speculative endpoint list.
Interface endpoints consume IPs and have SG/DNS/placement costs [S3]; gateway and
interface endpoint routing/policy differ. Build an approved caller→service→DNS/
route→SG/NACL/policy matrix before implementation. NAT does not enforce application
allowlists; stateful SGs, stateless NACL return paths, NetworkPolicy enforcement and
endpoint policies each require a distinct reviewed role, not assumed hardening.

## E. Identity and permission responsibility matrix

| Identity class / placeholder owner | Sole responsibility and separation | Checks before future implementation |
| --- | --- | --- |
| Human operations / account-security owner | Federated temporary administration with MFA/session expiry/revocation; no assumed existing workload account | Dedicated non-management ownership, Identity Center home Region/prerequisites separate from workload Region, SCP/session/permission boundaries; no unrestricted admin |
| Terraform deployment / infrastructure owner | Approved resource provisioning/refresh/lifecycle only in its scope, separate from app runtime | Account/Region guard, restricted trust, exact resources/actions/tagging, scoped PassRole and intended service; effective denials reviewed externally |
| Artifact publication / build owner | Publish approved ZIP version/image digest/provenance; not infrastructure state writer | Scoped object/repository/version permissions and session/source controls; Lambda gets no artifact grant merely because code lives in S3 |
| Application runtime / application owner | Exact log/optional approved secret/service access, separate from deployment | Trust and resource scope, no broad PassRole/IAM/S3/secret access; Approach A metadata only, actual values initialized externally |
| Kubernetes platform/controllers/workloads / platform owner | Distinct controller and workload ServiceAccounts; target registration separate from NLB creation; least-privilege RBAC | Controller IAM/trust/subject, namespace/SA binding, target-group scope, NetworkPolicy/identity and no dual reconciler; exact mechanisms/settings deferred |
| CI/CD OIDC / delivery owner | Scoped short-lived deployment/build role assumptions, not unrestricted human/runtime identity | Audience/subject/repository/environment/ref controls, negative trust/PassRole cases, private CodeBuild reachability; no static AWS credentials |
| API clients / application-security owner | Cognito access tokens/scopes and backend user/tenant authorization, not infrastructure roles | Wrong-owner/tenant/scope denials; preserve approved certificate/Cognito boundary. PKI/revocation compatibility is deferred, not replaced by SigV4 user auth |
| Secret initialization/rotation / secret owner | Approved external values and rotation; Terraform owns only Secrets Manager metadata | Google/DB/key/plaintext absent from variables/data/plans/state/outputs/CI; runtime use and revocation/rotation evidence outside this offline design |

Use dedicated approved workload accounts for Live; none is assumed created or
authorized. No real principal, trust document or IAM policy is assigned here.
Federation and temporary workload credentials are preferred official guidance [S8],
not proof of effective permissions. Never introduce unrestricted administration,
PassRole or speculative trust. Ownership approvals precede any identity implementation.

R1/R2 status: Lambda owns its four workload resources; HTTP API now owns its
five API/permission resources and dedicated access Log Group. DEV has four root
calls and the same 17 resources/eight outputs. Five exact moved declarations
retain historical identities in source. Generic logs/51 tests remain independently
retained with no DEV consumer; retirement needs separate review. See the
[migration record](repository-structure-strategy.md) for historical local evidence
and completed R1/R2 main CI. No actual state migration or new feature is claimed;
accepted R4 provenance is recorded above.

## F. Approved migration-first sequence

**R0 → R1 → R2 → R3 → R4 → new Architecture v2 features.** See the
[resource/output/test migration matrices](repository-structure-strategy.md) for
source-derived R1/R2 addresses and still-OPEN future operational decisions.
Functional grouping
and this order are approved. R0–R3 are merged and R4 is independently accepted
as recorded above. V1 is design only; new feature implementation still requires
separate approval.

| Stage | Separately authorized responsibility | Required verification / acceptance |
| --- | --- | --- |
| R0 — historical merged design | Approved structure, nine-module inventory, seven-instance/17-resource migration plan | Exact documentation scope, source/link/consistency/secret/diff checks; no migration |
| R1 — merged Lambda workload source | Consolidate function, dedicated role/inline policy and dedicated Lambda logs into lambda_workload; update affected root/interfaces/tests/docs/CI | Exact destination/move/output decisions first; four resources, effective configuration/security/dependencies preserved; actual-plan/policy/negative/mutation and complete independent CI; no new app feature |
| R2 — merged HTTP API/log source | Own dedicated API access Log Group inside api_gateway_http, retaining historical AWS_IAM architecture | Six resources together with exact invoke/log/auth/retention contracts, safe address compatibility and full affected tests/CI; retain generic logs/51 tests; any retirement needs separate consumer/coverage review |
| R3 — merged documentation stabilization | Status/provenance consistency and R4 handoff only; code/security contracts unchanged | Documentation/source/link/scope/secret/diff checks and independent complete PR CI; not R4 acceptance |
| R4 — accepted offline structural baseline | Exact post-R3 main/CI recorded above; no Live or real-state acceptance | Full Terraform/Python/IAM/guardrail/negative/mutation/evidence suite rerun and independently verified on exact final main; source-text checks are not enough |
| New features only after accepted R4 | Focused extensions of coherent existing vpc for NAT/EIP/per-AZ routing/compatible endpoints/security; later EKS/REST/Cognito/edge/mTLS/DB/delivery/developer DB-access work | Preserve current private-only behavior and 16 VPC cases; add actual resource/dependency/ownership/negative/security mutation evidence; detailed allocation/backend/IAM/provider/cost approvals still required |

R4 is additional baseline verification, not permission to defer security or full
CI in R1/R2/R3. All intermediate implementation PRs need relevant local security
checks and complete independent GitHub Actions regression. Codex still stops after
PR creation; completed CI/merge approval is verified independently. No pending run
or earlier branch result establishes an R4 final-main pass.

## G. Approved grouping and OPEN implementation register

D01 records the now-approved grouping separately from still-OPEN technical
subdecisions. Other rows require owner/reviewer approval before implementation.
Role labels below do not name actual assigned people or approvals.

| ID / status | Affected PR | Options / candidate | Security and operational implications | Evidence / official source needed | Required approval |
| --- | --- | --- | --- | --- | --- |
| D01 — APPROVED grouping / OPEN implementation | R1–R4 / post-R4 VPC | Coherent vpc ownership and migration-first priority approved; no default resource wrappers | Legacy shared-table compatibility, safe per-AZ route/endpoint semantics and address migration remain OPEN | Current VPC/tests plus approved R0 strategy; reviewed moves/ownership/plan | Grouping approved by user; implementation requires network/state reviewer approval |
| D02 — OPEN | Post-R4 root/state integration | Dedicated network root versus larger root; manifest/config service/direct state outputs | Interface stability, output leakage, orchestration/lifecycle and no shared writer | [S5–S7], minimal publication schema/access/freshness and downstream change contract | State/security/consumer owners |
| D03 — OPEN | Post-R4 VPC/root integration | Actual subnet/AZ/IP allocation | Enabled AZs, nonoverlap, EKS control-plane/node/Pod/IP surge and service quotas; no chosen CIDRs here | [S1], account-specific authorized allocation/capacity evidence | Network/IP allocation and platform owners |
| D04 — OPEN | Post-R4 VPC features | NAT mapping and endpoint/egress service matrix | Same-AZ STG/PROD routing, explicit DEV cross-AZ trade-offs, endpoint DNS/SG/policy/cost dependencies | [S2–S4], actual caller/network flow requirements | Network/security/cost owners |
| D05 — OPEN | Post-R4 VPC/root integration | SG rule ownership, NACL policy and NetworkPolicy roles | Stateless return paths versus stateful rules, default resources un-hardened today, avoid false isolation | [S3], reviewed flow/port/direction and controller enforcement requirements | Network/security/platform owners |
| D06 — OPEN | R1–R4 / later identity roots | Workload account and deployment/operational identity custodians | No management-account workloads, no assumed account or unrestricted trust | [S8], external account ownership/SCP/session/boundary and separation evidence | Account/identity/security owners |
| D07 — OPEN | Post-R4 root/state integration | Protected DEV local state; STG/PROD remote backend candidates | Locking/encryption/access/backups/recovery/migration; one authoritative owner/writer | [S5–S7], backend capability/security and restore/cutover design | State custodian and security/operations reviewers |
| D08 — OPEN | Post-R4 VPC / later EKS/ingress | Exact provider/resource compatibility and version policy | Existing pins/locks unchanged; no assumed private EKS/VPC Link/NLB/controller behavior | Pinned provider schema, relevant AWS docs and reviewed mock contract; runtime behavior separately evidenced | Module/platform reviewers |
| D09 — OPEN | R1–R4 / later ingress | Scoped trust, PassRole and Kubernetes controller rights | Exact principals/SA/RBAC/resource scopes; prevent controller/Terraform double ownership | [S8], effective trust/permission matrix and least-privilege resource/action references | IAM/security/platform owners |
| D10 — OPEN | Later ingress | NLB/TargetGroupBinding feasibility and cross-zone/health behavior | Terraform infrastructure versus Pod registration, TCP:443 passthrough, Gateway mTLS; no ALB substitution | Current AWS NLB/VPC Link and controller documentation/provider evidence in relevant PR | Ingress/platform/security reviewers |
| D11 — OPEN | Post-R4 VPC / later EKS | Capacity and costs | Safe DEV mesh/system fit; surviving-AZ STG/PROD peak CPU/memory/Pods/IP/DB capacity; no fixed workers/replicas guarantee | [S1–S4], explicit peak/overhead model, endpoint/NAT/service pricing and budget assumptions | Platform/network/cost owners |
| D12 — OPEN | Post-R4 roots / any later Live | Teardown and scenario compatibility | Cumulative actual JPY 10,000, complete removal within 72 hours; all exercise-created managed/external resources tracked | [Readiness G01–G07](dev-live-validation-readiness.md), approved scope/estimate/inventory/state reconciliation and teardown evidence | Account/state/security/cost/operations approvers |

No conflict with the approved target was established from the source/reference
review. The shared-table compatibility conflict remains a future technical decision
within approved vpc ownership,
not permission to weaken existing VPC assertions. The historical Secrets Manager
30-day recovery remains a blocker for 72-hour complete deletion if created
unchanged; do not fix it silently or authorize the full unchanged MVP for Live.
All Live scenarios need separate G01–G07 approval, actual cumulative spending at
most JPY 10,000, verified complete teardown within 72 hours from approved start,
no retained exercise-created AWS resources generating ongoing charges, resource
inventory/state reconciliation and approved external audit evidence. Delayed
historical billing is not proof a resource remains. Never delete pre-existing
shared resources. STG/PROD completion requires offline evidence only.

## Technical references and limits

The following official pages were consulted for consequential findings. They are
service/design references, not actual account verification or finalized settings.

- **S1:** [EKS VPC/subnet requirements](https://docs.aws.amazon.com/eks/latest/userguide/network-reqs.html): cluster subnets span at least two AZs and require sufficient address headroom; one active DEV worker AZ is not a one-subnet cluster.
- **S2:** [NAT Gateway basics](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-basics.html): NAT is AZ-local; review AZ-local routing/failure and costs, and NAT does not accept SG attachment.
- **S3:** [Interface endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html): one selected subnet per AZ for endpoint ENIs; private DNS requires VPC DNS support/hostnames; policies and SGs remain explicit.
- **S4:** [Private EKS clusters](https://docs.aws.amazon.com/eks/latest/userguide/private-clusters.html): private API endpoint access and private node/workload service connectivity are separate; derive endpoints from actual callers.
- **S5:** [Terraform local backend](https://developer.hashicorp.com/terraform/language/backend/local): local filesystem state and OS-level locking do not coordinate independently copied state.
- **S6:** [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking): locking depends on backend support; do not assume every remote backend supports it.
- **S7:** [Terraform remote-state data](https://developer.hashicorp.com/terraform/language/state/remote-state-data): output consumers require full snapshot access; explicit publication to another location can reduce exposure.
- **S8:** [IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html): federation/temporary credentials, MFA and least privilege are identity design requirements, not proof that an account/principal exists.

No AWS credentials, authenticated APIs/plans, state operations, imports, apply,
destroy, deployment, code/test fixtures or resources are introduced here. Source
and documentation checks only; unchanged full regression runs in GitHub Actions.
