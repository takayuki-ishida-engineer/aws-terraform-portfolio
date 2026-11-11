resource "aws_iam_role" "controller" {
  name = "${var.name}-lbc"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity",
    Principal = { Federated = var.controller_oidc.provider_arn },
    Condition = { StringEquals = {
      "${replace(var.controller_oidc.issuer, "https://", "")}:aud" = "sts.amazonaws.com",
      "${replace(var.controller_oidc.issuer, "https://", "")}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
    } }
  }] })
  tags = merge(var.tags, { Name = "${var.name}-lbc" })
}
resource "aws_iam_role_policy" "controller" {
  name = "${var.name}-target-registration"
  role = aws_iam_role.controller.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "RegionalDiscovery", Effect = "Allow", Action = ["ec2:DescribeVpcs", "ec2:DescribeSecurityGroups", "ec2:DescribeInstances", "ec2:DescribeAvailabilityZones", "elasticloadbalancing:DescribeTargetGroups", "elasticloadbalancing:DescribeTargetHealth"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.expected_scope.region } } },
    { Sid = "OwnedTargetRegistration", Effect = "Allow", Action = ["elasticloadbalancing:RegisterTargets", "elasticloadbalancing:DeregisterTargets"], Resource = aws_lb_target_group.gateway.arn, Condition = { StringEquals = { "aws:RequestedRegion" = var.expected_scope.region } } }
  ] })
}
