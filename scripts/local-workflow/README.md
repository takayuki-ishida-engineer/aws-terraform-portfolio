# Local DEV workflow

Tools for a real DEV plan, apply or destroy from the operator's workstation
([deployment configuration §1–§2](../../docs/deployment-configuration.md#2-local-only-real-deployment)).
Never run them with real AWS credentials in CI, Codex Cloud or other automation.
They refuse to start when `CI`, `GITHUB_ACTIONS`, `CLAUDE_CODE_REMOTE`,
`CODEX_SANDBOX` or `CODEX_SANDBOX_NETWORK_DISABLED` is set, or when an AWS
credential variable holds the cloud session placeholder `proxy-injected`. These
markers are a safety net, not the boundary: the rule itself is in `AGENTS.md`.

| File | Purpose |
| --- | --- |
| `preflight.py` | Offline checks of a root's input values; with `--live`, read-only AWS checks |
| `run.py` | `init` → preflight (offline and live) → saved plan → typed confirmation → apply of that plan; `migrate-state` moves local State into the optional S3 backend |
| `handoff.py` | `network`: writes the applied network output as `network_reference` into the platform and developer-access `local.auto.tfvars` (account checked) |
| `eks_tunnel.py` | `kubeconfig`: kubeconfig for `https://127.0.0.1:<port>` with the real `tls-server-name` and `aws eks get-token`; `start`: Session Manager port forwarding to the private EKS endpoint |
| `empty_bucket.py` | Deletes every object version from `<project>-dev-s3-artifact` or `-tfstate` before teardown, after a typed confirmation |
| `k8s_certs.py` | `generate`: DEV certificates and keys for the Kubernetes runtime, outside the repository (offline); `register`/`delete`: the four runtime Secrets in the `<project>-dev-eks` context (finding F4) |
| `test_local_workflow.py` | Offline self-tests with fake `terraform` and `aws` executables (Full CI) |
| `check_committed_values.py` | Full CI check of the committed values and the preflight against every DEV root |
| `test_k8s_certs.py` | Offline tests of `k8s_certs.py` with real OpenSSL in temporary directories and a fake `kubectl` (Full CI) |

## Prepare a root

1. Copy the root's `local.auto.tfvars.example` to `local.auto.tfvars` (ignored by Git)
   and replace every value. It overrides the placeholders in `terraform.tfvars`.
   Never put a credential or secret value in any tfvars file.
2. Sign in with your own AWS CLI profile for the DEV account, for example
   `export AWS_PROFILE=<your-dev-profile>`. Unset any `AWS_ENDPOINT_URL*` variable.
3. Run the preflight, then the wrapper:

```bash
python3 scripts/local-workflow/preflight.py network --live
```

```bash
python3 scripts/local-workflow/run.py network plan
```

```bash
python3 scripts/local-workflow/run.py network apply
```

Apply in the order `tfstate` (only for the optional S3 backend), `network`,
`registry`, `platform`, `developer-access`, then `serverless-api` and `api`; destroy in the
reverse order. The [DEV runbook](../../docs/dev-runbook.md) gives the complete
sequence, including `run.py serverless-api publish-artifact`, the hand-off, the
EKS tunnel and the teardown switches. The platform and developer-access roots need the network output in their
`local.auto.tfvars` (`terraform -chdir=infra/services/dev/ca-central-1/network output -json network`).
Step 1 item 6 automates that hand-off and the serverless-api artifact upload, and
adds the full runbook.

## What the preflight checks

Offline (no AWS call):

- `local.auto.tfvars` exists in the root, is ignored by Git and is not tracked.
- It assigns every environment-specific input of that root:

  | Root | Environment-specific inputs |
  | --- | --- |
  | network | `project`, `aws_account_id` |
  | platform | `project`, `aws_account_id`, `bootstrap_admin_role_arn`, `network_reference` |
  | serverless-api | `project`, `aws_account_id`, `artifact_object_version` |
  | api | `project`, `aws_account_id`, `callback_urls`, `logout_urls`, `default_redirect_uri` |
  | tfstate | `project`, `aws_account_id` |
  | developer-access | `project`, `aws_account_id`, `network_reference` |
  | registry | `project`, `aws_account_id` |

- No effective value of those inputs is a documented placeholder, an unedited
  example value or the Emulator's synthetic account `000000000000`, and every
  account ID inside them equals `aws_account_id`. Effective values come from
  `terraform console`, so Terraform's own precedence applies; the root must be
  initialized first (`run.py` does this).
- With the optional S3 backend: `backend_override.tf` and `backend.s3.tfbackend` are
  both ignored and untracked, the override holds only an empty `backend "s3" {}`,
  and the settings are exactly `bucket = "<project>-dev-s3-tfstate"`,
  `key = "<project>/dev/ca-central-1/<root>/terraform.tfstate"`,
  `region = "ca-central-1"`, `use_lockfile = true` and `encrypt = true`, with no
  profile, role or credential. The tfstate root must stay local.

Live (`--live`, read-only, workstation only):

- Refused in CI or a cloud session (see above) or when an `AWS_ENDPOINT_URL*` override exists.
- `aws sts get-caller-identity` must return `aws_account_id`.
- With the S3 backend: `aws s3api get-bucket-versioning` must report `Enabled` and
  `aws s3api get-public-access-block` all four settings `true` for the State bucket.
- platform: `aws eks describe-addon-versions` must list each pinned add-on version as
  compatible with `kubernetes_version`, the SSM public parameter for the pinned
  AL2023 node AMI release must exist, and `aws ec2 describe-managed-prefix-lists`
  must return exactly the configured S3 prefix list for
  `node_https_egress_prefix_list_ids`.

Only `sts get-caller-identity`, `s3api get-bucket-versioning`,
`s3api get-public-access-block`, `eks describe-addon-versions`,
`ssm get-parameter` and `ec2 describe-managed-prefix-lists` can be called. The scripts never read, print or store a
credential or secret value.

## Optional S3 backend

1. Apply the bootstrap root: `python3 scripts/local-workflow/run.py tfstate apply`.
2. In a root, copy `backend_override.tf.example` to `backend_override.tf` and
   `backend.s3.tfbackend.example` to `backend.s3.tfbackend`, and replace `project`
   with your project (compare with
   `terraform -chdir=infra/services/dev/ca-central-1/tfstate output -json backend_settings`).
3. Move the root's State:

```bash
python3 scripts/local-workflow/run.py network migrate-state
```

It checks the files, the caller account and the bucket, then runs
`terraform init -backend-config=backend.s3.tfbackend -migrate-state`; Terraform
asks before copying. From then on `run.py` passes the backend settings on every init.

Back to local State: delete both files, then run
`terraform -chdir=<root> init -migrate-state` and confirm. Teardown of the bucket:
every root back on local State (or destroyed), every object version deleted
(`force_destroy` is `false`), then `python3 scripts/local-workflow/run.py tfstate destroy`.

## Saved plans

`run.py` writes the plan to `dev-local.tfplan` inside the root (ignored by Git,
checked before writing), applies exactly that plan after you type the root name,
and deletes it afterwards, because a saved plan can contain sensitive values.

## Kubernetes certificates (`k8s_certs.py`)

The Kubernetes runtime references four Secrets that nothing in the repository or in
Terraform creates (finding F4; [deployment configuration §9](../../docs/deployment-configuration.md#9-step-1-operational-decisions-owner-2026-11-16)):

| Secret | Namespace | Keys | Content |
| --- | --- | --- | --- |
| `cacerts` (name fixed by Istio) | `istio-system` | `ca-cert.pem`, `ca-key.pem`, `root-cert.pem`, `cert-chain.pem` | Istio plug-in CA: an RSA 4096 intermediate (`pathlen:0`) signed by a root whose key is deleted after signing |
| `aws-load-balancer-controller-tls` (name fixed by the chart) | `kube-system` | `ca.crt`, `tls.crt`, `tls.key` | Webhook serving certificate for `aws-load-balancer-controller-webhook-service.kube-system.svc` |
| `<project>-gateway-tls` | `<project>-ingress` | `tls.crt`, `tls.key` | Gateway server certificate for the backend hostname |
| `<project>-gateway-client-cacert` | `<project>-ingress` | `ca.crt` | CA of the client certificates the MUTUAL Gateway accepts (public) |

Generate new material on your workstation, in a new directory outside the
repository (OpenSSL 3 is required; on macOS pass `--openssl` with Homebrew's
`openssl@3`):

```bash
python3 scripts/local-workflow/k8s_certs.py generate --project <project> --backend-hostname <backend hostname> --trust-domain <trust domain> --out ~/.config/<project>-dev-k8s-certs
```

- The directory is 0700 and every file 0600. Validity is 30 days by default and at
  most 90 (`--days`). Each CA signs and is verified with `openssl verify -x509_strict`.
  The root and issuing CA private keys are deleted right after signing; only the
  Istio intermediate key, which istiod signs workload certificates with, is kept.
- `public.json` holds only public values. Its `runtime` object is exactly the
  certificate-derived part of the renderer input: the Secret names,
  `expected_client_spki` (base64 SHA-256 of the client public key, which the Gateway
  pins) and `webhook_ca_bundle` (base64 of the public webhook CA). Copy them into the
  runtime input; the other fields come from the platform outputs and your resource
  choices.
- `client/tls.crt` and `client/tls.key` are the one client identity the Gateway
  accepts, for testing the mTLS path through the tunnel.

With the tunnel running (runbook §3) and the runtime's namespaces stage applied,
register the Secrets:

```bash
KUBECONFIG=~/.kube/<project>-dev-eks.json python3 scripts/local-workflow/k8s_certs.py register --project <project> --material ~/.config/<project>-dev-k8s-certs
```

Run it from the repository, so that it can read the applied platform root's output.
`register` refuses to run in automation (the same markers as above). It requires the
context `<project>-dev-eks` and checks the material before it contacts the cluster:
- the material is complete, owner-only and for this project;
- `public.json` lists exactly the Secret layout (names, namespaces, types, keys) that
  will be sent;
- every certificate is already valid, valid for at most 91 days and for more than a
  day more, and its expiry equals the one `public.json` records;
- `backend_hostname` is a DNS name and the gateway certificate's only SAN; the webhook
  certificate's SANs are exactly the webhook Service names; every SAN is a DNS name;
- every certificate matches its key and chains to its CA;
- `public.json` still matches the certificates (SPKI pin, webhook CA bundle, Secret
  names).

Then, before any Secret leaves the workstation, it reads the platform root's
`platform` output (`terraform output`, as `eks_tunnel.py` does) and
`kubectl config view --minify --raw` for the context. The context must be exactly
the kubeconfig `eks_tunnel.py kubeconfig` writes for that cluster:
- one cluster, context and user, all named `<project>-dev-eks`;
- the API server is the local tunnel `https://127.0.0.1:<port>`;
- TLS verification stays on: `tls-server-name` is the applied cluster's endpoint host,
  `certificate-authority-data` is its CA, and there is no `insecure-skip-tls-verify`,
  CA file, proxy or other cluster field;
- the only credential is `aws eks get-token --cluster-name <project>-dev-eks --region
  ca-central-1`, optionally with `--role-arn`; no token, client key or exec environment.

Any difference stops it before a namespace read. `delete` makes the same check. It then
checks that `istio-system`, `kube-system` and `<project>-ingress` exist, and applies
the Secrets with `kubectl apply --server-side` (no `last-applied` annotation). The Secret data goes through stdin, never through arguments or output.
Only `secret/<name> serverside-applied` lines are printed; any other kubectl output
and every error is redacted. Afterwards it deletes the three server private keys
from the material directory (`--keep-material` keeps them). Delete the directory
when you no longer need the client identity.

Renewal or a new cluster means new material: run `generate` again into a new
directory, update the runtime input from its `public.json`, render, then `register`.
The old CA is no longer trusted. `delete` removes the four Secrets
(`kubectl delete secret --ignore-not-found`); destroying the cluster removes them too.

`test_k8s_certs.py` runs `generate` with real OpenSSL in temporary directories and
`register`/`delete` against a fake `kubectl`. It checks, among other things, that no
key or certificate line reaches arguments or output, that the generated values pass
the renderer's live-input checks, and that the commands are refused in automation.
