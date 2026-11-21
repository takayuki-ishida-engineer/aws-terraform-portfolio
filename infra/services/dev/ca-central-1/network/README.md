# DEV network foundation — candidate V2

This is a usable Terraform root with required deployment inputs and credential-free
mock evidence. It has not been deployed or approved for AWS/Live execution. It does
not connect the independent serverless-api root or implement EKS/STG/PROD.
**V1-C01 acceptance is still required before this PR merges.**

## Input values (Step 1 item 3)

Values follow the [deployment configuration](../../../../../docs/deployment-configuration.md#1-where-values-live). The committed
`terraform.tfvars` holds every required input; environment-specific inputs there
are documented placeholders. Copy `local.auto.tfvars.example` to the untracked
`local.auto.tfvars` and set the real values: `project` and `aws_account_id`. The
[local workflow](../../../../../scripts/local-workflow/README.md) preflight refuses a plan or apply while any of them is
missing locally or still a placeholder. Full CI plans this root with the committed
values under mocks. Never put a credential or secret value in any tfvars file.
State is local by default; for the optional S3 backend copy
`backend_override.tf.example` and `backend.s3.tfbackend.example` (both stay
untracked once copied) and run `run.py <root> migrate-state`.

| Committed value | Setting |
| --- | --- |
| VPC | `10.40.0.0/16`, `per_az` routing, active workload AZ `ca-central-1a` |
| Private subnets | `private1` `10.40.1.0/24` (a), `private2` `10.40.2.0/24` (b) |
| Public subnets | `public1` `10.40.10.0/24` (a), `public2` `10.40.11.0/24` (b) |
| NAT | One NAT gateway in `ca-central-1a` (`public1`) serving the active AZ |
| S3 gateway endpoint | Not enabled (`gateway_endpoints` omitted; Module Default). ECR image layers use presigned S3 URLs that the module's mandatory role-ARN endpoint policy would deny, so nodes reach S3 through the NAT gateway |
| Interface endpoints | `ec2`, `ecr.api`, `ecr.dkr`, `logs`, `sts` for EKS nodes (finding F16), `elasticloadbalancing` for the AWS Load Balancer Controller (finding F21) and `ssm`, `ssmmessages`, `ec2messages` for Session Manager on the developer access host (item 5): nine endpoints in `private1` (active AZ only), private DNS, AWS default endpoint policy, security group `<project>-dev-sg-vpce` allowing only TCP 443 from `10.40.0.0/16`; billed per endpoint-hour plus per GB |
| Shared private route table | Not created in `per_az` routing (finding F8) |

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
| project | string, required | Project token for names and the `project` tag; placeholder `project`. 1–10 lowercase letters, digits or `-`, starts with a letter, no `aws`, `amazon` or `cognito`. Names use `<project>-dev` |
| vpc_cidr | string, required | Approved canonical IPv4 /16–/28; no allocation chosen in production source |
| private_subnets | map(object({cidr_block=string, availability_zone=string})), required | Nonempty; keys `private1`, `private2`, ... (the tier number in names); validated contained/nonoverlapping subnets |
| public_subnets | Same object map, required nonempty | Keys `public1`, `public2`, ...; explicit NAT hosting public subnet allocation; automatic public IP assignment stays false |
| active_workload_az | string, required | One configured private ca-central-1 AZ; real enabled AZ/quota support must be verified externally |
| nat | object({public_subnet_key_by_nat_az=map(string), nat_az_by_private_az=map(string)}), required | Exactly one NAT in the active workload AZ and an explicit same-AZ route for it; every additional cross-AZ consumer is visible in the map |
| gateway_endpoints | Child S3 map/object contract, default {} | Only actual reviewed S3 traffic, selected private AZ tables and explicit read-only endpoint policy; no enabled endpoint by default |
| interface_endpoints | object({services=set(string), subnet_keys=set(string)}), default null | Forwarded to the child, which allows only `ec2`, `ec2messages`, `ecr.api`, `ecr.dkr`, `elasticloadbalancing`, `logs`, `ssm`, `ssmmessages` and `sts`, existing private subnet keys and at most one subnet per AZ, in per_az routing only |
| tags | map(string), default {} | Optional extra tags; must not set `project`, `env`, `service`, `managed` or `Name`, which provider `default_tags` and the child own |

| Effective configuration source | Values |
| --- | --- |
| Root Override | per_az mode; `name_prefix = <project>-dev`; required account/subnet/AZ/NAT inputs; committed `interface_endpoints` with the nine reviewed services in `private1` (child default `null`); expected_scope aws/ca-central-1/required account; provider `default_tags` project=`<project>`, env=dev, managed=terraform; child `tags` = caller extra tags only |
| Module Default | No S3 endpoint when gateway_endpoints is omitted; caller tags empty |
| Module Fixed | DNS support/hostnames true, IPv6/automatic public IPs false; interface endpoints with private DNS, the AWS default endpoint policy and the `<project>-dev-sg-vpce` group allowing only TCP 443 from the VPC CIDR; no shared private table in per_az routing (finding F8), per-AZ selected tables, zonal/public NAT, explicit NAT-only private defaults and IGW public default |
| Root Fixed | Local backend, Terraform ~>1.17.0, AWS ~>6.72.0, lock selects 6.72.0; no provider credential or assume-role configuration |

Input values follow the [deployment configuration](../../../../../docs/deployment-configuration.md#1-where-values-live):
a committed `terraform.tfvars` with placeholders and an untracked
`local.auto.tfvars` for real environment values (see [Input values](#input-values-step-1-item-3)). Names
and tags follow sections 4 and 5 of that document. Never put credentials or secret
values in any tfvars file. Synthetic complete fixtures in
[tests](tests/network.tftest.hcl) are mock-only, not approved deployment allocation.

The optional S3 Gateway policy requires `Principal="*"` with mandatory
`Condition.ArnEquals["aws:PrincipalArn"]` selecting literal approved IAM role ARNs
in the expected account (one string or a nonempty list). The child rejects an
unconditioned wildcard, Principal.AWS objects, empty conditions/roles, foreign or
wildcard roles, unsupported operators/keys and malformed policies. Read-only action,
bucket/object scope and action/resource checks remain enforced. See the
[full child contract](../../../../modules/vpc/README.md#v2-extension-contract--candidate-pending-independent-review)
and [official gateway requirements](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-access.html).
ArnEquals itself supports wildcards in AWS; the module bans them in role values.
Role sessions match their IAM role ARN, not the STS session ARN. This endpoint
filter does not replace identity/bucket policies or prove effective authorization.

## Routing and actual resource inventory

Every private subnet selects its actual AZ table. Multiple keys in an AZ share
that table. Unmapped extra AZs have no NAT default; every egress-requiring platform
flow must be reviewed explicitly. Additional DEV cross-AZ sharing needs recorded
cost/failure approval; its presence in an input map does not grant that approval.
Future STG/PROD roots must enforce same-AZ NAT per active workload AZ and sufficient
surviving capacity; the child intentionally does not infer environment policy.

With n private subnets, m public subnets, a distinct private AZs, r explicitly
mapped private AZs, e selected S3 endpoint (0/1) and i interface endpoints, this root
has **5+2(n+m)+a+r+e** managed resources, plus **2+i** when interface endpoints are
selected:

| Child address template (module.network prefix) | Count / ownership |
| --- | --- |
| aws_vpc.this | 1 |
| aws_subnet.private[key] / aws_subnet.public[key] | n / m |
| aws_internet_gateway.this[0] | 1 |
| aws_route_table.private[0] | 0 in per_az routing (finding F8) |
| aws_route_table.public[0] | 1, inline IGW IPv4 default |
| aws_route_table_association.private[key] / public[key] | n / m; actual selected subnet/table IDs |
| aws_route_table.private_by_az[AZ] | a; no inline route owner |
| aws_eip.nat[active AZ] / aws_nat_gateway.this[active AZ] | 1 each; actual allocation/subnet references; fixed zonal/public |
| aws_route.private_nat[private AZ] | r; actual NAT target, explicit IPv4 default |
| aws_vpc_endpoint.gateway["s3"] | e; exclusive explicit table associations and reviewed policy |
| aws_security_group.endpoints[0] / aws_vpc_security_group_ingress_rule.endpoints_https[0] | 1 each when interface endpoints are selected; TCP 443 from the VPC CIDR only |
| aws_vpc_endpoint.interface[service] | i; selected private subnets, the endpoint group, private DNS, AWS default policy |

Mock fixtures observe 16 resources for the two-private/two-public-AZ foundation,
17 with an explicit second-AZ shared NAT route, 17 with the selected S3 endpoint,
and 27 with the committed values (the foundation plus the endpoint group, its rule
and nine interface endpoints, finding F21). These are fixture inventories, not
fixed deployed sizing. Apart from the endpoint group, no security groups, custom NACL, NetworkPolicy, NLB, EKS or application resources exist
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
15 passes (six complete positive integration plans, including
`tests/committed.tftest.hcl`, which plans the committed `terraform.tfvars` without
setting any variable, and nine intentional input rejections), plus seven independently failed missing-required-input processes and seven
Root-to-child security-input rejection processes (NAT AZ/Region, broad S3 actions,
unconditioned wildcard, old Principal object, foreign role and IfExists condition).
The shared [actual-plan checker](../../../../modules/vpc/tests/check_network_configuration.py)
verifies complete resources, bindings, policy, outputs and fixed security settings;
84 semantic mutations (42 of them on the committed plan: private DNS, region,
subnet and security group for each of the nine interface endpoints, the endpoint
rule source, and the `elasticloadbalancing` endpoint's VPC, tags, presence and
record drift), 22 capture
faults and 14 source/reference/account/backend and committed-test mutations
must be detected. Independent policy-structure validation also detects 33 cases
where plan and fixture contain the same invalid policy. The fourth positive case substitutes distinct computed IDs to
verify real resource/output references. Required-input failures and partial rejected plans are not
successful network topologies. Test identity/CIDR/IP fixtures are synthetic.

GitHub Actions initializes this root plus the existing root and eight children:
ten configurations sharing one locked AWS binary. Full existing Terraform/Python/
IAM/guardrail regressions remain mandatory; aggregate native expectation is 560
(491 baseline - 16 old VPC + 75 VPC + 10 network). The existing 153 Python toolkit
tests are unchanged; mutations and the fourteen rejected-input processes are separate.
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
