module "private_ingress" {
  source              = "../../../../modules/private_ingress"
  providers           = { aws = aws }
  expected_scope      = local.expected_scope
  network_reference   = var.network_reference
  name                = var.ingress_name
  subnet_keys         = toset([var.ingress_subnet_key])
  backend_target_port = var.gateway_target_port
  eks_security_groups = { cluster = module.eks_platform.security_group_ids.cluster, nodes = module.eks_platform.security_group_ids.nodes }
  cross_zone_enabled  = false
  deletion_protection = var.deletion_protection
  tags                = merge(var.tags, local.required_tags)
  controller_oidc     = { issuer = module.eks_platform.oidc_issuer, provider_arn = module.eks_platform.oidc_provider_arn }
}
