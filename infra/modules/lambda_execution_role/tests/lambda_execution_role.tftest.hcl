mock_provider "aws" {}

# Synthetic computed identity only. No role, session, secret value or key is used.
override_resource {
  target          = aws_iam_role.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::000000000000:role/portfolio-test-lambda-execution"
  }
}

variables {
  role_name     = "portfolio-test-lambda-execution"
  partition     = "aws"
  account_id    = "000000000000"
  region        = "ca-central-1"
  log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application"
}

run "default_logging_only_role" {
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
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${var.log_group_arn}:log-stream:*"] &&
      !can(jsondecode(aws_iam_role_policy.this.policy).Statement[0].Condition) &&
      !output.secret_read_enabled
    )
    error_message = "Default permissions must be exactly stream writes under the supplied group, with no Secrets Manager, KMS or administrative grant."
  }
}

run "exact_lambda_service_trust" {
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

run "scoped_log_stream_writes" {
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

run "resource_attribute_outputs" {
  command = plan
  assert {
    condition = (
      output.execution_role_arn == aws_iam_role.this.arn &&
      output.execution_role_arn == "arn:aws:iam::000000000000:role/portfolio-test-lambda-execution" &&
      output.execution_role_name == aws_iam_role.this.name &&
      output.inline_policy_name == aws_iam_role_policy.this.name &&
      output.log_group_arn == var.log_group_arn &&
      output.secret_read_enabled == var.enable_secret_read &&
      output.permission_scope == {
        partition          = var.partition
        account_id         = var.account_id
        region             = var.region
        role_name          = var.role_name
        log_group_arn      = var.log_group_arn
        enable_secret_read = var.enable_secret_read
        secret_arn         = var.secret_arn
        secret_kms_key_arn = var.secret_kms_key_arn
      }
    )
    error_message = "Outputs must bind the actual role/policy references and preserve the exact non-secret input scope for independent verification."
  }
}

run "enabled_secret_without_customer_key" {
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

run "enabled_secret_with_customer_key" {
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

run "existing_multi_region_customer_key" {
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

run "alternate_account_and_region" {
  command = plan
  variables {
    account_id    = "000000000001"
    region        = "us-east-2"
    log_group_arn = "arn:aws:logs:us-east-2:000000000001:log-group:/portfolio/alternate/application"
  }
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000001:role/portfolio-test-lambda-execution"
    }
  }
  assert {
    condition = (
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${var.log_group_arn}:log-stream:*"] &&
      output.execution_role_arn == aws_iam_role.this.arn &&
      output.permission_scope.account_id == var.account_id &&
      output.permission_scope.region == var.region
    )
    error_message = "A coherent alternate scope must remain exact rather than retain the default account or region."
  }
}

run "govcloud_scope_with_customer_key" {
  command = plan
  variables {
    partition          = "aws-us-gov"
    region             = "us-gov-west-1"
    log_group_arn      = "arn:aws-us-gov:logs:us-gov-west-1:000000000000:log-group:/portfolio/test/application"
    enable_secret_read = true
    secret_arn         = "arn:aws-us-gov:secretsmanager:us-gov-west-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws-us-gov:iam::000000000000:role/portfolio-test-lambda-execution"
    }
  }
  assert {
    condition = (
      jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com" &&
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${var.log_group_arn}:log-stream:*"] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "ReadAuthorizedSecret"]).Resource == [var.secret_arn] &&
      one([for s in jsondecode(aws_iam_role_policy.this.policy).Statement : s if s.Sid == "DecryptAuthorizedSecret"]).Condition.StringEquals["kms:ViaService"] == "secretsmanager.us-gov-west-1.amazonaws.com" &&
      output.permission_scope.partition == "aws-us-gov"
    )
    error_message = "The supported GovCloud contract must use coherent ARN partitions and the documented regional ViaService name without inventing trust principals."
  }
}

run "valid_role_name_characters" {
  command = plan
  variables { role_name = "portfolio_Example+=,.@-role" }
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/portfolio_Example+=,.@-role"
    }
  }
  assert {
    condition     = aws_iam_role.this.name == var.role_name && output.permission_scope.role_name == var.role_name
    error_message = "Supported IAM role-name characters must pass through exactly."
  }
}

run "maximum_role_name_length" {
  command = plan
  variables { role_name = join("", [for i in range(64) : "r"]) }
  override_resource {
    target          = aws_iam_role.this
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:role/${join("", [for i in range(64) : "r"])}"
    }
  }
  assert {
    condition     = length(aws_iam_role.this.name) == 64 && output.execution_role_name == aws_iam_role.this.name
    error_message = "The supported 64-character role-name boundary must remain usable."
  }
}

run "lambda_log_group_reference" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/aws/lambda/portfolio-api-handler" }
  assert {
    condition     = jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${var.log_group_arn}:log-stream:*"]
    error_message = "A bare ARN from the existing logging module must be scoped to its streams rather than used as a group-wide wildcard."
  }
}

run "maximum_log_group_name_length" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:${join("", [for i in range(512) : "l"])}" }
  assert {
    condition     = jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == ["${var.log_group_arn}:log-stream:*"] && length(aws_iam_role_policy.this.policy) <= 10240
    error_message = "An exact 512-character group name must remain scoped and within the inline-policy size budget."
  }
}

run "caller_owned_unicode_tags" {
  command = plan
  variables { tags = { Project = "explicit-project", Name = "caller-owned", "環境:分類" = "検証 @ team" } }
  assert {
    condition     = length(aws_iam_role.this.tags) == length(var.tags) && alltrue([for key, value in var.tags : aws_iam_role.this.tags[key] == value])
    error_message = "The role must preserve caller-owned non-secret tags without inventing or replacing Project metadata."
  }
}

run "maximum_tag_count_and_lengths" {
  command = plan
  variables {
    tags = merge(
      { for i in range(49) : "Tag${i}" => "test" },
      { (join("", [for i in range(128) : "k"])) = join("", [for i in range(256) : "v"]) }
    )
  }
  assert {
    condition     = length(aws_iam_role.this.tags) == 50 && length(aws_iam_role.this.tags[join("", [for i in range(128) : "k"])]) == 256
    error_message = "The supported 50-tag, 128-character key and 256-character value boundaries must remain usable."
  }
}

run "empty_role_name" {
  command = plan
  variables { role_name = "" }
  expect_failures = [var.role_name]
}

run "role_name_with_path" {
  command = plan
  variables { role_name = "portfolio/role" }
  expect_failures = [var.role_name]
}

run "role_name_with_wildcard" {
  command = plan
  variables { role_name = "portfolio-*" }
  expect_failures = [var.role_name]
}

run "overlong_role_name" {
  command = plan
  variables { role_name = join("", [for i in range(65) : "r"]) }
  expect_failures = [var.role_name]
}

run "null_role_name" {
  command = plan
  variables { role_name = null }
  expect_failures = [var.role_name]
}

run "unsupported_partition" {
  command = plan
  variables { partition = "aws-iso" }
  expect_failures = [var.partition]
}

run "china_partition_not_supported" {
  command = plan
  variables { partition = "aws-cn" }
  expect_failures = [var.partition]
}

run "null_partition" {
  command = plan
  variables { partition = null }
  expect_failures = [var.partition]
}

run "malformed_account_id" {
  command = plan
  variables { account_id = "12345678901" }
  expect_failures = [var.account_id]
}

run "wildcard_account_id" {
  command = plan
  variables { account_id = "00000000000*" }
  expect_failures = [var.account_id]
}

run "null_account_id" {
  command = plan
  variables { account_id = null }
  expect_failures = [var.account_id]
}

run "malformed_region" {
  command = plan
  variables { region = "not-a-region" }
  expect_failures = [var.region]
}

run "china_region_in_aws_partition" {
  command = plan
  variables { region = "cn-north-1" }
  expect_failures = [var.region]
}

run "govcloud_region_in_aws_partition" {
  command = plan
  variables { region = "us-gov-west-1" }
  expect_failures = [var.region]
}

run "null_region" {
  command = plan
  variables { region = null }
  expect_failures = [var.region]
}

run "wildcard_log_group_resource" {
  command = plan
  variables { log_group_arn = "*" }
  expect_failures = [var.log_group_arn]
}

run "wildcard_log_group_name" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/*" }
  expect_failures = [var.log_group_arn]
}

run "log_group_api_star_suffix" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application:*" }
  expect_failures = [var.log_group_arn]
}

run "log_stream_arn_is_not_group_arn" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application:log-stream:stream" }
  expect_failures = [var.log_group_arn]
}

run "missing_log_group_name" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:" }
  expect_failures = [var.log_group_arn]
}

run "overlong_log_group_name" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000000:log-group:${join("", [for i in range(513) : "l"])}" }
  expect_failures = [var.log_group_arn]
}

run "log_group_wrong_account" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:ca-central-1:000000000001:log-group:/portfolio/test/application" }
  expect_failures = [var.log_group_arn]
}

run "log_group_wrong_region" {
  command = plan
  variables { log_group_arn = "arn:aws:logs:us-east-2:000000000000:log-group:/portfolio/test/application" }
  expect_failures = [var.log_group_arn]
}

run "log_group_wrong_partition" {
  command = plan
  variables { log_group_arn = "arn:aws-us-gov:logs:us-gov-west-1:000000000000:log-group:/portfolio/test/application" }
  expect_failures = [var.log_group_arn]
}

run "null_log_group_arn" {
  command = plan
  variables { log_group_arn = null }
  expect_failures = [var.log_group_arn]
}

run "secret_input_while_disabled" {
  command = plan
  variables { secret_arn = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123" }
  expect_failures = [var.secret_arn]
}

run "kms_input_while_disabled" {
  command = plan
  variables { secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.secret_kms_key_arn]
}

run "enabled_secret_missing_arn" {
  command = plan
  variables { enable_secret_read = true }
  expect_failures = [var.secret_arn]
}

run "partial_secret_arn" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime"
  }
  expect_failures = [var.secret_arn]
}

run "short_generated_secret_suffix" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC12"
  }
  expect_failures = [var.secret_arn]
}

run "wildcard_secret_arn" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/*-ABC123"
  }
  expect_failures = [var.secret_arn]
}

run "secret_wrong_account" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000001:secret:portfolio/test/runtime-ABC123"
  }
  expect_failures = [var.secret_arn]
}

run "secret_wrong_region" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:us-east-2:000000000000:secret:portfolio/test/runtime-ABC123"
  }
  expect_failures = [var.secret_arn]
}

run "secret_wrong_partition" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws-us-gov:secretsmanager:us-gov-west-1:000000000000:secret:portfolio/test/runtime-ABC123"
  }
  expect_failures = [var.secret_arn]
}

run "kms_alias_is_not_key_arn" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:alias/portfolio-test"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "bare_kms_identifier" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "wildcard_kms_key" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/*"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "incomplete_kms_key_id" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "kms_wrong_account" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:ca-central-1:000000000001:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "kms_wrong_region" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "kms_wrong_partition" {
  command = plan
  variables {
    enable_secret_read = true
    secret_arn         = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/runtime-ABC123"
    secret_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.secret_kms_key_arn]
}

run "empty_tag_key" {
  command = plan
  variables { tags = { "" = "test" } }
  expect_failures = [var.tags]
}

run "reserved_tag_prefix" {
  command = plan
  variables { tags = { "AWS:Reserved" = "test" } }
  expect_failures = [var.tags]
}

run "null_tag_value" {
  command = plan
  variables { tags = { Owner = null } }
  expect_failures = [var.tags]
}

run "unsupported_tag_key_character" {
  command = plan
  variables { tags = { "Owner?" = "test" } }
  expect_failures = [var.tags]
}

run "unsupported_tag_value_character" {
  command = plan
  variables { tags = { Owner = "test!" } }
  expect_failures = [var.tags]
}

run "overlong_tag_key" {
  command = plan
  variables { tags = { (join("", [for i in range(129) : "k"])) = "test" } }
  expect_failures = [var.tags]
}

run "overlong_tag_value" {
  command = plan
  variables { tags = { Owner = join("", [for i in range(257) : "v"]) } }
  expect_failures = [var.tags]
}

run "too_many_tags" {
  command = plan
  variables { tags = { for i in range(51) : "Tag${i}" => "test" } }
  expect_failures = [var.tags]
}
