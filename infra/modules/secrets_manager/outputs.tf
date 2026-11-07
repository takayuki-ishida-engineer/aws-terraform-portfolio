output "secret_arn" {
  description = "Actual ARN of the secret container, including the suffix assigned by Secrets Manager."
  value       = aws_secretsmanager_secret.this.arn
}

output "secret_name" {
  description = "Stable secret name from the managed container."
  value       = aws_secretsmanager_secret.this.name
}

output "secret_id" {
  description = "Provider resource ID; the AWS provider uses the actual secret ARN."
  value       = aws_secretsmanager_secret.this.id
}

output "kms_configuration" {
  description = "Requested encryption mode and the container's configured KMS reference; this does not verify key capabilities or grant KMS access."
  value = {
    requested_mode           = var.kms_key_arn == null ? "aws-managed" : "customer-managed"
    configured_key_reference = aws_secretsmanager_secret.this.kms_key_id
  }
}

output "resource_policy_managed" {
  description = "Always false: this module does not manage a resource policy or reader role grants."
  value       = false
}
