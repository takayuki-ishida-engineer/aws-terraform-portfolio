# Reusable IPv4 VPC module

This child module implements one VPC with explicit, keyed private subnets and
optional public subnets. Its default posture is private-only, without internet
egress. It is not called by any service root yet. No AWS infrastructure has been
deployed and no live AWS integration testing has been performed.

## Resources and routing

- One `aws_vpc.this`, with DNS support and hostnames enabled.
- `aws_subnet.private` and `aws_route_table_association.private`, keyed by the
  caller's `private_subnets` map. All share `aws_route_table.private`.
- Only when `public_subnets` is nonempty: `aws_subnet.public` and its keyed
  associations, one `aws_internet_gateway.this[0]`, and one
  `aws_route_table.public[0]` with an inline `0.0.0.0/0` route to that gateway.

The private table explicitly configures no routes. AWS still supplies its implicit
VPC-local route; this module adds no private default internet route or NAT path.
Public subnet classification means association with the IGW-routed table, not
automatic assignment of public IPs or guaranteed reachability for workloads.
Neither private nor public subnets automatically assign public IPv4 or IPv6.

Stable caller map keys identify subnet and association resources. Reordering map
entries or AZ declarations does not change their addresses. Renaming keys or
changing CIDRs/AZs can replace resources: review a real Terraform plan outside
Codex Cloud before changes to managed infrastructure.

## Inputs, defaults, and fixed settings

All five inputs reject top-level null values. Subnet objects require both fields.

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
| Module Default | `public_subnets = {}` and `tags = {}` |
| Module Fixed | DNS support/hostnames enabled; generated IPv6 disabled; subnet public IPv4 and IPv6 assignment disabled; one shared private table without configured routes; module-owned `Name` tags |

No feature-flag input is necessary: a nonempty public subnet map is the explicit
request for public functionality. There are no speculative NAT or endpoint flags.

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
| `private_route_table_id` | `string` | Shared private route table ID |
| `public_route_table_id` | `string` or `null` | Public table ID; null when omitted |
| `internet_gateway_id` | `string` or `null` | IGW ID; null when omitted |

ID values come from resource references, not invented ARNs or IDs. Terraform
outputs infer their types; keyed objects are convertible to maps by callers.

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

The listed checks passed. Native `tests/vpc.tftest.hcl` has **16 passing runs, zero
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
credentials, or deployments were used. Mock plan results are not integration
tests or evidence of deployment readiness.

## Limitations and future integration

- No NAT Gateway, Elastic IP, VPC Endpoint, Flow Logs, IPv6, Transit Gateway,
  peering, cross-region networking, Route 53 private hosted zone, VPN, Direct
  Connect, Network Firewall, Security Group, custom Network ACL, or remote backend
  resources are implemented.
- Private subnets have no internet egress through this module. AWS-service access
  can require separately designed connectivity such as endpoints or NAT, neither
  of which is included. Public subnets do not automatically assign public IPv4.
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
- Root integration, additional modules, and changes to existing infrastructure
  require a separate request, PR review, and an appropriate plan review outside
  Codex Cloud. No service root is modified by this module implementation.
