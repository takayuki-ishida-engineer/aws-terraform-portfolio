output "log_group_name" {
  description = "Actual configured name of the managed log group, for future separately reviewed workload integration."
  value       = aws_cloudwatch_log_group.this.name
}

output "log_group_arn" {
  description = "Actual provider-managed log group ARN; an identity reference, not a logging permission grant or a predicted log-stream ARN."
  value       = aws_cloudwatch_log_group.this.arn
}

output "retention_in_days" {
  description = "Explicit finite retention period configured on the log group."
  value       = aws_cloudwatch_log_group.this.retention_in_days
}

output "deletion_protection_enabled" {
  description = "Configured service deletion protection; disabling it and applying is required before a later authorized teardown."
  value       = aws_cloudwatch_log_group.this.deletion_protection_enabled
}

output "log_group_class" {
  description = "Configured log group class, fixed to STANDARD in this module."
  value       = aws_cloudwatch_log_group.this.log_group_class
}

output "kms_key_arn" {
  description = "Actual KMS key reference from the provider resource; a null input requests normal service encryption without an explicit customer-managed key, and usability is not proved."
  value       = aws_cloudwatch_log_group.this.kms_key_id
}
