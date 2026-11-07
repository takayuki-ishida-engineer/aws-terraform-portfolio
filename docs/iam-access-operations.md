# Human access and network change review

This is an operational design for a separately authorized workflow outside
Codex Cloud. It creates no identities, assignments, roles, approval automation,
logging infrastructure, or AWS resources. The IAM module has not been deployed
or tested against an AWS account. Offline policy checks do not establish live
authorization readiness.

## Configuration and administrative prerequisites

The following labels are documentation placeholders, not Terraform values or
valid configuration. Never put them in active `.tfvars` or `*.auto.tfvars` files.
An authorized operator must supply verified existing identifiers outside this
document; never supply AWS credentials to Codex Cloud.

| Documentation label | Meaning and verification |
| --- | --- |
| `REPLACE_WITH_EXISTING_IDENTITY_CENTER_INSTANCE_ARN` | Existing organization instance; verify ownership, home region and trusted access |
| `REPLACE_WITH_12_DIGIT_ADMIN_ACCOUNT_ID` | Management account or registered delegated administrator operating the instance |
| `REPLACE_WITH_12_DIGIT_WORKLOAD_ACCOUNT_ID` | Approved workload member account, excluding both the management account and the selected administrative account |

An organization instance must be enabled in the Organizations management account.
Delegated-administrator registration requires management-account authority and
is an external prerequisite. Assigning Access Admin in an ordinary member
account does not register that account or establish functional administration.
A delegated administrator cannot administer Permission Sets provisioned in the
management account or enable access to that account. Verify these facts before
bootstrap; input format checks cannot verify them.

Use temporary workforce sessions and enforce MFA through the identity provider
and IAM Identity Center authentication configuration. Do not use IAM user keys
or assume the IAM-user MFA context key enforces MFA for federated sessions.
Existing group membership and its administration require separate review.

## What each control establishes

| Control | Scope and limit |
| --- | --- |
| Exact instance, Permission Set and account ARNs | Restricts assignment administration to the existing instance, Developer/Operator profiles and approved workload targets |
| `aws:PrincipalAccount` | Restricts the requesting principal's account; does not establish delegated registration or identify the assignment recipient |
| Administrative prerequisite review | Verifies instance ownership, management/delegated status, trusted access and excluded accounts outside Terraform |
| IAM Identity Center service authorization | Requires an actual organization instance and management/registered delegated administration; a Permission Set assignment in an ordinary member account does not establish these prerequisites |
| Independent request approval | Records approved intent; remains procedural while the human administrator retains direct assignment write rights |
| CloudTrail review | Provides detective evidence of requests and outcomes; does not prevent an unapproved request |
| Periodic reconciliation | Detects unapproved, expired or changed assignments and relevant group membership |

The current AWS authorization model for account assignments provides no supported
recipient-ID, recipient-type, self-comparison or group-membership condition for
these actions. Permission Set resource tags do not identify the recipient.
Access Admin can assign Developer/Operator to itself or a group it belongs to
within the approved workload accounts. Its own Access Admin Permission Set is
excluded, but this does not prevent that self-assignment path.

This design preserves the existing Access Admin profile and its direct
assignment rights. A holder can bypass a procedural approval flow. Technically
enforced independent approval would require a separately reviewed redesign:
remove direct human assignment write rights and permit writes only through a
distinct controlled execution identity that consumes approved requests. That
identity, its trust, approval mechanism and permissions are not implemented here.
Other policies and group administrators must also be reviewed for bypass paths.

## Access request to reconciliation

1. **Request.** Record the requester, immutable existing recipient ID and type
   (`USER` or `GROUP`), instance, workload account, Developer or Operator
   Permission Set, justification, requested expiry and whether access is added
   or revoked. Supply existing identifiers through the approved external
   process; this module does not grant identity discovery or create identities.
   Expiry requires external tracking and revocation; an account assignment has
   no expiry setting in this module or assignment API.
2. **Independent review.** A different authorized person verifies the requester,
   recipient and account, business need, expiry, separation of duties and
   conflicting access. Review group members and who can change membership,
   including whether the requester or approver benefits from the assignment.
   Reject excluded administrative accounts and unapproved profiles. Record
   approval of the exact request rather than a blanket permission to assign.
3. **Approved external execution.** An independently authorized execution
   identity outside Codex Cloud applies only the approved request and records
   its request identifier and final asynchronous status. The identity's access
   must be reviewed separately; this document grants none. Record failure and
   investigate before retrying. A successful assignment automatically provisions
   the approved Permission Set into the target account; it is an infrastructure
   change even without an explicit `sso:ProvisionPermissionSet` grant.
4. **CloudTrail audit.** Correlate the approval and executor with
   `CreateAccountAssignment` or `DeleteAccountAssignment` events from
   `sso.amazonaws.com`, including time, recipient, account, Permission Set,
   request and outcome where recorded. Investigate unapproved, failed or
   mismatched events. Review group-membership and identity changes from
   `identitystore.amazonaws.com` and `sso-directory.amazonaws.com` as applicable.
   Existing audit retention, protection and reviewer access must be verified;
   this module creates no trail or event processing.
5. **Periodic reconciliation.** At a documented review interval and after
   membership changes, compare actual assignments for approved account/profile
   pairs with approvals and expiry dates. Independently reconcile relevant
   group membership and other privilege paths. Investigate drift and submit
   revocation requests for expired or unapproved access, verifying completion.
   Required enumeration, membership inspection and audit-reader permissions
   need separate review; do not assume this module provides them.

Keep approvals and audit evidence access-controlled. Do not store credentials,
secret values or sensitive workforce records in Git. Known asynchronous status
requests are authorized at instance scope; the current policy cannot confine
their metadata to only the approved account/profile pairs.

## Network change approval and state controls

Developer access is a reviewed network-management capability, not an enforcement
of every network design invariant. This policy does not assert undocumented
attribute-name or Boolean-value condition mappings. Its Project/account/region
restrictions do not enforce DNS/public-IP/IPv6 settings. Route-table
association privileges must not be described as guaranteeing subnet-only
changes or preventing changes to a main association. Route writes do not enforce
the intended gateway, route destination or complete topology.

Before any externally authorized network change:

- Identify the environment, region, service, VPC, affected resources, current
  association IDs and whether an association is the VPC's main association.
  Include subnets relying on the main table implicitly, gateway associations,
  route destinations/targets and the old and proposed attribute values.
- Obtain a Terraform plan through the approved workflow outside Codex Cloud
  when changing Terraform-managed infrastructure. An independent reviewer must
  compare the plan with the current state and approved topology, assess the
  reachability/security impact, and approve the exact change. Treat main-table
  association changes and broad attribute changes as explicit review items;
  ordinary subnet-association approval does not authorize them.
- Use the owning root's provider and state for the correct environment, region
  and service. Keep those states separate, prevent concurrent writers and
  protect any state backups and plan artifacts. Do not introduce an unreviewed
  backend or commit plans/state. Resolve drift before executing an approved
  plan; regenerate and re-review it if the state or intended change changes.
- Use a separately approved external executor with temporary credentials and
  only its reviewed permissions. Record the approved plan/change and result,
  verify the resulting associations, attributes and effective routes, and
  reconcile state and CloudTrail evidence. A recovery plan requires its own
  review; it is not permission for an unreviewed destroy or broad rollback.

No network change, AWS API call, real-account plan, apply or destroy is performed
by this runbook or authorized inside Codex Cloud. Logging, enforcement automation
and any additional execution or inspection privileges require a separate design.

## Secret-container and value responsibilities

The [Secrets Manager module](../infra/modules/secrets_manager/README.md) owns one
metadata container only. Do not send values to Terraform, tests, CI, plans or
state. After an independently authorized external deployment, a separate approved
operational identity initializes/updates values and verifies the intended current
version. This module does not make a value or AWSCURRENT version exist.

Developer can call CreateSecret with initial payload parameters through the AWS
API: no documented IAM condition reliably enforces their absence. The Terraform
resource never supplies those parameters, but that does not constrain a human
using the same action. Account/region/Project scope and creation-tag governance
still apply; direct rights can bypass procedural approval. Existing Access Admin
self-assignment can confer these reviewed Developer capabilities and remains a
separate governance risk.

UpdateSecret is withheld because it can overwrite values; metadata description/
CMK updates require a separately reviewed controlled deployment identity and
payload-free workflow. Resource-policy writes, value retrieval/updates, rotation
and KMS Decrypt are not granted. Operator receives only DescribeSecret metadata;
names, descriptions, tags and policy documents must contain no confidential data.
Provider refresh additionally needs Developer's scoped GetResourcePolicy even
though the module does not own a resource policy.

Review recovery periods, deletion intent and name-reuse impact before scheduled
deletions. Developer must explicitly request 7–30 days and cannot force immediate
deletion through these grants. RestoreSecret is not granted or called by the
module; recovery needs a separately approved external operation before the window
expires. External policies can still affect access and must be reconciled.

## Service-policy ownership, migration and drift

The Developer Secrets Manager policy is now owned by each workload account's
future [account-policy root/module](../infra/modules/iam_account_policies/README.md).
It must exist with canonical name `Portfolio-Developer-SecretsManager`, path `/`,
in **every** assigned account before the administrative Identity Center reference
is provisioned. A policy in the management/delegated account is not sufficient.
Account input values do not select a provider; the owning root must explicitly
select and restrict its provider and be the sole state owner of this identity.

Use the same reviewed region/Project contract across the account policy,
secret metadata and human profiles. Account-specific ARN and PrincipalAccount
conditions intentionally tighten the old multi-account Secrets Manager grant.
The remaining EC2 inline, Operator and Access Admin policies are unchanged.

For separately authorized future deployment or migration:

1. Review actual policy exports and optional official validation results. Verify
   quotas, per-account provider selection and the independent approval below.
2. Create/verify the matching policy/default version in every workload account.
   Check content, name/path, ownership, tags and unauthorized external versions.
3. Attach the fixed Developer reference while old inline permissions remain.
   Provider 6.72.0 automatically provisions to all already provisioned accounts;
   verify completion and failures before continuing.
4. Remove the old Secrets Manager inline statements and verify provisioning again.
   The inline resource depends on the attachment, but there is no cross-state
   dependency on account roots: external orchestration is mandatory.
5. Reconcile account policy documents/default versions, references and actual role
   attachments, provisioning status and approved assignments. A changed account
   policy does not create copies in other accounts or trigger SSO provisioning.

Rollback must preserve authorization deliberately. If the reviewed old inline
still fits its approved inputs/quota, restore it and provision it **before**
detaching the reference. Otherwise retain the reference and restore a reviewed
account-policy version; do not force an oversized monolith back in or widen its
scope. Detach also provisions. Keep account policies until every relevant
reference/attachment and rollback check confirms removal is safe. No mutation,
assignment or deployment is performed by this document or this Codex task.

The current Identity Center table lists 25 managed policies per Permission Set;
the IAM table lists role defaults 20/max25, but the Identity Center footnote still
says default10. Use the repository's conservative budget10 as a portfolio choice,
not an assertion of the actual account quota. Its configured one-reference check
does not discover external attachments or target quotas; verify those externally.
Do not mix the nonexclusive resource with an exclusive attachment manager.

## Optional later official AWS policy validation

The [executable toolkit](../scripts/aws-policy-validation/README.md) exports actual
policies from successful mocked Terraform streams, creates a hashed manifest and
synthetic positive/negative cases, and processes results without AWS access by
default. Generate the bundle outside Git as documented there; do not commit plans,
raw results, session information, credentials or real identifiers. CI exercises
only offline export/check/default-run and deterministic mocked-response tests.

A repository owner may later copy the private synthetic bundle into an already
approved CloudShell/local session and intentionally use `run --execute-aws` as
shown in the toolkit README. **Do not execute that flag in Codex Cloud or CI.**
The runner refuses those environments and calls only:

- `access-analyzer:ValidatePolicy` for identity-policy findings.
- `iam:GetContextKeysForCustomPolicy` for context-key discovery.
- `iam:SimulateCustomPolicy` for the explicitly supplied synthetic cases.

These read APIs need `Resource: "*"` because no resource-level scope is supported;
no analyzer, IAM user, access key, role, policy, assignment or STS call is needed.
The user's existing approved identity must already have those permissions.
CloudShell session/launch rights (including credential forwarding through
`cloudshell:PutCredentials`) are separate prerequisites, not toolkit calls or
new grants in this PR. If a suitable Console/Identity Center session or CloudShell
authorization is absent, record that prerequisite and obtain it through the
organization's existing approval process. Do not use the root account for routine
validation or add keys/GitHub secrets to work around missing access.

Inspect all finding categories separately: ERROR is a failure; SECURITY_WARNING,
WARNING and SUGGESTION require the appropriate human review. The parser distinguishes
allowed, implicit/explicit deny, unexpected decisions, missing context, unsupported
or incomplete evaluation, API errors and pagination. Multi-resource requests need
complete resource-specific coverage; a single Allow is not a successful API call.
GetContext's listed keys can intentionally be absent for Null/IfExists; use actual
MissingContextValues rather than inventing every absent key as an error.

The private machine-readable and sanitized Markdown reports identify policy
hash/version and API evidence. Share only the sanitized reports after review;
never upload raw CloudShell responses or session data. Even an expected synthetic
Allow establishes neither a real assumed session nor live service authorization,
recipient governance, propagation or effective KMS/SCP/resource-policy access.
No official authenticated validation has been run in this Codex task.

## Resolution, evidence and remaining verification

| Risk / requirement | Resolved by design/code | Validated by offline tests | Requires manual AWS API or live infrastructure verification |
| --- | --- | --- | --- |
| Inline growth and managed-policy identity | Separate bounded service policy, fixed reference and independent size/attachment guards | Actual sizes/headroom, 7+1 inventories, reference matching and quota rejection | Every target's matching policy, default version, external attachments and actual quotas |
| Access Admin self/group assignment | Exact profiles/accounts retained; no unsupported recipient guard | Unchanged Admin JSON and forbidden privilege regressions | Independent approval/executor governance, memberships and audit; direct rights still permit bypass |
| Main-route-table association | Existing route-table/subnet ARN and Project scope retained | Exact EC2 projection and supported keys | Actual association IDs/topology and approved execution; simulation does not exclude main changes |
| VPC/subnet attribute values | No invented Boolean/attribute-value guarantee | Exact reviewed action/resource/condition structure | Runtime parameter context and network effects; plan approval is procedural |
| CreateSecret initial value | Terraform never handles values; inherited Create action remains broader | No payload flow; create/tag/replica guards and unchanged owning-account semantics | Direct human initial-value capability remains; no documented IAM absence condition |
| Missing UpdateSecret / recovery rights | Deliberately withheld along with retrieval, KMS and policy writes | Exact action/forbidden lists and implicit-deny cases | Separately approved metadata update/recovery process without Terraform values |
| Effective IAM/KMS and propagation | Explicit scope and account ownership contracts | Mock plans, official-reference compatibility and response-parser tests | Official APIs not executed here; live account/key/SCP/resource-policy and provisioning evidence still needed |
| Workloads and AWS deployment | No users, workload roles, assignments, root integration or deployment added | Exact intended resources only and no-call default/toolkit guards | Future authorized roots, workload permissions, connectivity and live operational readiness |

## Official evidence

Reviewed on 2026-11-07 using public documentation only:

- [IAM Identity Center Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam-identity-center.html)
- [Machine-readable SSO authorization reference](https://servicereference.us-east-1.amazonaws.com/v1/sso/sso.json)
- [Global principal-account condition](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-principalaccount)
- [Organization instances](https://docs.aws.amazon.com/singlesignon/latest/userguide/organization-instances-identity-center.html)
- [Delegated-administrator registration and exclusions](https://docs.aws.amazon.com/singlesignon/latest/userguide/delegated-admin-how-to-register.html)
- [Account-assignment parameters and automatic provisioning](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_CreateAccountAssignment.html)
- [IAM Identity Center CloudTrail event sources](https://docs.aws.amazon.com/singlesignon/latest/userguide/logging-using-cloudtrail.html)
- [EC2 Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html)
- [Machine-readable EC2 authorization reference](https://servicereference.us-east-1.amazonaws.com/v1/ec2/ec2.json)

- [Secrets Manager authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html)
- [Secrets Manager CreateSecret payload and tagging behavior](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_CreateSecret.html)
- [Secrets Manager UpdateSecret payload behavior](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_UpdateSecret.html)
- [Secrets Manager deletion and recovery](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DeleteSecret.html)
- [Secrets Manager ABAC creation/tag semantics](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_attribute-based-access-control.html)

- [Customer-managed policy references](https://docs.aws.amazon.com/singlesignon/latest/userguide/howtocmp.html)
- [Permission Set custom policies](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetcustom.html)
- [Identity Center quotas](https://docs.aws.amazon.com/singlesignon/latest/userguide/limits.html)
- [IAM quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
- [ValidatePolicy](https://docs.aws.amazon.com/access-analyzer/latest/APIReference/API_ValidatePolicy.html)
- [SimulateCustomPolicy](https://docs.aws.amazon.com/IAM/latest/APIReference/API_SimulateCustomPolicy.html)
- [GetContextKeysForCustomPolicy CLI schema](https://docs.aws.amazon.com/cli/latest/reference/iam/get-context-keys-for-custom-policy.html)
- [CloudShell existing identity/session authentication](https://docs.aws.amazon.com/cloudshell/latest/userguide/sec-auth-with-identities.html)
