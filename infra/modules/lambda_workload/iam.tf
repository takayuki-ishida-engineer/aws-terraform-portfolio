resource "aws_iam_role" "this" {
  name                 = var.role_name
  path                 = "/"
  max_session_duration = 3600
  assume_role_policy   = local.trust_policy
  tags                 = var.role_tags

  lifecycle {
    postcondition {
      condition = !local.scope_is_valid || self.arn == format(
        "arn:%s:iam::%s:role/%s", var.partition, var.account_id, var.role_name
      )
      error_message = "The actual owned role ARN must match expected partition/account/name; root provider account verification remains external."
    }
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "LambdaWorkloadAccess"
  role   = aws_iam_role.this.name
  policy = local.workload_policy
}
