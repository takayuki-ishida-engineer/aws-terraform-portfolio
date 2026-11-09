resource "aws_cloudwatch_log_group" "this" {
  name                        = var.access_log_group_name
  retention_in_days           = var.access_log_retention_in_days
  deletion_protection_enabled = var.access_log_deletion_protection_enabled
  kms_key_id                  = var.access_log_kms_key_arn
  log_group_class             = "STANDARD"
  skip_destroy                = false
  tags                        = var.access_log_tags
  lifecycle {
    postcondition {
      condition = !local.function_reference_is_valid || self.arn == format(
        "arn:%s:logs:%s:%s:log-group:%s", local.partition, local.region, local.account_id, var.access_log_group_name
      )
      error_message = "The actual owned bare access-log ARN must match its configured name and the Lambda partition, Region and account; the root must restrict its provider."
    }
  }
}
