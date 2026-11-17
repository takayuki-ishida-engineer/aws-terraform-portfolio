# Human access through IAM Identity Center

This module defines three distinct Permission Sets, their inline policies and
one Developer customer-managed-policy reference in an **existing organization
IAM Identity Center instance**. It does
not create an instance, users, groups, access keys, passwords, account assignments,
Organizations configuration, workload roles, or deployment identities. Nothing
has been deployed or connected to a real AWS account.

| Fixed Permission Set name | Responsibility | Session |
| --- | --- | --- |
| `Portfolio-Access-Admin` | Assign/revoke only Developer and Operator in approved workload accounts | One hour (`PT1H`) |
| `Portfolio-Developer` | Reviewed VPC and Secrets Manager container operations; live authorization unverified | One hour (`PT1H`) |
| `Portfolio-Operator` | VPC and scoped Secrets Manager metadata only | One hour (`PT1H`) |

Developer uses EC2 inline plus the account-owned Secrets Manager policy below.
Access Admin and Operator retain their reviewed inline policies. This module
creates no account-owned IAM policy: each workload account's future owning root
must use [`iam_account_policies`](../iam_account_policies/README.md) first.

There are no AWS-managed policy attachments. In particular, AdministratorAccess,
PowerUserAccess and ReadOnlyAccess are not used. Human permissions do not define
Lambda/ECS/EC2 execution roles, CI trust, or Terraform deployment credentials.
Future workload IAM must be designed and reviewed independently.

## Prerequisites and bootstrap boundary

1. An organization instance must already be enabled in the Organizations
   management account. Account instances are not accepted.
2. Access Admin must operate from the **management account or a registered
   delegated administrator account**. Merely assigning this Permission Set in an
   ordinary member account does not establish administrative access. Delegated
   administrator registration needs management-account authority and is outside
   this module. Root-user operations are not required or authorized here.
3. `administration_account_id` identifies that operating account. Every Access
   Admin statement requires `aws:PrincipalAccount` to equal it. This authentic
   context key checks the principal's account, **not delegated-admin registration**.
   External review must verify registration, trusted access and actual instance
   ownership before use; format validation cannot establish these facts.
4. Assignment targets must be approved workload member accounts. The module
   rejects the administration account as a target. External review must also
   exclude the management account when a separate delegated administrator is
   used. Management-account assignment administration is not supported here.
5. A separately approved bootstrap/automation identity outside Codex Cloud must
   create these definitions and provision the Access Admin entry point in the
   correct administrative account. This module does not grant bootstrap
   permissions, register administrators, onboard people, or assign anyone.

The caller's provider must use the Identity Center home region. `target_region`
is the separate EC2 portfolio authorization region; it does not configure the
SSO provider endpoint. Verify region/partition compatibility externally.

The customer-managed reference must not be provisioned into any target account
until that account contains **Portfolio-Developer-SecretsManager** at path **/**.
A policy existing in the administrative account does not satisfy this contract.
Name/path matching alone does not guarantee correct content; the per-account
module generates consistent account-specific policies that must be reviewed.

Each Permission Set has one `aws_ssoadmin_permission_set_inline_policy`. Explicit
references bind it to the corresponding Permission Set; Access Admin's policy
also depends on the exact Developer/Operator ARNs. Provider policy updates can
provision the updated policy into accounts where a Permission Set was previously
provisioned. This is not permission to create account assignments. Review changes
to existing provisioned profiles before an authorized external execution.

Customer-managed-key encrypted instances require separate, key-specific KMS
authorization and key policy review. No KMS permissions are granted here, so do
not assume this baseline can administer a CMK-backed instance. Do not add broad
Decrypt access or copy a KMS administrator template to make it work.

## Inputs and configuration sources

All required inputs have no defaults and reject null. No actual account IDs,
instance IDs, workforce identities, credentials, or secrets are provided here.

| Input | Type | Validation / purpose |
| --- | --- | --- |
| `name_prefix` | `string` | 1-63 alphanumeric/underscore/hyphen characters, starting alphanumeric; inventory Name tags only |
| `instance_arn` | `string` | Explicit `arn:<partition>:sso:::instance/ssoins-<16-character-id>` organization instance; supported partition syntax is `aws`, `aws-us-gov`, or `aws-cn` |
| `administration_account_id` | `string` | Exactly 12 digits; must not be an assignment target; management/registered delegated-admin account verified externally |
| `target_account_ids` | `set(string)` | Nonempty set of exactly 12-digit approved workload accounts |
| `target_region` | `string` | Explicit region identifier without wildcards; existence/partition support verified externally |
| `project_tag` | `string` | 1-63 lowercase letters/digits/hyphens, starting with a letter; project authorization tag value |
| `tags` | `map(string)` | Optional, default `{}`; Permission Set inventory tags only, never policy content |

`administration_account_id` is intentionally separate from workload targets:
it binds the administrative caller context without pretending target-account
scoping proves that the caller is a delegated administrator.

| Source | Configuration |
| --- | --- |
| Root Override | Explicit instance, administrative account, target accounts, region, project identity, inventory prefix and optional inventory tags |
| Module Default | Additional Permission Set `tags = {}` |
| Module Fixed | Three Permission Set names, one-hour sessions, reviewed actions/resource types/conditions, EC2 creation tag keys, module-owned Name/project inventory tags |

Permission Set names remain exactly those listed above; `name_prefix` does not
rename access identities. Module-owned `Name` and `project` inventory tags win
over caller tags. There is no arbitrary JSON policy input, managed-policy ARN
input, PassRole switch, or future-service toggle. Use one reviewed management
configuration for these organization-wide names rather than duplicate modules
per application environment.

## Outputs

| Output | Type | Meaning |
| --- | --- | --- |
| `access_admin_permission_set_arn` | `string` | ARN of the Access Admin Permission Set definition |
| `developer_permission_set_arn` | `string` | ARN of the Developer Permission Set definition |
| `operator_permission_set_arn` | `string` | ARN of the Operator Permission Set definition |

These are resource references, not active user sessions or account assignments.
No workforce identities, credentials, or target-account identifiers are output.

Additional non-secret outputs are `developer_customer_managed_policy_references`
(actual attachment name/path), `developer_inline_policy_quota` (actual bytes,
10,240-byte limit and remaining capacity), and `developer_managed_attachment_quota`
(actual configured count, conservative budget, service limit and available slots).
These describe configuration; they do not verify target-account policy existence
or live quota/role propagation.

## Complete permission matrix

All actions below are exact names. Let:

- **I** be the explicit instance ARN.
- **P** be only this module's exact Developer and Operator Permission Set ARNs.
- **A** be `arn:<partition>:sso:::account/<approved-target-id>` for each target.
- **V/S/G/T** be, respectively, the approved VPC/subnet/internet-gateway/route-table
  patterns `arn:<partition>:ec2:<target_region>:<approved-target-id>:<type>/*`.
- **R** require `aws:RequestedRegion = target_region` and
  `aws:PrincipalAccount` in `target_account_ids`.
- **E** mean R plus `aws:ResourceTag/project = project_tag`.
- **C** mean R plus `aws:RequestTag/project = project_tag` and
  `ForAllValues:StringEquals` on `aws:TagKeys` allowing only canonical
  `Name`, `env`, `managed`, `project`, `service` keys.

The principal-account condition constrains the caller's account, not ownership of
every returned shared resource. ARN account segments separately scope writes.
The matrix shows each action's compatible resource projection. For compactness,
equal-condition EC2 actions may share a statement containing the ARN union;
unsupported action/resource-type combinations grant no additional permission.

### Access Admin: six SSO actions

Every row also requires the administrative `aws:PrincipalAccount` input.

| Actions | Resources | Authorization meaning |
| --- | --- | --- |
| `sso:CreateAccountAssignment`, `sso:DeleteAccountAssignment` | I + P + A | All three resource types are required; exact targets/profiles only |
| `sso:ListAccountAssignments` | I + P + A | Read assignments for approved targets and profiles |
| `sso:DescribePermissionSet` | I + P | Read the two approved profile definitions |
| `sso:DescribeAccountAssignmentCreationStatus`, `sso:DescribeAccountAssignmentDeletionStatus` | I | Poll known asynchronous request IDs; instance-wide metadata scope |

No assignment action has `Resource = "*"`. Access Admin's own Permission Set ARN
is excluded. There is no permission-set editing, explicit
`sso:ProvisionPermissionSet` grant, managed-policy attachment, direct IAM or
EC2/workload write, Identity Store membership management, PassRole, or secret
access. A successful `CreateAccountAssignment` automatically provisions the
approved Permission Set into the target account and attaches its policy to the
Identity Center-managed IAM role. That necessary assignment side effect does not
grant direct role or Permission Set administration. Console navigation and principal discovery may need
extra permissions that are deliberately not granted; external workflows must
supply approved existing user/group identifiers.

### Developer: 27 EC2 actions for the current VPC lifecycle

| Actions | Resources | Conditions |
| --- | --- | --- |
| `ec2:CreateVpc` | New V | C |
| `ec2:CreateSubnet` | New S **and existing V** | C on S; separate E statement on V |
| `ec2:CreateInternetGateway` | New G | C |
| `ec2:CreateRouteTable` | New T **and existing V** | C on T; separate E statement on V |
| `ec2:DeleteVpc` | V | E |
| `ec2:DeleteSubnet` | S | E |
| `ec2:DeleteInternetGateway` | G | E |
| `ec2:AttachInternetGateway`, `ec2:DetachInternetGateway` | Both G and V | E on both |
| `ec2:DeleteRouteTable`, `ec2:CreateRoute`, `ec2:ReplaceRoute`, `ec2:DeleteRoute` | T | E; destination/next-hop not constrained by IAM |
| `ec2:ModifyVpcAttribute` | V | E; no undocumented attribute-name/value constraint |
| `ec2:ModifySubnetAttribute` | S | E; no undocumented attribute-name/value constraint |
| `ec2:AssociateRouteTable`, `ec2:ReplaceRouteTableAssociation`, `ec2:DisassociateRouteTable` | T + S | E on applicable authorized resources; no subnet-only or main-table exclusion guarantee |
| `ec2:CreateTags` during creation | Exact corresponding V/S/G/T | C and exact `ec2:CreateAction` paired with that resource's create API |
| `ec2:CreateTags`, `ec2:DeleteTags` after creation | V/S/G/T | E; `ForAllValues:StringNotEqualsIgnoreCase` excludes `project`; `Null: aws:TagKeys = false` |
| Five metadata actions listed below | Wildcard or V as documented below | R or E |
| `ec2:DescribeNetworkAcls`, `ec2:DescribeSecurityGroups` | `*` | R; Developer only, provider VPC default-resource metadata reads |

Creation grants are separate per new resource type, so a request tag cannot
substitute for authorization on an existing parent VPC. Creation-time tagging
works only in the service-supplied create context. Canonical tag-key restrictions
avoid ambiguous `project`/`Project` duplicates during creation. Later tag edits
cannot set/delete any case variant of project, adopt an unrelated resource into
the authorization scope, or use an omitted tag list to delete all tags.

All prior 20 actions were rechecked against the official action/resource/condition
tables, including parent-VPC authorization, both sides of IGW attachment, the
service-supplied tag-on-create context, and protection against adopting resources
by changing project. The seven additions are the five lifecycle writes below
and two provider metadata reads. There are no intentionally omitted operations
identified for the implemented explicit-IPv4-CIDR VPC path. This is an offline
design assessment, not proof that deployment or deletion will succeed in AWS.

### Service-specific composition and quotas

Developer's reviewed **27 EC2 actions** remain in the existing inline resource.
The six Secrets Manager actions now live in one workload-account-owned managed
policy, attached by fixed name/path. Access Admin and Operator are unchanged.
The prior compact EC2 statements are retained; future services should add a
separately reviewed, bounded service policy rather than grow this inline
indefinitely. No arbitrary policy/name/path input or speculative service is added.

| Actual synthetic fixture | Before | After | Limit / new headroom |
| --- | --- | --- | --- |
| Developer inline, two targets / `test-portfolio` | 9,877 bytes | 7,184 bytes | 10,240 / 3,056 bytes |
| Developer inline, two targets / full portfolio project | 10,048 bytes | 7,301 bytes | 10,240 / 2,939 bytes |
| Account Secrets Manager policy / `test-portfolio` | Part of monolith | 2,346 characters | 6,144 / 3,798 characters |

Compact policy inputs are ASCII, so native preconditions measure actual encoded
size correctly. Identity Center allows one inline document, at most 32,768 total
bytes and **10,240 non-whitespace bytes**; the compact inline guard satisfies both.
IAM customer-managed policies have an independent **6,144 non-whitespace character**
limit. Oversized account/project/region configurations are rejected, not widened.
All three Permission Sets, three inline resources, one Developer-only reference
and the one per-account policy are checked from actual mocked-plan inventories.

Current Identity Center documentation lists **25 managed policies per Permission
Set**. The current IAM quota table lists **20 default / 25 maximum policies per
role**, while the Identity Center page's footnote still says 10: the sources are
inconsistent about the role default. The repository therefore uses a clearly
**conservative portfolio budget of 10**, not a claim that 10 is today's IAM default.
The one configured reference is checked against both budget 10 and service limit
25. Externally managed attachments and each target's actual IAM quota must still
be verified before provisioning; this module does not discover or change quotas.
Do not combine this nonexclusive attachment with an exclusive attachment manager.

The six removed Secrets Manager grants preserve the prior conditions within the
owning account. Previously a principal in any approved account could match any
approved account's secret ARN; the managed policy intentionally narrows both its
principal condition and resource ARN to its own account. The effective union is
compared against an approved Terraform-rendered synthetic baseline, not merely
an action count. EC2, Access Admin and Operator remain identical; fifteen deliberate
mutations verify that the comparison rejects widened or missing privileges.

The approved baseline itself stays frozen and hash-pinned. Before comparison the
checker projects it through the Owner-approved tag key rename of
[deployment configuration](../../../docs/deployment-configuration.md#5-tags)
(`Project`→`project`, `Environment`→`env`, `ManagedBy`→`managed`,
`Service`→`service`, `Name` unchanged). Only `aws:RequestTag/<key>` and
`aws:ResourceTag/<key>` condition keys and `aws:TagKeys` values are renamed; every
action, resource, operator and value stays frozen, and an unknown key fails
closed. Three of the fifteen mutations reject a pre-rename condition key, the
pre-rename creation key list and an extra creation key.

### Five-action authorization decisions

The [EC2 SAR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html)
and [official EC2 JSON](https://servicereference.us-east-1.amazonaws.com/v1/ec2/ec2.json)
establish supported action/resource/key combinations. HTML asterisks establish
required resource types; the JSON v1.5 schema does not encode those asterisks.
V, S and T use the exact partition, region and account ARN patterns defined above.

| Exact action and API evidence | Required / associated resources | Current provider need and remaining capability |
| --- | --- | --- |
| [`ec2:ModifyVpcAttribute`](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifyVpcAttribute.html) | Required VPC, `arn:${Partition}:ec2:${Region}:${Account}:vpc/${VpcId}`; no additional parent authorization listed | Provider sets DNS hostnames true and repairs DNS drift. The grant also permits other exposed VPC attributes, including disabling DNS, on matching VPCs. |
| [`ec2:ModifySubnetAttribute`](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifySubnetAttribute.html) | Required subnet, `arn:${Partition}:ec2:${Region}:${Account}:subnet/${SubnetId}`; VPC is a supported context key, not a separately listed required resource | Provider sets public-IP/IPv6 assignment flags when the returned/current values differ. The grant can also enable those flags or change other exposed subnet attributes. |
| [`ec2:AssociateRouteTable`](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_AssociateRouteTable.html) | Required route table, `arn:${Partition}:ec2:${Region}:${Account}:route-table/${RouteTableId}`; subnet is request-dependent; gateway/pool types are also listed | Provider create sends route table and subnet IDs. Grant T + S with E; no gateway/pool ARN grants. The action is not an IAM guarantee of subnet-only use. |
| [`ec2:ReplaceRouteTableAssociation`](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ReplaceRouteTableAssociation.html) | Required route table; subnet/gateway/pool types request-dependent; no association ARN type | Provider update sends association ID and new route table ID. The same API can replace a VPC main route table; the policy cannot reliably exclude this. |
| [`ec2:DisassociateRouteTable`](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DisassociateRouteTable.html) | Route table/subnet/gateway/pool types listed with no universally required starred type | Provider delete sends association ID. A disassociated subnet falls back to the main route table; this can change effective routing. Grant only T + S with E. |

Supported keys for the selected resource types, in addition to global R:

| Operations / resource | Published service keys | Keys actually used |
| --- | --- | --- |
| ModifyVpcAttribute / V | `aws:ResourceTag/${TagKey}`, `ec2:ResourceTag/${TagKey}`, `ec2:Attribute`, `ec2:Attribute/${AttributeName}`, `ec2:Tenancy`, `ec2:VpcID`; action-level `ec2:Region` | `aws:ResourceTag/project` plus R |
| ModifySubnetAttribute / S | Tag keys above, both Attribute keys, `ec2:AvailabilityZone`, `ec2:AvailabilityZoneId`, `ec2:SubnetID`, `ec2:Vpc`; action-level `ec2:Region` | `aws:ResourceTag/project` plus R |
| All three association actions / T | Tag keys above, `ec2:RouteTableID`, `ec2:Vpc`; action-level `ec2:Region` | `aws:ResourceTag/project` plus R |
| All three association actions / S | Tag keys above, `ec2:AvailabilityZone`, `ec2:AvailabilityZoneId`, `ec2:SubnetID`, `ec2:Vpc`; action-level `ec2:Region` | `aws:ResourceTag/project` plus R |

`ec2:Attribute` and `ec2:Attribute/${AttributeName}` are documented String keys.
The [EC2 IAM guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-policies-for-amazon-ec2.html)
uses a ModifyImageAttribute string example; it does not establish the exact
VPC/subnet Boolean context names and values needed to enforce our DNS/public-IP
settings. No guessed Boolean, attribute-selection or attribute-value condition
is used. Terraform fixed values and plan review are not IAM parameter controls.

The references do not establish that every old/new route table and subnet is
always evaluated for an association-ID request. Restrictions on the project tag apply to
the resources actually authorized, not an invented universal parent check.
There is no supported `ec2:IsMain` discriminator or association ARN here.
Review main-association IDs, implicitly associated subnets and routing impact
before external execution. Direct Developer rights can bypass procedural
approval; enforced independent execution would require a separately approved
design removing those direct rights. That redesign is not implemented.

Provider evidence is pinned to v6.72.0:
[VPC](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_.go),
[subnet](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_subnet.go),
and [route-table association](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_route_table_association.go).
The module's routing and public-IP defaults are unchanged.

### Secrets Manager: six Developer actions, one Operator action

Developer's six actions are generated by `iam_account_policies`, not this
module's inline document. For that policy, let **Q** be
`arn:<partition>:secretsmanager:<region>:<account_id>:secret:*`, **Rₐ** be the
explicit region plus scalar `aws:PrincipalAccount = account_id`, **Eₐ** add the
matching project resource tag, and **Cₐ** add the project request tag plus the five
canonical creation keys. Operator keeps its previous multi-target Q/R/E scope.
Q contains explicit partition/region/account segments;
`SecretId` includes the service-assigned suffix and may contain `/` from the name.
All six actions require the SAR `Secret` resource type. The per-account policy
uses the same five canonical creation keys and project identity as the roots.

| Profile / exact action | Resource | Conditions / purpose |
| --- | --- | --- |
| Developer `secretsmanager:CreateSecret` | Q | Cₐ; `Null: secretsmanager:AddReplicaRegions = true`, `BoolIfExists: secretsmanager:ForceOverwriteReplicaSecret = false`; create a tagged container, no requested replicas/overwrite |
| Developer `secretsmanager:TagResource` with project supplied | Q | Cₐ **and** existing/resource `aws:ResourceTag/project = project_tag`; creation authorization or reaffirming the same project, not adopting unrelated secrets |
| Developer `secretsmanager:DescribeSecret`, `secretsmanager:GetResourcePolicy` | Q | Eₐ; provider refresh reads both, even when no resource policy is managed |
| Developer `secretsmanager:TagResource`, `secretsmanager:UntagResource` for other tags | Q | Eₐ; `ForAllValues:StringNotEqualsIgnoreCase` excludes project; `Null: aws:TagKeys = false` |
| Developer `secretsmanager:DeleteSecret` | Q | Eₐ; `BoolIfExists: ForceDeleteWithoutRecovery = false`; NumericGreaterThanEquals RecoveryWindowInDays 7 and NumericLessThanEquals 30 (both `secretsmanager:` keys) |
| Operator `secretsmanager:DescribeSecret` | Q | E; metadata only, no list/policy/value read or mutations |

CreateSecret with tags also requires TagResource. The official
[IAM Secrets Manager ABAC tutorial](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_attribute-based-access-control.html)
documents creation with matching resource/request tags. Requiring both project
values and exact canonical keys permits that path without a request-tag-only
Allow that could adopt an unrelated existing secret. It can reaffirm the same
project on an existing matching resource; there is no invented Secrets Manager
`CreateAction` key. Other project casing variants cannot be introduced through
these grants. Governance of the project tag by other identities remains an external trust
boundary.

The provider's safe deletion request supplies the recovery period and omits the
force flag. BoolIfExists permits absence/false while rejecting true; numeric
bounds require an explicit 7–30 day window. A caller omitting the window does not
satisfy this policy, even though the service has a default. Module validation also
rejects zero/fractional recovery windows. External restore remains a separately
approved operation; RestoreSecret is not used by the implemented provider path.

**CreateSecret is not an IAM-enforced metadata-only capability.** Its API accepts
initial SecretString/SecretBinary payloads, and the published keys provide no
reliable absence guard. Developer can initialize a value in a new in-scope secret;
Terraform never receives or manages that value. `UpdateSecret` is deliberately
withheld because it can also overwrite values; description and encryption-key
changes therefore cannot be completed using this human Developer policy alone.
A future controlled deployment identity needs separately reviewed permissions
and an execution process that excludes payloads. Removing direct human create
rights would be an additional design trade-off, not an effect of documentation.

The production scope intentionally grants **no** GetSecretValue,
BatchGetSecretValue, PutSecretValue, UpdateSecretVersionStage, rotation,
RestoreSecret, ListSecrets, PutResourcePolicy, DeleteResourcePolicy or KMS access.
The optional resource-policy model is omitted by the new module; workload
identity policies and any approved deployment identity are separate designs.
GetResourcePolicy is a required provider metadata read, not policy-edit authority.
CMK creation/use requires independent KMS/key-policy review; no Decrypt or other
KMS permission is automatically added to any human profile. Access Admin remains
unchanged and has no direct Secrets Manager action; its self-assignment risk
continues to apply to these newly reviewed Developer capabilities.

### Developer and Operator: metadata visibility

| Exact action | Resource | Why / restriction |
| --- | --- | --- |
| `ec2:DescribeVpcs` | `*` | VPC configuration metadata; no resource-level authorization support; R |
| `ec2:DescribeSubnets` | `*` | Subnet configuration metadata; no resource-level authorization support; R |
| `ec2:DescribeInternetGateways` | `*` | IGW attachment metadata; no resource-level authorization support; R |
| `ec2:DescribeRouteTables` | `*` | Route/association metadata; no resource-level authorization support; R |
| `ec2:DescribeVpcAttribute` | V | DNS/VPC attribute metadata; E |

Operator retains these five EC2 actions, plus only the scoped Secrets Manager
DescribeSecret above, and has no write grants. The four wildcard
describes cannot be project-filtered through IAM and can expose other-project
or shared-resource network metadata in the permitted region/account context.
They do not retrieve workload content. Do not put secrets in tags or metadata.

Developer additionally has only `ec2:DescribeNetworkAcls` and
`ec2:DescribeSecurityGroups`, both `Resource = "*"` with R because these actions
lack resource-level authorization. The v6.72.0 VPC read path queries default
NACL/security-group metadata; missing permissions produce warnings and missing
computed metadata. These reads can expose other-project/shared configuration,
including network rules, within the account/region context. They grant no ACL or
security-group writes. Operator's EC2 grants remain exactly the five actions above.

There is no DescribeTags/AvailabilityZones convenience permission, CloudWatch
metrics/log events, Secrets Manager plaintext, SSM parameter values, KMS Decrypt,
S3 object content, database data, IAM management, or IAM Identity Center assignment
capability in Operator. Monitoring extensions need a real requirement and review.

## Privilege-escalation and operational limitations

- Exact profile/account scoping **does not prevent self-assignment**. Access Admin
  may assign Developer/Operator to itself or to groups it belongs to. IAM does not
  offer the required recipient/self comparison here. Require independent access
  approval, separate group-membership administration, CloudTrail monitoring, and
  periodic access reviews. SSO SAR/JSON lists no supported recipient-ID/type,
  self-comparison or membership condition for these assignment actions. These
  procedural and detective controls do not technically prevent bypass. Enforcing
  independent approval requires removing direct human assignment writes and a
  separately reviewed controlled executor; this PR preserves the approved profile.
  See the [operations runbook](../../../docs/iam-access-operations.md) for request,
  independent approval, external execution, CloudTrail and reconciliation steps.
- Status APIs authorize only the instance. Known request IDs can reveal assignment
  metadata outside approved target/profile pairs; no status-list enumeration is
  granted, but the published model cannot enforce a narrower polling scope.
- Route write permissions authorize a tagged route table, not its gateway target
  or destination. They cannot enforce the VPC module's IGW-only routing intent.
  Require external plan/change review and monitoring for approved network changes.
- Attribute writes do not enforce DNS/public-IP/IPv6 values; association writes
  do not guarantee subnet-only operations or exclude main-table changes. Review
  exact API parameters, association IDs, state and resulting topology externally.
- These identity policies are not permissions boundaries or SCPs. Other policies,
  Permission Sets, privileged tag editors, account governance and resource policies
  affect effective access. Trusted governance of the project tag is essential.
- Creation covers the reviewed explicit-CIDR paths. IPAM pool authorization and
  other optional EC2 dependencies are not granted or tested.
- The new managed reference requires an existing matching policy in every assigned
  account; it creates none. Account policy content updates do not deploy themselves
  to other accounts. Both inline/account quota guards and actual attachment quotas
  require continued review; independently owned policy drift can alter access.
- MFA must be enforced by the workforce identity provider / Identity Center
  authentication setup. Do not assume the IAM-user MFA-present key enforces MFA
  for federated sessions. Use temporary workforce sessions, not IAM user keys.
- No live AWS authorization, account membership, delegated-admin registration,
  policy simulation, Access Analyzer, provisioning or integration test has run.
  Offline JSON and mock tests cannot prove successful or complete authorization.

## Example future management-root call (not integrated)

For a separately authorized root under
`infra/services/<environment>/<region>/<service>/`, with provider and state owned
by that root:

```hcl
module "human_access" {
  source                    = "../../../../modules/iam_access"
  name_prefix               = "portfolio"
  instance_arn              = var.organization_identity_center_instance_arn
  administration_account_id = var.identity_center_administration_account_id
  target_account_ids        = var.approved_workload_account_ids
  target_region             = var.portfolio_region
  project_tag               = "aws-terraform-portfolio"
}
```

Inputs above are intentionally supplied externally, without real identifiers or
credentials in the example. This call is not in any service root. The current VPC
module and dev root remain unchanged. Bootstrap provisioning and manual account
assignments, including the administrative-account entry point, require separate
approval outside Codex Cloud.

The [runbook's placeholder table](../../../docs/iam-access-operations.md#configuration-and-administrative-prerequisites)
uses `REPLACE_WITH_EXISTING_IDENTITY_CENTER_INSTANCE_ARN`,
`REPLACE_WITH_12_DIGIT_ADMIN_ACCOUNT_ID` and
`REPLACE_WITH_12_DIGIT_WORKLOAD_ACCOUNT_ID` as documentation labels only. Map
verified real identifiers to the required input variables in a future authorized
root through its approved external variable-binding process. Do not load invalid
placeholder strings or credentials into Terraform. Native tests retain only
format-correct synthetic identifiers; no active tfvars are added.

## Intentionally ungranted operations

The matrices above are exhaustive Allow lists, not a generic EC2 administration
policy. All other actions remain ungranted, including these reviewed boundaries:

| Excluded capability | Reason |
| --- | --- |
| VPC/subnet CIDR association, IPAM/pool allocation, IPv6 pool operations | Not used by the current explicit IPv4 implementation; optional dependencies need separate review |
| Additional main-table/gateway-association permissions or ARN expansion | Not requested by the module; no extra grants added, although ReplaceRouteTableAssociation retains the main-table residual explained above |
| Security-group/NACL writes, NAT gateways, endpoints, peering, VPN, transit gateway, EC2 instances | Not implemented; no speculative write access |
| `ec2:DescribeTags`, `ec2:DescribeAvailabilityZones` and general describe wildcards | Not needed by the implemented provider paths; no console convenience expansion |
| Project-tag changes, unscoped creates, all-resource EC2 writes | Would weaken the resource ownership boundary |
| Permission Set/policy editing, Access Admin assignment targets, Identity Store membership writes, organization/delegated-admin setup, explicit `sso:ProvisionPermissionSet` | Preserve profile separation and bootstrap/governance boundaries; approved assignment still auto-provisions |
| IAM role/user/policy administration and `iam:PassRole` | No workload execution roles or deployment identity in this phase |
| Secret-value retrieval/existing-value updates, SSM values, KMS Decrypt, S3 objects, database content, logs/events and future service writes | No retrieval or speculative services; CreateSecret still accepts initial payloads as explicitly documented; Operator stays metadata-only |

## Future deployment, migration and rollback

This is a design only: no root integration, assignments or AWS deployment exists.
For any separately authorized external execution:

1. Review/export policies and perform the optional official checks using the
   [validation toolkit](../../../scripts/aws-policy-validation/README.md). These
   checks do not establish effective authorization or production readiness.
2. Each workload account's owning root creates/verifies its fixed-name/path policy
   using that account's explicitly restricted provider. Check exact account,
   region, project, policy JSON/default version, quota and existing attachments.
3. Only after every target is ready, add the Developer reference. Provider 6.72.0
   attaches it and automatically provisions all already provisioned accounts.
4. Remove the Secrets Manager statements from the inline policy and verify
   provisioning/access again. The inline resource depends on the attachment to
   serialize this initial transition; separate account roots still need external
   orchestration. Do not assume Terraform dependencies span states/accounts.
5. Reconcile policy identities/content/default versions in all accounts, the
   Developer reference, IAM role attachments and provisioning outcomes. No account
   assignments are created by this migration.

For rollback, retain workload policies. Restore the reviewed old inline and
provision it **before** detaching the reference only when the old inline still
fits the approved scope/quota. If it cannot fit, keep the reference and restore a
reviewed managed-policy version instead; do not drop access or widen scope to
force the monolith back in. Detaching the reference also auto-provisions and must
be reviewed. Do not delete workload policies until all relevant references/role
attachments and drift checks establish that removal is safe.

IAM policy-content updates are owned by each account root, create a new default
policy version and require review across every target. Changing an account policy
does not call SSO provisioning or replicate that policy to other accounts. Fixed
name/path changes require a new explicit migration; do not mix exclusive managers
or reuse policy identity for unrelated unreviewed content.

## Future service expansion contract

Beyond the reviewed secret-container operations, do not add IAM workload roles,
secret-value access, Lambda, S3, CloudWatch, API Gateway, ECS or PassRole writes
merely because they are planned. Every future module PR
must explicitly review: exact IAM actions, resource ARNs, request/resource
conditions, operational purpose, escalation risks, new security tests and
documentation. Future PassRole must name approved workload roles and service
principals with `iam:PassedToService` where applicable. Workload roles must not
inherit these human-access policies.

## Verification and evidence

Requires Terraform `>= 1.17.0, < 2.0.0` and `hashicorp/aws >= 6.72.0, < 7.0.0`.
Tested on Linux amd64 with **Terraform 1.17.0 / AWS Provider 6.72.0**:

```sh
cd infra/modules/iam_access
terraform version
terraform fmt -check -recursive
terraform init -backend=false -input=false -no-color
terraform validate -no-color
terraform test -no-color
```

Formatting, initialization and validation passed; native tests passed **39 runs,
zero failed**. All prior 34 run names remain. A native alternate-module fixture
renders the actual account policy; retained Secrets Manager assertions inspect
that policy rather than an empty inline placeholder. New attachment, quota and
multi-account/project cases validate the split without weakening the old guards.
Coverage includes policy JSON,
binding, account/region/resource, creation-parent, tag-integrity, Operator
confidentiality, forbidden-privilege and administrative-input regressions.
Every run explicitly uses `command = plan` and `mock_provider "aws"`; only computed
Permission Set ARNs are overridden. Generated plan inventory was independently
checked: exactly three Permission Sets, three inline policies and one Developer reference,
plus exactly one account-owned managed policy in its independent module. No
identities or assignments are created. Actual generated IAM JSON was reviewed against official tables.

Validation excluded inherited AWS credential/profile and Terraform input bindings,
used `/dev/null` for shared AWS config/credentials, and disabled metadata lookup.
Initialization reused the retained, previously verified provider package with the
existing generated root lock as a checksum seed. No checksums, TLS checks or
provider authentication controls were disabled.
No child-module lock is committed; the existing root lock remains unchanged.
Fresh provider installation normally needs registry/release network access.

No real AWS plan, apply, destroy, credentials or account API calls occurred.
Mock plans are not integration tests and these undeployed definitions are not
active access identities. Git whitespace, file scope, credential/secret and
account-identifier checks supplement the tests.

### Static authorization-reference check

The stdlib-only [checker](tests/check_authorization_reference.py) consumes official
JSON and the **actual rendered policies** from a successful native test event
stream. First generate both successful JSONL streams using the
[toolkit export guide](../../../scripts/aws-policy-validation/README.md#export-actual-synthetic-policies);
run from this module with both streams, preserving test failure:

```sh
curl --fail --silent --show-error https://servicereference.us-east-1.amazonaws.com/v1/ec2/ec2.json -o /tmp/aws-ec2-authorization.json
curl --fail --silent --show-error https://servicereference.us-east-1.amazonaws.com/v1/sso/sso.json -o /tmp/aws-sso-authorization.json
curl --fail --silent --show-error https://servicereference.us-east-1.amazonaws.com/v1/secretsmanager/secretsmanager.json -o /tmp/aws-secretsmanager-authorization.json
terraform test -no-color -json -verbose > /tmp/iam-hardening-tests.jsonl &&
python3 tests/check_authorization_reference.py \
  --ec2-reference /tmp/aws-ec2-authorization.json \
  --sso-reference /tmp/aws-sso-authorization.json \
  --secretsmanager-reference /tmp/aws-secretsmanager-authorization.json \
  --test-events /tmp/iam-hardening-tests.jsonl \
  --account-test-events /tmp/account-policies-tests.jsonl
python3 tests/check_authorization_reference.py --self-test
```

All three public JSON endpoints returned HTTP 200, schema v1.5. The Secrets
Manager URL was discovered from the canonical SAR HTML link, not guessed. Current checks passed
for all four generated policies and exact seven-resource Identity Center plus
one-resource account-policy inventories.
Twenty-four negative mutation self-tests passed: the nine retained cases cover
unknown/wildcard actions, wildcard
write resources, unsupported ARN/key, wrong resource-tag context, missing parent
VPC, optional IPAM resource without the required VPC, and NotAction are rejected.
Eight additional Secrets Manager mutations reject fake payload-absence keys,
unsupported action/resource/condition combinations and unscoped ARNs; a valid
slash-containing secret ARN is accepted. Failed/skipped/errored summaries are
rejected. Seven added inventory mutations reject wrong profiles, names, paths
and unexpected IAM resources. The checker streams potentially large verbose output and does not contact AWS.

It validates action names, ARN type compatibility, action/resource-specific keys
and a manually reviewed required-resource overlay. Global exceptions are only
`aws:PrincipalAccount` and `aws:RequestedRegion`. JSON does not encode HTML's
required-resource asterisks; the checker cannot prove condition values, API
runtime context, parameter enforcement, all parent-resource evaluation, main-table
exclusion, full lifecycle success, other live account/service quotas or effective access. Native exact-policy
regressions complement this structural check; neither simulates IAM.

### Offline Design Readiness: complete

Supported actions, selected ARN patterns and condition keys are researched;
the current VPC operations are represented; security boundaries and residuals
are documented. Formatting/init/validation, 39 IAM mock tests, 24 account-policy tests and static reference
checks pass. This assessment is limited to the reviewed implementation and
official public references, not an AWS service acceptance or execution result.

### Live Authorization Readiness: not complete

Before authorized external use, verify actual IAM evaluation and other policies,
account/partition/region and project-tag governance, instance ownership and
management/delegated prerequisites, customer-managed-key needs, policy quotas,
runtime API authorization and topology, MFA, and assignment approval/audit/
reconciliation. Test through a separately authorized environment. No policy
simulation, Access Analyzer, authenticated AWS APIs or live authorization checks
were performed in Codex Cloud.

Official sources reviewed on 2026-11-07 (documentation reads only):

- [IAM Identity Center Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam-identity-center.html)
- [EC2 Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html)
- [Official EC2 machine-readable reference](https://servicereference.us-east-1.amazonaws.com/v1/ec2/ec2.json)
- [Official IAM Identity Center machine-readable reference](https://servicereference.us-east-1.amazonaws.com/v1/sso/sso.json)
- [Secrets Manager Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html)
- [Official Secrets Manager machine-readable reference, linked by the SAR](https://servicereference.us-east-1.amazonaws.com/v1/secretsmanager/secretsmanager.json)
- [Secrets Manager CreateSecret API](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_CreateSecret.html)
- [Secrets Manager UpdateSecret API](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_UpdateSecret.html)
- [Secrets Manager DeleteSecret API](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DeleteSecret.html)
- [Secrets Manager TagResource API](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_TagResource.html)
- [Secrets Manager ABAC creation/tag example](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_attribute-based-access-control.html)
- [IAM Identity Center policy quotas](https://docs.aws.amazon.com/singlesignon/latest/userguide/limits.html)
- [IAM customer-managed policy and role quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
- [Customer-managed name/path/account requirements](https://docs.aws.amazon.com/singlesignon/latest/userguide/howtocmp.html)
- [Permission Set custom policy responsibilities](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetcustom.html)
- [Provider 6.72.0 customer-managed reference behavior](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ssoadmin/customer_managed_policy_attachment.go)
- [Principal account and other global condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html)
- [String/set condition operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html#Conditions_String)
- [EC2 creation-time tagging](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/supported-iam-actions-tagging.html)
- [Organization instances](https://docs.aws.amazon.com/singlesignon/latest/userguide/organization-instances-identity-center.html)
- [Permission Set delegation](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetdelegation.html)
- [Account assignment and automatic provisioning](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_CreateAccountAssignment.html)
- [Registering a delegated administrator](https://docs.aws.amazon.com/singlesignon/latest/userguide/delegated-admin-how-to-register.html)
- [Customer-managed encryption keys](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-customer-managed-keys.html)

The old SAR URLs `list_awsiamidentitycenter.html` and `list_amazonec2.html` now
return redirect/index content even with HTTP 200; verification used the canonical
service tables linked above, not merely a successful HTTP status.
