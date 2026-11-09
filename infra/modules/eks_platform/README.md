# Reusable private EC2 EKS platform — V3 candidate

One coherent functional child owns the private IPv4 EKS control plane, one EC2
Managed Node Group, three dedicated IAM roles, custom SGs/rules, explicit access
entries, control-plane logs, OIDC and the three core managed add-ons. Providers,
backend, account guards, environment selection and network output custody belong
to roots. [DEV composition](../../services/dev/ca-central-1/platform/README.md)
uses the separately owned V2 network; neither root owns the other's resources.

This is offline configuration evidence, not an AWS deployment or acceptance. No
external Master Policy v11 PDF was available; only the user-supplied approved
requirements and accessible repository/official references are used. Istio, Helm,
applications, NetworkPolicy/Pod Security configuration, NLB/ingress, Fargate, Auto
Mode, autoscalers and delivery pipelines are outside this module. No credentials,
Pod tokens or secret plaintext are created, discovered, passed or output.

Exact provider schemas were inspected from locked AWS 6.72.0, alongside its
[Cluster](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/eks_cluster.html.markdown),
[Node Group](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/eks_node_group.html.markdown),
[add-on](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/eks_addon.html.markdown)
and [OIDC](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/iam_openid_connect_provider.html.markdown)
references. Newest-provider behavior is not assumed to apply to this lock.

## Inputs and supported initial catalog

All operational selections below are explicit inputs, not production defaults.
AWS availability, AZ IDs, actual identities, version compatibility and capacity
cannot be established by these syntax/relationship validations.

| Input | Type / default | Contract |
| --- | --- | --- |
| expected_scope | object({environment, partition, region, account_id}=strings), required | dev/stg/prod, aws, ca-central-1, twelve-digit expected account; root still owns provider restrictions |
| network_reference | Typed object, required; schema below | Reviewed minimal Network interface v1 values; no discovery/remote state/provenance service |
| cluster_name | string, required | Conservative 1–40 characters; derived machine-role/LT/SG/log names have room within service limits |
| kubernetes_version | string, required | Initial AL2023/API catalog requires explicit 1.xx >=1.30; no default/current-support assumption |
| service_ipv4_cidr | string, required | Canonical RFC1918 /12–/24, disjoint from supplied VPC; connected network/IP allocation review remains external |
| cluster_subnet_keys | set(string), required | Private reference keys in at least two distinct AZs |
| node_group | object, required | name, subnet_keys, instance_type, ami_type, release_version, disk_size_gib, min_size, desired_size, max_size |
| bootstrap_admin_role_arn | string, required | Approved existing same-account IAM role, not user/session/service-linked/machine role; initial explicit cluster administrator |
| namespace_access | map(object({principal_arn=string, policy=string, namespaces=set(string)})), {} | Optional distinct approved view/edit roles, explicit non-system namespaces; no extra cluster administrators or groups |
| api_client_cidrs | set(string), required | Canonical private source CIDRs, no world/public API client ranges; not an installed VPN/admin host |
| node_https_egress_cidrs | set(string), required | Explicit reviewed IPv4 /8–/32 destinations for actual AWS HTTPS flows, no world default |
| addon_versions | object({vpc_cni,coredns,kube_proxy}=strings), required | Exact vX.Y.Z-eksbuild.N, compatibility with Cluster/AMI/architecture externally verified; no most_recent discovery |
| cluster_kms_key_arn | string or null, null | Optional same-account/Region approved external customer key; no key/grant owner is created |
| deletion_protection | bool, true | Cluster and log group protected; disabling is configuration, not teardown/Live approval |
| tags | map(string), {} | Non-secret caller metadata; module Name wins; root governance tags win in DEV |

Node capacity must be integers 1 <= min <= desired <= max, disk >=20 GiB. The
initial AMI catalog is AL2023_x86_64_STANDARD or AL2023_ARM_64_STANDARD, with explicit
matching Kubernetes minor release and an explicit EC2 instance type. Instance/
architecture/release support, EKS quotas, Pod IP/ENI limits and CPU/memory/system/
Istio/monitoring/application fit require external evidence. A fixture with one
worker does **not** prove it can host that stack. One MNG can select multiple
private Cluster AZs for future composition; the DEV root enforces one worker AZ.
STG/PROD roots, two-AZ surviving-peak capacity and autoscaling remain future work.

Only private API, API access-entry authentication, ordinary EC2 MNG and IPv4 are
implemented. Public endpoints, legacy/mixed authentication and Auto Mode settings
are fixed off, not exposed as optional toggles. Actual unsafe-source re-plans test
those forbidden configurations. Unsupported AMI/access/version/reference inputs
are rejected. HPA, Cluster Autoscaler, node repair and Spot are not installed or
silently enabled; desired_size is Terraform-owned, with no ignore_changes escape.

## Typed network reference and ownership

The object is a minimal subset of existing V2 network outputs:

```text
network_reference = {
  interface_version: number,
  scope: { environment, partition, region, account_id: string },
  routing_mode: string,
  vpc_id: string, vpc_cidr: string,
  private_subnet_ids: map(string), public_subnet_ids: map(string),
  subnet_azs: { private: map(string) },
  private_route_table_ids_by_subnet: map(string),
  public_route_table_id: string,
  nat_gateway_ids_by_az: map(string)
}
```

Public IDs/table are exclusion evidence, not usable Cluster/Node selections. The
module checks unique private/public IDs, complete matching private key/AZ/table
maps, per-AZ table consistency, matching scope/version and selected private keys.
This rejects known public references and inconsistent declarations. It cannot
detect a fabricated manifest that consistently mislabels actual AWS resources.
Actual VPC/subnet/route/NAT existence, associations, free IPs, AZ support and trusted
Network Root output provenance must be independently verified externally before
execution. A NAT ID alone does not prove a NAT default route. Never distribute the
whole state or grant downstream writers to network state. Publication/integrity/
consumer access/custodian mechanisms remain OPEN; no service is fabricated here.

## Resource addresses and exclusive ownership

Addresses are module-relative; DEV prefixes them with module.eks_platform.
There are 29 declaration templates. With c API client CIDRs, h HTTPS destinations
and n namespace role entries, there are **35+c+h+2n** explicit managed resources.
The basic synthetic fixture has 37; two namespace roles have 41; two client and
two egress CIDRs have 39. These counts exclude AWS-created subordinate resources.

| Address template | Instances / owner |
| --- | --- |
| aws_eks_cluster.this | 1 private Cluster, creator admin false; no Auto/Fargate |
| aws_eks_node_group.this | 1 EC2 MNG, actual role/LT/subnet references |
| aws_launch_template.nodes | 1, no public IP/SSH/custom userdata/custom image/profile; IMDSv2 hop 1 and encrypted disposable gp3 root disk |
| aws_iam_role.cluster / nodes / cni | 1 each, separate service/WebIdentity trusts |
| aws_iam_role_policy.cluster | 1 reviewed minimum control-plane policy, no legacy ELB permissions |
| aws_iam_role_policy_attachment.nodes[policy] | 2 AWS-managed policies, WorkerNode and ECR PullOnly |
| aws_iam_role_policy_attachment.cni | 1 AWS-managed IPv4 CNI policy, only on CNI role |
| aws_iam_openid_connect_provider.cluster | 1, actual Cluster issuer and sts audience |
| aws_security_group.cluster / nodes | 1 each, attached respectively to control-plane config and node LT |
| aws_vpc_security_group_ingress_rule.cluster_nodes | 1, Node SG -> API TCP443 |
| aws_vpc_security_group_ingress_rule.cluster_clients[CIDR] | c, approved private client -> API TCP443 |
| aws_vpc_security_group_egress_rule.cluster_nodes[flow] | 4, control -> Node HTTPS/kubelet/TCP+UDP DNS |
| aws_vpc_security_group_ingress_rule.nodes_cluster[flow] | 4, control SG -> Node TCP443/10250 and TCP+UDP53 |
| aws_vpc_security_group_ingress_rule.nodes_dns[protocol] | 2, Node SG -> Node/Pod TCP+UDP53 |
| aws_vpc_security_group_egress_rule.nodes_cluster | 1, Node -> API TCP443 |
| aws_vpc_security_group_egress_rule.nodes_dns[protocol] | 2, VPC resolver TCP+UDP53 |
| aws_vpc_security_group_egress_rule.nodes_peer_dns[protocol] | 2, Node SG -> Node/Pod TCP+UDP53 |
| aws_vpc_security_group_egress_rule.nodes_https[CIDR] | h, explicit reviewed HTTPS destinations |
| aws_cloudwatch_log_group.cluster | 1, /aws/eks/{name}/cluster, 30 days, STANDARD, skip_destroy=false |
| aws_eks_access_entry.bootstrap / aws_eks_access_policy_association.bootstrap | 1 each, explicit required bootstrap role and cluster-scoped ClusterAdmin policy |
| aws_eks_access_entry.namespace[key] / aws_eks_access_policy_association.namespace[key] | n each, only selected view/edit namespace scope |
| aws_eks_addon.vpc_cni / kube_proxy / coredns | 1 each, pinned versions, no self-managed duplicate owner |

AWS owns the managed Cluster SG, control-plane ENIs, MNG ASG/instances and automatic
MNG node access entry. They are not extra Terraform definitions or imported into
another owner here. No aws-auth ConfigMap or manual EC2_LINUX entry duplicates MNG
authentication. Actual inventory/reconciliation/cleanup must include these AWS-
generated resources. All roots require one authorized state custodian/writer.

## IAM, access and bootstrap boundaries

Cluster trust is eks.amazonaws.com; node trust is ec2.amazonaws.com. The
[official minimum Cluster policy](https://docs.aws.amazon.com/eks/latest/userguide/cluster-iam-role.html)
permits EC2 discovery without legacy Load Balancer creation. This module uses an
explicit read-only EC2 Describe action set with Resource=* where those APIs need
it, constrained by aws:RequestedRegion. The sole CreateTags write targets instances
in the expected account/Region and only this Cluster's tag key, with ForAllValues
and a Null guard. This is intentionally restrictive; additional service-generated
tag requests must be reviewed externally, not accommodated by a broad grant.
Optional customer-key DescribeKey is scoped to that exact key; no decrypt, key
creation, IAM administration, unrestricted PassRole or ELB policy is granted.

[Node IAM requirements](https://docs.aws.amazon.com/eks/latest/userguide/create-node-role.html)
are represented by AmazonEKSWorkerNodePolicy and AmazonEC2ContainerRegistryPullOnly.
[IPv4 CNI IAM](https://docs.aws.amazon.com/eks/latest/userguide/cni-iam-role.html)
uses AmazonEKS_CNI_Policy on a separate role. AWS-managed policies have service-
required wildcard resources and AWS-controlled mutable contents: this module does
not claim repository-scoped ECR access or eliminate their capabilities. In
particular WorkerNodePolicy includes Pod Identity permission although no agent is
installed, and PullOnly includes pull-through-cache import. Review current policy
contents/effectiveness before Live. No customer workload role is created.

CNI trust uses the actual Cluster OIDC provider ARN, exact aws-node ServiceAccount
subject and sts audience. IAM retrieves the issuer's intermediate thumbprint at
initial provider creation; no TLS data source or guessed certificate is used.
[OIDC prerequisites](https://docs.aws.amazon.com/eks/latest/userguide/enable-iam-roles-for-service-accounts.html)
include issuer DNS reachability; an EKS VPC endpoint can require split-horizon DNS
or an external setup runner. SDK/STS regional endpoint behavior, actual CNI add-on
schema and image/API flows need external verification. Do not grant CNI rights to
the Node role or claim IRSA isolates every host-network Pod.

[API access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
are the only Cluster auth model. Creator admin is disabled at creation. The
required existing bootstrap role receives AmazonEKSClusterAdminPolicy explicitly;
this is necessary initial Kubernetes administration, **not AWS AdministratorAccess**.
Only approved same-account IAM roles are accepted; additional entries cannot select
cluster-admin or system groups. There is no generated human role or hidden creator
backdoor. That role must be assumable through an authorized external identity and
reach the private API before bootstrap can work. IAM deployment identity needs
separately reviewed EKS/IAM/EC2/Logs actions and scoped PassRole for the actual
machine/add-on roles, with supported service conditions; none is granted here.

Lockout recovery requires a separately approved IAM principal able to manage EKS
access entries/policies through the AWS control API even when Kubernetes access is
lost; source/state reconciliation and audit follow. Role deletion/recreation can
invalidate entries despite identical ARN strings; verify identities externally.
Namespace Edit is not a complete isolation boundary: it can create powerful Pods.
Do not enable it without reviewed Pod Security/RBAC/hostNetwork/hostPath/IMDS
controls in those namespaces. No namespace, admission policy or workload is
installed here; namespace_access defaults empty. Bootstrap administration is
intentionally privileged and requires explicit security approval.

## Security, add-on ordering and remaining limitations

[SG requirements](https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html)
and [launch-template behavior](https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html)
are consequential: specifying custom LT SGs prevents automatic addition of the
managed Cluster SG to nodes. Our actual Node SG is used by the LT; both control
and Node rules are reference-bound and no inline rule owner competes. CoreDNS TCP/UDP53 has paired Node-to-Node and control-plane-to-Node rules;
these system paths do not open arbitrary application ports. Public IP
assignment is false even if subnet metadata is wrong. No SSH, NodePort, all-
protocol or world ingress/egress rule is introduced. IMDSv2 hop 1 reduces ordinary
Pod access, but host-network/privileged Pods can bypass that boundary.

**The AWS-created Cluster SG still has AWS-managed default self rules and broad
outbound behavior.** Our attached SG is not an overriding deny: SG permissions
are additive. V3 does not remove/import/manage those defaults or claim complete
control-plane egress restriction. Managed-SG hardening/attachment inventory and
whether a later approved model is necessary remain OPEN before Live. SGs also do
not filter AmazonProvidedDNS; resolver rules here do not implement DNS filtering.
NACL, NetworkPolicy, admission controls, inter-Pod app/mesh ports and platform
controller privileges remain separate work, not implicit protection by routing.

[Private cluster connectivity](https://docs.aws.amazon.com/eks/latest/userguide/private-clusters.html)
requires approved API, EC2, STS, ECR API/DKR and S3 image paths as applicable to the
selected versions. Explicit HTTPS CIDRs must cover actual traffic via the reviewed
NAT/endpoint paths; dynamic AWS IP ranges need operational custody. No speculative
interface endpoint bundle or egress-to-world fallback is created. Supported AZ IDs,
subnet free IPs/ENI surge, quotas and all actual network paths require external
verification. Two Cluster AZs do not prove availability; one DEV worker AZ does
not prove system/mesh/monitor/app fit or future STG/PROD surviving-peak capacity.

[Core add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html)
have one owner: bootstrap_self_managed_addons=false, three explicit managed API
resources, pinned required versions, default parameter object {}, no overwrite
adoption, preserve=false. CNI waits for its separate IAM policy; CNI/kube-proxy
precede the MNG; CoreDNS follows the MNG to avoid waiting for Pods on absent nodes.
AWS health convergence and version/architecture compatibility remain unproven.
Future HPA, CA, Pod Identity Agent, EBS CSI, Istio and Helm are not installed.

[Default envelope encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html)
for >=1.28 uses an AWS-owned key with no additional IAM permissions. Optional
[customer KMS](https://docs.aws.amazon.com/eks/latest/userguide/enable-kms.html)
is an actual same-account/Region reference, never a key/grant creation. Key
symmetry, policies, caller DescribeKey/CreateGrant and service behavior require
external approval; mock acceptance is not KMS usability. Node root volumes are
encrypted gp3 with deletion on termination; review account default EBS key policy.
All five control-plane log types are selected; protect access, review service audit
content and cost. No runtime secret-redaction or log-delivery claim is made.

## Outputs and effective configuration

Twelve actual resource-backed outputs: cluster_name, cluster_arn, endpoint,
certificate_authority_data (public CA, not a credential), oidc_issuer,
oidc_provider_arn, node_group_arn, security_group_ids (custom cluster/node plus
AWS-managed diagnostic ID), role_arns, access_entry_arns, addon_arns and log_group_arn.
No kubeconfig, bearer token, secret or full-state publication is output.

| Source | Effective values |
| --- | --- |
| Root Override | Actual scope/network/name/version/subnet/Node/capacity/bootstrap/add-on/flow inputs; DEV active AZ guard and governance tags |
| Module Default | namespace_access={}, cluster_kms_key_arn=null, deletion_protection=true, tags={} |
| Module Fixed | Private IPv4/API auth, creator admin and Auto/Fargate off; EC2 ON_DEMAND AL2023 catalog, IMDSv2 hop1, no SSH/public IP, encrypted disposable gp3; explicit core add-ons and IRSA; 30-day STANDARD logs; no forced update/drain or floating versions |

## Actual offline verification and execution boundary

Terraform 1.17.0 / locked AWS 6.72.0: 52 native passes, seven complete positive
plans and 45 intentional native rejection cases. Independent actual-plan checks
exercise exact ownership/resource inventory, known critical computed values,
relationships, IAM/Trust/SG/access/add-on contracts and all outputs. There are 73
semantic mutations, 21 capture-failure injections and ten source dependency/guard
mutations per scope. Ten additional actual unsafe Terraform source copies are
re-planned: private-profile violations fail native assertions and independent
checks; other unsafe IAM/SG/add-on variants fail actual-plan checks. Failed native
assertions can emit a plan; this is rejected evidence, not a successful topology.
Required-input/partial-plan evidence is explicitly distinguished from full plans.

The 73 detected semantic cases per scope comprise 53 generated-resource contracts,
nine IAM/Trust JSON mutations, two namespace privilege escalations and nine
ownership/computed-value/output faults. The 21 capture rejections comprise seven
missing-event types, six duplicate-event types, three failed/errored/skipped
terminals, one nonzero Terraform process and four malformed/duplicate-key/nonfinite
JSON cases. Ten dependency/source-guard mutations are separate from the ten actual
unsafe Terraform source re-plans. Checker JSON reports list individual detections;
these categories are not extra native test passes.

The workflow performs init -backend=false with a readonly executing-root lock,
validate, native JSON capture/checker --self-test, required-input and actual-source
mutation checks. Child lock is transient, not committed; root lock is committed.
Existing V2 and all independent Terraform/Python/IAM/security regressions remain.
No mock proves authenticated IAM, addon health, log delivery, routing, failover,
real-state migration or a usable production version/capacity. Complete exact-HEAD
CI requires independent review; a local pass does not authorize merge or AWS.

DEV local state and a single custodian/writer remain mandatory; STG/PROD backend
choice is OPEN. Real resource/state ownership, costs (control plane, nodes/EBS,
NAT/transfer, logs, optional key), quotas and dependency-ordered teardown require
separate approval. Deletion protection defaults on; reviewed external changes must
disable it before approved teardown. Delete CoreDNS before compute, compute before
CNI/proxy/roles, then Cluster/managed resources; remove platform before network.
Inventory/reconcile service-created ENIs/SGs/ASGs/instances/access entries and logs.
G01–G07 remain OPEN. DEV Live retains cumulative actual JPY 10,000 and complete
verified teardown within 72 hours, with no retained charge-generating exercise
resources. Any scenario creating unchanged Secrets Manager metadata still has the
30-day recovery blocker; V3 does not resolve it. No AWS/State/Live operation occurs.
