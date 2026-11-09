# R1 compatibility for existing resource addresses; no state operation is run here.

moved {
  from = module.lambda_function.aws_lambda_function.this
  to   = module.lambda_workload.aws_lambda_function.this
}

moved {
  from = module.lambda_execution_role.aws_iam_role.this
  to   = module.lambda_workload.aws_iam_role.this
}

moved {
  from = module.lambda_execution_role.aws_iam_role_policy.this
  to   = module.lambda_workload.aws_iam_role_policy.this
}

moved {
  from = module.lambda_logs.aws_cloudwatch_log_group.this
  to   = module.lambda_workload.aws_cloudwatch_log_group.this
}

# R2: retain the existing API access log identity under its coherent owner.
moved {
  from = module.api_access_logs.aws_cloudwatch_log_group.this
  to   = module.http_api.aws_cloudwatch_log_group.this
}
