output "access_admin_permission_set_arn" {
  description = "ARN of the assignment-administration Permission Set; no assignment is created."
  value       = aws_ssoadmin_permission_set.access_admin.arn
}

output "developer_permission_set_arn" {
  description = "ARN of the Developer Permission Set; provisioning and onboarding require an external approved workflow."
  value       = aws_ssoadmin_permission_set.developer.arn
}

output "operator_permission_set_arn" {
  description = "ARN of the metadata-only Operator Permission Set; no assignment is created."
  value       = aws_ssoadmin_permission_set.operator.arn
}
