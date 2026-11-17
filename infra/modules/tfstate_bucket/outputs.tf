output "bucket_name" {
  description = "Name of the State bucket, for the bucket setting of each root's untracked backend.s3.tfbackend."
  value       = aws_s3_bucket.this.bucket
}

output "bucket_arn" {
  description = "ARN of the State bucket, for reviewed IAM policies that grant State access."
  value       = aws_s3_bucket.this.arn
}

output "versioning_status" {
  description = "Versioning status of the State bucket (always Enabled)."
  value       = aws_s3_bucket_versioning.this.versioning_configuration[0].status
}
