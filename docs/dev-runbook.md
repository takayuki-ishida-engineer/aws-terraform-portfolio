# DEV deploy and teardown runbook

Step 1 item 6 of the [step plan](deployment-configuration.md#8-step-plan). It covers
how to build and remove the DEV environment in `ca-central-1` from the operator's
workstation, using the [local workflow](../scripts/local-workflow/README.md).

**Never** run any of it in CI, Codex Cloud or a Claude Code cloud session. The
scripts refuse to start there, and real AWS access is prohibited there
(`AGENTS.md`).

**Not a current execution approval.** This runbook keeps the technical design for a
possible future real deployment. Under Master Policy v14.5 §1.3 and §15, real AWS/EKS
Live verification and enabling real Apply/Destroy are outside the current scope: no
one, the Owner and operators included, plans or runs these steps in the current
portfolio, and their real executability is not guaranteed. A future real scope would
need a new Owner cost and execution decision and independent review. The earlier
conditions (the G01–G07 gates, the cumulative JPY 10,000 DEV limit, teardown within
72 hours) are historical records and authorize nothing.

## 0. Prerequisites

| Item | Requirement |
| --- | --- |
| Tools | Terraform 1.17.x, AWS CLI v2 with the Session Manager plugin, kubectl, Python 3.11 or later, Git, OpenSSL 3 (Kubernetes certificates, §6), skopeo (image mirror, §6) |
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

This part has never been deployed or tested. The nodes cannot pull the Istio and AWS
Load Balancer Controller images from public registries while node egress stays
closed (finding F18, in progress). Do not open node egress to the internet to work
around it. The rendered runtime references the private ECR mirror instead:
`<account>.dkr.ecr.ca-central-1.amazonaws.com/<project>-dev-ecr-<purpose>@<digest>`
(item 6b-B2).

After provisioning, the AWS Load Balancer Controller is configured to reach the
Elastic Load Balancing (ELBv2) API by private DNS through the network root's
`elasticloadbalancing` interface endpoint in `private1` (finding F21). It uses that
path to register and deregister Pod IPs in the target group that Terraform
(`private_ingress`) owns, through TargetGroupBinding. The actual communication is
not verified: no controller call through this endpoint has been made in AWS or in
the Emulator.

The `registry` root (item 6b-B1) creates one private repository per purpose in
`kubernetes/images.lock.json`: immutable tags, AES-256, no repository or lifecycle
policy. Apply it:

```bash
python3 scripts/local-workflow/run.py registry apply
```

Then copy the pinned images into the repositories with `mirror_images.py` (item
6b-B3). It is code only: it has never been run against AWS, a registry or real
images. The default command is an offline plan:

```bash
python3 scripts/local-workflow/mirror_images.py
```

```bash
python3 scripts/local-workflow/mirror_images.py mirror --project <project> --account-id <account ID>
```

`mirror` needs skopeo. It checks the lock, the registry root, the caller account,
the repositories and each upstream tag before it copies, and verifies every index
digest, platform and child manifest afterwards. It never creates or deletes a
repository or an image. See the
[script description](../scripts/local-workflow/README.md#image-mirror-mirror_imagespy)
for the checks, re-runs and recovery.

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

  Build the renderer input from the applied outputs, its `public.json` and your
  resource selections, and show the staged plan (item 6c-A, code only, nothing is
  applied):

  ```bash
  python3 scripts/local-workflow/k8s_runtime_input.py --project <project> --account-id <account ID> --material ~/.config/<project>-dev-k8s-certs --selections ~/.config/<project>-dev-runtime-selections.json --out-dir ~/.config/<project>-dev-runtime-input
  ```

  ```bash
  python3 scripts/local-workflow/k8s_runtime.py plan --input ~/.config/<project>-dev-runtime-input/runtime-input.json --helm <pinned helm>
  ```

  With the tunnel running (§3), read the cluster's state without changing anything
  (item 6c-B1):

  ```bash
  KUBECONFIG=~/.kube/<project>-dev-eks.json python3 scripts/local-workflow/k8s_runtime.py status --input ~/.config/<project>-dev-runtime-input/runtime-input.json --helm <pinned helm>
  ```

  `status` refuses automation and stops unless the input, the applied outputs, the
  kubeconfig and the server version agree. It reports each object as present,
  missing or unknown, with its generation and readiness, and exits 3 when anything
  could not be determined.
  See the [script description](../scripts/local-workflow/README.md#kubernetes-runtime-input-and-plan-k8s_runtime_inputpy-k8s_runtimepy).
  Applying the stages is not implemented yet (no `apply`), and the ingress stage is
  blocked until the binding-writer method is approved. The apply and destroy design
  and its open Owner decisions are in the
  [6c-B2 design record](k8s-runtime-apply-destroy-design.md). Passing the offline
  checks does not make an apply against the cluster allowed. Once F18 is resolved
  and apply exists, the order is:
  1. render;
  2. apply the namespaces stage;
  3. register the Secrets through the tunnel (§3);
  4. apply the remaining stages in order.

  ```bash
  KUBECONFIG=~/.kube/<project>-dev-eks.json python3 scripts/local-workflow/k8s_certs.py register --project <project> --material ~/.config/<project>-dev-k8s-certs
  ```

  `register` refuses automation and any context other than `<project>-dev-eks`. It
  checks the material against its `public.json`, and the context against the
  applied platform output: the tunnel as API server, the cluster's own CA and
  endpoint host, and `aws eks get-token` for that cluster. It applies `cacerts`, `aws-load-balancer-controller-tls`, `<project>-gateway-tls` and
  `<project>-gateway-client-cacert` through stdin, and prints no key or certificate.
  Afterwards it deletes the server private keys from the material directory. See the
  [script description](../scripts/local-workflow/README.md#kubernetes-certificates-k8s_certspy)
  for the checks, renewal and `delete`.

## 7. Teardown

Remove everything in reverse order within 72 hours. Two settings change before
their root is destroyed: a protected Cognito user pool, log group, EKS cluster or
NLB blocks `terraform destroy` (finding F19).

The Kubernetes runtime has no destroy command yet, so this procedure removes it
with the cluster in step 4. The [6c-B2 design record](k8s-runtime-apply-destroy-design.md#12-complete-teardown-order-d12)
plans a runtime destroy between steps 2 and 3, while the tunnel, the AWS Load
Balancer Controller, its IAM role, the target group and the endpoints still exist:
- delete the TargetGroupBinding and wait for its finalizer and target
  deregistration;
- then the remaining stages;
- then the Secret cleanup.

That step is not implemented as an operation and needs Owner approval. A Fake-only
destroy engine exists as Source/Offline code (`k8s_runtime_destroy.py`, item 6c-B4b):
it implements this order against a fake API server only (the TargetGroupBinding first,
then the remaining stages in reverse with the D12 gates, the G9 Secret cleanup, then
the namespaces; the 17 CRDs and `kube-system` are kept). It is not a procedure:
`k8s_runtime.py destroy` still refuses, there is no real transport, and its Fake
COMPLETE is never evidence that a real teardown works. The Terraform roots the
TargetGroupBinding depends on (platform with the controller's IAM role and the target
group, network with the ELBv2 and STS endpoints, developer-access with the tunnel) are
outside it and must still exist when a future runtime destroy runs. Until a real one
is approved:
- never strip a finalizer;
- `k8s_certs.py delete` is retired and refuses (G9, finding F22). The safe cleanup
  (`k8s_certs_receipt.cleanup`) is Source/Offline only, with no real transport, so
  there is no real Secret cleanup yet and no namespace may be deleted while a
  Secret remains (D18);
- target deregistration is NOT_VERIFIED.

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

5. **Registry**, if applied. A repository that still holds images is not deleted
   unless the teardown switch is set: put `force_delete = true` in
   `registry/local.auto.tfvars`, run `run.py registry apply`, then
   `run.py registry destroy`. This switch is the only approved way to delete the
   mirrored images.

6. **Network.**

   ```bash
   python3 scripts/local-workflow/run.py network destroy
   ```

7. **State bucket**, if used. Move every root back to local State first: delete
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

Deleting the EKS cluster alone does not complete the teardown. Teardown is
complete only when all of these hold:
- every root's `terraform state list` is empty;
- the tag search above shows only the scheduled secret;
- the resource types a tag search may miss have been checked one by one: the
  cluster, the load balancer and target group, IAM roles, EKS-created security
  groups and network interfaces, log groups, ECR repositories, S3 buckets and VPC
  endpoints (design record §12);
- the local kubeconfig, runtime input and certificate material have been removed.

## 8. Cost drivers

| Resource | Billing basis |
| --- | --- |
| EKS control plane | Hourly |
| Managed node group (`m6i.large`) | Hourly, plus its EBS volume |
| NAT gateway | Hourly plus per GB processed |
| Interface endpoints | 9 in one AZ (`ec2`, `ec2messages`, `ecr.api`, `ecr.dkr`, `elasticloadbalancing`, `logs`, `ssm`, `ssmmessages`, `sts`), each hourly plus per GB. `elasticloadbalancing` (finding F21) adds one endpoint-hour from the network apply until its destroy |
| ECR private repositories (`registry` root) | Storage per GB-month of the mirrored images. If the account's registry-level enhanced scanning is on, Amazon Inspector may also charge for scanning them. The image sizes, the ca-central-1 price and the effective scanning configuration are not yet verified |
| Developer access host | `t3.micro`, hourly |
| NLB | Hourly plus capacity units |

Lambda, API Gateway and Cognito charge per use. Tear down promptly; nothing here is
needed when idle.
