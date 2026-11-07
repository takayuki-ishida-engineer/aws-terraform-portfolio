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

output "developer_customer_managed_policy_references" {
  description = "Reviewed policy names/paths; each target account must already contain a matching IAM policy before provisioning."
  value = {
    for service, attachment in aws_ssoadmin_customer_managed_policy_attachment.developer : service => {
      name = one(attachment.customer_managed_policy_reference).name
      path = one(attachment.customer_managed_policy_reference).path
    }
  }
}

output "developer_inline_policy_quota" {
  description = "Actual compact ASCII policy size and remaining non-whitespace byte capacity; not an AWS authorization result."
  value = {
    non_whitespace_bytes       = length(local.developer_policy)
    limit_non_whitespace_bytes = 10240
    remaining_bytes            = 10240 - length(local.developer_policy)
  }
}

output "developer_managed_attachment_quota" {
  description = "Actual managed reference count, conservative portfolio budget and current service limit; target IAM role quota requires external verification."
  value = {
    count                     = length(local.developer_customer_managed_policies)
    portfolio_budget          = local.portfolio_managed_policy_budget
    permission_set_limit      = local.permission_set_managed_policy_limit
    remaining_portfolio_slots = local.portfolio_managed_policy_budget - length(local.developer_customer_managed_policies)
  }
}
