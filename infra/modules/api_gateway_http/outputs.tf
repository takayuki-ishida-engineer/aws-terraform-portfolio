output "api_id" {
  description = "Actual managed API ID, ordered after the stage and invoke permission; not evidence of live availability or authorization."
  value       = aws_apigatewayv2_api.this.id

  depends_on = [aws_apigatewayv2_stage.this, aws_lambda_permission.this]
}

output "invoke_url" {
  description = "Actual provider-returned URL of the managed $default stage; clients require SigV4 and separately granted execute-api:Invoke."
  value       = aws_apigatewayv2_stage.this.invoke_url

  depends_on = [aws_apigatewayv2_stage.this, aws_lambda_permission.this]
}

output "execution_arn" {
  description = "Actual API execution ARN, ordered after stage and invoke permission; a reference rather than a client permission grant."
  value       = aws_apigatewayv2_api.this.execution_arn

  depends_on = [aws_apigatewayv2_stage.this, aws_lambda_permission.this]
}

output "access_log_group_name" {
  description = "Actual owned API access Log Group name; reference/configuration evidence, not live delivery or authorization."
  value       = aws_cloudwatch_log_group.this.name
}

output "access_log_group_arn" {
  description = "Actual owned API access Log Group arn; reference/configuration evidence, not live delivery or authorization."
  value       = aws_cloudwatch_log_group.this.arn
}

output "access_log_retention_in_days" {
  description = "Actual owned API access Log Group retention_in_days; reference/configuration evidence, not live delivery or authorization."
  value       = aws_cloudwatch_log_group.this.retention_in_days
}

output "access_log_deletion_protection_enabled" {
  description = "Actual owned API access Log Group deletion_protection_enabled; reference/configuration evidence, not live delivery or authorization."
  value       = aws_cloudwatch_log_group.this.deletion_protection_enabled
}

output "access_log_group_class" {
  description = "Actual owned API access Log Group log_group_class; reference/configuration evidence, not live delivery or authorization."
  value       = aws_cloudwatch_log_group.this.log_group_class
}

output "access_log_kms_key_arn" {
  description = "Actual owned API access Log Group kms_key_id; reference/configuration evidence, not live delivery or authorization."
  value       = aws_cloudwatch_log_group.this.kms_key_id
}
