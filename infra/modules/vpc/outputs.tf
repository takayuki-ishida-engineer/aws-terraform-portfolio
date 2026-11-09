output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "IPv4 network CIDR of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "private_subnet_ids" {
  description = "Private subnet IDs keyed by the caller's stable private_subnets keys."
  value       = { for key, subnet in aws_subnet.private : key => subnet.id }
}

output "public_subnet_ids" {
  description = "Public subnet IDs keyed by stable public_subnets keys, or an empty map."
  value       = { for key, subnet in aws_subnet.public : key => subnet.id }
}

output "private_route_table_id" {
  description = "Legacy shared no-internet table ID; null in opted-in per_az (candidate V1-C01 requires independent acceptance before merge)."
  value       = local.per_az ? null : aws_route_table.private.id
}

output "public_route_table_id" {
  description = "ID of the public route table, or null when public_subnets is empty."
  value       = try(aws_route_table.public[0].id, null)
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway, or null when public_subnets is empty."
  value       = try(aws_internet_gateway.this[0].id, null)
}

output "subnet_azs" {
  description = "Actual private/public subnet AZs keyed like subnet ID outputs."
  value = {
    private = tomap({ for key, subnet in aws_subnet.private : key => subnet.availability_zone })
    public  = tomap({ for key, subnet in aws_subnet.public : key => subnet.availability_zone })
  }
}
output "private_route_table_ids_by_az" {
  description = "Active private table per AZ; legacy mode repeats the shared ID."
  value       = tomap({ for az in local.private_azs : az => local.per_az ? aws_route_table.private_by_az[az].id : aws_route_table.private.id })
}
output "private_route_table_ids_by_subnet" {
  description = "Actual selected table per stable private subnet key."
  value       = tomap({ for key, association in aws_route_table_association.private : key => association.route_table_id })
}
output "nat_gateway_ids_by_az" {
  description = "Actual zonal NAT IDs; empty when disabled."
  value       = tomap({ for az, nat in aws_nat_gateway.this : az => nat.id })
}
output "nat_eips_by_az" {
  description = "Actual allocation IDs/public IPs, not secrets or an automatic publication."
  value       = tomap({ for az, eip in aws_eip.nat : az => { allocation_id = eip.id, public_ip = eip.public_ip } })
}
output "endpoint_ids" {
  description = "Actual enabled gateway endpoint IDs. No interface endpoints implemented."
  value       = { gateway = tomap({ for service, endpoint in aws_vpc_endpoint.gateway : service => endpoint.id }) }
}
output "routing_mode" {
  description = "Explicit selected routing layout."
  value       = var.private_routing.mode
}
output "interface_version" {
  description = "Candidate extension interface version; V1-C01 still requires review acceptance before merge."
  value       = 1
}
