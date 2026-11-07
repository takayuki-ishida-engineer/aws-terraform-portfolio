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
    tags = { Name = "ignored", Project = "ignored", Owner = "test-team" }
  }

  assert {
    condition     = aws_ssoadmin_permission_set.access_admin.name == "Portfolio-Access-Admin" && aws_ssoadmin_permission_set.developer.name == "Portfolio-Developer" && aws_ssoadmin_permission_set.operator.name == "Portfolio-Operator"
    error_message = "The three Permission Set identities must remain explicit and fixed."
  }

  assert {
    condition     = alltrue([for profile in [aws_ssoadmin_permission_set.access_admin, aws_ssoadmin_permission_set.developer, aws_ssoadmin_permission_set.operator] : profile.instance_arn == var.instance_arn && profile.session_duration == "PT1H" && profile.tags.Project == "test-portfolio" && profile.tags.Owner == "test-team"])
    error_message = "Permission Sets must use the supplied instance, fixed one-hour sessions, and module-owned Project tags."
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

run "default_inventory_tags" {
  command = plan

  assert {
    condition     = aws_ssoadmin_permission_set.developer.tags == tomap({ Name = "test-portfolio-developer", Project = "test-portfolio" })
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
      length(jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement) == 17 &&
      toset([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement.Sid]) == toset([
        "RegionalNetworkMetadata", "ProjectVpcAttributes", "CreateVpc", "CreateSubnet", "CreateInternetGateway", "CreateRouteTable",
        "UseExistingProjectVpc", "DeleteProjectVpc", "DeleteProjectSubnet", "DeleteProjectInternetGateway", "AttachProjectInternetGateway",
        "ManageProjectRouteTable", "EditNonAuthorizationTags", "TagDuringCreateVpc", "TagDuringCreateSubnet", "TagDuringCreateInternetGateway", "TagDuringCreateRouteTable"
      ])
    )
    error_message = "All 17 reviewed statements must be present exactly once, so scoped assertion filters cannot pass vacuously."
  }

  assert {
    condition = toset(flatten([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement.Action])) == toset([
      "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeVpcAttribute",
      "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:CreateSubnet", "ec2:DeleteSubnet",
      "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
      "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute", "ec2:CreateTags", "ec2:DeleteTags"
    ])
    error_message = "Developer must have exactly the reviewed 20 EC2 actions, excluding unverified attribute/association writes and future services."
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
    error_message = "All Developer statements must enforce explicit account/region boundaries and only the four approved network ARN types."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      toset(statement.Action) == toset(["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables"])
      if contains(statement.Resource, "*")
    ])
    error_message = "Only the four documented non-resource-scopeable metadata actions may use a wildcard resource."
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
        statement.Condition.StringEquals["aws:RequestTag/Project"] == "test-portfolio" &&
        toset(statement.Condition["ForAllValues:StringEquals"]["aws:TagKeys"]) == toset(["Environment", "ManagedBy", "Name", "Project", "Service"])
        if statement.Sid == spec.action
    ])])
    error_message = "Each create grant must pair only its new resource type with the required Project tag and canonical approved tag keys."
  }

  assert {
    condition = (
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "UseExistingProjectVpc"]).Action) == toset(["ec2:CreateSubnet", "ec2:CreateRouteTable"]) &&
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "UseExistingProjectVpc"]).Resource) == toset(["arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"]) &&
      one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "UseExistingProjectVpc"]).Condition.StringEquals["aws:ResourceTag/Project"] == "test-portfolio"
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
        statement.Condition.StringEquals["aws:RequestTag/Project"] == "test-portfolio" &&
        toset(statement.Resource) == toset([for id in ["000000000000", "000000000001"] : "arn:aws:ec2:ca-central-1:${id}:${spec.type}/*"])
        if statement.Sid == "TagDuring${spec.action}"
    ])])
    error_message = "Create-time tagging must pair each exact EC2 create context and resource type; it must not authorize adopting unrelated resources."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      statement.Condition.StringEquals["aws:ResourceTag/Project"] == "test-portfolio" &&
      statement.Condition["ForAllValues:StringNotEqualsIgnoreCase"]["aws:TagKeys"] == ["Project"] &&
      statement.Condition.Null["aws:TagKeys"] == "false"
      if statement.Sid == "EditNonAuthorizationTags"
    ])
    error_message = "Existing tag edits must exclude all Project casing variants and reject missing-tag-list deletes."
  }
}

run "developer_existing_resource_controls" {
  command = plan

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement :
      statement.Condition.StringEquals["aws:ResourceTag/Project"] == "test-portfolio"
      if contains(["UseExistingProjectVpc", "DeleteProjectVpc", "DeleteProjectSubnet", "DeleteProjectInternetGateway", "AttachProjectInternetGateway", "ManageProjectRouteTable", "EditNonAuthorizationTags", "ProjectVpcAttributes"], statement.Sid)
    ])
    error_message = "Every existing resource operation must require the Project authorization tag."
  }

  assert {
    condition = (
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "AttachProjectInternetGateway"]).Resource) == toset([
        "arn:aws:ec2:ca-central-1:000000000000:internet-gateway/*", "arn:aws:ec2:ca-central-1:000000000001:internet-gateway/*",
        "arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"
      ]) &&
      toset(one([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.developer.inline_policy).Statement : statement if statement.Sid == "ManageProjectRouteTable"]).Resource) == toset(["arn:aws:ec2:ca-central-1:000000000000:route-table/*", "arn:aws:ec2:ca-central-1:000000000001:route-table/*"])
    )
    error_message = "IGW attachment requires both project VPC and IGW resources; route writes authorize only scoped route tables."
  }
}

run "operator_metadata_only" {
  command = plan

  assert {
    condition = (
      length(jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement) == 2 &&
      toset(flatten([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement : statement.Action])) == toset([
        "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeVpcAttribute"
      ])
    )
    error_message = "Operator must receive only five network metadata actions, never writes, IAM management, log events or other data-plane reads."
  }

  assert {
    condition = alltrue([for statement in jsondecode(aws_ssoadmin_permission_set_inline_policy.operator.inline_policy).Statement :
      statement.Condition.StringEquals["aws:RequestedRegion"] == "ca-central-1" &&
      toset(statement.Condition.StringEquals["aws:PrincipalAccount"]) == toset(["000000000000", "000000000001"]) &&
      (statement.Sid == "RegionalNetworkMetadata" ? statement.Resource == ["*"] :
      toset(statement.Resource) == toset(["arn:aws:ec2:ca-central-1:000000000000:vpc/*", "arn:aws:ec2:ca-central-1:000000000001:vpc/*"]) && statement.Condition.StringEquals["aws:ResourceTag/Project"] == "test-portfolio")
    ])
    error_message = "Operator's resource wildcard must be limited to region/account metadata, with VPC attributes project-scoped."
  }
}

run "profile_privilege_escalation_regression" {
  command = plan

  assert {
    condition = alltrue(flatten([for policy in [aws_ssoadmin_permission_set_inline_policy.access_admin, aws_ssoadmin_permission_set_inline_policy.developer, aws_ssoadmin_permission_set_inline_policy.operator] : [
      for statement in jsondecode(policy.inline_policy).Statement :
      statement.Effect == "Allow" && !can(statement.NotAction) && !can(statement.NotResource) &&
      alltrue([for action in statement.Action : !strcontains(action, "*") && !contains([
        "iam:PassRole", "secretsmanager:GetSecretValue", "ssm:GetParameter", "ssm:GetParameters", "kms:Decrypt", "s3:GetObject",
        "sso:PutInlinePolicyToPermissionSet", "sso:CreatePermissionSet", "sso:AttachManagedPolicyToPermissionSet"
      ], action)])
    ]]))
    error_message = "No profile may acquire administrative wildcards, IAM escalation, policy editing, secret plaintext or general data-plane permissions."
  }

  assert {
    condition = alltrue(flatten([for policy in [aws_ssoadmin_permission_set_inline_policy.developer, aws_ssoadmin_permission_set_inline_policy.operator] : [
      for statement in jsondecode(policy.inline_policy).Statement : alltrue([for action in statement.Action : startswith(action, "ec2:")])
    ]]))
    error_message = "Developer and Operator must not administer Identity Center or gain planned future service permissions."
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
