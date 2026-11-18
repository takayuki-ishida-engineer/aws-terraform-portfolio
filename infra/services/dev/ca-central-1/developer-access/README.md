# DEV developer access host

Step 1 item 5 of the [step plan](../../../../../docs/deployment-configuration.md#8-step-plan)
(finding F3): a private instance that operators reach only through Session
Manager, so a local workstation can port-forward to the private EKS endpoint
(443) and later private RDS (5432). No SSH, no inbound rule, no public IP.

## Selected infrastructure

| Item | Value | Source |
| --- | --- | --- |
| Module | [`developer_access`](../../../../modules/developer_access/README.md) | Root selection |
| AMI | `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64` (AWS public SSM parameter, read at plan time); a newly published AMI replaces the stateless host on the next apply | Root Override (`ami_id`) |
| Subnet | `network_reference.private_subnet_ids[subnet_key]`, committed `private1` (in the platform root's `api_client_cidrs`) | Root Override |
| VPC and HTTPS egress destination | `network_reference.vpc_id` and `vpc_cidr` | Root Override |
| Instance type | `t3.micro` (committed) | Root Override (Module Default is the same) |
| Names | `<project>-dev-ec2-bastion`, `-role-bastion`, `-profile-bastion`, `-sg-bastion` | Module Fixed from the root's `name_prefix` |
| Hardening | IMDSv2 hop 1, encrypted gp3, no key/user data, `AmazonSSMManagedInstanceCore` only | Module Fixed |
| Provider | `ca-central-1`, `allowed_account_ids`, `default_tags` `project`, `env = dev`, `managed = terraform` | Root Fixed |
| Backend | `local`; optional S3 backend through the untracked override files | Root Fixed |

Prerequisite: the network root's `ssm`, `ssmmessages` and `ec2messages` interface
endpoints (committed in its `terraform.tfvars`). Apply after the network root.

## Input values

The committed `terraform.tfvars` holds placeholders for `project`,
`aws_account_id` and `network_reference`. Copy `local.auto.tfvars.example` to the
untracked `local.auto.tfvars` and paste the network output
(`terraform -chdir=../network output -json network`; extra fields are ignored).
The [local workflow](../../../../../scripts/local-workflow/README.md) preflight
refuses a plan or apply while a placeholder remains. `network_reference` must be
interface version 1 for dev, aws, ca-central-1 and this account, and `subnet_key`
must be one of its private subnets.

## Output

`developer_access`: `instance_id` (Session Manager target), `private_ip`,
`security_group_id`, `role_arn`, `region`.

## Port forwarding to the private EKS endpoint

With the AWS CLI and the Session Manager plugin on the workstation and an
operator role allowed to start sessions on this instance:

```bash
aws ssm start-session --region ca-central-1 --target <instance_id> --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters 'host=<eks endpoint host>,portNumber=443,localPortNumber=8443'
```

Then point kubectl at `https://localhost:8443` with the cluster CA and
`tls-server-name` set to the EKS endpoint host. Step 1 item 6 adds the scripted
hand-off and the full runbook.

## Verification (offline)

`tests/developer_access.tftest.hcl` runs 9 mock-provider plans (2 positive,
7 rejected inputs). `tests/check_root.py` checks the planned module resources
against the selected subnet, VPC and resolved AMI, the root output, the public
parameter source, that omitting `project`, `aws_account_id`, `network_reference`
or `subnet_key` fails before any plan, and rejects 6 semantic mutations and
4 capture failures. Full CI also plans this root with its committed values and
runs the preflight against it. No AWS API is called.
