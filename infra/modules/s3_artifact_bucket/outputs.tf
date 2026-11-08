output "bucket_name" {
  description = "Actual bucket name, ordered after versioning and all security configuration; not proof of propagation, uploaded artifacts or deployment readiness."
  value       = aws_s3_bucket.this.bucket

  depends_on = [
    aws_s3_bucket_versioning.this,
    aws_s3_bucket_public_access_block.this,
    aws_s3_bucket_ownership_controls.this,
    aws_s3_bucket_server_side_encryption_configuration.this,
    aws_s3_bucket_policy.this,
  ]
}

output "bucket_arn" {
  description = "Actual provider-managed bucket ARN, ordered after versioning and security configuration; no authorization grant is implied."
  value       = aws_s3_bucket.this.arn

  depends_on = [
    aws_s3_bucket_versioning.this,
    aws_s3_bucket_public_access_block.this,
    aws_s3_bucket_ownership_controls.this,
    aws_s3_bucket_server_side_encryption_configuration.this,
    aws_s3_bucket_policy.this,
  ]
}

output "versioning_status" {
  description = "Actual configured versioning status, fixed to Enabled; Terraform ordering does not guarantee immediate S3 versioning propagation."
  value       = aws_s3_bucket_versioning.this.versioning_configuration[0].status

  depends_on = [
    aws_s3_bucket_versioning.this,
    aws_s3_bucket_public_access_block.this,
    aws_s3_bucket_ownership_controls.this,
    aws_s3_bucket_server_side_encryption_configuration.this,
    aws_s3_bucket_policy.this,
  ]
}
