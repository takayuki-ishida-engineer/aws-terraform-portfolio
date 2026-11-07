output "policy_arn" {
  description = "Actual customer-managed policy ARN returned by the workload account provider."
  value       = aws_iam_policy.developer_secrets_manager.arn
}

output "policy_name" {
  description = "Fixed reviewed name that the Developer Permission Set must reference in every target account."
  value       = aws_iam_policy.developer_secrets_manager.name
}

output "policy_path" {
  description = "Fixed reviewed IAM policy path; it must match the Identity Center reference exactly."
  value       = aws_iam_policy.developer_secrets_manager.path
}

output "policy_json" {
  description = "Actual rendered non-secret policy JSON for offline export and separately authorized validation."
  value       = aws_iam_policy.developer_secrets_manager.policy
}

output "policy_non_whitespace_characters" {
  description = "Actual compact ASCII policy character count, excluding no characters because it contains no whitespace."
  value       = length(aws_iam_policy.developer_secrets_manager.policy)
}

output "policy_headroom_characters" {
  description = "Remaining headroom under the IAM customer-managed policy's 6,144-character limit."
  value       = 6144 - length(aws_iam_policy.developer_secrets_manager.policy)
}
