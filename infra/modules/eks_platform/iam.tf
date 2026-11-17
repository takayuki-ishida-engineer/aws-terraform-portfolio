resource "aws_iam_role" "cluster" {
  name               = local.role_name.cluster
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "eks.amazonaws.com" } }] })
  tags               = merge(var.tags, { Name = local.role_name.cluster, service = "role" })
}
resource "aws_iam_role_policy" "cluster" {
  name = "${var.name_prefix}-policy-eks-cluster"
  role = aws_iam_role.cluster.name
  # AWS cluster-role minimum without legacy ELB permissions. Resource wildcard
  # is required by these read-only EC2 Describe operations, with Region scope.
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Sid = "RegionalEC2Discovery", Effect = "Allow", Action = ["ec2:DescribeInstances", "ec2:DescribeNetworkInterfaces", "ec2:DescribeVpcs", "ec2:DescribeDhcpOptions", "ec2:DescribeAvailabilityZones", "ec2:DescribeInstanceTopology"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.expected_scope.region } } },
    { Sid = "OwnClusterInstanceTag", Effect = "Allow", Action = ["ec2:CreateTags"], Resource = "arn:aws:ec2:${var.expected_scope.region}:${var.expected_scope.account_id}:instance/*", Condition = { "ForAllValues:StringEquals" = { "aws:TagKeys" = ["kubernetes.io/cluster/${local.cluster_name}"] }, Null = { "aws:TagKeys" = "false" } } }
  ], var.cluster_kms_key_arn == null ? [] : [{ Sid = "ExplicitClusterKeyMetadata", Effect = "Allow", Action = ["kms:DescribeKey"], Resource = var.cluster_kms_key_arn }]) })
}
resource "aws_iam_role" "nodes" {
  name               = local.role_name.nodes
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }] })
  tags               = merge(var.tags, { Name = local.role_name.nodes, service = "role" })
}
resource "aws_iam_role_policy_attachment" "nodes" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly"])
  role       = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/${each.key}"
}
resource "aws_iam_openid_connect_provider" "cluster" {
  url            = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
  # IAM retrieves the intermediate CA thumbprint on initial creation. No TLS
  # data source, certificate guess, Pod token or credential enters Terraform.
  tags = merge(var.tags, { Name = "${var.name_prefix}-oidc", service = "oidc" })
}
resource "aws_iam_role" "cni" {
  name = local.role_name.cni
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = aws_iam_openid_connect_provider.cluster.arn },
    Condition = { StringEquals = {
      "${replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")}:aud" = "sts.amazonaws.com",
      "${replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")}:sub" = "system:serviceaccount:kube-system:aws-node"
    } }
  }] })
  tags = merge(var.tags, { Name = local.role_name.cni, service = "role" })
}
resource "aws_iam_role_policy_attachment" "cni" {
  role       = aws_iam_role.cni.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}
