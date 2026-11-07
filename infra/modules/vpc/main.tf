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
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "public" {
  for_each = var.public_subnets

  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public[0].id
}
