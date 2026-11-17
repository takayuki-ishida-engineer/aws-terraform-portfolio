"""Reviewed synthetic IAM policy-context cases; this module never calls AWS.

The supplied scope comes from exported mocked Terraform policy documents.
Resources below are synthetic, and context entries do not represent a session.
"""

import copy


def build_cases(scope):
  """Return deterministic cases for the effective reviewed policy composition."""
  partition = scope["instance_arn"].split(":")[1]
  account = scope["account_id"]
  region = scope["region"]
  project = scope["project_tag"]
  approved = set(scope["target_account_ids"]) | {account, scope["administration_account_id"]}
  other_account = next(f"{number:012d}" for number in range(90, 190) if f"{number:012d}" not in approved)
  other_region = "us-west-2" if region != "us-west-2" else "us-east-2"
  other_project = "unapproved-project" if project != "unapproved-project" else "other-project"
  ec2 = f"arn:{partition}:ec2:{region}:{account}:"
  resources = {
    "vpc": ec2 + "vpc/vpc-00000000000000000",
    "subnet": ec2 + "subnet/subnet-00000000000000000",
    "gateway": ec2 + "internet-gateway/igw-00000000000000000",
    "route_table": ec2 + "route-table/rtb-00000000000000000",
    "secret": f"arn:{partition}:secretsmanager:{region}:{account}:secret:portfolio/test/metadata-ABC123",
    "kms": f"arn:{partition}:kms:{region}:{account}:key/00000000-0000-0000-0000-000000000000",
    "role": f"arn:{partition}:iam::{account}:role/SyntheticValidationRole",
    "security_group": ec2 + "security-group/sg-00000000000000000",
  }
  cases = []

  def entry(key, values, kind="string"):
    return {"ContextKeyName": key, "ContextKeyValues": values if isinstance(values, list) else [values], "ContextKeyType": kind}

  regional = [entry("aws:PrincipalAccount", account), entry("aws:RequestedRegion", region)]
  existing = regional + [entry("aws:ResourceTag/project", project)]
  creation = regional + [entry("aws:RequestTag/project", project), entry("aws:TagKeys", ["Name", "env", "managed", "project", "service"], "stringList")]
  admin_context = [entry("aws:PrincipalAccount", scope["administration_account_id"])]

  def change(context, key, value, kind=None):
    result = copy.deepcopy(context)
    for item in result:
      if item["ContextKeyName"] == key:
        item["ContextKeyValues"] = value if isinstance(value, list) else [value]
        if kind:
          item["ContextKeyType"] = kind
        return result
    result.append(entry(key, value, kind or "string"))
    return result

  def case(identifier, profile, action, arns, context, expected="allowed", notes="", supported=True):
    cases.append({
      "id": identifier,
      "profile": profile,
      "action": action,
      "resources": copy.deepcopy(arns),
      "context": copy.deepcopy(context),
      "expected": expected,
      "supported": supported,
      "synthetic": True,
      "notes": notes or "Synthetic policy-context evaluation only; not a real principal session or live API authorization test.",
    })

  # EC2 API operations that require more than one resource include every
  # required resource. Their combined decision must not be inferred from one.
  case("developer-vpc-delete", "developer", "ec2:DeleteVpc", [resources["vpc"]], existing)
  case("developer-igw-attachment-both-resources", "developer", "ec2:AttachInternetGateway", [resources["gateway"], resources["vpc"]], existing,
       notes="Both required IGW and VPC resources must be allowed; one isolated Allow is insufficient.")
  subnet_creation = creation + [entry("aws:ResourceTag/project", project)]
  case("developer-subnet-create-parent-and-new-resource", "developer", "ec2:CreateSubnet", [resources["subnet"], resources["vpc"]], subnet_creation,
       notes="Models request tags on the new subnet and matching existing-parent project context. Actual service-supplied context and dependent CreateTags require external verification.")
  case("developer-subnet-create-tags", "developer", "ec2:CreateTags", [resources["subnet"]], creation + [entry("ec2:CreateAction", "CreateSubnet")],
       notes="The dependent tagging authorization is evaluated separately; this does not prove a live CreateSubnet request succeeds.")
  case("developer-vpc-unapproved-principal-account", "developer", "ec2:DeleteVpc", [resources["vpc"]], change(existing, "aws:PrincipalAccount", other_account), "deny")
  case("developer-vpc-unapproved-resource-account", "developer", "ec2:DeleteVpc", [resources["vpc"].replace(f":{account}:", f":{other_account}:")], existing, "deny")
  case("developer-vpc-unapproved-region", "developer", "ec2:DeleteVpc", [resources["vpc"]], change(existing, "aws:RequestedRegion", other_region), "deny")
  case("developer-vpc-project-mismatch", "developer", "ec2:DeleteVpc", [resources["vpc"]], change(existing, "aws:ResourceTag/project", other_project), "deny")
  case("developer-vpc-project-tag-change", "developer", "ec2:CreateTags", [resources["vpc"]], existing + [entry("aws:TagKeys", ["pRoJeCt"], "stringList")], "deny")
  case("developer-unrelated-ec2-write", "developer", "ec2:DeleteSecurityGroup", [resources["security_group"]], existing, "deny")
  case("developer-iam-administration", "developer", "iam:CreateRole", [resources["role"]], existing, "deny")

  # CreateSecret and its dependent TagResource authorization are separate cases.
  # Absence of AddReplicaRegions is intentional for its Null condition.
  secret_create = creation + [entry("secretsmanager:ForceOverwriteReplicaSecret", "false", "boolean")]
  secret_tag_identity = creation + [entry("aws:ResourceTag/project", project)]
  secret_tag_edit = existing + [entry("aws:TagKeys", ["Name"], "stringList")]
  deletion = existing + [entry("secretsmanager:RecoveryWindowInDays", "30", "numeric"), entry("secretsmanager:ForceDeleteWithoutRecovery", "false", "boolean")]
  case("developer-secret-create", "developer", "secretsmanager:CreateSecret", [resources["secret"]], secret_create,
       notes="Policy-context check with no replica context. CreateSecret can initialize values; this case neither sends a payload nor proves its absence is IAM-enforced. Dependent TagResource is evaluated separately.")
  case("developer-secret-describe", "developer", "secretsmanager:DescribeSecret", [resources["secret"]], existing)
  case("developer-secret-resource-policy-metadata", "developer", "secretsmanager:GetResourcePolicy", [resources["secret"]], existing)
  case("developer-secret-tag-matching-project", "developer", "secretsmanager:TagResource", [resources["secret"]], secret_tag_identity,
       notes="Both requested and resource project values match. Synthetic supplied context does not prove AWS creation-time context behavior.")
  case("developer-secret-edit-non-project-tag", "developer", "secretsmanager:TagResource", [resources["secret"]], secret_tag_edit)
  case("developer-secret-remove-non-project-tag", "developer", "secretsmanager:UntagResource", [resources["secret"]], secret_tag_edit)
  case("developer-secret-delete-30-days", "developer", "secretsmanager:DeleteSecret", [resources["secret"]], deletion)
  case("developer-secret-delete-7-days", "developer", "secretsmanager:DeleteSecret", [resources["secret"]], change(deletion, "secretsmanager:RecoveryWindowInDays", "7"))
  case("developer-secret-force-delete", "developer", "secretsmanager:DeleteSecret", [resources["secret"]], change(deletion, "secretsmanager:ForceDeleteWithoutRecovery", "true"), "deny")
  case("developer-secret-zero-recovery", "developer", "secretsmanager:DeleteSecret", [resources["secret"]], change(deletion, "secretsmanager:RecoveryWindowInDays", "0"), "deny")
  case("developer-secret-excess-recovery", "developer", "secretsmanager:DeleteSecret", [resources["secret"]], change(deletion, "secretsmanager:RecoveryWindowInDays", "31"), "deny")
  case("developer-secret-replica-request", "developer", "secretsmanager:CreateSecret", [resources["secret"]], secret_create + [entry("secretsmanager:AddReplicaRegions", [other_region], "stringList")], "deny")
  case("developer-secret-replica-overwrite", "developer", "secretsmanager:CreateSecret", [resources["secret"]], change(secret_create, "secretsmanager:ForceOverwriteReplicaSecret", "true"), "deny")
  case("developer-secret-unapproved-principal-account", "developer", "secretsmanager:DescribeSecret", [resources["secret"]], change(existing, "aws:PrincipalAccount", other_account), "deny")
  case("developer-secret-unapproved-resource-account", "developer", "secretsmanager:DescribeSecret", [resources["secret"].replace(f":{account}:", f":{other_account}:")], existing, "deny")
  case("developer-secret-unapproved-region", "developer", "secretsmanager:DescribeSecret", [resources["secret"]], change(existing, "aws:RequestedRegion", other_region), "deny")
  case("developer-secret-project-mismatch", "developer", "secretsmanager:DescribeSecret", [resources["secret"]], change(existing, "aws:ResourceTag/project", other_project), "deny")
  case("developer-secret-project-adoption", "developer", "secretsmanager:TagResource", [resources["secret"]], change(secret_tag_identity, "aws:ResourceTag/project", other_project), "deny")
  case("developer-secret-project-change", "developer", "secretsmanager:TagResource", [resources["secret"]], change(secret_tag_identity, "aws:RequestTag/project", other_project), "deny")
  case("developer-secret-project-removal", "developer", "secretsmanager:UntagResource", [resources["secret"]], change(secret_tag_edit, "aws:TagKeys", ["pRoJeCt"]), "deny")
  for identifier, action, arn in [
    ("get-value", "secretsmanager:GetSecretValue", resources["secret"]),
    ("put-value", "secretsmanager:PutSecretValue", resources["secret"]),
    ("update", "secretsmanager:UpdateSecret", resources["secret"]),
    ("batch-get-values", "secretsmanager:BatchGetSecretValue", "*"),
    ("kms-decrypt", "kms:Decrypt", resources["kms"]),
    ("put-policy", "secretsmanager:PutResourcePolicy", resources["secret"]),
    ("delete-policy", "secretsmanager:DeleteResourcePolicy", resources["secret"]),
    ("restore", "secretsmanager:RestoreSecret", resources["secret"]),
  ]:
    case("developer-secret-forbidden-" + identifier, "developer", action, [arn], existing, "deny")

  case("operator-vpc-regional-metadata", "operator", "ec2:DescribeVpcs", ["*"], regional)
  case("operator-vpc-project-attribute-metadata", "operator", "ec2:DescribeVpcAttribute", [resources["vpc"]], existing)
  case("operator-secret-metadata", "operator", "secretsmanager:DescribeSecret", [resources["secret"]], existing)
  case("operator-secret-value-retrieval", "operator", "secretsmanager:GetSecretValue", [resources["secret"]], existing, "deny")
  case("operator-secret-write", "operator", "secretsmanager:DeleteSecret", [resources["secret"]], deletion, "deny")
  case("operator-iam-administration", "operator", "iam:CreateRole", [resources["role"]], regional, "deny")
  case("operator-identity-center-administration", "operator", "sso:CreatePermissionSet", [scope["instance_arn"]], admin_context, "deny")

  account_arn = f"arn:{partition}:sso:::account/{account}"
  assignment = [scope["instance_arn"], scope["developer_permission_set_arn"], account_arn]
  case("access-admin-approved-assignment-resources", "access_admin", "sso:CreateAccountAssignment", assignment, admin_context,
       notes="All three required instance, Permission Set and account resources must be evaluated. Does not model recipient identity, real session, service prerequisites, assignments or propagation.")
  unapproved_set = scope["developer_permission_set_arn"].rsplit("/", 1)[0] + "/ps-ffffffffffffffff"
  if unapproved_set in {scope["developer_permission_set_arn"], scope["operator_permission_set_arn"]}:
    unapproved_set = unapproved_set.rsplit("/", 1)[0] + "/ps-eeeeeeeeeeeeeeee"
  case("access-admin-unapproved-permission-set", "access_admin", "sso:CreateAccountAssignment", [scope["instance_arn"], unapproved_set, account_arn], admin_context, "deny")
  case("access-admin-unapproved-target-account", "access_admin", "sso:CreateAccountAssignment", [scope["instance_arn"], scope["developer_permission_set_arn"], f"arn:{partition}:sso:::account/{other_account}"], admin_context, "deny")
  case("access-admin-unrelated-account-management", "access_admin", "organizations:CreateAccount", ["*"], admin_context, "deny")

  # These desired protections have no supported discriminator in the reviewed
  # policy model. They are explicitly unverified, never fabricated passing denies.
  case("unverified-main-route-table-exclusion", "developer", "ec2:ReplaceRouteTableAssociation", [resources["route_table"], resources["subnet"]], existing, "deny", supported=False,
       notes="Desired exclusion cannot be represented: no reviewed main-association discriminator or association ARN. Current grant retains main-route-table capability; a synthetic evaluation cannot prove prevention.")
  case("unverified-vpc-dns-value-restriction", "developer", "ec2:ModifyVpcAttribute", [resources["vpc"]], existing, "deny", supported=False,
       notes="Exact VPC Boolean-value IAM context is not established. This desired restriction is not enforced by the current action grant and must not be reported as a passing denial.")
  case("unverified-secret-payload-absence", "developer", "secretsmanager:CreateSecret", [resources["secret"]], secret_create, "deny", supported=False,
       notes="No documented IAM condition enforces initial-payload absence for CreateSecret. The current action can initialize values; metadata-only Terraform and a synthetic policy-context simulation do not technically prevent that capability. No payload is supplied by this case.")
  case("unverified-access-admin-self-assignment-prevention", "access_admin", "sso:CreateAccountAssignment", assignment, admin_context, "deny", supported=False,
       notes="No supported recipient/self/group condition is supplied or invented. Access Admin can self-assign an approved profile; independent approval needs a different execution design. Expected deny is a desired protection, not the current policy's behavior.")
  return cases
