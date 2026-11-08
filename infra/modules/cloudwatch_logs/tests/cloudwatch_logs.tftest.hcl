mock_provider "aws" {}

# Pinned provider 6.72.0 exports the log-group identity ARN without the API's
# trailing :*. This deterministic fixture is metadata, not an IAM permission.
override_resource {
  target          = aws_cloudwatch_log_group.this
  override_during = plan
  values = {
    arn = "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application"
  }
}

variables {
  name = "/portfolio/test/application"
}

run "default_log_group_configuration" {
  command = plan

  assert {
    condition = (
      aws_cloudwatch_log_group.this.name == var.name &&
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

run "resource_attribute_outputs" {
  command = plan

  assert {
    condition = (
      output.log_group_name == aws_cloudwatch_log_group.this.name &&
      output.log_group_arn == aws_cloudwatch_log_group.this.arn &&
      output.log_group_arn == "arn:aws:logs:ca-central-1:000000000000:log-group:/portfolio/test/application" &&
      output.retention_in_days == aws_cloudwatch_log_group.this.retention_in_days &&
      output.deletion_protection_enabled == aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      output.log_group_class == aws_cloudwatch_log_group.this.log_group_class &&
      output.kms_key_arn == aws_cloudwatch_log_group.this.kms_key_id
    )
    error_message = "Every operational output must read the actual resource attribute, including the provider-computed identity ARN and configured encryption reference."
  }
}

run "lambda_log_group_name" {
  command = plan
  variables { name = "/aws/lambda/portfolio-api-handler" }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == "/aws/lambda/portfolio-api-handler"
    error_message = "A preprovisioned /aws/lambda/ name is valid; only the literal aws/ prefix is rejected."
  }
}

run "workload_log_group_name" {
  command = plan
  variables { name = "/portfolio/dev/serverless-api" }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == var.name
    error_message = "A stable workload-owned name must pass through without random suffixes or module invention."
  }
}

run "maximum_name_length" {
  command = plan
  variables { name = join("", [for i in range(512) : "x"]) }

  assert {
    condition     = length(aws_cloudwatch_log_group.this.name) == 512 && output.log_group_name == var.name
    error_message = "The documented inclusive 512-character name limit must remain usable."
  }
}

run "supported_name_characters" {
  command = plan
  variables { name = "/portfolio/test/log_group-1.#" }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == var.name
    error_message = "CloudWatch Logs name characters include slash, underscore, hyphen, dot and hash."
  }
}

run "minimum_finite_retention" {
  command = plan
  variables { retention_in_days = 1 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 1 && output.retention_in_days == 1
    error_message = "The supported minimum one-day retention must reach the resource and output."
  }
}

run "weekly_retention" {
  command = plan
  variables { retention_in_days = 7 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 7
    error_message = "An explicit supported seven-day root override must be preserved."
  }
}

run "supported_400_day_retention" {
  command = plan
  variables { retention_in_days = 400 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 400
    error_message = "Supported retention choices need not be a simple multiple of 30 or 365."
  }
}

run "supported_731_day_retention" {
  command = plan
  variables { retention_in_days = 731 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 731
    error_message = "The supported leap-year-aware 731-day retention must be accepted exactly."
  }
}

run "maximum_supported_retention" {
  command = plan
  variables { retention_in_days = 3653 }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 3653
    error_message = "The documented maximum supported finite retention is 3653 days, not indefinite retention."
  }
}

run "explicit_disposable_development_override" {
  command = plan
  variables { deletion_protection_enabled = false }

  assert {
    condition = (
      !aws_cloudwatch_log_group.this.deletion_protection_enabled &&
      !output.deletion_protection_enabled &&
      !aws_cloudwatch_log_group.this.skip_destroy &&
      aws_cloudwatch_log_group.this.retention_in_days == 30
    )
    error_message = "An explicit development protection override must not enable skip_destroy or change finite retention."
  }
}

run "existing_symmetric_key_reference" {
  command = plan
  variables {
    kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.kms_key_arn && output.kms_key_arn == var.kms_key_arn
    error_message = "The supplied key reference must pass through; this does not prove key existence, symmetry or authorization."
  }
}

run "existing_multi_region_key_reference" {
  command = plan
  variables {
    kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/mrk-00000000000000000000000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.kms_key_arn
    error_message = "A format-valid regional reference to an existing multi-region key is accepted without creating a key or replica."
  }
}

run "govcloud_partition_key_syntax" {
  command = plan
  variables {
    kms_key_arn = "arn:aws-us-gov:kms:us-gov-west-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.kms_key_arn
    error_message = "A supported GovCloud ARN shape is accepted; selecting a compatible provider and usable regional key remains external."
  }
}

run "china_partition_key_syntax" {
  command = plan
  variables {
    kms_key_arn = "arn:aws-cn:kms:cn-north-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.kms_key_id == var.kms_key_arn
    error_message = "A supported China ARN shape is accepted without claiming real regional or account compatibility."
  }
}

run "caller_owned_unicode_tags" {
  command = plan
  variables {
    tags = { Project = "Root-Owned", "運用:部門" = "本番 構成 +:@/=", Environment = "test" }
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.tags == var.tags &&
      aws_cloudwatch_log_group.this.tags.Project == "Root-Owned" &&
      !contains(keys(aws_cloudwatch_log_group.this.tags), "Name")
    )
    error_message = "Caller Project metadata and API-supported Unicode/colon tags must pass through without invented Name or Project values."
  }
}

run "maximum_tag_count_and_lengths" {
  command = plan
  variables {
    tags = merge(
      { (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) },
      { for i in range(49) : format("tag-%02d", i) => "" }
    )
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.this.tags == var.tags &&
      length(aws_cloudwatch_log_group.this.tags) == 50 &&
      length(aws_cloudwatch_log_group.this.tags[join("", [for i in range(128) : "K"])]) == 256
    )
    error_message = "The documented API limits of 50 tags, 128-character keys, 256-character values and empty values must remain usable."
  }
}

run "empty_name" {
  command = plan
  variables { name = "" }
  expect_failures = [var.name]
}

run "null_name" {
  command = plan
  variables { name = null }
  expect_failures = [var.name]
}

run "name_with_space" {
  command = plan
  variables { name = "invalid name" }
  expect_failures = [var.name]
}

run "name_with_unsupported_character" {
  command = plan
  variables { name = "invalid:name" }
  expect_failures = [var.name]
}

run "literal_aws_prefix" {
  command = plan
  variables { name = "aws/lambda/portfolio-api-handler" }
  expect_failures = [var.name]
}

run "overlong_name" {
  command = plan
  variables { name = join("", [for i in range(513) : "x"]) }
  expect_failures = [var.name]
}

run "indefinite_retention" {
  command = plan
  variables { retention_in_days = 0 }
  expect_failures = [var.retention_in_days]
}

run "negative_retention" {
  command = plan
  variables { retention_in_days = -1 }
  expect_failures = [var.retention_in_days]
}

run "unsupported_short_retention" {
  command = plan
  variables { retention_in_days = 2 }
  expect_failures = [var.retention_in_days]
}

run "fractional_retention" {
  command = plan
  variables { retention_in_days = 1.5 }
  expect_failures = [var.retention_in_days]
}

run "unsupported_366_day_retention" {
  command = plan
  variables { retention_in_days = 366 }
  expect_failures = [var.retention_in_days]
}

run "unsupported_3650_day_retention" {
  command = plan
  variables { retention_in_days = 3650 }
  expect_failures = [var.retention_in_days]
}

run "above_maximum_retention" {
  command = plan
  variables { retention_in_days = 3654 }
  expect_failures = [var.retention_in_days]
}

run "empty_kms_reference" {
  command = plan
  variables { kms_key_arn = "" }
  expect_failures = [var.kms_key_arn]
}

run "key_id_is_not_key_arn" {
  command = plan
  variables { kms_key_arn = "00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.kms_key_arn]
}

run "kms_alias_is_not_key_arn" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:alias/portfolio-test" }
  expect_failures = [var.kms_key_arn]
}

run "incomplete_kms_key_arn" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/" }
  expect_failures = [var.kms_key_arn]
}

run "wildcard_kms_key_arn" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/*" }
  expect_failures = [var.kms_key_arn]
}

run "malformed_kms_account" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:00000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.kms_key_arn]
}

run "unsupported_kms_partition" {
  command = plan
  variables { kms_key_arn = "arn:aws-iso:kms:us-iso-east-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.kms_key_arn]
}

run "non_hexadecimal_kms_identifier" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-00000000000g" }
  expect_failures = [var.kms_key_arn]
}

run "incomplete_multi_region_key_identifier" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/mrk-0000" }
  expect_failures = [var.kms_key_arn]
}

run "wrong_service_key_arn" {
  command = plan
  variables { kms_key_arn = "arn:aws:logs:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.kms_key_arn]
}

run "overlong_kms_key_arn" {
  command = plan
  variables {
    kms_key_arn = "arn:aws:kms:ca-${join("", [for i in range(200) : "a"])}-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.kms_key_arn]
}

run "empty_tag_key" {
  command = plan
  variables { tags = { "" = "invalid" } }
  expect_failures = [var.tags]
}

run "reserved_tag_prefix" {
  command = plan
  variables { tags = { "aws:owner" = "invalid" } }
  expect_failures = [var.tags]
}

run "case_variant_reserved_tag_prefix" {
  command = plan
  variables { tags = { "AWS:owner" = "invalid" } }
  expect_failures = [var.tags]
}

run "null_tag_value" {
  command = plan
  variables { tags = { Test = null } }
  expect_failures = [var.tags]
}

run "overlong_tag_key" {
  command = plan
  variables { tags = { (join("", [for i in range(129) : "K"])) = "invalid" } }
  expect_failures = [var.tags]
}

run "overlong_tag_value" {
  command = plan
  variables { tags = { Test = join("", [for i in range(257) : "v"]) } }
  expect_failures = [var.tags]
}

run "too_many_tags" {
  command = plan
  variables { tags = { for i in range(51) : format("tag-%02d", i) => "invalid" } }
  expect_failures = [var.tags]
}

run "unsupported_tag_key_character" {
  command = plan
  variables { tags = { "invalid#key" = "invalid" } }
  expect_failures = [var.tags]
}

run "unsupported_tag_value_character" {
  command = plan
  variables { tags = { Test = "invalid!value" } }
  expect_failures = [var.tags]
}
