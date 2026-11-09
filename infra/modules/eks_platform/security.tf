resource "aws_security_group" "cluster" {
  name_prefix = "${var.cluster_name}-control-"
  description = "Explicit private API clients and managed nodes; AWS also attaches its own cluster SG."
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = "${var.cluster_name}-control" })
}
resource "aws_security_group" "nodes" {
  name_prefix = "${var.cluster_name}-nodes-"
  description = "Only reviewed EKS system flows and explicit HTTPS destinations. No SSH/NodePort/application ingress."
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = "${var.cluster_name}-nodes" })
}
resource "aws_vpc_security_group_ingress_rule" "cluster_nodes" {
  security_group_id            = aws_security_group.cluster.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${var.cluster_name}-cluster_nodes" })
}
resource "aws_vpc_security_group_ingress_rule" "cluster_clients" {
  for_each          = var.api_client_cidrs
  security_group_id = aws_security_group.cluster.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${var.cluster_name}-cluster_clients" })
}
resource "aws_vpc_security_group_egress_rule" "cluster_nodes" {
  for_each                     = { https = { protocol = "tcp", port = 443 }, kubelet = { protocol = "tcp", port = 10250 }, dns_tcp = { protocol = "tcp", port = 53 }, dns_udp = { protocol = "udp", port = 53 } }
  security_group_id            = aws_security_group.cluster.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  tags                         = merge(var.tags, { Name = "${var.cluster_name}-cluster_nodes" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_cluster" {
  for_each                     = { https = { protocol = "tcp", port = 443 }, kubelet = { protocol = "tcp", port = 10250 }, dns_tcp = { protocol = "tcp", port = 53 }, dns_udp = { protocol = "udp", port = 53 } }
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.cluster.id
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  tags                         = merge(var.tags, { Name = "${var.cluster_name}-nodes_cluster" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_dns" {
  for_each                     = toset(["tcp", "udp"])
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = each.value
  from_port                    = 53
  to_port                      = 53
  tags                         = merge(var.tags, { Name = "${var.cluster_name}-nodes_dns" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_cluster" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.cluster.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${var.cluster_name}-nodes_cluster" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_dns" {
  for_each          = toset(["tcp", "udp"])
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = "${cidrhost(var.network_reference.vpc_cidr, 2)}/32"
  ip_protocol       = each.value
  from_port         = 53
  to_port           = 53
  tags              = merge(var.tags, { Name = "${var.cluster_name}-nodes_dns" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_https" {
  for_each          = var.node_https_egress_cidrs
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${var.cluster_name}-nodes_https" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_peer_dns" {
  for_each                     = toset(["tcp", "udp"])
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = each.value
  from_port                    = 53
  to_port                      = 53
  tags                         = merge(var.tags, { Name = "${var.cluster_name}-nodes-peer-dns" })
}
