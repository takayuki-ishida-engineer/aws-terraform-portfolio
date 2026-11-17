mock_provider "aws" {}

# Synthetic provider-computed identity; this never contacts or creates an AWS bucket.
override_resource {
  target          = aws_s3_bucket.this
  override_during = plan
  values = {
    acl           = ""
    policy        = ""
    bucket_prefix = ""
    id            = "test-dev-s3-tfstate"
    arn           = "arn:aws:s3:::test-dev-s3-tfstate"
  }
}

variables {
  bucket_name = "test-dev-s3-tfstate"
}

run "default_state_bucket" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket.this.bucket == var.bucket_name &&
      aws_s3_bucket.this.bucket_namespace == "global" &&
      !aws_s3_bucket.this.force_destroy &&
      aws_s3_bucket_versioning.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled" &&
      aws_s3_bucket_public_access_block.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_public_access_block.this.block_public_acls &&
      aws_s3_bucket_public_access_block.this.ignore_public_acls &&
      aws_s3_bucket_public_access_block.this.block_public_policy &&
      aws_s3_bucket_public_access_block.this.restrict_public_buckets &&
      aws_s3_bucket_ownership_controls.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_ownership_controls.this.rule[0].object_ownership == "BucketOwnerEnforced" &&
      aws_s3_bucket_server_side_encryption_configuration.this.bucket == aws_s3_bucket.this.id &&
      one(aws_s3_bucket_server_side_encryption_configuration.this.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" &&
      aws_s3_bucket_lifecycle_configuration.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_policy.this.bucket == aws_s3_bucket.this.id
    )
    error_message = "Every bucket configuration must bind to the actual bucket and keep versioning, privacy, ownership, SSE-S3 encryption and non-forced deletion."
  }

  assert {
    condition = jsondecode(aws_s3_bucket_policy.this.policy) == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid       = "DenyInsecureTransport"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
          Condition = { Bool = { "aws:SecureTransport" = "false" } }
        },
        {
          Sid       = "DenyOutdatedTls"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
          Condition = { NumericLessThan = { "s3:TlsVersion" = "1.2" } }
        },
      ]
    }
    error_message = "The bucket policy must deny every non-TLS and pre-TLS-1.2 request to the bucket and its objects, with no exception."
  }
  assert {
    condition = (
      length(aws_s3_bucket_lifecycle_configuration.this.rule) == 1 &&
      one(aws_s3_bucket_lifecycle_configuration.this.rule).id == "state-history" &&
      one(aws_s3_bucket_lifecycle_configuration.this.rule).status == "Enabled" &&
      one(one(aws_s3_bucket_lifecycle_configuration.this.rule).noncurrent_version_expiration).noncurrent_days == 90 &&
      one(one(aws_s3_bucket_lifecycle_configuration.this.rule).abort_incomplete_multipart_upload).days_after_initiation == 7 &&
      length(one(aws_s3_bucket_lifecycle_configuration.this.rule).expiration) == 0
    )
    error_message = "Lifecycle must only expire noncurrent State versions after 90 days and abort incomplete uploads after 7 days; current State never expires."
  }

  assert {
    condition     = aws_s3_bucket.this.tags == tomap({ Name = "test-dev-s3-tfstate", service = "s3" })
    error_message = "Default tags must be exactly the module-owned Name and service."
  }

  assert {
    condition     = output.bucket_name == "test-dev-s3-tfstate" && output.bucket_arn == "arn:aws:s3:::test-dev-s3-tfstate" && output.versioning_status == "Enabled"
    error_message = "Outputs must expose the actual bucket name, ARN and versioning status."
  }
}

run "custom_retention_and_tags" {
  command = plan

  variables {
    noncurrent_version_retention_days = 30
    tags                              = { owner = "platform" }
  }

  assert {
    condition = (
      aws_s3_bucket.this.bucket == var.bucket_name &&
      aws_s3_bucket.this.bucket_namespace == "global" &&
      !aws_s3_bucket.this.force_destroy &&
      aws_s3_bucket_versioning.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled" &&
      aws_s3_bucket_public_access_block.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_public_access_block.this.block_public_acls &&
      aws_s3_bucket_public_access_block.this.ignore_public_acls &&
      aws_s3_bucket_public_access_block.this.block_public_policy &&
      aws_s3_bucket_public_access_block.this.restrict_public_buckets &&
      aws_s3_bucket_ownership_controls.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_ownership_controls.this.rule[0].object_ownership == "BucketOwnerEnforced" &&
      aws_s3_bucket_server_side_encryption_configuration.this.bucket == aws_s3_bucket.this.id &&
      one(aws_s3_bucket_server_side_encryption_configuration.this.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" &&
      aws_s3_bucket_lifecycle_configuration.this.bucket == aws_s3_bucket.this.id &&
      aws_s3_bucket_policy.this.bucket == aws_s3_bucket.this.id
    )
    error_message = "Every bucket configuration must bind to the actual bucket and keep versioning, privacy, ownership, SSE-S3 encryption and non-forced deletion."
  }

  assert {
    condition = jsondecode(aws_s3_bucket_policy.this.policy) == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid       = "DenyInsecureTransport"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
          Condition = { Bool = { "aws:SecureTransport" = "false" } }
        },
        {
          Sid       = "DenyOutdatedTls"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
          Condition = { NumericLessThan = { "s3:TlsVersion" = "1.2" } }
        },
      ]
    }
    error_message = "The bucket policy must deny every non-TLS and pre-TLS-1.2 request to the bucket and its objects, with no exception."
  }
  assert {
    condition = (
      length(aws_s3_bucket_lifecycle_configuration.this.rule) == 1 &&
      one(aws_s3_bucket_lifecycle_configuration.this.rule).id == "state-history" &&
      one(aws_s3_bucket_lifecycle_configuration.this.rule).status == "Enabled" &&
      one(one(aws_s3_bucket_lifecycle_configuration.this.rule).noncurrent_version_expiration).noncurrent_days == 30 &&
      one(one(aws_s3_bucket_lifecycle_configuration.this.rule).abort_incomplete_multipart_upload).days_after_initiation == 7 &&
      length(one(aws_s3_bucket_lifecycle_configuration.this.rule).expiration) == 0
    )
    error_message = "Lifecycle must only expire noncurrent State versions after 30 days and abort incomplete uploads after 7 days; current State never expires."
  }

  assert {
    condition     = aws_s3_bucket.this.tags == tomap({ owner = "platform", Name = "test-dev-s3-tfstate", service = "s3" })
    error_message = "Caller tags must merge with the module-owned Name and service."
  }
}

run "maximum_retention" {
  command = plan

  variables {
    noncurrent_version_retention_days = 365
  }

  assert {
    condition = (
      length(aws_s3_bucket_lifecycle_configuration.this.rule) == 1 &&
      one(aws_s3_bucket_lifecycle_configuration.this.rule).id == "state-history" &&
      one(aws_s3_bucket_lifecycle_configuration.this.rule).status == "Enabled" &&
      one(one(aws_s3_bucket_lifecycle_configuration.this.rule).noncurrent_version_expiration).noncurrent_days == 365 &&
      one(one(aws_s3_bucket_lifecycle_configuration.this.rule).abort_incomplete_multipart_upload).days_after_initiation == 7 &&
      length(one(aws_s3_bucket_lifecycle_configuration.this.rule).expiration) == 0
    )
    error_message = "Lifecycle must only expire noncurrent State versions after 365 days and abort incomplete uploads after 7 days; current State never expires."
  }
}

run "rejects_bucket_without_tfstate_suffix" {
  command = plan

  variables {
    bucket_name = "test-dev-s3-artifact"
  }

  expect_failures = [var.bucket_name]
}

run "rejects_uppercase_bucket" {
  command = plan

  variables {
    bucket_name = "Test-dev-s3-tfstate"
  }

  expect_failures = [var.bucket_name]
}

run "rejects_reserved_prefix" {
  command = plan

  variables {
    bucket_name = "xn--test-s3-tfstate"
  }

  expect_failures = [var.bucket_name]
}

run "rejects_period_in_bucket" {
  command = plan

  variables {
    bucket_name = "test.dev-s3-tfstate"
  }

  expect_failures = [var.bucket_name]
}

run "rejects_short_retention" {
  command = plan

  variables {
    noncurrent_version_retention_days = 29
  }

  expect_failures = [var.noncurrent_version_retention_days]
}

run "rejects_long_retention" {
  command = plan

  variables {
    noncurrent_version_retention_days = 366
  }

  expect_failures = [var.noncurrent_version_retention_days]
}

run "rejects_fractional_retention" {
  command = plan

  variables {
    noncurrent_version_retention_days = 90.5
  }

  expect_failures = [var.noncurrent_version_retention_days]
}

run "rejects_name_tag" {
  command = plan

  variables {
    tags = { Name = "other" }
  }

  expect_failures = [var.tags]
}

run "rejects_service_tag" {
  command = plan

  variables {
    tags = { service = "other" }
  }

  expect_failures = [var.tags]
}

run "rejects_aws_prefixed_tag" {
  command = plan

  variables {
    tags = { "aws:owner" = "x" }
  }

  expect_failures = [var.tags]
}

run "rejects_long_tag_value" {
  command = plan

  variables {
    tags = { owner = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" }
  }

  expect_failures = [var.tags]
}
