# DEV private EKS platform foundation — V3 candidate

This is an offline-verified Terraform root, not an AWS deployment. It calls exactly
one [eks_platform child](../../../../modules/eks_platform/README.md), owns a fixed
ca-central-1 AWS provider with allowed_account_ids, a local backend and a committed
AWS 6.72.0 lock (Terraform ~>1.17.0 / AWS ~>6.72.0). It modifies neither the Network
nor historical serverless API roots, their state or approved resource moves.

## Required input and network interface

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
| Root Override | Required operational selections, one active worker AZ and matching declared NAT; tags Environment=dev, Service=platform, Project=aws-terraform-portfolio, ManagedBy=Terraform |
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
