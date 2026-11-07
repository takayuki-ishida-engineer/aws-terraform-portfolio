resource "aws_secretsmanager_secret" "this" {
  name                    = var.name
  description             = var.description
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days

  # Secret names can exceed AWS's 256-character tag-value limit.
  tags = merge(var.tags, {
    Name    = try(substr(var.name, 0, 256), "")
    Project = var.project_tag
  })
}
