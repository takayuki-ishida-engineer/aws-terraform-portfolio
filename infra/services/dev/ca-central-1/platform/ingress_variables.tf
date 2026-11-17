variable "ingress_subnet_key" {
  type     = string
  nullable = false
  validation {
    condition     = try(contains(keys(var.network_reference.private_subnet_ids), var.ingress_subnet_key) && var.network_reference.subnet_azs.private[var.ingress_subnet_key] == var.active_workload_az, false)
    error_message = "DEV ingress must select an approved private subnet in the explicit active worker AZ."
  }
}
variable "gateway_target_port" {
  type     = number
  nullable = false
  validation {
    condition     = var.gateway_target_port >= 1 && var.gateway_target_port <= 65535 && floor(var.gateway_target_port) == var.gateway_target_port
    error_message = "Supply an explicit integer Gateway Pod TCP target port 1-65535."
  }
}
