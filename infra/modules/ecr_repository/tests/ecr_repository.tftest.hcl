mock_provider "aws" {}

# Synthetic provider-computed identity per repository; nothing contacts or creates AWS.
override_resource {
  target          = aws_ecr_repository.this["istio-pilot"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-istio-pilot"
    region         = "ca-central-1"
    registry_id    = "000000000000"
    repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-istio-pilot"
  }
}
override_resource {
  target          = aws_ecr_repository.this["istio-proxy"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-istio-proxy"
    region         = "ca-central-1"
    registry_id    = "000000000000"
    repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-istio-proxy"
  }
}
override_resource {
  target          = aws_ecr_repository.this["lbc"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-lbc"
    region         = "ca-central-1"
    registry_id    = "000000000000"
    repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-lbc"
  }
}

variables {
  name_prefix    = "test-dev"
  purposes       = ["istio-pilot", "istio-proxy", "lbc"]
  expected_scope = { account_id = "000000000000", region = "ca-central-1" }
}

run "locked_repositories" {
  command = plan

  assert {
    condition = (
      length(aws_ecr_repository.this) == 3 &&
      alltrue([for purpose, repository in aws_ecr_repository.this :
        repository.name == "test-dev-ecr-${purpose}" &&
        repository.image_tag_mutability == "IMMUTABLE" &&
        length(repository.image_tag_mutability_exclusion_filter) == 0 &&
        !repository.force_delete &&
        one(repository.encryption_configuration).encryption_type == "AES256" &&
        one(repository.image_scanning_configuration).scan_on_push == false &&
        repository.tags == tomap({ Name = "test-dev-ecr-${purpose}", service = "ecr" })
      ])
    )
    error_message = "Each locked purpose needs one private repository: immutable tags, AES-256, no forced deletion, module-owned tags."
  }

  assert {
    condition = output.repositories == {
      for purpose in ["istio-pilot", "istio-proxy", "lbc"] : purpose => {
        name           = "test-dev-ecr-${purpose}"
        arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-${purpose}"
        repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-${purpose}"
      }
    }
    error_message = "The output must give each repository's actual name, ARN and URL, and nothing else."
  }
}

run "teardown_switch_and_caller_tags" {
  command = plan

  variables {
    force_delete = true
    tags         = { owner = "platform" }
  }

  assert {
    condition = alltrue([for purpose, repository in aws_ecr_repository.this :
      repository.force_delete && repository.image_tag_mutability == "IMMUTABLE" &&
      repository.tags == tomap({ owner = "platform", Name = "test-dev-ecr-${purpose}", service = "ecr" })
    ])
    error_message = "The teardown switch may only enable forced deletion; caller tags pass through beside the module-owned tags."
  }
}

run "rejects_foreign_account_repository" {
  command = plan

  override_resource {
    target          = aws_ecr_repository.this["lbc"]
    override_during = plan
    values = {
      arn            = "arn:aws:ecr:ca-central-1:111111111111:repository/test-dev-ecr-lbc"
      region         = "ca-central-1"
      registry_id    = "111111111111"
      repository_url = "111111111111.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-lbc"
    }
  }

  expect_failures = [aws_ecr_repository.this["lbc"]]
}

run "rejects_other_region_repository" {
  command = plan

  override_resource {
    target          = aws_ecr_repository.this["istio-pilot"]
    override_during = plan
    values = {
      arn            = "arn:aws:ecr:us-east-1:000000000000:repository/test-dev-ecr-istio-pilot"
      region         = "us-east-1"
      registry_id    = "000000000000"
      repository_url = "000000000000.dkr.ecr.us-east-1.amazonaws.com/test-dev-ecr-istio-pilot"
    }
  }

  expect_failures = [aws_ecr_repository.this["istio-pilot"]]
}

run "rejects_uppercase_prefix" {
  command = plan

  variables {
    name_prefix = "Test-dev"
  }

  expect_failures = [var.name_prefix]
}

run "rejects_prefix_without_environment" {
  command = plan

  variables {
    name_prefix = "test"
  }

  expect_failures = [var.name_prefix]
}

run "rejects_long_project_prefix" {
  command = plan

  variables {
    name_prefix = "projectname1-dev"
  }

  expect_failures = [var.name_prefix]
}

run "rejects_empty_purposes" {
  command = plan

  variables {
    purposes = []
  }

  expect_failures = [var.purposes]
}

run "rejects_uppercase_purpose" {
  command = plan

  variables {
    purposes = ["Istio-pilot"]
  }

  expect_failures = [var.purposes]
}

run "rejects_purpose_with_slash" {
  command = plan

  variables {
    purposes = ["istio/pilot"]
  }

  expect_failures = [var.purposes]
}

run "rejects_too_many_purposes" {
  command = plan

  variables {
    purposes = ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9", "a10", "a11"]
  }

  expect_failures = [var.purposes]
}

run "rejects_invalid_account" {
  command = plan

  variables {
    expected_scope = { account_id = "12345", region = "ca-central-1" }
  }

  expect_failures = [var.expected_scope]
}

run "rejects_invalid_region" {
  command = plan

  variables {
    expected_scope = { account_id = "000000000000", region = "Canada" }
  }

  expect_failures = [var.expected_scope]
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
    tags = { service = "s3" }
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
