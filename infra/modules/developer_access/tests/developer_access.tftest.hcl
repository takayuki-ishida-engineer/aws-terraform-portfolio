mock_provider "aws" {}

# Synthetic provider-computed identities; nothing is created and no AWS API is called.
override_resource {
  target          = aws_iam_role.this
  override_during = plan
  values          = { arn = "arn:aws:iam::000000000000:role/test-dev-role-bastion", id = "test-dev-role-bastion" }
}
override_resource {
  target          = aws_security_group.this
  override_during = plan
  values          = { id = "sg-0123456789abcdef0", arn = "arn:aws:ec2:ca-central-1:000000000000:security-group/sg-0123456789abcdef0" }
}
override_resource {
  target          = aws_instance.this
  override_during = plan
  values          = { id = "i-0123456789abcdef0", private_ip = "10.40.1.10", arn = "arn:aws:ec2:ca-central-1:000000000000:instance/i-0123456789abcdef0" }
}

variables {
  name_prefix  = "test-dev"
  vpc_id       = "vpc-0123456789abcdef0"
  vpc_cidr     = "10.40.0.0/16"
  subnet_id    = "subnet-0123456789abcdef0"
  ami_id       = "ami-0123456789abcdef0"
  default_tags = { project = "test", env = "dev", managed = "terraform" }
}

run "default_access_host" {
  command = plan

  assert {
    condition = (
      aws_instance.this.ami == var.ami_id && aws_instance.this.subnet_id == var.subnet_id &&
      aws_instance.this.vpc_security_group_ids == toset([aws_security_group.this.id]) &&
      aws_instance.this.iam_instance_profile == aws_iam_instance_profile.this.name &&
      aws_instance.this.associate_public_ip_address == false &&
      aws_instance.this.user_data == null &&
      one(aws_instance.this.metadata_options).http_tokens == "required" &&
      one(aws_instance.this.metadata_options).http_put_response_hop_limit == 1 &&
      one(aws_instance.this.metadata_options).http_endpoint == "enabled" &&
      one(aws_instance.this.root_block_device).encrypted == true &&
      one(aws_instance.this.root_block_device).volume_type == "gp3"
    )
    error_message = "The host must stay private (no public IP, no SSH key, no user data), (no key_name in the source) require IMDSv2 with hop limit 1 and use an encrypted gp3 root volume."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.vpc_https.security_group_id == aws_security_group.this.id &&
      aws_vpc_security_group_egress_rule.vpc_https.cidr_ipv4 == var.vpc_cidr &&
      aws_vpc_security_group_egress_rule.vpc_https.ip_protocol == "tcp" &&
      aws_vpc_security_group_egress_rule.vpc_https.from_port == 443 && aws_vpc_security_group_egress_rule.vpc_https.to_port == 443 &&
      aws_security_group.this.vpc_id == var.vpc_id
    )
    error_message = "The only security group rule is HTTPS egress to the VPC CIDR."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.this.assume_role_policy) == { Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }] } &&
      aws_iam_role_policy_attachment.ssm.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" &&
      aws_iam_role_policy_attachment.ssm.role == aws_iam_role.this.name &&
      aws_iam_instance_profile.this.role == aws_iam_role.this.name
    )
    error_message = "The role trusts only EC2 and carries only AmazonSSMManagedInstanceCore."
  }

  assert {
    condition = (
      aws_instance.this.instance_type == "t3.micro" &&
      aws_instance.this.tags == tomap({ Name = "test-dev-ec2-bastion", service = "ec2" }) &&
      one(aws_instance.this.root_block_device).tags == tomap({ project = "test", env = "dev", managed = "terraform", Name = "test-dev-ec2-bastion-root", service = "ec2" }) &&
      aws_iam_role.this.name == "test-dev-role-bastion" && aws_iam_instance_profile.this.name == "test-dev-profile-bastion" &&
      aws_security_group.this.name == "test-dev-sg-bastion"
    )
    error_message = "Names and tags must follow <prefix>-<type>-bastion with the module-owned Name and service."
  }

  assert {
    condition     = output.instance_id == "i-0123456789abcdef0" && output.security_group_id == "sg-0123456789abcdef0" && output.role_arn == "arn:aws:iam::000000000000:role/test-dev-role-bastion" && output.private_ip == "10.40.1.10"
    error_message = "Outputs must expose the actual instance, security group, role and private IP."
  }
}

run "custom_type_and_tags" {
  command = plan

  variables {
    instance_type = "t3.small"
    tags          = { owner = "platform" }
  }

  assert {
    condition = (
      aws_instance.this.ami == var.ami_id && aws_instance.this.subnet_id == var.subnet_id &&
      aws_instance.this.vpc_security_group_ids == toset([aws_security_group.this.id]) &&
      aws_instance.this.iam_instance_profile == aws_iam_instance_profile.this.name &&
      aws_instance.this.associate_public_ip_address == false &&
      aws_instance.this.user_data == null &&
      one(aws_instance.this.metadata_options).http_tokens == "required" &&
      one(aws_instance.this.metadata_options).http_put_response_hop_limit == 1 &&
      one(aws_instance.this.metadata_options).http_endpoint == "enabled" &&
      one(aws_instance.this.root_block_device).encrypted == true &&
      one(aws_instance.this.root_block_device).volume_type == "gp3"
    )
    error_message = "The host must stay private (no public IP, no SSH key, no user data), (no key_name in the source) require IMDSv2 with hop limit 1 and use an encrypted gp3 root volume."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.vpc_https.security_group_id == aws_security_group.this.id &&
      aws_vpc_security_group_egress_rule.vpc_https.cidr_ipv4 == var.vpc_cidr &&
      aws_vpc_security_group_egress_rule.vpc_https.ip_protocol == "tcp" &&
      aws_vpc_security_group_egress_rule.vpc_https.from_port == 443 && aws_vpc_security_group_egress_rule.vpc_https.to_port == 443 &&
      aws_security_group.this.vpc_id == var.vpc_id
    )
    error_message = "The only security group rule is HTTPS egress to the VPC CIDR."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.this.assume_role_policy) == { Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }] } &&
      aws_iam_role_policy_attachment.ssm.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" &&
      aws_iam_role_policy_attachment.ssm.role == aws_iam_role.this.name &&
      aws_iam_instance_profile.this.role == aws_iam_role.this.name
    )
    error_message = "The role trusts only EC2 and carries only AmazonSSMManagedInstanceCore."
  }

  assert {
    condition     = aws_instance.this.instance_type == "t3.small" && aws_instance.this.tags == tomap({ owner = "platform", Name = "test-dev-ec2-bastion", service = "ec2" })
    error_message = "The instance type override and caller tags must apply."
  }
}

run "rejects_invalid_ami" {
  command = plan

  variables {
    ami_id = "ami-xyz"
  }

  expect_failures = [var.ami_id]
}

run "rejects_invalid_subnet" {
  command = plan

  variables {
    subnet_id = "subnet-1"
  }

  expect_failures = [var.subnet_id]
}

run "rejects_invalid_vpc" {
  command = plan

  variables {
    vpc_id = "vpc-zz"
  }

  expect_failures = [var.vpc_id]
}

run "rejects_non_canonical_cidr" {
  command = plan

  variables {
    vpc_cidr = "10.40.1.0/16"
  }

  expect_failures = [var.vpc_cidr]
}

run "rejects_wide_cidr" {
  command = plan

  variables {
    vpc_cidr = "10.0.0.0/8"
  }

  expect_failures = [var.vpc_cidr]
}

run "rejects_unsupported_instance_type" {
  command = plan

  variables {
    instance_type = "m5.large"
  }

  expect_failures = [var.instance_type]
}

run "rejects_name_tag" {
  command = plan

  variables {
    tags = { Name = "x" }
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

run "rejects_extra_default_tag" {
  command = plan

  variables {
    default_tags = { project = "test", Team = "x" }
  }

  expect_failures = [var.default_tags]
}

run "rejects_invalid_name_prefix" {
  command = plan

  variables {
    name_prefix = "Test-Dev"
  }

  expect_failures = [var.name_prefix]
}
