# Human access through IAM Identity Center

This module defines three distinct Permission Sets and their custom inline
policies in an **existing organization IAM Identity Center instance**. It does
not create an instance, users, groups, access keys, passwords, account assignments,
Organizations configuration, workload roles, or deployment identities. Nothing
has been deployed or connected to a real AWS account.

| Fixed Permission Set name | Responsibility | Session |
| --- | --- | --- |
| `Portfolio-Access-Admin` | Assign/revoke only Developer and Operator in approved workload accounts | One hour (`PT1H`) |
| `Portfolio-Developer` | Reviewed, project-scoped VPC management subset | One hour (`PT1H`) |
| `Portfolio-Operator` | VPC configuration metadata only | One hour (`PT1H`) |

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
| `project_tag` | `string` | 1-63 lowercase letters/digits/hyphens, starting with a letter; Project authorization tag value |
| `tags` | `map(string)` | Optional, default `{}`; Permission Set inventory tags only, never policy content |

`administration_account_id` is intentionally separate from workload targets:
it binds the administrative caller context without pretending target-account
scoping proves that the caller is a delegated administrator.

| Source | Configuration |
| --- | --- |
| Root Override | Explicit instance, administrative account, target accounts, region, project identity, inventory prefix and optional inventory tags |
| Module Default | Additional Permission Set `tags = {}` |
| Module Fixed | Three Permission Set names, one-hour sessions, reviewed actions/resource types/conditions, EC2 creation tag keys, module-owned Name/Project inventory tags |

Permission Set names remain exactly those listed above; `name_prefix` does not
rename access identities. Module-owned `Name` and `Project` inventory tags win
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

## Complete permission matrix

All actions below are exact names. Let:

- **I** be the explicit instance ARN.
- **P** be only this module's exact Developer and Operator Permission Set ARNs.
- **A** be `arn:<partition>:sso:::account/<approved-target-id>` for each target.
- **V/S/G/T** be, respectively, the approved VPC/subnet/internet-gateway/route-table
  patterns `arn:<partition>:ec2:<target_region>:<approved-target-id>:<type>/*`.
- **R** require `aws:RequestedRegion = target_region` and
  `aws:PrincipalAccount` in `target_account_ids`.
- **E** mean R plus `aws:ResourceTag/Project = project_tag`.
- **C** mean R plus `aws:RequestTag/Project = project_tag` and
  `ForAllValues:StringEquals` on `aws:TagKeys` allowing only canonical
  `Environment`, `ManagedBy`, `Name`, `Project`, `Service` keys.

The principal-account condition constrains the caller's account, not ownership of
every returned shared resource. ARN account segments separately scope writes.

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

### Developer: 20 EC2 actions, a verified subset

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
| `ec2:CreateTags` during creation | Exact corresponding V/S/G/T | C and exact `ec2:CreateAction` paired with that resource's create API |
| `ec2:CreateTags`, `ec2:DeleteTags` after creation | V/S/G/T | E; `ForAllValues:StringNotEqualsIgnoreCase` excludes `Project`; `Null: aws:TagKeys = false` |
| Five metadata actions listed below | Wildcard or V as documented below | R or E |

Creation grants are separate per new resource type, so a request tag cannot
substitute for authorization on an existing parent VPC. Creation-time tagging
works only in the service-supplied create context. Canonical tag-key restrictions
avoid ambiguous `Project`/`project` duplicates during creation. Later tag edits
cannot set/delete any case variant of Project, adopt an unrelated resource into
the authorization scope, or use an omitted tag list to delete all tags.

**Deferred, not granted:** `ec2:ModifyVpcAttribute`, `ec2:ModifySubnetAttribute`,
`ec2:AssociateRouteTable`, `ec2:ReplaceRouteTableAssociation`, and
`ec2:DisassociateRouteTable`. Published attribute keys do not establish the exact
VPC/subnet value semantics needed here, and association resource listings do not
establish a subnet-only/no-main-association guarantee. Do not invent conditions.
These missing actions mean Developer **cannot fully provision or destroy the
existing VPC Terraform module**. Adding them needs a separate reviewed policy
change and external authorization validation, not wildcard expansion.

### Developer and Operator: metadata visibility

| Exact action | Resource | Why / restriction |
| --- | --- | --- |
| `ec2:DescribeVpcs` | `*` | VPC configuration metadata; no resource-level authorization support; R |
| `ec2:DescribeSubnets` | `*` | Subnet configuration metadata; no resource-level authorization support; R |
| `ec2:DescribeInternetGateways` | `*` | IGW attachment metadata; no resource-level authorization support; R |
| `ec2:DescribeRouteTables` | `*` | Route/association metadata; no resource-level authorization support; R |
| `ec2:DescribeVpcAttribute` | V | DNS/VPC attribute metadata; E |

Operator has exactly these five actions and no write grants. The four wildcard
describes cannot be Project-filtered through IAM and can expose other-project
or shared-resource network metadata in the permitted region/account context.
They do not retrieve workload content. Do not put secrets in tags or metadata.

There is no DescribeTags/AvailabilityZones convenience permission, CloudWatch
metrics/log events, Secrets Manager plaintext, SSM parameter values, KMS Decrypt,
S3 object content, database data, IAM management, or IAM Identity Center assignment
capability in Operator. Monitoring extensions need a real requirement and review.

## Privilege-escalation and operational limitations

- Exact profile/account scoping **does not prevent self-assignment**. Access Admin
  may assign Developer/Operator to itself or to groups it belongs to. IAM does not
  offer the required recipient/self comparison here. Require independent access
  approval, separate group-membership administration, CloudTrail monitoring, and
  periodic access reviews. No ineffective self-assignment condition is simulated.
- Status APIs authorize only the instance. Known request IDs can reveal assignment
  metadata outside approved target/profile pairs; no status-list enumeration is
  granted, but the published model cannot enforce a narrower polling scope.
- Route write permissions authorize a tagged route table, not its gateway target
  or destination. They cannot enforce the VPC module's IGW-only routing intent.
  Require external plan/change review and monitoring for approved network changes.
- These identity policies are not permissions boundaries or SCPs. Other policies,
  Permission Sets, privileged tag editors, account governance and resource policies
  affect effective access. Trusted governance of the Project tag is essential.
- Creation covers the reviewed explicit-CIDR paths. IPAM pool authorization and
  other optional EC2 dependencies are not granted or tested.
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

## Future service expansion contract

Do not add IAM workload roles, Secrets Manager, Lambda, S3, CloudWatch, API Gateway,
ECS or PassRole writes merely because they are planned. Every future module PR
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

Formatting, initialization and validation passed; native tests passed **21 runs,
zero failed**. The original eight WIP tests are retained, with new policy JSON,
binding, account/region/resource, creation-parent, tag-integrity, Operator
confidentiality, forbidden-privilege and administrative-input regressions.
Every run explicitly uses `command = plan` and `mock_provider "aws"`; only computed
Permission Set ARNs are overridden. Generated plan inventory was independently
checked: exactly three Permission Sets and three inline policies, no identities
or assignments. Actual generated IAM JSON was reviewed against official tables.

Validation excluded inherited AWS credential/profile and Terraform input bindings,
used `/dev/null` for shared AWS config/credentials, and disabled metadata lookup.
Initialization reused the retained, previously verified provider package with the
existing generated root lock as a checksum seed and an external filesystem
mirror. No checksums, TLS checks or provider authentication controls were disabled.
No child-module lock is committed; the existing root lock remains unchanged.
Fresh provider installation normally needs registry/release network access.

No real AWS plan, apply, destroy, credentials or account API calls occurred.
Mock plans are not integration tests and these undeployed definitions are not
active access identities. Git whitespace, file scope, credential/secret and
account-identifier checks supplement the tests.

Official sources reviewed on 2026-11-07 (documentation reads only):

- [IAM Identity Center Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam-identity-center.html)
- [EC2 Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html)
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
