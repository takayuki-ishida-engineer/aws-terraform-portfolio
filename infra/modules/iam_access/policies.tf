locals {
  partition = try(split(":", var.instance_arn)[1], "aws")
  account_arns = [
    for id in sort(tolist(var.target_account_ids)) : "arn:${local.partition}:sso:::account/${id}"
  ]
  assignable_permission_set_arns = [
    aws_ssoadmin_permission_set.developer.arn,
    aws_ssoadmin_permission_set.operator.arn
  ]
  assignment_resources = concat([var.instance_arn], local.account_arns, local.assignable_permission_set_arns)
  administration_condition = {
    StringEquals = { "aws:PrincipalAccount" = var.administration_account_id }
  }

  vpc_arns              = [for id in sort(tolist(var.target_account_ids)) : "arn:${local.partition}:ec2:${var.target_region}:${id}:vpc/*"]
  subnet_arns           = [for id in sort(tolist(var.target_account_ids)) : "arn:${local.partition}:ec2:${var.target_region}:${id}:subnet/*"]
  internet_gateway_arns = [for id in sort(tolist(var.target_account_ids)) : "arn:${local.partition}:ec2:${var.target_region}:${id}:internet-gateway/*"]
  route_table_arns      = [for id in sort(tolist(var.target_account_ids)) : "arn:${local.partition}:ec2:${var.target_region}:${id}:route-table/*"]
  network_arns          = concat(local.vpc_arns, local.subnet_arns, local.internet_gateway_arns, local.route_table_arns)

  regional_equals = {
    "aws:RequestedRegion"  = var.target_region
    "aws:PrincipalAccount" = sort(tolist(var.target_account_ids))
  }
  project_condition = {
    StringEquals = merge(local.regional_equals, { "aws:ResourceTag/project" = var.project_tag })
  }
  # Exactly the approved tag keys (docs/deployment-configuration.md section 5);
  # one canonical spelling avoids ambiguous project/Project duplicates.
  creation_tag_keys = ["Name", "env", "managed", "project", "service"]
  creation_condition = {
    StringEquals                = merge(local.regional_equals, { "aws:RequestTag/project" = var.project_tag })
    "ForAllValues:StringEquals" = { "aws:TagKeys" = local.creation_tag_keys }
  }
  # Fixed, reviewed create pairs: callers cannot inject actions or resource types.
  network_creates = [
    { action = "CreateVpc", resources = local.vpc_arns },
    { action = "CreateSubnet", resources = local.subnet_arns },
    { action = "CreateInternetGateway", resources = local.internet_gateway_arns },
    { action = "CreateRouteTable", resources = local.route_table_arns }
  ]

  metadata_statements = [
    {
      Sid    = "RegionalNetworkMetadata"
      Effect = "Allow"
      Action = [
        "ec2:DescribeVpcs", "ec2:DescribeSubnets",
        "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables"
      ]
      Resource  = ["*"]
      Condition = { StringEquals = local.regional_equals }
    },
    {
      Sid       = "ProjectVpcAttributes"
      Effect    = "Allow"
      Action    = ["ec2:DescribeVpcAttribute"]
      Resource  = local.vpc_arns
      Condition = local.project_condition
    }
  ]

  access_admin_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AssignApprovedProfiles"
        Effect    = "Allow"
        Action    = ["sso:CreateAccountAssignment", "sso:DeleteAccountAssignment"]
        Resource  = local.assignment_resources
        Condition = local.administration_condition
      },
      {
        Sid       = "ReadApprovedAssignments"
        Effect    = "Allow"
        Action    = ["sso:ListAccountAssignments"]
        Resource  = local.assignment_resources
        Condition = local.administration_condition
      },
      {
        Sid       = "ReadApprovedProfiles"
        Effect    = "Allow"
        Action    = ["sso:DescribePermissionSet"]
        Resource  = concat([var.instance_arn], local.assignable_permission_set_arns)
        Condition = local.administration_condition
      },
      {
        Sid    = "ReadAssignmentRequestStatus"
        Effect = "Allow"
        Action = [
          "sso:DescribeAccountAssignmentCreationStatus",
          "sso:DescribeAccountAssignmentDeletionStatus"
        ]
        Resource  = [var.instance_arn]
        Condition = local.administration_condition
      }
    ]
  })

  developer_policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        # Same region/account conditions; combine only Developer's metadata reads.
        merge(local.metadata_statements[0], {
          Action = concat(local.metadata_statements[0].Action, ["ec2:DescribeNetworkAcls", "ec2:DescribeSecurityGroups"])
        }),
        local.metadata_statements[1]
      ],
      [for spec in local.network_creates : {
        Sid       = spec.action
        Effect    = "Allow"
        Action    = ["ec2:${spec.action}"]
        Resource  = spec.resources
        Condition = local.creation_condition
      }],
      [
        {
          Sid       = "UseExistingProjectVpc"
          Effect    = "Allow"
          Action    = ["ec2:CreateSubnet", "ec2:CreateRouteTable"]
          Resource  = local.vpc_arns
          Condition = local.project_condition
        },
        {
          Sid    = "ManageExistingProjectNetwork"
          Effect = "Allow"
          Action = [
            "ec2:DeleteVpc", "ec2:DeleteSubnet", "ec2:DeleteInternetGateway",
            "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
            "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute",
            "ec2:ModifyVpcAttribute", "ec2:ModifySubnetAttribute"
          ]
          Resource  = local.network_arns
          Condition = local.project_condition
        },
        {
          Sid       = "ManageProjectSubnetAssociations"
          Effect    = "Allow"
          Action    = ["ec2:AssociateRouteTable", "ec2:ReplaceRouteTableAssociation", "ec2:DisassociateRouteTable"]
          Resource  = concat(local.route_table_arns, local.subnet_arns)
          Condition = local.project_condition
        },
        {
          Sid      = "EditNonAuthorizationTags"
          Effect   = "Allow"
          Action   = ["ec2:CreateTags", "ec2:DeleteTags"]
          Resource = local.network_arns
          Condition = merge(local.project_condition, {
            "ForAllValues:StringNotEqualsIgnoreCase" = { "aws:TagKeys" = ["project"] }
            Null                                     = { "aws:TagKeys" = "false" }
          })
        }
      ],
      [for spec in local.network_creates : {
        Sid      = "TagDuring${spec.action}"
        Effect   = "Allow"
        Action   = ["ec2:CreateTags"]
        Resource = spec.resources
        Condition = merge(local.creation_condition, {
          StringEquals = merge(local.creation_condition.StringEquals, { "ec2:CreateAction" = spec.action })
        })
      }]
    )
  })

  secret_arns = [for id in sort(tolist(var.target_account_ids)) : "arn:${local.partition}:secretsmanager:${var.target_region}:${id}:secret:*"]
  secret_metadata_statement = {
    Sid       = "ReadProjectSecretMetadata"
    Effect    = "Allow"
    Action    = ["secretsmanager:DescribeSecret"]
    Resource  = local.secret_arns
    Condition = local.project_condition
  }
  operator_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = concat(local.metadata_statements, [local.secret_metadata_statement])
  })
}
