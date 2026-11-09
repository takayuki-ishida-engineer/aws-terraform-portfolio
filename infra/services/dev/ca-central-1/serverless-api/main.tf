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

module "lambda_workload" {
  source = "../../../../modules/lambda_workload"

  function_name  = "${local.name_prefix}-function"
  role_name      = "${local.name_prefix}-execution"
  partition      = "aws"
  account_id     = var.aws_account_id
  region         = local.region
  log_group_name = "/aws/lambda/${local.name_prefix}-function"

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

  api_name              = "${local.name_prefix}-http"
  lambda_function_arn   = module.lambda_workload.function_arn
  lambda_invoke_arn     = module.lambda_workload.invoke_arn
  access_log_group_name = "/aws/apigateway/${local.name_prefix}-access"
}
