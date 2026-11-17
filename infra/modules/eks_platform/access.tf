resource "aws_eks_access_entry" "bootstrap" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = var.bootstrap_admin_role_arn
  type          = "STANDARD"
  tags          = merge(var.tags, { Name = "${local.cluster_name}-access-bootstrap", service = "eks" })
}
resource "aws_eks_access_policy_association" "bootstrap" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.bootstrap.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}
resource "aws_eks_access_entry" "namespace" {
  for_each      = var.namespace_access
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value.principal_arn
  type          = "STANDARD"
  tags          = merge(var.tags, { Name = "${local.cluster_name}-access-${each.key}", service = "eks" })
}
resource "aws_eks_access_policy_association" "namespace" {
  for_each      = var.namespace_access
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.namespace[each.key].principal_arn
  policy_arn    = each.value.policy == "view" ? "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy" : "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
  access_scope {
    type       = "namespace"
    namespaces = sort(tolist(each.value.namespaces))
  }
}
