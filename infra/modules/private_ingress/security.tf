resource "aws_security_group" "nlb" {
  name_prefix = "${var.name}-nlb-"
  description = "Internal TCP passthrough NLB only"
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-nlb" })
}
resource "aws_security_group" "vpc_link_client" {
  name_prefix = "${var.name}-vpc-link-client-"
  description = "Future VPC Link V2 ENIs only; API Root attaches this group, does not own it"
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-vpc_link_client" })
}
resource "aws_vpc_security_group_egress_rule" "client_nlb" {
  security_group_id            = aws_security_group.vpc_link_client.id
  referenced_security_group_id = aws_security_group.nlb.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${var.name}-client_nlb" })
}
resource "aws_vpc_security_group_ingress_rule" "nlb_clients" {
  security_group_id            = aws_security_group.nlb.id
  referenced_security_group_id = aws_security_group.vpc_link_client.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${var.name}-nlb_clients" })
}
resource "aws_vpc_security_group_egress_rule" "nlb_targets" {
  security_group_id            = aws_security_group.nlb.id
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = var.backend_target_port
  to_port                      = var.backend_target_port
  tags                         = merge(var.tags, { Name = "${var.name}-nlb_targets" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_targets" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = aws_security_group.nlb.id
  ip_protocol                  = "tcp"
  from_port                    = var.backend_target_port
  to_port                      = var.backend_target_port
  tags                         = merge(var.tags, { Name = "${var.name}-nodes_targets" })
}
resource "aws_vpc_security_group_egress_rule" "cluster_webhook" {
  security_group_id            = var.eks_security_groups.cluster
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = 9443
  to_port                      = 9443
  tags                         = merge(var.tags, { Name = "${var.name}-cluster_webhook" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_webhook" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = var.eks_security_groups.cluster
  ip_protocol                  = "tcp"
  from_port                    = 9443
  to_port                      = 9443
  tags                         = merge(var.tags, { Name = "${var.name}-nodes_webhook" })
}
