mock_provider "aws" {
  override_during = plan
}

# Finding F21: a plan from the committed terraform.tfvars alone. This file sets no
# variables (the checker rejects a variables block), so every input comes from the
# committed values. The checker verifies the planned resources against
# network_cases.json "root_committed": the complete inventory and all nine
# interface endpoints (service name, subnet, security group, private DNS, Name and
# service tags). A committed-value change without a matching record update fails.
# The committed account is the documented placeholder. Run it in a clean checkout,
# as CI does: an untracked local.auto.tfvars would override the committed values.
override_resource {
  target          = module.network.aws_vpc.this
  override_during = plan
  values          = { "id" : "vpc-v2-mock", "arn" : "arn:aws:ec2:ca-central-1:123456789012:vpc/vpc-v2-mock" }
}
override_resource {
  target          = module.network.aws_route_table.public[0]
  override_during = plan
  values          = { "id" : "rtb-public" }
}
override_resource {
  target          = module.network.aws_internet_gateway.this[0]
  override_during = plan
  values          = { "id" : "igw-mock" }
}
override_resource {
  target          = module.network.aws_route_table.private_by_az["ca-central-1a"]
  override_during = plan
  values          = { "id" : "rtb-a" }
}
override_resource {
  target          = module.network.aws_route_table.private_by_az["ca-central-1b"]
  override_during = plan
  values          = { "id" : "rtb-b" }
}
override_resource {
  target          = module.network.aws_nat_gateway.this["ca-central-1a"]
  override_during = plan
  values          = { "id" : "nat-a" }
}
override_resource {
  target          = module.network.aws_eip.nat["ca-central-1a"]
  override_during = plan
  values          = { "id" : "eipalloc-a", "public_ip" : "192.0.2.10" }
}
override_resource {
  target          = module.network.aws_subnet.private["private1"]
  override_during = plan
  values          = { "id" : "subnet-app-a" }
}
override_resource {
  target          = module.network.aws_subnet.private["private2"]
  override_during = plan
  values          = { "id" : "subnet-app-b" }
}
override_resource {
  target          = module.network.aws_subnet.public["public1"]
  override_during = plan
  values          = { "id" : "subnet-public-a" }
}
override_resource {
  target          = module.network.aws_subnet.public["public2"]
  override_during = plan
  values          = { "id" : "subnet-public-b" }
}
override_resource {
  target          = module.network.aws_security_group.endpoints[0]
  override_during = plan
  values          = { "id" : "sg-vpce" }
}
override_resource {
  target          = module.network.aws_vpc_security_group_ingress_rule.endpoints_https[0]
  override_during = plan
  values          = { "id" : "sgr-vpce-https" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["ec2"]
  override_during = plan
  values          = { "id" : "vpce-ec2" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["ec2messages"]
  override_during = plan
  values          = { "id" : "vpce-ec2messages" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["ecr.api"]
  override_during = plan
  values          = { "id" : "vpce-ecr-api" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["ecr.dkr"]
  override_during = plan
  values          = { "id" : "vpce-ecr-dkr" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["elasticloadbalancing"]
  override_during = plan
  values          = { "id" : "vpce-elasticloadbalancing" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["logs"]
  override_during = plan
  values          = { "id" : "vpce-logs" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["ssm"]
  override_during = plan
  values          = { "id" : "vpce-ssm" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["ssmmessages"]
  override_during = plan
  values          = { "id" : "vpce-ssmmessages" }
}
override_resource {
  target          = module.network.aws_vpc_endpoint.interface["sts"]
  override_during = plan
  values          = { "id" : "vpce-sts" }
}

run "dev_network_committed" {
  command = plan
  assert {
    condition     = length(output.network.endpoint_ids.interface) == 9 && output.network.endpoint_ids.interface["elasticloadbalancing"] == "vpce-elasticloadbalancing"
    error_message = "The committed DEV values must create the nine reviewed interface endpoints, including elasticloadbalancing (finding F21)."
  }
  assert {
    condition     = output.network.routing_mode == "per_az" && output.network.scope.account_id == var.aws_account_id && local.name_prefix == "${var.project}-dev"
    error_message = "The committed DEV values must keep per-AZ routing, the account scope and the <project>-dev name prefix."
  }
}
