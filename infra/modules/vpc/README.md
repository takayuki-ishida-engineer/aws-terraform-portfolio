# Reusable IPv4 VPC module

This child module implements one VPC with explicit, keyed private subnets and
optional public subnets. Its default posture is private-only, without internet
egress. The [DEV network root](../../services/dev/ca-central-1/network/README.md)
now opts into per-AZ zonal NAT routing; the existing serverless API root remains
independent. Evidence is credential-free mock configuration only, not deployment
or live reachability/authorization.

## Resources and routing

- One `aws_vpc.this`, with DNS support and hostnames enabled.
- `aws_subnet.private` and `aws_route_table_association.private`, keyed by the
  caller's `private_subnets` map. Legacy mode shares `aws_route_table.private`;
  opted-in mode selects the actual AZ table for every subnet.
- Only when `public_subnets` is nonempty: `aws_subnet.public` and its keyed
  associations, one `aws_internet_gateway.this[0]`, and one
  `aws_route_table.public[0]` with an inline `0.0.0.0/0` route to that gateway.

The private table explicitly configures no routes. AWS still supplies its implicit
VPC-local route; **legacy mode** adds no private default internet route or NAT path.
The original shared table remains unchanged and owned even when unused in per-AZ
mode. New AZ tables omit inline routes; standalone NAT defaults own their routes.
Public subnet classification means association with the IGW-routed table, not
automatic assignment of public IPs or guaranteed reachability for workloads.
Neither private nor public subnets automatically assign public IPv4 or IPv6.

Stable caller map keys identify subnet and association resources. Reordering map
entries or AZ declarations does not change their addresses. Renaming keys or
changing CIDRs/AZs can replace resources: review a real Terraform plan outside
Codex Cloud before changes to managed infrastructure.

## Inputs, defaults, and fixed settings

All five legacy inputs have non-null effective values. Required inputs reject null;
nullable=false defaulted public_subnets/tags use {} when omitted or explicitly
null. Subnet objects require both fields.

| Input | Type | Default | Validation / responsibility |
| --- | --- | --- | --- |
| `name_prefix` | `string` | Required | 1-63 letters, digits, `_` or `-`; first character alphanumeric |
| `vpc_cidr` | `string` | Required | Canonical IPv4 network CIDR, `/16` through `/28` |
| `private_subnets` | `map(object({ cidr_block = string, availability_zone = string }))` | Required | At least one entry; nonblank keys; canonical IPv4 `/16`-`/28`; explicit AZ name |
| `public_subnets` | Same map/object type | `{}` | Same entry validations; empty map omits all public networking |
| `tags` | `map(string)` | `{}` | Caller tags; module-owned `Name` wins on each taggable resource |

AZ names must match `^[a-z]{2}(-[a-z0-9]+)+-[0-9]+[a-z]$`. Empty, null, or malformed
AZ fields fail validation. This is a syntax check, not discovery or proof that a
zone exists, is enabled, or belongs to the root's provider region/account. AZ IDs
and Wavelength zone names are not supported by this interface.

CIDRs must use network addresses, without host bits. Resource preconditions reject
subnets outside the VPC, subnets broader than the VPC, and overlapping subnets
within or across both maps. Containment compares network bases at the VPC prefix;
overlap compares each pair at the shorter prefix. These use standard Terraform
`cidrhost`, `cidrnetmask`, and numeric prefix operations, without external tools.
Pairwise overlap checking is quadratic in subnet count and intended for ordinary
VPC-sized maps, not a general IP address management system.

| Configuration source | Settings / behavior |
| --- | --- |
| Root Override | The calling root supplies required naming/CIDR/private subnet inputs and may supply public subnets and caller tags |
| Module Default | `public_subnets = {}`, `tags = {}`, `private_routing = {mode="legacy_shared", nat=null}`, `expected_scope = null`, `gateway_endpoints = {}` |
| Module Fixed | DNS support/hostnames enabled; generated IPv6 disabled; subnet public IPv4 and IPv6 assignment disabled; one shared private table without configured routes; module-owned `Name` tags |

Public subnets select only the public/IGW path. The structured `private_routing`
selector and explicit endpoint map select genuine optional extensions; public
subnet existence never silently enables private internet egress.

Tag merging is `merge(var.tags, { Name = ... })`: arbitrary caller tags are
preserved, but callers cannot replace `Name`. Names are `<prefix>-vpc`,
`<prefix>-private-<key>`, `<prefix>-public-<key>`, `<prefix>-private-rt`,
`<prefix>-public-rt`, and `<prefix>-igw`. Associations have no tag support.
Provider default tags, if any, belong to the root; the module defines no provider.
Callers must keep final tag lengths within AWS limits, including long subnet keys.

## Outputs

| Output | Value type | Behavior |
| --- | --- | --- |
| `vpc_id` | `string` | Created VPC ID |
| `vpc_cidr` | `string` | VPC IPv4 CIDR |
| `private_subnet_ids` | Map-shaped object of strings | Private subnet IDs keyed by stable input keys |
| `public_subnet_ids` | Map-shaped object of strings | Public subnet IDs keyed by stable input keys; `{}` when omitted |
| `private_route_table_id` | `string` or `null` | Legacy shared ID; candidate null in per-AZ mode (V1-C01 needs acceptance before merge) |
| `public_route_table_id` | `string` or `null` | Public table ID; null when omitted |
| `internet_gateway_id` | `string` or `null` | IGW ID; null when omitted |

ID values come from resource references, not invented ARNs or IDs. Terraform
outputs infer their types; keyed objects are convertible to maps by callers.

## V2 extension contract — candidate pending independent review

**V1-C01 requires explicit acceptance before this PR merges.** Legacy mode retains
all seven original output meanings and the original 16 native tests byte-for-byte.
Opted-in per-AZ mode returns null for `private_route_table_id`: the old physical
table is retained but is not the active private routing table. Consumers must use
the new selected-table maps. This is a candidate exception, not already approved.
The [V1 decision](../../../docs/vpc-extension-decision.md) remains design provenance.

| New input | Type / default | Contract |
| --- | --- | --- |
| private_routing | object({mode=optional(string,"legacy_shared"), nat=optional(object({public_subnet_key_by_nat_az=map(string), nat_az_by_private_az=map(string)}))}); default {} | Mode legacy_shared/per_az. null NAT means no EIP/NAT/default, including per-AZ isolated mode. Non-null maps must both be nonempty |
| expected_scope | nullable object({partition=string, region=string, account_id=string}); default null | Required for per-AZ. Initial extension catalog is aws/ca-central-1; actual VPC ARN/ID must match. Legacy defaults gain no account/Region constraint |
| gateway_endpoints | map(object({private_route_table_azs=set(string), policy_json=string})); default {} | Only explicitly requested s3 is implemented; nonempty existing private AZ selection and reviewed scoped read-only policy |

NAT keys are real caller-supplied AZ names, not ordinal indexes. Every NAT AZ must
have an actual private AZ and a distinct same-AZ public subnet key. A private AZ
routes only when explicitly mapped to a declared NAT AZ; unmapped AZs remain
without an internet default. All declared NATs must have a consumer. Multiple
private subnet keys in one AZ share a table/default target. Missing keys, foreign
AZ syntax/Region, duplicated public selection and unused/missing NAT mappings fail.
There is no fallback public subnet, inferred AZ, regional/private NAT or IPv6 mode.
Actual enabled AZs, quotas/IP capacity and account authorization remain external.

Root owns environment differences: DEV uses one public NAT in its one active
workload AZ; any extra-AZ sharing is explicit and separately reviewed for cost and
failure exposure. Future STG/PROD roots must require one NAT per active AZ (nominally two) and
same-AZ routes; they are not implemented. A valid child cross-AZ mapping is not
STG/PROD approval. EKS cluster-subnet requirements are not implemented by this root.

| Resource address template | Sole ownership / dependency |
| --- | --- |
| Existing eight declaration addresses | VPC, keyed subnets, optional IGW/public table, shared private table and keyed associations retain their addresses. No moved declarations |
| aws_route_table.private_by_az[AZ] | Opt-in table per distinct private AZ; no inline route argument |
| aws_eip.nat[AZ] | Module-owned VPC-domain EIP per requested zonal NAT; release after NAT deletion |
| aws_nat_gateway.this[AZ] | Fixed zonal/public; actual EIP allocation and selected public subnet references; explicit IGW/public table/association readiness |
| aws_route.private_nat[private AZ] | Only explicitly mapped AZ defaults, actual NAT ID through nat_gateway_id; never gateway_id or invented IDs |
| aws_vpc_endpoint.gateway["s3"] | Explicit actual AZ-table association list and service/policy; no standalone endpoint association or service-prefix route owner |

There are thirteen resource declaration templates after extension (eight retained,
five new), not thirteen fixed instances. Legacy private-only with n private
subnets has 2+2n resources. With nonempty public subnets, per-AZ resource count is
4+2(n+m)+a+2g+r+e: private/public subnet counts n/m, private AZ count a, NAT count g,
explicit private NAT route count r, selected S3 endpoint count e (0/1).
NAT-disabled per-AZ omits g/r; no-public isolated mode replaces base 4 by 2.

Legacy private route=[] and public inline IGW default remain their sole route
owners. New tables omit inline route management and use standalone NAT defaults.
AWS owns implicit local and endpoint service-prefix routes; the endpoint owns its
inline route_table_ids only. Pinned 6.72.0 filters AWS-managed gateway routes from
route-table state. There are no interface endpoint bundles, endpoint SGs, SG/NACL
or Kubernetes NetworkPolicy rules. Routing alone does not enforce isolation.
Omitted inline routes also do not audit arbitrary out-of-band route drift.

S3 Gateway Endpoint policy follows the [AWS gateway Principal contract](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-access.html)
and [S3 gateway guidance](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html).
Every Allow statement requires `Principal = "*"` **and** exactly
`Condition.ArnEquals["aws:PrincipalArn"]`, containing one literal IAM role ARN or a
nonempty list of explicitly approved role ARNs. Every role must match
`expected_scope.account_id`; a list allows any of those approved roles, not every
role in the account. An unconditioned wildcard and the old `Principal.AWS` role
object are rejected. Missing/null/empty conditions or role values, cross-account
roles, STS session/user ARNs, extra operators/keys, ArnLike, negation, IfExists and
set operators are outside the supported contract. AWS supports additional forms;
this reviewed module deliberately accepts only this restrictive shape.

[AWS ARN operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html)
permit * and ? even with ArnEquals, so the literal role ARN pattern explicitly
rejects both and policy-variable expressions. The
[aws:PrincipalArn context](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html)
contains the IAM role ARN for role requests, not its STS assumed-role session ARN.
Unsigned requests lack that key and cannot satisfy this positive ArnEquals
condition. Role ARN conditions identify names/paths rather than pinning an IAM
principal's unique ID: role deletion/recreation and trust/lifecycle ownership
still require review.

Version 2012-10-17, a nonempty Statement array, supported read actions and scoped
bucket/object ARNs remain mandatory. ListBucket/GetBucketLocation use bucket ARNs;
GetObject/GetObjectVersion use object ARNs, optionally with a trailing prefix *.
No administrative/write/action/bucket wildcard, NotAction, NotResource or extra
policy/statement key is accepted. Never remove Condition to satisfy the mandatory
wildcard Principal. The endpoint policy does not override or replace IAM identity
or S3 bucket/resource policies; actual role/bucket ownership, service availability,
KMS requirements and effective authorization require external evidence. No secret
plaintext is consumed or live policy acceptance claimed.

Synthetic policy fragment (not an approved deployment identity/allocation):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": ["s3:GetObject"],
    "Resource": ["arn:aws:s3:::example-bucket/approved/*"],
    "Condition": {
      "ArnEquals": {
        "aws:PrincipalArn": "arn:aws:iam::000000000000:role/test-network-reader"
      }
    }
  }]
}
```

| Added output | Inferred Terraform shape / meaning |
| --- | --- |
| subnet_azs | object({private=map(string), public=map(string)}), actual resource AZs |
| private_route_table_ids_by_az | map(string), selected active table per AZ; repeated shared ID in legacy |
| private_route_table_ids_by_subnet | map(string), actual association target per stable key |
| nat_gateway_ids_by_az | map(string), actual IDs or {} |
| nat_eips_by_az | map(object({allocation_id=string, public_ip=string})), actual references or {} |
| endpoint_ids | object({gateway=map(string)}), enabled S3 only; no speculative interface field |
| routing_mode | string, selected mode |
| interface_version | number, candidate 1; not publication authorization |

A table-only association change retains the Terraform address and is expected to
update through ReplaceRouteTableAssociation; its AWS association ID can change.
Key/CIDR/AZ changes and NAT/EIP changes can replace objects. No moved declarations
are needed for the retained layout. Real-user/state inventories, staged authorized
external plans and explicit V1-C01 acceptance are necessary before routing changes;
mock creation plans do not establish real-state migration or zero disruption.
Rollback/removal must reconcile associations/routes/endpoints before dependent
tables/NATs/EIPs/subnets/IGW and inventory the retained compatibility table. Review
actual mixed update/destroy ordering externally; no atomic rollback is promised.

## Offline verification and operational limits

`tests/vpc.tftest.hcl` keeps all original 16 cases unchanged. `extension.tftest.hcl`
adds 59 cases: 12 positive configurations and 47 intended rejections. Together:
75 native passes, 15 complete positive plans and 60 rejected partial plans.
`tests/check_network_configuration.py` checks actual generated resource identities,
exact inventories, known critical route/subnet/NAT/endpoint bindings, output
contracts, policy fields and private IP/DNS defaults. Repeated provider schemas
are streamed away; resource plans, diagnostics and terminal evidence are retained.
Unknown provider-derived EC2 instance/ENI metadata is not a configured NAT target;
configured alternate targets and unknown critical IDs/route targets are rejected.

The checker rejects 36 actual-plan semantic mutations, 22 capture faults and eight
source reference/dependency/account/backend mutations. An independent Python policy
validator also rejects 33 matched-invalid-policy mutations per scope: both the
actual plan and input are deliberately poisoned identically, so equality cannot
mask an AWS-invalid or overbroad policy. Rejected-input plans must have their
specific failure diagnostics and exact reviewed partial-resource/output shapes;
they are never counted as complete networks. Source guards supplement actual
plan evidence. All original Terraform/Python/IAM/guardrail checks remain required
in GitHub Actions; no live connectivity, effective IAM or failover is proved.

Affected credential-free commands after init with the reviewed root lock:

```sh
cp ../../services/dev/ca-central-1/network/.terraform.lock.hcl .terraform.lock.hcl
terraform init -backend=false -input=false -no-color -lockfile=readonly
terraform validate -no-color
set -o pipefail
if terraform test -no-color -json -verbose | python3 tests/check_network_configuration.py --compact > /tmp/vpc-tests.jsonl; then
  test_status=0
else
  test_status=$?
fi
python3 tests/check_network_configuration.py --scope child --test-events /tmp/vpc-tests.jsonl --terraform-exit-code "$test_status" --self-test
```

Supply the actual process/pipeline failure code to the checker (CI does so), never
substitute 0 after a failed command. Do not run authenticated plans in Codex Cloud.
The VPC library still permits Terraform >=1.17.0,<2 / AWS >=6.72.0,<7; execution
uses Terraform 1.17.0 and root-locked AWS 6.72.0. NAT hours/data processing,
public IPv4/EIP and cross-AZ charges, S3 traffic costs, quotas, IP/surviving-AZ
capacity, account/state custodians and teardown approval remain OPEN.
G01–G07 remain OPEN; DEV Live requires separate approval, cumulative actual
JPY 10,000 maximum and complete verified cleanup within 72 hours. The 30-day
Secrets Manager recovery blocker remains unresolved. No Live/AWS/state work occurs.

## Example root configurations (not implemented integrations)

These are alternative examples for a root at
`infra/services/dev/ca-central-1/serverless-api/`. Neither call exists in that root.
The root must separately own provider authentication, region, account restrictions,
backend/state, and environment overrides. Never supply AWS credentials in Codex
Cloud. The explicit example AZs are caller choices, not module defaults.

Private-only example:

```hcl
module "network" {
  source      = "../../../../modules/vpc"
  name_prefix = "example-dev-network"
  vpc_cidr    = "10.40.0.0/16"
  private_subnets = {
    app-a = { cidr_block = "10.40.1.0/24", availability_zone = "ca-central-1a" }
    app-b = { cidr_block = "10.40.2.0/24", availability_zone = "ca-central-1b" }
  }
  tags = { Environment = "dev", Project = "example" }
}
```

Public and private example, as an alternative to the previous call:

```hcl
module "network" {
  source      = "../../../../modules/vpc"
  name_prefix = "example-dev-network"
  vpc_cidr    = "10.40.0.0/16"
  private_subnets = {
    app-a = { cidr_block = "10.40.1.0/24", availability_zone = "ca-central-1a" }
    app-b = { cidr_block = "10.40.2.0/24", availability_zone = "ca-central-1b" }
  }
  public_subnets = {
    web-a = { cidr_block = "10.40.10.0/24", availability_zone = "ca-central-1a" }
    web-b = { cidr_block = "10.40.11.0/24", availability_zone = "ca-central-1b" }
  }
  tags = { Environment = "dev", Project = "example" }
}
```

## Versions and verification

The module requires Terraform `>= 1.17.0, < 2.0.0` and declares `hashicorp/aws`
`>= 6.72.0, < 7.0.0`. This is compatible with the existing root's narrower
`~> 1.17.0` / `~> 6.72.0` constraints without pinning this library to a patch.
Tested: Terraform CLI 1.17.0 and HashiCorp-signed AWS Provider 6.72.0, Linux amd64.
Other versions in the allowed ranges have not been tested.

From an isolated shell with no AWS credentials or credential-bearing Terraform
inputs, use the required Terraform CLI:

```sh
cd infra/modules/vpc
terraform version
terraform fmt -check -recursive
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Initialization downloads provider schemas; it is not an AWS API call. Local
initialization may generate `.terraform.lock.hcl`; do not commit that child-module
lock file. Dependency locks belong to executing roots; the existing root lock
remains unchanged. Do not commit `.terraform/`, state, or plans.

The retained baseline checks passed. Native `tests/vpc.tftest.hcl` still has
**16 passing runs, zero
failures**. Every run explicitly uses `command = plan` and a mocked AWS provider.
Computed IDs alone are overridden at plan time with distinct test IDs; configured
CIDRs, AZs, routes and associations remain subject to the assertions.

Coverage includes private-only defaults, two-AZ public/private routing and all
associations, stable map-key identities, outputs, fixed IP/DNS settings and tag
precedence; expected failures cover invalid names, malformed/IPv6/oversized VPC
CIDRs, empty private maps, invalid private/public CIDRs, empty/invalid AZs, blank
keys, outside/broader-than-VPC subnets, and cross-map overlapping subnet ranges.

Validation processes excluded inherited AWS credential/profile and Terraform
variable bindings, directed shared AWS config/credential paths to `/dev/null`,
and disabled metadata lookup. No actual AWS `plan`, `apply`, `destroy`, API calls,
credentials, or deployments were used. Mock plan results are not live AWS integration
tests or proof of runtime readiness.

## Limitations and future integration

- No interface/DynamoDB endpoints, Flow Logs, IPv6, Transit Gateway,
  peering, cross-region networking, Route 53 private hosted zone, VPN, Direct
  Connect, Network Firewall, Security Group, custom Network ACL, or remote backend
  resources are implemented.
- Legacy and unmapped isolated private AZs have no internet default. Explicit
  opt-in NAT/S3 routing covers only selected paths, not unrelated service access.
  Public subnets do not automatically assign public IPv4.
- This is not complete production network hardening. AWS-created default security
  groups, default ACLs, and the VPC's main route table are not hardened here.
- AWS CIDR reservations, subnet/IP capacity, quotas, enabled AZs, actual region
  compatibility, routing reachability and provider runtime behavior remain
  unverified against AWS. Offline syntax and range checks cannot replace those
  checks in a future authorized environment outside Codex Cloud.
- Future AWS networking services and features may introduce costs. Review cost,
  routing and security implications before enabling them.
- A Lambda function does not automatically require VPC integration. A Lambda in
  private VPC subnets may need additional connectivity to reach services such as
  Secrets Manager; attaching it here alone does not provide that connectivity.
- The new DEV network root is offline-integrated; the existing serverless root is
  unchanged. Workload integration and changes to actual infrastructure require
  separate authorization, PR review and external authenticated plan review.
