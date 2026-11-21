mock_provider "aws" {}

# Synthetic provider-computed identity per repository; nothing contacts or creates AWS.
override_resource {
  target          = module.repositories.aws_ecr_repository.this["istio-pilot"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-istio-pilot"
    region         = "ca-central-1"
    registry_id    = "000000000000"
    repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-istio-pilot"
  }
}
override_resource {
  target          = module.repositories.aws_ecr_repository.this["istio-proxy"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-istio-proxy"
    region         = "ca-central-1"
    registry_id    = "000000000000"
    repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-istio-proxy"
  }
}
override_resource {
  target          = module.repositories.aws_ecr_repository.this["lbc"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-lbc"
    region         = "ca-central-1"
    registry_id    = "000000000000"
    repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-lbc"
  }
}

variables {
  project        = "test"
  aws_account_id = "000000000000"
}

run "registry_from_image_lock" {
  command = plan

  # Repository protections and tags are verified from the plan by tests/check_root.py,
  # which also compares the repositories with kubernetes/images.lock.json.
  assert {
    condition = output.registry == {
      host = "000000000000.dkr.ecr.ca-central-1.amazonaws.com"
      repositories = {
        for purpose in ["istio-pilot", "istio-proxy", "lbc"] : purpose => {
          name           = "test-dev-ecr-${purpose}"
          arn            = "arn:aws:ecr:ca-central-1:000000000000:repository/test-dev-ecr-${purpose}"
          repository_url = "000000000000.dkr.ecr.ca-central-1.amazonaws.com/test-dev-ecr-${purpose}"
        }
      }
    }
    error_message = "The registry output must give the private registry host and one repository per locked purpose, and nothing else."
  }
}

run "teardown_switch_and_caller_tags" {
  command = plan

  variables {
    force_delete = true
    tags         = { owner = "platform" }
  }

  assert {
    condition     = keys(output.registry.repositories) == ["istio-pilot", "istio-proxy", "lbc"]
    error_message = "The teardown switch and caller tags must not change the repository set."
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

run "rejects_name_tag" {
  command = plan

  variables {
    tags = { Name = "other" }
  }

  expect_failures = [var.tags]
}
