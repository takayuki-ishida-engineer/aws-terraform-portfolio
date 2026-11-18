# DEV EKS and private ingress platform — V4 candidate

## Input values (Step 1 item 3)

Values follow the [deployment configuration](../../../../../docs/deployment-configuration.md#1-where-values-live). The committed
`terraform.tfvars` holds every required input; environment-specific inputs there
are documented placeholders. Copy `local.auto.tfvars.example` to the untracked
`local.auto.tfvars` and set the real values: `project`, `aws_account_id`, `bootstrap_admin_role_arn` and `network_reference` (the network root output). The
[local workflow](../../../../../scripts/local-workflow/README.md) preflight refuses a plan or apply while any of them is
missing locally or still a placeholder. Full CI plans this root with the committed
values under mocks. Never put a credential or secret value in any tfvars file.
State is local by default; for the optional S3 backend copy
`backend_override.tf.example` and `backend.s3.tfbackend.example` (both stay
untracked once copied) and run `run.py <root> migrate-state`.

| Committed value | Setting |
| --- | --- |
| Kubernetes | `1.35`; add-ons vpc-cni `v1.23.1-eksbuild.1`, coredns `v1.14.3-eksbuild.16`, kube-proxy `v1.35.3-eksbuild.25` (EKS User Guide source, read 2026-11-17) |
| Node group | `private1`, `m6i.large`, `AL2023_x86_64_STANDARD` release `1.35.9-20261112`, 30 GiB, 1/1/2 |
| Cluster subnets and service CIDR | `private1`, `private2`; `172.20.0.0/16` |
| Private API clients | `10.40.1.0/24` (subnet of the item 5 developer-access EC2) |
| Node HTTPS egress | `10.40.0.0/16`; nodes still need AWS service reachability (audit finding F16) |
| Private ingress | `private1`, Gateway target port `8443` |

## Current V5 runtime identity extension

[private_ingress](../../../../modules/private_ingress/README.md) now owns17 resources:
the original eleven V4 addresses, exact-subject IRSA Role+inline policy and four
paired TCP15017/15012 SG rules. The basic Platform plan has54 resources (58 with
two namespace access pairs), retaining the37 EKS addresses. No new Root, provider,
backend, lock or State boundary; Network/serverless Roots remain unchanged.

Root Override supplies controller_oidc from actual module.eks_platform outputs;
Module Fixed is the kube-system/aws-load-balancer-controller subject/audience and
registration-only policy on the actual owned TG. Existing platform and
private_ingress outputs are unchanged. Additional controller_identity output has
11 fields: interface_version, scope, role_arn, oidc_issuer, oidc_provider_arn,
namespace, service_account, target_group_arn, actual cluster_name, requested
kubernetes_version and active_workload_az. No new operational allocation is invented.

The [Kubernetes runtime](../../../../../kubernetes/README.md) consumes reviewed
minimal extracts, never whole State. It renders pinned LBC/Istio/TGB/MUTUAL TLS/
STRICT/default-deny source without deploying. Registration is dynamic controller
ownership; NLB/TG settings/static SGs/IAM remain Terraform-owned. Publication,
authenticity, live identity, CA/Secrets, capacity, connectivity and effective
admission remain OPEN. See that README for deployment/teardown ordering and
fail-closed external dependencies.

## Current names, tags and naming inputs (Step 1)

Names and tags follow [deployment configuration](../../../../../docs/deployment-configuration.md#4-resource-naming)
sections 4 and 5. Required `project` (1–10 lowercase characters, starting with a
letter, without aws/amazon/cognito; tracked placeholder `project`) replaces the
former `cluster_name` and `ingress_name` inputs, and `node_group` no longer carries
a name. The root derives `name_prefix = <project>-dev` (**Root Override**) and both
children derive every name from it, for example `<project>-dev-eks`,
`<project>-dev-ng`, `<project>-dev-role-eks-cluster`, `<project>-dev-nlb` and
`<project>-dev-tg-gw` (**Module Fixed**; full tables in the
[eks_platform](../../../../modules/eks_platform/README.md#names-and-tags) and
[private_ingress](../../../../modules/private_ingress/README.md#names-and-tags-module-fixed)
READMEs). Provider `default_tags` set only `project`, `env = dev` and
`managed = terraform` (**Root Override**); the root also passes them to
eks_platform `default_tags` because provider default tags do not reach instances
and volumes launched by the node group. Modules set `Name` and `service`. Optional
`tags` adds caller tags and may not set `project`, `env`, `service`, `managed` or
`Name`. The bootstrap and namespace roles may not be any of the derived
`role-eks-cluster`, `role-eks-node` or `role-cni` machine roles. Namespace access
keys are lowercase hyphenated words. The former Environment/Service/Project/
ManagedBy tags are removed.

Affected local native results are Root39, ingress Child36, EKS Child54; independent
IAM/SG/security/input/evidence/mutations pass as recorded in child/runtime READMEs.
Current totals are in the latest Full CI job summary ("Summarize actual validation results"), requiring
exact-HEAD independent review. Historical V3/V4 sections below retain their scoped counts;
they are not current repository-wide totals. All G01–G07/JPY10,000/72-hour removal/
Secrets recovery restrictions are unchanged.

## Historical V3/V4 implementation notes


This is an offline-verified Terraform root, not an AWS deployment. It composes the [eks_platform child](../../../../modules/eks_platform/README.md), owns a fixed
ca-central-1 AWS provider with allowed_account_ids, a local backend and a committed
AWS 6.72.0 lock (Terraform ~>1.17.0 / AWS ~>6.72.0). It modifies neither the Network
nor historical serverless API roots, their state or approved resource moves.


## V4 private ingress foundation candidate

V4 starts at accepted post-V3 main `6b185820c806a0c96410a145106b9f103db14d89`,
[successful push CI42720431920](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42720431920).
The V3-only inventory/evidence below is retained historical context. This Root now
also calls [private_ingress](../../../../modules/private_ingress/README.md) directly,
with no new provider, backend, lock, Root or State boundary. EKS still owns its
37-resource basic configuration; ingress adds 11 (48 combined, 52 with two namespace
access pairs). EKS-owned addresses and the complete platform output are unchanged.

Three additional required non-secret inputs: ingress_name (reviewed valid 1–20
character name), ingress_subnet_key (known private key in active_workload_az) and
gateway_target_port (integer 1–65535). All prior 12 required inputs and four defaults
remain effective. The typed Network reference is unchanged. No concrete allocation,
account, port, subnet or identity is invented; 8443 is only a synthetic test fixture.
The child receives actual module.eks_platform.security_group_ids.cluster/nodes,
never the AWS-managed ID. DEV fixes cross_zone_enabled=false, selects exactly one
private subnet and propagates deletion_protection and mandatory governance tags.

Root Override: the three required ingress values, expected scope/network reference,
actual EKS custom SGs, DEV cross-zone=false, existing deletion protection and tags.
Module Default: protection=true/tags={}; Module Fixed: internal IPv4 TCP443 →
reviewed TCP/IP backend port, client IP/Proxy Protocol disabled, PrivateLink SG
filtering on, TCP traffic-port health checks, 300-second drain, webhookTCP9443.
The child owns both new SGs and six scoped standalone rules, including three on
existing EKS custom SGs (Node target ingress, control webhook egress, Node webhook
ingress). EKS retains its SG resources and original rules; future controllers
must not reconcile those Terraform-owned rules or target-group settings.

The additional inferred-typed private_ingress output has interface_version/scope,
NLB ARN/DNS/zone, listener ARN, target group ARN/name, NLB and future VPC Link client
SG IDs, selected private subnet IDs, VPC ID, backend port and cross-zone selection.
The API Root will attach the client SG to VPC Link V2 ENIs; it must not recreate it.
Publication/authenticity/integrity/read access/custody remain OPEN, without whole
State access. No API Root or distribution service is implemented.

No targets exist initially. V5 Terraform owns scoped controller IAM; separately approved deployment owns ServiceAccount,
RBAC-restricted TargetGroupBinding and Gateway Service/Pods. Do not create another
NLB via a LoadBalancer Service. No Terraform Pod registration, controller install,
Kubernetes/Helm provider or workload is added. Paired webhook9443 SG rules do not
make a webhook operational. SG-for-Pod/CNI assumptions, AWS-managed Cluster SG
residual permissions, actual data/health/DNS/AWS API connectivity remain OPEN.

TCP passthrough is not TLS/mTLS implementation. Istio must later terminate TLS and
verify the expected API client certificate; API integration must verify server
chain/hostname/SNI. VPC Link V2/provider compatibility, PKI/rotation/revocation,
NetworkPolicy and mesh/application authorization remain OPEN. No TLS listener,
certificate or insecure verification fallback exists. TCP health is not TLS or
application authorization evidence. Single-AZ DEV is not highly available.

Local V4: Root38 native (6 positives/32 rejections), Child28 (6/22); ingress checks
per scope detect45 semantic mutations, reject21 capture faults and detect8 source
mutations. Nine unsafe actual source re-plans are rejected. Existing EKS73/21/10
remain, as do required-input checks (now15 Root+11 Network fields). Full CI expected
678 native/153 Python/13 configurations; no pending CI success is claimed. Timeout
stays30 minutes. All G01–G07/budget/72-hour inventory+teardown/Secrets recovery gates
below remain OPEN; source/mock success does not authorize AWS, merge or V5.

## Historical V3 required input and network interface

Required inputs are aws_account_id, active_workload_az, network_reference,
cluster_name, kubernetes_version, service_ipv4_cidr, cluster_subnet_keys,
node_group, bootstrap_admin_role_arn, api_client_cidrs, node_https_egress_cidrs and
addon_versions. Optional namespace_access={}, cluster_kms_key_arn=null,
deletion_protection=true and tags={} match child defaults. No actual account, AZ,
CIDR, IAM principal, instance size, Kubernetes/add-on/AMI release or capacity has a
production default. Complete synthetic configurations in the native test file
are offline fixtures only, not approved allocations or version compatibility.

Supply actual reviewed non-secret environment values through a separately
reviewed var-file in a future separately authorized external workflow. Never put
credentials, secret plaintext, Pod tokens or private keys in that file/Terraform.
Actual AWS identity/account authorization must be verified outside Codex; an
account restriction or echoed manifest scope does not create/authorize an account.
Use a dedicated non-management workload account and one approved state writer.

The strongly typed network_reference consumes only these V2 output fields:

```text
interface_version=1
scope={environment="dev",partition="aws",region="ca-central-1",account_id=<required account>}
routing_mode="per_az"
vpc_id, vpc_cidr
private_subnet_ids, public_subnet_ids
subnet_azs={private=<key-to-AZ map>}
private_route_table_ids_by_subnet, public_route_table_id
nat_gateway_ids_by_az
```

Public IDs/table are needed solely to reject known public selections and conflicting
references. Maps must have complete consistent keys and unique IDs; private tables
must reflect AZ identity and differ from the public table. Cluster keys select
private subnets in >=2 distinct Region-matching AZs. DEV Node keys are a subset of
those keys and all select the explicitly supplied active_workload_az; the declared
single V2 NAT must be in that AZ. Empty/duplicate/missing/wrong-scope/version or
public references are rejected. Real supported AZ IDs, free IPs and route/NAT
relationships are not discoverable from these declarations.

Output publication, integrity, consumer authorization and State distribution remain
OPEN. No terraform_remote_state, AWS data lookup, invented parameter service or
state sharing is implemented. A consistently fabricated manifest can still mislabel
real resources: an authorized external workflow must verify actual Network Root
outputs, VPC/subnet/route/SG ownership and state custodian before using them. The
Platform Root must never write network state or claim NAT existence proves egress.

## Effective DEV configuration and resource ownership

| Source | Effective configuration |
| --- | --- |
| Root Fixed | AWS ca-central-1, account guard from required aws_account_id, local state, reviewed provider lock, scope dev/aws/ca-central-1 |
| Root Override | Required operational selections, one active worker AZ and matching declared NAT; name_prefix `<project>-dev`; provider default_tags project=`<project>`, env=dev, managed=terraform, also passed to eks_platform default_tags; child `tags` = caller extra tags only |
| Module Default | No extra namespace roles/customer key unless selected; deletion protection on; caller tags empty |
| Module Fixed | Private API only, API access entries, creator admin off, IPv4, EC2 ON_DEMAND MNG with explicit AL2023 release; IMDSv2 hop1/no public IP/SSH; separate Cluster/Node/CNI roles, IRSA and three managed add-ons; all five control-plane logs |

All resource addresses are prefixed module.eks_platform. The child owns 29
resource declaration templates and 35+c+h+2n actual managed instances: c approved
API source CIDRs, h approved HTTPS destination CIDRs, n namespace role entries.
The [complete child inventory](../../../../modules/eks_platform/README.md#resource-addresses-and-exclusive-ownership)
lists Cluster, MNG/LT, three roles, scoped Cluster inline policy, three policy
attachments, OIDC provider, two SGs/eighteen rules in the basic fixture, log group,
bootstrap access pair, optional namespace access pairs and three add-ons.
Native basic/ARM/customer-key/alternate-ID fixtures have 37 resources; the two-role
namespace fixture has 41. AWS-generated managed SG, ENIs, ASG/instances and MNG
node auth entries are service-owned and must also be externally inventoried.

## IAM, access, networking and known gaps

Cluster role uses the official minimum control-plane discovery/tag policy without
legacy ELB writes. EC2 reads needing wildcard resources remain Region-constrained;
instance tags are expected account/Region/Cluster-key scoped with a presence guard.
Node role attaches official WorkerNode and ECR PullOnly policies. CNI alone gets
its separate CNI policy with actual OIDC-provider trust restricted to aws-node and
sts audience. Managed policy contents are AWS-controlled: review their full scope,
including wildcard resources and optional capabilities, before Live. No custom
PassRole/admin/workload policy or actual deployment principal is generated.

The required bootstrap role is an existing explicitly approved same-account IAM
role, distinct from machine/add-on roles. It receives cluster-scoped Kubernetes
ClusterAdmin through an explicit access entry/association, never implicit creator
admin or legacy aws-auth. Optional other principals are distinct view/edit roles
with explicit non-system namespace scope. Namespace Edit is not Pod isolation;
review admission/RBAC/host-network/host-mount controls before enabling it. None is
installed by V3. Actual private administrative/deployment connectivity is required.
A separately approved IAM recovery operator needs EKS control-API rights to repair
entries if Kubernetes access is lost; Terraform/state reconciliation remains owned.

Custom control SG is actually attached to the Cluster config; custom Node SG is
actually attached to the LT and is not replaced by a managed/unused group. The
custom LT prevents automatic Node attachment of the EKS managed Cluster SG.
Explicit system SG flows and approved HTTPS CIDRs are enforced in configuration.
**AWS still creates/attaches its managed Cluster SG with default self/broad egress
rules. SG permissions are additive; V3 does not harden/remove those defaults or
prove complete control-plane egress restriction.** Managed-SG hardening/attachment
review remains OPEN before Live. DNS filtering, NACL, NetworkPolicy, Pod Security,
mesh/app ports and controller rights are also outside V3. IMDSv2 hop1 is not a
barrier to privileged/host-network Pods.

Private Cluster endpoint is true, public endpoint false; Cluster subnets span at
least two AZs while DEV Nodes use one active AZ. IPv4 service CIDR is required,
private and nonoverlapping with supplied VPC; connected-network allocations remain
external. Actual EC2/STS/ECR API+DKR/S3/API and DNS paths must be verified for the
selected versions and the restricted CIDR/NAT/endpoint model. Default CNI/proxy are
not double-owned: self-managed bootstrap is off, managed versions are required,
CNI IAM readiness and CNI/proxy precede MNG, CoreDNS follows MNG. No Pod Identity
Agent, EBS CSI, HPA/CA, Istio, Helm, ingress or application is deployed. No assertion
that one worker fits system/mesh/monitor/app or survives an AZ failure is made.

AWS-owned default envelope encryption applies for the allowed EKS versions; an
optional external customer key requires separately verified key type/policy/grants.
Node gp3 root disks are encrypted/disposable; review account EBS key defaults.
Control logs are 30-day STANDARD with protection by default. Real KMS usability,
permissions, log content/delivery and actual service health are not mock-proven.

## Actual outputs and offline verification

The single platform output contains expected scope plus twelve actual child fields:
cluster_name, cluster_arn, endpoint, certificate_authority_data (public CA),
oidc_issuer, oidc_provider_arn, node_group_arn, security_group_ids, role_arns,
access_entry_arns, addon_arns and log_group_arn. No token/kubeconfig/secret or full
state is exposed. Alternate computed-value fixtures change SG/LT/issuer/endpoint/
public CA values to verify resource references instead of hardcoded test IDs.

Affected local evidence: Root 29 native passes (five complete positive plans,
24 intentional rejections); child 52 (seven complete positive plans, 45 intentional
rejections). Actual-plan checks pass 73 semantic mutations, 21 malformed/missing/
duplicate/failure capture injections and ten dependency/account/backend/source
guard mutations per scope. Ten unsafe actual Terraform source variants are
re-planned and rejected. Twelve independently missing Root inputs and eleven
missing network fields fail before a successful resource plan. Rejected partial
plans are checked against reviewed shapes and never counted as full topologies.

The 73 detected semantic cases per scope comprise 53 generated-resource contracts,
nine IAM/Trust JSON mutations, two namespace privilege escalations and nine
ownership/computed-value/output faults. The 21 capture rejections comprise seven
missing-event types, six duplicate-event types, three failed/errored/skipped
terminals, one nonzero Terraform process and four malformed/duplicate-key/nonfinite
JSON cases. Ten dependency/source-guard mutations are separate from the ten actual
unsafe Terraform source re-plans. Checker JSON reports list individual detections;
these categories are not extra native test passes.

CI initializes three roots and nine children: 12 configurations sharing one locked
AWS 6.72.0 binary. Expected native aggregate is 641 = 560 accepted V2 + 52 child +
29 platform Root; existing 153 Python toolkit and every prior VPC/Lambda/HTTP/IAM/
Secrets/S3/guardrail/negative/mutation check remain unchanged. Complete exact-HEAD
CI is independently reviewed after PR creation; no pending CI is claimed passed.

## Prerequisites before authenticated external work — all OPEN

1. Actual trusted Network deployment/output provenance, allocation, state/resource
   inventory and one authorized network/platform writer/custodian each.
2. Dedicated account, actual deployment/bootstrap/recovery identities, scoped
   IAM/PassRole and private administrative/deployment connectivity.
3. Supported EKS version, AL2023 release/instance architecture, pinned add-on
   versions/schema and exact CNI/node IAM/service authorization effectiveness.
4. Supported AZ IDs, subnet/IP/ENI/surge quotas and capacity model for system,
   CoreDNS/CNI/proxy plus future Istio/monitoring/apps; no worker sizing guarantee.
5. Actual egress/DNS/ECR/STS/API paths and SG/managed-SG/admission/network controls.
6. Optional KMS key type/policies/grants, account EBS defaults, log delivery,
   access/privacy and cost behavior.
7. Cost model (control plane, compute/EBS, NAT/data, logs, optional key), contingency,
   teardown ordering and actual inventory/state reconciliation.

No AWS credentials/authenticated API/plan, state operations, apply/destroy/import
or Live work occurs in Codex. DEV local state protection/backups/restore remain
operational approvals; STG/PROD roots/backend are not implemented. Deletion
protection must be deliberately disabled through an approved external change before
teardown; do not interpret its input value as approval. Remove platform and AWS-
generated resources before network, with actual inventory reconciliation.
G01–G07 remain OPEN; DEV Live is at most JPY 10,000 cumulative actual expenditure
and complete verified cleanup within 72 hours. No exercise-created charge-generating
resource may remain. The unchanged Secrets Manager 30-day recovery scenario blocker
is not solved by this module. Source/local CI success does not authorize merge,
AWS deployment or the next phase.
