override_resource {
  override_during = plan
  target          = aws_api_gateway_rest_api.this
  values          = { id = "resttest123" }
}
override_resource {
  override_during = plan
  target          = aws_api_gateway_authorizer.this
  values          = { id = "authtest123" }
}
mock_provider "aws" {}
run "standard" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
}
run "reject_0" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 2, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_1" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "fake", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_2" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "wrong", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_3" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : [] }
  }
  expect_failures = [var.authentication]
}
run "reject_4" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read", "portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_5" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["other/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_6" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : ".*", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_7" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "111111111111" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_8" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_9" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "prod", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_10" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws-cn", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.authentication]
}
run "reject_11" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "bad" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "bad" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.expected_scope]
}
run "reject_12" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.expected_scope]
}
run "reject_13" {
  command = plan
  variables {
    expected_scope = { "environment" : "unknown", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "unknown", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.expected_scope]
}
run "reject_14" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws-cn", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws-cn", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.expected_scope]
}
run "reject_15" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "bad"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.name_prefix]
}
run "reject_16" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "test-prod"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.name_prefix]
}
run "reject_17" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "te@st-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.name_prefix]
}
run "reject_18" {
  command = plan
  variables {
    expected_scope = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    name_prefix    = "aaaaaaaaaaaaaaaaa-dev"
    authentication = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "user_pool_id" : "ca-central-1_TestPool", "user_pool_arn" : "arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool", "resource_server_identifier" : "portfolio-api", "approved_custom_scopes" : ["portfolio-api/read"] }
  }
  expect_failures = [var.name_prefix]
}
