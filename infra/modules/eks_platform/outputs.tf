output "cluster_name" { value = aws_eks_cluster.this.name }
output "cluster_arn" { value = aws_eks_cluster.this.arn }
output "endpoint" { value = aws_eks_cluster.this.endpoint }
output "certificate_authority_data" {
  description = "Public CA data, not a client credential or token."
  value       = aws_eks_cluster.this.certificate_authority[0].data
}
output "oidc_issuer" { value = aws_eks_cluster.this.identity[0].oidc[0].issuer }
output "oidc_provider_arn" { value = aws_iam_openid_connect_provider.cluster.arn }
output "node_group_arn" { value = aws_eks_node_group.this.arn }
output "security_group_ids" {
  description = "Actual attached custom groups plus AWS-created managed cluster group; managed defaults are not hardened/owned here."
  value       = { cluster = aws_security_group.cluster.id, nodes = aws_security_group.nodes.id, eks_managed = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id }
}
output "role_arns" { value = { cluster = aws_iam_role.cluster.arn, nodes = aws_iam_role.nodes.arn, cni = aws_iam_role.cni.arn } }
output "access_entry_arns" { value = { bootstrap = aws_eks_access_entry.bootstrap.access_entry_arn, namespaced = { for k, e in aws_eks_access_entry.namespace : k => e.access_entry_arn } } }
output "addon_arns" { value = { vpc_cni = aws_eks_addon.vpc_cni.arn, kube_proxy = aws_eks_addon.kube_proxy.arn, coredns = aws_eks_addon.coredns.arn } }
output "log_group_arn" { value = aws_cloudwatch_log_group.cluster.arn }
