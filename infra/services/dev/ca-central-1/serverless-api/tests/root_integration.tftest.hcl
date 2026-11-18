mock_provider "aws" {}

# Only provider-computed attributes are supplied. All configured resource
# arguments and all four child module instances still come from the actual root.
# These identities are synthetic; mocks neither authenticate nor deploy.
override_resource {
  target          = module.artifact_bucket.aws_s3_bucket.this
  override_during = plan
  values = {
    id            = "test-dev-s3-artifact"
    arn           = "arn:aws:s3:::test-dev-s3-artifact"
    acl           = ""
    policy        = ""
    bucket_prefix = ""
    tags_all = {
      project = "test"
      env     = "dev"
      managed = "terraform"
      Name    = "test-dev-s3-artifact"
      service = "s3"
    }
  }
}

override_resource {
  target          = module.secret_metadata.aws_secretsmanager_secret.this
  override_during = plan
  values = {
    arn = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:/test/dev/secret/app-ABC123"
    id  = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:/test/dev/secret/app-ABC123"
  }
}

override_resource {
  target          = module.lambda_workload.aws_cloudwatch_log_group.this
  override_during = plan
  values = {
    arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/aws/lambda/test-dev-lambda"
    id  = "/aws/lambda/test-dev-lambda"
  }
}

override_resource {
  target          = module.http_api.aws_cloudwatch_log_group.this
  override_during = plan
  values = {
    arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/test/dev/apigw/http"
    id  = "/test/dev/apigw/http"
  }
}

override_resource {
  target          = module.lambda_workload.aws_iam_role.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::000000000000:role/test-dev-role-lambda"
  }
}

override_resource {
  target          = module.lambda_workload.aws_lambda_function.this
  override_during = plan
  values = {
    arn        = "arn:aws:lambda:ca-central-1:000000000000:function:test-dev-lambda"
    invoke_arn = "arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:000000000000:function:test-dev-lambda/invocations"
    version    = "$LATEST"
  }
}

override_resource {
  target          = module.http_api.aws_apigatewayv2_api.this
  override_during = plan
  values = {
    id              = "a1b2c3d4e5"
    arn             = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5"
    execution_arn   = "arn:aws:execute-api:ca-central-1:000000000000:a1b2c3d4e5"
    api_endpoint    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com"
    region          = "ca-central-1"
    ip_address_type = "ipv4"
    tags_all = {
      project = "test"
      env     = "dev"
      managed = "terraform"
      Name    = "test-dev-apigw-http"
      service = "apigw"
    }
  }
}

override_resource {
  target          = module.http_api.aws_apigatewayv2_integration.this
  override_during = plan
  values = {
    id                                        = "intg123"
    region                                    = "ca-central-1"
    timeout_milliseconds                      = 30000
    integration_response_selection_expression = null
  }
}

override_resource {
  target          = module.http_api.aws_apigatewayv2_route.this
  override_during = plan
  values = {
    id     = "route123"
    region = "ca-central-1"
  }
}

override_resource {
  target          = module.http_api.aws_apigatewayv2_stage.this
  override_during = plan
  values = {
    id            = "$default"
    arn           = "arn:aws:apigateway:ca-central-1::/apis/a1b2c3d4e5/stages/$default"
    execution_arn = "arn:aws:execute-api:ca-central-1:000000000000:a1b2c3d4e5/$default"
    invoke_url    = "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/"
    region        = "ca-central-1"
    deployment_id = "mock-deployment"
    # This provider-computed WebSocket-only value does not override the
    # configured HTTP throttling values, which the actual-plan checker checks.
    default_route_settings = { logging_level = "OFF" }
    tags_all = {
      project = "test"
      env     = "dev"
      managed = "terraform"
      Name    = "test-dev-apigw-http-default"
      service = "apigw"
    }
  }
}

override_resource {
  target          = module.http_api.aws_lambda_permission.this
  override_during = plan
  values = {
    id                  = "mock-permission"
    region              = "ca-central-1"
    statement_id_prefix = null
  }
}

variables {
  aws_account_id          = "000000000000"
  project                 = "test"
  artifact_key            = "lambda/test/function.zip"
  artifact_object_version = "synthetic-version-001"
  lambda_runtime          = "python3.13"
  lambda_handler          = "app.handler"
}

run "default_secret_read_disabled" {
  command = plan

  assert {
    condition = (
      local.environment == "dev" &&
      local.region == "ca-central-1" &&
      local.name_prefix == "test-dev" &&
      local.path_prefix == "/test/dev"
    )
    error_message = "Root workload identity must remain dev/ca-central-1 and derive names from <project>-dev; mocks do not verify a live provider identity."
  }

  assert {
    condition = (
      !var.enable_secret_read &&
      !module.lambda_workload.secret_read_enabled &&
      module.lambda_workload.permission_scope.secret_arn == null &&
      module.lambda_workload.permission_scope.secret_kms_key_arn == null &&
      module.lambda_workload.permission_scope.partition == "aws" &&
      module.lambda_workload.permission_scope.account_id == var.aws_account_id &&
      module.lambda_workload.permission_scope.region == "ca-central-1"
    )
    error_message = "The default root must select the fixed workload scope without a secret or customer-managed KMS grant."
  }

  assert {
    condition = (
      module.lambda_workload.execution_role_name == "${local.name_prefix}-role-lambda" &&
      module.lambda_workload.execution_role_arn == "arn:aws:iam::${var.aws_account_id}:role/${local.name_prefix}-role-lambda" &&
      module.lambda_workload.permission_scope.role_name == module.lambda_workload.execution_role_name &&
      module.lambda_workload.inline_policy_name == "${local.name_prefix}-policy-lambda" &&
      module.lambda_workload.log_group_name == "/aws/lambda/${local.name_prefix}-lambda" &&
      module.lambda_workload.log_group_arn == "arn:aws:logs:${local.region}:${var.aws_account_id}:log-group:/aws/lambda/${local.name_prefix}-lambda" &&
      module.lambda_workload.permission_scope.log_group_arn == module.lambda_workload.log_group_arn &&
      module.lambda_workload.runtime == var.lambda_runtime &&
      module.lambda_workload.architecture == "x86_64" &&
      length(module.lambda_workload.vpc_configuration.subnet_ids) == 0 &&
      length(module.lambda_workload.vpc_configuration.security_group_ids) == 0 &&
      module.artifact_bucket.bucket_name == "${local.name_prefix}-s3-artifact" &&
      module.artifact_bucket.versioning_status == "Enabled"
    )
    error_message = "Provider-backed role/log outputs must match the root workload identity and permission scope, with the explicit artifact bucket and no VPC integration."
  }

  assert {
    condition = (
      module.http_api.access_log_group_name == "${local.path_prefix}/apigw/http" &&
      module.http_api.access_log_group_arn == "arn:aws:logs:${local.region}:${var.aws_account_id}:log-group:${local.path_prefix}/apigw/http" &&
      module.lambda_workload.log_group_name != module.http_api.access_log_group_name &&
      module.lambda_workload.log_group_arn != module.http_api.access_log_group_arn &&
      module.lambda_workload.log_retention_in_days == 30 &&
      module.http_api.access_log_retention_in_days == 30 &&
      module.lambda_workload.log_deletion_protection_enabled &&
      module.http_api.access_log_deletion_protection_enabled &&
      module.lambda_workload.log_group_class == "STANDARD" &&
      module.http_api.access_log_group_class == "STANDARD" &&
      module.lambda_workload.log_kms_key_arn == null &&
      module.http_api.access_log_kms_key_arn == null &&
      module.secret_metadata.kms_configuration.requested_mode == "aws-managed" &&
      !module.secret_metadata.resource_policy_managed
    )
    error_message = "Dedicated application/access log groups must preserve secure defaults and metadata-only default secret encryption."
  }

  assert {
    condition = (
      output.api_invoke_url == module.http_api.invoke_url &&
      output.api_invoke_url == "https://a1b2c3d4e5.execute-api.ca-central-1.amazonaws.com/" &&
      output.api_id == module.http_api.api_id &&
      output.lambda_function_name == module.lambda_workload.function_name &&
      output.lambda_function_arn == module.lambda_workload.function_arn &&
      output.artifact_bucket_name == module.artifact_bucket.bucket_name &&
      output.secret_metadata_arn == module.secret_metadata.secret_arn &&
      output.lambda_log_group_name == module.lambda_workload.log_group_name &&
      output.api_access_log_group_name == module.http_api.access_log_group_name
    )
    error_message = "Every root operational output must preserve the corresponding actual child-module output, including the provider-returned stage URL."
  }
}

run "enabled_exact_secret_read" {
  command = plan
  variables {
    enable_secret_read = true
  }

  assert {
    condition = (
      module.lambda_workload.secret_read_enabled &&
      module.lambda_workload.permission_scope.secret_arn == module.secret_metadata.secret_arn &&
      module.lambda_workload.permission_scope.secret_kms_key_arn == null &&
      module.lambda_workload.execution_role_name == "${local.name_prefix}-role-lambda" &&
      module.lambda_workload.execution_role_arn == "arn:aws:iam::${var.aws_account_id}:role/${local.name_prefix}-role-lambda" &&
      output.secret_metadata_arn == module.secret_metadata.secret_arn
    )
    error_message = "Opt-in secret reading must pass the actual full secret ARN to the existing role contract without enabling customer-managed KMS access."
  }
}

run "node_runtime" {
  command = plan
  variables {
    lambda_runtime = "nodejs22.x"
    lambda_handler = "index.handler"
  }
  assert {
    condition     = module.lambda_workload.runtime == "nodejs22.x"
    error_message = "The reviewed Node.js runtime must remain available with a matching explicit handler."
  }
}

run "java_runtime" {
  command = plan
  variables {
    lambda_runtime = "java21"
    lambda_handler = "com.example.Handler::handleRequest"
  }
  assert {
    condition     = module.lambda_workload.runtime == "java21"
    error_message = "The reviewed Java runtime must remain available with a matching explicit handler."
  }
}

run "teardown_log_protection_off" {
  command = plan
  variables {
    log_deletion_protection = false
  }
  assert {
    condition     = !module.lambda_workload.log_deletion_protection_enabled && !module.http_api.access_log_deletion_protection_enabled
    error_message = "The teardown switch must turn off deletion protection on both log groups and nothing else."
  }
}

run "invalid_account_id" {
  command = plan
  variables {
    aws_account_id = "not-an-account"
  }
  expect_failures = [var.aws_account_id]
}
