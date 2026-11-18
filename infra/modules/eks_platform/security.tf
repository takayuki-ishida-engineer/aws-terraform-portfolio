resource "aws_security_group" "cluster" {
  name_prefix = "${local.sg_name.cluster}-"
  description = "Explicit private API clients and managed nodes; AWS also attaches its own cluster SG."
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = local.sg_name.cluster, service = "sg" })
}
resource "aws_security_group" "nodes" {
  name_prefix = "${local.sg_name.nodes}-"
  description = "Only reviewed EKS system flows and explicit HTTPS destinations. No SSH/NodePort/application ingress."
  vpc_id      = var.network_reference.vpc_id
  tags        = merge(var.tags, { Name = local.sg_name.nodes, service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "cluster_nodes" {
  security_group_id            = aws_security_group.cluster.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${local.sg_name.cluster}-in-node-https", service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "cluster_clients" {
  for_each          = var.api_client_cidrs
  security_group_id = aws_security_group.cluster.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${local.sg_name.cluster}-in-client-https${local.client_rule_suffix[each.value]}", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "cluster_nodes" {
  for_each                     = { https = { protocol = "tcp", port = 443 }, kubelet = { protocol = "tcp", port = 10250 }, dns_tcp = { protocol = "tcp", port = 53 }, dns_udp = { protocol = "udp", port = 53 } }
  security_group_id            = aws_security_group.cluster.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  tags                         = merge(var.tags, { Name = "${local.sg_name.cluster}-out-node-${replace(each.key, "_", "-")}", service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_cluster" {
  for_each                     = { https = { protocol = "tcp", port = 443 }, kubelet = { protocol = "tcp", port = 10250 }, dns_tcp = { protocol = "tcp", port = 53 }, dns_udp = { protocol = "udp", port = 53 } }
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.cluster.id
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  tags                         = merge(var.tags, { Name = "${local.sg_name.nodes}-in-cluster-${replace(each.key, "_", "-")}", service = "sg" })
}
resource "aws_vpc_security_group_ingress_rule" "nodes_dns" {
  for_each                     = toset(["tcp", "udp"])
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = each.value
  from_port                    = 53
  to_port                      = 53
  tags                         = merge(var.tags, { Name = "${local.sg_name.nodes}-in-node-dns-${each.value}", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_cluster" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.cluster.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  tags                         = merge(var.tags, { Name = "${local.sg_name.nodes}-out-cluster-https", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_dns" {
  for_each          = toset(["tcp", "udp"])
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = "${cidrhost(var.network_reference.vpc_cidr, 2)}/32"
  ip_protocol       = each.value
  from_port         = 53
  to_port           = 53
  tags              = merge(var.tags, { Name = "${local.sg_name.nodes}-out-resolver-dns-${each.value}", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_https" {
  for_each          = var.node_https_egress_cidrs
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${local.sg_name.nodes}-out-https${local.https_rule_suffix[each.value]}", service = "sg" })
}
# HTTPS to AWS-managed prefix lists (for example S3 for ECR image layers, finding F16).
resource "aws_vpc_security_group_egress_rule" "nodes_https_prefix_list" {
  for_each          = var.node_https_egress_prefix_list_ids
  security_group_id = aws_security_group.nodes.id
  prefix_list_id    = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${local.sg_name.nodes}-out-pl-https${local.prefix_rule_suffix[each.value]}", service = "sg" })
}
resource "aws_vpc_security_group_egress_rule" "nodes_peer_dns" {
  for_each                     = toset(["tcp", "udp"])
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = each.value
  from_port                    = 53
  to_port                      = 53
  tags                         = merge(var.tags, { Name = "${local.sg_name.nodes}-out-node-dns-${each.value}", service = "sg" })
}
