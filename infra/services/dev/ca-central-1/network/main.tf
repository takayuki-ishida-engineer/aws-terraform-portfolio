locals {
  region      = "ca-central-1"
  environment = "dev"
  required_tags = {
    Environment = local.environment
    Service     = "network"
    Project     = "aws-terraform-portfolio"
    ManagedBy   = "Terraform"
  }
}
module "network" {
  source          = "../../../../modules/vpc"
  providers       = { aws = aws }
  name_prefix     = var.name_prefix
  vpc_cidr        = var.vpc_cidr
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets
  tags            = merge(var.tags, local.required_tags)
  private_routing = { mode = "per_az", nat = var.nat }
  expected_scope = {
    partition  = "aws"
    region     = local.region
    account_id = var.aws_account_id
  }
  gateway_endpoints = var.gateway_endpoints
}
