locals {
  region         = "ca-central-1"
  expected_scope = { environment = "dev", partition = "aws", region = local.region, account_id = var.aws_account_id }
  required_tags  = { Environment = "dev", Service = "platform", Project = "aws-terraform-portfolio", ManagedBy = "Terraform" }
}
module "eks_platform" {
  source                   = "../../../../modules/eks_platform"
  providers                = { aws = aws }
  expected_scope           = local.expected_scope
  network_reference        = var.network_reference
  cluster_name             = var.cluster_name
  kubernetes_version       = var.kubernetes_version
  service_ipv4_cidr        = var.service_ipv4_cidr
  cluster_subnet_keys      = var.cluster_subnet_keys
  node_group               = var.node_group
  bootstrap_admin_role_arn = var.bootstrap_admin_role_arn
  namespace_access         = var.namespace_access
  api_client_cidrs         = var.api_client_cidrs
  node_https_egress_cidrs  = var.node_https_egress_cidrs
  addon_versions           = var.addon_versions
  cluster_kms_key_arn      = var.cluster_kms_key_arn
  deletion_protection      = var.deletion_protection
  tags                     = merge(var.tags, local.required_tags)
}
