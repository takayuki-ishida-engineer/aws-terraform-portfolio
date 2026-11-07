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
  description = "ID of the shared private route table, with no configured internet route."
  value       = aws_route_table.private.id
}

output "public_route_table_id" {
  description = "ID of the public route table, or null when public_subnets is empty."
  value       = try(aws_route_table.public[0].id, null)
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway, or null when public_subnets is empty."
  value       = try(aws_internet_gateway.this[0].id, null)
}
