# Committed non-secret DEV values (docs/deployment-configuration.md section 1).
# Environment-specific values below are documented placeholders. Put the real
# values only in the untracked local.auto.tfvars (copy local.auto.tfvars.example);
# the local workflow refuses to plan or apply while a placeholder remains.

project                  = "project"                                     # placeholder
aws_account_id           = "123456789012"                                # placeholder
bootstrap_admin_role_arn = "arn:aws:iam::123456789012:role/example-role" # placeholder: pre-existing admin role

# Placeholder hand-off from the network root outputs (IDs are illustrative). Replace
# it in local.auto.tfvars with the actual network outputs before planning.
network_reference = {
  interface_version = 1
  scope             = { environment = "dev", partition = "aws", region = "ca-central-1", account_id = "123456789012" }
  routing_mode      = "per_az"
  vpc_id            = "vpc-0123456789abcdef0"
  vpc_cidr          = "10.40.0.0/16"
  private_subnet_ids = {
    private1 = "subnet-00000000000000001"
    private2 = "subnet-00000000000000002"
  }
  public_subnet_ids = {
    public1 = "subnet-00000000000000003"
    public2 = "subnet-00000000000000004"
  }
  subnet_azs = { private = { private1 = "ca-central-1a", private2 = "ca-central-1b" } }
  private_route_table_ids_by_subnet = {
    private1 = "rtb-00000000000000001"
    private2 = "rtb-00000000000000002"
  }
  public_route_table_id = "rtb-00000000000000003"
  nat_gateway_ids_by_az = { "ca-central-1a" = "nat-00000000000000001" }
}

active_workload_az = "ca-central-1a"

# Kubernetes 1.35 (EKS standard support until 2027-03-27). Add-on versions are the
# latest Amazon EKS add-on type listed for 1.35 in the EKS User Guide source
# (awsdocs/amazon-eks-user-guide, latest/ug/networking/managing-*.adoc), read
# 2026-11-17. The node release is AMI release v20261112 (awslabs/amazon-eks-ami).
# The workstation preflight (--live) re-checks them with read-only EKS calls.
kubernetes_version = "1.35"
addon_versions = {
  vpc_cni    = "v1.23.1-eksbuild.1"
  coredns    = "v1.14.3-eksbuild.16"
  kube_proxy = "v1.35.3-eksbuild.25"
}

service_ipv4_cidr   = "172.20.0.0/16"
cluster_subnet_keys = ["private1", "private2"]
node_group = {
  subnet_keys     = ["private1"]
  instance_type   = "m6i.large"
  ami_type        = "AL2023_x86_64_STANDARD"
  release_version = "1.35.9-20261112"
  disk_size_gib   = 30
  min_size        = 1
  desired_size    = 1
  max_size        = 2
}

# Private API clients: the private subnet that will host the SSM developer-access EC2 (Step 1 item 5).
api_client_cidrs = ["10.40.1.0/24"]

# Node HTTPS egress stays inside the VPC. See the audit report (F16): a working node
# group also needs ECR/S3/STS reachability through interface endpoints or reviewed ranges.
node_https_egress_cidrs = ["10.40.0.0/16"]

# Private ingress (NLB in the active worker AZ, Gateway Pod port).
ingress_subnet_key  = "private1"
gateway_target_port = 8443
