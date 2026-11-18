locals {
  region      = "ca-central-1"
  environment = "dev"
  # Names and tags follow docs/deployment-configuration.md sections 4 and 5.
  name_prefix = "${var.project}-${local.environment}"
  default_tags = {
    project = var.project
    env     = local.environment
    managed = "terraform"
  }
}
module "network" {
  source          = "../../../../modules/vpc"
  providers       = { aws = aws }
  name_prefix     = local.name_prefix
  vpc_cidr        = var.vpc_cidr
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets
  tags            = var.tags
  private_routing = { mode = "per_az", nat = var.nat }
  expected_scope = {
    partition  = "aws"
    region     = local.region
    account_id = var.aws_account_id
  }
  gateway_endpoints   = var.gateway_endpoints
  interface_endpoints = var.interface_endpoints
}
