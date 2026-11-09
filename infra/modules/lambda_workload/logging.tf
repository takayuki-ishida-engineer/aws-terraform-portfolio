resource "aws_cloudwatch_log_group" "this" {
  name                        = var.log_group_name
  retention_in_days           = var.log_retention_in_days
  deletion_protection_enabled = var.log_deletion_protection_enabled
  kms_key_id                  = var.log_kms_key_arn
  log_group_class             = "STANDARD"
  skip_destroy                = false
  tags                        = var.log_tags

  lifecycle {
    postcondition {
      condition = !local.scope_is_valid || self.arn == format(
        "arn:%s:logs:%s:%s:log-group:%s", var.partition, var.region, var.account_id, var.log_group_name
      )
      error_message = "The actual owned bare log-group ARN must match expected partition/Region/account/name."
    }
  }
}
