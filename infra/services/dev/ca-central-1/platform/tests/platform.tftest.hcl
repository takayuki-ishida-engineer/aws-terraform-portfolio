mock_provider "aws" {
  override_during = plan
  mock_resource "aws_eks_cluster" {
    defaults = { "arn" : "arn:aws:eks:ca-central-1:000000000000:cluster/test-eks", "id" : "test-eks", "endpoint" : "https://TEST.gr7.ca-central-1.eks.amazonaws.com", "certificate_authority" : [{ "data" : "VEVTVC1QVUJMSUMtQ0E=" }], "identity" : [{ "oidc" : [{ "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }] }], "vpc_config" : { "vpc_id" : "vpc-0123456789abcdef0", "cluster_security_group_id" : "sg-00000000000000003" } }
  }
}
override_resource {
  target          = module.eks_platform.aws_security_group.cluster
  override_during = plan
  values          = { "id" : "sg-00000000000000001" }
}
override_resource {
  target          = module.eks_platform.aws_security_group.nodes
  override_during = plan
  values          = { "id" : "sg-00000000000000002" }
}
override_resource {
  target          = module.eks_platform.aws_launch_template.nodes
  override_during = plan
  values          = { "id" : "lt-00000000000000001", "latest_version" : 1 }
}
override_resource {
  target          = module.eks_platform.aws_iam_openid_connect_provider.cluster
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }
}
override_resource {
  target          = module.eks_platform.aws_eks_node_group.this
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:nodegroup/test-eks/test-workers/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = module.eks_platform.aws_cloudwatch_log_group.cluster
  override_during = plan
  values          = { "arn" : "arn:aws:logs:ca-central-1:000000000000:log-group:/aws/eks/test-eks/cluster" }
}
override_resource {
  target          = module.eks_platform.aws_eks_access_entry.bootstrap
  override_during = plan
  values          = { "access_entry_arn" : "arn:aws:eks:ca-central-1:000000000000:access-entry/test-eks/role/test-platform-bootstrap/00000000" }
}
override_resource {
  target          = module.eks_platform.aws_iam_role.cluster
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:role/test-eks-cluster" }
}
override_resource {
  target          = module.eks_platform.aws_iam_role.nodes
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:role/test-eks-nodes" }
}
override_resource {
  target          = module.eks_platform.aws_iam_role.cni
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:role/test-eks-cni" }
}
override_resource {
  target          = module.eks_platform.aws_eks_addon.vpc_cni
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:addon/test-eks/vpc-cni/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = module.eks_platform.aws_eks_addon.kube_proxy
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:addon/test-eks/kube-proxy/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = module.eks_platform.aws_eks_addon.coredns
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:addon/test-eks/coredns/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = module.eks_platform.aws_eks_access_entry.namespace["reader"]
  override_during = plan
  values          = { "access_entry_arn" : "arn:aws:eks:ca-central-1:000000000000:access-entry/test-eks/role/test-reader/00000000" }
}
override_resource {
  target          = module.eks_platform.aws_eks_access_entry.namespace["deployer"]
  override_during = plan
  values          = { "access_entry_arn" : "arn:aws:eks:ca-central-1:000000000000:access-entry/test-eks/role/test-deployer/00000000" }
}

variables {
  ingress_name        = "test-ingress"
  ingress_subnet_key  = "private-a"
  gateway_target_port = 8443
}
override_resource {
  target          = module.private_ingress.aws_lb.this
  override_during = plan
  values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:loadbalancer/net/test-ingress/0123456789abcdef", "dns_name" : "test-ingress.example.elb.amazonaws.com", "zone_id" : "ZTESTZONE", "vpc_id" : "vpc-0123456789abcdef0" }
}

override_resource {
  target          = module.private_ingress.aws_lb_target_group.gateway
  override_during = plan
  values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:targetgroup/test-ingress-gateway/0123456789abcdef" }
}

override_resource {
  target          = module.private_ingress.aws_lb_listener.https_passthrough
  override_during = plan
  values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:listener/net/test-ingress/0123456789abcdef/0123456789abcdef" }
}

override_resource {
  target          = module.private_ingress.aws_security_group.nlb
  override_during = plan
  values          = { "id" : "sg-00000000000000101" }
}

override_resource {
  target          = module.private_ingress.aws_security_group.vpc_link_client
  override_during = plan
  values          = { "id" : "sg-00000000000000102" }
}

run "private_dev" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  assert {
    condition     = output.platform.scope.environment == "dev" && output.platform.cluster_name == var.cluster_name
    error_message = "Root must expose the actual DEV cluster."
  }
}

run "namespace_access" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    namespace_access         = { "reader" : { "principal_arn" : "arn:aws:iam::000000000000:role/test-reader", "policy" : "view", "namespaces" : ["test-app"] }, "deployer" : { "principal_arn" : "arn:aws:iam::000000000000:role/test-deployer", "policy" : "edit", "namespaces" : ["test-app", "test-jobs"] } }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  assert {
    condition     = output.platform.scope.environment == "dev" && output.platform.cluster_name == var.cluster_name
    error_message = "Root must expose the actual DEV cluster."
  }
}

run "customer_kms" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    cluster_kms_key_arn      = "arn:aws:kms:ca-central-1:000000000000:key/00000000-0000-0000-0000-000000000001"
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  assert {
    condition     = output.platform.scope.environment == "dev" && output.platform.cluster_name == var.cluster_name
    error_message = "Root must expose the actual DEV cluster."
  }
}

run "arm_nodes" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m7g.large", "ami_type" : "AL2023_ARM_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  assert {
    condition     = output.platform.scope.environment == "dev" && output.platform.cluster_name == var.cluster_name
    error_message = "Root must expose the actual DEV cluster."
  }
}

run "wrong_network_version" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 2, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_account" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "111111111111" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_region" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_environment" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "prod", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_partition" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws-cn", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "duplicate_private_subnet" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000001" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "public_subnet_masquerade" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000003", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "public_table_masquerade" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000003", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.network_reference]
}

run "one_cluster_subnet" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.cluster_subnet_keys]
}

run "public_cluster_selection" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "public-a"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.cluster_subnet_keys]
}

run "public_node_selection" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["public-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.node_group]
}

run "zero_minimum" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 0, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.node_group]
}

run "fractional_capacity" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2.5 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.node_group]
}

run "foreign_bootstrap" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::111111111111:role/test-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "wildcard_bootstrap" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/*"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "machine_role_as_admin" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-eks-nodes"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "namespace_admin_policy" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    namespace_access         = { "user" : { "principal_arn" : "arn:aws:iam::000000000000:role/test-reader", "policy" : "admin", "namespaces" : ["test-app"] } }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.namespace_access]
}

run "namespace_wildcard" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    namespace_access         = { "user" : { "principal_arn" : "arn:aws:iam::000000000000:role/test-reader", "policy" : "view", "namespaces" : ["*"] } }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.namespace_access]
}

run "world_api_ingress" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["0.0.0.0/0"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.api_client_cidrs]
}

run "world_https_egress" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["0.0.0.0/0"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.node_https_egress_cidrs]
}

run "dev_multiple_node_azs" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a", "private-b"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.node_group]
}

run "missing_active_nat" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1b" : "nat-00000000000000002" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.node_group]
}

run "invalid_root_account" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "invalid"
    active_workload_az       = "ca-central-1a"
  }
  expect_failures = [var.aws_account_id]
}

run "invalid_active_az" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1c"
  }
  expect_failures = [var.active_workload_az]
}

run "alternate_computed_values" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
  }
  override_resource {
    target          = module.eks_platform.aws_security_group.cluster
    override_during = plan
    values          = { "id" : "sg-00000000000000011" }
  }
  override_resource {
    target          = module.eks_platform.aws_security_group.nodes
    override_during = plan
    values          = { "id" : "sg-00000000000000012" }
  }
  override_resource {
    target          = module.eks_platform.aws_launch_template.nodes
    override_during = plan
    values          = { "id" : "lt-00000000000000002", "latest_version" : 2 }
  }
  override_resource {
    target          = module.eks_platform.aws_eks_cluster.this
    override_during = plan
    values          = { "endpoint" : "https://ALTERNATE.gr7.ca-central-1.eks.amazonaws.com", "certificate_authority" : [{ "data" : "QUxURVJOQVRFLVBVQkxJQy1DQQ==" }], "identity" : [{ "oidc" : [{ "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/ALTERNATEISSUER" }] }], "arn" : "arn:aws:eks:ca-central-1:000000000000:cluster/test-eks", "vpc_config" : { "vpc_id" : "vpc-0123456789abcdef0", "cluster_security_group_id" : "sg-00000000000000003" } }
  }
  override_resource {
    target          = module.eks_platform.aws_iam_openid_connect_provider.cluster
    override_during = plan
    values          = { "arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/ALTERNATEISSUER" }
  }
  override_resource {
    target          = module.eks_platform.aws_eks_node_group.this
    override_during = plan
    values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:nodegroup/test-eks/test-workers/00000000-0000-0000-0000-000000000002" }
  }
}
run "backend_443" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "private-a"
    gateway_target_port      = 443
  }
  assert {
    condition     = module.private_ingress.private_ingress.backend_target_port == var.gateway_target_port
    error_message = "Private TCP passthrough and reviewed backend-port contract required."
  }
}
run "ingress_public" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "public-a"
    gateway_target_port      = 8443
  }
  expect_failures = [var.ingress_subnet_key]
}
run "ingress_unknown" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "unknown"
    gateway_target_port      = 8443
  }
  expect_failures = [var.ingress_subnet_key]
}
run "ingress_wrong_az" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "private-b"
    gateway_target_port      = 8443
  }
  expect_failures = [var.ingress_subnet_key]
}
run "ingress_empty" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = ""
    gateway_target_port      = 8443
  }
  expect_failures = [var.ingress_subnet_key]
}
run "ingress_zero_port" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "private-a"
    gateway_target_port      = 0
  }
  expect_failures = [var.gateway_target_port]
}
run "ingress_large_port" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "private-a"
    gateway_target_port      = 65536
  }
  expect_failures = [var.gateway_target_port]
}
run "ingress_fractional_port" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "test-ingress"
    ingress_subnet_key       = "private-a"
    gateway_target_port      = 443.5
  }
  expect_failures = [var.gateway_target_port]
}
run "ingress_bad_name" {
  command = plan
  variables {
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    aws_account_id           = "000000000000"
    active_workload_az       = "ca-central-1a"
    ingress_name             = "internal-test"
    ingress_subnet_key       = "private-a"
    gateway_target_port      = 8443
  }
  expect_failures = [var.ingress_name]
}
