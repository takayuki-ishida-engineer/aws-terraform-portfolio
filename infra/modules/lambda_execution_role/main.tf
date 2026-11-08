resource "aws_iam_role" "this" {
  name                 = var.role_name
  path                 = "/"
  max_session_duration = 3600
  assume_role_policy   = local.trust_policy
  tags                 = var.tags
}

resource "aws_iam_role_policy" "this" {
  name   = "LambdaWorkloadAccess"
  role   = aws_iam_role.this.name
  policy = local.workload_policy
}
