# Committed non-secret DEV values (docs/deployment-configuration.md section 1).
# Environment-specific values below are documented placeholders. Put the real
# values only in the untracked local.auto.tfvars (copy local.auto.tfvars.example);
# the local workflow refuses to plan or apply while a placeholder remains.

project        = "project"      # placeholder: replace in local.auto.tfvars
aws_account_id = "123456789012" # placeholder: replace in local.auto.tfvars

vpc_cidr = "10.40.0.0/16"

# Subnet tiers are numbered across the VPC: AZ a holds private1/public1, AZ b private2/public2.
private_subnets = {
  private1 = { cidr_block = "10.40.1.0/24", availability_zone = "ca-central-1a" }
  private2 = { cidr_block = "10.40.2.0/24", availability_zone = "ca-central-1b" }
}
public_subnets = {
  public1 = { cidr_block = "10.40.10.0/24", availability_zone = "ca-central-1a" }
  public2 = { cidr_block = "10.40.11.0/24", availability_zone = "ca-central-1b" }
}

# DEV runs workers in one AZ with one NAT gateway in that AZ.
active_workload_az = "ca-central-1a"
nat = {
  public_subnet_key_by_nat_az = { "ca-central-1a" = "public1" }
  nat_az_by_private_az        = { "ca-central-1a" = "ca-central-1a" }
}

# AWS API access without leaving the VPC, with private DNS in the active workload
# AZ only: ec2, ecr.api, ecr.dkr, logs and sts for the EKS nodes (finding F16);
# elasticloadbalancing as the path for the AWS Load Balancer Controller's target
# registration and Describe calls on the Terraform-owned target group (finding F21,
# not verified); ssm, ssmmessages and ec2messages for Session Manager on the
# developer access host (Step 1 item 5). Image layers come from S3 through the
# NAT gateway (node egress limited to the S3 managed prefix list in the platform
# root). Each endpoint is billed per hour.
interface_endpoints = {
  services    = ["ec2", "ec2messages", "ecr.api", "ecr.dkr", "elasticloadbalancing", "logs", "ssm", "ssmmessages", "sts"]
  subnet_keys = ["private1"]
}
