locals {
  # Reviewed portfolio budget is deliberately below the current service maximum.
  # Include every managed attachment here when extending this fixed service map.
  developer_customer_managed_policies = {
    secrets_manager = { name = "Portfolio-Developer-SecretsManager", path = "/" }
  }
  permission_set_managed_policy_limit = 25
  portfolio_managed_policy_budget     = 10
}

resource "aws_ssoadmin_customer_managed_policy_attachment" "developer" {
  for_each = local.developer_customer_managed_policies

  instance_arn       = var.instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.developer.arn
  customer_managed_policy_reference {
    name = each.value.name
    path = each.value.path
  }

  lifecycle {
    precondition {
      condition = (
        length(local.developer_customer_managed_policies) <= local.permission_set_managed_policy_limit &&
        length(local.developer_customer_managed_policies) <= local.portfolio_managed_policy_budget
      )
      error_message = "Managed attachments exceed the reviewed portfolio budget or Identity Center limit; also verify each target account's IAM role attachment quota before provisioning."
    }
  }
}
