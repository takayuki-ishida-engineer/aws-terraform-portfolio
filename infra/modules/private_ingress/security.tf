resource "aws_security_group" "nlb" {
  name_prefix = "${var.name_prefix}-sg-nlb-"
  description = "Internal TCP passthrough NLB only"
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-sg-nlb", service = "sg" })
}
resource "aws_security_group" "vpc_link_client" {
  name_prefix = "${var.name_prefix}-sg-vpc-link-"
  description = "Future VPC Link V2 ENIs only; API Root attaches this group, does not own it"
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-sg-vpc-link", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "client_nlb" {
  security_group_id            = aws_security_group.vpc_link_client.id
  referenced_security_group_id = aws_security_group.nlb.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-vpc-link-out-nlb-https", service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "nlb_clients" {
  security_group_id            = aws_security_group.nlb.id
  referenced_security_group_id = aws_security_group.vpc_link_client.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-nlb-in-vpc-link-https", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "nlb_targets" {
  security_group_id            = aws_security_group.nlb.id
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = var.backend_target_port
  to_port                      = var.backend_target_port
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-nlb-out-node-gw", service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_targets" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = aws_security_group.nlb.id
  ip_protocol                  = "tcp"
  from_port                    = var.backend_target_port
  to_port                      = var.backend_target_port
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-node-in-nlb-gw", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "cluster_webhook" {
  security_group_id            = var.eks_security_groups.cluster
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = 9443
  to_port                      = 9443
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-cluster-out-node-lbc-webhook", service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_webhook" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = var.eks_security_groups.cluster
  ip_protocol                  = "tcp"
  from_port                    = 9443
  to_port                      = 9443
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-node-in-cluster-lbc-webhook", service = "sg" })
}

resource "aws_vpc_security_group_egress_rule" "cluster_istio_webhook" {
  security_group_id            = var.eks_security_groups.cluster
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = 15017
  to_port                      = 15017
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-cluster-out-node-istio-webhook", service = "sg" })
}

resource "aws_vpc_security_group_ingress_rule" "nodes_istio_webhook" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = var.eks_security_groups.cluster
  ip_protocol                  = "tcp"
  from_port                    = 15017
  to_port                      = 15017
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-node-in-cluster-istio-webhook", service = "sg" })
}

resource "aws_vpc_security_group_egress_rule" "nodes_istiod" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = 15012
  to_port                      = 15012
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-node-out-node-istiod", service = "sg" })
}

resource "aws_vpc_security_group_ingress_rule" "nodes_istiod" {
  security_group_id            = var.eks_security_groups.nodes
  referenced_security_group_id = var.eks_security_groups.nodes
  ip_protocol                  = "tcp"
  from_port                    = 15012
  to_port                      = 15012
  tags                         = merge(var.tags, { Name = "${var.name_prefix}-sg-eks-node-in-node-istiod", service = "sg" })
}
