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
    tags_all        = { Name = "test-http-api", service = "apigw" }
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
    tags_all               = { Name = "test-http-api-default", service = "apigw" }
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

override_resource {
  target          = aws_cloudwatch_log_group.this
  override_during = plan
  values = {
    arn      = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access"
    region   = "ca-central-1"
    tags_all = {}
  }
}

variables {
  api_name              = "test-http-api"
  lambda_function_arn   = "arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler"
  lambda_invoke_arn     = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:111111111111:function:test-api-handler/invocations"
  access_log_group_name = "/test/api-access"
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
      aws_apigatewayv2_stage.this.access_log_settings[0].destination_arn == aws_cloudwatch_log_group.this.arn &&
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
    error_message = "All six managed resources must preserve the reviewed HTTP API, IAM route, Lambda integration, access logging, throttling and exact invoke-permission configuration."
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
    lambda_function_arn = "arn:aws-us-gov:lambda:us-gov-west-1:222222222222:function:test-api-handler"
    lambda_invoke_arn   = "arn:aws-us-gov:apigateway:us-gov-west-1:lambda:path/2015-03-31/functions/arn:aws-us-gov:lambda:us-gov-west-1:222222222222:function:test-api-handler/invocations"
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
      tags_all        = { Name = "test-http-api", service = "apigw" }
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
      tags_all               = { Name = "test-http-api-default", service = "apigw" }
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

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws-us-gov:logs:us-gov-west-1:222222222222:log-group:/test/api-access"
      region   = "us-gov-west-1"
      tags_all = {}
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
      tags_all        = { Name = "a", service = "apigw" }
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
      tags_all               = { Name = "a-default", service = "apigw" }
    }
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
      tags_all        = { Name = join("", [for i in range(128) : "a"]), service = "apigw" }
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
      tags_all               = { Name = "${join("", [for i in range(128) : "a"])}-default", service = "apigw" }
    }
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
      tags_all        = { "Owner" : "Root-Owned", "Purpose" : "HTTP access", "Empty" : "", Name = "test-http-api", service = "apigw" }
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
      tags_all               = { "Owner" : "Root-Owned", "Purpose" : "HTTP access", "Empty" : "", Name = "test-http-api-default", service = "apigw" }
    }
  }

  assert {
    condition     = (aws_apigatewayv2_api.this.tags == tomap(merge(var.tags, { Name = var.api_name, service = "apigw" })) && aws_apigatewayv2_stage.this.tags == tomap(merge(var.tags, { Name = "${var.api_name}-default", service = "apigw" })))
    error_message = "Caller tags must pass through to both resources beside the module-owned Name and service tags."
  }
}


run "maximum_tag_limits" {
  command = plan
  variables {
    tags = merge({ (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) }, { for i in range(47) : format("tag-%02d", i) => "" })
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
      tags_all        = merge({ (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) }, { for i in range(47) : format("tag-%02d", i) => "" }, { Name = "test-http-api", service = "apigw" })
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
      tags_all               = merge({ (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) }, { for i in range(47) : format("tag-%02d", i) => "" }, { Name = "test-http-api-default", service = "apigw" })
    }
  }

  assert {
    condition     = (length(aws_apigatewayv2_api.this.tags) == 50 && aws_apigatewayv2_api.this.tags == tomap(merge(var.tags, { Name = var.api_name, service = "apigw" })) && aws_apigatewayv2_stage.this.tags == tomap(merge(var.tags, { Name = "${var.api_name}-default", service = "apigw" })))
    error_message = "Fifty tags (48 caller tags plus Name and service) with inclusive 128-character keys and 256-character values must remain accepted."
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
      tags_all        = { "Owner" : "Root-Owned", "CostCentre" : "test-default", Name = "test-http-api", service = "apigw" }
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
      tags_all               = { "Owner" : "Root-Owned", "CostCentre" : "test-default", Name = "test-http-api-default", service = "apigw" }
    }
  }

  assert {
    condition     = (aws_apigatewayv2_api.this.tags_all == tomap({ "Owner" : "Root-Owned", "CostCentre" : "test-default", Name = "test-http-api", service = "apigw" }) && aws_apigatewayv2_stage.this.tags_all == tomap({ "Owner" : "Root-Owned", "CostCentre" : "test-default", Name = "test-http-api-default", service = "apigw" }))
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
  variables { access_log_group_name = null }
  expect_failures = [var.access_log_group_name]
}

run "malformed_access_log_group_arn" {
  command = plan
  variables { access_log_group_name = "invalid name" }
  expect_failures = [var.access_log_group_name]
}

run "wildcard_access_log_group_arn" {
  command = plan
  variables { access_log_group_name = "/test/*" }
  expect_failures = [var.access_log_group_name]
}

run "log_stream_instead_of_group" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access:log-stream:test"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
}

run "log_group_api_suffix" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access:*"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
}

run "mismatched_log_account" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws:logs:ca-central-1:222222222222:log-group:/test/api-access"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
}

run "mismatched_log_region" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws:logs:us-east-1:111111111111:log-group:/test/api-access"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
}

run "mismatched_log_partition" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws-us-gov:logs:ca-central-1:111111111111:log-group:/test/api-access"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
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
      tags_all        = { Name = "test-http-api", service = "apigw" }
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
      tags_all        = { Name = "test-http-api", service = "apigw" }
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
      tags_all        = { Name = "test-http-api", service = "apigw" }
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

run "logging_default_log_group_configuration" {
  command = plan

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.name == var.access_log_group_name &&
      aws_cloudwatch_log_group.this.retention_in_days == 30 &&
      aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      aws_cloudwatch_log_group.this.log_group_class == "STANDARD" &&
      aws_cloudwatch_log_group.this.kms_key_id == null &&
      !aws_cloudwatch_log_group.this.skip_destroy &&
      aws_cloudwatch_log_group.this.tags == tomap({ Name = var.access_log_group_name, service = "apigw" })
    )
    error_message = "Defaults must preserve the supplied name, finite 30-day retention, deletion protection, STANDARD class, ordinary service encryption, only the module-owned Name/service tags and no skip-destroy orphaning."
  }
}


run "logging_resource_attribute_outputs" {
  command = plan

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition = (
      output.access_log_group_name == aws_cloudwatch_log_group.this.name &&
      output.access_log_group_arn == aws_cloudwatch_log_group.this.arn &&
      output.access_log_group_arn == "arn:aws:logs:ca-central-1:111111111111:log-group:/test/api-access" &&
      output.access_log_retention_in_days == aws_cloudwatch_log_group.this.retention_in_days &&
      output.access_log_deletion_protection_enabled == aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      output.access_log_group_class == aws_cloudwatch_log_group.this.log_group_class &&
      output.access_log_kms_key_arn == aws_cloudwatch_log_group.this.kms_key_id
    )
    error_message = "Every operational output must read the actual resource attribute, including the provider-computed identity ARN and configured encryption reference."
  }
}


run "logging_lambda_log_group_name" {
  command = plan
  variables { access_log_group_name = "/aws/lambda/portfolio-api-handler" }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/aws/lambda/portfolio-api-handler")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == "/aws/lambda/portfolio-api-handler"
    error_message = "A preprovisioned /aws/lambda/ name is valid; only the literal aws/ prefix is rejected."
  }
}


run "logging_workload_log_group_name" {
  command = plan
  variables { access_log_group_name = "/portfolio/dev/serverless-api" }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/portfolio/dev/serverless-api")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == var.access_log_group_name
    error_message = "A stable workload-owned name must pass through without random suffixes or module invention."
  }
}


run "logging_maximum_name_length" {
  command = plan
  variables { access_log_group_name = join("", [for i in range(512) : "x"]) }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", join("", [for i in range(512) : "x"]))
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = length(aws_cloudwatch_log_group.this.name) == 512 && output.access_log_group_name == var.access_log_group_name
    error_message = "The documented inclusive 512-character name limit must remain usable."
  }
}


run "logging_supported_name_characters" {
  command = plan
  variables { access_log_group_name = "/portfolio/test/log_group-1.#" }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/portfolio/test/log_group-1.#")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == var.access_log_group_name
    error_message = "CloudWatch Logs name characters include slash, underscore, hyphen, dot and hash."
  }
}


run "logging_minimum_finite_retention" {
  command = plan
  variables { access_log_retention_in_days = 1 }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 1 && output.access_log_retention_in_days == 1
    error_message = "The supported minimum one-day retention must reach the resource and output."
  }
}


run "logging_weekly_retention" {
  command = plan
  variables { access_log_retention_in_days = 7 }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 7
    error_message = "An explicit supported seven-day root override must be preserved."
  }
}


run "logging_supported_400_day_retention" {
  command = plan
  variables { access_log_retention_in_days = 400 }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 400
    error_message = "Supported retention choices need not be a simple multiple of 30 or 365."
  }
}


run "logging_supported_731_day_retention" {
  command = plan
  variables { access_log_retention_in_days = 731 }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 731
    error_message = "The supported leap-year-aware 731-day retention must be accepted exactly."
  }
}


run "logging_maximum_supported_retention" {
  command = plan
  variables { access_log_retention_in_days = 3653 }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 3653
    error_message = "The documented maximum supported finite retention is 3653 days, not indefinite retention."
  }
}


run "logging_explicit_disposable_development_override" {
  command = plan
  variables { access_log_deletion_protection_enabled = false }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition = (
      !aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      !output.access_log_deletion_protection_enabled &&
      !aws_cloudwatch_log_group.this.skip_destroy &&
      aws_cloudwatch_log_group.this.retention_in_days == 30
    )
    error_message = "An explicit development protection override must not enable skip_destroy or change finite retention."
  }
}


run "logging_existing_symmetric_key_reference" {
  command = plan
  variables {
    access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:key/00000000-0000-0000-0000-111111111111"
  }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.access_log_kms_key_arn && output.access_log_kms_key_arn == var.access_log_kms_key_arn
    error_message = "The supplied key reference must pass through; this does not prove key existence, symmetry or authorization."
  }
}


run "logging_existing_multi_region_key_reference" {
  command = plan
  variables {
    access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:key/mrk-11111111111111111111111100000000"
  }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.access_log_kms_key_arn
    error_message = "A format-valid regional reference to an existing multi-region key is accepted without creating a key or replica."
  }
}


run "logging_govcloud_partition_key_syntax" {
  command = plan
  variables {
    access_log_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:111111111111:key/00000000-0000-0000-0000-111111111111"
  }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.access_log_kms_key_arn
    error_message = "A supported GovCloud ARN shape is accepted; selecting a compatible provider and usable regional key remains external."
  }
}


run "logging_china_partition_key_syntax" {
  command = plan
  variables {
    access_log_kms_key_arn = "arn:aws-cn:kms:cn-north-1:111111111111:key/00000000-0000-0000-0000-111111111111"
  }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.access_log_kms_key_arn
    error_message = "A supported China ARN shape is accepted without claiming real regional or account compatibility."
  }
}


run "logging_caller_owned_unicode_tags" {
  command = plan
  variables {
    access_log_tags = { Project = "Root-Owned", "運用:部門" = "本番 構成 +:@/=", Environment = "test" }
  }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.tags == tomap(merge(var.access_log_tags, { Name = var.access_log_group_name, service = "apigw" })) &&
      aws_cloudwatch_log_group.this.tags.Project == "Root-Owned"
    )
    error_message = "Caller metadata and API-supported Unicode/colon tags must pass through; only the module-owned Name and service win."
  }
}


run "logging_maximum_tag_count_and_lengths" {
  command = plan
  variables {
    access_log_tags = merge(
      { (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) },
      { for i in range(47) : format("tag-%02d", i) => "" }
    )
  }

  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = format("arn:aws:logs:ca-central-1:111111111111:log-group:%s", "/test/api-access")
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.tags == tomap(merge(var.access_log_tags, { Name = var.access_log_group_name, service = "apigw" })) &&
      length(aws_cloudwatch_log_group.this.tags) == 50 &&
      length(aws_cloudwatch_log_group.this.tags[join("", [for i in range(128) : "K"])]) == 256
    )
    error_message = "The documented API limits of 50 tags, 128-character keys, 256-character values and empty values must remain usable."
  }
}


run "logging_empty_name" {
  command = plan
  variables { access_log_group_name = "" }
  expect_failures = [var.access_log_group_name]
}


run "logging_null_name" {
  command = plan
  variables { access_log_group_name = null }
  expect_failures = [var.access_log_group_name]
}


run "logging_name_with_space" {
  command = plan
  variables { access_log_group_name = "invalid name" }
  expect_failures = [var.access_log_group_name]
}


run "logging_name_with_unsupported_character" {
  command = plan
  variables { access_log_group_name = "invalid:name" }
  expect_failures = [var.access_log_group_name]
}


run "logging_literal_aws_prefix" {
  command = plan
  variables { access_log_group_name = "aws/lambda/portfolio-api-handler" }
  expect_failures = [var.access_log_group_name]
}


run "logging_overlong_name" {
  command = plan
  variables { access_log_group_name = join("", [for i in range(513) : "x"]) }
  expect_failures = [var.access_log_group_name]
}


run "logging_indefinite_retention" {
  command = plan
  variables { access_log_retention_in_days = 0 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_negative_retention" {
  command = plan
  variables { access_log_retention_in_days = -1 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_unsupported_short_retention" {
  command = plan
  variables { access_log_retention_in_days = 2 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_fractional_retention" {
  command = plan
  variables { access_log_retention_in_days = 1.5 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_unsupported_366_day_retention" {
  command = plan
  variables { access_log_retention_in_days = 366 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_unsupported_3650_day_retention" {
  command = plan
  variables { access_log_retention_in_days = 3650 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_above_maximum_retention" {
  command = plan
  variables { access_log_retention_in_days = 3654 }
  expect_failures = [var.access_log_retention_in_days]
}


run "logging_empty_kms_reference" {
  command = plan
  variables { access_log_kms_key_arn = "" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_key_id_is_not_key_arn" {
  command = plan
  variables { access_log_kms_key_arn = "00000000-0000-0000-0000-111111111111" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_kms_alias_is_not_key_arn" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:alias/portfolio-test" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_incomplete_kms_key_arn" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:key/" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_wildcard_kms_key_arn" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:key/*" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_malformed_kms_account" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:kms:ca-central-1:00000000000:key/00000000-0000-0000-0000-111111111111" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_unsupported_kms_partition" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws-iso:kms:us-iso-east-1:111111111111:key/00000000-0000-0000-0000-111111111111" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_non_hexadecimal_kms_identifier" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:key/00000000-0000-0000-0000-00000000000g" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_incomplete_multi_region_key_identifier" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:kms:ca-central-1:111111111111:key/mrk-0000" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_wrong_service_key_arn" {
  command = plan
  variables { access_log_kms_key_arn = "arn:aws:logs:ca-central-1:111111111111:key/00000000-0000-0000-0000-111111111111" }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_overlong_kms_key_arn" {
  command = plan
  variables {
    access_log_kms_key_arn = "arn:aws:kms:ca-${join("", [for i in range(200) : "a"])}-1:111111111111:key/00000000-0000-0000-0000-111111111111"
  }
  expect_failures = [var.access_log_kms_key_arn]
}


run "logging_empty_tag_key" {
  command = plan
  variables { access_log_tags = { "" = "invalid" } }
  expect_failures = [var.access_log_tags]
}


run "logging_reserved_tag_prefix" {
  command = plan
  variables { access_log_tags = { "aws:owner" = "invalid" } }
  expect_failures = [var.access_log_tags]
}


run "logging_case_variant_reserved_tag_prefix" {
  command = plan
  variables { access_log_tags = { "AWS:owner" = "invalid" } }
  expect_failures = [var.access_log_tags]
}


run "logging_null_tag_value" {
  command = plan
  variables { access_log_tags = { Test = null } }
  expect_failures = [var.access_log_tags]
}


run "logging_overlong_tag_key" {
  command = plan
  variables { access_log_tags = { (join("", [for i in range(129) : "K"])) = "invalid" } }
  expect_failures = [var.access_log_tags]
}


run "logging_overlong_tag_value" {
  command = plan
  variables { access_log_tags = { Test = join("", [for i in range(257) : "v"]) } }
  expect_failures = [var.access_log_tags]
}


run "logging_too_many_tags" {
  command = plan
  variables { access_log_tags = { for i in range(51) : format("tag-%02d", i) => "invalid" } }
  expect_failures = [var.access_log_tags]
}


run "logging_unsupported_tag_key_character" {
  command = plan
  variables { access_log_tags = { "invalid#key" = "invalid" } }
  expect_failures = [var.access_log_tags]
}


run "logging_unsupported_tag_value_character" {
  command = plan
  variables { access_log_tags = { Test = "invalid!value" } }
  expect_failures = [var.access_log_tags]
}

run "actual_log_wrong_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "arn:aws:logs:ca-central-1:111111111111:log-group:/test/other"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
}

run "actual_log_malformed_arn" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn      = "not-an-arn"
      region   = "ca-central-1"
      tags_all = {}
    }
  }

  expect_failures = [aws_cloudwatch_log_group.this]
}
