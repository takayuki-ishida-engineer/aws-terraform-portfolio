output "bucket_name" {
  description = "State bucket name (<project>-dev-s3-tfstate)."
  value       = module.state_bucket.bucket_name
}

output "bucket_arn" {
  description = "State bucket ARN for reviewed IAM policies that grant State access."
  value       = module.state_bucket.bucket_arn
}

output "backend_settings" {
  description = "Non-secret settings for each root's untracked backend.s3.tfbackend: bucket, Region, S3 native locking, encryption and one State key per root."
  value = {
    bucket       = module.state_bucket.bucket_name
    region       = local.region
    use_lockfile = true
    encrypt      = true
    keys         = { for root in local.backend_roots : root => "${var.project}/${local.environment}/${local.region}/${root}/terraform.tfstate" }
  }
}
