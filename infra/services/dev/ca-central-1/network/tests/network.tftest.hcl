mock_provider "aws" {
  override_during = plan
}

override_resource {
  target          = module.network.aws_vpc.this
  override_during = plan
  values          = { "id" : "vpc-v2-mock", "arn" : "arn:aws:ec2:ca-central-1:000000000000:vpc/vpc-v2-mock" }
}
override_resource {
  target          = module.network.aws_route_table.private
  override_during = plan
  values          = { "id" : "rtb-legacy" }
}
override_resource {
  target          = module.network.aws_route_table.public[0]
  override_during = plan
  values          = { "id" : "rtb-public" }
}
override_resource {
  target          = module.network.aws_internet_gateway.this[0]
  override_during = plan
  values          = { "id" : "igw-mock" }
}
override_resource {
  target          = module.network.aws_route_table.private_by_az["ca-central-1a"]
  override_during = plan
  values          = { "id" : "rtb-a" }
}
override_resource {
  target          = module.network.aws_nat_gateway.this["ca-central-1a"]
  override_during = plan
  values          = { "id" : "nat-a" }
}
override_resource {
  target          = module.network.aws_eip.nat["ca-central-1a"]
  override_during = plan
  values          = { "id" : "eipalloc-a", "public_ip" : "192.0.2.10" }
}
override_resource {
  target          = module.network.aws_route_table.private_by_az["ca-central-1b"]
  override_during = plan
  values          = { "id" : "rtb-b" }
}
override_resource {
  target          = module.network.aws_nat_gateway.this["ca-central-1b"]
  override_during = plan
  values          = { "id" : "nat-b" }
}
override_resource {
  target          = module.network.aws_eip.nat["ca-central-1b"]
  override_during = plan
  values          = { "id" : "eipalloc-b", "public_ip" : "192.0.2.11" }
}
override_resource {
  target          = module.network.aws_subnet.private["private1"]
  override_during = plan
  values          = { "id" : "subnet-app-a" }
}
override_resource {
  target          = module.network.aws_subnet.private["private2"]
  override_during = plan
  values          = { "id" : "subnet-app-b" }
}
override_resource {
  target          = module.network.aws_subnet.private["app-extra"]
  override_during = plan
  values          = { "id" : "subnet-app-extra" }
}
override_resource {
  target          = module.network.aws_subnet.public["public1"]
  override_during = plan
  values          = { "id" : "subnet-public-a" }
}
override_resource {
  target          = module.network.aws_subnet.public["public2"]
  override_during = plan
  values          = { "id" : "subnet-public-b" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.gateway["s3"]
  override_during = plan
  values          = { "id" : "vpce-s3" }
}

run "dev_network" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  assert {
    condition     = output.network.scope.environment == "dev" && output.network.private_route_table_id == null && output.network.routing_mode == "per_az"
    error_message = "Root must expose DEV scope and the explicit V1-C01 candidate contract."
  }
  assert {
    condition     = local.name_prefix == "test-dev" && local.default_tags == { project = "test", env = "dev", managed = "terraform" }
    error_message = "Root must derive <project>-<env> names and set project, env and managed only through provider default_tags."
  }
}

run "dev_cross_az_explicit" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1a" } }
  }
  assert {
    condition     = output.network.scope.environment == "dev" && output.network.private_route_table_id == null && output.network.routing_mode == "per_az"
    error_message = "Root must expose DEV scope and the explicit V1-C01 candidate contract."
  }
}

run "dev_network_s3" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  assert {
    condition     = output.network.scope.environment == "dev" && output.network.private_route_table_id == null && output.network.routing_mode == "per_az"
    error_message = "Root must expose DEV scope and the explicit V1-C01 candidate contract."
  }
}

run "invalid_account" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "invalid"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  expect_failures = [var.aws_account_id]
}

run "invalid_active_az" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1c"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  expect_failures = [var.active_workload_az]
}

run "multiple_dev_nats" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1", "ca-central-1b" : "public2" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a", "ca-central-1b" : "ca-central-1b" } }
  }
  expect_failures = [var.nat]
}

run "missing_active_route" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1b" : "ca-central-1a" } }
  }
  expect_failures = [var.nat]
}

run "missing_public" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = {}
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  expect_failures = [var.public_subnets]
}

run "invalid_root_cidr" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "bad"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  expect_failures = [var.vpc_cidr]
}

run "dev_network_alternate_computed_ids" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = { "s3" : { "private_route_table_azs" : ["ca-central-1a"], "policy_json" : "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadApprovedObjects\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":[\"s3:GetObject\",\"s3:GetObjectVersion\"],\"Resource\":[\"arn:aws:s3:::test-network-artifacts/approved/*\"],\"Condition\":{\"ArnEquals\":{\"aws:PrincipalArn\":\"arn:aws:iam::000000000000:role/test-network-reader\"}}}]}" } }
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  override_resource {
    target          = module.network.aws_vpc.this
    override_during = plan
    values          = { "id" : "vpc-alternate", "arn" : "arn:aws:ec2:ca-central-1:000000000000:vpc/vpc-alternate" }
  }
  override_resource {
    target          = module.network.aws_route_table.private
    override_during = plan
    values          = { "id" : "rtb-alternate-legacy" }
  }
  override_resource {
    target          = module.network.aws_route_table.public[0]
    override_during = plan
    values          = { "id" : "rtb-alternate-public" }
  }
  override_resource {
    target          = module.network.aws_internet_gateway.this[0]
    override_during = plan
    values          = { "id" : "igw-alternate" }
  }
  override_resource {
    target          = module.network.aws_nat_gateway.this["ca-central-1a"]
    override_during = plan
    values          = { "id" : "nat-alternate-a" }
  }
  override_resource {
    target          = module.network.aws_eip.nat["ca-central-1a"]
    override_during = plan
    values          = { "id" : "eipalloc-alternate-a", "public_ip" : "192.0.2.30" }
  }
  override_resource {
    target          = module.network.aws_vpc_endpoint.gateway["s3"]
    override_during = plan
    values          = { "id" : "vpce-alternate-s3" }
  }
  override_resource {
    target          = module.network.aws_route_table.private_by_az["ca-central-1a"]
    override_during = plan
    values          = { "id" : "rtb-alternate-a" }
  }
  override_resource {
    target          = module.network.aws_route_table.private_by_az["ca-central-1b"]
    override_during = plan
    values          = { "id" : "rtb-alternate-b" }
  }
  override_resource {
    target          = module.network.aws_subnet.private["private1"]
    override_during = plan
    values          = { "id" : "subnet-alternate-app-a" }
  }
  override_resource {
    target          = module.network.aws_subnet.private["private2"]
    override_during = plan
    values          = { "id" : "subnet-alternate-app-b" }
  }
  override_resource {
    target          = module.network.aws_subnet.public["public1"]
    override_during = plan
    values          = { "id" : "subnet-alternate-public-a" }
  }
  override_resource {
    target          = module.network.aws_subnet.public["public2"]
    override_during = plan
    values          = { "id" : "subnet-alternate-public-b" }
  }
}

run "invalid_project" {
  command = plan
  variables {
    project            = "aws-portal"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  expect_failures = [var.project]
}

run "invalid_subnet_keys" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "app-a" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "app-b" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
  }
  expect_failures = [var.private_subnets]
}

run "reserved_tag_keys" {
  command = plan
  variables {
    project            = "test"
    vpc_cidr           = "10.40.0.0/16"
    private_subnets    = { "private1" : { "cidr_block" : "10.40.1.0/24", "availability_zone" : "ca-central-1a" }, "private2" : { "cidr_block" : "10.40.2.0/24", "availability_zone" : "ca-central-1b" } }
    public_subnets     = { "public1" : { "cidr_block" : "10.40.10.0/24", "availability_zone" : "ca-central-1a" }, "public2" : { "cidr_block" : "10.40.11.0/24", "availability_zone" : "ca-central-1b" } }
    gateway_endpoints  = {}
    aws_account_id     = "000000000000"
    active_workload_az = "ca-central-1a"
    nat                = { "public_subnet_key_by_nat_az" : { "ca-central-1a" : "public1" }, "nat_az_by_private_az" : { "ca-central-1a" : "ca-central-1a" } }
    tags               = { "service" : "network" }
  }
  expect_failures = [var.tags]
}
