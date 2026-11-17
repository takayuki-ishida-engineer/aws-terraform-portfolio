locals {
  per_az          = var.private_routing.mode == "per_az"
  private_azs     = toset([for subnet in var.private_subnets : subnet.availability_zone])
  nat_subnet_keys = try(var.private_routing.nat.public_subnet_key_by_nat_az, {})
  private_nat_azs = try(var.private_routing.nat.nat_az_by_private_az, {})
  # Filter invalid references so the explicit preconditions report the cause.
  nat_public_subnets = { for az, key in local.nat_subnet_keys : az => var.public_subnets[key] if contains(keys(var.public_subnets), key) }
  nat_routes         = { for az, target in local.private_nat_azs : az => target if local.per_az && contains(local.private_azs, az) && contains(keys(local.nat_public_subnets), target) }
  # A per-AZ private table takes the tier key of the first private subnet in its AZ, for example private1.
  private_table_purpose = { for az in local.private_azs : az => sort([for key, subnet in var.private_subnets : key if subnet.availability_zone == az])[0] }
}

resource "aws_route_table" "private_by_az" {
  for_each = local.per_az ? local.private_azs : toset([])
  vpc_id   = aws_vpc.this.id
  # Intentionally omit inline routes: aws_route owns ordinary NAT defaults.
  tags = merge(var.tags, { Name = "${var.name_prefix}-${substr(each.key, length(each.key) - 1, 1)}-rtb-${local.private_table_purpose[each.key]}", service = "rtb" })
}

resource "aws_eip" "nat" {
  for_each = local.per_az ? local.nat_public_subnets : {}
  domain   = "vpc"
  tags     = merge(var.tags, { Name = "${var.name_prefix}-${substr(each.key, length(each.key) - 1, 1)}-eip-nat", service = "eip" })
}

resource "aws_nat_gateway" "this" {
  for_each          = local.per_az ? local.nat_public_subnets : {}
  availability_mode = "zonal"
  connectivity_type = "public"
  allocation_id     = aws_eip.nat[each.key].id
  subnet_id         = aws_subnet.public[local.nat_subnet_keys[each.key]].id
  tags              = merge(var.tags, { Name = "${var.name_prefix}-${substr(each.key, length(each.key) - 1, 1)}-nat", service = "nat" })

  depends_on = [aws_internet_gateway.this, aws_route_table.public, aws_route_table_association.public]
}

resource "aws_route" "private_nat" {
  for_each               = local.nat_routes
  route_table_id         = aws_route_table.private_by_az[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[each.value].id
}
