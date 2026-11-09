# Architecture v2 foundation design — Network / State / Identity

This is an implementation-readiness proposal, not implementation or execution
approval. Master Policy v10 (2026-11-08), reproduced in
[Architecture v2](architecture-v2.md), remains authoritative. All recommendations
and decision-register entries below are **OPEN**. No account, CIDR, AZ allocation,
operational resource name, backend or principal is selected. All G01–G07 Live gates
remain OPEN. Do not create the future PRs described here during this task.

Evidence baseline: main `7876bdbf6cef7f1cb171521352e69a43cc14113e` and successful
[post-merge offline CI 42569910881](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42569910881).
The [verification policy](portfolio-verification-policy.md),
[readiness gates](dev-live-validation-readiness.md),
[bootstrap proposal](dev-bootstrap-decision-plan.md) and
[technical history](../infra/README.md) retain their existing authority/evidence.
Mocks never establish actual AWS reachability, ownership, permission or availability.

## A. Current implementation inventory

| Source evidence | Implemented contract | Missing / limitation |
| --- | --- | --- |
| [VPC resources](../infra/modules/vpc/main.tf) | IPv4 VPC with DNS support/hostnames; keyed private/public subnets and associations; no automatic public IPv4/IPv6 assignment | No NAT/EIP, endpoints, per-AZ private routing, SG/custom ACL hardening or EKS integration |
| Same VPC source | One shared private route table with route=[]; optional IGW and one public table/IGW default route only when public subnet map is nonempty | Private route table has no configured internet path; implicit AWS VPC-local routing is not isolation enforcement. AWS-created default SG/ACL/main table are not hardened |
| [VPC inputs](../infra/modules/vpc/variables.tf), [outputs](../infra/modules/vpc/outputs.tf), [README](../infra/modules/vpc/README.md) | Required prefix/VPC CIDR/nonempty keyed private subnets; empty public map default; canonical IPv4/range/containment/nonoverlap and AZ syntax validation; actual VPC/subnet/table/IGW references | Syntax does not prove enabled AZs, account/Region membership, quotas or available IPs. Shared private_route_table_id is a singular compatibility contract, not per-AZ output |
| [VPC native tests](../infra/modules/vpc/tests/vpc.tftest.hcl) | 16 historical mocked plan runs: private defaults, public/private routing/associations, stable keys, tags, outputs and input/precondition rejection | These tests do not verify NAT, endpoints, new topology or live network behavior; no new test results claimed here |
| [DEV root](../infra/services/dev/ca-central-1/serverless-api/main.tf) | dev / ca-central-1 / serverless-api; nine reusable modules repository-wide, seven workload instances and 17 resource definitions | Root does not call VPC; Lambda remains outside a VPC. Historical HTTP API MVP stays independent from REST/NLB/Istio target |
| [Provider](../infra/services/dev/ca-central-1/serverless-api/providers.tf), [backend](../infra/services/dev/ca-central-1/serverless-api/backend.tf), [versions](../infra/services/dev/ca-central-1/serverless-api/versions.tf) | Root AWS provider, fixed workload Region, allowed_account_ids=[var.aws_account_id], default tags; local state; Terraform ~>1.17.0 / AWS ~>6.72.0 and committed root lock | No live account verified. STG/PROD roots/backend operation are not implemented; remote-state selection remains OPEN |
| [Offline workflow](../.github/workflows/terraform-offline-ci.yml), historical acceptance | Complete suite retains 384 Terraform native and 153 Python tests, IAM reference/equivalence/negative/mutation/independent guardrails and fail-closed evidence checks | Historical counts are neither future coverage nor a ceiling. Root 12 rejected inputs/35 mutations/22 capture faults and HTTP API 17 mutations/19 faults are separate evidence categories |

## B. Network ownership and composition

### Candidate ownership map

The future networking root should compose resources; child modules should own
implementation/defaults/validation/outputs, with no providers/backends inside them.
No shared mutable resource may have two Terraform owners or competing reconcilers.
Candidate custom NACLs/rules belong to the network root under D05 approval;
workload SGs belong to their consuming root, with each rule owned once. Do not
mix inline and standalone management of the same rules or routes.

| Resource / interface | Proposed sole owner | Dependency / exclusion |
| --- | --- | --- |
| VPC, keyed subnet identities, optional IGW and public route tables/associations | Network foundation core within one environment/Region network root | Stable keys and actual references; no public IP assignment by default; no speculative toggles |
| NAT Gateways and their EIPs | Small public-NAT module in that same root | Approved public subnet/IGW path and AZ mapping; owns no subnet associations or route tables; no security group can attach to a NAT gateway [S2] |
| Private per-AZ route tables, routes and subnet associations | Private-routing owner in network root | Consume actual subnet/NAT references; only this owner changes private associations/routes; no inline/standalone route conflict |
| Interface/gateway VPC endpoints and endpoint policy/SG/association contracts | Scoped endpoint owner in network root, with reviewed service-specific authorization | Explicit endpoint requirements, DNS and account/Region/subnet scope. One owner per SG rule/route association; no competing endpoint route-table association mechanisms |
| EKS cluster/node network requirements | EKS root consumes approved network outputs; cluster-specific SGs owned there | No ownership of foundation subnets/routes. Review control-plane ENIs, node/Pod addressing, private API access, capacity and connectivity before integration |
| Internal NLB, TCP:443 listener, target groups and ingress-specific SG/network resources | Future ingress root's Terraform | Consume approved network/EKS references. No ALB target or TLS termination at NLB; Gateway performs backend mTLS |
| Gateway Pod registration | Kubernetes-side controller, separate from Terraform target-group infrastructure | TargetGroupBinding/Pod IP/health/controller permissions and NLB compatibility OPEN; no independently controller-created duplicate load balancer |
| Workload SGs / RBAC / NetworkPolicy | Owning EKS/application/platform boundary with explicit rule ownership | Least-privilege ingress/egress; default-deny policies where appropriate; network encryption is not identity authorization |
| Cross-root dependency | Approved immutable network interface plus external orchestration | Consumers read references without becoming state writers; no implicit cross-root depends_on or cycle |

Routing owns explicit routes; an approved gateway-endpoint association may add
AWS-managed service-prefix routes. The endpoint/routing contract must distinguish
those from explicit routes and avoid authoritative inline route collections that
would remove them. This interaction requires D04 review before implementation.

### Two feasible module approaches

| Approach | Advantage | Migration/dependency impact | Testing consequence |
| --- | --- | --- | --- |
| Extend existing VPC carefully | Reuses established subnet validation and source; one internal routing owner | Preserve private-only defaults, stable keyed addresses, existing shared-table output and all current tests. Per-AZ routing is not a trivial additive switch: requires reviewed new input/output semantics and safe association/address migration for existing consumers | Keep all 16 runs; add per-AZ/NAT/endpoint actual-plan, negative and unsafe-route/ownership mutation coverage. Explicitly verify legacy calls remain identical; do not weaken old shared-table assertions |
| Distinct modules at real ownership boundaries | Keeps historical VPC untouched; NAT, v2 core, private routing and endpoints can be independently reviewed/tested | A new core must deliberately omit private tables/associations owned by routing module. Reusing old VPC alongside another private-routing owner is not safe. Avoid duplicate helper wrappers/stacks with no resource responsibility | Each module needs precise resource inventory/output/ownership tests and later composition tests; duplicated validation must be justified and kept consistent, not a generic framework |

**Recommendation (D01 OPEN):** separate NAT first, then a narrowly scoped v2 network
core/private-routing/endpoint decomposition if reviewers accept the ownership split.
Retain legacy VPC unchanged for its historical contract. If extension is chosen
instead, rescope the core/routing roadmap before coding, retaining a single route
owner and compatible legacy behavior. Do not bolt standalone NAT routes onto the
existing route=[] table or reassign subnets owned by existing associations: inline
route enforcement and competing association owners would conflict. No speculative
feature flag or stack layer is proposed. Root selection is explicit composition.

## C. Proposed root and state boundaries

Evaluate a dedicated network-service root at
`infra/services/<env>/<region>/<service>/`, separate from application/EKS/ingress
roots. The network service slug and exact root split are not assigned. This can
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

## F. Dependency and implementation sequence — proposed future PRs

D01–D12 below must be resolved where applicable before their implementation. Each
PR is separately authorized, focused and independently reviewed. Proposed new
module names are code-scope candidates, not operational AWS resource names. No
backend, IAM or infrastructure is created by this design. All listed Terraform
work is **credential-free offline only**; none authorizes Live operations.

1. **F1 — smallest useful Terraform PR: standalone public NAT/EIP module.**
   Proposed scope: `infra/modules/nat_gateway/` implementation/README/native and
   focused actual-plan/mutation tests, plus only its necessary offline CI step.
   Own exactly an EIP and public NAT Gateway per caller-selected stable map key;
   own no VPC/subnet/IGW/routes/associations/SG/root. Required approved public-subnet
   references and explicit AZ/scope metadata; outputs actual keyed NAT/EIP IDs.
   Root eventually selects one DEV or two STG/PROD instances, not an env-aware
   feature flag. No resource is deployed or existing VPC called. Depends on D01,
   D03–D04/D08/D11 schema/cost decisions, not EKS or backend implementation.
   Tests: one/two configured NAT pairs, stable keys and actual references; malformed/
   missing/duplicate input rejection; public NAT/EIP scope and mapping mutations;
   exact inventory/no routes/no data sources/no secret/provider configuration.
   Mock tests cannot prove a supplied subnet's real VPC/AZ/public/IGW path; root
   composition and later authorized evidence must establish that. CI preserves
   all existing suites and adds the affected module checks only, including reviewed
   extension of locked shared-cache/storage topology assertions for the new
   initialized configuration; never remove those checks. Report actual new test
   counts rather than inventing them. Full regression
   remains GitHub's responsibility. No IAM/PassRole grant belongs in this module.
2. **F2 — core network ownership, after D01 choice.**
   If separate modules are approved: proposed `infra/modules/network_core/` owns
   VPC, keyed subnets, optional approved IGW/public tables/associations, explicitly
   no private tables/associations. Inputs approved CIDR/AZ/subnet/key/tag maps;
   outputs actual VPC/subnet/IGW/public-route references plus scope metadata.
   Otherwise submit a narrowly reviewed compatible extension to existing VPC,
   with explicit association/address migration proposal before changing ownership.
   Depends on approved D01/D03/D05/D08. Tests: private-only/public cases, CIDR/AZ/
   overlap boundaries, stable outputs/IP/DNS defaults, public-exposure and unexpected
   private-association mutations. Preserve old 16 tests unchanged. CI adds core
   checks and reruns affected VPC checks only where changed; no service root yet.
3. **F3 — private per-AZ routing composition.**
   Proposed `infra/modules/private_routing/` owns private tables/routes/associations
   exclusively; actual subnet/NAT/IGW readiness references from F1/F2. Inputs
   explicit approved subnet→AZ→NAT mapping; outputs keyed actual table IDs and
   association scope. Depends on F1/F2 and D01/D03/D04. Test DEV mapping and STG/PROD
   AZ locality, subnet/table dependency and no IGW default for private subnets;
   reject missing/ambiguous/cross-scope maps and detect cross-AZ STG/PROD NAT,
   unintended public routes, duplicate ownership and inline/standalone conflicts.
   CI adds actual composition/negative/mutation verification; no endpoint/EKS work.
4. **F4 — reviewed endpoint and network-security boundary.**
   Proposed scoped endpoint module under `infra/modules/` (name approved in D04)
   and its tests; no catch-all feature flags. Inputs approved service/caller/DNS/
   subnet/table/SG/policy references, outputs actual endpoint identities/interfaces.
   Depends on F2/F3 and D04–D05/D08. Tests distinguish gateway/interface contracts,
   endpoint association ownership, scoped policies/SGs/DNS and missing connectivity;
   exposure/unrestricted-policy/duplicate-association mutations fail closed. CI
   adds affected policy/security/reference checks; no arbitrary future IAM grants.
5. **F5 — root/state/output interface integration.**
   Proposed approved network roots under `infra/services/<env>/<region>/<service>/`
   and contract tests/documentation; existing serverless-api root remains untouched
   unless separately approved migration. Inputs approved env/account/Region/IP/AZ
   allocation and F1–F4 interfaces; outputs versioned minimum actual network scope.
   Depends on D02/D03/D06–D08/D11–D12, F1–F4 and approved backend design. Review DEV
   state protection separately from STG/PROD remote-backend implementation; split
   remote backend resources/migration into their own PR if needed, never hide them
   here. Tests env NAT count/routing, provider guards, no credentials/shared writers,
   stale/wrong-scope interfaces and lifecycle/ownership/dependency negatives/mutations.
   CI adds credential-free backend-disabled root checks and preserves historical
   root/lock tests. Backend operation, imports and state migration are not offline
   test results and require later external approval; no backend is selected here.
6. **F6 — identity boundary implementation, separately scoped.**
   Proposed least-privilege deployment/workload/controller role modules and their
   tests under `infra/modules/`, only after D06/D09 defines exact identities and
   actions. Inputs approved principal/SA/resource scope; outputs actual role refs,
   never keys/secrets. Can design in parallel with network, but IAM implementation
   depends on known consumers and D08 compatibility. Positive exact trust/permission
   plans; wrong subject/audience/account/service/PassRole-resource and escalation/
   secret-access negatives/mutations; independent actual-policy checks. CI extends
   IAM/reference checks proportionately, retaining every historical guardrail.

Only after these contracts, separately propose EKS networking and then NLB/Gateway
integration PRs. Candidate scopes are future EKS/ingress modules/roots plus required
controller interfaces, not this foundation implementation. Inputs are approved
network outputs and exact identity scopes; outputs cluster/target-group references.
D08–D12 must resolve private endpoint access, Pod addressing, TCP passthrough,
TargetGroupBinding/controller rights and health/cross-zone ownership first. Add
resource/dependency, IAM/RBAC, exposure/topology and wrong-owner/termination mutations;
CI remains offline. Kubernetes deployment, PKI, CloudFront pricing, Cognito certificate
authorization and API backend certificate implementation stay with their respective
PRs, not a simultaneous Network/State/Identity/EKS/ingress change.

## G. OPEN decision register

Every row is a proposal requiring owner/reviewer approval **before the affected
implementation**. Role labels below do not name actual assigned people or approvals.

| ID / status | Affected PR | Options / candidate | Security and operational implications | Evidence / official source needed | Required approval |
| --- | --- | --- | --- | --- | --- |
| D01 — OPEN | F1–F3 | Compatible VPC extension versus separate NAT/core/routing | Legacy shared-table contract and single association owner; migration/address stability | Current VPC source/tests; reviewed ownership map and no-competing-route plan | Network/state architecture reviewer |
| D02 — OPEN | F5 | Dedicated network root versus larger root; manifest/config service/direct state outputs | Interface stability, output leakage, orchestration/lifecycle and no shared writer | [S5–S7], minimal publication schema/access/freshness and downstream change contract | State/security/consumer owners |
| D03 — OPEN | F1–F5 | Actual subnet/AZ/IP allocation | Enabled AZs, nonoverlap, EKS control-plane/node/Pod/IP surge and service quotas; no chosen CIDRs here | [S1], account-specific authorized allocation/capacity evidence | Network/IP allocation and platform owners |
| D04 — OPEN | F1/F3/F4 | NAT mapping and endpoint/egress service matrix | Same-AZ STG/PROD routing, explicit DEV cross-AZ trade-offs, endpoint DNS/SG/policy/cost dependencies | [S2–S4], actual caller/network flow requirements | Network/security/cost owners |
| D05 — OPEN | F2/F4/F5 | SG rule ownership, NACL policy and NetworkPolicy roles | Stateless return paths versus stateful rules, default resources un-hardened today, avoid false isolation | [S3], reviewed flow/port/direction and controller enforcement requirements | Network/security/platform owners |
| D06 — OPEN | F5/F6 | Workload account and deployment/operational identity custodians | No management-account workloads, no assumed account or unrestricted trust | [S8], external account ownership/SCP/session/boundary and separation evidence | Account/identity/security owners |
| D07 — OPEN | F5 | Protected DEV local state; STG/PROD remote backend candidates | Locking/encryption/access/backups/recovery/migration; one authoritative owner/writer | [S5–S7], backend capability/security and restore/cutover design | State custodian and security/operations reviewers |
| D08 — OPEN | F1–F6 / later EKS/ingress | Exact provider/resource compatibility and version policy | Existing pins/locks unchanged; no assumed private EKS/VPC Link/NLB/controller behavior | Pinned provider schema, relevant AWS docs and reviewed mock contract; runtime behavior separately evidenced | Module/platform reviewers |
| D09 — OPEN | F6 / later ingress | Scoped trust, PassRole and Kubernetes controller rights | Exact principals/SA/RBAC/resource scopes; prevent controller/Terraform double ownership | [S8], effective trust/permission matrix and least-privilege resource/action references | IAM/security/platform owners |
| D10 — OPEN | Later ingress | NLB/TargetGroupBinding feasibility and cross-zone/health behavior | Terraform infrastructure versus Pod registration, TCP:443 passthrough, Gateway mTLS; no ALB substitution | Current AWS NLB/VPC Link and controller documentation/provider evidence in relevant PR | Ingress/platform/security reviewers |
| D11 — OPEN | F1–F6 / later EKS | Capacity and costs | Safe DEV mesh/system fit; surviving-AZ STG/PROD peak CPU/memory/Pods/IP/DB capacity; no fixed workers/replicas guarantee | [S1–S4], explicit peak/overhead model, endpoint/NAT/service pricing and budget assumptions | Platform/network/cost owners |
| D12 — OPEN | F5 / any later Live | Teardown and scenario compatibility | Cumulative actual JPY 10,000, complete removal within 72 hours; all exercise-created managed/external resources tracked | [Readiness G01–G07](dev-live-validation-readiness.md), approved scope/estimate/inventory/state reconciliation and teardown evidence | Account/state/security/cost/operations approvers |

No conflict with the approved target was established from the source/reference
review. The shared-table composition conflict is a future ownership decision,
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
