# V1 — VPC extension contract and compatibility decision proposal

## Status, authority and evidence

**PROPOSED — independent V1 approval required before V2 implementation.** This
PR changes documentation only. The user independently accepted R0–R4 at main
`899f944c3887fa739dfb39f43617321a696c727b`; matching [push CI 42628851626](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42628851626)
completed successfully (491 native / 153 Python, including 16 VPC cases).
Those are existing baseline results, not tests of this proposal.

At that time (historical), Master Policy v11 (2026-11-09) was the user-approved external operating policy. Its
PDF is unavailable here; this proposal uses the decisions supplied with V1 and
accessible source, without claiming complete PDF review or inventing contents.
One coherent `infra/modules/vpc/` remains the owner; no NAT/core/routing/endpoint
wrapper modules. Roots own providers, account guards, backends and environment
selection. Actual accounts, CIDRs, AZ allocations, deployment/state and Live remain
OPEN. References [A1]–[A7]/[H1]–[H2] describe service/language behavior; [P1]–[P8]
are pinned **v6.72.0** provider evidence, not latest-provider assumptions.

## 1. Verified existing contract

Source: [resources](../infra/modules/vpc/main.tf), [inputs](../infra/modules/vpc/variables.tf),
[outputs](../infra/modules/vpc/outputs.tf), [versions](../infra/modules/vpc/versions.tf),
[README](../infra/modules/vpc/README.md), [native tests](../infra/modules/vpc/tests/vpc.tftest.hcl).

| Existing input | Current contract to retain when extensions are omitted |
| --- | --- |
| name_prefix | Required non-null string; 1–63 conservative name characters, alphanumeric first |
| vpc_cidr | Required non-null canonical IPv4 /16–/28 |
| private_subnets | Required nonempty map of stable key → {cidr_block, availability_zone}; nonblank keys, canonical IPv4 /16–/28 and AZ-name syntax |
| public_subnets | Same map/object contract, default {}; empty omits the public path |
| tags | Non-null map(string), default {}; module-owned Name tags take precedence |

VPC preconditions enforce containment/nonoverlap, not allocation approval. DNS
support/hostnames are true; generated IPv6 and automatic subnet public IPv4/IPv6
assignment are false. One shared private table has `route = []`. Public subnets
select one IGW, one public table with one inline IPv4 default route to that IGW,
and keyed associations. Public naming does not assign public IPs or prove access.
AWS supplies the implicit local route; an empty managed route list is not isolation.

There are eight resource declaration blocks with keyed/count instances, seven
outputs, and no NAT/EIP/endpoints/SG/custom ACL/EKS. The module has no provider or
backend. No Terraform service root calls it; README examples are not consumers.
The DEV serverless workload remains independent and outside this VPC.

The library permits Terraform >=1.17.0,<2 and AWS >=6.72.0,<7. The executing
[DEV root versions](../infra/services/dev/ca-central-1/serverless-api/versions.tf)
are narrower (~>1.17.0/~>6.72.0), its [committed lock](../infra/services/dev/ca-central-1/serverless-api/.terraform.lock.hcl)
selects 6.72.0, and [CI](../.github/workflows/terraform-offline-ci.yml) installs
Terraform 1.17.0. V1 changes none of these. New schema support does not prove
availability, quotas or permissions in an actual account/Region.

## 2. Routing alternatives and selected recommendation

| Alternative | Address / association consequences | Singular output / trade-off | Disposition |
| --- | --- | --- | --- |
| A. Legacy shared default; explicit per-AZ overlay; retain legacy table | Existing addresses stay, including unindexed aws_route_table.private. Add private_by_az; existing keyed private associations select an AZ table only after opt-in | The retained legacy table is no longer the active shared table in per-AZ mode. Recommend null singular output there, requiring explicit compatibility approval | **Preferred**, conditional on V1-C01 below; no automatic resource removal |
| B. Fully AZ-key the existing private table in all modes | Singleton → map is an address change even for old callers. One old table can map to one explicitly chosen AZ only; additional AZs require new tables. Private associations rebind | No truthful singular shared-table ID for multiple AZs; old 16-case default contract changes | Reject as default: unnecessary baseline migration and output break |
| C. Shared-table NAT using inline routes | Can retain table and association addresses, but changes shared table from no internet default to one NAT default; no per-AZ path for STG/PROD | Violates the old no-internet-route meaning despite retaining the ID; shared failure/cross-AZ domain | Reject for NAT: not a solution to the output or resilience contract |
| D. Gateway-endpoint-only extension on the legacy shared table | Technically feasible without table/association moves: pinned provider excludes AWS-managed endpoint routes from inline route state [P2] | Shared-table output can remain meaningful; endpoint association affects every subnet using that shared table, not a selected AZ | Compatible alternative for an endpoint-only first increment; not selected for the initial unified per-AZ extension contract |

Recommendation A preserves **exact old behavior by default**, then introduces a
clearly selected routing layout. Retain the legacy table unchanged even when
unused; it remains Terraform-owned and must be inventoried/deleted during any
approved complete network teardown. Its later removal requires separate breaking
migration approval. Do not repurpose it as a hidden NAT table or select a
lexicographically first AZ for the old output.

**Compatibility exception V1-C01 — OPEN for explicit approval:** in per-AZ mode,
`private_route_table_id` becomes null. Keeping its old physical ID would misleadingly
identify an unused compatibility table as the active private routing table.
Default legacy mode retains the original ID and semantics exactly. Callers opting
in must migrate to the new maps and accept nullable singular output; no consumer
is migrated automatically. If this exception is rejected, do not implement per-AZ
mode or silently retain a misleading output; return for contract review. The
endpoint-only alternative D remains a possible separately approved narrower path.

Multiple private subnet keys in one AZ share that AZ's new table. Reordering map
entries does not change identity. Adding an AZ adds its table and explicitly
selected NAT/routes; removing it removes those instances only after consumers,
associations, endpoint subnets and EIPs are reconciled. A subnet key rename needs
explicit old→new subnet **and** association mappings if preserving the same object;
changing actual AZ/CIDR can replace the subnet [P7] and cannot be made safe by a
moved declaration. AZ changes/renames affect dependent NAT, routes and endpoints.
No allocation or key-rename operation is authorized here.

## 3. Preferred typed input contract (proposed, not implemented)

Keep the five existing inputs. Add the following structured selectors; these are
type notation and candidate defaults, not Terraform implementation:

```text
private_routing: object({
  mode: optional(string, legacy_shared)  # legacy_shared | per_az
  nat: optional(object({
    public_subnet_key_by_nat_az: map(string)
    nat_az_by_private_az: map(string)
  }), null)
}) = { mode: legacy_shared, nat: null }

expected_scope: object({ partition: string, region: string, account_id: string }) = null

gateway_endpoints: map(object({
  private_route_table_azs: set(string)
  policy_json: string
})) = {}                                  # keys limited to s3 / dynamodb

interface_endpoints: map(object({
  private_subnet_key_by_az: map(string)
  client_security_group_ids: map(string)  # stable client key -> approved SG reference
  policy_json: string
})) = {}                                  # approved service catalog only
```

- No requested extension means legacy_shared, nat=null, both endpoint maps empty:
  no NAT/EIP/endpoint/new table/default route; public path and all seven outputs
  unchanged. Do not infer egress from public subnet existence.
- per_az creates tables for distinct private subnet AZs; nat=null creates **no**
  NAT/EIP/default route. A non-null NAT object must have nonempty gateway and target
  maps, no unused NAT entries, and refer only to existing private/public AZs/keys.
  Legacy_shared plus NAT or endpoints is rejected in the preferred first contract;
  alternative D is not implicitly enabled. Empty NAT objects are rejected rather
  than treated as a second disabled spelling.
- Every NAT AZ selects exactly one actual public subnet key in that same AZ. Two
  public subnets in one AZ are allowed; selection is explicit. Reusing one public
  subnet across mismatched AZ keys, missing public subnets/IGW, missing gateway
  targets or conflicting keys is rejected. No implicit first-subnet fallback.
- `nat_az_by_private_az` explicitly selects which private AZ tables receive a NAT
  default. An omitted private AZ stays without an internet default; consumers must
  not mistake that for connectivity. Root must cover every approved egress-requiring
  workload/control-plane flow. Multiple private keys in an AZ cannot request
  different default NATs under this AZ-table contract.
- Enabling any extension requires non-null expected_scope. It is caller metadata,
  not authenticated identity: root pins Region and allowed_account_ids; a proposed
  actual VPC ARN/ID postcondition checks matching scope. Do not override the root
  provider Region on child resources. Enabled AZ/service membership and permissions
  require separate authorized external evidence. Legacy callers gain no new scope
  restriction when all extensions are omitted.
- Initial endpoint service-name construction/catalog is for the approved commercial
  ca-central-1 target. Partition-specific naming and service availability elsewhere
  require D08 approval; do not silently change legacy support or claim GovCloud/
  China feature verification. Wrong service/type/Region and unsupported catalog
  entries fail validation before planning usable connectivity.

Environment differences are **Root Override**, not child environment flags. DEV
root selects one public zonal NAT and one active workload AZ. Additional required
AZ subnets may remain isolated or use an explicitly reviewed cross-AZ target.
STG/PROD roots select one NAT per active workload AZ (nominally two) and require
each active AZ's default route to its own AZ NAT. Child permits an explicit DEV
cross-AZ mapping, but a mapping is not proof of approval: STG/PROD root checks must
reject cross-AZ egress, and DEV review records its cost/failure acceptance. No
boolean merely asserts that an unsafe configuration is approved.

## 4. Complete resource address and route ownership proposal

Addresses below are **module-relative templates**. K/P are the existing quoted
private/public subnet keys; AZ is an approved AZ identity; S/C are stable service/
client keys. No real allocation, account or operational AWS name is selected.
A future root supplies the module-instance prefix.

| Existing address | Preferred future address | Default / opted-in behavior |
| --- | --- | --- |
| aws_vpc.this | unchanged | Same settings; optional scope postcondition is verification, not a new VPC |
| aws_subnet.private[K] | unchanged | Same keys/CIDRs/AZs and IP defaults |
| aws_subnet.public[P] | unchanged | Same optional public path and keys |
| aws_internet_gateway.this[0] | unchanged | Still exists iff public_subnets is nonempty |
| aws_route_table.private | unchanged | Retained route=[] compatibility table; active shared table only in legacy mode |
| aws_route_table.public[0] | unchanged | Same inline IGW default; no standalone route owner on this table |
| aws_route_table_association.private[K] | unchanged | Same subnet_id; route_table_id switches to private_by_az[private_subnets[K].availability_zone].id only after opt-in |
| aws_route_table_association.public[P] | unchanged | Same public subnet and shared public table references |

| Proposed new address | Instances / sole owner |
| --- | --- |
| aws_route_table.private_by_az[AZ] | One per distinct private AZ in per_az; **omit route argument**, no inline blocks/route=[] |
| aws_eip.nat[AZ] | One per requested NAT AZ; domain=vpc; module owns allocation and release |
| aws_nat_gateway.this[AZ] | One per requested NAT AZ; actual EIP allocation ID/public subnet ID, fixed public + zonal |
| aws_route.private_nat[AZ] | One per explicit private-AZ target; destination 0.0.0.0/0, actual NAT via nat_gateway_id and actual AZ table ID |
| aws_vpc_endpoint.gateway[S] | Requested s3/dynamodb only; owns its explicit route_table_ids list |
| aws_vpc_endpoint.interface[S] | Requested approved service only; owns subnet_ids/security_group_ids and private_dns_enabled=true |
| aws_security_group.endpoint[S] | Dedicated endpoint ENI SG in actual VPC; not workload/node/Pod or NAT SG |
| aws_vpc_security_group_ingress_rule.endpoint_https[S/C] | One tcp:443 source-SG reference rule per approved client; keys must prevent separator collisions |

No existing resource address needs a moved block under A. Association changes are
**configuration updates**, not address moves: 6.72.0 marks subnet_id ForceNew, but
not route_table_id; its Update calls ReplaceRouteTableAssociation and records the
new association ID [P3]. Therefore a table-only change is expected to plan update,
with AWS association ID potentially changing. This does not promise zero disruption
or rule out replacement for other changes. V2 must inspect actual plan actions.

Alternative B would require one explicit singleton→chosen-AZ moved declaration
for an existing table, never one→many or variable-generated moved blocks [H1].
Without actual approved AZ/state identity, no concrete destination can be selected.
Never infer that a source move guarantees live preservation.

Route ownership rules [P2], [A3]:

1. Legacy private table keeps route=[]; public table keeps its inline IGW default.
   No aws_route resources manage either table in the preferred contract.
2. New AZ tables omit route configuration; standalone aws_route.private_nat is the
   only ordinary IPv4 default-route owner. Omission ignores other existing routes;
   it is **not** a claim that drift/unmanaged routes cannot exist. Review actual
   route inventories externally before Live and on changes. Do not mix inline and
   standalone routes on a table, or use gateway_id for a NAT target.
3. Gateway endpoints own their route_table_ids inline; do not also create standalone
   endpoint-route-table association resources for the same endpoint/table pair.
   AWS creates/removes service-prefix-list routes. No aws_route duplicates them.
   The pinned route-table flattener skips implicit local, propagated and gateway-
   endpoint routes [P2]; route=[] does not delete AWS's implicit local route.
   This supports alternative D, rather than proving it inherently incompatible.
4. Interface endpoints own subnet/SG association lists inline; no duplicate
   standalone association owner. Workload/controller roots do not edit these routes
   or lists. Future routes/removals require the same exclusive network-state writer.

The NAT references actual EIP and public subnet. Explicit readiness must also wait
for IGW attachment, public table and public associations: subnet_id alone does not
order that whole public path. NAT defaults depend on actual NAT/AZ-table references;
private association cutover must wait for the requested defaults and gateway
endpoint associations (endpoint resource owns the list). Use legal static collection
references for dependencies, not unsupported dynamic each.value expressions in
depends_on. Validate no dependency cycle; source/configuration dependency checks
supplement actual full-resource plans, not replace them.

## 5. Zonal NAT, regional NAT and operations

6.72.0 supports availability_mode=zonal/regional. Its schema makes availability_mode,
allocation_id and subnet_id replacement-triggering [P1]. Explicitly select **zonal**
and public for this proposal; use aws_eip.nat[AZ].id, not a public-IP string, as
allocation_id. Private NAT and regional NAT are not selectable features here.

Regional NAT can expand AZ coverage and EIPs automatically, does not require a
hosting public subnet, and has a different vpc_id/address/managed-route-table model
[A2], [P1]. Manual/automatic regional configuration transitions can force recreation.
It is **not** the approved one-public-NAT-per-active-AZ model and is not adopted
merely because the pinned provider supports it. A material change needs new approval.

AWS zonal NAT is redundant inside its AZ, not resilient to losing that AZ; shared
cross-AZ consumers lose that egress on failure [A1]. NAT has no attachable SG.
Model quotas, connections/ports/throughput, public-subnet IP availability and
remaining-AZ workload capacity; counts alone prove no availability percentage,
RTO or RPO. Public subnet/IGW existence is necessary, not proof of usable egress.

Create reviewed public path/EIPs/NATs and route targets before association cutover.
A new NAT or changed source EIP can disrupt sessions/allowlists. Before removing
an AZ/NAT/endpoint, migrate/quiesce consumers, review routes and endpoint lists,
then remove routes/associations before dependent NAT/EIP/subnet/IGW deletion as
appropriate. Removing endpoints can change DNS/paths and break active connections.
NAT deletion must complete before EIP release; preserve provider waiters, review
failures/inventory and do not orphan allocations. Mode rollback restores reviewed
legacy associations before deleting AZ tables. No automatic instant or atomic
cutover/rollback guarantee; staged authenticated plans outside Codex are required.

## 6. Endpoint requirements and ownership

All endpoint maps default empty. This is a **candidate service matrix**, not an
enabled endpoint list. Root supplies an approved caller→service→DNS→route→SG/NACL→
policy flow and cost justification before each service is implemented/selected.

| Candidate / actual prospective consumer | Type, routing and DNS | Policy / SG / availability / cost and limits |
| --- | --- | --- |
| S3: future private workloads or EKS/ECR layer downloads | Gateway; selected actual private AZ tables; AWS regional S3 prefix route, normal service DNS; no interface Private DNS/SG | Explicit reviewed endpoint policy plus caller IAM/bucket policy. No additional gateway-endpoint charge [A3]; service/transfer/request costs still reviewed. Avoids NAT for matching regional S3 traffic only |
| DynamoDB: only if a real approved workload uses it | Gateway; same explicit route-table selection; no SG or interface Private DNS | Not a current dependency; leave absent. Explicit table/action scope and consumer need required. Not connectivity for any unrelated service |
| ECR API + DKR: future private image pulls | Two interface services where selected; S3 layer connectivity is a separate requirement | One chosen private subnet per AZ per endpoint, endpoint SG tcp:443 from approved source SGs, Private DNS and required IAM; endpoints do not upload/deploy images by themselves |
| STS/EC2/Logs/Secrets Manager: only actual token, controller, telemetry or reference-reading traffic | Separate interface services if supported/needed; not supplied by an S3 gateway endpoint | Runtime identity, regional DNS behavior, service endpoint-policy support and least-privilege permissions reviewed separately; no speculative future write privileges |
| SSM control/data services: only the reviewed private management/developer-access flow | Review actual agent/version/Region dependencies, e.g. SSM/ssmmessages and any additional required service | No blanket all-service bundle; source identity, NAT alternative, agent evidence, SG/NACL and operational custodian review. No developer-access EC2 implemented here |

Gateway endpoint association routes are AWS-managed and more specific than an
internet default for the same regional service [A3]; they do not replace every NAT
flow, regional service, endpoint policy or IAM grant. Selected AZ sets must be
nonempty/subsets of current AZ tables, without implicit all-table attachment.

Interface endpoints select exactly one private subnet per chosen AZ, even if the
VPC has several private subnets there [A4]. Reject a key/AZ mismatch, missing subnet,
public subnet selection or duplicate AZ. Existing VPC DNS settings satisfy the
baseline hostname/resolution prerequisite; Private DNS is fixed true for the
initial reviewed standard-service catalog. Custom DNS, service exceptions and
S3-interface/inbound-resolver combinations require separate design review.

The coherent VPC module owns endpoint ENI SGs and dedicated standalone ingress
rules, without mixed inline SG rules [P6], [P8]. Clients' workload SGs/egress remain
owned by their workload/platform boundary. No world CIDR, all-protocol rule or
fallback to the default SG. Provider documentation removes AWS's default allow-all
egress on new SG creation; provision no endpoint-initiated egress rules. This is
not an ongoing unmanaged-rule audit. Stateful replies and actual node/Pod source
identity need flow verification; SGs are not Kubernetes identity/authorization.

policy_json is explicit, parsed/reviewed non-secret policy input, never an implicit
full-access default. Gateway and some interface services support endpoint policies
[P4]; services without the proposed policy/Private DNS contract must remain outside
the initial catalog until an explicit alternative control is reviewed. Endpoint
policy does not grant identity permissions or prove effective authorization. No
real principal/resource policy is chosen here. Service/Region/type mismatches and
unreviewed service names are rejected; live availability remains external evidence.

Endpoint ENIs consume IPs and may incur per-AZ recurring/data-processing charges;
requests, logging and cross-AZ flows can add costs. They can reduce selected NAT
traffic, not guarantee a cheaper total. DNS/association teardown precedes subnet/SG
removal and must reconcile residual ENIs with inventory; no endpoint left billed.

## 7. Outputs and future network root

| Existing output | Legacy behavior | Preferred per-AZ behavior |
| --- | --- | --- |
| vpc_id / vpc_cidr | Actual VPC ID/CIDR | Unchanged |
| private_subnet_ids / public_subnet_ids | Same stable-key maps, public {} when absent | Unchanged key/ID semantics |
| private_route_table_id | Actual shared table ID with no configured internet route | **null only after V1-C01 approval**; consumers must use selected-table maps |
| public_route_table_id | Actual shared public table ID or null | Unchanged |
| internet_gateway_id | Actual IGW ID or null | Unchanged |

Do not declare that all seven outputs remain fully compatible in opted-in mode:
there is one explicitly proposed exception. Six retain meanings in both modes;
all seven retain exact baseline behavior when extensions are omitted.

Proposed additions read actual resources, not constructed IDs:

| Output | Proposed shape / interpretation |
| --- | --- |
| subnet_azs | object({private=map(string), public=map(string)}), keyed like existing subnet IDs |
| private_route_table_ids_by_az | map(string) of active table IDs; legacy can repeat the shared ID for several AZ keys, per_az has one table per AZ |
| private_route_table_ids_by_subnet | map(string) keyed by every private subnet; actual selected table |
| nat_gateway_ids_by_az | map(string), {} when nat=null |
| nat_eips_by_az | map(object({allocation_id=string, public_ip=string})), actual references; {} disabled |
| endpoint_ids | object({gateway=map(string), interface=map(string)}), only requested endpoints |
| routing_mode / interface_version | Selected layout / proposed first published schema version 1; old seven-output interface was unversioned |

Outputs infer Terraform types; consumers should normalize map-shaped values
explicitly. The publication schema/version above remains a proposal. No secret,
private key, policy document or whole-state output. IDs/public IPs are operational
metadata, not automatically public information.

A separate future `infra/services/<env>/ca-central-1/network/` root is recommended
for one authoritative network state/writer and independent lifecycle. It is not
created by V1. DEV local state protection/custodian and STG/PROD remote backend
choice, locks/encryption/backups/restore/access/migration remain D02/D07 OPEN.
Workload/platform roots consume approved minimal values, never write network state.

| Distribution candidate | Assessment / approval needed |
| --- | --- |
| Minimal versioned manifest | Preferred candidate: approved env/Region/account/partition, schema/version, actual required IDs/AZs/routing metadata only; publication/access, freshness/integrity, release/rollback and custodians still OPEN |
| Approved configuration service | Can separate output reads from full state but adds IAM/service/connectivity/consistency/cost/teardown ownership; no service selected |
| terraform_remote_state | Not default: access can expose the entire state snapshot, not merely outputs [H2]; explicit security/backend/consumer acceptance required |

Environment/account/Region scope belongs to the root's versioned envelope and
verified provider, not an environment-specific VPC child or a mere echoed identity
claim. Publish only fields consumers need; EIP references are not automatically
included. Review dependency ordering, stale/wrong-scope rejection, interface
changes, consumer migration and foundation teardown before choosing distribution.

## 8. Security, IP capacity, pricing and Live boundaries

Private routes are not a workload firewall: VPC-local communication remains.
Review workload SG egress, stateless NACL request/return paths and Kubernetes
NetworkPolicy enforcement separately; no SG on NAT and no automatic NACL/mesh/SG
hardening is inferred. D05 must assign every rule/flow to one owner; keep default
SG/ACL/main-table limitations visible. Wrong-VPC tables, NATs, endpoint services,
route targets, broadened policies and public association mistakes require rejection.

EKS cluster subnets must span at least two AZs even with one active DEV worker AZ.
AWS specifies at least six available IPs per cluster subnet and recommends at least
16 [A5]; these are service requirements/recommendations, **not selected subnet
sizes**. Allocate for AWS reservations, control-plane ENIs/upgrades, nodes/Pod CNI
and warm pools, endpoint ENIs, ingress/DB dependencies and surge/headroom. Review
AZ support/IDs-to-account-name mapping, quotas and surviving-AZ peak capacity for
STG/PROD. No concrete CIDRs, AZ allocation or worker/replica counts are fixed here.

Cost review must include zonal NAT hours per selected AZ, NAT processed data,
public IPv4/EIP charges [A6]–[A7], internet/service and cross-AZ transfer; interface endpoint
hours per endpoint/AZ and processed data; other workload/service and teardown
costs. Gateway endpoints have no additional endpoint charge [A3], not free S3/
DynamoDB usage. Obtain current ca-central-1 pricing, tax/FX and contingency before
selection; no rate or total is invented here. DEV's single NAT reduces one cost
component but concentrates failure/cross-AZ exposure. STG/PROD per-AZ NAT does not
by itself establish sufficient surviving workload capacity or end-to-end HA.

All G01–G07 remain OPEN. Future DEV Live requires separately approved scope and
actual cumulative cost <=JPY 10,000 plus verified complete teardown within 72
hours, including NAT/EIPs/endpoint ENIs/SGs/routes and any retained compatibility
table created for the exercise. Do not retain charge-generating exercise resources.
No 72-hour cost guarantee; secret 30-day recovery remains an unresolved complete-
deletion blocker. No AWS credentials/account APIs, real plans/state/imports,
apply/destroy, deployment, publication or Live test is performed by V1.

## 9. Concrete V2 verification contract — not executed by V1

Preserve these exact existing native case names and assertions, unchanged in
baseline mode; their real CIDR/AZ fixtures are tests, not approved allocations:

| Existing case | Preserved purpose |
| --- | --- |
| private_only | Exact private inventory, shared empty table, no public resources, IP/DNS/tags/seven outputs |
| public_and_private | Two-AZ keyed resources, IGW-only public default, associations, actual outputs |
| stable_keys_and_defaults | Stable map identity despite declaration/AZ ordering; private-only defaults |
| invalid_name_prefix | Naming rejection |
| invalid_vpc_cidr | Malformed IPv4 rejection |
| ipv6_vpc_rejected | Unsupported VPC IPv6 rejection |
| invalid_vpc_prefix | Out-of-range VPC prefix rejection |
| empty_private_subnets | Nonempty private requirement |
| invalid_private_cidr | Private CIDR rejection |
| invalid_public_cidr | Public CIDR rejection |
| empty_private_availability_zone | Missing private AZ rejection |
| invalid_public_availability_zone | Malformed public AZ rejection |
| empty_private_key | Blank identity rejection |
| subnet_outside_vpc | Containment rejection |
| subnet_broader_than_vpc | Broader subnet rejection |
| overlapping_private_and_public | Cross-map overlap rejection |

Add named cases / independent actual-plan expectations in the relevant V2 PR:

| New family | Positive, negative and mutation obligations |
| --- | --- |
| legacy_unchanged / public_unchanged | Compare all old resource addresses/settings/actions and seven outputs; no NAT/EIP/endpoint even with public subnets unless requested |
| per_az_isolated / nat_disabled | New AZ tables, no inline managed routes/NAT/EIP/defaults; same-AZ multiple private keys share a table; old table retained, explicit null singular contract/new maps |
| dev_one_nat / dev_shared_nat_explicit | One actual zonal/public NAT+EIP; actual public subnet/AZ/IGW path; every requested AZ route uses declared NAT, cross-AZ only explicitly mapped/reviewed |
| stg_prod_same_az / capacity_contract | Per-active-AZ NAT, routes target own AZ; root rejects cross-AZ/omitted active-AZ mapping. Offline capacity assumptions, not measured failover |
| missing_public / missing_nat_az / conflicting_mapping | Reject absent public path, nonexistent keys, foreign AZ, reused/conflicting subnet selection, empty/unused gateways, invalid mode/scope, multiple target attempts; unverified enabled AZs stay externally OPEN |
| wrong_route / wrong_association | Mutate NAT target to another AZ, IGW, invented/wrong-VPC ID; swap private/public table or subnet; reject broad/default routes on legacy/private-isolated tables and unexpected replacement actions |
| endpoint_disabled / gateway_enabled | Empty maps create none; S3 selected actual AZ tables/policy only; DynamoDB requires explicit reviewed use; no standalone duplicate service-prefix route or association owner |
| interface_enabled / endpoint_invalid | Actual VPC/subnet/SG references, one subnet per AZ, Private DNS, tcp:443 scoped client rules; reject wrong service/Region/type/AZ, default/world SG, unreviewed policy, unmanaged association duplication |
| address_output_compatibility | Exact old addresses; no surprise delete/create/replace; all provider-backed IDs/maps, defaults, scope/version and singular output behavior. Reorder/add/remove/rename/rollback scenarios and malformed output rejection |
| routing_security_mutations | Wrong AZ/VPC target, missing IGW readiness, public IP enabled, private table default to IGW, competing inline+standalone route, gateway-prefix spoof, broadened endpoint policy/SG, missing protection of baseline assertions |
| evidence_failure_injections | Nonzero process, failed/error/skipped cases, missing/duplicate runs/plans/resources/outputs, unknown/null critical fields, unexpected resource/type/provider, malformed/duplicate-key/nonfinite JSON, incomplete file/summary/dependency evidence |

Native tests use mock providers and plan only; inspect the complete actual resource
inventory, configurations/references, route targets, output types/values and action
sets. Intentionally rejected partial plans require reviewed per-case shapes and
validation reasons; never count them as complete topologies. Distinct deterministic
computed IDs must expose swapped references. Require actual-plan mutation witnesses,
not checksums/count-only or source substrings. Graph/configuration/source dependency
assertions supplement full plans; mocks cannot prove routing, atomic cutover,
provider identity, enabled AZs, endpoint policy enforcement or effective AWS access.

V2 must retain all existing Terraform/Python/IAM/security checks and update genuine
case totals/CI summaries from execution, not delete/skip/weaken the 16 VPC cases.
Run affected local fmt/init/validate/native/actual-plan/negative/mutation checks and
complete independent GitHub Actions regression on each implementation PR.

## 10. Approval register and staged handoff

Every recommendation above remains **PROPOSED**, not an implemented or approved
selection. Coherent VPC ownership and environment NAT cardinality are already
approved; the following decisions remain OPEN before their implementation:

| Foundation ID | Concrete V1 recommendation / evidence | Approval still needed |
| --- | --- | --- |
| D01 / V1-C01 | A: retain legacy table/address/defaults, explicit AZ overlay, null singular output only in opted-in mode; [P2]/[P3]/[H1] | Explicit output compatibility exception, resource names/addresses/input semantics, association cutover and real-user/state inventory; no silent consumer change |
| D02 | Separate network root and minimal versioned manifest candidate; [H2] | Root/state ownership, publication service/schema/version/access/freshness, consumers and lifecycle ordering |
| D03 | Stable existing keys plus AZ table identity, no allocation examples | Actual subnet/AZ/IP assignments, account mapping, enabled zones, EKS/endpoint/upgrade headroom and quotas |
| D04 | Public zonal NAT map, explicit DEV sharing versus STG/PROD same-AZ, endpoint service matrix | Exact active/egress AZs, public subnet choice, cross-AZ acceptance, service policies and route removal plan |
| D05 | VPC owns endpoint SG/rules; workloads own client SG/egress; separate NACL/NetworkPolicy roles | Actual flow/source identity, rule/policy ownership and drift evidence; no implicit network isolation claim |
| D07 | DEV local state; separately approved STG/PROD remote state | Custodian/writer, locks/encryption/backups/access/recovery/cutover; no backend chosen |
| D08 | 6.72.0 schema/source supports proposed zonal NAT, endpoint and association forms; regional NAT excluded | V2 exact schema/config validation/mocks, service/partition/Region catalog and provider compatibility; any pin/model change separately approved |
| D11 | Review NAT/EIP/cross-AZ/endpoint cost and remaining-AZ IP/compute/service capacity | Actual traffic/peak assumptions, pricing/FX/contingency and capacity model; no fixed size/cost selected |
| D12 | Dependency-ordered teardown includes EIPs/endpoints and legacy table | Approved scenario/estimate/inventory/complete-deletion evidence; G01–G07 and secret-recovery blocker remain OPEN |

D06 account/deployment identity and D09 controller/PassRole responsibilities also
remain prerequisites where applicable; V1 does not create IAM policies or select
principals. Regional NAT, IPv6, new workload/controller/EKS integration and custom
endpoint DNS/policy exceptions need their own approvals, not feature creep here.

Recommended sequence: approve V1-C01 and input/address contracts first; then a
focused V2 child-module per-AZ/zonal-NAT implementation with retained legacy tests
and actual-plan checker. Endpoint additions can follow as independently reviewed
increments inside the same VPC module once D04/D05/D08 service evidence is ready.
Network root/publication integration is a separate D02/D07 approval. Do not create
any of these PRs/resources as part of V1. A passing documentation CI does not grant
implementation, route migration, NAT/EIP creation, endpoint deployment or AWS access.

## Official references inspected for V1

Public documentation and pinned HashiCorp source were retrieved read-only. No
account API discovery or schema from a newer provider is substituted.

- [A1] [AWS NAT gateway connectivity](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html) and [zonal NAT basics, AZ failure and no SG](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-basics.html).
- [A2] [AWS regional NAT gateway](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateways-regional.html).
- [A3] [Gateway endpoints: S3/DynamoDB, managed routes, longest prefix and pricing](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html).
- [A4] [Interface endpoints: one subnet per AZ, DNS, SG and policies](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html).
- [A5] [EKS VPC/subnet requirements](https://docs.aws.amazon.com/eks/latest/userguide/network-reqs.html).
- [A6] [AWS NAT hourly/data processing pricing and cross-AZ considerations](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html).
- [A7] [AWS Elastic IP/public IPv4 pricing and explicit release](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html).
- [P1] [NAT 6.72.0 resource documentation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/nat_gateway.html.markdown), [actual schema/validation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_nat_gateway.go), [EIP arguments](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/eip.html.markdown).
- [P2] [Route table 6.72.0 ownership/omission semantics](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/route_table.html.markdown), [flattenRoutes local/endpoint exclusions](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_route_table.go), [standalone routes](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/route.html.markdown).
- [P3] [Association 6.72.0 schema/update/ID behavior](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_route_table_association.go).
- [P4] [Endpoint 6.72.0 arguments and association ownership warnings](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/vpc_endpoint.html.markdown), [actual schema](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_endpoint.go).
- [P5] [Standalone endpoint association alternative](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/vpc_endpoint_route_table_association.html.markdown).
- [P6] [Security group 6.72.0 standalone-rule guidance and default egress removal](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/security_group.html.markdown).
- [P7] [Subnet 6.72.0 AZ/CIDR replacement schema](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_subnet.go).
- [P8] [Scoped SG ingress-rule 6.72.0 attributes](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/vpc_security_group_ingress_rule.html.markdown).
- [H1] [HashiCorp resource/module address refactoring](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring).
- [H2] [HashiCorp remote-state full-snapshot access warning](https://developer.hashicorp.com/terraform/language/state/remote-state-data).
