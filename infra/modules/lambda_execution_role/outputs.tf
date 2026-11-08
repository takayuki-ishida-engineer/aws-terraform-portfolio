output "execution_role_arn" {
  description = "Actual execution-role ARN returned by the provider resource; not constructed from expected account metadata."
  value       = aws_iam_role.this.arn
}

output "execution_role_name" {
  description = "Actual configured execution-role name."
  value       = aws_iam_role.this.name
}

output "inline_policy_name" {
  description = "Actual name of the single workload inline policy."
  value       = aws_iam_role_policy.this.name
}

output "log_group_arn" {
  description = "Configured existing bare log-group reference; the policy scopes its stream resources, not group creation."
  value       = var.log_group_arn
}

output "secret_read_enabled" {
  description = "Explicit runtime secret-read configuration status, not proof of effective deployed authorization."
  value       = var.enable_secret_read
}

output "permission_scope" {
  description = "Non-secret configured scope metadata for independent static verification; references only, never credentials or secret values."
  value = {
    role_name          = var.role_name
    partition          = var.partition
    account_id         = var.account_id
    region             = var.region
    log_group_arn      = var.log_group_arn
    enable_secret_read = var.enable_secret_read
    secret_arn         = var.secret_arn
    secret_kms_key_arn = var.secret_kms_key_arn
  }
}
