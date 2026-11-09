mock_provider "aws" {}

# Actual four-resource module, deterministic provider-computed identities only.
# Source case mapping lives in coverage.json; no AWS identity or artifact is real.
variables {
  function_name     = "portfolio-test-lambda"
  role_name         = "portfolio-test-lambda-execution"
  partition         = "aws"
  account_id        = "000000000000"
  region            = "ca-central-1"
  log_group_name    = "/portfolio/test/application"
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
    arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application"
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

run "role_default_logging_only_role" {
  command = plan

  assert {
    condition = (
      aws_iam_role.this.name == var.role_name &&
      aws_iam_role.this.path == "/" &&
      aws_iam_role.this.max_session_duration == 3600 &&
      length(aws_iam_role.this.tags) == 0 &&
      aws_iam_role_policy.this.name == "LambdaWorkloadAccess" &&
      aws_iam_role_policy.this.role == aws_iam_role.this.name
    )
    error_message = "The default module must own the named role and its one fixed, correctly bound inline policy without inventing tags."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.this.policy).Version == "2012-10-17" &&
      length(jsondecode(aws_iam_role_policy.this.policy).Statement) == 1 &&
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Effect == "Allow" &&
      toset(jsondecode(aws_iam_role_policy.this.policy).Statement[0].Action) == toset(["logs:CreateLogStream", "logs:PutLogEvents"]) &&
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${aws_cloudwatch_log_group.this.arn}:log-stream:*"] &&
      !can(jsondecode(aws_iam_role_policy.this.policy).Statement[0].Condition) &&
      !output.secret_read_enabled
    )
    error_message = "Default permissions must be exactly stream writes under the supplied group, with no Secrets Manager, KMS or administrative grant."
  }
}


run "role_exact_lambda_service_trust" {
  command = plan
  assert {
    condition = (
      jsondecode(aws_iam_role.this.assume_role_policy).Version == "2012-10-17" &&
      length(jsondecode(aws_iam_role.this.assume_role_policy).Statement) == 1 &&
      jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Effect == "Allow" &&
      toset(jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Action) == toset(["sts:AssumeRole"]) &&
      jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com" &&
      toset(keys(jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Principal)) == toset(["Service"]) &&
      !can(jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Condition) &&
      !can(jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].NotPrincipal) &&
      !can(jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].NotAction)
    )
    error_message = "Trust must allow only the Lambda service to AssumeRole, without guessed conditions or external principals."
  }
}


run "role_scoped_log_stream_writes" {
  command = plan
  assert {
    condition = alltrue([for statement in jsondecode(aws_iam_role_policy.this.policy).Statement :
      statement.Effect == "Allow" &&
      toset(statement.Action) == toset(["logs:CreateLogStream", "logs:PutLogEvents"]) &&
      statement.Resource == ["arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application:log-stream:*"] &&
      !can(statement.NotAction) && !can(statement.NotResource) && !can(statement.Principal)
    ]) && length(aws_iam_role_policy.this.policy) <= 10240
    error_message = "The actual compact policy must grant neither CreateLogGroup nor unrelated actions/resources, and must fit the role inline-policy quota."
  }
}


run "role_resource_attribute_outputs" {
  command = plan
  assert {
    condition = (
      output.execution_role_arn == aws_iam_role.this.arn &&
      output.execution_role_arn == "arn:aws:iam::000000000000:role/portfolio-test-lambda-execution" &&
      output.execution_role_name == aws_iam_role.this.name &&
      output.inline_policy_name == aws_iam_role_policy.this.name &&
      output.log_group_arn == aws_cloudwatch_log_group.this.arn &&
      output.secret_read_enabled == var.enable_secret_read &&
      output.permission_scope == {
        partition          = var.partition
        account_id         = var.account_id
        region             = var.region
        role_name          = var.role_name
        log_group_arn      = aws_cloudwatch_log_group.this.arn
        enable_secret_read = var.enable_secret_read
        secret_arn         = var.secret_arn
        secret_kms_key_arn = var.secret_kms_key_arn
      }
    )
    error_message = "Outputs must bind the actual role/policy references and preserve the exact non-secret input scope for independent verification."
  }
}


run "role_enabled_secret_without_customer_key" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
  }
  assert {
    condition = (
      output.secret_read_enabled &&
      length(jsondecode(aws_iam_role_policy.this.policy).Statement) == 2 &&
      toset(one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "ReadAuthorizedSecret"]).Action) == toset(["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]) &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "ReadAuthorizedSecret"]).Resource == [var.secret_arn] &&
      alltrue([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : !contains(s.Action, "kms:Decrypt")]) &&
      output.permission_scope.secret_arn == var.secret_arn &&
      output.permission_scope.secret_kms_key_arn == null
    )
    error_message = "Explicit secret reading must add only its two exact-ARN reads and no customer-managed KMS grant when no key was supplied."
  }
}


run "role_enabled_secret_with_customer_key" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  assert {
    condition = (
      length(jsondecode(aws_iam_role_policy.this.policy).Statement) == 3 &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Effect == "Allow" &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Action == ["kms:Decrypt"] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Resource == [var.secret_kms_key_arn] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Condition == {
        StringEquals = {
          "kms:ViaService"                  = "secretsmanager.ca-central-1.amazonaws.com"
          "kms:EncryptionContext:SecretARN" = var.secret_arn
          "kms:CallerAccount"               = var.account_id
        }
      } &&
      output.permission_scope.secret_kms_key_arn == var.secret_kms_key_arn
    )
    error_message = "Only the exact key may decrypt through regional Secrets Manager with the exact SecretARN context and caller account."
  }
}


run "role_existing_multi_region_customer_key" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/mrk-00000000000000000000000000000000"
  }
  assert {
    condition = (
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Resource == [var.secret_kms_key_arn] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Condition.StringEquals["kms:EncryptionContext:SecretARN"] == var.secret_arn
    )
    error_message = "An existing MRK reference must remain exact and secret-context scoped, without creating replicas or broad permissions."
  }
}


run "role_alternate_account_and_region" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000001:role/portfolio-test-lambda-execution"
    }
  }
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:us-east-2:000000000001:log-group:/portfolio/alternate/application"
    }
  }
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:us-east-2:000000000001:function:portfolio-test-lambda"
      invoke_arn = "arn:aws:apigateway:us-east-2:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-2:000000000001:function:portfolio-test-lambda/invocations"
      version    = "$LATEST"
    }
  }
  variables {
    account_id     = "000000000001"
    region         = "us-east-2"
    log_group_name = "/portfolio/alternate/application"
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${aws_cloudwatch_log_group.this.arn}:log-stream:*"] &&
      output.execution_role_arn == aws_iam_role.this.arn &&
      output.permission_scope.account_id == var.account_id &&
      output.permission_scope.region == var.region
    )
    error_message = "A coherent alternate scope must remain exact rather than retain the default account or region."
  }
}


run "role_govcloud_scope_with_customer_key" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws-us-gov:iam::000000000000:role/portfolio-test-lambda-execution"
    }
  }
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws-us-gov:logs:us-gov-west-1:000000000000:log-group:/portfolio/test/application"
    }
  }
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws-us-gov:lambda:us-gov-west-1:000000000000:function:portfolio-test-lambda"
      invoke_arn = "arn:aws-us-gov:apigateway:us-gov-west-1:lambda:path/2015-03-31/functions/arn:aws-us-gov:lambda:us-gov-west-1:000000000000:function:portfolio-test-lambda/invocations"
      version    = "$LATEST"
    }
  }
  variables {
    partition          = "aws-us-gov"
    region             = "us-gov-west-1"
    log_group_name     = "/portfolio/test/application"
    enable_secret_read = true
    secret_arn         = "arn:aws-us-gov:secretsmanager:us-gov-west-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com" &&
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${aws_cloudwatch_log_group.this.arn}:log-stream:*"] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "ReadAuthorizedSecret"]).Resource == [var.secret_arn] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Condition.StringEquals["kms:ViaService"] == "secretsmanager.us-gov-west-1.amazonaws.com" &&
      output.permission_scope.partition == "aws-us-gov"
    )
    error_message = "The supported GovCloud contract must use coherent ARN partitions and the documented regional ViaService name without inventing trust principals."
  }
}


run "role_valid_role_name_characters" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/portfolio_Example+=,.@-role"
    }
  }
  variables { role_name = "portfolio_Example+=,.@-role" }

  assert {
    condition     = aws_iam_role.this.name == var.role_name && output.permission_scope.role_name == var.role_name
    error_message = "Supported IAM role-name characters must pass through exactly."
  }
}


run "role_maximum_role_name_length" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/${join("", [for i in range(64) : "r"])}"
    }
  }
  variables { role_name = join("", [for i in range(64) : "r"]) }

  assert {
    condition     = length(aws_iam_role.this.name) == 64 && output.execution_role_name == aws_iam_role.this.name
    error_message = "The supported 64-character role-name boundary must remain usable."
  }
}


run "role_lambda_log_group_reference" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/aws/lambda/portfolio-api-handler"
    }
  }
  variables { log_group_name = "/aws/lambda/portfolio-api-handler" }
  assert {
    condition     = jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${aws_cloudwatch_log_group.this.arn}:log-stream:*"]
    error_message = "A bare ARN from the existing logging module must be scoped to its streams rather than used as a group-wide wildcard."
  }
}


run "role_maximum_log_group_name_length" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:${join("", [for i in range(512) : "l"])}"
    }
  }
  variables { log_group_name = join("", [for i in range(512) : "l"]) }
  assert {
    condition     = jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${aws_cloudwatch_log_group.this.arn}:log-stream:*"] && length(aws_iam_role_policy.this.policy) <= 10240
    error_message = "An exact 512-character group name must remain scoped and within the inline-policy size budget."
  }
}


run "role_caller_owned_unicode_tags" {
  command = plan
  variables { role_tags = { Project = "explicit-project", Name = "caller-owned", "環境:分類" = "検証 @ team" } }
  assert {
    condition     = length(aws_iam_role.this.tags) == length(var.role_tags) && alltrue([for key, value in var.role_tags : aws_iam_role.this.tags[key] == value])
    error_message = "The role must preserve caller-owned non-secret tags without inventing or replacing Project metadata."
  }
}


run "role_maximum_tag_count_and_lengths" {
  command = plan
  variables {
    role_tags = merge(
      { for i in range(49) : "Tag${i}" => "test" },
      { (join("", [for i in range(128) : "k"])) = join("", [for i in range(256) : "v"]) }
    )
  }
  assert {
    condition     = length(aws_iam_role.this.tags) == 50 && length(aws_iam_role.this.tags[join("", [for i in range(128) : "k"])]) == 256
    error_message = "The supported 50-tag, 128-character key and 256-character value boundaries must remain usable."
  }
}


run "role_empty_role_name" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/"
    }
  }
  variables { role_name = "" }
  expect_failures = [var.role_name]
}


run "role_role_name_with_path" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/portfolio/role"
    }
  }
  variables { role_name = "portfolio/role" }
  expect_failures = [var.role_name]
}


run "role_role_name_with_wildcard" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/portfolio-*"
    }
  }
  variables { role_name = "portfolio-*" }
  expect_failures = [var.role_name]
}


run "role_overlong_role_name" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/${join("", [for i in range(65) : "r"])}"
    }
  }
  variables { role_name = join("", [for i in range(65) : "r"]) }
  expect_failures = [var.role_name]
}


run "role_null_role_name" {
  command = plan
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/invalid"
    }
  }
  variables { role_name = null }
  expect_failures = [var.role_name]
}


run "role_unsupported_partition" {
  command = plan
  variables { partition = "aws-iso" }
  expect_failures = [var.partition]
}


run "role_china_partition_not_supported" {
  command = plan
  variables { partition = "aws-cn" }
  expect_failures = [var.partition]
}


run "role_null_partition" {
  command = plan
  variables { partition = null }
  expect_failures = [var.partition]
}


run "role_malformed_account_id" {
  command = plan
  variables { account_id = "12345678901" }
  expect_failures = [var.account_id]
}


run "role_wildcard_account_id" {
  command = plan
  variables { account_id = "00000000000*" }
  expect_failures = [var.account_id]
}


run "role_null_account_id" {
  command = plan
  variables { account_id = null }
  expect_failures = [var.account_id]
}


run "role_malformed_region" {
  command = plan
  variables { region = "not-a-region" }
  expect_failures = [var.region]
}


run "role_china_region_in_aws_partition" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:cn-north-1:000000000000:log-group:/portfolio/test/application"
    }
  }
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:cn-north-1:000000000000:function:portfolio-test-lambda"
      invoke_arn = "arn:aws:apigateway:cn-north-1:lambda:path/2015-03-31/functions/arn:aws:lambda:cn-north-1:000000000000:function:portfolio-test-lambda/invocations"
      version    = "$LATEST"
    }
  }
  variables { region = "cn-north-1" }
  expect_failures = [var.region]
}


run "role_govcloud_region_in_aws_partition" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:us-gov-west-1:000000000000:log-group:/portfolio/test/application"
    }
  }
  override_resource {
    target          = aws_lambda_function.this
    override_during = plan
    values = {
      arn        = "arn:aws:lambda:us-gov-west-1:000000000000:function:portfolio-test-lambda"
      invoke_arn = "arn:aws:apigateway:us-gov-west-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-gov-west-1:000000000000:function:portfolio-test-lambda/invocations"
      version    = "$LATEST"
    }
  }
  variables { region = "us-gov-west-1" }
  expect_failures = [var.region]
}


run "role_null_region" {
  command = plan
  variables { region = null }
  expect_failures = [var.region]
}


run "role_wildcard_log_group_resource" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "*"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_wildcard_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/*"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_log_group_api_star_suffix" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application:*"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_log_stream_arn_is_not_group_arn" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application:log-stream:stream"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_missing_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_overlong_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:${join("", [for i in range(513) : "l"])}"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_log_group_wrong_account" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000001:log-group:/portfolio/test/application"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_log_group_wrong_region" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:us-east-2:000000000000:log-group:/portfolio/test/application"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_log_group_wrong_partition" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws-us-gov:logs:us-gov-west-1:000000000000:log-group:/portfolio/test/application"
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_null_log_group_arn" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = null
    }
  }
  expect_failures = [aws_cloudwatch_log_group.this]
}


run "role_secret_input_while_disabled" {
  command = plan
  variables { secret_arn = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123" }
  expect_failures = [var.secret_arn]
}


run "role_kms_input_while_disabled" {
  command = plan
  variables { secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_enabled_secret_missing_arn" {
  command = plan
  variables { enable_secret_read = true }
  expect_failures = [var.secret_arn]
}


run "role_partial_secret_arn" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime"
  }
  expect_failures = [var.secret_arn]
}


run "role_short_generated_secret_suffix" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC12"
  }
  expect_failures = [var.secret_arn]
}


run "role_wildcard_secret_arn" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/*-ABC123"
  }
  expect_failures = [var.secret_arn]
}


run "role_secret_wrong_account" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000001:secret:portfolio/test/runtime-ABC123"
  }
  expect_failures = [var.secret_arn]
}


run "role_secret_wrong_region" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:us-east-2:000000000000:secret:portfolio/test/runtime-ABC123"
  }
  expect_failures = [var.secret_arn]
}


run "role_secret_wrong_partition" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws-us-gov:secretsmanager:us-gov-west-1:000000000000:secret:portfolio/test/runtime-ABC123"
  }
  expect_failures = [var.secret_arn]
}


run "role_kms_alias_is_not_key_arn" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:alias/portfolio-test"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_bare_kms_identifier" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_wildcard_kms_key" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/*"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_incomplete_kms_key_id" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_kms_wrong_account" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000001:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_kms_wrong_region" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_kms_wrong_partition" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}


run "role_empty_tag_key" {
  command = plan
  variables { role_tags = { "" = "test" } }
  expect_failures = [var.role_tags]
}


run "role_reserved_tag_prefix" {
  command = plan
  variables { role_tags = { "AWS:Reserved" = "test" } }
  expect_failures = [var.role_tags]
}


run "role_null_tag_value" {
  command = plan
  variables { role_tags = { Owner = null } }
  expect_failures = [var.role_tags]
}


run "role_unsupported_tag_key_character" {
  command = plan
  variables { role_tags = { "Owner?" = "test" } }
  expect_failures = [var.role_tags]
}


run "role_unsupported_tag_value_character" {
  command = plan
  variables { role_tags = { Owner = "test!" } }
  expect_failures = [var.role_tags]
}


run "role_overlong_tag_key" {
  command = plan
  variables { role_tags = { (join("", [for i in range(129) : "k"])) = "test" } }
  expect_failures = [var.role_tags]
}


run "role_overlong_tag_value" {
  command = plan
  variables { role_tags = { Owner = join("", [for i in range(257) : "v"]) } }
  expect_failures = [var.role_tags]
}


run "role_too_many_tags" {
  command = plan
  variables { role_tags = { for i in range(51) : "Tag${i}" => "test" } }
  expect_failures = [var.role_tags]
}
