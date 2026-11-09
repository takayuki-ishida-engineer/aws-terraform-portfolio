# DEV network foundation — candidate V2

This is a usable Terraform root with required deployment inputs and credential-free
mock evidence. It has not been deployed or approved for AWS/Live execution. It does
not connect the independent serverless-api root or implement EKS/STG/PROD.
**V1-C01 acceptance is still required before this PR merges.**

## Ownership and configuration

Root owns the fixed ca-central-1 AWS provider, allowed_account_ids guard, local
backend, environment selection and the committed dependency lock. It calls exactly
one coherent [VPC child](../../../../modules/vpc/README.md), module.network; it owns
no additional resource outside that child. One network state/custodian/writer must
be approved externally before deployment. No resources may be double-managed or
imported without separate state/ownership approval. STG/PROD remote backends remain
OPEN and unimplemented.

| Input | Type / default | Requirement |
| --- | --- | --- |
| aws_account_id | string, required | Exactly 12 digits; separately approve a dedicated non-management workload account. Syntax/account guard is not evidence that an account exists or is authorized |
| name_prefix | string, required | Approved operational naming; child validates 1–63 conservative characters |
| vpc_cidr | string, required | Approved canonical IPv4 /16–/28; no allocation chosen in production source |
| private_subnets | map(object({cidr_block=string, availability_zone=string})), required | Nonempty, stable keys and validated contained/nonoverlapping subnets |
| public_subnets | Same object map, required nonempty | Explicit NAT hosting public subnet allocation; automatic public IP assignment stays false |
| active_workload_az | string, required | One configured private ca-central-1 AZ; real enabled AZ/quota support must be verified externally |
| nat | object({public_subnet_key_by_nat_az=map(string), nat_az_by_private_az=map(string)}), required | Exactly one NAT in the active workload AZ and an explicit same-AZ route for it; every additional cross-AZ consumer is visible in the map |
| gateway_endpoints | Child S3 map/object contract, default {} | Only actual reviewed S3 traffic, selected private AZ tables and explicit read-only endpoint policy; no enabled endpoint by default |
| tags | map(string), default {} | Root-owned Environment/Service/Project/ManagedBy and child Name take precedence |

| Effective configuration source | Values |
| --- | --- |
| Root Override | per_az mode; required naming/account/subnet/AZ/NAT inputs; expected_scope aws/ca-central-1/required account; root tags Environment=dev, Service=network, Project=aws-terraform-portfolio, ManagedBy=Terraform |
| Module Default | No S3 endpoint when gateway_endpoints is omitted; caller tags empty |
| Module Fixed | DNS support/hostnames true, IPv6/automatic public IPs false; retained legacy empty table, per-AZ selected tables, zonal/public NAT, explicit NAT-only private defaults and IGW public default |
| Root Fixed | Local backend, Terraform ~>1.17.0, AWS ~>6.72.0, lock selects 6.72.0; no provider credential or assume-role configuration |

A complete **non-secret** separately reviewed DEV input file can assign all seven
required inputs and optional tags/gateway_endpoints. Terraform accepts a reviewed
`-var-file=/approved/path/dev.network.tfvars` or JSON equivalent in the future
separately authorized workflow. The repository intentionally supplies no operational
CIDRs, account IDs, EIPs, enabled-AZ assumptions or operational names. Do not put
credentials or secret values in that file. Local tfvars remain ignored; do not
force-add environment configuration. Synthetic complete fixtures in
[tests](tests/network.tftest.hcl) are mock-only, not approved deployment allocation.

## Routing and actual resource inventory

Every private subnet selects its actual AZ table. Multiple keys in an AZ share
that table. Unmapped extra AZs have no NAT default; every egress-requiring platform
flow must be reviewed explicitly. Additional DEV cross-AZ sharing needs recorded
cost/failure approval; its presence in an input map does not grant that approval.
Future STG/PROD roots must enforce same-AZ NAT per active workload AZ and sufficient
surviving capacity; the child intentionally does not infer environment policy.

With n private subnets, m public subnets, a distinct private AZs, r explicitly
mapped private AZs and e selected S3 endpoint (0/1), this root has
**6+2(n+m)+a+r+e** managed resources:

| Child address template (module.network prefix) | Count / ownership |
| --- | --- |
| aws_vpc.this | 1 |
| aws_subnet.private[key] / aws_subnet.public[key] | n / m |
| aws_internet_gateway.this[0] | 1 |
| aws_route_table.private | 1 retained compatibility table, unused by per-AZ subnets |
| aws_route_table.public[0] | 1, inline IGW IPv4 default |
| aws_route_table_association.private[key] / public[key] | n / m; actual selected subnet/table IDs |
| aws_route_table.private_by_az[AZ] | a; no inline route owner |
| aws_eip.nat[active AZ] / aws_nat_gateway.this[active AZ] | 1 each; actual allocation/subnet references; fixed zonal/public |
| aws_route.private_nat[private AZ] | r; actual NAT target, explicit IPv4 default |
| aws_vpc_endpoint.gateway["s3"] | e; exclusive explicit table associations and reviewed policy |

Mock fixtures observe 17 resources for the two-private/two-public-AZ foundation,
18 with an explicit second-AZ shared NAT route, and 18 with the selected S3 endpoint.
These are fixture inventories, not fixed deployed sizing. No interface endpoints,
security groups, custom NACL, NetworkPolicy, NLB, EKS or application resources exist
in this root. Workload isolation and real reachability need separately approved
controls/evidence. EKS control-plane subnets still need AWS multi-AZ/IP requirements
before any future platform work, regardless of the single active DEV worker AZ.

## Candidate output interface

The single network output is a non-secret object of actual resource-backed fields:

- interface_version=1, routing_mode=per_az and root scope
  (environment/partition/Region/account expectation; not authentication).
- vpc_id, vpc_cidr, private_subnet_ids, public_subnet_ids, subnet_azs.
- private_route_table_ids_by_az, private_route_table_ids_by_subnet,
  public_route_table_id, internet_gateway_id.
- nat_gateway_ids_by_az, nat_eips_by_az (allocation_id/public_ip), endpoint_ids.gateway.
- private_route_table_id=null — **candidate V1-C01**, not automatic acceptance.

Actual VPC ARN/ID has a child postcondition matching expected account/Region.
Legacy callers retain the old singular ID and all original resource addresses.
No current serverless root interfaces or R1/R2 moves change. No real state migration
is verified. Existing users need an authorized external plan and reviewed routing
cutover before opting in; creation mocks do not prove no replacement/disruption.

Output publication/access/freshness/versioning/custodian decisions stay OPEN.
This root does not publish a manifest, create a configuration service or consume
terraform_remote_state. Giving a consumer state access can expose the whole
snapshot, not merely outputs. Protect local state/plans/identity metadata; never
commit them or use a shared state writer.

## Offline checks and future operational boundary

After init with the committed readonly lock, run fmt/validate and the native suite:
10 passes (four complete positive integration plans, six intentional input
rejections), plus seven independently failed missing-required-input processes and three
Root-to-child security-input rejection processes (NAT AZ, Region, endpoint policy).
The shared [actual-plan checker](../../../../modules/vpc/tests/check_network_configuration.py)
verifies complete resources, bindings, policy, outputs and fixed security settings;
34 semantic mutations, 22 capture faults and eight source/reference/account/backend mutations
must be detected. The fourth positive case substitutes distinct computed IDs to
verify real resource/output references. Required-input failures and partial rejected plans are not
successful network topologies. Test identity/CIDR/IP fixtures are synthetic.

GitHub Actions initializes this root plus the existing root and eight children:
ten configurations sharing one locked AWS binary. Full existing Terraform/Python/
IAM/guardrail regressions remain mandatory; aggregate native expectation is 541
(491 baseline - 16 old VPC + 56 VPC + 10 network). The existing 153 Python toolkit
tests are unchanged; mutations and the ten rejected-input processes are separate.
Counts describe the reviewed test contract; completed exact-HEAD CI is reviewed
independently and is not claimed here.

Future deployment still needs real account/identity, IP/AZ/service/quota allocation,
state protection/backups/writer ownership, approved S3 policy/traffic, NAT/EIP/
cross-AZ pricing and workload capacity, input-file review and authenticated external
plan review. No AWS credentials or authenticated AWS plan/state/deployment is allowed
in Codex Cloud. Public-path readiness dependencies order NAT creation; associations
wait for routes/endpoint lists. Real cutover/rollback and complete teardown ordering
must still be reviewed externally. NAT must delete before EIP release; inventory
routes, endpoint routes/ENIs and the retained shared table, not just billed NATs.

All G01–G07 remain OPEN. DEV Live requires separate authorization, maximum cumulative
actual JPY 10,000, complete testing and verified cleanup within 72 hours and no
retained charge-generating exercise resources. Secret 30-day recovery remains an
unresolved full-teardown blocker. This PR creates no AWS resource or Live evidence.
