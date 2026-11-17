mock_provider "aws" {}

# Synthetic test-only ARNs; no real instance, Permission Set or account is used.
override_resource {
  target          = aws_ssoadmin_permission_set.access_admin
  override_during = plan
  values          = { arn = "arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-0000000000000001" }
}

override_resource {
  target          = aws_ssoadmin_permission_set.developer
  override_during = plan
  values          = { arn = "arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-0000000000000002" }
}

override_resource {
  target          = aws_ssoadmin_permission_set.operator
  override_during = plan
  values          = { arn = "arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-0000000000000003" }
}

variables {
  name_prefix               = "test-portfolio"
  instance_arn              = "arn:aws:sso:::instance/ssoins-0000000000000000"
  target_account_ids        = ["000000000000", "000000000001"]
  administration_account_id = "000000000002"
  target_region             = "ca-central-1"
  project_tag               = "test-portfolio"
}

run "permission_set_identity_and_sessions" {
  command = plan

  variables {
    tags = { Name = "ignored", project = "ignored", Owner = "test-team" }
  }

  assert {
    condition     = aws_ssoadmin_permission_set.access_admin.name == "Portfolio-Access-Admin" && aws_ssoadmin_permission_set.developer.name == "Portfolio-Developer" && aws_ssoadmin_permission_set.operator.name == "Portfolio-Operator"
    error_message = "The three Permission Set identities must remain explicit and fixed."
  }

  assert {
    condition     = alltrue([for profile in [aws_ssoadmin_permission_set.access_admin, aws_ssoadmin_permission_set.developer, aws_ssoadmin_permission_set.operator] : profile.instance_arn == var.instance_arn && profile.session_duration == "PT1H" && profile.tags.project == "test-portfolio" && profile.tags.Owner == "test-team"])
    error_message = "Permission Sets must use the supplied instance, fixed one-hour sessions, and module-owned project tags."
  }

  assert {
    condition     = aws_ssoadmin_permission_set.access_admin.tags.Name == "test-portfolio-access-admin" && aws_ssoadmin_permission_set.developer.tags.Name == "test-portfolio-developer" && aws_ssoadmin_permission_set.operator.tags.Name == "test-portfolio-operator"
    error_message = "Caller tags must not replace module-owned inventory names."
  }

  assert {
    condition     = output.access_admin_permission_set_arn == aws_ssoadmin_permission_set.access_admin.arn && output.developer_permission_set_arn == aws_ssoadmin_permission_set.developer.arn && output.operator_permission_set_arn == aws_ssoadmin_permission_set.operator.arn
    error_message = "Outputs must expose only the intended Permission Set resource ARNs."
  }
}

run "account_policy_fixture" {
  command = plan

  module {
    source = "../iam_account_policies"
  }

  variables {
    account_id  = "000000000000"
    region      = "ca-central-1"
    project_tag = "test-portfolio"
  }

  assert {
    condition = (
      output.policy_name == "Portfolio-Developer-SecretsManager" &&
      output.policy_path == "/" &&
      output.policy_json == aws_iam_policy.developer_secrets_manager.policy
    )
    error_message = "The account fixture must render the real reviewed policy with the same canonical identity as the Identity Center reference."
  }
}

run "default_inventory_tags" {
  command = plan

  assert {
    condition     = aws_ssoadmin_permission_set.developer.tags == tomap({ Name = "test-portfolio-developer", project = "test-portfolio" })
    error_message = "Default optional tags must add no caller-controlled identity or permissions."
  }
}

run "invalid_instance_arn" {
  command = plan
  variables {
    instance_arn = "arn:aws:sso:::instance/ins-0000000000000000"
  }
  expect_failures = [var.instance_arn]
}

run "invalid_account_id" {
  command = plan
  variables {
    target_account_ids = ["not-an-account"]
  }
  expect_failures = [var.target_account_ids]
}

run "empty_target_accounts" {
  command = plan
  variables {
    target_account_ids = []
  }
  expect_failures = [var.target_account_ids]
}

run "invalid_name_prefix" {
  command = plan
  variables {
    name_prefix = ""
  }
  expect_failures = [var.name_prefix]
}

run "invalid_region" {
  command = plan
  variables {
    target_region = "*"
  }
  expect_failures = [var.target_region]
}

run "invalid_project_tag" {
  command = plan
  variables {
    project_tag = "*"
  }
  expect_failures = [var.project_tag]
}

run "inline_policy_bindings" {
  command = plan

  assert {
    condition = (
      aws_ssoadmin_permission_set_inline_policy.access_admin.permission_set_arn == output.access_admin_permission_set_arn &&
      aws_ssoadmin_permission_set_inline_policy.developer.permission_set_arn == output.developer_permission_set_arn &&
      aws_ssoadmin_permission_set_inline_policy.operator.permission_set_arn == output.operator_permission_set_arn &&
      alltrue([for policy in [aws_ssoadmin_permission_set_inline_policy.access_admin, aws_ssoadmin_permission_set_inline_policy.developer, aws_ssoadmin_permission_set_inline_policy.operator] : policy.instance_arn == var.instance_arn && jsondecode(policy.inline_policy).Version == "2012-10-17"])
    )
    error_message = "Each valid IAM document must be bound to its own Permission Set and the supplied instance."
  }
}

run "access_admin_assignment_scope" {
  command = plan

  assert {
    condition = length(jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement) == 4 && toset([
      for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement : statement.Sid
    ]) == toset(["AssignApprovedProfiles", "ReadApprovedAssignments", "ReadApprovedProfiles", "ReadAssignmentRequestStatus"])
    error_message = "Access Admin must contain all four reviewed statements exactly once."
  }

  assert {
    condition = toset(flatten([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement : statement.Action])) == toset([
      "sso:CreateAccountAssignment", "sso:DeleteAccountAssignment", "sso:ListAccountAssignments",
      "sso:DescribePermissionSet", "sso:DescribeAccountAssignmentCreationStatus", "sso:DescribeAccountAssignmentDeletionStatus"
    ])
    error_message = "Access Admin must have exactly the six reviewed assignment/metadata actions and no policy editing or infrastructure privileges."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement :
      toset(statement.Resource) == toset([
        var.instance_arn,
        "arn:aws:sso:::account/000000000000", "arn:aws:sso:::account/000000000001",
        output.developer_permission_set_arn, output.operator_permission_set_arn
      ]) if contains(statement.Action, "sso:CreateAccountAssignment") || contains(statement.Action, "sso:DeleteAccountAssignment") || contains(statement.Action, "sso:ListAccountAssignments")
    ])
    error_message = "Assignment operations require all three exact resource types: approved accounts, instance and only Developer/Operator profiles."
  }
}

run "access_admin_origin_and_metadata" {
  command = plan

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement :
      statement.Effect == "Allow" && statement.Condition == { StringEquals = { "aws:PrincipalAccount" = "000000000002" } } &&
      alltrue([for arn in statement.Resource : !strcontains(arn, "*") && arn != output.access_admin_permission_set_arn])
    ])
    error_message = "Access Admin must operate from the explicit administration account with no wildcard resource or self-profile assignment scope."
  }

  assert {
    condition = (
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement : statement if statement.Sid == "ReadApprovedProfiles"]).Resource) == toset([var.instance_arn, output.developer_permission_set_arn, output.operator_permission_set_arn]) &&
      one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement : statement if statement.Sid == "ReadAssignmentRequestStatus"]).Resource == [var.instance_arn]
    )
    error_message = "Profile reads must remain exact; status reads must use only the documented instance resource, without fake recipient conditions."
  }
}

run "developer_action_allowlist" {
  command = plan

  assert {
    condition = (
      length(jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement) == 14 &&
      toset([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement.Sid]) == toset([
        "RegionalNetworkMetadata", "ProjectVpcAttributes", "CreateVpc", "CreateSubnet", "CreateInternetGateway", "CreateRouteTable",
        "UseExistingProjectVpc", "ManageExistingProjectNetwork", "EditNonAuthorizationTags", "TagDuringCreateVpc", "TagDuringCreateSubnet", "TagDuringCreateInternetGateway", "TagDuringCreateRouteTable",
        "ManageProjectSubnetAssociations"
      ])
    )
    error_message = "All 14 reviewed inline statements must be present exactly once, so scoped assertion filters cannot pass vacuously."
  }

  assert {
    condition = toset(flatten([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement.Action])) == toset([
      "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeVpcAttribute",
      "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:CreateSubnet", "ec2:DeleteSubnet",
      "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
      "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute", "ec2:CreateTags", "ec2:DeleteTags",
      "ec2:ModifyVpcAttribute", "ec2:ModifySubnetAttribute", "ec2:AssociateRouteTable", "ec2:ReplaceRouteTableAssociation", "ec2:DisassociateRouteTable",
      "ec2:DescribeNetworkAcls", "ec2:DescribeSecurityGroups"
    ])
    error_message = "Developer inline must retain exactly the 27 reviewed EC2 actions; Secrets Manager is owned by the separately tested account policy."
  }
}

run "developer_account_region_and_resources" {
  command = plan

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      statement.Condition.StringEquals["aws:RequestedRegion"] == "ca-central-1" &&
      toset(statement.Condition.StringEquals["aws:PrincipalAccount"]) == toset(["000000000000", "000000000001"]) &&
      alltrue([for arn in statement.Resource : statement.Sid == "RegionalNetworkMetadata" ? arn == "*" : can(regex("^arn:aws:ec2:ca-central-1:00000000000[01]:(vpc|subnet|internet-gateway|route-table)/\\*$", arn))])
    ])
    error_message = "All Developer inline statements must enforce the unchanged account/region boundaries and only reviewed EC2 ARN types."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      statement.Sid == "RegionalNetworkMetadata" && toset(statement.Action) == toset(["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeNetworkAcls", "ec2:DescribeSecurityGroups"])
      if contains(statement.Resource, "*")
    ])
    error_message = "Only the six documented VPC/provider metadata actions may use a wildcard resource, in their exact statements."
  }
}

run "developer_creation_and_parent_authorization" {
  command = plan

  assert {
    condition = alltrue([for spec in [
      { action = "CreateVpc", type = "vpc" }, { action = "CreateSubnet", type = "subnet" },
      { action = "CreateInternetGateway", type = "internet-gateway" }, { action = "CreateRouteTable", type = "route-table" }
      ] : alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
        statement.Action == ["ec2:${spec.action}"] &&
        toset(statement.Resource) == toset([for id in ["000000000000", "000000000001"] : "arn:aws:ec2:ca-central-1:${id}:${spec.type}/*"]) &&
        statement.Condition.StringEquals["aws:RequestTag/project"] == "test-portfolio" &&
        toset(statement.Condition["ForAllValues:StringEquals"]["aws:TagKeys"]) == toset(["Name", "env", "managed", "project", "service"])
        if statement.Sid == spec.action
    ])])
    error_message = "Each create grant must pair only its new resource type with the required project tag and canonical approved tag keys."
  }

  assert {
    condition = (
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "UseExistingProjectVpc"]).Action) == toset(["ec2:CreateSubnet", "ec2:CreateRouteTable"]) &&
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "UseExistingProjectVpc"]).Resource) == toset(["arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"]) &&
      one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "UseExistingProjectVpc"]).Condition.StringEquals["aws:ResourceTag/project"] == "test-portfolio"
    )
    error_message = "Subnet/route-table creation must separately authorize the existing project VPC, not bypass it with request-tag permissions."
  }
}

run "developer_tag_integrity" {
  command = plan

  assert {
    condition = alltrue([for spec in [
      { action = "CreateVpc", type = "vpc" }, { action = "CreateSubnet", type = "subnet" },
      { action = "CreateInternetGateway", type = "internet-gateway" }, { action = "CreateRouteTable", type = "route-table" }
      ] : alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
        statement.Action == ["ec2:CreateTags"] && statement.Condition.StringEquals["ec2:CreateAction"] == spec.action &&
        statement.Condition.StringEquals["aws:RequestTag/project"] == "test-portfolio" &&
        toset(statement.Resource) == toset([for id in ["000000000000", "000000000001"] : "arn:aws:ec2:ca-central-1:${id}:${spec.type}/*"])
        if statement.Sid == "TagDuring${spec.action}"
    ])])
    error_message = "Create-time tagging must pair each exact EC2 create context and resource type; it must not authorize adopting unrelated resources."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      statement.Condition.StringEquals["aws:ResourceTag/project"] == "test-portfolio" &&
      statement.Condition["ForAllValues:StringNotEqualsIgnoreCase"]["aws:TagKeys"] == ["project"] &&
      statement.Condition.Null["aws:TagKeys"] == "false"
      if statement.Sid == "EditNonAuthorizationTags"
    ])
    error_message = "Existing tag edits must exclude all project casing variants and reject missing-tag-list deletes."
  }
}

run "developer_existing_resource_controls" {
  command = plan

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      statement.Condition.StringEquals["aws:ResourceTag/project"] == "test-portfolio"
      if contains(["UseExistingProjectVpc", "ManageExistingProjectNetwork", "EditNonAuthorizationTags", "ProjectVpcAttributes", "ManageProjectSubnetAssociations"], statement.Sid)
    ])
    error_message = "Every existing network resource operation must retain the project authorization tag."
  }

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : s if s.Sid == "ManageExistingProjectNetwork"])] :
      contains(statement.Action, "ec2:AttachInternetGateway") && contains(statement.Action, "ec2:DetachInternetGateway") &&
      toset([for arn in statement.Resource : arn if can(regex(":(vpc|internet-gateway)/", arn))]) == toset([
        "arn:aws:ec2:ca-central-1:000000000000:internet-gateway/*", "arn:aws:ec2:ca-central-1:000000000001:internet-gateway/*",
        "arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"
      ]) &&
      alltrue([for action in ["ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute"] : contains(statement.Action, action)]) &&
      toset([for arn in statement.Resource : arn if strcontains(arn, ":route-table/")]) == toset([
        "arn:aws:ec2:ca-central-1:000000000000:route-table/*", "arn:aws:ec2:ca-central-1:000000000001:route-table/*"
      ])
    ])
    error_message = "Compaction must preserve both compatible IGW/VPC resources for attachments and only scoped route-table resources for route actions."
  }
}

run "operator_metadata_only" {
  command = plan

  assert {
    condition = (
      length(jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement) == 3 &&
      toset([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : statement.Sid]) == toset(["RegionalNetworkMetadata", "ProjectVpcAttributes", "ReadProjectSecretMetadata"]) &&
      toset(flatten([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : statement.Action])) == toset([
        "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeVpcAttribute", "secretsmanager:DescribeSecret"
      ])
    )
    error_message = "Operator must retain exactly five network metadata actions and add only DescribeSecret, never writes, IAM management or data-plane reads."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement :
      statement.Condition.StringEquals["aws:RequestedRegion"] == "ca-central-1" &&
      toset(statement.Condition.StringEquals["aws:PrincipalAccount"]) == toset(["000000000000", "000000000001"]) &&
      (statement.Sid == "RegionalNetworkMetadata" ? statement.Resource == ["*"] :
        statement.Condition.StringEquals["aws:ResourceTag/project"] == "test-portfolio" &&
        (statement.Sid == "ProjectVpcAttributes" ?
          toset(statement.Resource) == toset(["arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"]) :
      toset(statement.Resource) == toset(["arn:aws:secretsmanager:ca-central-1:000000000000:secret:*", "arn:aws:secretsmanager:ca-central-1:000000000001:secret:*"])))
    ])
    error_message = "Operator's wildcard stays limited to regional network metadata; VPC attributes and Secret metadata remain exactly project/account/region scoped."
  }
}

run "profile_privilege_escalation_regression" {
  command = plan

  assert {
    condition = alltrue(flatten([for document in [aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy, aws_ssoadmin_permission_set_inline_policy.developer.inline_policy, aws_ssoadmin_permission_set_inline_policy.operator.inline_policy, run.account_policy_fixture.policy_json] : [
      for statement in jsondecode(document).Statement :
      statement.Effect == "Allow" && !can(statement.NotAction) && !can(statement.NotResource) &&
      alltrue([for action in statement.Action : !strcontains(action, "*") && !contains([
        "iam:PassRole", "secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue", "secretsmanager:PutSecretValue", "secretsmanager:UpdateSecret", "secretsmanager:UpdateSecretVersionStage", "secretsmanager:RotateSecret", "secretsmanager:RestoreSecret", "secretsmanager:PutResourcePolicy", "secretsmanager:DeleteResourcePolicy", "ssm:GetParameter", "ssm:GetParameters", "kms:Decrypt", "s3:GetObject",
        "sso:PutInlinePolicyToPermissionSet", "sso:CreatePermissionSet", "sso:AttachManagedPolicyToPermissionSet"
      ], action)])
    ]]))
    error_message = "No profile may acquire administrative wildcards, IAM escalation, policy editing, secret plaintext or general data-plane permissions."
  }

  assert {
    condition = alltrue(flatten([for spec in [
      { policy = aws_ssoadmin_permission_set_inline_policy.developer, secret_actions = [] },
      { policy = aws_ssoadmin_permission_set_inline_policy.operator, secret_actions = ["secretsmanager:DescribeSecret"] }
      ] : [for statement in jsondecode(spec.policy.inline_policy).Statement :
      alltrue([for action in statement.Action : startswith(action, "ec2:") || contains(spec.secret_actions, action)])
    ]]))
    error_message = "Developer and Operator must not administer Identity Center or gain services beyond EC2 and their exact reviewed Secret actions."
  }
}

run "invalid_administration_account" {
  command = plan
  variables {
    administration_account_id = "not-an-account"
  }
  expect_failures = [var.administration_account_id]
}

run "administration_account_not_assignment_target" {
  command = plan
  variables {
    administration_account_id = "000000000000"
  }
  expect_failures = [var.administration_account_id]
}

run "malformed_instance_arn" {
  command = plan
  variables {
    instance_arn = "not-an-arn"
  }
  expect_failures = [var.instance_arn]
}

run "vpc_attribute_authorization" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : s if contains(s.Action, "ec2:ModifyVpcAttribute")])] :
      statement.Sid == "ManageExistingProjectNetwork" &&
      toset([for arn in statement.Resource : arn if strcontains(arn, ":vpc/")]) == toset(["arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"]) &&
      statement.Condition == { StringEquals = {
        "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = ["000000000000", "000000000001"], "aws:ResourceTag/project" = "test-portfolio"
      } }
    ])
    error_message = "Compacted vpc attribute authorization must retain exactly its compatible vpc ARNs and project/account/region conditions, without fabricated value guards."
  }
}

run "subnet_attribute_authorization" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : s if contains(s.Action, "ec2:ModifySubnetAttribute")])] :
      statement.Sid == "ManageExistingProjectNetwork" &&
      toset([for arn in statement.Resource : arn if strcontains(arn, ":subnet/")]) == toset(["arn:aws:ec2:ca-central-1:000000000000:subnet/*", "arn:aws:ec2:ca-central-1:000000000001:subnet/*"]) &&
      statement.Condition == { StringEquals = {
        "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = ["000000000000", "000000000001"], "aws:ResourceTag/project" = "test-portfolio"
      } }
    ])
    error_message = "Compacted subnet attribute authorization must retain exactly its compatible subnet ARNs and project/account/region conditions, without fabricated value guards."
  }
}

run "association_lifecycle_authorization" {
  command = plan

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      toset(statement.Action) == toset(["ec2:AssociateRouteTable", "ec2:ReplaceRouteTableAssociation", "ec2:DisassociateRouteTable"]) &&
      toset(statement.Resource) == toset([
        "arn:aws:ec2:ca-central-1:000000000000:route-table/*", "arn:aws:ec2:ca-central-1:000000000001:route-table/*",
        "arn:aws:ec2:ca-central-1:000000000000:subnet/*", "arn:aws:ec2:ca-central-1:000000000001:subnet/*"
      ]) &&
      statement.Condition == { StringEquals = {
        "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = ["000000000000", "000000000001"], "aws:ResourceTag/project" = "test-portfolio"
      } } if statement.Sid == "ManageProjectSubnetAssociations"
    ])
    error_message = "Association grants must use only reviewed route-table/subnet resources and supported conditions, never a fake IsMain or association-ARN restriction."
  }
}

run "provider_metadata_does_not_expand_operator" {
  command = plan

  assert {
    condition = (
      one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "RegionalNetworkMetadata"]).Resource == ["*"] &&
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "RegionalNetworkMetadata"]).Action) == toset(["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeNetworkAcls", "ec2:DescribeSecurityGroups"]) &&
      alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : !contains(statement.Action, "ec2:DescribeNetworkAcls") && !contains(statement.Action, "ec2:DescribeSecurityGroups")])
    )
    error_message = "Only Developer may gain the two provider-read dependencies; Operator must retain its five existing EC2 metadata actions without gaining these provider-only reads."
  }
}

run "secret_action_and_resource_scope" {
  command = plan

  assert {
    condition = (
      length([for statement in jsondecode(run.account_policy_fixture.policy_json).Statement : statement if alltrue([for action in statement.Action : startswith(action, "secretsmanager:")])]) == 5 &&
      toset(flatten([for statement in jsondecode(run.account_policy_fixture.policy_json).Statement : statement.Action if alltrue([for action in statement.Action : startswith(action, "secretsmanager:")])])) == toset([
        "secretsmanager:CreateSecret", "secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy", "secretsmanager:TagResource", "secretsmanager:UntagResource", "secretsmanager:DeleteSecret"
      ]) &&
      alltrue([for statement in jsondecode(run.account_policy_fixture.policy_json).Statement :
        toset(statement.Resource) == toset(["arn:aws:secretsmanager:ca-central-1:000000000000:secret:*"]) &&
        statement.Condition.StringEquals["aws:RequestedRegion"] == "ca-central-1" &&
        statement.Condition.StringEquals["aws:PrincipalAccount"] == "000000000000"
        if alltrue([for action in statement.Action : startswith(action, "secretsmanager:")])
      ])
    )
    error_message = "Exactly five Secret statements must contain only the six reviewed actions and approved account/region Secret ARNs, never all-resource grants."
  }
}

run "secret_creation_controls" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(run.account_policy_fixture.policy_json).Statement : s if s.Sid == "CreateProjectSecret"])] :
      statement.Action == ["secretsmanager:CreateSecret"] &&
      statement.Condition == {
        StringEquals = {
          "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = "000000000000", "aws:RequestTag/project" = "test-portfolio"
        }
        "ForAllValues:StringEquals" = { "aws:TagKeys" = ["Name", "env", "managed", "project", "service"] }
        Null                        = { "secretsmanager:AddReplicaRegions" = "true" }
        BoolIfExists                = { "secretsmanager:ForceOverwriteReplicaSecret" = "false" }
      }
    ])
    error_message = "Secret creation must require canonical project request tags and reject replicas/overwrite without inventing payload-absence conditions."
  }
}

run "secret_tag_identity_boundaries" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(run.account_policy_fixture.policy_json).Statement : s if s.Sid == "TagProjectSecretIdentity"])] :
      statement.Action == ["secretsmanager:TagResource"] &&
      statement.Condition == {
        StringEquals = {
          "aws:RequestedRegion"     = "ca-central-1", "aws:PrincipalAccount" = "000000000000",
          "aws:ResourceTag/project" = "test-portfolio", "aws:RequestTag/project" = "test-portfolio"
        }
        "ForAllValues:StringEquals" = { "aws:TagKeys" = ["Name", "env", "managed", "project", "service"] }
      }
    ])
    error_message = "Identity tagging must require both resource and request project values and exact canonical keys; request tags alone must never authorize adopting unrelated secrets."
  }
}

run "secret_existing_tag_integrity" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(run.account_policy_fixture.policy_json).Statement : s if s.Sid == "EditProjectSecretTags"])] :
      toset(statement.Action) == toset(["secretsmanager:TagResource", "secretsmanager:UntagResource"]) &&
      statement.Condition == {
        StringEquals = {
          "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = "000000000000", "aws:ResourceTag/project" = "test-portfolio"
        }
        "ForAllValues:StringNotEqualsIgnoreCase" = { "aws:TagKeys" = ["project"] }
        Null                                     = { "aws:TagKeys" = "false" }
      }
    ])
    error_message = "Existing Secret tag edits must require matching ownership, exclude every project spelling and reject omitted tag lists."
  }
}

run "secret_deletion_recovery_controls" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(run.account_policy_fixture.policy_json).Statement : s if s.Sid == "ScheduleProjectSecretDeletion"])] :
      statement.Action == ["secretsmanager:DeleteSecret"] &&
      statement.Condition == {
        StringEquals = {
          "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = "000000000000", "aws:ResourceTag/project" = "test-portfolio"
        }
        BoolIfExists             = { "secretsmanager:ForceDeleteWithoutRecovery" = "false" }
        NumericGreaterThanEquals = { "secretsmanager:RecoveryWindowInDays" = "7" }
        NumericLessThanEquals    = { "secretsmanager:RecoveryWindowInDays" = "30" }
      }
    ])
    error_message = "Deletion must require explicit recovery 7-30 and deny force deletion while allowing the provider's omitted ForceDeleteWithoutRecovery flag."
  }
}

run "secret_profile_separation" {
  command = plan

  assert {
    condition = (
      one([for s in jsondecode(run.account_policy_fixture.policy_json).Statement : s if s.Sid == "ReadProjectSecretMetadata"]).Action == ["secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy"] &&
      one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : s if s.Sid == "ReadProjectSecretMetadata"]).Action == ["secretsmanager:DescribeSecret"] &&
      alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.access_admin.inline_policy).Statement : alltrue([for action in statement.Action : startswith(action, "sso:")])]) &&
      alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : alltrue([for action in statement.Action : !startswith(action, "secretsmanager:") || action == "secretsmanager:DescribeSecret"])])
    )
    error_message = "Only Developer may read the policy metadata required by provider refresh; Operator gets DescribeSecret only and Access Admin remains SSO-only."
  }

  assert {
    condition = (
      one([for s in jsondecode(run.account_policy_fixture.policy_json).Statement : s if s.Sid == "ReadProjectSecretMetadata"]).Condition == { StringEquals = {
        "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = "000000000000", "aws:ResourceTag/project" = "test-portfolio"
      } } &&
      one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : s if s.Sid == "ReadProjectSecretMetadata"]).Condition == { StringEquals = {
        "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = ["000000000000", "000000000001"], "aws:ResourceTag/project" = "test-portfolio"
      } }
    )
    error_message = "Developer managed permissions must be narrowed to the owning account while Operator's original metadata scope remains unchanged."
  }
}

run "vpc_effective_authorization_preserved" {
  command = plan

  assert {
    condition = alltrue([for statement in [one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : s if s.Sid == "ManageExistingProjectNetwork"])] :
      toset(statement.Action) == toset([
        "ec2:DeleteVpc", "ec2:DeleteSubnet", "ec2:DeleteInternetGateway", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
        "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute", "ec2:ModifyVpcAttribute", "ec2:ModifySubnetAttribute"
      ]) &&
      toset(statement.Resource) == toset(flatten([for kind in ["vpc", "subnet", "internet-gateway", "route-table"] : [
        for account in ["000000000000", "000000000001"] : "arn:aws:ec2:ca-central-1:${account}:${kind}/*"
      ]])) &&
      statement.Condition == { StringEquals = {
        "aws:RequestedRegion" = "ca-central-1", "aws:PrincipalAccount" = ["000000000000", "000000000001"], "aws:ResourceTag/project" = "test-portfolio"
      } }
    ])
    error_message = "Same-condition compaction must preserve the exact eleven existing actions and four account-scoped ARN types, with unchanged project/region/account conditions."
  }

  assert {
    # Types are the action-specific compatible resources from the official EC2 SAR.
    condition = alltrue([for spec in [
      { action = "DeleteVpc", types = ["vpc"] }, { action = "ModifyVpcAttribute", types = ["vpc"] },
      { action = "DeleteSubnet", types = ["subnet"] }, { action = "ModifySubnetAttribute", types = ["subnet"] },
      { action = "DeleteInternetGateway", types = ["internet-gateway"] },
      { action = "AttachInternetGateway", types = ["vpc", "internet-gateway"] }, { action = "DetachInternetGateway", types = ["vpc", "internet-gateway"] },
      { action = "DeleteRouteTable", types = ["route-table"] }, { action = "CreateRoute", types = ["route-table"] },
      { action = "ReplaceRoute", types = ["route-table"] }, { action = "DeleteRoute", types = ["route-table"] }
      ] : alltrue([for statement in [one([for s in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : s if contains(s.Action, "ec2:${spec.action}")])] :
        toset([for arn in statement.Resource : arn if anytrue([for kind in spec.types : strcontains(arn, ":${kind}/")])]) == toset(flatten([
          for kind in spec.types : [for account in ["000000000000", "000000000001"] : "arn:aws:ec2:ca-central-1:${account}:${kind}/*"]
        ]))
      ])
    ])
    error_message = "Each compacted action must retain exactly the same compatible resource ARN projection as before compaction; association grants must remain separate."
  }
}

run "rendered_policy_size_within_quota" {
  command = plan
  variables {
    project_tag = "aws-terraform-portfolio"
  }

  assert {
    condition = alltrue([for policy in [aws_ssoadmin_permission_set_inline_policy.access_admin, aws_ssoadmin_permission_set_inline_policy.developer, aws_ssoadmin_permission_set_inline_policy.operator] :
      length(policy.inline_policy) <= 10240
    ])
    error_message = "The actual compact ASCII policy documents must remain below the non-adjustable inline policy quota for the reviewed two-account fixture and full portfolio project tag."
  }
}

run "inline_policy_quota_overflow" {
  command = plan
  variables {
    target_account_ids = [for account in range(100, 120) : format("%012d", account)]
  }
  expect_failures = [aws_ssoadmin_permission_set_inline_policy.developer]
}

run "developer_customer_managed_attachment" {
  command = plan

  assert {
    condition = (
      length(aws_ssoadmin_customer_managed_policy_attachment.developer) == 1 &&
      keys(aws_ssoadmin_customer_managed_policy_attachment.developer) == ["secrets_manager"] &&
      aws_ssoadmin_customer_managed_policy_attachment.developer["secrets_manager"].instance_arn == var.instance_arn &&
      aws_ssoadmin_customer_managed_policy_attachment.developer["secrets_manager"].permission_set_arn == output.developer_permission_set_arn &&
      output.developer_customer_managed_policy_references == {
        secrets_manager = { name = run.account_policy_fixture.policy_name, path = run.account_policy_fixture.policy_path }
      }
    )
    error_message = "Exactly the reviewed account policy name/path must attach only to Developer and the supplied instance."
  }
}

run "developer_policy_capacity_and_attachment_budget" {
  command = plan

  assert {
    condition = (
      output.developer_inline_policy_quota.non_whitespace_bytes == length(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy) &&
      output.developer_inline_policy_quota.limit_non_whitespace_bytes == 10240 &&
      output.developer_inline_policy_quota.remaining_bytes == 10240 - length(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy) &&
      output.developer_inline_policy_quota.remaining_bytes >= 2500 &&
      output.developer_managed_attachment_quota == {
        count = 1, portfolio_budget = 10, permission_set_limit = 25, remaining_portfolio_slots = 9
      } &&
      alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : alltrue([for action in statement.Action : startswith(action, "ec2:")])])
    )
    error_message = "Actual inline headroom must materially improve, with one reference under the conservative portfolio budget and service limit."
  }
}

run "three_account_full_project_capacity" {
  command = plan
  variables {
    target_account_ids = ["000000000000", "000000000001", "000000000003"]
    project_tag        = "aws-terraform-portfolio"
  }

  assert {
    condition = (
      output.developer_inline_policy_quota.non_whitespace_bytes < 10240 &&
      output.developer_inline_policy_quota.remaining_bytes > 0 &&
      alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
        toset(statement.Condition.StringEquals["aws:PrincipalAccount"]) == toset(var.target_account_ids)
      ])
    )
    error_message = "A three-account portfolio case must fit without removing explicit account restrictions."
  }
}

run "single_account_maximum_project_capacity" {
  command = plan
  variables {
    target_account_ids = ["000000000000"]
    project_tag        = join("", [for i in range(63) : "p"])
  }

  assert {
    condition = (
      output.developer_inline_policy_quota.non_whitespace_bytes < 10240 &&
      output.developer_inline_policy_quota.remaining_bytes > 0 &&
      alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
        statement.Condition.StringEquals["aws:PrincipalAccount"] == ["000000000000"]
      ])
    )
    error_message = "Maximum project identity length must remain supported without weakening account scope."
  }
}
