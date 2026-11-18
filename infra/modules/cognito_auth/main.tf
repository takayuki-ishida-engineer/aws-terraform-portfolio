resource "aws_cognito_user_pool" "this" {
  region                   = var.expected_scope.region
  name                     = "${var.name_prefix}-cognito"
  user_pool_tier           = var.feature_plan
  deletion_protection      = var.deletion_protection
  username_attributes      = ["email"]
  auto_verified_attributes = []
  mfa_configuration        = var.mfa_configuration
  username_configuration { case_sensitive = false }
  admin_create_user_config { allow_admin_create_user_only = true }
  software_token_mfa_configuration { enabled = true }
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }
  password_policy {
    minimum_length                   = var.password_minimum_length
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 1
  }
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = "3"
      max_length = "2048"
    }
  }
  # Names and tags follow docs/deployment-configuration.md sections 4 and 5.
  tags = merge(var.tags, { Name = "${var.name_prefix}-cognito", service = "cognito" })
}
resource "aws_cognito_user_pool_domain" "this" {
  region                = var.expected_scope.region
  domain                = "${var.name_prefix}-auth"
  user_pool_id          = aws_cognito_user_pool.this.id
  managed_login_version = 2
}
resource "aws_cognito_resource_server" "this" {
  region       = var.expected_scope.region
  name         = var.resource_server_identifier
  identifier   = var.resource_server_identifier
  user_pool_id = aws_cognito_user_pool.this.id
  dynamic "scope" {
    for_each = var.scopes
    content {
      scope_name        = scope.key
      scope_description = scope.value
    }
  }
}
resource "aws_cognito_user_pool_client" "this" {
  region                               = var.expected_scope.region
  name                                 = "${var.name_prefix}-client"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = concat(["openid", "email"], [for s in sort(tolist(var.approved_scope_names)) : "${aws_cognito_resource_server.this.identifier}/${s}"])
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]
  supported_identity_providers         = ["COGNITO"]
  enable_token_revocation              = true
  prevent_user_existence_errors        = "ENABLED"
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  default_redirect_uri                 = var.default_redirect_uri
  access_token_validity                = var.access_token_minutes
  id_token_validity                    = var.id_token_minutes
  refresh_token_validity               = var.refresh_token_hours
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }
  auth_session_validity = 3
  read_attributes       = ["email", "email_verified"]
  write_attributes      = ["name"]
  depends_on            = [aws_cognito_resource_server.this]
}
resource "aws_cognito_managed_login_branding" "this" {
  region                      = var.expected_scope.region
  user_pool_id                = aws_cognito_user_pool.this.id
  client_id                   = aws_cognito_user_pool_client.this.id
  use_cognito_provided_values = true
  depends_on                  = [aws_cognito_user_pool_domain.this]
}
