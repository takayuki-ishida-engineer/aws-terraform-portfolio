output "network" {
  description = "Candidate minimal network interface; not automatically published and not proof of actual account authorization. No state/secret exposure."
  value = {
    interface_version                 = module.network.interface_version
    scope                             = { environment = local.environment, region = local.region, partition = "aws", account_id = var.aws_account_id }
    vpc_id                            = module.network.vpc_id
    vpc_cidr                          = module.network.vpc_cidr
    private_subnet_ids                = module.network.private_subnet_ids
    public_subnet_ids                 = module.network.public_subnet_ids
    subnet_azs                        = module.network.subnet_azs
    private_route_table_id            = module.network.private_route_table_id
    private_route_table_ids_by_az     = module.network.private_route_table_ids_by_az
    private_route_table_ids_by_subnet = module.network.private_route_table_ids_by_subnet
    public_route_table_id             = module.network.public_route_table_id
    internet_gateway_id               = module.network.internet_gateway_id
    nat_gateway_ids_by_az             = module.network.nat_gateway_ids_by_az
    nat_eips_by_az                    = module.network.nat_eips_by_az
    endpoint_ids                      = module.network.endpoint_ids
    routing_mode                      = module.network.routing_mode
  }
}
