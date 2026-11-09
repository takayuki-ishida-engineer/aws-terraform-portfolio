resource "aws_launch_template" "nodes" {
  name_prefix            = "${var.cluster_name}-"
  update_default_version = false
  network_interfaces {
    device_index                = 0
    associate_public_ip_address = false
    delete_on_termination       = true
    security_groups             = [aws_security_group.nodes.id]
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    http_protocol_ipv6          = "disabled"
    instance_metadata_tags      = "disabled"
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      encrypted             = true
      delete_on_termination = true
      volume_size           = var.node_group.disk_size_gib
      volume_type           = "gp3"
    }
  }
  dynamic "tag_specifications" {
    for_each = toset(["instance", "volume"])
    content {
      resource_type = tag_specifications.value
      tags          = merge(var.tags, { Name = "${var.cluster_name}-nodes" })
    }
  }
  tags = merge(var.tags, { Name = "${var.cluster_name}-nodes" })
}
resource "aws_eks_node_group" "this" {
  cluster_name         = aws_eks_cluster.this.name
  node_group_name      = var.node_group.name
  node_role_arn        = aws_iam_role.nodes.arn
  subnet_ids           = [for k in sort(tolist(var.node_group.subnet_keys)) : var.network_reference.private_subnet_ids[k]]
  ami_type             = var.node_group.ami_type
  release_version      = var.node_group.release_version
  version              = var.kubernetes_version
  instance_types       = [var.node_group.instance_type]
  capacity_type        = "ON_DEMAND"
  force_update_version = false
  launch_template {
    id      = aws_launch_template.nodes.id
    version = tostring(aws_launch_template.nodes.latest_version)
  }
  scaling_config {
    min_size     = var.node_group.min_size
    desired_size = var.node_group.desired_size
    max_size     = var.node_group.max_size
  }
  update_config { max_unavailable = 1 }
  node_repair_config { enabled = false }
  tags       = merge(var.tags, { Name = var.node_group.name })
  depends_on = [aws_iam_role_policy_attachment.nodes, aws_eks_addon.vpc_cni, aws_eks_addon.kube_proxy, aws_eks_access_policy_association.bootstrap, aws_vpc_security_group_ingress_rule.nodes_cluster, aws_vpc_security_group_ingress_rule.nodes_dns, aws_vpc_security_group_egress_rule.nodes_cluster, aws_vpc_security_group_egress_rule.nodes_dns, aws_vpc_security_group_egress_rule.nodes_peer_dns, aws_vpc_security_group_egress_rule.nodes_https]
}
