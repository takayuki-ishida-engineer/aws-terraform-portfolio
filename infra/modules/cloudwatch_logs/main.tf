resource "aws_cloudwatch_log_group" "this" {
  name                        = var.name
  retention_in_days           = var.retention_in_days
  deletion_protection_enabled = var.deletion_protection_enabled
  kms_key_id                  = var.kms_key_arn
  log_group_class             = "STANDARD"
  skip_destroy                = false
  tags                        = var.tags
}
