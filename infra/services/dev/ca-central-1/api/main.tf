locals {
  required_tags = { Environment = "dev", Service = "api", Project = "aws-terraform-portfolio", ManagedBy = "Terraform" }
}
module "cognito_auth" {
  source                     = "../../../../modules/cognito_auth"
  providers                  = { aws = aws }
  expected_scope             = { environment = "dev", partition = "aws", region = "ca-central-1", account_id = var.aws_account_id }
  pool_name                  = var.pool_name
  domain_prefix              = var.domain_prefix
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
  tags                       = merge(var.tags, local.required_tags)
}
