mock_provider "aws" {}

# Synthetic computed references only; no AWS account or real secret is used.
override_resource {
  target          = aws_secretsmanager_secret.this
  override_during = plan
  values = {
    arn = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/metadata-ABC123"
    id  = "arn:aws:secretsmanager:ca-central-1:000000000000:secret:portfolio/test/metadata-ABC123"
  }
}

variables {
  name        = "portfolio/test/metadata"
  project_tag = "test-portfolio"
}

run "default_metadata_and_references" {
  command = plan

  assert {
    condition = (
      aws_secretsmanager_secret.this.name == "portfolio/test/metadata" &&
      aws_secretsmanager_secret.this.description == null &&
      aws_secretsmanager_secret.this.tags == tomap({ Name = "portfolio/test/metadata", project = "test-portfolio" }) &&
      aws_secretsmanager_secret.this.recovery_window_in_days == 30
    )
    error_message = "The container must preserve its explicit name, module tags, absent description and 30-day recovery default."
  }

  assert {
    condition = (
      aws_secretsmanager_secret.this.kms_key_id == null &&
      output.kms_configuration.requested_mode == "aws-managed" &&
      output.kms_configuration.configured_key_reference == null &&
      !output.resource_policy_managed
    )
    error_message = "Default encryption must leave key selection to Secrets Manager and must not add a resource policy."
  }

  assert {
    condition = (
      output.secret_arn == aws_secretsmanager_secret.this.arn &&
      output.secret_name == aws_secretsmanager_secret.this.name &&
      output.secret_id == aws_secretsmanager_secret.this.id &&
      output.secret_id == output.secret_arn
    )
    error_message = "Outputs must reference the actual mocked container and provider ID, never construct an ARN suffix."
  }
}

run "description_and_module_tag_ownership" {
  command = plan
  variables {
    description = "Non-sensitive application configuration metadata"
    tags        = { Name = "ignored", project = "ignored", Environment = "test", ManagedBy = "Terraform" }
  }

  assert {
    condition = (
      aws_secretsmanager_secret.this.description == "Non-sensitive application configuration metadata" &&
      aws_secretsmanager_secret.this.tags == tomap({ Name = "portfolio/test/metadata", project = "test-portfolio", Environment = "test", ManagedBy = "Terraform" })
    )
    error_message = "Module-owned Name/project must win while preserving the caller's other metadata tags and description."
  }
}

run "minimum_recovery_window" {
  command = plan
  variables {
    recovery_window_in_days = 7
  }
  assert {
    condition     = aws_secretsmanager_secret.this.recovery_window_in_days == 7
    error_message = "A reviewed minimum seven-day recovery override must be preserved."
  }
}

run "intermediate_recovery_window" {
  command = plan
  variables {
    recovery_window_in_days = 14
  }
  assert {
    condition     = aws_secretsmanager_secret.this.recovery_window_in_days == 14
    error_message = "A valid intermediate recovery override must be preserved."
  }
}

run "existing_customer_managed_key" {
  command = plan
  variables {
    kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  assert {
    condition = (
      aws_secretsmanager_secret.this.kms_key_id == var.kms_key_arn &&
      output.kms_configuration == { requested_mode = "customer-managed", configured_key_reference = var.kms_key_arn }
    )
    error_message = "An existing key ARN must pass through without creating a key or implying KMS authorization."
  }
}

run "existing_multi_region_key_reference" {
  command = plan
  variables {
    kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/mrk-00000000000000000000000000000000"
  }
  assert {
    condition     = aws_secretsmanager_secret.this.kms_key_id == var.kms_key_arn
    error_message = "A format-valid existing multi-region key ARN is accepted without creating replicas."
  }
}

run "full_name_and_bounded_inventory_tag" {
  command = plan
  variables {
    name = join("", [for i in range(512) : "x"])
  }
  assert {
    condition = (
      length(aws_secretsmanager_secret.this.name) == 512 &&
      output.secret_name == var.name &&
      aws_secretsmanager_secret.this.tags.Name == join("", [for i in range(256) : "x"])
    )
    error_message = "The full supported name must survive while Name inventory metadata obeys the tag-value length limit."
  }
}

run "supported_name_characters" {
  command = plan
  variables {
    name = "portfolio/test_1/config+meta=info.@-entry"
  }
  assert {
    condition     = aws_secretsmanager_secret.this.name == var.name
    error_message = "The documented supported ASCII secret-name characters must remain usable."
  }
}

run "empty_name" {
  command = plan
  variables { name = "" }
  expect_failures = [var.name]
}

run "unsupported_name_character" {
  command = plan
  variables { name = "not a valid name" }
  expect_failures = [var.name]
}

run "overlong_name" {
  command = plan
  variables { name = join("", [for i in range(513) : "x"]) }
  expect_failures = [var.name]
}

run "ambiguous_name_suffix" {
  command = plan
  variables { name = "portfolio/metadata-Ab12Cd" }
  expect_failures = [var.name]
}

run "null_required_name" {
  command = plan
  variables { name = null }
  expect_failures = [var.name]
}

run "empty_project_tag" {
  command = plan
  variables { project_tag = "" }
  expect_failures = [var.project_tag]
}

run "invalid_project_tag" {
  command = plan
  variables { project_tag = "Invalid/Project" }
  expect_failures = [var.project_tag]
}

run "null_required_project_tag" {
  command = plan
  variables { project_tag = null }
  expect_failures = [var.project_tag]
}

run "zero_day_deletion_rejected" {
  command = plan
  variables { recovery_window_in_days = 0 }
  expect_failures = [var.recovery_window_in_days]
}

run "recovery_window_below_minimum" {
  command = plan
  variables { recovery_window_in_days = 6 }
  expect_failures = [var.recovery_window_in_days]
}

run "recovery_window_above_maximum" {
  command = plan
  variables { recovery_window_in_days = 31 }
  expect_failures = [var.recovery_window_in_days]
}

run "fractional_recovery_window" {
  command = plan
  variables { recovery_window_in_days = 7.5 }
  expect_failures = [var.recovery_window_in_days]
}

run "kms_alias_rejected" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:alias/example" }
  expect_failures = [var.kms_key_arn]
}

run "kms_invalid_account_rejected" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:not-an-account:key/00000000-0000-0000-0000-000000000000" }
  expect_failures = [var.kms_key_arn]
}

run "kms_wildcard_rejected" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:ca-central-1:000000000000:key/*" }
  expect_failures = [var.kms_key_arn]
}

run "description_length_limit" {
  command = plan
  variables { description = format("%2049s", "metadata") }
  expect_failures = [var.description]
}

run "noncanonical_project_tag_rejected" {
  command = plan
  variables { tags = { Project = "other-project" } }
  expect_failures = [var.tags]
}

run "noncanonical_name_tag_rejected" {
  command = plan
  variables { tags = { NAME = "ambiguous" } }
  expect_failures = [var.tags]
}

run "null_tag_value_rejected" {
  command = plan
  variables { tags = { Environment = null } }
  expect_failures = [var.tags]
}

run "reserved_tag_prefix_rejected" {
  command = plan
  variables { tags = { "aws:reserved" = "not-allowed" } }
  expect_failures = [var.tags]
}

run "tag_value_length_limit" {
  command = plan
  variables { tags = { Environment = join("", [for i in range(257) : "x"]) } }
  expect_failures = [var.tags]
}

run "tag_count_limit" {
  command = plan
  variables { tags = { for i in range(49) : "key-${i}" => "metadata" } }
  expect_failures = [var.tags]
}

run "empty_tag_key_rejected" {
  command = plan
  variables { tags = { "" = "metadata" } }
  expect_failures = [var.tags]
}
