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

run "logging_default_log_group_configuration" {
  command = plan

  assert {
    condition = (
      aws_cloudwatch_log_group.this.name == var.log_group_name &&
      aws_cloudwatch_log_group.this.retention_in_days == 30 &&
      aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      aws_cloudwatch_log_group.this.log_group_class == "STANDARD" &&
      aws_cloudwatch_log_group.this.kms_key_id == null &&
      !aws_cloudwatch_log_group.this.skip_destroy &&
      length(aws_cloudwatch_log_group.this.tags) == 0
    )
    error_message = "Defaults must preserve the supplied name, finite 30-day retention, deletion protection, STANDARD class, ordinary service encryption and no added tags or skip-destroy orphaning."
  }
}


run "logging_resource_attribute_outputs" {
  command = plan

  assert {
    condition = (
      output.log_group_name == aws_cloudwatch_log_group.this.name &&
      output.log_group_arn == aws_cloudwatch_log_group.this.arn &&
      output.log_group_arn == "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application" &&
      output.log_retention_in_days == aws_cloudwatch_log_group.this.retention_in_days &&
      output.log_deletion_protection_enabled == aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      output.log_group_class == aws_cloudwatch_log_group.this.log_group_class &&
      output.log_kms_key_arn == aws_cloudwatch_log_group.this.kms_key_id
    )
    error_message = "Every operational output must read the actual resource attribute, including the provider-computed identity ARN and configured encryption reference."
  }
}


run "logging_lambda_log_group_name" {
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
    condition     = aws_cloudwatch_log_group.this.name == "/aws/lambda/portfolio-api-handler"
    error_message = "A preprovisioned /aws/lambda/ name is valid; only the literal aws/ prefix is rejected."
  }
}


run "logging_workload_log_group_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/dev/serverless-api"
    }
  }
  variables { log_group_name = "/portfolio/dev/serverless-api" }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == var.log_group_name
    error_message = "A stable workload-owned name must pass through without random suffixes or module invention."
  }
}


run "logging_maximum_name_length" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:${join("", [for i in range(512) : "x"])}"
    }
  }
  variables { log_group_name = join("", [for i in range(512) : "x"]) }

  assert {
    condition     = length(aws_cloudwatch_log_group.this.name) == 512 && output.log_group_name == var.log_group_name
    error_message = "The documented inclusive 512-character name limit must remain usable."
  }
}


run "logging_supported_name_characters" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/log_group-1.#"
    }
  }
  variables { log_group_name = "/portfolio/test/log_group-1.#" }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == var.log_group_name
    error_message = "CloudWatch Logs name characters include slash, underscore, hyphen, dot and hash."
  }
}


run "logging_minimum_finite_retention" {
  command = plan
  variables { log_retention_in_days = 1 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 1 && output.log_retention_in_days == 1
    error_message = "The supported minimum one-day retention must reach the resource and output."
  }
}


run "logging_weekly_retention" {
  command = plan
  variables { log_retention_in_days = 7 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 7
    error_message = "An explicit supported seven-day root override must be preserved."
  }
}


run "logging_supported_400_day_retention" {
  command = plan
  variables { log_retention_in_days = 400 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 400
    error_message = "Supported retention choices need not be a simple multiple of 30 or 365."
  }
}


run "logging_supported_731_day_retention" {
  command = plan
  variables { log_retention_in_days = 731 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 731
    error_message = "The supported leap-year-aware 731-day retention must be accepted exactly."
  }
}


run "logging_maximum_supported_retention" {
  command = plan
  variables { log_retention_in_days = 3653 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 3653
    error_message = "The documented maximum supported finite retention is 3653 days, not indefinite retention."
  }
}


run "logging_explicit_disposable_development_override" {
  command = plan
  variables { log_deletion_protection_enabled = false }

  assert {
    condition = (
      !aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      !output.log_deletion_protection_enabled &&
      !aws_cloudwatch_log_group.this.skip_destroy &&
      aws_cloudwatch_log_group.this.retention_in_days == 30
    )
    error_message = "An explicit development protection override must not enable skip_destroy or change finite retention."
  }
}


run "logging_existing_symmetric_key_reference" {
  command = plan
  variables {
    log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.log_kms_key_arn && output.log_kms_key_arn == var.log_kms_key_arn
    error_message = "The supplied key reference must pass through; this does not prove key existence, symmetry or authorization."
  }
}


run "logging_existing_multi_region_key_reference" {
  command = plan
  variables {
    log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/mrk-00000000000000000000000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.log_kms_key_arn
    error_message = "A format-valid regional reference to an existing multi-region key is accepted without creating a key or replica."
  }
}


run "logging_govcloud_partition_key_syntax" {
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
    partition       = "aws-us-gov"
    region          = "us-gov-west-1"
    log_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.log_kms_key_arn
    error_message = "A supported GovCloud ARN shape is accepted; selecting a compatible provider and usable regional key remains external."
  }
}


run "logging_china_partition_key_syntax" {
  command = plan
  variables {
    log_kms_key_arn = "arn:aws-cn:kms:cn-north-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  expect_failures = [var.log_kms_key_arn]
}

run "logging_caller_owned_unicode_tags" {
  command = plan
  variables {
    log_tags = { Project = "Root-Owned", "運用:部門" = "本番 構成 +:@/=", Environment = "test" }
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.tags == var.log_tags &&
      aws_cloudwatch_log_group.this.tags.Project == "Root-Owned" &&
      !contains(keys(aws_cloudwatch_log_group.this.tags), "Name")
    )
    error_message = "Caller Project metadata and API-supported Unicode/colon tags must pass through without invented Name or Project values."
  }
}


run "logging_maximum_tag_count_and_lengths" {
  command = plan
  variables {
    log_tags = merge(
      { (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) },
      { for i in range(49) : format("tag-%02d", i) => "" }
    )
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.tags == var.log_tags &&
      length(aws_cloudwatch_log_group.this.tags) == 50 &&
      length(aws_cloudwatch_log_group.this.tags[join("", [for i in range(128) : "K"])]) == 256
    )
    error_message = "The documented API limits of 50 tags, 128-character keys, 256-character values and empty values must remain usable."
  }
}


run "logging_empty_name" {
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


run "logging_null_name" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:invalid"
    }
  }
  variables { log_group_name = null }
  expect_failures = [var.log_group_name]
}


run "logging_name_with_space" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:invalid name"
    }
  }
  variables { log_group_name = "invalid name" }
  expect_failures = [var.log_group_name]
}


run "logging_name_with_unsupported_character" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:invalid:name"
    }
  }
  variables { log_group_name = "invalid:name" }
  expect_failures = [var.log_group_name]
}


run "logging_literal_aws_prefix" {
  command = plan
  override_resource {
    target          = aws_cloudwatch_log_group.this
    override_during = plan
    values = {
      arn = "arn:aws:logs:ca-central-1:000000000000:log-group:aws/lambda/portfolio-api-handler"
    }
  }
  variables { log_group_name = "aws/lambda/portfolio-api-handler" }
  expect_failures = [var.log_group_name]
}


run "logging_overlong_name" {
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


run "logging_indefinite_retention" {
  command = plan
  variables { log_retention_in_days = 0 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_negative_retention" {
  command = plan
  variables { log_retention_in_days = -1 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_unsupported_short_retention" {
  command = plan
  variables { log_retention_in_days = 2 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_fractional_retention" {
  command = plan
  variables { log_retention_in_days = 1.5 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_unsupported_366_day_retention" {
  command = plan
  variables { log_retention_in_days = 366 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_unsupported_3650_day_retention" {
  command = plan
  variables { log_retention_in_days = 3650 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_above_maximum_retention" {
  command = plan
  variables { log_retention_in_days = 3654 }
  expect_failures = [var.log_retention_in_days]
}


run "logging_empty_kms_reference" {
  command = plan
  variables { log_kms_key_arn = "" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_key_id_is_not_key_arn" {
  command = plan
  variables { log_kms_key_arn = "00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_kms_alias_is_not_key_arn" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:alias/portfolio-test" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_incomplete_kms_key_arn" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_wildcard_kms_key_arn" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/*" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_malformed_kms_account" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:00000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_unsupported_kms_partition" {
  command = plan
  variables { log_kms_key_arn = "arn:aws-iso:kms:us-iso-east-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_non_hexadecimal_kms_identifier" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-00000000000g" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_incomplete_multi_region_key_identifier" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/mrk-0000" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_wrong_service_key_arn" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:logs:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_overlong_kms_key_arn" {
  command = plan
  variables {
    log_kms_key_arn = "arn:aws:kms:ca-${join("", [for i in range(200) : "a"])}-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.log_kms_key_arn]
}


run "logging_empty_tag_key" {
  command = plan
  variables { log_tags = { "" = "invalid" } }
  expect_failures = [var.log_tags]
}


run "logging_reserved_tag_prefix" {
  command = plan
  variables { log_tags = { "aws:owner" = "invalid" } }
  expect_failures = [var.log_tags]
}


run "logging_case_variant_reserved_tag_prefix" {
  command = plan
  variables { log_tags = { "AWS:owner" = "invalid" } }
  expect_failures = [var.log_tags]
}


run "logging_null_tag_value" {
  command = plan
  variables { log_tags = { Test = null } }
  expect_failures = [var.log_tags]
}


run "logging_overlong_tag_key" {
  command = plan
  variables { log_tags = { (join("", [for i in range(129) : "K"])) = "invalid" } }
  expect_failures = [var.log_tags]
}


run "logging_overlong_tag_value" {
  command = plan
  variables { log_tags = { Test = join("", [for i in range(257) : "v"]) } }
  expect_failures = [var.log_tags]
}


run "logging_too_many_tags" {
  command = plan
  variables { log_tags = { for i in range(51) : format("tag-%02d", i) => "invalid" } }
  expect_failures = [var.log_tags]
}


run "logging_unsupported_tag_key_character" {
  command = plan
  variables { log_tags = { "invalid#key" = "invalid" } }
  expect_failures = [var.log_tags]
}


run "logging_unsupported_tag_value_character" {
  command = plan
  variables { log_tags = { Test = "invalid!value" } }
  expect_failures = [var.log_tags]
}

run "logging_owned_key_wrong_account" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:ca-central-1:000000000001:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}

run "logging_owned_key_wrong_region" {
  command = plan
  variables { log_kms_key_arn = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}

run "logging_owned_key_wrong_partition" {
  command = plan
  variables { log_kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.log_kms_key_arn]
}
