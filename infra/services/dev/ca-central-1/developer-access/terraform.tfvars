# Committed non-secret DEV values (docs/deployment-configuration.md section 1).
# Environment-specific values below are documented placeholders. Put the real
# values only in the untracked local.auto.tfvars (copy local.auto.tfvars.example);
# the local workflow refuses to plan or apply while a placeholder remains.

project        = "project"      # placeholder
aws_account_id = "123456789012" # placeholder

# Placeholder hand-off from the network root outputs (IDs are illustrative). Replace
# it in local.auto.tfvars with the actual network output before planning.
network_reference = {
  interface_version  = 1
  scope              = { environment = "dev", partition = "aws", region = "ca-central-1", account_id = "123456789012" }
  vpc_id             = "vpc-0123456789abcdef0"
  vpc_cidr           = "10.40.0.0/16"
  private_subnet_ids = { private1 = "subnet-00000000000000001", private2 = "subnet-00000000000000002" }
}

# private1 is in the platform root's api_client_cidrs (10.40.1.0/24), so the host
# reaches the private EKS endpoint; the network root's ssm, ssmmessages and
# ec2messages interface endpoints carry the Session Manager traffic.
subnet_key    = "private1"
instance_type = "t3.micro"
