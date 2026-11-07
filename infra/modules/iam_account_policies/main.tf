resource "aws_iam_policy" "developer_secrets_manager" {
  name        = local.policy_name
  path        = local.policy_path
  description = "Reviewed account-specific secret-container permissions; CreateSecret can initialize values. No value retrieval, UpdateSecret, policy editing or KMS grants."
  policy      = local.developer_secrets_manager_policy
  tags        = merge(var.tags, { Name = local.policy_name, Project = var.project_tag })

  lifecycle {
    precondition {
      # All policy-bound inputs are ASCII and jsonencode emits compact JSON.
      condition     = length(local.developer_secrets_manager_policy) <= 6144
      error_message = "The Secrets Manager customer-managed policy exceeds IAM's non-whitespace 6,144-character limit; revise the reviewed scope instead of broadening resources or conditions."
    }
  }
}
