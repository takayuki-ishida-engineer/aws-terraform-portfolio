resource "aws_secretsmanager_secret" "this" {
  name                    = var.name
  description             = var.description
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days

  # Secret names can exceed AWS's 256-character tag-value limit.
  # project is the authorization tag; it is module-owned so that IAM ABAC does
  # not depend on provider default_tags (docs/deployment-configuration.md section 5).
  tags = merge(var.tags, {
    Name    = try(substr(var.name, 0, 256), "")
    project = var.project_tag
  })
}
