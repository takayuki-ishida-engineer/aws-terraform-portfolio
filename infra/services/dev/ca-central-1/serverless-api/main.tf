locals {
  environment = "dev"
  region      = "ca-central-1"

  # Names follow docs/deployment-configuration.md section 4: <project>-<env>-<type>[-<purpose>],
  # with the path form for the secret and the API access log group.
  name_prefix = "${var.project}-${local.environment}"
  path_prefix = "/${var.project}/${local.environment}"
}

module "artifact_bucket" {
  source = "../../../../modules/s3_artifact_bucket"

  bucket_name = "${local.name_prefix}-s3-artifact"
}

module "secret_metadata" {
  source = "../../../../modules/secrets_manager"

  name        = "${local.path_prefix}/secret/app"
  project_tag = var.project
  # Seven days lets a destroyed DEV secret be restored and re-imported within a
  # short window (docs/deployment-configuration.md section 9).
  recovery_window_in_days = 7
}

module "lambda_workload" {
  source = "../../../../modules/lambda_workload"

  function_name  = "${local.name_prefix}-lambda"
  role_name      = "${local.name_prefix}-role-lambda"
  policy_name    = "${local.name_prefix}-policy-lambda"
  partition      = "aws"
  account_id     = var.aws_account_id
  region         = local.region
  log_group_name = "/aws/lambda/${local.name_prefix}-lambda"

  s3_bucket         = module.artifact_bucket.bucket_name
  s3_key            = var.artifact_key
  s3_object_version = var.artifact_object_version
  runtime           = var.lambda_runtime
  handler           = var.lambda_handler

  enable_secret_read = var.enable_secret_read
  secret_arn         = var.enable_secret_read ? module.secret_metadata.secret_arn : null
  secret_kms_key_arn = null
  environment_variables = var.enable_secret_read ? {
    SECRET_ARN = module.secret_metadata.secret_arn
  } : {}
}

module "http_api" {
  source = "../../../../modules/api_gateway_http"

  api_name              = "${local.name_prefix}-apigw-http"
  lambda_function_arn   = module.lambda_workload.function_arn
  lambda_invoke_arn     = module.lambda_workload.invoke_arn
  access_log_group_name = "${local.path_prefix}/apigw/http"
}
