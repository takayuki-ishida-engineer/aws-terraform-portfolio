locals {
  region         = "ca-central-1"
  environment    = "dev"
  expected_scope = { environment = local.environment, partition = "aws", region = local.region, account_id = var.aws_account_id }
  # Names and tags follow docs/deployment-configuration.md sections 4 and 5.
  name_prefix = "${var.project}-${local.environment}"
  default_tags = {
    project = var.project
    env     = local.environment
    managed = "terraform"
  }
  # Platform machine identities that may never be cluster administrators.
  machine_role_names = ["${local.name_prefix}-role-eks-cluster", "${local.name_prefix}-role-eks-node", "${local.name_prefix}-role-cni"]
}
module "eks_platform" {
  source                   = "../../../../modules/eks_platform"
  providers                = { aws = aws }
  expected_scope           = local.expected_scope
  network_reference        = var.network_reference
  name_prefix              = local.name_prefix
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
  tags                     = var.tags
  default_tags             = local.default_tags
}
