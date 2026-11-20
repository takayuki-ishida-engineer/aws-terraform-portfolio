# DEV deploy and teardown runbook

Step 1 item 6 of the [step plan](deployment-configuration.md#8-step-plan). It covers
how to build and remove the DEV environment in `ca-central-1` from the operator's
workstation, using the [local workflow](../scripts/local-workflow/README.md).

**Never** run any of it in CI, Codex Cloud or a Claude Code cloud session. The
scripts refuse to start there, and real AWS access is prohibited there
(`AGENTS.md`).

A real deployment is optional and needs a separate Owner decision. Before it
starts, the G01–G07 gates, the cumulative JPY 10,000 DEV limit and complete,
verified teardown within 72 hours all apply.

## 0. Prerequisites

| Item | Requirement |
| --- | --- |
| Tools | Terraform 1.17.x, AWS CLI v2 with the Session Manager plugin, kubectl, Python 3.11 or later, Git, OpenSSL 3 (Kubernetes certificates, §6) |
| Account | The dedicated DEV workload account; budget alarms in place |
| Operator identity (F6) | Your own AWS CLI profile (`AWS_PROFILE`), never long-lived keys in files. It needs permissions to create and delete everything below. Includes `iam:PassRole` for the EKS cluster, node and Lambda roles and the developer access instance profile. A least-privilege operator role is deferred to Step 3 (finding F10) |
| EKS bootstrap admin role (F6) | An existing IAM role you can assume for kubectl; its ARN goes into the platform root's `bootstrap_admin_role_arn` |
| Local values | Each root's `local.auto.tfvars.example` copied to `local.auto.tfvars` and filled in. Use the same `project` and `aws_account_id` in every root |

Operator permissions by service:
- EC2 and VPC: VPC, subnets, route tables, NAT and Internet gateways, Elastic IPs, VPC endpoints, security groups and rules, instances.
- EKS: cluster, node group, add-ons, access entries.
- IAM: roles, inline policies, attachments, instance profiles, OIDC provider.
- CloudWatch Logs; S3 (buckets, objects, versions); Lambda; API Gateway (HTTP and REST); Cognito; Secrets Manager (metadata).
- ELBv2 (NLB and target group).
- SSM: `ssm:StartSession` on the developer access instance with `AWS-StartPortForwardingSessionToRemoteHost`, and `ssm:GetParameter` on the public AMI parameters.
- STS.

Run every command from the repository root.

## 1. Optional: State bucket

Skip this to keep local State (the DEV default).

```bash
python3 scripts/local-workflow/run.py tfstate apply
```

Then move each root's State into the bucket, as described in the local workflow README:
copy `backend_override.tf.example` and `backend.s3.tfbackend.example`, fill in the
project, then run `run.py <root> migrate-state`.

## 2. Network, platform and developer access

```bash
python3 scripts/local-workflow/run.py network apply
```

```bash
python3 scripts/local-workflow/handoff.py network
```

`handoff.py` writes the network output as `network_reference` into the platform and
developer-access `local.auto.tfvars`, after checking the account.

```bash
python3 scripts/local-workflow/run.py platform apply
```

```bash
python3 scripts/local-workflow/run.py developer-access apply
```

Every `run.py` call runs the offline and live preflight first. The live preflight
checks the caller account, the EKS add-on versions, the node AMI release and the S3
prefix list.

## 3. Reach the private EKS endpoint

```bash
python3 scripts/local-workflow/eks_tunnel.py kubeconfig --role-arn <bootstrap admin role ARN>
```

```bash
python3 scripts/local-workflow/eks_tunnel.py start
```

`kubeconfig` writes `~/.kube/<project>-dev-eks.json`, which points to
`https://127.0.0.1:8443` with `tls-server-name` set to the real endpoint, and stores
no token. `start` keeps a Session Manager port-forwarding session open through the
developer access host. In a second terminal:

```bash
KUBECONFIG=~/.kube/<project>-dev-eks.json kubectl get nodes
```

## 4. Serverless API (finding F2)

```bash
python3 scripts/local-workflow/run.py serverless-api publish-artifact
```

`publish-artifact` does three things:
1. creates the artifact bucket with a confirmed, targeted plan;
2. uploads the committed `function/function.zip`;
3. writes the returned version into `artifact_object_version` in `local.auto.tfvars`.

Then apply the whole root:

```bash
python3 scripts/local-workflow/run.py serverless-api apply
```

The secret `/<project>/dev/secret/app` is created with metadata only (approach A).
`enable_secret_read` is `false` by default. Before you turn it on, register the
value yourself, outside Terraform and without putting it in shell history, for
example from a file you delete afterwards:

```bash
aws secretsmanager put-secret-value --region ca-central-1 --secret-id /<project>/dev/secret/app --secret-string file://secret.json
```

## 5. API (Cognito and REST core)

```bash
python3 scripts/local-workflow/run.py api apply
```

## 6. Kubernetes runtime

This part is still not deployable. The nodes cannot pull the Istio and AWS Load
Balancer Controller images from public registries while node egress stays closed
(finding F18, open). Do not open node egress to the internet to work around it.

What is ready (Step 1 item 6b-A):
- **Object names (F11).** Every object the project creates is named
  `<project>-<purpose>`, for example `<project>-ingress`, `<project>-gateway`,
  `<project>-app` and revision `<project>-v1`. The renderer input carries
  `runtime.project`, which must match the platform's `<project>-dev-eks` cluster and
  `<project>-dev-role-lbc` role. See the
  [input description](../kubernetes/environments/dev/README.md).
- **Certificates and Secrets (F4).** Generate the DEV material on your workstation,
  outside the repository:

  ```bash
  python3 scripts/local-workflow/k8s_certs.py generate --project <project> --backend-hostname <backend hostname> --trust-domain <trust domain> --out ~/.config/<project>-dev-k8s-certs
  ```

  Copy the `runtime` values from its `public.json` into the renderer input. Once
  F18 is resolved, the order is:
  1. render;
  2. apply the namespaces stage;
  3. register the Secrets through the tunnel (§3);
  4. apply the remaining stages in order.

  ```bash
  KUBECONFIG=~/.kube/<project>-dev-eks.json python3 scripts/local-workflow/k8s_certs.py register --project <project> --material ~/.config/<project>-dev-k8s-certs
  ```

  `register` refuses automation and any context other than `<project>-dev-eks`. It
  applies `cacerts`, `aws-load-balancer-controller-tls`, `<project>-gateway-tls` and
  `<project>-gateway-client-cacert` through stdin, and prints no key or certificate.
  Afterwards it deletes the server private keys from the material directory. See the
  [script description](../scripts/local-workflow/README.md#kubernetes-certificates-k8s_certspy)
  for the checks, renewal and `delete`.

## 7. Teardown

Remove everything in reverse order within 72 hours. Two settings change before
their root is destroyed: a protected Cognito user pool, log group, EKS cluster or
NLB blocks `terraform destroy` (finding F19).

1. **API.** Set `deletion_protection = false` in `api/local.auto.tfvars`, then:

   ```bash
   python3 scripts/local-workflow/run.py api apply
   ```

   ```bash
   python3 scripts/local-workflow/run.py api destroy
   ```

2. **Serverless API.**
   - Set `log_deletion_protection = false` in `serverless-api/local.auto.tfvars` and run `run.py serverless-api apply`.
   - Empty the artifact bucket, including every version (`force_destroy` is `false`):

     ```bash
     python3 scripts/local-workflow/empty_bucket.py <project>-dev-s3-artifact
     ```

   - Then run `run.py serverless-api destroy`.
   - The secret is scheduled for deletion with a 7-day recovery window (finding F5). Its name cannot be reused until the window ends. To rebuild inside the window, restore and import the secret instead of creating it again:

     ```bash
     aws secretsmanager restore-secret --region ca-central-1 --secret-id /<project>/dev/secret/app
     ```

     ```bash
     terraform -chdir=infra/services/dev/ca-central-1/serverless-api import module.secret_metadata.aws_secretsmanager_secret.this <secret ARN>
     ```

3. **Developer access.**

   ```bash
   python3 scripts/local-workflow/run.py developer-access destroy
   ```

4. **Platform.** Set `deletion_protection = false` in `platform/local.auto.tfvars`, run `run.py platform apply`, then `run.py platform destroy`.
   The Kubernetes Secrets go with the cluster. If you generated certificate material
   (§6), delete its directory as well, for example `~/.config/<project>-dev-k8s-certs`.

5. **Network.**

   ```bash
   python3 scripts/local-workflow/run.py network destroy
   ```

6. **State bucket**, if used. Move every root back to local State first: delete
   both override files and run `terraform -chdir=<root> init -migrate-state`. Then:

   ```bash
   python3 scripts/local-workflow/empty_bucket.py <project>-dev-s3-tfstate
   ```

   ```bash
   python3 scripts/local-workflow/run.py tfstate destroy
   ```

Finally, confirm that nothing is left:

```bash
aws resourcegroupstaggingapi get-resources --region ca-central-1 --tag-filters Key=project,Values=<project> --query 'ResourceTagMappingList[].ResourceARN'
```

Expect only the secret while it is scheduled for deletion. Also check the AWS
Billing console for running costs.

## 8. Cost drivers

| Resource | Billing basis |
| --- | --- |
| EKS control plane | Hourly |
| Managed node group (`m6i.large`) | Hourly, plus its EBS volume |
| NAT gateway | Hourly plus per GB processed |
| Interface endpoints | 8 in one AZ, each hourly plus per GB |
| Developer access host | `t3.micro`, hourly |
| NLB | Hourly plus capacity units |

Lambda, API Gateway and Cognito charge per use. Tear down promptly; nothing here is
needed when idle.
