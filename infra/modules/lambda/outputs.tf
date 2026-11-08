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

output "execution_role_arn" {
  description = "Configured existing execution role reference; no trust or permissions are created by this module."
  value       = aws_lambda_function.this.role
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

output "log_group_name" {
  description = "Configured reference to the externally managed CloudWatch Log Group; this does not prove that the group exists."
  value       = aws_lambda_function.this.logging_config[0].log_group
}
