mock_provider "aws" {}

# Synthetic public-parameter value and provider-computed identities; nothing is
# created and no AWS API is called.
override_data {
  target = data.aws_ssm_parameter.al2023
  values = { insecure_value = "ami-0123456789abcdef0", value = "ami-0123456789abcdef0", type = "String" }
}
override_resource {
  target          = module.developer_access.aws_iam_role.this
  override_during = plan
  values          = { arn = "arn:aws:iam::000000000000:role/test-dev-role-bastion", id = "test-dev-role-bastion" }
}
override_resource {
  target          = module.developer_access.aws_security_group.this
  override_during = plan
  values          = { id = "sg-0123456789abcdef0" }
}
override_resource {
  target          = module.developer_access.aws_instance.this
  override_during = plan
  values          = { id = "i-0123456789abcdef0", private_ip = "10.40.1.10" }
}

run "access_host" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
  }
  assert {
    condition     = output.developer_access == { instance_id = "i-0123456789abcdef0", private_ip = "10.40.1.10", security_group_id = "sg-0123456789abcdef0", role_arn = "arn:aws:iam::000000000000:role/test-dev-role-bastion", region = "ca-central-1" }
    error_message = "The root must expose the Session Manager target, private IP, security group, role and Region."
  }
}

run "alternate_subnet_and_type" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private2"
    instance_type     = "t3.small"
    tags              = { "owner" : "platform" }
  }
  assert {
    condition     = output.developer_access.instance_id == "i-0123456789abcdef0"
    error_message = "The alternate subnet and instance type must still plan the host."
  }
}

run "rejects_foreign_account_scope" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "111111111111" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
  }
  expect_failures = [var.network_reference]
}

run "rejects_other_region_scope" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
  }
  expect_failures = [var.network_reference]
}

run "rejects_interface_version_2" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 2, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
  }
  expect_failures = [var.network_reference]
}

run "rejects_unknown_subnet_key" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "public1"
  }
  expect_failures = [var.subnet_key]
}

run "rejects_invalid_project" {
  command = plan
  variables {
    project           = "aws-proj"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
  }
  expect_failures = [var.project]
}

run "rejects_invalid_account" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "12345"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
  }
  expect_failures = [var.aws_account_id]
}

run "rejects_reserved_tag" {
  command = plan
  variables {
    project           = "test"
    aws_account_id    = "000000000000"
    network_reference = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.40.0.0/16", "private_subnet_ids" : { "private1" : "subnet-0123456789abcdef0", "private2" : "subnet-0fedcba9876543210" } }
    subnet_key        = "private1"
    tags              = { "managed" : "manual" }
  }
  expect_failures = [var.tags]
}
