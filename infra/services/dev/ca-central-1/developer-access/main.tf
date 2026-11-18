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

# AWS public parameter for the current Amazon Linux 2023 x86_64 AMI (SSM agent
# preinstalled). A newly published AMI replaces the stateless host on the next apply.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

module "developer_access" {
  source    = "../../../../modules/developer_access"
  providers = { aws = aws }

  name_prefix   = local.name_prefix
  vpc_id        = var.network_reference.vpc_id
  vpc_cidr      = var.network_reference.vpc_cidr
  subnet_id     = var.network_reference.private_subnet_ids[var.subnet_key]
  ami_id        = data.aws_ssm_parameter.al2023.insecure_value
  instance_type = var.instance_type
  default_tags  = local.default_tags
  tags          = var.tags
}
