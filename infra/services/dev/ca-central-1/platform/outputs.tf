output "platform" {
  description = "Actual private platform interface; public CA/endpoint/identity metadata only. No kubeconfig/token, state publication or reachability proof."
  value = {
    scope                      = local.expected_scope
    cluster_name               = module.eks_platform.cluster_name
    cluster_arn                = module.eks_platform.cluster_arn
    endpoint                   = module.eks_platform.endpoint
    certificate_authority_data = module.eks_platform.certificate_authority_data
    oidc_issuer                = module.eks_platform.oidc_issuer
    oidc_provider_arn          = module.eks_platform.oidc_provider_arn
    node_group_arn             = module.eks_platform.node_group_arn
    security_group_ids         = module.eks_platform.security_group_ids
    role_arns                  = module.eks_platform.role_arns
    access_entry_arns          = module.eks_platform.access_entry_arns
    addon_arns                 = module.eks_platform.addon_arns
    log_group_arn              = module.eks_platform.log_group_arn
  }
}

output "private_ingress" {
  value       = module.private_ingress.private_ingress
  description = "Additional scoped ingress interface; platform output remains unchanged. Publication and actual runtime remain OPEN."
}
