mock_provider "aws" {}

# Synthetic provider-computed identity; this never contacts or creates an AWS bucket.
override_resource {
  target          = aws_s3_bucket.this
  override_during = plan
  values = {
    acl           = ""
    policy        = ""
    bucket_prefix = ""
    id            = "test-lambda-artifacts"
    arn           = "arn:aws:s3:::test-lambda-artifacts"
    tags_all      = {}
  }
}

variables {
  bucket_name = "test-lambda-artifacts"
}

run "default_private_bucket" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket.this.bucket == var.bucket_name &&
      aws_s3_bucket.this.bucket_namespace == "global" &&
      !aws_s3_bucket.this.force_destroy &&
      length(aws_s3_bucket.this.tags) == 0 &&
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
      aws_s3_bucket_policy.this.bucket == aws_s3_bucket.this.id
    )
    error_message = "All six resource configurations must bind to the actual bucket identity and preserve fixed versioning, privacy, ownership, encryption and safe nonempty-bucket deletion behavior."
  }

  assert {
    condition = jsondecode(aws_s3_bucket_policy.this.policy) == {
      Version = "2012-10-17"
      Statement = [{
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
        Condition = {
          Bool = {
            "aws:SecureTransport"       = "false"
            "aws:PrincipalIsAWSService" = "false"
          }
        }
      }]
    }
    error_message = "The actual policy must contain only the reviewed bucket/object-scoped insecure-transport Deny, with both required Bool keys and no access Allow."
  }
}

run "resource_attribute_outputs" {
  command = plan

  # A different provider-returned partition distinguishes an actual ARN output
  # from a hard-coded or reconstructed commercial-partition ARN.
  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws-us-gov:s3:::test-lambda-artifacts"
      tags_all      = {}
    }
  }

  assert {
    condition = (
      output.bucket_name == aws_s3_bucket.this.bucket &&
      output.bucket_arn == aws_s3_bucket.this.arn &&
      output.bucket_arn == "arn:aws-us-gov:s3:::test-lambda-artifacts" &&
      output.versioning_status == aws_s3_bucket_versioning.this.versioning_configuration[0].status &&
      output.versioning_status == "Enabled" &&
      jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Resource == [output.bucket_arn, "${output.bucket_arn}/*"]
    )
    error_message = "All outputs and the policy resource scope must preserve actual resource attributes, including the provider-computed partition-aware ARN."
  }
}

run "minimum_name_length" {
  command = plan
  variables { bucket_name = "0a0" }

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "0a0"
      arn           = "arn:aws:s3:::0a0"
      tags_all      = {}
    }
  }

  assert {
    condition     = output.bucket_name == "0a0"
    error_message = "The inclusive three-character lower boundary must allow numeric first and last characters."
  }
}

run "maximum_name_length" {
  command = plan
  variables { bucket_name = join("", [for i in range(63) : "a"]) }

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = join("", [for i in range(63) : "a"])
      arn           = "arn:aws:s3:::${join("", [for i in range(63) : "a"])}"
      tags_all      = {}
    }
  }

  assert {
    condition     = output.bucket_name == var.bucket_name && length(output.bucket_name) == 63
    error_message = "The inclusive 63-character shared-namespace bucket-name boundary must remain accepted without generated suffixes."
  }
}

run "caller_owned_tags" {
  command = plan
  variables { tags = { Owner = "Root-Owned", Purpose = "artifact storage", Empty = "" } }

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws:s3:::test-lambda-artifacts"
      tags_all      = { Owner = "Root-Owned", Purpose = "artifact storage", Empty = "" }
    }
  }

  assert {
    condition     = aws_s3_bucket.this.tags == var.tags && !contains(keys(aws_s3_bucket.this.tags), "Name")
    error_message = "Caller-owned non-secret tags, including an empty value, must pass through without invented module metadata."
  }
}

run "maximum_tag_limits" {
  command = plan
  variables {
    tags = merge(
      { (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) },
      { for i in range(49) : format("tag-%02d", i) => "" }
    )
  }

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws:s3:::test-lambda-artifacts"
      tags_all = merge(
        { (join("", [for i in range(128) : "K"])) = join("", [for i in range(256) : "v"]) },
        { for i in range(49) : format("tag-%02d", i) => "" }
      )
    }
  }

  assert {
    condition     = aws_s3_bucket.this.tags == var.tags && length(aws_s3_bucket.this.tags) == 50
    error_message = "Exactly 50 non-secret tags, 128-character keys and 256-character values must remain accepted."
  }
}

run "effective_provider_default_tags" {
  command = plan
  variables { tags = { Owner = "Root-Owned" } }

  # Model the provider-computed merged result; this is not a second provider
  # configuration and does not claim to exercise a real provider's merge logic.
  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws:s3:::test-lambda-artifacts"
      tags_all      = { Owner = "Root-Owned", CostCentre = "test-default" }
    }
  }

  assert {
    condition = (
      aws_s3_bucket.this.tags == var.tags &&
      aws_s3_bucket.this.tags_all == tomap({ Owner = "Root-Owned", CostCentre = "test-default" })
    )
    error_message = "Caller tags and a valid mocked provider-default merge must both satisfy the effective tag contract."
  }
}

run "empty_bucket_name" {
  command = plan
  variables { bucket_name = "" }
  expect_failures = [var.bucket_name]
}

run "too_short_bucket_name" {
  command = plan
  variables { bucket_name = "ab" }
  expect_failures = [var.bucket_name]
}

run "too_long_bucket_name" {
  command = plan
  variables { bucket_name = join("", [for i in range(64) : "a"]) }
  expect_failures = [var.bucket_name]
}

run "uppercase_bucket_name" {
  command = plan
  variables { bucket_name = "Test-artifacts" }
  expect_failures = [var.bucket_name]
}

run "bucket_name_with_period" {
  command = plan
  variables { bucket_name = "test.artifacts" }
  expect_failures = [var.bucket_name]
}

run "unsupported_bucket_character" {
  command = plan
  variables { bucket_name = "test_artifacts" }
  expect_failures = [var.bucket_name]
}

run "leading_hyphen_bucket_name" {
  command = plan
  variables { bucket_name = "-test-artifacts" }
  expect_failures = [var.bucket_name]
}

run "trailing_hyphen_bucket_name" {
  command = plan
  variables { bucket_name = "test-artifacts-" }
  expect_failures = [var.bucket_name]
}

run "wildcard_bucket_name" {
  command = plan
  variables { bucket_name = "test-artifacts-*" }
  expect_failures = [var.bucket_name]
}

run "bucket_arn_instead_of_name" {
  command = plan
  variables { bucket_name = "arn:aws:s3:::test-artifacts" }
  expect_failures = [var.bucket_name]
}

run "null_bucket_name" {
  command = plan
  variables { bucket_name = null }
  expect_failures = [var.bucket_name]
}

run "xn_reserved_prefix" {
  command = plan
  variables { bucket_name = "xn--test-artifacts" }
  expect_failures = [var.bucket_name]
}

run "sthree_reserved_prefix" {
  command = plan
  variables { bucket_name = "sthree-test-artifacts" }
  expect_failures = [var.bucket_name]
}

run "amzn_s3_demo_reserved_prefix" {
  command = plan
  variables { bucket_name = "amzn-s3-demo-test-artifacts" }
  expect_failures = [var.bucket_name]
}

run "s3alias_reserved_suffix" {
  command = plan
  variables { bucket_name = "test-artifacts-s3alias" }
  expect_failures = [var.bucket_name]
}

run "object_lambda_reserved_suffix" {
  command = plan
  variables { bucket_name = "test-artifacts--ol-s3" }
  expect_failures = [var.bucket_name]
}

run "mrap_reserved_suffix" {
  command = plan
  variables { bucket_name = "test-artifacts.mrap" }
  expect_failures = [var.bucket_name]
}

run "directory_bucket_reserved_suffix" {
  command = plan
  variables { bucket_name = "test-artifacts--x-s3" }
  expect_failures = [var.bucket_name]
}

run "table_bucket_reserved_suffix" {
  command = plan
  variables { bucket_name = "test-artifacts--table-s3" }
  expect_failures = [var.bucket_name]
}

run "account_regional_reserved_suffix" {
  command = plan
  variables { bucket_name = "test-artifacts-an" }
  expect_failures = [var.bucket_name]
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
  variables { tags = { Owner = null } }
  expect_failures = [var.tags]
}

run "overlong_tag_key" {
  command = plan
  variables { tags = { (join("", [for i in range(129) : "K"])) = "invalid" } }
  expect_failures = [var.tags]
}

run "overlong_tag_value" {
  command = plan
  variables { tags = { Owner = join("", [for i in range(257) : "v"]) } }
  expect_failures = [var.tags]
}

run "too_many_tags" {
  command = plan
  variables { tags = { for i in range(51) : format("tag-%02d", i) => "invalid" } }
  expect_failures = [var.tags]
}

run "effective_provider_tags_exceed_limit" {
  command = plan

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws:s3:::test-lambda-artifacts"
      tags_all      = { for i in range(51) : format("tag-%02d", i) => "invalid" }
    }
  }

  expect_failures = [aws_s3_bucket.this]
}

run "effective_provider_reserved_tag_prefix" {
  command = plan

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws:s3:::test-lambda-artifacts"
      tags_all      = { "aws:owner" = "invalid" }
    }
  }

  expect_failures = [aws_s3_bucket.this]
}

run "effective_provider_overlong_tag_value" {
  command = plan

  override_resource {
    target          = aws_s3_bucket.this
    override_during = plan
    values = {
      acl           = ""
      policy        = ""
      bucket_prefix = ""
      id            = "test-lambda-artifacts"
      arn           = "arn:aws:s3:::test-lambda-artifacts"
      tags_all      = { Owner = join("", [for i in range(257) : "v"]) }
    }
  }

  expect_failures = [aws_s3_bucket.this]
}
