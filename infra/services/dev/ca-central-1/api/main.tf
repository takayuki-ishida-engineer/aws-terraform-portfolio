locals {
  environment = "dev"
  # Names and tags follow docs/deployment-configuration.md sections 4 and 5.
  name_prefix = "${var.project}-${local.environment}"
  default_tags = {
    project = var.project
    env     = local.environment
    managed = "terraform"
  }
}
module "api_gateway_rest" {
  source         = "../../../../modules/api_gateway_rest"
  providers      = { aws = aws }
  expected_scope = { environment = local.environment, partition = "aws", region = "ca-central-1", account_id = var.aws_account_id }
  name_prefix    = local.name_prefix
  authentication = module.cognito_auth.authentication
  tags           = var.tags
}
module "cognito_auth" {
  source                     = "../../../../modules/cognito_auth"
  providers                  = { aws = aws }
  expected_scope             = { environment = local.environment, partition = "aws", region = "ca-central-1", account_id = var.aws_account_id }
  name_prefix                = local.name_prefix
  deletion_protection        = var.deletion_protection ? "ACTIVE" : "INACTIVE"
  feature_plan               = var.feature_plan
  allow_dev_loopback         = var.allow_dev_loopback
  callback_urls              = var.callback_urls
  logout_urls                = var.logout_urls
  default_redirect_uri       = var.default_redirect_uri
  resource_server_identifier = var.resource_server_identifier
  scopes                     = var.scopes
  approved_scope_names       = var.approved_scope_names
  mfa_configuration          = var.mfa_configuration
  password_minimum_length    = var.password_minimum_length
  access_token_minutes       = var.access_token_minutes
  id_token_minutes           = var.id_token_minutes
  refresh_token_hours        = var.refresh_token_hours
  tags                       = var.tags
}
