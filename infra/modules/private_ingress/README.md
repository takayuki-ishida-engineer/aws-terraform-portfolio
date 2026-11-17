# Private ingress foundation — V5 extension

A coherent Terraform child owns one **internal IPv4 Network Load Balancer**, one
TCP:443 listener, an IP-mode TCP target group and its static security configuration.
The [DEV Platform Root](../../services/dev/ca-central-1/platform/README.md) composes
it beside eks_platform in the same local state. It creates no targets or Kubernetes controller,
Kubernetes resources, certificate or TLS termination. A newly created target group
has **zero Gateway targets** until separately approved runtime registration.

The external Master Policy v11 PDF was not available for independent reading.
User-supplied v11 requirements and repository decisions govern; no older policy
is substituted. All evidence is credential-free offline evidence, not deployment.

## V5 IAM, connectivity and evidence

Six additional resources extend the unchanged eleven V4 addresses. Root Override:
actual EKS OIDC issuer/provider; Module Fixed: kube-system controller SA subject,
sts audience, exact target group registration and Region condition. No default
OIDC identity is invented. Dedicated Role ARN is exposed by controller_identity
alongside issuer/provider, target group, scope, namespace and ServiceAccount. Root
adds actual cluster name, requested Kubernetes version and active AZ. The original
private_ingress output keeps all14 names and semantics; platform output is unchanged.

The Role grants only sts:AssumeRoleWithWebIdentity with exact StringEquals aud/sub
and actual Federated provider. Inline policy writes are only RegisterTargets and
DeregisterTargets on aws_lb_target_group.gateway.arn. DescribeVpcs,
DescribeSecurityGroups, DescribeInstances, DescribeAvailabilityZones,
DescribeTargetGroups and DescribeTargetHealth use Resource=* because official
service authorization lacks resource-level support, with aws:RequestedRegion.
No ModifyTargetGroup/Attributes, SG mutation, LB creation/deletion, PassRole,
cross-account assumption, broad IAM or secret-value permission is added. See the
[runtime source review and controller limitation](../../../kubernetes/README.md#registration-only-iam-and-kubernetes-isolation).

Paired standalone rules allow Istio webhook TCP15017 and Node-to-Istiod TCP15012,
using actual custom SG references. They supplement existing LBC9443/DNS paths,
not unrestricted connectivity or AWS-managed SG hardening. No Kubernetes provider,
new Root/backend/lock or double owner is added.

Current affected local results: Child36 native (7 complete positive plans,
29 rejections); Root39 native (6/33), EKS Child54. Independent ingress validation
per Child/Root:63 semantic,12 IAM policy mutations,21 capture faults,8 dependency
checks. Twelve actual unsafe source re-plans were detected; Root14 required inputs
and11 Network fields rejected. Root basic inventory54=EKS37+ingress17, or58 with
two namespace access pairs. EKS76/21/10 checks remain. Full independent CI expected
686 native/153 toolkit/13 configurations, not claimed passed locally.

## Inputs and effective configuration

| Input | Type / default | Validation / responsibility |
| --- | --- | --- |
| expected_scope | required object(environment, partition, region, account_id strings) | dev/stg/prod, aws, ca-central-1, explicit 12-digit account; Root owns provider guard |
| network_reference | required typed object, described below | Version 1, matching scope, VPC ID, complete keyed private subnet/AZ map, distinct private/public IDs, Region-matching AZ syntax |
| name_prefix | required string | `<project>-<env>`, 2–20 lowercase letters, digits or hyphens, starting with a letter, not internal-*; names below derive from it |
| subnet_keys | required set(string) | Nonempty subset of private keys, at most one subnet per AZ; public/unknown/duplicate-AZ selections rejected |
| backend_target_port | required number | Integer 1–65535; reviewed actual Gateway Pod port, not assumed equal to Service/listener 443 |
| controller_oidc | required object(issuer, provider_arn strings) | Exact ca-central-1 EKS issuer/provider, matching expected_scope.account_id; actual EKS outputs from Root |
| eks_security_groups | required object(cluster, nodes strings) | Distinct valid custom SG IDs; Root supplies actual attached EKS outputs, never managed Cluster SG |
| cross_zone_enabled | required bool | Explicit NLB behavior; DEV fixes false; multi-AZ callers review capacity, transfer and failure behavior |
| deletion_protection | bool, true | NLB protection; disabling is configuration, not teardown authorization |
| tags | map(string), {} | Additional non-secret caller tags; the module-owned Name and service tags win |

The minimal network object contains interface_version, scope, vpc_id,
private_subnet_ids, public_subnet_ids and subnet_azs.private. Public IDs are only
exclusion evidence. AZ names and IDs are declared, not discovered. Valid-looking
references can be fabricated: trusted output provenance, actual existence,
associations, enabled AZs, quotas and free IPs need external verification.
No whole State, remote-state reader or publication service is introduced.

| Effective source | Value |
| --- | --- |
| Root Override | Scope, minimal network references, name_prefix `<project>-dev`, required subnet/backend port, actual custom EKS SGs; DEV cross-zone false and existing deletion-protection selection |
| Module Default | deletion_protection=true, tags={} |
| Module Fixed | Internal network LB, IPv4, TCP:443 passthrough, TCP/IP target group, client-IP preservation=false, Proxy Protocol v2=false, target cross-zone inherits NLB, PrivateLink inbound SG evaluation=on, TCP traffic-port health checks, drain 300 seconds with connection termination, webhook TCP9443; names and Name/service tags below |

### Names and tags (Module Fixed)

Names follow [deployment configuration](../../../docs/deployment-configuration.md#4-resource-naming)
with `<prefix>` = `<project>-<env>`. Every taggable resource gets `Name` and
`service`; caller `tags` pass through and the module-owned keys win. `project`,
`env` and `managed` come from the root's provider `default_tags`.

| Resource | Name | service |
| --- | --- | --- |
| Network Load Balancer | `<prefix>-nlb` | `nlb` |
| Listener (sub-resource) | Name tag `<prefix>-nlb-tcp443` | `nlb` |
| Target group | `<prefix>-tg-gw` | `tg` |
| Controller IAM role / inline policy | `<prefix>-role-lbc` / `<prefix>-policy-lbc` (policy not taggable) | `role` |
| Security groups | `name_prefix` `<prefix>-sg-nlb-` / `<prefix>-sg-vpc-link-` (create-before-destroy), Name tags without the trailing hyphen | `sg` |
| Security group rules | `<security group Name>-<in or out>-<peer>-<flow>`, for example `<prefix>-sg-nlb-out-node-gw`; rules on the EKS groups use the `eks_platform` group names `<prefix>-sg-eks-cluster` / `<prefix>-sg-eks-node` | `sg` |

With the 10-character project limit the longest names stay within the 32-character
load balancer and target group limit.

Client-IP preservation is deliberately disabled and Proxy Protocol v2 is not
injected into the future TLS stream. No original-client-IP or authorization claim
is made. API Gateway VPC Link V2 is not automatically equivalent to AWS PrivateLink;
future REST integration must review actual traffic/SG behavior. The pinned setting
keeps PrivateLink inbound rule evaluation on, with no implicit bypass.

## Exact resource addresses and rule ownership

DEV prefixes each address with module.private_ingress. Every configuration creates
exactly 17 resources; multi-AZ selection changes subnet membership, not ownership.

| Child address | Exclusive owner / contract |
| --- | --- |
| aws_lb.this | Internal IPv4 NLB, private subnets, NLB SG attached at creation |
| aws_lb_listener.https_passthrough | TCP443, forwards actual target-group ARN, no certificate/TLS listener |
| aws_lb_target_group.gateway | TCP/ip, explicit backend port, static attributes and health check only |
| aws_security_group.nlb | NLB SG resource; no competing inline rule owner |
| aws_security_group.vpc_link_client | Future VPC Link ENI client SG; Platform retains ownership |
| aws_vpc_security_group_egress_rule.client_nlb | Client SG → actual NLB SG TCP443 |
| aws_vpc_security_group_ingress_rule.nlb_clients | NLB SG ← actual client SG TCP443 |
| aws_vpc_security_group_egress_rule.nlb_targets | NLB SG → actual Node custom SG, backend port |
| aws_vpc_security_group_ingress_rule.nodes_targets | Existing Node custom SG ← NLB SG, same backend/health port |
| aws_vpc_security_group_egress_rule.cluster_webhook | Existing Cluster custom SG → Node custom SG TCP9443 |
| aws_vpc_security_group_ingress_rule.nodes_webhook | Existing Node custom SG ← Cluster custom SG TCP9443 |
| aws_iam_role.controller | Exact EKS OIDC aud/sub IRSA role, no human/EC2 assumption |
| aws_iam_role_policy.controller | Regional read discovery and exact owned-TG registration only |
| aws_vpc_security_group_egress_rule.cluster_istio_webhook | Custom Cluster SG → Node SG TCP15017 |
| aws_vpc_security_group_ingress_rule.nodes_istio_webhook | Custom Node SG ← Cluster SG TCP15017 |
| aws_vpc_security_group_egress_rule.nodes_istiod | Custom Node SG → Node SG TCP15012 |
| aws_vpc_security_group_ingress_rule.nodes_istiod | Custom Node SG ← Node SG TCP15012 |

private_ingress owns these ten standalone rule resources, including rules on
existing EKS groups. eks_platform retains both EKS SG **resources**, all original
rules, Cluster/MNG/IAM/access/add-ons. VPC resources stay with vpc. No resource
moves/imports, shared inline rule sets or overlapping controller writers are added.
NLB explicitly depends on the target/client rule path being configured; references
order SG creation and listener → NLB/target group. Stateful return traffic does not
require a blanket reverse rule. Target health checks use the backend traffic port.

No CIDR ingress or all-protocol fallback is created. SG-to-Node references assume
ordinary VPC CNI Pods use the Node SG; security groups for Pods, alternate CNI,
NetworkPolicy and NACL behavior require a new review. NLB outbound filtering also
applies to health checks. TCP reachability does not establish TLS, mTLS, readiness,
identity authorization, correct target registration or end-to-end connectivity.
AWS-managed EKS Cluster SG permissions remain additive and **not hardened here**;
these rules are not proof of complete restricted control-plane connectivity.

## Kubernetes and future API ownership boundary

The future API Root consumes the actual VPC Link client SG ID and attaches it to
REST VPC Link V2 ENIs; it must not recreate/manage that group. This avoids a reverse
Platform dependency on a future API Root. Output publication/authenticity/integrity,
consumer read permissions and single-writer custody remain OPEN. Never distribute
whole Terraform State to obtain one reference.

A separately approved runtime installs AWS Load Balancer Controller, its dedicated
ServiceAccount and TargetGroupBinding using the Terraform-owned IAM identity. Use the pre-existing target
Group ARN, explicit targetType=ip and actual VPC ID with the reviewed Gateway
Service/Pod target port. Do not use a LoadBalancer Service that creates another
NLB; review controller default mutating-webhook behavior. Do not add Terraform
aws_lb_target_group_attachment or placeholder Pod IPs. The [V5 runtime bundle](../../../kubernetes/README.md) supplies pinned renderable source; no deployment is claimed.

**TargetGroupBinding is an authorization boundary**: untrusted namespace users
must not create/update arbitrary bindings. Later runtime approval must constrain
CRD RBAC/admission and controller IAM to approved target groups, with explicit
RegisterTargets/DeregisterTargets and necessary describe permissions. No Node-role
controller policy, broad wildcard writer or unreviewed cross-account trust is
created here. The controller must not modify Terraform-owned SG rules, target-group
attributes, listener or NLB. Pin/review its version, TGB-only permissions and
networking configuration; omit/disable competing SG reconciliation and verify it.

Upstream controller installation requires control-plane → worker TCP9443 for its
webhook. The paired custom-SG rules are implemented, but there is no deployed
webhook or claim of operational connectivity. Controller certificates, DNS,
private API/AWS endpoint access, IAM effectiveness and Pod placement remain OPEN.

## Outputs, TLS and runtime limitations

One inferred-typed private_ingress object exposes 14 fields: interface_version=1,
scope, nlb_arn, nlb_dns_name, nlb_zone_id, listener_arn, target_group_arn,
target_group_name, nlb_security_group_id, vpc_link_client_security_group_id,
private_subnet_ids by selected key, vpc_id, backend_target_port and cross_zone_enabled.
AWS references come from resources; metadata comes from validated inputs. Root
adds this output without renaming/removing any existing platform fields. No
certificate, private key, token, kubeconfig or secret is exposed.

NLB forwards TCP bytes. Future Istio Gateway owns backend TLS termination and
verification of the expected API Gateway client certificate. Future REST integration
must verify server chain/hostname and review TLS/SNI/VPC Link V2/provider behavior.
No insecureSkipVerification, plaintext fallback, PKI issuance, client certificate,
rotation/revocation, mesh STRICT mTLS or AuthorizationPolicy is implemented by this Terraform child; the V5 runtime supplies fail-closed declarations.
TCP health checks succeed before or without these security controls; do not treat
a healthy TCP target as proof of application or certificate authorization.

The reusable child supports one selected subnet per AZ and explicit cross-zone
choice. DEV selects exactly one private subnet in its active worker AZ and disables
cross-zone: **no HA claim**. Future STG/PROD distribution/surviving-AZ peak capacity,
NLB quotas, Pod IP headroom, health fail-open behavior and actual routing remain
external design/operational evidence, not consequences of a mocked multi-AZ plan.

## Provider evidence and offline verification

Actual AWS 6.72.0 schemas were inspected before implementation; no upgrade or new
provider is added. Terraform ~>1.17.0 and AWS ~>6.72.0 remain pinned at the Root;
child compatible bounds follow the existing module convention. Root lock is
unchanged; child lock is transient and seeded from it during initialization.

Historical V4 local native cases: Child 28 (six positive plans, 22 intentional input rejections);
Platform Root 38 (six positive plans, 32 intentional rejections), retaining all
29 V3 runs/assertions and adding nine. Independent ingress checks run per scope:
45 semantic mutations, 21 missing/duplicate/failed/malformed evidence faults,
eight source/dependency guards. Nine actual unsafe source copies are re-planned
and rejected, including disabling interface validation. Source guards supplement
actual plan checks; they do not prove AWS execution ordering. The existing EKS
73/21/10 checks remain. Separate required-input processes check 15 Root inputs and
11 Network fields. Rejected partial plans are never counted as complete positives.

Expected complete CI: 678 native (=641 V3 +28 child +9 Root), unchanged 153 Python,
13 initialized configurations sharing one locked AWS binary. Local affected checks
are not a claim that full V4 CI already passed. Independent exact-HEAD review is
required; no test proves real AWS creation, IAM/controller/TLS effectiveness,
capacity, pricing, log delivery or teardown.

## External execution and teardown — OPEN

Require authorized account/identity, trusted actual Network outputs, one protected
local-state custodian/writer, actual SG/VPC/subnet/Pod ownership, service support,
controller rights and actual data/health/webhook paths before authenticated work.
Review NLB capacity/LCU/hourly/data/cross-zone, EKS/NAT/logs/other service costs,
contingency and full dependency-ordered teardown. Stop/drain runtime registration
and bindings before deleting listener/target group/NLB/rules; remove all dependent
AWS/Kubernetes resources before network. Deletion protection defaults on and needs
a separately approved external configuration change. No apply/destroy is run here.
G01–G07 remain OPEN: cumulative actual JPY10,000, complete verified removal within
72 hours, no retained charge-generating exercise resources. Inventory must include
dynamic controller resources. The unchanged Secrets Manager 30-day recovery blocker
remains. No real AWS credentials/authenticated requests/plan, operational State
operations or real AWS Apply/Destroy/Import/Live work is permitted in Codex.
Isolated Emulator adapters follow [the permanent controls](../../../AGENTS.md#mandatory-official-aws-emulator-safety-controls);
the historical VPC proof establishes no ingress lifecycle compatibility.

Sources:

- [AWS NLB SG behavior](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/load-balancer-security-groups.html)
- [AWS target groups](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/load-balancer-target-groups.html)
- [AWS target attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/edit-target-group-attributes.html)
- [AWS TCP health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/target-group-health-checks.html)
- [Controller TGB security/registration](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/main/docs/guide/targetgroupbinding/targetgroupbinding.md)
- [Controller installation, TGB-only IAM and webhook9443](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/main/docs/deploy/installation.md)
- [Pinned Provider NLB](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/lb.html.markdown)
- [Pinned listener](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/lb_listener.html.markdown)
- [Pinned target group](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/lb_target_group.html.markdown)
