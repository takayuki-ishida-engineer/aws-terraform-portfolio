resource "aws_ssoadmin_permission_set" "access_admin" {
  name             = "Portfolio-Access-Admin"
  description      = "Delegated assignment of the preapproved Developer and Operator profiles to approved member accounts."
  instance_arn     = var.instance_arn
  session_duration = "PT1H"
  tags             = merge(var.tags, { Name = "${var.name_prefix}-access-admin", Project = var.project_tag })
}

resource "aws_ssoadmin_permission_set" "developer" {
  name             = "Portfolio-Developer"
  description      = "Reviewed portfolio VPC permissions only; no IAM, Identity Center, workload-role, or secret-value administration."
  instance_arn     = var.instance_arn
  session_duration = "PT1H"
  tags             = merge(var.tags, { Name = "${var.name_prefix}-developer", Project = var.project_tag })
}

resource "aws_ssoadmin_permission_set" "operator" {
  name             = "Portfolio-Operator"
  description      = "Portfolio VPC metadata visibility only; no mutations or general data-plane content access."
  instance_arn     = var.instance_arn
  session_duration = "PT1H"
  tags             = merge(var.tags, { Name = "${var.name_prefix}-operator", Project = var.project_tag })
}

resource "aws_ssoadmin_permission_set_inline_policy" "access_admin" {
  instance_arn       = var.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.access_admin.arn
  inline_policy      = local.access_admin_policy
}

resource "aws_ssoadmin_permission_set_inline_policy" "developer" {
  instance_arn       = var.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.developer.arn
  inline_policy      = local.developer_policy
}

resource "aws_ssoadmin_permission_set_inline_policy" "operator" {
  instance_arn       = var.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.operator.arn
  inline_policy      = local.operator_policy
}
