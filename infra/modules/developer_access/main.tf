# Developer access host (Step 1 item 5): an instance in a private subnet that
# operators reach only through AWS Systems Manager Session Manager, for port
# forwarding to the private EKS endpoint (and later private RDS). No SSH key, no
# inbound rule, no public IP; HTTPS egress only to the VPC CIDR (interface
# endpoints and private service endpoints).
locals {
  name = {
    instance = "${var.name_prefix}-ec2-bastion"
    role     = "${var.name_prefix}-role-bastion"
    profile  = "${var.name_prefix}-profile-bastion"
    sg       = "${var.name_prefix}-sg-bastion"
  }
}

resource "aws_iam_role" "this" {
  name                 = local.name.role
  description          = "Session Manager access for the developer access host only."
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }]
  })
  tags = merge(var.tags, { Name = local.name.role, service = "role" })
}

# AWS managed policy for the SSM agent (Session Manager, no S3 or KMS access added).
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "this" {
  name = local.name.profile
  role = aws_iam_role.this.name
  tags = merge(var.tags, { Name = local.name.profile, service = "profile" })
}

resource "aws_security_group" "this" {
  name        = local.name.sg
  description = "Developer access host: no inbound; HTTPS to the VPC only."
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = local.name.sg, service = "sg" })
}

resource "aws_vpc_security_group_egress_rule" "vpc_https" {
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  tags              = merge(var.tags, { Name = "${local.name.sg}-out-vpc-https", service = "sg" })
}

resource "aws_instance" "this" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  associate_public_ip_address = false
  monitoring                  = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    encrypted             = true
    volume_type           = "gp3"
    delete_on_termination = true
    tags                  = merge(var.default_tags, var.tags, { Name = "${local.name.instance}-root", service = "ec2" })
  }

  tags = merge(var.tags, { Name = local.name.instance, service = "ec2" })

  # The agent registers with Session Manager only once its role and egress exist.
  depends_on = [aws_iam_role_policy_attachment.ssm, aws_vpc_security_group_egress_rule.vpc_https]
}
