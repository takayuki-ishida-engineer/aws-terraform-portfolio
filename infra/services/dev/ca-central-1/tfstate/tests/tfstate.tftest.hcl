mock_provider "aws" {}

# Synthetic provider-computed identity; this never contacts or creates an AWS bucket.
override_resource {
  target          = module.state_bucket.aws_s3_bucket.this
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
  project        = "test"
  aws_account_id = "000000000000"
}

run "bootstrap_state_bucket" {
  command = plan

  # Bucket protections and tags are verified from the plan by tests/check_root.py.

  assert {
    condition = output.backend_settings == {
      bucket       = "test-dev-s3-tfstate"
      region       = "ca-central-1"
      use_lockfile = true
      encrypt      = true
      keys = {
        network          = "test/dev/ca-central-1/network/terraform.tfstate"
        platform         = "test/dev/ca-central-1/platform/terraform.tfstate"
        "serverless-api" = "test/dev/ca-central-1/serverless-api/terraform.tfstate"
        api              = "test/dev/ca-central-1/api/terraform.tfstate"
      }
    }
    error_message = "backend_settings must give the bucket, Region, native locking, encryption and one <project>/dev/ca-central-1/<root>/terraform.tfstate key per root."
  }

  assert {
    condition     = output.bucket_name == "test-dev-s3-tfstate" && output.bucket_arn == "arn:aws:s3:::test-dev-s3-tfstate"
    error_message = "Outputs must expose the actual bucket name and ARN."
  }
}

run "caller_tags_pass_through" {
  command = plan

  variables {
    tags = { owner = "platform" }
  }

  # Root assertions see only module outputs; tests/check_root.py verifies the
  # planned bucket tags and every fixed protection from the actual plan events.
  assert {
    condition     = output.bucket_name == "test-dev-s3-tfstate"
    error_message = "Caller tags must not change the derived bucket name."
  }
}

run "rejects_invalid_project" {
  command = plan

  variables {
    project = "aws-proj"
  }

  expect_failures = [var.project]
}

run "rejects_long_project" {
  command = plan

  variables {
    project = "projectname1"
  }

  expect_failures = [var.project]
}

run "rejects_invalid_account" {
  command = plan

  variables {
    aws_account_id = "12345"
  }

  expect_failures = [var.aws_account_id]
}

run "rejects_reserved_tag" {
  command = plan

  variables {
    tags = { managed = "manual" }
  }

  expect_failures = [var.tags]
}
