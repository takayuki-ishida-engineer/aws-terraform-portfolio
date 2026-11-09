resource "aws_eks_addon" "vpc_cni" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "vpc-cni"
  addon_version               = var.addon_versions.vpc_cni
  service_account_role_arn    = aws_iam_role.cni.arn
  resolve_conflicts_on_create = "NONE"
  resolve_conflicts_on_update = "NONE"
  configuration_values        = jsonencode({})
  preserve                    = false
  tags                        = merge(var.tags, { Name = "${var.cluster_name}-vpc-cni" })
  depends_on                  = [aws_iam_role_policy_attachment.cni]
}
resource "aws_eks_addon" "kube_proxy" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "kube-proxy"
  addon_version               = var.addon_versions.kube_proxy
  resolve_conflicts_on_create = "NONE"
  resolve_conflicts_on_update = "NONE"
  configuration_values        = jsonencode({})
  preserve                    = false
  tags                        = merge(var.tags, { Name = "${var.cluster_name}-kube-proxy" })
}
resource "aws_eks_addon" "coredns" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "coredns"
  addon_version               = var.addon_versions.coredns
  resolve_conflicts_on_create = "NONE"
  resolve_conflicts_on_update = "NONE"
  configuration_values        = jsonencode({})
  preserve                    = false
  tags                        = merge(var.tags, { Name = "${var.cluster_name}-coredns" })
  depends_on                  = [aws_eks_node_group.this]
}
