resource "aws_cloudwatch_log_group" "cluster" {
  name                        = "/aws/eks/${local.cluster_name}/cluster"
  retention_in_days           = 30
  log_group_class             = "STANDARD"
  deletion_protection_enabled = var.deletion_protection
  skip_destroy                = false
  tags                        = merge(var.tags, { Name = "/aws/eks/${local.cluster_name}/cluster", service = "eks" })
}
resource "aws_eks_cluster" "this" {
  name                          = local.cluster_name
  version                       = var.kubernetes_version
  role_arn                      = aws_iam_role.cluster.arn
  bootstrap_self_managed_addons = false
  deletion_protection           = var.deletion_protection
  force_update_version          = false
  enabled_cluster_log_types     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  compute_config { enabled = false }
  storage_config {
    block_storage { enabled = false }
  }
  kubernetes_network_config {
    ip_family         = "ipv4"
    service_ipv4_cidr = var.service_ipv4_cidr
    elastic_load_balancing { enabled = false }
  }
  upgrade_policy { support_type = "STANDARD" }
  vpc_config {
    subnet_ids                = [for k in sort(tolist(var.cluster_subnet_keys)) : var.network_reference.private_subnet_ids[k]]
    endpoint_private_access   = true
    endpoint_public_access    = false
    control_plane_egress_mode = "AWS_MANAGED"
    security_group_ids        = [aws_security_group.cluster.id]
  }
  dynamic "encryption_config" {
    for_each = var.cluster_kms_key_arn == null ? [] : [var.cluster_kms_key_arn]
    content {
      resources = ["secrets"]
      provider { key_arn = encryption_config.value }
    }
  }
  tags       = merge(var.tags, { Name = local.cluster_name, service = "eks" })
  depends_on = [aws_iam_role_policy.cluster, aws_cloudwatch_log_group.cluster, aws_vpc_security_group_ingress_rule.cluster_nodes, aws_vpc_security_group_ingress_rule.cluster_clients, aws_vpc_security_group_egress_rule.cluster_nodes]
  lifecycle {
    postcondition {
      condition     = self.arn == "arn:${var.expected_scope.partition}:eks:${var.expected_scope.region}:${var.expected_scope.account_id}:cluster/${local.cluster_name}" && self.vpc_config[0].vpc_id == var.network_reference.vpc_id
      error_message = "Actual cluster ARN/account/Region/VPC must match the explicit network scope."
    }
  }
}
