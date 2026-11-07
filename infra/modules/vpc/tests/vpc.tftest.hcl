mock_provider "aws" {
  # Resolve computed IDs during mocked plans so associations can be checked.
  override_during = plan
}

override_resource {
  target          = aws_vpc.this
  override_during = plan
  values          = { id = "vpc-mock" }
}

override_resource {
  target          = aws_route_table.private
  override_during = plan
  values          = { id = "rtb-private-mock" }
}

variables {
  name_prefix = "test-network"
  vpc_cidr    = "10.40.0.0/16"
  private_subnets = {
    app-a = { cidr_block = "10.40.1.0/24", availability_zone = "ca-central-1a" }
  }
}

run "private_only" {
  command = plan

  override_resource {
    target          = aws_subnet.private["app-a"]
    override_during = plan
    values          = { id = "subnet-private-a-mock" }
  }

  variables {
    tags = { Team = "platform", Name = "caller-name-must-not-win" }
  }

  assert {
    condition     = aws_vpc.this.cidr_block == "10.40.0.0/16" && aws_vpc.this.enable_dns_support && aws_vpc.this.enable_dns_hostnames && !aws_vpc.this.assign_generated_ipv6_cidr_block
    error_message = "The VPC must use the supplied IPv4 CIDR, enable DNS, and not allocate IPv6."
  }

  assert {
    condition     = length(aws_subnet.private) == 1 && length(aws_subnet.public) == 0 && length(aws_internet_gateway.this) == 0 && length(aws_route_table.public) == 0 && length(aws_route_table_association.public) == 0
    error_message = "Default private-only mode must omit all optional public infrastructure."
  }

  assert {
    condition     = length(aws_route_table.private.route) == 0 && aws_route_table_association.private["app-a"].route_table_id == aws_route_table.private.id && aws_route_table_association.private["app-a"].subnet_id == aws_subnet.private["app-a"].id
    error_message = "Private subnets must use the explicit shared private route table without configured internet routes."
  }

  assert {
    condition     = !aws_subnet.private["app-a"].map_public_ip_on_launch && !aws_subnet.private["app-a"].assign_ipv6_address_on_creation && aws_subnet.private["app-a"].cidr_block == "10.40.1.0/24" && aws_subnet.private["app-a"].availability_zone == "ca-central-1a"
    error_message = "Private subnet addressing must match the caller while public IPv4 and IPv6 assignment remain disabled."
  }

  assert {
    condition     = aws_vpc.this.tags.Name == "test-network-vpc" && aws_vpc.this.tags.Team == "platform" && aws_subnet.private["app-a"].tags.Name == "test-network-private-app-a" && aws_subnet.private["app-a"].tags.Team == "platform" && aws_route_table.private.tags.Name == "test-network-private-rt"
    error_message = "Caller tags must survive, but module-owned Name tags must take precedence."
  }

  assert {
    condition     = output.vpc_id == aws_vpc.this.id && output.vpc_cidr == "10.40.0.0/16" && output.private_subnet_ids["app-a"] == aws_subnet.private["app-a"].id && output.private_route_table_id == aws_route_table.private.id && length(output.public_subnet_ids) == 0 && output.public_route_table_id == null && output.internet_gateway_id == null
    error_message = "Outputs must expose real resource references and null/empty optional values."
  }
}

run "public_and_private" {
  command = plan

  override_resource {
    target          = aws_subnet.private["app-a"]
    override_during = plan
    values          = { id = "subnet-private-a-mock" }
  }

  override_resource {
    target          = aws_subnet.private["app-b"]
    override_during = plan
    values          = { id = "subnet-private-b-mock" }
  }

  override_resource {
    target          = aws_subnet.public["web-a"]
    override_during = plan
    values          = { id = "subnet-public-a-mock" }
  }

  override_resource {
    target          = aws_subnet.public["web-b"]
    override_during = plan
    values          = { id = "subnet-public-b-mock" }
  }

  override_resource {
    target          = aws_internet_gateway.this[0]
    override_during = plan
    values          = { id = "igw-mock" }
  }

  override_resource {
    target          = aws_route_table.public[0]
    override_during = plan
    values          = { id = "rtb-public-mock" }
  }

  variables {
    private_subnets = {
      app-a = { cidr_block = "10.40.1.0/24", availability_zone = "ca-central-1a" }
      app-b = { cidr_block = "10.40.2.0/24", availability_zone = "ca-central-1b" }
    }
    public_subnets = {
      web-a = { cidr_block = "10.40.10.0/24", availability_zone = "ca-central-1a" }
      web-b = { cidr_block = "10.40.11.0/24", availability_zone = "ca-central-1b" }
    }
    tags = { Team = "platform", Name = "ignored" }
  }

  assert {
    condition     = length(aws_subnet.private) == 2 && length(aws_subnet.public) == 2 && length(aws_internet_gateway.this) == 1 && length(aws_route_table.public) == 1
    error_message = "Explicit public subnets must create exactly one shared public route table and Internet Gateway."
  }

  assert {
    condition     = length(aws_route_table.public[0].route) == 1 && alltrue([for route in aws_route_table.public[0].route : route.cidr_block == "0.0.0.0/0" && route.gateway_id == aws_internet_gateway.this[0].id]) && length(aws_route_table.private.route) == 0
    error_message = "Only the public table may contain the IPv4 default route to the Internet Gateway."
  }

  assert {
    condition     = alltrue([for key, subnet in aws_subnet.private : subnet.cidr_block == var.private_subnets[key].cidr_block && subnet.availability_zone == var.private_subnets[key].availability_zone && subnet.vpc_id == aws_vpc.this.id && !subnet.map_public_ip_on_launch && !subnet.assign_ipv6_address_on_creation]) && alltrue([for key, subnet in aws_subnet.public : subnet.cidr_block == var.public_subnets[key].cidr_block && subnet.availability_zone == var.public_subnets[key].availability_zone && subnet.vpc_id == aws_vpc.this.id && !subnet.map_public_ip_on_launch && !subnet.assign_ipv6_address_on_creation])
    error_message = "Subnets must preserve their keyed CIDR/AZ mappings, VPC membership, and fixed IP assignment settings."
  }

  assert {
    condition     = length(aws_route_table_association.private) == 2 && alltrue([for key, association in aws_route_table_association.private : association.subnet_id == aws_subnet.private[key].id && association.route_table_id == aws_route_table.private.id]) && length(aws_route_table_association.public) == 2 && alltrue([for key, association in aws_route_table_association.public : association.subnet_id == aws_subnet.public[key].id && association.route_table_id == aws_route_table.public[0].id])
    error_message = "Every subnet association must target its own subnet and the intended private/public route table."
  }

  assert {
    condition     = aws_internet_gateway.this[0].vpc_id == aws_vpc.this.id && aws_internet_gateway.this[0].tags.Name == "test-network-igw" && aws_route_table.public[0].tags.Name == "test-network-public-rt" && alltrue([for key, subnet in aws_subnet.public : subnet.tags.Name == "test-network-public-${key}" && subnet.tags.Team == "platform"])
    error_message = "Public resources must use consistent naming and caller tags without allowing Name overrides."
  }

  assert {
    condition     = output.public_route_table_id == aws_route_table.public[0].id && output.internet_gateway_id == aws_internet_gateway.this[0].id && alltrue([for key, id in output.public_subnet_ids : id == aws_subnet.public[key].id])
    error_message = "Optional output IDs must reference the actual mocked public resources."
  }
}

run "stable_keys_and_defaults" {
  command = plan

  override_resource {
    target          = aws_subnet.private["zulu"]
    override_during = plan
    values          = { id = "subnet-zulu-mock" }
  }

  override_resource {
    target          = aws_subnet.private["alpha"]
    override_during = plan
    values          = { id = "subnet-alpha-mock" }
  }

  variables {
    # Deliberately reverse declaration and AZ order: addresses still use keys.
    private_subnets = {
      zulu  = { cidr_block = "10.40.3.0/24", availability_zone = "ca-central-1b" }
      alpha = { cidr_block = "10.40.4.0/24", availability_zone = "ca-central-1a" }
    }
  }

  assert {
    condition     = keys(aws_subnet.private) == ["alpha", "zulu"] && keys(aws_route_table_association.private) == ["alpha", "zulu"] && keys(output.private_subnet_ids) == ["alpha", "zulu"] && aws_subnet.private["zulu"].cidr_block == "10.40.3.0/24" && aws_subnet.private["alpha"].cidr_block == "10.40.4.0/24"
    error_message = "Subnets, associations and outputs must use stable caller map keys rather than declaration or AZ order."
  }

  assert {
    condition     = length(aws_subnet.public) == 0 && length(aws_route_table.public) == 0 && length(aws_internet_gateway.this) == 0 && length(aws_route_table.private.route) == 0 && alltrue([for subnet in aws_subnet.private : !subnet.map_public_ip_on_launch && !subnet.assign_ipv6_address_on_creation]) && aws_vpc.this.tags == tomap({ Name = "test-network-vpc" })
    error_message = "Default empty public_subnets/tags must preserve private-only networking and fixed security settings."
  }
}

run "invalid_name_prefix" {
  command = plan
  variables {
    name_prefix = " invalid/name "
  }
  expect_failures = [var.name_prefix]
}

run "invalid_vpc_cidr" {
  command = plan
  variables {
    vpc_cidr = "not-a-cidr"
  }
  expect_failures = [var.vpc_cidr]
}

run "ipv6_vpc_rejected" {
  command = plan
  variables {
    vpc_cidr = "2001:db8::/56"
  }
  expect_failures = [var.vpc_cidr]
}

run "invalid_vpc_prefix" {
  command = plan
  variables {
    vpc_cidr = "10.40.0.0/15"
  }
  expect_failures = [var.vpc_cidr]
}

run "empty_private_subnets" {
  command = plan
  variables {
    private_subnets = {}
  }
  expect_failures = [var.private_subnets]
}

run "invalid_private_cidr" {
  command = plan
  variables {
    private_subnets = {
      app-a = { cidr_block = "invalid", availability_zone = "ca-central-1a" }
    }
  }
  expect_failures = [var.private_subnets]
}

run "invalid_public_cidr" {
  command = plan
  variables {
    public_subnets = {
      web-a = { cidr_block = "invalid", availability_zone = "ca-central-1a" }
    }
  }
  expect_failures = [var.public_subnets]
}

run "empty_private_availability_zone" {
  command = plan
  variables {
    private_subnets = {
      app-a = { cidr_block = "10.40.1.0/24", availability_zone = "" }
    }
  }
  expect_failures = [var.private_subnets]
}

run "invalid_public_availability_zone" {
  command = plan
  variables {
    public_subnets = {
      web-a = { cidr_block = "10.40.10.0/24", availability_zone = "not-an-az" }
    }
  }
  expect_failures = [var.public_subnets]
}

run "empty_private_key" {
  command = plan
  variables {
    private_subnets = {
      " " = { cidr_block = "10.40.1.0/24", availability_zone = "ca-central-1a" }
    }
  }
  expect_failures = [var.private_subnets]
}

run "subnet_outside_vpc" {
  command = plan
  variables {
    private_subnets = {
      app-a = { cidr_block = "10.41.1.0/24", availability_zone = "ca-central-1a" }
    }
  }
  expect_failures = [aws_vpc.this]
}

run "subnet_broader_than_vpc" {
  command = plan
  variables {
    vpc_cidr = "10.40.1.0/24"
    private_subnets = {
      app-a = { cidr_block = "10.40.0.0/16", availability_zone = "ca-central-1a" }
    }
  }
  expect_failures = [aws_vpc.this]
}

run "overlapping_private_and_public" {
  command = plan
  variables {
    public_subnets = {
      web-a = { cidr_block = "10.40.1.0/25", availability_zone = "ca-central-1b" }
    }
  }
  expect_failures = [aws_vpc.this]
}
