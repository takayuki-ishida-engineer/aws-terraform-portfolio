resource "aws_ssoadmin_permission_set" "access_admin" {
  name             = "Portfolio-Access-Admin"
  description      = "Delegated assignment of the preapproved Developer and Operator profiles to approved member accounts."
  instance_arn     = var.instance_arn
  session_duration = "PT1H"
  tags             = merge(var.tags, { Name = "${var.name_prefix}-access-admin", project = var.project_tag })
}

resource "aws_ssoadmin_permission_set" "developer" {
  name             = "Portfolio-Developer"
  description      = "Reviewed VPC and secret-container operations; CreateSecret can initialize values. No value retrieval, policy editing, IAM or workload-role administration."
  instance_arn     = var.instance_arn
  session_duration = "PT1H"
  tags             = merge(var.tags, { Name = "${var.name_prefix}-developer", project = var.project_tag })
}

resource "aws_ssoadmin_permission_set" "operator" {
  name             = "Portfolio-Operator"
  description      = "Portfolio VPC and scoped Secrets Manager metadata only; no mutations, secret values or general data-plane content access."
  instance_arn     = var.instance_arn
  session_duration = "PT1H"
  tags             = merge(var.tags, { Name = "${var.name_prefix}-operator", project = var.project_tag })
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

  # References auto-provision. All workload policies must exist before execution.
  # Attach while the old inline permissions still exist, then update the inline.
  depends_on = [aws_ssoadmin_customer_managed_policy_attachment.developer]

  lifecycle {
    precondition {
      # Generated policy text is ASCII and compact: characters equal UTF-8 bytes.
      condition     = length(local.developer_policy) <= 10240
      error_message = "Developer inline policy exceeds IAM Identity Center's non-whitespace 10,240-byte limit; reduce the reviewed target scope or redesign policy composition before provisioning."
    }
  }
}

resource "aws_ssoadmin_permission_set_inline_policy" "operator" {
  instance_arn       = var.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.operator.arn
  inline_policy      = local.operator_policy
}
