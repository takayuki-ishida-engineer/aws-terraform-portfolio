mock_provider "aws" { override_during = plan }
override_resource {
  target          = aws_lb.this
  override_during = plan
  values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:loadbalancer/net/test-ingress/0123456789abcdef", "dns_name" : "test-ingress.example.elb.amazonaws.com", "zone_id" : "ZTESTZONE", "vpc_id" : "vpc-0123456789abcdef0" }
}

override_resource {
  target          = aws_lb_target_group.gateway
  override_during = plan
  values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:targetgroup/test-ingress-gateway/0123456789abcdef" }
}

override_resource {
  target          = aws_lb_listener.https_passthrough
  override_during = plan
  values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:listener/net/test-ingress/0123456789abcdef/0123456789abcdef" }
}

override_resource {
  target          = aws_security_group.nlb
  override_during = plan
  values          = { "id" : "sg-00000000000000011" }
}

override_resource {
  target          = aws_security_group.vpc_link_client
  override_during = plan
  values          = { "id" : "sg-00000000000000012" }
}
variables { controller_oidc = { "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" } }
override_resource {
  target          = aws_iam_role.controller
  override_during = plan
  values          = { arn = "arn:aws:iam::000000000000:role/test-ingress-lbc" }
}

run "private_dev" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  assert {
    condition     = aws_lb.this.internal && aws_lb_listener.https_passthrough.protocol == "TCP" && aws_lb_target_group.gateway.port == var.backend_target_port
    error_message = "Private TCP passthrough and reviewed backend-port contract required."
  }
}
run "multi_az" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a", "private-b"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  assert {
    condition     = aws_lb.this.internal && aws_lb_listener.https_passthrough.protocol == "TCP" && aws_lb_target_group.gateway.port == var.backend_target_port
    error_message = "Private TCP passthrough and reviewed backend-port contract required."
  }
}
run "cross_zone" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a", "private-b"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = true
  }
  assert {
    condition     = aws_lb.this.internal && aws_lb_listener.https_passthrough.protocol == "TCP" && aws_lb_target_group.gateway.port == var.backend_target_port
    error_message = "Private TCP passthrough and reviewed backend-port contract required."
  }
}
run "backend_443" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  assert {
    condition     = aws_lb.this.internal && aws_lb_listener.https_passthrough.protocol == "TCP" && aws_lb_target_group.gateway.port == var.backend_target_port
    error_message = "Private TCP passthrough and reviewed backend-port contract required."
  }
}
run "backend_max" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 65535
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  assert {
    condition     = aws_lb.this.internal && aws_lb_listener.https_passthrough.protocol == "TCP" && aws_lb_target_group.gateway.port == var.backend_target_port
    error_message = "Private TCP passthrough and reviewed backend-port contract required."
  }
}
run "wrong_version" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 2, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "wrong_account" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "111111111111" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "wrong_region" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "us-east-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "wrong_env" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "prod", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "wrong_partition" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws-cn", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "wrong_vpc" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "bad", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "empty_private" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : {}, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "duplicate_subnet" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000001" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "public_masquerade" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000003", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "missing_az" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "invalid_az" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "us-east-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.network_reference]
}
run "empty_selection" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = []
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.subnet_keys]
}
run "unknown_selection" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["missing"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.subnet_keys]
}
run "public_selection" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["public-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.subnet_keys]
}
run "duplicate_az" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1a" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a", "private-b"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.subnet_keys]
}
run "zero_port" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 0
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.backend_target_port]
}
run "large_port" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 65536
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.backend_target_port]
}
run "fractional_port" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 443.5
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.backend_target_port]
}
run "same_sg" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000001" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.eks_security_groups]
}
run "invalid_sg" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "bad" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.eks_security_groups]
}
run "reserved_name" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "internal-test"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.name]
}
run "invalid_name" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "Unsafe_Name"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  expect_failures = [var.name]
}

run "alternate_computed" {
  command = plan
  override_resource {
    target          = aws_lb.this
    override_during = plan
    values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:loadbalancer/net/test-ingress/fedcba9876543210", "dns_name" : "alternate-ingress.example.elb.amazonaws.com", "zone_id" : "ZALTERNATE", "vpc_id" : "vpc-0123456789abcdef0" }
  }
  override_resource {
    target          = aws_lb_target_group.gateway
    override_during = plan
    values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:targetgroup/test-ingress-gateway/fedcba9876543210" }
  }
  override_resource {
    target          = aws_lb_listener.https_passthrough
    override_during = plan
    values          = { "arn" : "arn:aws:elasticloadbalancing:ca-central-1:000000000000:listener/net/test-ingress/fedcba9876543210/fedcba9876543210" }
  }
  override_resource {
    target          = aws_security_group.nlb
    override_during = plan
    values          = { "id" : "sg-00000000000000131" }
  }
  override_resource {
    target          = aws_security_group.vpc_link_client
    override_during = plan
    values          = { "id" : "sg-00000000000000132" }
  }
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
  }
  assert {
    condition     = aws_lb.this.internal
    error_message = "Internal NLB required."
  }
}

run "alternate_oidc" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/ALTERNATEISSUER", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/ALTERNATEISSUER" }
  }
  assert {
    condition     = aws_iam_role.controller.arn == output.controller_identity.role_arn
    error_message = "Actual IRSA role output required."
  }
}

run "oidc_cross_account" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER", "provider_arn" : "arn:aws:iam::111111111111:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }
  }
  expect_failures = [var.controller_oidc]
}

run "oidc_wrong_region" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://oidc.eks.us-east-1.amazonaws.com/id/TESTISSUER", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/TESTISSUER" }
  }
  expect_failures = [var.controller_oidc]
}

run "oidc_wrong_issuer" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://untrusted.example.com/id/TEST", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }
  }
  expect_failures = [var.controller_oidc]
}

run "oidc_mismatch" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/OTHER" }
  }
  expect_failures = [var.controller_oidc]
}

run "oidc_empty" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }
  }
  expect_failures = [var.controller_oidc]
}

run "oidc_wildcard" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER*", "provider_arn" : "arn:aws:iam::000000000000:oidc-provider/oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER" }
  }
  expect_failures = [var.controller_oidc]
}

run "oidc_wrong_provider" {
  command = plan
  variables {
    expected_scope      = { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }
    network_reference   = { "interface_version" : 1, "scope" : { "environment" : "dev", "partition" : "aws", "region" : "ca-central-1", "account_id" : "000000000000" }, "vpc_id" : "vpc-0123456789abcdef0", "private_subnet_ids" : { "private-a" : "subnet-00000000000000001", "private-b" : "subnet-00000000000000002" }, "public_subnet_ids" : { "public-a" : "subnet-00000000000000003" }, "subnet_azs" : { "private" : { "private-a" : "ca-central-1a", "private-b" : "ca-central-1b" } } }
    name                = "test-ingress"
    subnet_keys         = ["private-a"]
    backend_target_port = 8443
    eks_security_groups = { "cluster" : "sg-00000000000000001", "nodes" : "sg-00000000000000002" }
    cross_zone_enabled  = false
    controller_oidc     = { "issuer" : "https://oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER", "provider_arn" : "arn:aws:iam::000000000000:role/not-oidc" }
  }
  expect_failures = [var.controller_oidc]
}
