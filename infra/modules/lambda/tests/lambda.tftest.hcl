mock_provider "aws" {}

# Computed references are deterministic synthetic fixtures; no AWS account,
# deployment archive or API call is used. Publishing stays disabled.
override_resource {
  target          = aws_lambda_function.this
  override_during = plan
  values = {
    arn        = "arn:aws:lambda:ca-central-1:000000000000:function:portfolio-test-lambda"
    invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:portfolio-test-lambda/invocations"
    version    = "$LATEST"
  }
}

variables {
  function_name      = "portfolio-test-lambda"
  execution_role_arn = "arn:aws:iam::000000000000:role/portfolio/test-lambda-execution"
  s3_bucket          = "portfolio-test-artifacts"
  s3_key             = "lambda/test/function.zip"
  s3_object_version  = "synthetic-version-001"
  runtime            = "python3.13"
  handler            = "app.handler"
  log_group_name     = "/portfolio/test/lambda"
}

run "default_function_configuration" {
  command = plan

  assert {
    condition = (
      aws_lambda_function.this.function_name == var.function_name &&
      aws_lambda_function.this.description == null &&
      aws_lambda_function.this.role == var.execution_role_arn &&
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
      length(aws_lambda_function.this.tags) == 0
    )
    error_message = "Defaults must add no VPC/environment/layers/tags and no reserved concurrency override."
  }
}

run "resource_attribute_outputs" {
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

run "node_runtime_and_compute_overrides" {
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

run "java_runtime_on_arm64" {
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

run "maximum_compute_boundaries" {
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

run "minimum_timeout_and_name_description_boundaries" {
  command = plan
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

run "existing_versioned_layers_and_concurrency" {
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

run "maximum_layer_count_and_zero_concurrency" {
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

run "existing_vpc_references" {
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

run "maximum_vpc_reference_counts" {
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

run "nonsecret_configuration_and_secret_reference" {
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

run "environment_byte_boundary" {
  command = plan
  variables { environment_variables = { APP_MODE = format("%4088s", "x") } }
  assert {
    condition     = aws_lambda_function.this.environment[0].variables == var.environment_variables
    error_message = "A 4096-byte total key/value configuration must remain usable without introducing secret values."
  }
}

run "caller_owned_tags" {
  command = plan
  variables {
    tags = { Name = "test-function", Project = "test-portfolio", Environment = "test" }
  }
  assert {
    condition     = aws_lambda_function.this.tags == var.tags
    error_message = "Caller-owned non-sensitive tags must pass through without hidden additional tags."
  }
}

# Every invalid case names the variable whose own validation must reject it.

run "empty_function_name" {
  command = plan
  variables { function_name = "" }
  expect_failures = [var.function_name]
}

run "invalid_function_name" {
  command = plan
  variables { function_name = "not a function" }
  expect_failures = [var.function_name]
}

run "overlong_function_name" {
  command = plan
  variables { function_name = join("", [for i in range(65) : "x"]) }
  expect_failures = [var.function_name]
}

run "null_function_name" {
  command = plan
  variables { function_name = null }
  expect_failures = [var.function_name]
}

run "overlong_description" {
  command = plan
  variables { description = join("", [for i in range(257) : "x"]) }
  expect_failures = [var.description]
}

run "sts_session_is_not_execution_role" {
  command = plan
  variables { execution_role_arn = "arn:aws:sts::000000000000:assumed-role/example/session" }
  expect_failures = [var.execution_role_arn]
}

run "wildcard_execution_role_rejected" {
  command = plan
  variables { execution_role_arn = "arn:aws:iam::000000000000:role/*" }
  expect_failures = [var.execution_role_arn]
}

run "malformed_execution_role_account" {
  command = plan
  variables { execution_role_arn = "arn:aws:iam::not-an-account:role/example" }
  expect_failures = [var.execution_role_arn]
}

run "bucket_arn_is_not_bucket_name" {
  command = plan
  variables { s3_bucket = "arn:aws:s3:::portfolio-test-artifacts" }
  expect_failures = [var.s3_bucket]
}

run "uppercase_bucket_rejected" {
  command = plan
  variables { s3_bucket = "Portfolio-Test-Artifacts" }
  expect_failures = [var.s3_bucket]
}

run "empty_artifact_key" {
  command = plan
  variables { s3_key = "" }
  expect_failures = [var.s3_key]
}

run "empty_artifact_version" {
  command = plan
  variables { s3_object_version = "" }
  expect_failures = [var.s3_object_version]
}

run "blank_artifact_version" {
  command = plan
  variables { s3_object_version = "   " }
  expect_failures = [var.s3_object_version]
}

run "unversioned_null_artifact_rejected" {
  command = plan
  variables { s3_object_version = "null" }
  expect_failures = [var.s3_object_version]
}

run "missing_artifact_version" {
  command = plan
  variables { s3_object_version = null }
  expect_failures = [var.s3_object_version]
}

run "unsupported_runtime" {
  command = plan
  variables { runtime = "nodejs99.x" }
  expect_failures = [var.runtime]
}

run "missing_runtime" {
  command = plan
  variables { runtime = null }
  expect_failures = [var.runtime]
}

run "empty_handler" {
  command = plan
  variables { handler = "" }
  expect_failures = [var.handler]
}

run "malformed_handler" {
  command = plan
  variables { handler = "not a valid handler" }
  expect_failures = [var.handler]
}

run "incompatible_python_handler" {
  command = plan
  variables { handler = "org.example.Handler::handleRequest" }
  expect_failures = [var.handler]
}

run "unsupported_architecture" {
  command = plan
  variables { architecture = "sparc" }
  expect_failures = [var.architecture]
}

run "memory_below_minimum" {
  command = plan
  variables { memory_size = 127 }
  expect_failures = [var.memory_size]
}

run "memory_above_maximum" {
  command = plan
  variables { memory_size = 10241 }
  expect_failures = [var.memory_size]
}

run "fractional_memory" {
  command = plan
  variables { memory_size = 128.5 }
  expect_failures = [var.memory_size]
}

run "timeout_below_minimum" {
  command = plan
  variables { timeout = 0 }
  expect_failures = [var.timeout]
}

run "timeout_above_maximum" {
  command = plan
  variables { timeout = 901 }
  expect_failures = [var.timeout]
}

run "fractional_timeout" {
  command = plan
  variables { timeout = 1.5 }
  expect_failures = [var.timeout]
}

run "ephemeral_storage_below_minimum" {
  command = plan
  variables { ephemeral_storage_size = 511 }
  expect_failures = [var.ephemeral_storage_size]
}

run "ephemeral_storage_above_maximum" {
  command = plan
  variables { ephemeral_storage_size = 10241 }
  expect_failures = [var.ephemeral_storage_size]
}

run "fractional_ephemeral_storage" {
  command = plan
  variables { ephemeral_storage_size = 512.5 }
  expect_failures = [var.ephemeral_storage_size]
}

run "invalid_environment_key" {
  command = plan
  variables { environment_variables = { "1INVALID" = "test" } }
  expect_failures = [var.environment_variables]
}

run "reserved_environment_key" {
  command = plan
  variables { environment_variables = { AWS_REGION = "ca-central-1" } }
  expect_failures = [var.environment_variables]
}

run "null_environment_value" {
  command = plan
  variables { environment_variables = { APP_MODE = null } }
  expect_failures = [var.environment_variables]
}

run "oversized_environment" {
  command = plan
  variables { environment_variables = { APP_MODE = format("%4096s", "x") } }
  expect_failures = [var.environment_variables]
}

run "utf8_environment_byte_limit" {
  command = plan
  variables { environment_variables = { APP_MODE = join("", [for i in range(1024) : "ééé"]) } }
  expect_failures = [var.environment_variables]
}

run "unversioned_layer_arn" {
  command = plan
  variables { layers = ["arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common"] }
  expect_failures = [var.layers]
}

run "duplicate_layers" {
  command = plan
  variables { layers = ["arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common:1", "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-common:1"] }
  expect_failures = [var.layers]
}

run "too_many_layers" {
  command = plan
  variables { layers = [for i in range(6) : "arn:aws:lambda:ca-central-1:000000000000:layer:portfolio-test-layer-${i}:1"] }
  expect_failures = [var.layers]
}

run "cross_partition_layer_rejected" {
  command = plan
  variables { layers = ["arn:aws-cn:lambda:cn-north-1:000000000000:layer:portfolio-test-common:1"] }
  expect_failures = [var.layers]
}

run "negative_reserved_concurrency" {
  command = plan
  variables { reserved_concurrent_executions = -1 }
  expect_failures = [var.reserved_concurrent_executions]
}

run "fractional_reserved_concurrency" {
  command = plan
  variables { reserved_concurrent_executions = 1.5 }
  expect_failures = [var.reserved_concurrent_executions]
}

run "reserved_concurrency_integer_limit" {
  command = plan
  variables { reserved_concurrent_executions = 2147483648 }
  expect_failures = [var.reserved_concurrent_executions]
}

run "empty_log_group_name" {
  command = plan
  variables { log_group_name = "" }
  expect_failures = [var.log_group_name]
}

run "invalid_log_group_name" {
  command = plan
  variables { log_group_name = "not a log group" }
  expect_failures = [var.log_group_name]
}

run "reserved_log_group_prefix" {
  command = plan
  variables { log_group_name = "aws/lambda/portfolio-test-lambda" }
  expect_failures = [var.log_group_name]
}

run "overlong_log_group_name" {
  command = plan
  variables { log_group_name = join("", [for i in range(513) : "x"]) }
  expect_failures = [var.log_group_name]
}

run "reserved_tag_prefix" {
  command = plan
  variables { tags = { "aws:reserved" = "test" } }
  expect_failures = [var.tags]
}

run "null_tag_value" {
  command = plan
  variables { tags = { Environment = null } }
  expect_failures = [var.tags]
}

run "too_many_tags" {
  command = plan
  variables { tags = { for i in range(51) : "key-${i}" => "test" } }
  expect_failures = [var.tags]
}

run "subnets_without_security_groups" {
  command = plan
  variables {
    subnet_ids = ["subnet-00000000000000001"]
  }
  expect_failures = [var.security_group_ids]
}

run "security_groups_without_subnets" {
  command = plan
  variables {
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.security_group_ids]
}

run "invalid_subnet_id" {
  command = plan
  variables {
    subnet_ids         = ["invalid-subnet"]
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.subnet_ids]
}

run "invalid_security_group_id" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001"]
    security_group_ids = ["invalid-security-group"]
  }
  expect_failures = [var.security_group_ids]
}

run "duplicate_subnets" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001", "subnet-00000000000000001"]
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.subnet_ids]
}

run "duplicate_security_groups" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001"]
    security_group_ids = ["sg-00000000000000001", "sg-00000000000000001"]
  }
  expect_failures = [var.security_group_ids]
}

run "too_many_subnets" {
  command = plan
  variables {
    subnet_ids         = [for i in range(17) : format("subnet-%017x", i)]
    security_group_ids = ["sg-00000000000000001"]
  }
  expect_failures = [var.subnet_ids]
}

run "too_many_security_groups" {
  command = plan
  variables {
    subnet_ids         = ["subnet-00000000000000001"]
    security_group_ids = [for i in range(6) : format("sg-%017x", i)]
  }
  expect_failures = [var.security_group_ids]
}
