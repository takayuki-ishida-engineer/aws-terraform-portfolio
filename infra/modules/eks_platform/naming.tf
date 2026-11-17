# Names and service tags follow docs/deployment-configuration.md sections 4 and 5:
# <prefix>-<type>[-<purpose>], where <prefix> is <project>-<env>. Taggable
# sub-resources (security group rules, add-ons, access entries) take the name
# of their parent plus a purpose and the parent's service token.
locals {
  cluster_name = "${var.name_prefix}-eks"
  sg_name = {
    cluster = "${var.name_prefix}-sg-eks-cluster"
    nodes   = "${var.name_prefix}-sg-eks-node"
  }
  role_name = {
    cluster = "${var.name_prefix}-role-eks-cluster"
    nodes   = "${var.name_prefix}-role-eks-node"
    cni     = "${var.name_prefix}-role-cni"
  }
  node_instance_name = "${var.name_prefix}-ec2-eks-node"
  # A repeated identical purpose takes a two-digit sequence only when the set
  # holds more than one CIDR.
  client_rule_suffix = { for cidr in var.api_client_cidrs : cidr => length(var.api_client_cidrs) > 1 ? format("-%02d", index(sort(tolist(var.api_client_cidrs)), cidr) + 1) : "" }
  https_rule_suffix  = { for cidr in var.node_https_egress_cidrs : cidr => length(var.node_https_egress_cidrs) > 1 ? format("-%02d", index(sort(tolist(var.node_https_egress_cidrs)), cidr) + 1) : "" }
}
