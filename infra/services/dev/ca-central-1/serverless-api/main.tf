locals {
  environment = "dev"
  region      = "ca-central-1"
  service     = "serverless-api"
  project     = "aws-terraform-portfolio"

  name_prefix = "${local.project}-${local.environment}-${local.service}"
}

module "artifact_bucket" {
  source = "../../../../modules/s3_artifact_bucket"

  bucket_name = var.artifact_bucket_name
}

module "secret_metadata" {
  source = "../../../../modules/secrets_manager"

  name        = "${local.name_prefix}/application"
  project_tag = local.project
}

module "lambda_logs" {
  source = "../../../../modules/cloudwatch_logs"

  name = "/aws/lambda/${local.name_prefix}-function"
}

module "api_access_logs" {
  source = "../../../../modules/cloudwatch_logs"

  name = "/aws/apigateway/${local.name_prefix}-access"
}

module "lambda_execution_role" {
  source = "../../../../modules/lambda_execution_role"

  role_name     = "${local.name_prefix}-execution"
  partition     = "aws"
  account_id    = var.aws_account_id
  region        = local.region
  log_group_arn = module.lambda_logs.log_group_arn

  enable_secret_read = var.enable_secret_read
  secret_arn         = var.enable_secret_read ? module.secret_metadata.secret_arn : null
  secret_kms_key_arn = null
}

module "lambda_function" {
  source = "../../../../modules/lambda"

  function_name      = "${local.name_prefix}-function"
  execution_role_arn = module.lambda_execution_role.execution_role_arn
  s3_bucket          = module.artifact_bucket.bucket_name
  s3_key             = var.artifact_key
  s3_object_version  = var.artifact_object_version
  runtime            = var.lambda_runtime
  handler            = var.lambda_handler
  log_group_name     = module.lambda_logs.log_group_name

  environment_variables = var.enable_secret_read ? {
    SECRET_ARN = module.secret_metadata.secret_arn
  } : {}

  # The role ARN output waits for the role, not its inline policy. Complete that
  # policy before deploying the function; this does not prove IAM propagation.
  depends_on = [module.lambda_execution_role]
}

module "http_api" {
  source = "../../../../modules/api_gateway_http"

  api_name             = "${local.name_prefix}-http"
  lambda_function_arn  = module.lambda_function.function_arn
  lambda_invoke_arn    = module.lambda_function.invoke_arn
  access_log_group_arn = module.api_access_logs.log_group_arn
}
