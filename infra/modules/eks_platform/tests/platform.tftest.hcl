mock_provider "aws" {
  override_during = plan
  mock_resource "aws_eks_cluster" {
    defaults = { "arn" : "arn:aws:eks:ca-central-1:000000000000:cluster/test-eks", "id" : "test-eks", "endpoint" : "https://TEST.gr7.ca-central-1.eks.amazonaws.com", "certificate_authority" : [{ "data" : "VEVTVC1QVUJMSUMtQ0E=" }], "identity" : [{ "oidc" : [{ "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }] }], "vpc_config" : { "vpc_id" : "vpc-0123456789abcdef0", "cluster_security_group_id" : "sg-00000000000000003" } }
  }
}
override_resource {
  target          = aws_security_group.cluster
  override_during = plan
  values          = { "id" : "sg-00000000000000001" }
}
override_resource {
  target          = aws_security_group.nodes
  override_during = plan
  values          = { "id" : "sg-00000000000000002" }
}
override_resource {
  target          = aws_launch_template.nodes
  override_during = plan
  values          = { "id" : "lt-00000000000000001", "latest_version" : 1 }
}
override_resource {
  target          = aws_iam_openid_connect_provider.cluster
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }
}
override_resource {
  target          = aws_eks_node_group.this
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:nodegroup/test-eks/test-workers/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = aws_cloudwatch_log_group.cluster
  override_during = plan
  values          = { "arn" : "arn:aws:logs:ca-central-1:000000000000:log-group:/aws/eks/test-eks/cluster" }
}
override_resource {
  target          = aws_eks_access_entry.bootstrap
  override_during = plan
  values          = { "access_entry_arn" : "arn:aws:eks:ca-central-1:000000000000:access-entry/test-eks/role/test-platform-bootstrap/00000000" }
}
override_resource {
  target          = aws_iam_role.cluster
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:role/test-eks-cluster" }
}
override_resource {
  target          = aws_iam_role.nodes
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:role/test-eks-nodes" }
}
override_resource {
  target          = aws_iam_role.cni
  override_during = plan
  values          = { "arn" : "arn:aws:iam::000000000000:role/test-eks-cni" }
}
override_resource {
  target          = aws_eks_addon.vpc_cni
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:addon/test-eks/vpc-cni/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = aws_eks_addon.kube_proxy
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:addon/test-eks/kube-proxy/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = aws_eks_addon.coredns
  override_during = plan
  values          = { "arn" : "arn:aws:eks:ca-central-1:000000000000:addon/test-eks/coredns/00000000-0000-0000-0000-000000000001" }
}
override_resource {
  target          = aws_eks_access_entry.namespace["reader"]
  override_during = plan
  values          = { "access_entry_arn" : "arn:aws:eks:ca-central-1:000000000000:access-entry/test-eks/role/test-reader/00000000" }
}
override_resource {
  target          = aws_eks_access_entry.namespace["deployer"]
  override_during = plan
  values          = { "access_entry_arn" : "arn:aws:eks:ca-central-1:000000000000:access-entry/test-eks/role/test-deployer/00000000" }
}

run "private_dev" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "namespace_access" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "arm_nodes" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "customer_kms" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "future_two_az_nodes" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-b", "private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "extra_reviewed_flows" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24", "10.70.21.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24", "198.51.100.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
    tags                     = { "Team" : "test-platform", "Name" : "caller-must-not-win" }
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "reviewed_teardown_setting" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
    deletion_protection      = false
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Private API-only authentication and disabled implicit creator admin are mandatory."
  }
}

run "wrong_network_version" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_account" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_region" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_environment" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "wrong_network_partition" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "legacy_network_mode" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "legacy_shared", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "invalid_vpc_id" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-invented", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "empty_private_subnets" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : {}, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "duplicate_private_subnet" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "public_subnet_masquerade" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "missing_subnet_az" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "wrong_subnet_region" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "us-east-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "public_table_masquerade" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.network_reference]
}

run "shared_table_in_per_az" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000001" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "invalid_nat_id" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-invalid" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.network_reference]
}

run "one_cluster_subnet" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.cluster_subnet_keys]
}

run "public_cluster_selection" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.cluster_subnet_keys]
}

run "one_cluster_az" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1a" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000001" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.cluster_subnet_keys]
}

run "public_node_selection" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.node_group]
}

run "empty_node_selection" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : [], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "zero_minimum" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.node_group]
}

run "desired_below_minimum" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 0, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "maximum_below_desired" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 0 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "fractional_capacity" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.node_group]
}

run "unreviewed_ami" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "CUSTOM", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "wrong_release_version" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.33.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "missing_instance_selection" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "too_small_disk" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 1, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.node_group]
}

run "invalid_kubernetes_version" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "latest"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.kubernetes_version]
}

run "public_service_range" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "203.0.113.0/24"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.service_ipv4_cidr]
}

run "overlapping_service_range" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "10.70.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.service_ipv4_cidr]
}

run "foreign_bootstrap" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "wildcard_bootstrap" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "session_bootstrap" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:sts::000000000000:assumed-role/test/session"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "machine_role_as_admin" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "service_linked_admin" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.bootstrap_admin_role_arn]
}

run "namespace_admin_policy" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.namespace_access]
}

run "namespace_wildcard" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.namespace_access]
}

run "system_namespace" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
    namespace_access         = { "user" : { "principal_arn" : "arn:aws:iam::000000000000:role/test-reader", "policy" : "view", "namespaces" : ["kube-system"] } }
  }
  expect_failures = [var.namespace_access]
}

run "namespace_bootstrap_reuse" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
    namespace_access         = { "user" : { "principal_arn" : "arn:aws:iam::000000000000:role/test-platform-bootstrap", "policy" : "view", "namespaces" : ["test-app"] } }
  }
  expect_failures = [var.namespace_access]
}

run "unselected_addon_version" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["10.70.20.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "latest", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.addon_versions]
}

run "wrong_kms_account" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
    cluster_kms_key_arn      = "arn:aws:kms:ca-central-1:111111111111:key/00000000-0000-0000-0000-000000000001"
  }
  expect_failures = [var.cluster_kms_key_arn]
}

run "world_api_ingress" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.api_client_cidrs]
}

run "public_api_client" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference        = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "routing_mode" : "per_az", "vpc_id" : "vpc-0123456789abcdef0", "vpc_cidr" : "10.70.0.0/16", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } }, "private_route_table_ids_by_subnet" : { "private-a" : "rtb-00000000000000001", "private-b" : "rtb-00000000000000002" }, "public_route_table_id" : "rtb-00000000000000003", "nat_gateway_ids_by_az" : { "ca-central-1a" : "nat-00000000000000001" } }
    cluster_name             = "test-eks"
    kubernetes_version       = "1.34"
    service_ipv4_cidr        = "172.20.0.0/16"
    cluster_subnet_keys      = ["private-a", "private-b"]
    node_group               = { "name" : "test-workers", "subnet_keys" : ["private-a"], "instance_type" : "m6i.large", "ami_type" : "AL2023_x86_64_STANDARD", "release_version" : "1.34.0-20260101", "disk_size_gib" : 30, "min_size" : 1, "desired_size" : 1, "max_size" : 2 }
    bootstrap_admin_role_arn = "arn:aws:iam::000000000000:role/test-platform-bootstrap"
    api_client_cidrs         = ["203.0.113.0/24"]
    node_https_egress_cidrs  = ["203.0.113.0/24"]
    addon_versions           = { "vpc_cni" : "v1.20.0-eksbuild.1", "coredns" : "v1.12.0-eksbuild.1", "kube_proxy" : "v1.34.0-eksbuild.1" }
  }
  expect_failures = [var.api_client_cidrs]
}

run "world_https_egress" {
  command = plan
  variables {
    expected_scope           = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
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
  }
  expect_failures = [var.node_https_egress_cidrs]
}
