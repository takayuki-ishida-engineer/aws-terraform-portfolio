locals {
  public_enabled = length(var.public_subnets) > 0
  subnet_cidrs = concat(
    [for subnet in var.private_subnets : subnet.cidr_block],
    [for subnet in var.public_subnets : subnet.cidr_block]
  )
  # Syntax errors belong to variable validation, rather than duplicate preconditions.
  valid_ipv4_cidrs = alltrue([for cidr in concat([var.vpc_cidr], local.subnet_cidrs) : can(cidrnetmask(cidr))])
}

resource "aws_vpc" "this" {
  cidr_block                       = var.vpc_cidr
  enable_dns_support               = true
  enable_dns_hostnames             = true
  assign_generated_ipv6_cidr_block = false
  tags                             = merge(var.tags, { Name = "${var.name_prefix}-vpc" })

  lifecycle {
    precondition {
      condition     = local.per_az || (var.private_routing.nat == null && length(var.gateway_endpoints) == 0)
      error_message = "NAT/endpoints require explicit per_az routing; legacy_shared must remain unchanged."
    }
    precondition {
      condition     = !local.per_az || var.expected_scope != null
      error_message = "per_az requires expected_scope; root must also restrict the provider account and Region."
    }
    precondition {
      condition     = !local.per_az || try(alltrue([for subnet in concat(values(var.private_subnets), values(var.public_subnets)) : can(regex("^${var.expected_scope.region}[a-z]$", subnet.availability_zone))]), false)
      error_message = "Every opted-in subnet AZ must match the explicit expected Region; enabled zones still require external verification."
    }
    precondition {
      condition = (alltrue([for az, key in local.nat_subnet_keys : try(
        contains(local.private_azs, az) && var.public_subnets[key].availability_zone == az, false)]) &&
      length(distinct(values(local.nat_subnet_keys))) == length(local.nat_subnet_keys))
      error_message = "Each NAT AZ must be a private AZ with one distinct, existing same-AZ public subnet; this also requires the public IGW path."
    }
    precondition {
      condition = (alltrue([for az, target in local.private_nat_azs : contains(local.private_azs, az) && contains(keys(local.nat_subnet_keys), target)]) &&
      toset(values(local.private_nat_azs)) == toset(keys(local.nat_subnet_keys)))
      error_message = "NAT routes must map existing private AZs to declared NAT AZs with no unused gateways or missing targets."
    }
    precondition {
      condition     = alltrue([for endpoint in var.gateway_endpoints : try(length(setsubtract(endpoint.private_route_table_azs, local.private_azs)) == 0, false)])
      error_message = "Gateway endpoints may associate only explicitly selected existing private AZ tables."
    }
    precondition {
      condition = alltrue([for endpoint in var.gateway_endpoints : try(alltrue([
        for statement in jsondecode(endpoint.policy_json).Statement : alltrue([
          for principal in try(tolist(statement.Principal.AWS), [statement.Principal.AWS]) : split(":", principal)[4] == var.expected_scope.account_id
        ])
      ]), false)])
      error_message = "Endpoint principals must belong to the explicit expected account; cross-account policy needs separate review."
    }
    postcondition {
      condition     = !local.per_az || try(startswith(self.arn, "arn:${var.expected_scope.partition}:ec2:${var.expected_scope.region}:${var.expected_scope.account_id}:vpc/") && endswith(self.arn, "/${self.id}"), false)
      error_message = "Actual VPC ARN/ID must match expected account, Region and partition; caller metadata is not authentication."
    }
    precondition {
      # Project each subnet address onto the VPC prefix and compare network bases.
      condition = !local.valid_ipv4_cidrs || try(alltrue([
        for cidr in local.subnet_cidrs :
        tonumber(split("/", cidr)[1]) >= tonumber(split("/", var.vpc_cidr)[1]) &&
        cidrhost("${split("/", cidr)[0]}/${split("/", var.vpc_cidr)[1]}", 0) == cidrhost(var.vpc_cidr, 0)
      ]), false)
      error_message = "Every subnet CIDR must be fully contained within vpc_cidr."
    }

    precondition {
      # Two CIDRs overlap iff their network bases match at the shorter prefix.
      condition = !local.valid_ipv4_cidrs || try(alltrue(flatten([
        for i, first in local.subnet_cidrs : [
          for j, second in local.subnet_cidrs : i >= j ||
          cidrhost("${split("/", first)[0]}/${min(tonumber(split("/", first)[1]), tonumber(split("/", second)[1]))}", 0) !=
          cidrhost("${split("/", second)[0]}/${min(tonumber(split("/", first)[1]), tonumber(split("/", second)[1]))}", 0)
        ]
      ])), false)
      error_message = "Subnet CIDRs must not overlap, including across private and public maps."
    }
  }
}

resource "aws_subnet" "private" {
  for_each = var.private_subnets

  vpc_id                          = aws_vpc.this.id
  cidr_block                      = each.value.cidr_block
  availability_zone               = each.value.availability_zone
  map_public_ip_on_launch         = false
  assign_ipv6_address_on_creation = false
  tags                            = merge(var.tags, { Name = "${var.name_prefix}-private-${each.key}" })
}

resource "aws_subnet" "public" {
  for_each = var.public_subnets

  vpc_id                          = aws_vpc.this.id
  cidr_block                      = each.value.cidr_block
  availability_zone               = each.value.availability_zone
  map_public_ip_on_launch         = false
  assign_ipv6_address_on_creation = false
  tags                            = merge(var.tags, { Name = "${var.name_prefix}-public-${each.key}" })
}

resource "aws_internet_gateway" "this" {
  count = local.public_enabled ? 1 : 0

  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  route  = []
  tags   = merge(var.tags, { Name = "${var.name_prefix}-private-rt" })
}

resource "aws_route_table" "public" {
  count = local.public_enabled ? 1 : 0

  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this[0].id
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-public-rt" })
}

resource "aws_route_table_association" "private" {
  for_each = var.private_subnets

  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = local.per_az ? aws_route_table.private_by_az[var.private_subnets[each.key].availability_zone].id : aws_route_table.private.id

  depends_on = [aws_route.private_nat, aws_vpc_endpoint.gateway]
}

resource "aws_route_table_association" "public" {
  for_each = var.public_subnets

  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public[0].id
}
