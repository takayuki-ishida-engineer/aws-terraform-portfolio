resource "aws_vpc_endpoint" "gateway" {
  for_each          = local.per_az ? var.gateway_endpoints : {}
  vpc_id            = aws_vpc.this.id
  vpc_endpoint_type = "Gateway"
  service_name      = "com.amazonaws.${try(var.expected_scope.region, "")}.s3"
  policy            = each.value.policy_json
  # This resource exclusively owns endpoint/table associations and AWS service routes.
  route_table_ids = [for az in sort(tolist(each.value.private_route_table_azs)) : aws_route_table.private_by_az[az].id if contains(local.private_azs, az)]
  tags            = merge(var.tags, { Name = length(var.gateway_endpoints) > 1 ? "${var.name_prefix}-vpce-${each.key}" : "${var.name_prefix}-vpce", service = "vpce" })
}
