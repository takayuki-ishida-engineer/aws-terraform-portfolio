locals {
  policy_name = "Portfolio-Developer-SecretsManager"
  policy_path = "/"
  secret_arns = ["arn:${var.partition}:secretsmanager:${var.region}:${var.account_id}:secret:*"]
  regional_equals = {
    "aws:RequestedRegion"  = var.region
    "aws:PrincipalAccount" = var.account_id
  }
  project_condition = {
    StringEquals = merge(local.regional_equals, { "aws:ResourceTag/Project" = var.project_tag })
  }
  creation_condition = {
    StringEquals                = merge(local.regional_equals, { "aws:RequestTag/Project" = var.project_tag })
    "ForAllValues:StringEquals" = { "aws:TagKeys" = ["Environment", "ManagedBy", "Name", "Project", "Service"] }
  }
  developer_secrets_manager_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "CreateProjectSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:CreateSecret"]
        Resource = local.secret_arns
        Condition = merge(local.creation_condition, {
          Null         = { "secretsmanager:AddReplicaRegions" = "true" }
          BoolIfExists = { "secretsmanager:ForceOverwriteReplicaSecret" = "false" }
        })
      },
      {
        # Matching resource/request tags follow the published Secrets Manager ABAC model.
        Sid      = "TagProjectSecretIdentity"
        Effect   = "Allow"
        Action   = ["secretsmanager:TagResource"]
        Resource = local.secret_arns
        Condition = merge(local.creation_condition, {
          StringEquals = merge(local.creation_condition.StringEquals, { "aws:ResourceTag/Project" = var.project_tag })
        })
      },
      {
        Sid       = "ReadProjectSecretMetadata"
        Effect    = "Allow"
        Action    = ["secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy"]
        Resource  = local.secret_arns
        Condition = local.project_condition
      },
      {
        Sid      = "EditProjectSecretTags"
        Effect   = "Allow"
        Action   = ["secretsmanager:TagResource", "secretsmanager:UntagResource"]
        Resource = local.secret_arns
        Condition = merge(local.project_condition, {
          "ForAllValues:StringNotEqualsIgnoreCase" = { "aws:TagKeys" = ["Project"] }
          Null                                     = { "aws:TagKeys" = "false" }
        })
      },
      {
        Sid      = "ScheduleProjectSecretDeletion"
        Effect   = "Allow"
        Action   = ["secretsmanager:DeleteSecret"]
        Resource = local.secret_arns
        Condition = merge(local.project_condition, {
          BoolIfExists             = { "secretsmanager:ForceDeleteWithoutRecovery" = "false" }
          NumericGreaterThanEquals = { "secretsmanager:RecoveryWindowInDays" = "7" }
          NumericLessThanEquals    = { "secretsmanager:RecoveryWindowInDays" = "30" }
        })
      }
    ]
  })
}
