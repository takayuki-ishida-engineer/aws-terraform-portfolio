resource "aws_vpc_endpoint" "gateway" {
  for_each          = local.per_az ? var.gateway_endpoints : {}
  vpc_id            = aws_vpc.this.id
  vpc_endpoint_type = "Gateway"
  service_name      = "com.amazonaws.${try(var.expected_scope.region, "")}.s3"
  policy            = each.value.policy_json
  # This resource exclusively owns endpoint/table associations and AWS service routes.
  route_table_ids = [for az in sort(tolist(each.value.private_route_table_azs)) : aws_route_table.private_by_az[az].id if contains(local.private_azs, az)]
  # Every endpoint gets a purpose once more than one endpoint exists (section 4).
  tags = merge(var.tags, { Name = local.endpoint_count > 1 ? "${var.name_prefix}-vpce-${each.key}" : "${var.name_prefix}-vpce", service = "vpce" })
}

locals {
  interface_services = local.per_az && var.interface_endpoints != null ? var.interface_endpoints.services : toset([])
  endpoint_count     = length(var.gateway_endpoints) + length(local.interface_services)
}

# Interface endpoints let private workloads (for example EKS nodes) reach AWS
# APIs without leaving the VPC (finding F16). Only HTTPS from the VPC CIDR is
# allowed in; the group has no egress rules.
resource "aws_security_group" "endpoints" {
  count = length(local.interface_services) > 0 ? 1 : 0

  name        = "${var.name_prefix}-sg-vpce"
  description = "Interface VPC endpoints: HTTPS from the VPC CIDR only"
  vpc_id      = aws_vpc.this.id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-sg-vpce", service = "sg" })
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  count = length(local.interface_services) > 0 ? 1 : 0

  security_group_id = aws_security_group.endpoints[0].id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${var.name_prefix}-sg-vpce-in-vpc-https", service = "sg" })
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_services

  vpc_id              = aws_vpc.this.id
  vpc_endpoint_type   = "Interface"
  service_name        = "com.amazonaws.${try(var.expected_scope.region, "")}.${each.key}"
  subnet_ids          = [for key in sort(tolist(var.interface_endpoints.subnet_keys)) : aws_subnet.private[key].id]
  security_group_ids  = [aws_security_group.endpoints[0].id]
  private_dns_enabled = true
  tags                = merge(var.tags, { Name = "${var.name_prefix}-vpce-${replace(each.key, ".", "-")}", service = "vpce" })
}
