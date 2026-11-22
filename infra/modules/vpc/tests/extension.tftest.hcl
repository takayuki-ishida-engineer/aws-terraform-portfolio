mock_provider "aws" {
  override_during = plan
}

override_resource {
  target          = aws_vpc.this
  override_during = plan
  values          = { "id" : "vpc-v2-mock", "arn" : "arn:aws:ec2:ca-central-1:000000000000:vpc/vpc-v2-mock" }
}
override_resource {
  target          = aws_route_table.private
  override_during = plan
  values          = { "id" : "rtb-legacy" }
}
override_resource {
  target          = aws_route_table.public[0]
  override_during = plan
  values          = { "id" : "rtb-public" }
}
override_resource {
  target          = aws_internet_gateway.this[0]
  override_during = plan
  values          = { "id" : "igw-mock" }
}
override_resource {
  target          = aws_route_table.private_by_az["ca-central-1a"]
  override_during = plan
  values          = { "id" : "rtb-a" }
}
override_resource {
  target          = aws_nat_gateway.this["ca-central-1a"]
  override_during = plan
  values          = { "id" : "nat-a" }
}
override_resource {
  target          = aws_eip.nat["ca-central-1a"]
  override_during = plan
  values          = { "id" : "eipalloc-a", "public_ip" : "192.0.2.10" }
}
override_resource {
  target          = aws_route_table.private_by_az["ca-central-1b"]
  override_during = plan
  values          = { "id" : "rtb-b" }
}
override_resource {
  target          = aws_nat_gateway.this["ca-central-1b"]
  override_during = plan
  values          = { "id" : "nat-b" }
}
override_resource {
  target          = aws_eip.nat["ca-central-1b"]
  override_during = plan
  values          = { "id" : "eipalloc-b", "public_ip" : "192.0.2.11" }
}
override_resource {
  target          = aws_subnet.private["app-a"]
  override_during = plan
  values          = { "id" : "subnet-app-a" }
}
override_resource {
  target          = aws_subnet.private["app-b"]
  override_during = plan
  values          = { "id" : "subnet-app-b" }
}
override_resource {
  target          = aws_subnet.private["app-extra"]
  override_during = plan
  values          = { "id" : "subnet-app-extra" }
}
override_resource {
  target          = aws_subnet.public["public-a"]
  override_during = plan
  values          = { "id" : "subnet-public-a" }
}
override_resource {
  target          = aws_subnet.public["public-b"]
  override_during = plan
  values          = { "id" : "subnet-public-b" }
}
override_resource {
  target          = aws_vpc_endpoint.gateway["s3"]
  override_during = plan
  values          = { "id" : "vpce-s3" }
}

override_resource {
  target          = aws_security_group.endpoints[0]
  override_during = plan
  values          = { "id" : "sg-vpce" }
}
override_resource {
  target          = aws_vpc_security_group_ingress_rule.endpoints_https[0]
  override_during = plan
  values          = { "id" : "sgr-vpce-https" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["ec2"]
  override_during = plan
  values          = { "id" : "vpce-ec2" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["ecr.api"]
  override_during = plan
  values          = { "id" : "vpce-ecr-api" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["ecr.dkr"]
  override_during = plan
  values          = { "id" : "vpce-ecr-dkr" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["logs"]
  override_during = plan
  values          = { "id" : "vpce-logs" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["sts"]
  override_during = plan
  values          = { "id" : "vpce-sts" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["ec2messages"]
  override_during = plan
  values          = { "id" : "vpce-ec2messages" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["elasticloadbalancing"]
  override_during = plan
  values          = { "id" : "vpce-elasticloadbalancing" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["ssm"]
  override_during = plan
  values          = { "id" : "vpce-ssm" }
}
override_resource {
  target          = aws_vpc_endpoint.interface["ssmmessages"]
  override_during = plan
  values          = { "id" : "vpce-ssmmessages" }
}

run "per_az_isolated" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "dev_one_nat" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "multi_az_nat" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a", "ca-central-1b" : "public-b" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1b" } } }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "dev_explicit_shared_nat" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "s3_selected_table" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "s3_isolated_both_tables" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1b", "ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "same_az_multiple_subnets" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" }, "app-extra" : { "cidr_block" : "10.40.3.0/24", "availability_zone" : "ca-central-1a" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a", "ca-central-1b" : "public-b" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1b" } } }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "legacy_public_unchanged" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = null
    private_routing   = { "mode" : "legacy_shared", "nat" : null }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "legacy_private_unchanged" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = {}
    expected_scope    = null
    private_routing   = { "mode" : "legacy_shared", "nat" : null }
    gateway_endpoints = {}
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}

run "invalid_mode" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "ambiguous", "nat" : null }
    gateway_endpoints = {}
  }
  expect_failures = [var.private_routing]
}

run "legacy_nat_rejected" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "legacy_shared", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "legacy_endpoint_rejected" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "legacy_shared", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1b", "ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [aws_vpc.this]
}

run "missing_scope" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = null
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "wrong_region" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  expect_failures = [var.expected_scope]
}

run "wrong_account_syntax" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "invalid" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  expect_failures = [var.expected_scope]
}

run "wrong_subnet_region" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "us-east-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "missing_public_path" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = {}
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "missing_public_key" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "missing" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "wrong_public_az" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-b" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "duplicate_public_subnet" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a", "ca-central-1b" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1b" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "missing_nat_target" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1b" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "unknown_private_az" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1c" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "unused_nat" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a", "ca-central-1b" : "public-b" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = {}
  }
  expect_failures = [aws_vpc.this]
}

run "empty_nat_maps" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : {}, "nat_az_by_private_az" : {} } }
    gateway_endpoints = {}
  }
  expect_failures = [var.private_routing]
}

run "endpoint_wrong_service" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "dynamodb" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_unknown_table" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1c"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [aws_vpc.this]
}

run "endpoint_empty_tables" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : [], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

# AWS requires Principal="*"; this negative deliberately omits its role Condition.
run "endpoint_wildcard_principal" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"]}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_foreign_principal" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::111111111111:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [aws_vpc.this]
}

run "endpoint_admin_actions" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:*\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_write_action" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:PutObject\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_world_resource" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_wrong_action_scope" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_notaction" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"NotAction\":[\"s3:DeleteObject\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_malformed_json" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{broken" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "wrong_actual_account" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  override_resource {
    target          = aws_vpc.this
    override_during = plan
    values          = { "id" : "vpc-v2-mock", "arn" : "arn:aws:ec2:ca-central-1:111111111111:vpc/vpc-v2-mock" }
  }
  expect_failures = [aws_vpc.this]
}

run "wrong_actual_region" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
  override_resource {
    target          = aws_vpc.this
    override_during = plan
    values          = { "id" : "vpc-v2-mock", "arn" : "arn:aws:ec2:us-east-1:000000000000:vpc/vpc-v2-mock" }
  }
  expect_failures = [aws_vpc.this]
}

run "endpoint_statement_not_array" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":{\"zero\":{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}}}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "per_az_no_public" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = {}
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = {}
  }
}

run "s3_bucket_and_object_policy" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::test-network-artifacts/approved/*\",\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}},{\"Sid\":\"ReadBucketMetadata\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:ListBucket\",\"s3:GetBucketLocation\"],\"Resource\":\"arn:aws:s3:::test-network-artifacts\",\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":[\"arn:aws:iam::000000000000:role/test-network-reader\"]}}}]}" } }
  }
}

run "s3_multiple_approved_roles" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":[\"arn:aws:iam::000000000000:role/test-network-reader\",\"arn:aws:iam::000000000000:role/team/test-second-reader\"]}}}]}" } }
  }
  assert {
    condition     = jsondecode(aws_vpc_endpoint.gateway["s3"].policy).Statement[0].Principal == "*" && length(jsondecode(aws_vpc_endpoint.gateway["s3"].policy).Statement[0].Condition.ArnEquals["aws:PrincipalArn"]) == 2
    error_message = "Gateway Principal must be star with two explicitly approved role ARN conditions."
  }
}

run "endpoint_empty_condition" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_empty_arn_equals" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_empty_role_string" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_empty_role_list" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":[]}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_null_condition" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":null}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_wildcard_role" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-*\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_question_role" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-?\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_mixed_account_roles" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":[\"arn:aws:iam::000000000000:role/test-network-reader\",\"arn:aws:iam::111111111111:role/test-network-reader\"]}}}]}" } }
  }
  expect_failures = [aws_vpc.this]
}

run "endpoint_arnlike_operator" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnLike\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_ifexists_operator" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEqualsIfExists\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_negated_operator" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnNotEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_set_operator" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ForAllValues:ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_wrong_condition_key" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalAccount\":\"000000000000\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_extra_condition_key" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\",\"aws:PrincipalAccount\":\"000000000000\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_extra_condition_operator" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"},\"Bool\":{\"aws:SecureTransport\":\"true\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_sts_session_role" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:sts::000000000000:assumed-role/test-network-reader/test-session\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_iam_user_condition" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:user/test-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}

run "endpoint_legacy_principal_object" {
  command = plan
  variables {
    name_prefix       = "test-network"
    vpc_cidr          = "10.40.0.0/16"
    private_subnets   = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets    = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope    = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing   = { "mode" : "per_az", "nat" : null }
    gateway_endpoints = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":{\"AWS\":\"arn:aws:iam::000000000000:role/test-network-reader\"},\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
  }
  expect_failures = [var.gateway_endpoints]
}
run "interface_endpoints_active_az" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    gateway_endpoints   = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
    interface_endpoints = { "services" : ["ec2", "ecr.api", "ecr.dkr", "logs", "sts"], "subnet_keys" : ["app-a"] }
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}
run "interface_endpoints_two_azs" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : null }
    interface_endpoints = { "services" : ["sts"], "subnet_keys" : ["app-a", "app-b"] }
  }
  assert {
    condition     = output.routing_mode == var.private_routing.mode && output.interface_version == 1
    error_message = "The selected mode and candidate interface version must be exposed."
  }
}
# Finding F21: the reviewed list accepts elasticloadbalancing next to the other
# eight services. This mock plan checks the configuration only; it does not prove
# that the AWS Load Balancer Controller can reach the ELB API.
run "interface_endpoints_elbv2" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    interface_endpoints = { "services" : ["ec2", "ec2messages", "ecr.api", "ecr.dkr", "elasticloadbalancing", "logs", "ssm", "ssmmessages", "sts"], "subnet_keys" : ["app-a"] }
  }
  assert {
    condition     = length(output.endpoint_ids.interface) == 9 && output.endpoint_ids.interface["elasticloadbalancing"] == "vpce-elasticloadbalancing"
    error_message = "All nine reviewed interface endpoints, including elasticloadbalancing, must be created."
  }
}
run "interface_legacy_rejected" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "legacy_shared", "nat" : null }
    interface_endpoints = { "services" : ["sts"], "subnet_keys" : ["app-a"] }
  }
  expect_failures = [aws_vpc.this]
}
run "interface_unknown_service" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    interface_endpoints = { "services" : ["s3"], "subnet_keys" : ["app-a"] }
  }
  expect_failures = [var.interface_endpoints]
}
run "interface_unreviewed_elb_variant" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    interface_endpoints = { "services" : ["elasticloadbalancing", "elasticloadbalancingv2"], "subnet_keys" : ["app-a"] }
  }
  expect_failures = [var.interface_endpoints]
}
run "interface_empty_subnets" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    interface_endpoints = { "services" : ["sts"], "subnet_keys" : [] }
  }
  expect_failures = [var.interface_endpoints]
}
run "interface_unknown_subnet" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } } }
    interface_endpoints = { "services" : ["sts"], "subnet_keys" : ["app-c"] }
  }
  expect_failures = [aws_vpc.this]
}
run "interface_same_az_subnets" {
  command = plan
  variables {
    name_prefix         = "test-network"
    vpc_cidr            = "10.40.0.0/16"
    private_subnets     = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" }, "app-extra" : { "cidr_block" : "10.40.3.0/24", "availability_zone" : "ca-central-1a" } }
    public_subnets      = { "public-a" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public-b" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    expected_scope      = { "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    private_routing     = { "mode" : "per_az", "nat" : { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public-a", "ca-central-1b" : "public-b" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1b" } } }
    interface_endpoints = { "services" : ["sts"], "subnet_keys" : ["app-a", "app-extra"] }
  }
  expect_failures = [aws_vpc.this]
}
