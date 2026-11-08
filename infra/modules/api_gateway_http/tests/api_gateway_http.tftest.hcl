mock_provider "aws" {}


# Synthetic provider-computed identities; no real AWS requests or resources.

override_resource {
  target          = aws_apigatewayv2_api.this
  override_during = plan
  values = {
    id              = "a1b2c3d4e5"
    arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
    execution_arn   = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5"
    api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
    region          = "ca-central-1"
    ip_address_type = "ipv4"
    tags_all        = {}
  }
}

override_resource {
  target          = aws_apigatewayv2_integration.this
  override_during = plan
  values = {
    id                                        = "intg123"
    region                                    = "ca-central-1"
    timeout_milliseconds                      = 30000
    integration_response_selection_expression = null
  }
}

override_resource {
  target          = aws_apigatewayv2_route.this
  override_during = plan
  values = {
    id     = "route123"
    region = "ca-central-1"
  }
}

# Neutralize only the provider-computed WebSocket logging property; actual
# configured throttling values remain untouched and are asserted below.
override_resource {
  target          = aws_apigatewayv2_stage.this
  override_during = plan
  values = {
    id                     = "$default"
    arn                    = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5/stages/$default"
    execution_arn          = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5/$default"
    invoke_url             = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
    region                 = "ca-central-1"
    deployment_id          = "mock-deployment"
    default_route_settings = { logging_level = "OFF" }
    tags_all               = {}
  }
}

override_resource {
  target          = aws_lambda_permission.this
  override_during = plan
  values = {
    id                  = "mock-permission"
    region              = "ca-central-1"
    statement_id_prefix = null
  }
}

variables {
  api_name             = "test-http-api"
  lambda_function_arn  = "arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler"
  lambda_invoke_arn    = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler/invocations"
  access_log_group_arn = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access"
}

run "default_http_api_configuration" {
  command = plan

  assert {
    condition = (
      aws_apigatewayv2_api.this.protocol_type == "HTTP" &&
      !aws_apigatewayv2_api.this.disable_execute_api_endpoint &&
      aws_apigatewayv2_api.this.name == var.api_name &&
      aws_apigatewayv2_api.this.body == null &&
      aws_apigatewayv2_api.this.target == null &&
      length(aws_apigatewayv2_api.this.cors_configuration) == 0 &&
      aws_apigatewayv2_integration.this.api_id == aws_apigatewayv2_api.this.id &&
      aws_apigatewayv2_integration.this.integration_type == "AWS_PROXY" &&
      aws_apigatewayv2_integration.this.integration_method == "POST" &&
      aws_apigatewayv2_integration.this.integration_uri == var.lambda_invoke_arn &&
      aws_apigatewayv2_integration.this.payload_format_version == "2.0" &&
      aws_apigatewayv2_integration.this.connection_type == "INTERNET" &&
      aws_apigatewayv2_integration.this.credentials_arn == null &&
      aws_apigatewayv2_route.this.api_id == aws_apigatewayv2_api.this.id &&
      aws_apigatewayv2_route.this.route_key == "$default" &&
      aws_apigatewayv2_route.this.authorization_type == "AWS_IAM" &&
      aws_apigatewayv2_route.this.authorizer_id == null &&
      aws_apigatewayv2_route.this.target == "integrations/${aws_apigatewayv2_integration.this.id}" &&
      aws_apigatewayv2_stage.this.api_id == aws_apigatewayv2_api.this.id &&
      aws_apigatewayv2_stage.this.name == "$default" &&
      aws_apigatewayv2_stage.this.auto_deploy &&
      aws_apigatewayv2_stage.this.access_log_settings[0].destination_arn == var.access_log_group_arn &&
      aws_apigatewayv2_stage.this.default_route_settings[0].throttling_rate_limit == 10 &&
      aws_apigatewayv2_stage.this.default_route_settings[0].throttling_burst_limit == 20 &&
      aws_lambda_permission.this.action == "lambda:InvokeFunction" &&
      aws_lambda_permission.this.principal == "apigateway.amazonaws.com" &&
      aws_lambda_permission.this.function_name == var.lambda_function_arn &&
      aws_lambda_permission.this.source_arn == "${aws_apigatewayv2_api.this.execution_arn}/$default/$default" &&
      aws_lambda_permission.this.statement_id == "AllowHttpApi${sha256(aws_apigatewayv2_api.this.id)}" &&
      aws_lambda_permission.this.qualifier == null &&
      aws_lambda_permission.this.source_account == null
    )
    error_message = "All five managed resources must preserve the reviewed HTTP API, IAM route, Lambda integration, access logging, throttling and exact invoke-permission configuration."
  }

  assert {
    condition     = jsondecode(aws_apigatewayv2_stage.this.access_log_settings[0].format) == { "requestId" : "$context.requestId", "routeKey" : "$context.routeKey", "httpMethod" : "$context.httpMethod", "status" : "$context.status", "responseLatency" : "$context.responseLatency", "integrationLatency" : "$context.integrationLatency", "responseLength" : "$context.responseLength" }
    error_message = "Access log JSON must contain exactly the reviewed operational context fields, without bodies, headers, credentials or secret data."
  }
}

run "resource_attribute_outputs" {
  command = plan

  assert {
    condition = (
      output.api_id == aws_apigatewayv2_api.this.id &&
      output.execution_arn == aws_apigatewayv2_api.this.execution_arn &&
      output.invoke_url == aws_apigatewayv2_stage.this.invoke_url &&
      output.invoke_url != aws_apigatewayv2_api.this.api_endpoint &&
      output.invoke_url == "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
    )
    error_message = "Outputs must preserve actual API and stage attributes; the stage URL differs from the API endpoint by its provider-returned trailing slash."
  }
}

run "govcloud_reference_scope" {
  command = plan
  variables {
    lambda_function_arn  = "arn:aws-us-gov:lambda:us-gov-west-1:222222222222:function:test-api-handler"
    lambda_invoke_arn    = "arn:aws-us-gov:apigateway:us-gov-west-1:lambda:path/2015-03-31/functions/arn:aws-us-gov:lambda:us-gov-west-1:222222222222:function:test-api-handler/invocations"
    access_log_group_arn = "arn:aws-us-gov:logs:us-gov-west-1:222222222222:log-group:/test/api-access"
  }

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "gov1234567"
      arn             = "arn:aws-us-gov:apigateway:us-gov-west-1::/apis/gov1234567"
      execution_arn   = "arn:aws-us-gov:execute-api:us-gov-west-1:222222222222:gov1234567"
      api_endpoint    = "https://gov1234567.execute-api.us-gov-west-1.amazonaws.com"
      region          = "us-gov-west-1"
      ip_address_type = "ipv4"
      tags_all        = {}
    }
  }
  override_resource {
    target          = aws_apigatewayv2_integration.this
    override_during = plan
    values = {
      id                                        = "intg123"
      region                                    = "us-gov-west-1"
      timeout_milliseconds                      = 30000
      integration_response_selection_expression = null
    }
  }
  override_resource {
    target          = aws_apigatewayv2_route.this
    override_during = plan
    values = {
      id     = "route123"
      region = "us-gov-west-1"
    }
  }
  override_resource {
    target          = aws_apigatewayv2_stage.this
    override_during = plan
    values = {
      id                     = "$default"
      arn                    = "arn:aws-us-gov:apigateway:us-gov-west-1::/apis/gov1234567/stages/$default"
      execution_arn          = "arn:aws-us-gov:execute-api:us-gov-west-1:222222222222:gov1234567/$default"
      invoke_url             = "https://gov1234567.execute-api.us-gov-west-1.amazonaws.com/"
      region                 = "us-gov-west-1"
      deployment_id          = "mock-deployment"
      default_route_settings = { logging_level = "OFF" }
      tags_all               = {}
    }
  }
  override_resource {
    target          = aws_lambda_permission.this
    override_during = plan
    values = {
      id                  = "mock-permission"
      region              = "us-gov-west-1"
      statement_id_prefix = null
    }
  }

  assert {
    condition     = (output.execution_arn == "arn:aws-us-gov:execute-api:us-gov-west-1:222222222222:gov1234567" && aws_lambda_permission.this.source_arn == "${output.execution_arn}/$default/$default" && output.invoke_url == "https://gov1234567.execute-api.us-gov-west-1.amazonaws.com/")
    error_message = "Reviewed GovCloud references, provider-computed API identity and invoke permission must remain coherent without commercial-partition reconstruction."
  }
}

run "minimum_api_name" {
  command = plan
  variables {
    api_name = "a"
  }

  assert {
    condition     = (aws_apigatewayv2_api.this.name == "a")
    error_message = "The inclusive one-character API name boundary must remain supported."
  }
}

run "maximum_api_name" {
  command = plan
  variables {
    api_name = join("", [for i in range(128) : "a"])
  }

  assert {
    condition     = (length(aws_apigatewayv2_api.this.name) == 128 && aws_apigatewayv2_api.this.name == var.api_name)
    error_message = "The inclusive 128-character API name boundary must remain supported."
  }
}

run "caller_owned_tags" {
  command = plan
  variables {
    tags = { "Owner" : "Root-Owned", "Purpose" : "HTTP access", "Empty" : "" }
  }

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
      region          = "ca-central-1"
      ip_address_type = "ipv4"
      tags_all        = { "Owner" : "Root-Owned", "Purpose" : "HTTP access", "Empty" : "" }
    }
  }
  override_resource {
    target          = aws_apigatewayv2_stage.this
    override_during = plan
    values = {
      id                     = "$default"
      arn                    = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5/stages/$default"
      execution_arn          = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5/$default"
      invoke_url             = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
      region                 = "ca-central-1"
      deployment_id          = "mock-deployment"
      default_route_settings = { logging_level = "OFF" }
      tags_all               = { "Owner" : "Root-Owned", "Purpose" : "HTTP access", "Empty" : "" }
    }
  }

  assert {
    condition     = (aws_apigatewayv2_api.this.tags == var.tags && aws_apigatewayv2_stage.this.tags == var.tags)
    error_message = "Caller tags must pass through to both resources without invented project/environment metadata."
  }
}

run "maximum_tag_limits" {
  command = plan
  variables {
    tags = merge({ (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) }, { for i in range(49) : format("tag-%02d", i) => "" })
  }

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
      region          = "ca-central-1"
      ip_address_type = "ipv4"
      tags_all        = merge({ (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) }, { for i in range(49) : format("tag-%02d", i) => "" })
    }
  }
  override_resource {
    target          = aws_apigatewayv2_stage.this
    override_during = plan
    values = {
      id                     = "$default"
      arn                    = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5/stages/$default"
      execution_arn          = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5/$default"
      invoke_url             = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
      region                 = "ca-central-1"
      deployment_id          = "mock-deployment"
      default_route_settings = { logging_level = "OFF" }
      tags_all               = merge({ (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) }, { for i in range(49) : format("tag-%02d", i) => "" })
    }
  }

  assert {
    condition     = (length(aws_apigatewayv2_api.this.tags) == 50 && aws_apigatewayv2_api.this.tags == var.tags && aws_apigatewayv2_stage.this.tags == var.tags)
    error_message = "Fifty tags with inclusive 128-character keys and 256-character values must remain accepted."
  }
}

# Model the provider-computed tag merge; this does not test a real provider merge or AWS preflight.

run "effective_provider_default_tags" {
  command = plan
  variables {
    tags = { "Owner" : "Root-Owned" }
  }

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
      region          = "ca-central-1"
      ip_address_type = "ipv4"
      tags_all        = { "Owner" : "Root-Owned", "CostCentre" : "test-default" }
    }
  }
  override_resource {
    target          = aws_apigatewayv2_stage.this
    override_during = plan
    values = {
      id                     = "$default"
      arn                    = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5/stages/$default"
      execution_arn          = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5/$default"
      invoke_url             = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
      region                 = "ca-central-1"
      deployment_id          = "mock-deployment"
      default_route_settings = { logging_level = "OFF" }
      tags_all               = { "Owner" : "Root-Owned", "CostCentre" : "test-default" }
    }
  }

  assert {
    condition     = (aws_apigatewayv2_api.this.tags_all == tomap({ "Owner" : "Root-Owned", "CostCentre" : "test-default" }) && aws_apigatewayv2_stage.this.tags_all == tomap({ "Owner" : "Root-Owned", "CostCentre" : "test-default" }))
    error_message = "Valid known effective default/caller tag sets must satisfy both resource postconditions."
  }
}

run "empty_api_name" {
  command = plan
  variables {
    api_name = ""
  }
  expect_failures = [var.api_name]
}

run "invalid_api_name" {
  command = plan
  variables {
    api_name = "bad api/name"
  }
  expect_failures = [var.api_name]
}

run "overlong_api_name" {
  command = plan
  variables {
    api_name = join("", [for i in range(129) : "a"])
  }
  expect_failures = [var.api_name]
}

run "null_lambda_function_arn" {
  command = plan
  variables {
    lambda_function_arn = null
  }
  expect_failures = [var.lambda_function_arn]
}

run "malformed_lambda_function_arn" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:ca-central-1:111111111111:function"
  }
  expect_failures = [var.lambda_function_arn]
}

run "lambda_alias_arn" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler:live"
  }
  expect_failures = [var.lambda_function_arn]
}

run "lambda_version_arn" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler:1"
  }
  expect_failures = [var.lambda_function_arn]
}

run "wildcard_lambda_function_arn" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:ca-central-1:111111111111:function:*"
  }
  expect_failures = [var.lambda_function_arn]
}

run "unsupported_lambda_partition" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws-cn:lambda:ca-central-1:111111111111:function:test-api-handler"
  }
  expect_failures = [var.lambda_function_arn]
}

run "unsupported_lambda_region" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:us-gov-west-1:111111111111:function:test-api-handler"
  }
  expect_failures = [var.lambda_function_arn]
}

run "null_lambda_invoke_arn" {
  command = plan
  variables {
    lambda_invoke_arn = null
  }
  expect_failures = [var.lambda_invoke_arn]
}

run "malformed_lambda_invoke_arn" {
  command = plan
  variables {
    lambda_invoke_arn = "arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler"
  }
  expect_failures = [var.lambda_invoke_arn]
}

run "mismatched_lambda_invoke_function" {
  command = plan
  variables {
    lambda_invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:111111111111:function:another-test-handler/invocations"
  }
  expect_failures = [var.lambda_invoke_arn]
}

run "mismatched_lambda_invoke_account" {
  command = plan
  variables {
    lambda_invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:222222222222:function:test-api-handler/invocations"
  }
  expect_failures = [var.lambda_invoke_arn]
}

run "mismatched_lambda_invoke_region" {
  command = plan
  variables {
    lambda_invoke_arn = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:111111111111:function:test-api-handler/invocations"
  }
  expect_failures = [var.lambda_invoke_arn]
}

run "mismatched_lambda_invoke_partition" {
  command = plan
  variables {
    lambda_invoke_arn = "arn:aws-us-gov:apigateway:us-gov-west-1:lambda:path/2015-03-31/functions/arn:aws-us-gov:lambda:us-gov-west-1:222222222222:function:test-api-handler/invocations"
  }
  expect_failures = [var.lambda_invoke_arn]
}

run "null_access_log_group_arn" {
  command = plan
  variables {
    access_log_group_arn = null
  }
  expect_failures = [var.access_log_group_arn]
}

run "malformed_access_log_group_arn" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws:logs:ca-central-1:111111111111:log-group"
  }
  expect_failures = [var.access_log_group_arn]
}

run "wildcard_access_log_group_arn" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access*"
  }
  expect_failures = [var.access_log_group_arn]
}

run "log_stream_instead_of_group" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access:log-stream:test"
  }
  expect_failures = [var.access_log_group_arn]
}

run "log_group_api_suffix" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access:*"
  }
  expect_failures = [var.access_log_group_arn]
}

run "mismatched_log_account" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws:logs:ca-central-1:222222222222:log-group:/test/api-access"
  }
  expect_failures = [var.access_log_group_arn]
}

run "mismatched_log_region" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws:logs:us-east-1:111111111111:log-group:/test/api-access"
  }
  expect_failures = [var.access_log_group_arn]
}

run "mismatched_log_partition" {
  command = plan
  variables {
    access_log_group_arn = "arn:aws-us-gov:logs:ca-central-1:111111111111:log-group:/test/api-access"
  }
  expect_failures = [var.access_log_group_arn]
}

run "empty_tag_key" {
  command = plan
  variables {
    tags = { "" : "test" }
  }
  expect_failures = [var.tags]
}

run "reserved_tag_prefix" {
  command = plan
  variables {
    tags = { "AWS:reserved" : "test" }
  }
  expect_failures = [var.tags]
}

run "null_tag_value" {
  command = plan
  variables {
    tags = { "Owner" : null }
  }
  expect_failures = [var.tags]
}

run "overlong_tag_key" {
  command = plan
  variables {
    tags = { (join("", [for i in range(129) : "K"])) = "test" }
  }
  expect_failures = [var.tags]
}

run "overlong_tag_value" {
  command = plan
  variables {
    tags = { Owner = join("", [for i in range(257) : "v"]) }
  }
  expect_failures = [var.tags]
}

run "too_many_tags" {
  command = plan
  variables {
    tags = { for i in range(51) : format("tag-%02d", i) => "test" }
  }
  expect_failures = [var.tags]
}

run "invalid_tag_key_character" {
  command = plan
  variables {
    tags = { "bad*key" : "test" }
  }
  expect_failures = [var.tags]
}

run "invalid_tag_value_character" {
  command = plan
  variables {
    tags = { "Owner" : "bad*value" }
  }
  expect_failures = [var.tags]
}

run "actual_api_wrong_account" {
  command = plan

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws:execute-api:ca-central-1:222222222222:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
      region          = "ca-central-1"
      ip_address_type = "ipv4"
      tags_all        = {}
    }
  }
  expect_failures = [aws_apigatewayv2_api.this]
}

run "actual_api_wrong_region" {
  command = plan

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws:apigateway:us-east-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws:execute-api:us-east-1:111111111111:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.us-east-1.amazonaws.com"
      region          = "us-east-1"
      ip_address_type = "ipv4"
      tags_all        = {}
    }
  }
  expect_failures = [aws_apigatewayv2_api.this]
}

run "actual_api_wrong_partition" {
  command = plan

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws-us-gov:apigateway:ca-central-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws-us-gov:execute-api:ca-central-1:111111111111:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
      region          = "ca-central-1"
      ip_address_type = "ipv4"
      tags_all        = {}
    }
  }
  expect_failures = [aws_apigatewayv2_api.this]
}

run "effective_api_tags_exceed_limit" {
  command = plan

  override_resource {
    target          = aws_apigatewayv2_api.this
    override_during = plan
    values = {
      id              = "a1b2c3d4e5"
      arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
      execution_arn   = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5"
      api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
      region          = "ca-central-1"
      ip_address_type = "ipv4"
      tags_all        = { for i in range(51) : format("tag-%02d", i) => "test" }
    }
  }
  expect_failures = [aws_apigatewayv2_api.this]
}

run "effective_stage_tags_exceed_limit" {
  command = plan

  override_resource {
    target          = aws_apigatewayv2_stage.this
    override_during = plan
    values = {
      id                     = "$default"
      arn                    = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5/stages/$default"
      execution_arn          = "arn:aws:execute-api:ca-central-1:111111111111:a1b2c3d4e5/$default"
      invoke_url             = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
      region                 = "ca-central-1"
      deployment_id          = "mock-deployment"
      default_route_settings = { logging_level = "OFF" }
      tags_all               = { for i in range(51) : format("tag-%02d", i) => "test" }
    }
  }
  expect_failures = [aws_apigatewayv2_stage.this]
}

run "overlong_lambda_function_arn" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:us-${join("", [for i in range(57) : "a"])}-1:111111111111:function:${join("", [for i in range(64) : "f"])}"
  }
  expect_failures = [var.lambda_function_arn]
}

run "unsupported_numeric_region_shape" {
  command = plan
  variables {
    lambda_function_arn = "arn:aws:lambda:us-east-12:111111111111:function:test-api-handler"
  }
  expect_failures = [var.lambda_function_arn]
}
