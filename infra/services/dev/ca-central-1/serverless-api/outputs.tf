output "api_invoke_url" {
  description = "Actual API Gateway stage URL; a reference, not proof of deployed availability, SigV4 authorization or successful requests."
  value       = module.http_api.invoke_url
}

output "api_id" {
  description = "Actual API Gateway HTTP API ID."
  value       = module.http_api.api_id
}

output "lambda_function_name" {
  description = "Actual configured workload Lambda function name."
  value       = module.lambda_workload.function_name
}

output "lambda_function_arn" {
  description = "Actual provider-returned workload Lambda function ARN."
  value       = module.lambda_workload.function_arn
}

output "artifact_bucket_name" {
  description = "Actual artifact bucket name ordered after its versioning and security configuration; not evidence of an uploaded ZIP."
  value       = module.artifact_bucket.bucket_name
}

output "secret_metadata_arn" {
  description = "Actual metadata-container ARN for separately authorized initialization; no secret value or AWSCURRENT version is managed here."
  value       = module.secret_metadata.secret_arn
}

output "lambda_log_group_name" {
  description = "Actual Lambda application Log Group name."
  value       = module.lambda_workload.log_group_name
}

output "api_access_log_group_name" {
  description = "Actual separate API Gateway access Log Group name; not proof of log delivery."
  value       = module.http_api.access_log_group_name
}
