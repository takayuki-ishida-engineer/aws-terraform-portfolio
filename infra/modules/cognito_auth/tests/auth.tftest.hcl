mock_provider "aws" {}
override_resource {
  override_during = plan
  target          = aws_cognito_user_pool.this
  values          = { "id" : "ca-central-1_TestPool", "arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "endpoint" : "cognito-idp.ca-central-1.amazonaws.com/ca-central-1_TestPool" }
}
override_resource {
  override_during = plan
  target          = aws_cognito_user_pool_client.this
  values          = { "id" : "testclient123" }
}
override_resource {
  override_during = plan
  target          = aws_cognito_managed_login_branding.this
  values          = { "managed_login_branding_id" : "test-branding" }
}
run "standard" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  assert {
    condition     = output.authentication.interface_version == 1 && output.authentication.app_client_id == "testclient123"
    error_message = "Computed authentication contract failed."
  }
}
run "alternate_names" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-alternate-auth"
    domain_prefix              = "test-alternate-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  assert {
    condition     = output.authentication.interface_version == 1 && output.authentication.app_client_id == "testclient123"
    error_message = "Computed authentication contract failed."
  }
}
run "plus" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "PLUS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  assert {
    condition     = output.authentication.interface_version == 1 && output.authentication.app_client_id == "testclient123"
    error_message = "Computed authentication contract failed."
  }
}
run "write_scope" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read", "write"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  assert {
    condition     = output.authentication.interface_version == 1 && output.authentication.app_client_id == "testclient123"
    error_message = "Computed authentication contract failed."
  }
}
run "loopback" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = true
    callback_urls              = ["http://localhost:8080/callback"]
    logout_urls                = ["http://127.0.0.1:8080/logout"]
    default_redirect_uri       = "http://localhost:8080/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  assert {
    condition     = output.authentication.interface_version == 1 && output.authentication.app_client_id == "testclient123"
    error_message = "Computed authentication contract failed."
  }
}
run "reject_feature_plan_0" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "LITE"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.feature_plan]
}
run "reject_feature_plan_1" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "UNKNOWN"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.feature_plan]
}
run "reject_pool_name_2" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "prod-wrong"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.pool_name]
}
run "reject_pool_name_3" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = ""
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.pool_name]
}
run "reject_domain_prefix_4" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "-bad"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.domain_prefix]
}
run "reject_domain_prefix_5" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "with.dot"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.domain_prefix]
}
run "reject_domain_prefix_6" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "amazon-name"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.domain_prefix]
}
run "reject_resource_server_identifier_7" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "*"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.resource_server_identifier]
}
run "reject_resource_server_identifier_8" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "https://*"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.resource_server_identifier]
}
run "reject_scopes_9" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = {}
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.scopes]
}
run "reject_scopes_10" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.scopes]
}
run "reject_scopes_11" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "*" : "All" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.scopes]
}
run "reject_approved_scope_names_12" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = []
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.approved_scope_names]
}
run "reject_approved_scope_names_13" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["admin"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.approved_scope_names]
}
run "reject_mfa_configuration_14" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "OFF"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.mfa_configuration]
}
run "reject_mfa_configuration_15" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "SMS"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.mfa_configuration]
}
run "reject_password_minimum_length_16" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 8
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.password_minimum_length]
}
run "reject_password_minimum_length_17" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14.5
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.password_minimum_length]
}
run "reject_access_token_minutes_18" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 61
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.access_token_minutes]
}
run "reject_access_token_minutes_19" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 0
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.access_token_minutes]
}
run "reject_id_token_minutes_20" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 61
    refresh_token_hours        = 8
  }
  expect_failures = [var.id_token_minutes]
}
run "reject_refresh_token_hours_21" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 25
  }
  expect_failures = [var.refresh_token_hours]
}
run "reject_default_redirect_uri_22" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://other.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.default_redirect_uri]
}
run "reject_callback_urls_23" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = [""]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = ""
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_24" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://*.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://*.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_25" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/#token"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/#token"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_26" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://user:pass@client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://user:pass@client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_27" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["http://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "http://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_28" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["http://localhost:8080/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "http://localhost:8080/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_29" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/$${unresolved}"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/$${unresolved}"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_callback_urls_30" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback", "https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.callback_urls]
}
run "reject_logout_urls_31" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = [""]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_32" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://*.example.invalid/callback"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_33" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/#token"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_34" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://user:pass@client.example.invalid/callback"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_35" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["http://client.example.invalid/callback"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_36" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["http://localhost:8080/callback"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_37" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/$${unresolved}"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_logout_urls_38" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout", "https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.logout_urls]
}
run "reject_scope_account_id" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "bad" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.expected_scope]
}
run "reject_scope_region" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.expected_scope]
}
run "reject_scope_partition" {
  command = plan
  variables {
    expected_scope             = { "environment" : "dev", "partition" : "aws-cn", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.expected_scope]
}
run "reject_scope_environment" {
  command = plan
  variables {
    expected_scope             = { "environment" : "qa", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    pool_name                  = "qa-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
  }
  expect_failures = [var.expected_scope]
}

run "reject_invalid_port" {
  command = plan
  variables {
    pool_name                  = "dev-test-auth"
    domain_prefix              = "test-portfolio-auth"
    feature_plan               = "ESSENTIALS"
    allow_dev_loopback         = false
    callback_urls              = ["https://client.example.invalid:65536/callback"]
    logout_urls                = ["https://client.example.invalid/logout"]
    default_redirect_uri       = "https://client.example.invalid:65536/callback"
    resource_server_identifier = "portfolio-api"
    scopes                     = { "read" : "Read approved records", "write" : "Write approved records" }
    approved_scope_names       = ["read"]
    mfa_configuration          = "ON"
    password_minimum_length    = 14
    access_token_minutes       = 15
    id_token_minutes           = 15
    refresh_token_hours        = 8
    expected_scope             = { environment = "dev", partition = "aws", region = "ca-central-1", account_id = "000000000000" }
  }
  expect_failures = [var.callback_urls]
}
