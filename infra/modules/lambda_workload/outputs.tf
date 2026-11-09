output "function_arn" {
  description = "Actual function ARN returned by the Lambda provider resource."
  value       = aws_lambda_function.this.arn
}


output "function_name" {
  description = "Configured name of the managed function."
  value       = aws_lambda_function.this.function_name
}


output "invoke_arn" {
  description = "Actual provider invocation ARN for future separately reviewed integrations; this grants no invocation permission."
  value       = aws_lambda_function.this.invoke_arn
}


output "version" {
  description = "Provider function version; publish is fixed false, so this does not create immutable published versions or aliases."
  value       = aws_lambda_function.this.version
}


output "runtime" {
  description = "Explicit runtime configured on the function."
  value       = aws_lambda_function.this.runtime
}


output "architecture" {
  description = "Single configured instruction-set architecture."
  value       = one(aws_lambda_function.this.architectures)
}


output "vpc_configuration" {
  description = "Configured VPC subnet/security group references, empty when detached; existence, same-VPC membership and connectivity are not verified."
  value = {
    subnet_ids         = try(aws_lambda_function.this.vpc_config[0].subnet_ids, toset([]))
    security_group_ids = try(aws_lambda_function.this.vpc_config[0].security_group_ids, toset([]))
  }
}


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
  description = "Actual owned bare log-group reference; the policy scopes its stream resources, not group creation."
  value       = aws_cloudwatch_log_group.this.arn
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
    log_group_arn      = aws_cloudwatch_log_group.this.arn
    enable_secret_read = var.enable_secret_read
    secret_arn         = var.secret_arn
    secret_kms_key_arn = var.secret_kms_key_arn
  }
}

output "log_group_name" {
  description = "Actual configured name of the managed log group, for future separately reviewed workload integration."
  value       = aws_cloudwatch_log_group.this.name
}


output "log_retention_in_days" {
  description = "Explicit finite retention period configured on the log group."
  value       = aws_cloudwatch_log_group.this.retention_in_days
}


output "log_deletion_protection_enabled" {
  description = "Configured service deletion protection; disabling it and applying is required before a later authorized teardown."
  value       = aws_cloudwatch_log_group.this.deletion_protection_enabled
}


output "log_group_class" {
  description = "Configured log group class, fixed to STANDARD in this module."
  value       = aws_cloudwatch_log_group.this.log_group_class
}


output "log_kms_key_arn" {
  description = "Actual KMS key reference from the provider resource; a null input requests normal service encryption without an explicit customer-managed key, and usability is not proved."
  value       = aws_cloudwatch_log_group.this.kms_key_id
}
