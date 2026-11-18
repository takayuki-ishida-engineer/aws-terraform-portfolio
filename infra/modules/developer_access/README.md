# developer_access

A small instance in a private subnet that operators reach only through AWS
Systems Manager Session Manager, for port forwarding from a local workstation to
the private EKS endpoint (and later private RDS). Step 1 item 5 of the
[step plan](../../../docs/deployment-configuration.md#8-step-plan). There is no SSH
key, no inbound rule and no public IP. The calling root owns the provider and
resolves the AMI.

## Resources

| Resource | Name | Purpose |
| --- | --- | --- |
| `aws_iam_role.this` | `<prefix>-role-bastion` | Trusts only `ec2.amazonaws.com`, 1-hour sessions |
| `aws_iam_role_policy_attachment.ssm` | — | AWS managed `AmazonSSMManagedInstanceCore` only |
| `aws_iam_instance_profile.this` | `<prefix>-profile-bastion` | Instance profile for the role |
| `aws_security_group.this` | `<prefix>-sg-bastion` | No inbound rules |
| `aws_vpc_security_group_egress_rule.vpc_https` | `<prefix>-sg-bastion-out-vpc-https` | TCP 443 to the VPC CIDR only (interface endpoints, private EKS endpoint) |
| `aws_instance.this` | `<prefix>-ec2-bastion` | The host; root volume `<prefix>-ec2-bastion-root` |

## Effective configuration

| Setting | Value | Source |
| --- | --- | --- |
| Placement | `subnet_id`, `vpc_id`, `vpc_cidr` | Caller input (root passes the network output) |
| AMI | `ami_id` | Caller input (root resolves the AL2023 public SSM parameter) |
| Instance type | `t3.micro` | Module Default (`t3.nano`, `t3.micro` or `t3.small`) |
| Public IP | none (`associate_public_ip_address = false`) | Module Fixed |
| SSH key, user data | none | Module Fixed (source contract) |
| Instance metadata | IMDSv2 required, hop limit 1, instance tags in metadata disabled | Module Fixed |
| Root volume | encrypted gp3 (AWS managed EBS key), deleted with the instance | Module Fixed |
| Detailed monitoring | off | Module Fixed |
| IAM | EC2 trust only; `AmazonSSMManagedInstanceCore` only; no inline policy | Module Fixed |
| Network | No inbound rule; HTTPS egress to the VPC CIDR only | Module Fixed |
| Tags | Caller `tags` plus module-owned `Name` and `service`; the root volume also gets `default_tags` | Module Default `{}` / Module Fixed |

The host reaches Session Manager through the network root's `ssm`, `ssmmessages`
and `ec2messages` interface endpoints, so it needs no internet route. Session
Manager port forwarding (`AWS-StartPortForwardingSessionToRemoteHost`) then
connects the workstation to a private endpoint; the target's security group must
allow the host (the platform root allows its subnet in `api_client_cidrs`).
Session logging to S3 or CloudWatch is not configured.

## Inputs and validation

| Input | Type | Default | Validation |
| --- | --- | --- | --- |
| `name_prefix` | string | required | 2–20 lowercase letters, digits or hyphens, starts with a letter |
| `vpc_id` | string | required | `vpc-` + 8–17 hex |
| `vpc_cidr` | string | required | Canonical IPv4 CIDR, /16–/28 |
| `subnet_id` | string | required | `subnet-` + 8–17 hex |
| `ami_id` | string | required | `ami-` + 8–17 hex |
| `instance_type` | string | `t3.micro` | `t3.nano`, `t3.micro` or `t3.small` (x86_64, matching the AMI) |
| `default_tags` | map(string) | `{}` | Only `project`, `env`, `managed` |
| `tags` | map(string) | `{}` | No `Name`, `service` or `aws:` key; at most 50 with `Name` and `service` |

## Outputs

| Output | Description |
| --- | --- |
| `instance_id` | Session Manager target |
| `security_group_id` | Security group of the host |
| `role_arn` | Instance role ARN |
| `private_ip` | Private IPv4 address |

## Verification (offline)

`tests/developer_access.tftest.hcl` runs 12 mock-provider plans (2 positive,
10 rejected inputs). `tests/check_developer_access.py` checks the actual planned
resources (trust policy, managed policy, egress rule, IMDSv2, private placement,
encrypted root volume, names and tags), a source contract (no SSH key, user data,
inbound or inline rules, single managed policy) and, with `--self-test`, rejects
13 semantic mutations, 6 capture failures and 5 source mutations. Full CI runs
both. Nothing is created and no AWS API is called; Session Manager connectivity
and port forwarding are verified only on a real deployment.
