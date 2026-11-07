mock_provider "aws" {}

# Synthetic computed ARN only; no workload account is queried.
override_resource {
  target          = aws_iam_policy.developer_secrets_manager
  override_during = plan
  values = {
    arn = "arn:aws:iam::000000000000:policy/Portfolio-Developer-SecretsManager"
  }
}

variables {
  account_id  = "000000000000"
  region      = "ca-central-1"
  project_tag = "test-portfolio"
}

run "fixed_identity_and_outputs" {
  command = plan

  assert {
    condition = (
      aws_iam_policy.developer_secrets_manager.name == "Portfolio-Developer-SecretsManager" &&
      aws_iam_policy.developer_secrets_manager.path == "/" &&
      aws_iam_policy.developer_secrets_manager.tags == tomap({ Name = "Portfolio-Developer-SecretsManager", Project = "test-portfolio" }) &&
      output.policy_arn == aws_iam_policy.developer_secrets_manager.arn &&
      output.policy_name == aws_iam_policy.developer_secrets_manager.name &&
      output.policy_path == aws_iam_policy.developer_secrets_manager.path &&
      output.policy_json == aws_iam_policy.developer_secrets_manager.policy
    )
    error_message = "Exactly the reviewed policy identity and actual resource references must be exposed."
  }

  assert {
    condition = (
      output.policy_non_whitespace_characters == length(output.policy_json) &&
      output.policy_non_whitespace_characters <= 6144 &&
      output.policy_headroom_characters == 6144 - output.policy_non_whitespace_characters &&
      output.policy_headroom_characters > 0
    )
    error_message = "Quota outputs must measure the actual compact rendered document and remaining headroom."
  }
}

run "module_owned_inventory_tags" {
  command = plan
  variables {
    tags = { Name = "ignored", Project = "ignored", Owner = "test-team" }
  }
  assert {
    condition     = aws_iam_policy.developer_secrets_manager.tags == tomap({ Name = "Portfolio-Developer-SecretsManager", Project = "test-portfolio", Owner = "test-team" })
    error_message = "Additional inventory tags must not override the module-owned policy identity or Project."
  }
}

run "exact_reviewed_policy_actions" {
  command = plan
  assert {
    condition = (
      jsondecode(output.policy_json).Version == "2012-10-17" &&
      length(jsondecode(output.policy_json).Statement) == 5 &&
      toset([for statement in jsondecode(output.policy_json).Statement : statement.Sid]) == toset([
        "CreateProjectSecret", "TagProjectSecretIdentity", "ReadProjectSecretMetadata", "EditProjectSecretTags", "ScheduleProjectSecretDeletion"
      ]) &&
      toset(flatten([for statement in jsondecode(output.policy_json).Statement : statement.Action])) == toset([
        "secretsmanager:CreateSecret", "secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy", "secretsmanager:TagResource", "secretsmanager:UntagResource", "secretsmanager:DeleteSecret"
      ])
    )
    error_message = "All five reviewed statements and exactly six Secrets Manager actions must remain present."
  }
}

run "one_account_region_and_resource_scope" {
  command = plan
  assert {
    condition = alltrue([for statement in jsondecode(output.policy_json).Statement :
      statement.Resource == ["arn:aws:secretsmanager:ca-central-1:000000000000:secret:*"] &&
      statement.Condition.StringEquals["aws:PrincipalAccount"] == "000000000000" &&
      statement.Condition.StringEquals["aws:RequestedRegion"] == "ca-central-1"
    ])
    error_message = "Every statement must authorize only the explicit owning account and region with its exact secret ARN scope."
  }
}

run "creation_request_tags_and_replication_guards" {
  command = plan
  assert {
    condition = one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "CreateProjectSecret"]).Condition == {
      StringEquals = {
        "aws:PrincipalAccount" = "000000000000", "aws:RequestedRegion" = "ca-central-1", "aws:RequestTag/Project" = "test-portfolio"
      }
      "ForAllValues:StringEquals" = { "aws:TagKeys" = ["Environment", "ManagedBy", "Name", "Project", "Service"] }
      Null                        = { "secretsmanager:AddReplicaRegions" = "true" }
      BoolIfExists                = { "secretsmanager:ForceOverwriteReplicaSecret" = "false" }
    }
    error_message = "Creation must require canonical Project request tags and retain supported no-replica/overwrite guards without fake payload restrictions."
  }
}

run "tag_identity_requires_matching_resource_and_request" {
  command = plan
  assert {
    condition = one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "TagProjectSecretIdentity"]).Condition == {
      StringEquals = {
        "aws:PrincipalAccount"   = "000000000000", "aws:RequestedRegion" = "ca-central-1",
        "aws:RequestTag/Project" = "test-portfolio", "aws:ResourceTag/Project" = "test-portfolio"
      }
      "ForAllValues:StringEquals" = { "aws:TagKeys" = ["Environment", "ManagedBy", "Name", "Project", "Service"] }
    }
    error_message = "The special tag grant must require both Project values and canonical keys, never request-tag-only resource adoption."
  }
}

run "metadata_reads_require_existing_project" {
  command = plan
  assert {
    condition = (
      toset(one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "ReadProjectSecretMetadata"]).Action) == toset(["secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy"]) &&
      one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "ReadProjectSecretMetadata"]).Condition == { StringEquals = {
        "aws:PrincipalAccount" = "000000000000", "aws:RequestedRegion" = "ca-central-1", "aws:ResourceTag/Project" = "test-portfolio"
      } }
    )
    error_message = "Provider refresh metadata reads must remain separate from value retrieval and Project-scoped."
  }
}

run "existing_tags_protect_project_identity" {
  command = plan
  assert {
    condition = one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "EditProjectSecretTags"]).Condition == {
      StringEquals = {
        "aws:PrincipalAccount" = "000000000000", "aws:RequestedRegion" = "ca-central-1", "aws:ResourceTag/Project" = "test-portfolio"
      }
      "ForAllValues:StringNotEqualsIgnoreCase" = { "aws:TagKeys" = ["Project"] }
      Null                                     = { "aws:TagKeys" = "false" }
    }
    error_message = "Existing tag edits must exclude every Project case variant and reject a missing tag-key list."
  }
}

run "deletion_recovery_and_force_guards" {
  command = plan
  assert {
    condition = one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "ScheduleProjectSecretDeletion"]).Condition == {
      StringEquals = {
        "aws:PrincipalAccount" = "000000000000", "aws:RequestedRegion" = "ca-central-1", "aws:ResourceTag/Project" = "test-portfolio"
      }
      BoolIfExists             = { "secretsmanager:ForceDeleteWithoutRecovery" = "false" }
      NumericGreaterThanEquals = { "secretsmanager:RecoveryWindowInDays" = "7" }
      NumericLessThanEquals    = { "secretsmanager:RecoveryWindowInDays" = "30" }
    }
    error_message = "Deletion must require an explicit safe 7-30-day recovery interval and reject force deletion while allowing an omitted force flag."
  }
}

run "forbidden_privilege_regression" {
  command = plan
  assert {
    condition = alltrue([for statement in jsondecode(output.policy_json).Statement :
      statement.Effect == "Allow" && !can(statement.NotAction) && !can(statement.NotResource) && !can(statement.Principal) &&
      statement.Resource != ["*"] && alltrue([for action in statement.Action :
        !strcontains(action, "*") && !contains([
          "secretsmanager:UpdateSecret", "secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue", "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecretVersionStage", "secretsmanager:RotateSecret", "secretsmanager:RestoreSecret", "secretsmanager:ListSecrets",
          "secretsmanager:PutResourcePolicy", "secretsmanager:DeleteResourcePolicy", "kms:Decrypt", "iam:PassRole"
        ], action)
      ])
    ])
    error_message = "The policy must not acquire action wildcards, values, updates, recovery, policy administration, KMS or IAM escalation."
  }
}

run "alternate_account_region_and_project" {
  command = plan
  variables {
    account_id  = "000000000001"
    region      = "us-east-2"
    project_tag = "second-project"
  }
  assert {
    condition = alltrue([for statement in jsondecode(output.policy_json).Statement :
      statement.Resource == ["arn:aws:secretsmanager:us-east-2:000000000001:secret:*"] &&
      statement.Condition.StringEquals["aws:PrincipalAccount"] == "000000000001" &&
      statement.Condition.StringEquals["aws:RequestedRegion"] == "us-east-2"
    ])
    error_message = "A second synthetic account/region must generate its own scope, not retain another account's resources."
  }
}

run "government_partition_scope" {
  command = plan
  variables {
    partition = "aws-us-gov"
    region    = "us-gov-west-1"
  }
  assert {
    condition     = alltrue([for statement in jsondecode(output.policy_json).Statement : statement.Resource == ["arn:aws-us-gov:secretsmanager:us-gov-west-1:000000000000:secret:*"]])
    error_message = "The explicitly selected partition must be preserved without account discovery."
  }
}

run "china_partition_scope" {
  command = plan
  variables {
    partition = "aws-cn"
    region    = "cn-north-1"
  }
  assert {
    condition     = alltrue([for statement in jsondecode(output.policy_json).Statement : statement.Resource == ["arn:aws-cn:secretsmanager:cn-north-1:000000000000:secret:*"]])
    error_message = "China partition ARN scope must be explicit and remain limited to the selected account/region."
  }
}

run "longest_project_stays_bounded" {
  command = plan
  variables {
    project_tag = join("", [for i in range(63) : "a"])
  }
  assert {
    condition = (
      output.policy_non_whitespace_characters <= 6144 &&
      one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "CreateProjectSecret"]).Condition.StringEquals["aws:RequestTag/Project"] == var.project_tag &&
      one([for statement in jsondecode(output.policy_json).Statement : statement if statement.Sid == "ReadProjectSecretMetadata"]).Condition.StringEquals["aws:ResourceTag/Project"] == var.project_tag
    )
    error_message = "The maximum valid Project length must remain fully enforced and within the policy quota."
  }
}

run "invalid_account_id" {
  command = plan
  variables { account_id = "not-an-account" }
  expect_failures = [var.account_id]
}

run "account_wildcard_rejected" {
  command = plan
  variables { account_id = "*" }
  expect_failures = [var.account_id]
}

run "empty_account_rejected" {
  command = plan
  variables { account_id = "" }
  expect_failures = [var.account_id]
}

run "region_wildcard_rejected" {
  command = plan
  variables { region = "*" }
  expect_failures = [var.region]
}

run "empty_region_rejected" {
  command = plan
  variables { region = "" }
  expect_failures = [var.region]
}

run "invalid_project_rejected" {
  command = plan
  variables { project_tag = "Other/Project" }
  expect_failures = [var.project_tag]
}

run "overlong_project_rejected" {
  command = plan
  variables { project_tag = join("", [for i in range(64) : "a"]) }
  expect_failures = [var.project_tag]
}

run "empty_project_rejected" {
  command = plan
  variables { project_tag = "" }
  expect_failures = [var.project_tag]
}

run "unsupported_partition_rejected" {
  command = plan
  variables { partition = "aws-other" }
  expect_failures = [var.partition]
}

run "oversize_managed_policy_rejected" {
  command = plan
  variables { region = "us-${join("", [for i in range(800) : "a"])}-1" }
  expect_failures = [aws_iam_policy.developer_secrets_manager]
}
