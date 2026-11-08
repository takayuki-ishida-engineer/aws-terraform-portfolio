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
