mock_provider "aws" {}

# Actual four-resource module, deterministic provider-computed identities only.
# Source case mapping lives in coverage.json; no AWS identity or artifact is real.
variables {
  function_name     = "portfolio-test-lambda"
  role_name         = "portfolio-test-lambda-execution"
  policy_name       = "portfolio-test-lambda-policy"
  partition         = "aws"
  account_id        = "000000000000"
  region            = "ca-central-1"
  log_group_name    = "/portfolio/test/lambda"
  s3_bucket         = "portfolio-test-artifacts"
  s3_key            = "lambda/test/function.zip"
  s3_object_version = "synthetic-version-001"
  runtime           = "python3.13"
  handler           = "app.handler"
}

override_resource {
  target          = aws_iam_role.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::000000000000:role/portfolio-test-lambda-execution"
  }
}
override_resource {
  target          = aws_cloudwatch_log_group.this
  override_during = plan
  values = {
    arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/lambda"
  }
}
override_resource {
  target          = aws_lambda_function.this
  override_during = plan
  values = {
    arn        = "arn:aws:lambda:ca-central-1:000000000000:function:portfolio-test-lambda"
    invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:portfolio-test-lambda/invocations"
    version    = "$LATEST"
  }
}

run "lambda_default_function_configuration" {
  command = plan

  assert {
    condition = (
      aws_lambda_function.this.function_name == var.function_name &&
      aws_lambda_function.this.description == null &&
      aws_lambda_function.this.role == aws_iam_role.this.arn &&
      aws_lambda_function.this.runtime == "python3.13" &&
      aws_lambda_function.this.handler == "app.handler" &&
      aws_lambda_function.this.architectures == tolist(["x86_64"]) &&
      aws_lambda_function.this.memory_size == 128 &&
      aws_lambda_function.this.timeout == 10 &&
      aws_lambda_function.this.ephemeral_storage[0].size == 512
    )
    error_message = "The function must retain the explicit role/runtime/handler and reviewed compute defaults."
  }

  assert {
    condition = (
      aws_lambda_function.this.package_type == "Zip" &&
      aws_lambda_function.this.s3_bucket == var.s3_bucket &&
      aws_lambda_function.this.s3_key == var.s3_key &&
      aws_lambda_function.this.s3_object_version == var.s3_object_version &&
      !aws_lambda_function.this.publish &&
      aws_lambda_function.this.tracing_config[0].mode == "PassThrough" &&
      aws_lambda_function.this.logging_config[0].log_format == "Text" &&
      aws_lambda_function.this.logging_config[0].log_group == var.log_group_name
    )
    error_message = "The module must reference the versioned ZIP and existing log group without publishing or activating X-Ray."
  }

  assert {
    condition = (
      length(aws_lambda_function.this.vpc_config) == 0 &&
      length(aws_lambda_function.this.environment) == 0 &&
      length(aws_lambda_function.this.layers) == 0 &&
      aws_lambda_function.this.reserved_concurrent_executions == null &&
      aws_lambda_function.this.tags == tomap({ Name = var.function_name, service = "lambda" })
    )
    error_message = "Defaults must add no VPC/environment/layers, only the module-owned Name/service tags and no reserved concurrency override."
  }
}


run "lambda_resource_attribute_outputs" {
  command = plan
  assert {
    condition = (
      output.function_arn == aws_lambda_function.this.arn &&
      output.function_arn == "arn:aws:lambda:ca-central-1:000000000000:function:portfolio-test-lambda" &&
      output.function_name == aws_lambda_function.this.function_name &&
      output.invoke_arn == aws_lambda_function.this.invoke_arn &&
      output.version == aws_lambda_function.this.version &&
      output.version == "$LATEST" &&
      output.execution_role_arn == aws_lambda_function.this.role &&
      output.runtime == aws_lambda_function.this.runtime &&
      output.architecture == aws_lambda_function.this.architectures[0] &&
      output.log_group_name == aws_lambda_function.this.logging_config[0].log_group &&
      output.vpc_configuration == { subnet_ids = toset([]), security_group_ids = toset([]) }
    )
    error_message = "Operational outputs must reference actual resource attributes and retain the unpublished version."
  }
}


run "lambda_node_runtime_and_compute_overrides" {
  command = plan
  variables {
    runtime                = "nodejs22.x"
    handler                = "index.handler"
    description            = "Synthetic non-sensitive request handler"
    memory_size            = 512
    timeout                = 30
    ephemeral_storage_size = 1024
  }
  assert {
    condition = (
      aws_lambda_function.this.runtime == "nodejs22.x" &&
      aws_lambda_function.this.handler == "index.handler" &&
      aws_lambda_function.this.description == var.description &&
      aws_lambda_function.this.memory_size == 512 &&
      aws_lambda_function.this.timeout == 30 &&
      aws_lambda_function.this.ephemeral_storage[0].size == 1024 &&
      output.runtime == "nodejs22.x"
    )
    error_message = "An explicitly selected Node runtime and compute overrides must reach the function."
  }
}


run "lambda_java_runtime_on_arm64" {
  command = plan
  variables {
    runtime      = "java21"
    handler      = "org.example.Handler::handleRequest"
    architecture = "arm64"
    memory_size  = 1024
  }
  assert {
    condition = (
      aws_lambda_function.this.runtime == "java21" &&
      aws_lambda_function.this.handler == "org.example.Handler::handleRequest" &&
      aws_lambda_function.this.architectures == tolist(["arm64"]) &&
      output.architecture == "arm64" &&
      output.runtime == "java21"
    )
    error_message = "Java handlers and arm64 must be supported without assuming a Python or Node handler shape."
  }
}


run "lambda_maximum_compute_boundaries" {
  command = plan
  variables {
    memory_size            = 10240
    timeout                = 900
    ephemeral_storage_size = 10240
  }
  assert {
    condition = (
      aws_lambda_function.this.memory_size == 10240 &&
      aws_lambda_function.this.timeout == 900 &&
      aws_lambda_function.this.ephemeral_storage[0].size == 10240
    )
    error_message = "Documented inclusive compute maxima must be preserved."
  }
}


run "lambda_minimum_timeout_and_name_description_boundaries" {
  command = plan
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:ca-central-1:000000000000:function:${join("", [for i in range(64) : "x"])}"
      invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:${join("", [for i in range(64) : "x"])}/invocations"
      version    = "$LATEST"
    }
  }
  variables {
    function_name = join("", [for i in range(64) : "x"])
    description   = join("", [for i in range(256) : "x"])
    timeout       = 1
  }
  assert {
    condition = (
      length(aws_lambda_function.this.function_name) == 64 &&
      length(aws_lambda_function.this.description) == 256 &&
      aws_lambda_function.this.timeout == 1
    )
    error_message = "Inclusive name/description limits and the one-second timeout minimum must remain usable."
  }
}


run "lambda_existing_versioned_layers_and_concurrency" {
  command = plan
  variables {
    layers = [
      "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common:1",
      "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-observability:2"
    ]
    reserved_concurrent_executions = 20
  }
  assert {
    condition = (
      aws_lambda_function.this.layers == var.layers &&
      aws_lambda_function.this.reserved_concurrent_executions == 20
    )
    error_message = "Existing layer versions and an explicit concurrency reservation must pass through unchanged."
  }
}


run "lambda_maximum_layer_count_and_zero_concurrency" {
  command = plan
  variables {
    layers                         = [for i in range(5) : "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-layer-${i}:1"]
    reserved_concurrent_executions = 0
  }
  assert {
    condition = (
      length(aws_lambda_function.this.layers) == 5 &&
      aws_lambda_function.this.reserved_concurrent_executions == 0
    )
    error_message = "Five existing layers and an intentional zero concurrency throttle are supported."
  }
}


run "lambda_existing_vpc_references" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001", "subnet-00000000000000002"]
    security_group_ids = ["sg-00000000000000001", "sg-00000000000000002"]
  }
  assert {
    condition = (
      toset(aws_lambda_function.this.vpc_config[0].subnet_ids) == toset(var.subnet_ids) &&
      toset(aws_lambda_function.this.vpc_config[0].security_group_ids) == toset(var.security_group_ids) &&
      output.vpc_configuration == {
        subnet_ids         = toset(var.subnet_ids)
        security_group_ids = toset(var.security_group_ids)
      }
    )
    error_message = "VPC attachment must use exactly the supplied subnet and security-group references."
  }
}


run "lambda_maximum_vpc_reference_counts" {
  command = plan
  variables {
    subnet_ids         = [for i in range(16) : format("subnet-%017x", i)]
    security_group_ids = [for i in range(5) : format("sg-%017x", i)]
  }
  assert {
    condition = (
      length(aws_lambda_function.this.vpc_config[0].subnet_ids) == 16 &&
      length(aws_lambda_function.this.vpc_config[0].security_group_ids) == 5
    )
    error_message = "The supported inclusive VPC reference counts must be accepted."
  }
}


run "lambda_nonsecret_configuration_and_secret_reference" {
  command = plan
  variables {
    environment_variables = {
      APP_MODE   = "test"
      SECRET_ARN = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/metadata-ABC123"
    }
  }
  assert {
    condition     = aws_lambda_function.this.environment[0].variables == var.environment_variables
    error_message = "Only these supplied non-secret settings and secret metadata reference must be passed through."
  }
}


run "lambda_environment_byte_boundary" {
  command = plan
  variables { environment_variables = { APP_MODE = format("%4088s", "x") } }
  assert {
    condition     = aws_lambda_function.this.environment[0].variables == var.environment_variables
    error_message = "A 4096-byte total key/value configuration must remain usable without introducing secret values."
  }
}


run "lambda_caller_owned_tags" {
  command = plan
  variables {
    tags = { Name = "test-function", Project = "test-portfolio", Environment = "test" }
  }
  assert {
    condition     = aws_lambda_function.this.tags == tomap(merge(var.tags, { Name = var.function_name, service = "lambda" }))
    error_message = "Caller-owned non-sensitive tags must pass through; only the module-owned Name and service win."
  }
}

# Every invalid case names the variable whose own validation must reject it.


run "lambda_empty_function_name" {
  command = plan
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:ca-central-1:000000000000:function:"
      invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:/invocations"
      version    = "$LATEST"
    }
  }
  variables { function_name = "" }
  expect_failures = [var.function_name]
}


run "lambda_invalid_function_name" {
  command = plan
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:ca-central-1:000000000000:function:not a function"
      invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:not a function/invocations"
      version    = "$LATEST"
    }
  }
  variables { function_name = "not a function" }
  expect_failures = [var.function_name]
}


run "lambda_overlong_function_name" {
  command = plan
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:ca-central-1:000000000000:function:${join("", [for i in range(65) : "x"])}"
      invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:${join("", [for i in range(65) : "x"])}/invocations"
      version    = "$LATEST"
    }
  }
  variables { function_name = join("", [for i in range(65) : "x"]) }
  expect_failures = [var.function_name]
}


run "lambda_null_function_name" {
  command = plan
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:ca-central-1:000000000000:function:invalid"
      invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:invalid/invocations"
      version    = "$LATEST"
    }
  }
  variables { function_name = null }
  expect_failures = [var.function_name]
}


run "lambda_overlong_description" {
  command = plan
  variables { description = join("", [for i in range(257) : "x"]) }
  expect_failures = [var.description]
}


run "lambda_sts_session_is_not_execution_role" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:sts::000000000000:assumed-role/example/session"
    }
  }
  expect_failures = [aws_iam_role.this]
}


run "lambda_wildcard_execution_role_rejected" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/*"
    }
  }
  expect_failures = [aws_iam_role.this]
}


run "lambda_malformed_execution_role_account" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::not-an-account:role/example"
    }
  }
  expect_failures = [aws_iam_role.this]
}


run "lambda_bucket_arn_is_not_bucket_name" {
  command = plan
  variables { s3_bucket = "arn:aws:s3:::portfolio-test-artifacts" }
  expect_failures = [var.s3_bucket]
}


run "lambda_uppercase_bucket_rejected" {
  command = plan
  variables { s3_bucket = "Portfolio-Test-Artifacts" }
  expect_failures = [var.s3_bucket]
}


run "lambda_empty_artifact_key" {
  command = plan
  variables { s3_key = "" }
  expect_failures = [var.s3_key]
}


run "lambda_empty_artifact_version" {
  command = plan
  variables { s3_object_version = "" }
  expect_failures = [var.s3_object_version]
}


run "lambda_blank_artifact_version" {
  command = plan
  variables { s3_object_version = "   " }
  expect_failures = [var.s3_object_version]
}


run "lambda_unversioned_null_artifact_rejected" {
  command = plan
  variables { s3_object_version = "null" }
  expect_failures = [var.s3_object_version]
}


run "lambda_missing_artifact_version" {
  command = plan
  variables { s3_object_version = null }
  expect_failures = [var.s3_object_version]
}


run "lambda_unsupported_runtime" {
  command = plan
  variables { runtime = "nodejs99.x" }
  expect_failures = [var.runtime]
}


run "lambda_missing_runtime" {
  command = plan
  variables { runtime = null }
  expect_failures = [var.runtime]
}


run "lambda_empty_handler" {
  command = plan
  variables { handler = "" }
  expect_failures = [var.handler]
}


run "lambda_malformed_handler" {
  command = plan
  variables { handler = "not a valid handler" }
  expect_failures = [var.handler]
}


run "lambda_incompatible_python_handler" {
  command = plan
  variables { handler = "org.example.Handler::handleRequest" }
  expect_failures = [var.handler]
}


run "lambda_unsupported_architecture" {
  command = plan
  variables { architecture = "sparc" }
  expect_failures = [var.architecture]
}


run "lambda_memory_below_minimum" {
  command = plan
  variables { memory_size = 127 }
  expect_failures = [var.memory_size]
}


run "lambda_memory_above_maximum" {
  command = plan
  variables { memory_size = 10241 }
  expect_failures = [var.memory_size]
}


run "lambda_fractional_memory" {
  command = plan
  variables { memory_size = 128.5 }
  expect_failures = [var.memory_size]
}


run "lambda_timeout_below_minimum" {
  command = plan
  variables { timeout = 0 }
  expect_failures = [var.timeout]
}


run "lambda_timeout_above_maximum" {
  command = plan
  variables { timeout = 901 }
  expect_failures = [var.timeout]
}


run "lambda_fractional_timeout" {
  command = plan
  variables { timeout = 1.5 }
  expect_failures = [var.timeout]
}


run "lambda_ephemeral_storage_below_minimum" {
  command = plan
  variables { ephemeral_storage_size = 511 }
  expect_failures = [var.ephemeral_storage_size]
}


run "lambda_ephemeral_storage_above_maximum" {
  command = plan
  variables { ephemeral_storage_size = 10241 }
  expect_failures = [var.ephemeral_storage_size]
}


run "lambda_fractional_ephemeral_storage" {
  command = plan
  variables { ephemeral_storage_size = 512.5 }
  expect_failures = [var.ephemeral_storage_size]
}


run "lambda_invalid_environment_key" {
  command = plan
  variables { environment_variables = { "1INVALID" = "test" } }
  expect_failures = [var.environment_variables]
}


run "lambda_reserved_environment_key" {
  command = plan
  variables { environment_variables = { AWS_REGION = "ca-central-1" } }
  expect_failures = [var.environment_variables]
}


run "lambda_null_environment_value" {
  command = plan
  variables { environment_variables = { APP_MODE = null } }
  expect_failures = [var.environment_variables]
}


run "lambda_oversized_environment" {
  command = plan
  variables { environment_variables = { APP_MODE = format("%4096s", "x") } }
  expect_failures = [var.environment_variables]
}


run "lambda_utf8_environment_byte_limit" {
  command = plan
  variables { environment_variables = { APP_MODE = join("", [for i in range(1024) : "ééé"]) } }
  expect_failures = [var.environment_variables]
}


run "lambda_unversioned_layer_arn" {
  command = plan
  variables { layers = ["arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common"] }
  expect_failures = [var.layers]
}


run "lambda_duplicate_layers" {
  command = plan
  variables { layers = ["arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common:1", "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common:1"] }
  expect_failures = [var.layers]
}


run "lambda_too_many_layers" {
  command = plan
  variables { layers = [for i in range(6) : "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-layer-${i}:1"] }
  expect_failures = [var.layers]
}


run "lambda_cross_partition_layer_rejected" {
  command = plan
  variables { layers = ["arn:aws-cn:lambda:cn-north-1:000000000000:layer:portfolio-test-common:1"] }
  expect_failures = [var.layers]
}


run "lambda_negative_reserved_concurrency" {
  command = plan
  variables { reserved_concurrent_executions = -1 }
  expect_failures = [var.reserved_concurrent_executions]
}


run "lambda_fractional_reserved_concurrency" {
  command = plan
  variables { reserved_concurrent_executions = 1.5 }
  expect_failures = [var.reserved_concurrent_executions]
}


run "lambda_reserved_concurrency_integer_limit" {
  command = plan
  variables { reserved_concurrent_executions = 2147483648 }
  expect_failures = [var.reserved_concurrent_executions]
}


run "lambda_empty_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:"
    }
  }
  variables { log_group_name = "" }
  expect_failures = [var.log_group_name]
}


run "lambda_invalid_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:not a log group"
    }
  }
  variables { log_group_name = "not a log group" }
  expect_failures = [var.log_group_name]
}


run "lambda_reserved_log_group_prefix" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:aws/lambda/portfolio-test-lambda"
    }
  }
  variables { log_group_name = "aws/lambda/portfolio-test-lambda" }
  expect_failures = [var.log_group_name]
}


run "lambda_overlong_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:${join("", [for i in range(513) : "x"])}"
    }
  }
  variables { log_group_name = join("", [for i in range(513) : "x"]) }
  expect_failures = [var.log_group_name]
}


run "lambda_reserved_tag_prefix" {
  command = plan
  variables { tags = { "aws:reserved" = "test" } }
  expect_failures = [var.tags]
}


run "lambda_null_tag_value" {
  command = plan
  variables { tags = { Environment = null } }
  expect_failures = [var.tags]
}


run "lambda_too_many_tags" {
  command = plan
  variables { tags = { for i in range(51) : "key-${i}" => "test" } }
  expect_failures = [var.tags]
}


run "lambda_subnets_without_security_groups" {
  command = plan
  variables {
    subnet_ids = ["subnet-00000000000000001"]
  }
  expect_failures = [var.security_group_ids]
}


run "lambda_security_groups_without_subnets" {
  command = plan
  variables {
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.security_group_ids]
}


run "lambda_invalid_subnet_id" {
  command = plan
  variables {
    subnet_ids         = ["invalid-subnet"]
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.subnet_ids]
}


run "lambda_invalid_security_group_id" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001"]
    security_group_ids = ["invalid-security-group"]
  }
  expect_failures = [var.security_group_ids]
}


run "lambda_duplicate_subnets" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001", "subnet-00000000000000001"]
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.subnet_ids]
}


run "lambda_duplicate_security_groups" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001"]
    security_group_ids = ["sg-00000000000000001", "sg-00000000000000001"]
  }
  expect_failures = [var.security_group_ids]
}


run "lambda_too_many_subnets" {
  command = plan
  variables {
    subnet_ids         = [for i in range(17) : format("subnet-%017x", i)]
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.subnet_ids]
}


run "lambda_too_many_security_groups" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001"]
    security_group_ids = [for i in range(6) : format("sg-%017x", i)]
  }
  expect_failures = [var.security_group_ids]
}
