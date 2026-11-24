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
| `mirror_images.py` | `plan` (default, offline): verifies `kubernetes/images.lock.json` and prints the copy plan; `mirror`: copies the three locked images into the `registry` root's private ECR repositories and verifies them (finding F18) |
| `test_mirror_images.py` | Offline tests of `mirror_images.py` with fake `aws`, `skopeo` and `terraform` executables, and source mutations of its guards (Full CI) |
| `k8s_runtime_input.py` | Builds the Kubernetes runtime renderer input from the applied root outputs, `public.json` and the operator's resource selections, cross-checked, outside the repository (item 6c-A) |
| `k8s_runtime.py` | `plan` (offline): renders and validates the runtime with the pinned Helm and shows the 9 apply stages, their objects, actors, Secrets, prerequisites and readiness conditions; executes nothing (item 6c-A). `status` (workstation only, read-only): the state of the 62 objects in the `<project>-dev-eks` cluster after a preflight safety gate (item 6c-B1) |
| `test_k8s_runtime.py` | Offline tests of both with a fake `terraform`, synthetic `public.json` and the pinned Helm, and source mutations of their guards (Full CI) |
| `test_k8s_runtime_status.py` | Offline tests of `status` with a fake `kubectl` serving a synthetic cluster, and source mutations of its guards (Full CI) |

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
The old CA is no longer trusted. Destroying the cluster removes the Secrets.

`delete` is retired (G9, finding F22, Owner decision 2026-11-24). It used to delete
by name (`kubectl delete secret --ignore-not-found`) without a UID check. It now
refuses on every path (`name_based_delete_retired`) and never reads the kubeconfig
or runs kubectl; automation is still refused first (`live_refused_*`). The safe
replacement, `k8s_certs_receipt.cleanup`, is Source/Offline only (see
[below](#registration-uid-receipt-and-safe-secret-cleanup-g9-d19-fake-only)), so no
real Secret cleanup exists yet. The real `register` is unchanged and writes no UID
receipt.

`test_k8s_certs.py` runs `generate` with real OpenSSL in temporary directories and
`register` against a fake `kubectl`, and checks that `delete` and the CLI `delete`
refuse without running kubectl. It checks, among other things, that no
key or certificate line reaches arguments or output, that the generated values pass
the renderer's live-input checks, and that the commands are refused in automation.

## Kubernetes runtime input and plan (`k8s_runtime_input.py`, `k8s_runtime.py`)

Step 1 items 6c-A and 6c-B1. Code only: nothing here has been run against a real
cluster or AWS account. `status` only reads; `apply` and `destroy` do not exist yet,
so nothing is applied.

### Build the input (workstation only)

```bash
cp kubernetes/environments/dev/runtime-selections.example.json ~/.config/<project>-dev-runtime-selections.json
```

Choose the controller, istiod and gateway requests and limits in that copy and set
`project`; every `REPLACE` value is refused. Then:

```bash
python3 scripts/local-workflow/k8s_runtime_input.py --project <project> --account-id <account ID> --material ~/.config/<project>-dev-k8s-certs --selections ~/.config/<project>-dev-runtime-selections.json --out-dir ~/.config/<project>-dev-runtime-input
```

It is refused in CI, in cloud sessions, with the placeholder credentials and with an
AWS endpoint override, before any tool starts. It reads exactly four Terraform
outputs with `terraform output -json <name>`, never the State:

- `controller_identity` (platform root), all 11 fields unchanged;
- `platform` (platform root), for the cluster name and ARN and the OIDC issuer and
  provider;
- `private_ingress` (platform root), projected to `interface_version`, `scope`,
  `target_group_arn`, `vpc_id` and `backend_target_port`;
- `network` (network root), for the VPC ID.

From the material directory it reads only `public.json` and the public
`webhook/ca.crt`. No private key is opened, and the Secret data and tokens never
reach the input, the provenance record or the output.

Before writing, it refuses:
- a scope that is not dev, aws, ca-central-1 and the given account, in any of the
  four outputs;
- a cluster other than `<project>-dev-eks`, or a cluster ARN, controller role or
  target group in another account;
- OIDC values that differ between `controller_identity` and `platform`;
- a target group ARN that differs between `controller_identity` and
  `private_ingress`, or a VPC ID that differs from the network output;
- missing or extra `controller_identity` fields;
- a `public.json` for another project, with other Secret names or layout, with a
  `not_after` date within a day, with a webhook CA that differs from
  `webhook/ca.crt`, or that contains a private key;
- selections for another project, with a placeholder or with requests above limits;
- placeholder projects and accounts;
- an output directory inside the repository or not empty. The directory is 0700
  and the files 0600.

The result must pass the renderer's own input contract. The directory then holds
`runtime-input.json` and `provenance.json`. The provenance record holds:
- the input's SHA-256;
- the root, output name and canonical SHA-256 of each of the four Terraform outputs,
  exactly as `terraform output` returned them;
- which output or file each section came from, with file SHA-256;
- the cross-checks made and what was not verified.

Verification boundaries, also recorded there:
- **State freshness: NOT_VERIFIED.** `terraform output` returns the values recorded
  at the last apply; it does not prove that the State matches the live resources.
- **Certificates:** only the `not_after` dates recorded in `public.json` are
  checked. The X.509 certificates are not read or verified by this tool;
  `k8s_certs.py register` re-checks the certificates, keys and chains against the
  material before it applies the Secrets.
- `kubernetes_version` is the requested Terraform value, not the server version.
- The referenced AWS resources are not checked for existence or reachability.

### Plan (offline, anywhere)

```bash
python3 scripts/local-workflow/k8s_runtime.py plan --input ~/.config/<project>-dev-runtime-input/runtime-input.json --helm <pinned helm>
```

`plan` renders with the pinned Helm (`kubernetes/tools/install_helm.py`), runs the
existing validator and re-checks the render evidence (contract version 5, image lock,
pinned Helm and charts, input and manifest SHA-256). It then cuts the bundle into the
9 stages of [`kubernetes/tests/expected-stages.json`](../../kubernetes/tests/expected-stages.json):
namespaces 2, base 16, controller 13, istiod 12, gateway 5, mesh_security 5,
admission 4, binding_writer 3, ingress 2. Each stage must hold exactly the reviewed
apiVersion, kind, namespace and name of its objects, in the reviewed order, not just
the same count or the same set. The stages together must equal
`kubernetes/tests/expected-inventory.json`. Secrets and
cluster-admin bindings are refused, and kinds may appear only in their own stage
(for example the TargetGroupBinding only in ingress).

For every stage it shows:
- the objects;
- the actor: the operator for everything but the TargetGroupBinding, whose actor
  is `system:serviceaccount:<project>-ingress:<project>-binding-writer`;
- the k8s_certs Secrets that must exist first;
- the prerequisites and the readiness conditions.

How the operator acts as the binding-writer ServiceAccount is not approved:
impersonation on the current EKS cluster is NOT_TESTED, and TokenRequest is not
approved. The ingress stage is therefore shown as BLOCKED.

`--fixture` plans the synthetic fixture, and `--format json` prints the report. The
only process `plan` starts is the pinned Helm. It contacts no cluster and no AWS API.

### Tests

`test_k8s_runtime.py` (Full CI, 29 tests) builds the input from a fake `terraform`
and a synthetic material directory whose key files hold a marker that must never be
read or shown. It covers:
- every mismatch above, the CI and cloud refusals and the file modes;
- an end-to-end plan of the built input with the pinned Helm;
- the fixture plan, with only Helm allowed to start;
- stage tampering with unchanged counts: a swapped or moved object, two objects
  swapped inside one stage (same set), a changed apiVersion, namespace or name, a
  disguised Secret, a cluster-admin binding;
- the provenance record: the output digests, State freshness NOT_VERIFIED and the
  certificate boundary;
- evidence and stage table tampering, and a skipped validator.

39 source mutations each remove one guard, and every one must be detected.

### Status (read-only, workstation only)

Start the tunnel first (§3 of the runbook), then:

```bash
KUBECONFIG=~/.kube/<project>-dev-eks.json python3 scripts/local-workflow/k8s_runtime.py status --input ~/.config/<project>-dev-runtime-input/runtime-input.json --helm <pinned helm>
```

`--format json` prints the report. `--timeout` sets the per-request limit (5 to 120
seconds, default 20). `--context` may only name `<project>-dev-eks`.

**Preflight safety gate.** Before any object is read, `status` stops (exit 2) or
refuses (exit 1) unless all of these hold:

1. It is not run in CI, in a Claude Code or Codex cloud session, with the
   placeholder credentials or with an AWS endpoint override. This is checked before
   any tool starts.
2. The input is operational (`fixture: false`) and passes the renderer contract.
   The context is exactly `<project>-dev-eks`; a foreign context is refused before
   rendering.
3. The input renders, validates and splits into the 9 reviewed stages exactly as
   `plan` does (same code), so the input, the manifest and the expected inventory
   agree.
4. The four applied Terraform outputs pass the same cross-checks as
   `k8s_runtime_input.py`: dev, the input's account, ca-central-1, the cluster
   `<project>-dev-eks`, OIDC, controller role, target group and VPC. The input's
   `controller_identity` and `private_ingress` must equal them.
5. The context is exactly the kubeconfig that `eks_tunnel.py kubeconfig` writes for
   the applied cluster: the loopback tunnel as API server, the cluster's own CA and
   endpoint host, and `aws eks get-token` for that cluster. Static tokens, client
   keys, `insecure-skip-tls-verify` and any other server are refused (the same check
   as `k8s_certs.py register`).
6. The server's major.minor version equals the input's `kubernetes_version`.

**Read-only commands.** Every kubectl call has the form
`kubectl --context <project>-dev-eks --request-timeout=<n>s <command>`, and
`<command>` is one of exactly three shapes:
- `config view --minify --raw -o json`;
- `version -o json`;
- `get <kind.version.group> <name> [-n <namespace>] --ignore-not-found -o json`.

For `get`, the resource type must be one of the 19 types of the reviewed inventory,
spelled exactly as `kind.version.group`. The name and namespace must be valid
Kubernetes names that cannot start with `-`. The object must be one of the 62
objects of this bundle. Anything else is refused before it starts, including:
- `apply`, `delete`, `patch`, `create` and `auth`;
- any read of a Secret, through `secret`, `secrets` or any `secret.*` or
  `secrets.*` spelling;
- other resource types or aliases (`pod`, `all`, `sa`, plural forms);
- `-A` and `--all-namespaces`, and flags placed where the name or namespace belongs;
- `--as`, `--as-group`, `--token`, `--server`, `--kubeconfig` and
  `--insecure-skip-tls-verify`.

kubectl's output and error text are never printed. Only fixed codes are shown.

**Output contract.** For each of the 62 objects, in stage order:
- identity: `apiVersion`, `kind`, `namespace`, `name`, `stage`, and `actor` (the
  operator, or the binding-writer ServiceAccount for the TargetGroupBinding);
- `presence`: `PRESENT`, `MISSING` or `UNKNOWN`;
- `generation`, `observed_generation`, and `observed`: true or false, or null where
  the kind has no status generation;
- `readiness`:
  - `READY`: the observed Kubernetes conditions are met (Namespace Active; CRD
    Established and NamesAccepted; Deployment Available with every replica updated,
    ready and available and the generation observed; ValidatingAdmissionPolicy
    observed without type-checking warnings). An object with
    `metadata.deletionTimestamp` is never `READY`; it is `NOT_READY` with the reason
    `deletion_pending`;
  - `NOT_READY`;
  - `NOT_APPLICABLE`: the kind has no readiness condition, so only its existence is
    checked;
  - `NOT_VERIFIABLE`: the TargetGroupBinding, because target registration and
    health are NOT_TESTED;
  - `UNKNOWN`;
- `reasons`: fixed codes, for example `missing`, `generation_not_observed`,
  `deployment_not_available`, `crd_not_established`, `identity_mismatch`,
  `api_forbidden`, `api_unreachable`, `api_timeout`, `incomplete_response`.

Each stage reports what was observed and, separately, whether it may be executed:
- `state`, the observation only:
  - `OBSERVED_CONDITIONS_MET`: every object exists, and every condition status can
    observe is met. It is not readiness for apply;
  - `NOT_READY`, `PARTIAL`, `NOT_APPLIED`;
  - `UNKNOWN`, whenever any object in the stage is unknown;
  - `UNVERIFIED`: the ingress stage once the TargetGroupBinding exists, because its
    target health cannot be checked.
- `unverified_conditions`: what status does not observe for the stage, for example
  webhook endpoint serving, the k8s_certs Secrets, running Pod image digests,
  injection, field ownership and drift, and target registration and health.
- `execution_gate`, independent of the observation:
  - `BLOCKED` for ingress, whether or not the TargetGroupBinding exists, until the
    Owner approves the binding-writer method;
  - `NOT_AVAILABLE` for every other stage, because `apply` is not implemented.

The report-level `execution_gate` records:
- ingress `BLOCKED`;
- impersonation `NOT_TESTED`, TokenRequest `NOT_APPROVED`, live RBAC `NOT_TESTED`;
- F21 target registration and health `NOT_TESTED`;
- `status_is_sufficient_for_apply: false`.

A status result is never a sufficient condition for a future apply.

**Exit codes.**
- `0`: every object's state was determined. This is not the same as ready.
- `1`: refused.
- `2`: stopped by the gate.
- `3`: incomplete, because at least one object is unknown. A state that cannot be
  determined is never reported as success.

**What a report does and does not show.** Existing, observed and ready are separate
facts, and none of them shows that the application or network works.
- `runtime_ready` is always false.
- `functional` is always `NOT_TESTED`.
- `status` does not check, and lists as not checked:
  - Secret presence and contents (Secrets are never read);
  - Pod image digests;
  - webhook serving and admission behaviour;
  - binding-writer RBAC and impersonation;
  - target registration and health (F21);
  - application and network behaviour.

### Receipt, crash recovery and transport boundary (item 6c-B3a, offline foundation)

6c-B3a adds the safety foundation that a later `apply` and `destroy` will use. It
implements the Owner decisions of 2026-11-22, for Source/Offline use only:
- **D7**: ownership is identity, UID, receipt and field ownership together;
- **D8**: conflicts are never forced;
- **D10**: a different manifest, input or version stops;
- **D16**: no automatic quarantine release or adoption;
- **D17**: the cluster ARN plus the `kube-system` namespace UID;
- **D19**: the transport interface and a fake only;
- **D3**, in part: reading the `kube-system` namespace for the fingerprint.

It enables nothing. `apply` and `destroy` exist only to refuse
(`operation_not_approved`, exit 1) before any argument, input or tool is touched.
There is no recovery, release or adoption command.

**`k8s_runtime_receipt.py`: store and journal.**
- **Location.** One directory per cluster fingerprint, outside the repository. The
  default root is `~/.local/state/<project>-k8s-runtime/`.
  - Directory 0700 and files 0600, owned by the current user.
  - Symlinks, other owners and group or other permissions are refused.
  - Files are opened with `O_NOFOLLOW` and re-checked after opening.
  - Writers hold an exclusive `flock`.
- **`journal.jsonl`.** Write-ahead and append-only.
  - Canonical JSON lines, each fsynced and chained to the previous line by SHA-256.
  - Records: HEADER (project, fingerprint, pinned manifest and input SHA-256),
    INTENT (before an object is applied), RESULT (the UID read back), STAGE_DONE
    and QUARANTINE.
  - Every field is allowlisted and validated, and every write is checked by
    replaying the journal before it reaches the disk.
  - Refused before writing: Secret identities, unknown fields (such as a manifest
    `spec`), control characters, and values that look like keys, tokens or encoded
    blobs. So no Secret value, token, kubeconfig or manifest body can be stored.
- **`receipt.json`.** A snapshot of the journal, replaced atomically (temporary
  file, fsync, rename, directory fsync).
  - The journal wins. A snapshot behind the journal (a crash between the two
    writes) is STALE, and the writer refreshes it under the lock.
  - A missing snapshot is recreated only when the journal holds nothing but a
    verified HEADER, after its fingerprint and pins are checked (a crash right
    after the first write). With any INTENT, RESULT or other record it stays
    missing, and the run stops (`receipt_snapshot_missing`).
  - An inconsistent snapshot is never regenerated. `receipt verify` never repairs
    anything.
  - A missing journal is never a fresh start. A new journal is created only in a
    directory that the writing Store has just created and that holds nothing but
    its lock file.
    - "Just created" means the Store's own atomic `mkdir` succeeded. A directory
      another process created, even a moment earlier, does not count.
    - The permission is used at most once, and it is consumed before the first
      write. So the same Store never initialises twice, even after a failed write
      or after both files disappear.
    - A journal missing next to a snapshot stops (`journal_missing`), and the
      snapshot bytes are left untouched.
    - An older directory with neither file stops (`receipt_directory_not_new`).
      The operator must investigate; nothing is recreated automatically.
    - A corrupt journal stops and is never replaced.
  - A snapshot ahead of the journal is `journal_truncated`; any other difference is
    `receipt_journal_mismatch`.
- **Journal rules.** Every one stops on violation:
  - one open INTENT at a time, with consecutive sequence numbers;
  - a RESULT only for the open INTENT;
  - stages in plan order;
  - STAGE_DONE only when every object of the stage has a RESULT;
  - an "owned" prior state only with the UID the journal recorded
    (`adoption_refused`);
  - no INTENT for a quarantined object (`quarantined`). There is no release record
    type, and `release_quarantine` and `adopt` always refuse.

**Crash reconciliation (`reconcile`, read-only).** Every planned object is
classified against the journal and an observation (presence, UID, field managers):

| Verdict | Meaning |
| --- | --- |
| `CONSISTENT` | Recorded UID equals the live UID, and the runtime manager `<project>-k8s-runtime` has the only managedFields entry, an Apply |
| `ABSENT` | Never recorded and not present |
| `NOT_APPLIED` | An unfinished INTENT whose object is absent |
| `REAPPLY_SAFE` | An unfinished update whose live UID equals the recorded UID, with the runtime Apply entry as the only manager. With the same UID, no runtime Apply entry is `NOT_OWNED` and other managers are `OWNERSHIP_NOT_VERIFIED` |
| `QUARANTINE_REQUIRED` | An object exists whose creation the journal cannot prove |
| `UID_CHANGED` | The live UID differs from the recorded one, or the object is gone |
| `NOT_OWNED` | Present but never recorded; never adopted |
| `OWNERSHIP_NOT_VERIFIED` | The runtime Apply entry plus other managers; the allowed-manager table (D13) is not decided |
| `QUARANTINED` | Quarantined in the journal |
| `UNKNOWN` | The observation failed |

Only `CONSISTENT` and `ABSENT` are settled. A manager name alone never proves
ownership.

**`k8s_runtime.py receipt verify` (read-only).**

```bash
python3 scripts/local-workflow/k8s_runtime.py receipt verify --input <runtime-input.json> --helm <pinned helm> --receipt-dir ~/.local/state/<project>-k8s-runtime/<fingerprint id> --expect-manifest-sha256 <from plan> --expect-input-sha256 <from plan> [--cluster]
```

- **Pins.** It re-renders the plan. The given SHA-256 values must equal the plan
  exactly (`sha_mismatch`, `sha_pin_invalid`), and so must the receipt's HEADER
  (`bundle_changed`, D10).
- **Offline.** It validates:
  - the store's safety (location, modes, owner, symlinks);
  - the chain, schema, journal rules and snapshot;
  - the project and the directory name against the HEADER fingerprint.
- **`--cluster`** (workstation only; refused in CI and cloud sessions).
  - It passes the `status` preflight gate.
  - It reads the `kube-system` namespace once for the fingerprint. This is the only
    read outside the 62 objects, and `status` still cannot make it.
  - A receipt for another cluster stops (`fingerprint_mismatch`).
  - It reconciles every planned object with read-only `kubectl get`.
- **Writes nothing.** It never creates, refreshes, quarantines, adopts or releases.
- **Exit codes:**

  | Code | Meaning |
  | --- | --- |
  | 0 | Settled |
  | 1 | Refused |
  | 2 | Stopped: unsafe, missing, tampered or mismatched receipt, preflight or pins |
  | 3 | Attention required: a STALE snapshot, an open INTENT, a quarantine, or any unsettled verdict |

**`k8s_runtime_transport.py`: D19 transport boundary, contract only.**
- **Requests.** It builds exactly two request shapes, and only for allowlisted
  identities:
  - a metadata-only GET with
    `Accept: application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1`;
  - a DELETE whose body is `DeleteOptions` with `preconditions.uid`.
- **Responses.**
  - A metadata response must be a `PartialObjectMetadata` for the requested object,
    within 1 MiB, and without `data`, `stringData`, `spec` or `status`.
  - A DELETE answered 409 is `uid_precondition_failed`, never success.
- **Secrets** (G9, Owner decision D19/G9 2026-11-24, Fake-only): only the four
  `k8s_certs.py` Secret identities of the policy's `secret_project`
  (`secret_identities`), for a metadata GET and a UID-precondition DELETE. Any other
  Secret, namespace or project is `secret_path_not_approved`; a policy without
  `secret_project` refuses every Secret. A Secret metadata response with the
  `last-applied-configuration` annotation is refused, and only name, namespace,
  UID, labels, managedFields and resourceVersion are returned. Metadata LIST,
  discovery and inventory reads do not exist (D3, D19, before 6c-B4).
- **No network code.** The module has no socket, TLS, HTTP or token code; a test
  checks the imports. Opening or constructing a real transport is refused
  (`real_transport_not_implemented`); only `FakeTransport` exists, for tests.
- **Not implemented.** `UNIMPLEMENTED_REQUIREMENTS` lists what the real transport
  must satisfy before it can be approved:
  - TLS against the kubeconfig CA, and SNI equal to `tls-server-name` through the
    tunnel;
  - the token from `aws eks get-token`, held in memory only;
  - the exact request bodies;
  - response validation;
  - bounded timeouts;
  - Secrets only as the G9 contract above.

**Tests.** `test_k8s_runtime_receipt.py` expects 144 tests and 382 source mutations, each
required to be detected: 39 tests and 58 mutations of its own, the 27 tests and 67 mutations of
`test_k8s_certs_receipt.py`, the 36 tests and 144 mutations of
`test_k8s_runtime_destroy_foundation.py` and the 42 tests and 113 mutations of
`test_k8s_runtime_destroy.py` (all below), whose classes it imports. It uses temporary stores outside the repository, the fake transport, and
for `--cluster` the fake kubectl of the status tests. It covers:
- modes, symlinks and owners;
- the repository location and the lock;
- Secret, token and extra-field writes;
- pins and fingerprint;
- a missing receipt and a missing snapshot;
- chain, canonical-form and value tampering, a truncated line, a truncated journal
  and a snapshot mismatch;
- a crash between journal and snapshot (STALE, then refreshed by the writer);
- a crash between the HEADER and the first snapshot: recreated only for a verified
  HEADER-only journal, never with other records, never over an inconsistent
  snapshot, and never by `receipt verify`;
- a missing journal next to a snapshot, an existing directory without either file,
  a non-empty new directory and a corrupt journal: none is reinitialised or
  overwritten;
- the same Store after both files vanish (HEADER-only or full journal), a failed
  first write, and a directory created concurrently by another process: none
  re-grants initialisation;
- a crash between INTENT and RESULT, and `REAPPLY_SAFE` only with both the UID and
  the runtime's field ownership;
- UID changes, quarantine without release, adoption refusal and field-manager
  ownership;
- journal ordering;
- transport request, response and real-transport refusal;
- apply and destroy refusal;
- the fingerprint read scope;
- offline and cluster verify, including the automation refusal.

**Not covered here (later items, separate approval):**
- the real transport and any real GET or DELETE (D19);
- `apply` (6c-B3b) and `destroy` (6c-B4);
- the allowed-manager table (D13);
- the remaining read scope (D3);
- Secret cleanup against a real cluster (G9 is Fake-only, below);
- the Istio `caBundle` renderer change (C1).

### Destroy safety foundation (item 6c-B4a, Fake-only, merged as PR #100)

Owner decisions D3, D5, D6, D11, D12 and the remaining D19 scope (2026-11-24). The
contracts below are the transport and journal foundation; the Fake-only engine that
orchestrates them is 6c-B4b (next section), and the real `destroy` command still
refuses (`operation_not_approved`).

**Transport scopes (`k8s_runtime_transport.DestroyPolicy`).** Built only from the
reviewed plan and the receipt, immutable, and never widened by what a read returns:
- single-object metadata read: the plan's identities and `kube-system`
  (`destroy_metadata_request`, finalizers and `deletionTimestamp` through
  `object_state`);
- discovery: `GET /api`, `/apis` and each advertised group version, only with
  `discovery=True`;
- namespace LIST: `istio-system`, `<project>-ingress`, `<project>-app` only, with
  `inventory=True`; `kube-system` and any other namespace are refused;
- CRD instance LIST and the specialised CRD read: the reviewed CRDs given with their
  manifest fields (`crd_spec_from_manifest`);
- specialised Service read: `spec.type` of the runtime's `<project>-ingress` Services;
- runtime DELETE: identity → UID proven by the receipt; never a CRD, a Secret or the
  `kube-system` namespace, never another UID (`delete_uid_not_proven`);
- the G9 Secret GET and DELETE stay in `Policy(secret_project=...)`, unchanged.

**The send boundary (review of PR #100).** `FakeDestroyTransport.send` is the only
way to the server. It refuses after the global `Deadline`, then `authorize` requires the
request to equal, field for field (method, path, query, headers, body), the request a
builder makes for this policy and this transport's own evidence; anything else, including
a raw request for a CRD, `kube-system`, a Secret, an unowned object or another UID, a full
object, an undiscovered LIST or a changed header or query, is `request_not_authorized` and
never reaches the server. Each request is bounded by its own D11 timeout or the remaining
global time, whichever is less; a later answer is `request_timeout` or `deadline_exceeded`,
never evidence, and the fake API's own timeout is `transport_timeout`. `check_request`
still refuses any method other than GET and DELETE, a collection DELETE, a query other
than `limit` and `continue`, and DeleteOptions other than exactly the UID precondition with
`propagationPolicy: Background`. The generic `Policy` can no longer name a CRD or the
`kube-system` namespace for deletion. `open_destroy_transport` opens only the fake and
needs the policy, the server and the deadline; the policy's inputs come from
`k8s_runtime_receipt.plan_identities` and `owned_uids`.

**Evidence.** Discovery, CRD read and CRD verification results that later requests depend
on are `Evidence`: issued by one transport for one policy, sealed and immutable. A builder
accepts only evidence for its policy and kind with an intact seal; the transport accepts
only evidence it issued and has not withdrawn (a new discovery withdraws the old one).
Hand-made, copied, re-bound, edited or re-sealed evidence is `evidence_invalid`.

**Second review (R01–R04).**
- CRD verification is bound to the receipt: the policy holds two separate maps from a
  verified journal, the runtime DELETE map (`owned_uids`, never a CRD) and the CRD
  verification map (`crd_receipt_uids`: owned, not quarantined CRDs; never a DELETE).
  `verify_crd` uses the policy's CRD receipt UID as the only ownership evidence; no entry
  (`crd_not_owned_by_receipt`), a different caller UID (`crd_receipt_uid_mismatch`) or a
  different observed UID (`crd_uid_mismatch`) is BLOCKED with no evidence. Every new read
  of a CRD withdraws its earlier read and verification evidence first, whatever the read
  finds or if it fails; only a verification of the latest read allows the instance LIST
  again, at the send boundary too.
- Discovery requires the core v1 `secrets`, `services`, `configmaps`, `pods` and
  `serviceaccounts`, each namespaced, listable and mapped to its kind; every resource entry
  needs a kind and well-formed, unique verbs. Otherwise no discovery evidence is issued, so
  no namespace inventory can complete. This never proves a real server's discovery
  complete.
- The global deadline is checked on its own after every answer: an answer at or after it is
  `deadline_exceeded` (never a deletion or a COMPLETE list, also in `collect_list`), while
  the request's own 20 s bound stays inclusive (`request_timeout` beyond it).
- `merge_listed` also requires one UID per logical identity (resource or the approved event
  alias, namespace, name) across versions (`cross_version_identity_conflict`); different
  resources may share a name.

**Final correction (R01-R).** The invalidation is enforced at the final send boundary.
Every authorised request on the CRD path, either the specialised CRD GET or the metadata
GET of the CRD identity, sent by `read_crd`, `get_metadata` or a raw `send`, withdraws
that CRD's issued read and verification evidence and its verified mark before it reaches
the server. Every authorised discovery GET withdraws the discovery evidence and the
discovered targets the same way. No answer revives the old evidence: absence, another UID,
not Established, another storage version, 403, 5xx, a timeout, an invalid or an identical
answer. Other CRDs keep their evidence. A request refused at the deadline never reaches the
server and invalidates nothing; there `read_crd` and `discover_all` still withdraw first,
and every later LIST is refused at the deadline anyway.

**Validation.** Discovery documents (kinds, group versions, duplicates), LIST pages
(`PartialObjectMetadataList` only; payload keys or the last-applied annotation refused by
their position; item identity, namespace, UID, owners, finalizers, duplicates and the page
limit checked; only the name, namespace, UID, minimal owner references, deletion flag and
finalizers returned), the CRD read (only identity, UID, group, plural, scope, versions and
Established) and the Service read (only UID and type). A DELETE answered 200 or 202 is
`REQUESTED`, never done; a NotFound counts only as the API server's `Status` for that
object (`trusted_not_found`), never a bare 404 or a missing endpoint.

**Discovery and pagination.** `discover_all` reads `/api`, `/apis`, `/api/v1` and every
advertised group version; `discovery_targets` keeps namespaced listable resources and
returns UNKNOWN for a missing or unexpected resource list, an unknown mapping, an
unlistable resource outside `bindings` and `localsubjectaccessreviews`, or no target at
all. Only a COMPLETE discovery issues the evidence that namespace LISTs need, and only its
targets can be listed (`list_target_not_discovered`). `inventory_namespace` lists every
target of one namespace and `merge_listed` requires exactly the discovered targets, each
listed once and COMPLETE (missing, unexpected, repeated or empty is UNKNOWN). `collect_list` returns COMPLETE only when the last page has
no continue token; a 410 restarts the list from the start (at most twice) and discards the
partial result; 100 pages per logical list, restarts included; a repeated token, a snapshot
change, a duplicate, a timeout or an invalid page is UNKNOWN and a 403 is BLOCKED; nothing
is sent after the global `Deadline` (3600 s, immutable). `merge_listed` merges versions of a
resource (and the two event resources) by UID only with the same name, namespace, owners,
finalizers and deletion state (`cross_version_conflict` otherwise). Pages also refuse an
item type other than `PartialObjectMetadata`, an empty resourceVersion, an invalid
`remainingItemCount`, malformed or conflicting owner references (two controllers, a
repeated owner), repeated finalizers, a malformed `deletionTimestamp`, and one name with two
UIDs across pages (`list_identity_conflict`).

**CRDs.** `verify_crd` is VERIFIED only for the receipt UID, the reviewed group, plural and
scope, the storage version served and Established; the CRD read refuses a missing,
repeated or invalid Established condition and repeated, malformed or not exactly one
storage version. Only the transport's own `verify_crd` issues the evidence that a CRD
instance LIST needs; a VERIFIED dictionary is not evidence. `classify_crd` adds CRD_NOT_CREATED (no
creation evidence, no open INTENT, trusted NotFound, discovery not serving the plural) and
BLOCKED for a claimed CRD that is missing or a foreign CRD. `classify_crd_instances` is
ZERO_INSTANCES only for 200, no items and no continue token.

**Journal destroy phase (`k8s_runtime_receipt`, FORMAT 1, additive).** DESTROY_BEGIN (no
open INTENT; no apply record after it), DESTROY_INTENT (fsynced before a DELETE; exactly the
owned UID; the destroy order is the apply stages reversed then `namespace_phase`; never a
CRD), DESTROY_RESULT (`deleted`, `absent_confirmed` or `failed`, matching the open INTENT)
and DESTROY_STAGE_DONE (only when every owned deletable member is deleted or confirmed
absent, and no member is quarantined). Ownership evidence is kept; quarantine is never
released. `reconcile` reports `DELETE_PENDING_RECHECK`, `DELETE_ABSENT_UNCONFIRMED`,
`DESTROYED` and `RECREATED_AFTER_DESTROY`. An apply-only journal keeps exactly its snapshot;
an older reader refuses the new records; `k8s_runtime_apply` stops on a destroy-phase
journal (`receipt_destroy_phase`) before any read or write.

**Tests.** `test_k8s_runtime_destroy_foundation.py`: 36 tests and 144 source mutations,
each detected by an assertion (a crash is undetected), run inside the
`k8s_runtime_receipt_tests` suite.

### Fake-only destroy engine (item 6c-B4b, Source/Offline only)

`k8s_runtime_destroy.destroy(report, objects, receipt_root, g9_root, server, clock,
expected_manifest, expected_input, cluster_arn)` (Owner authorization 2026-11-24,
decisions D3, D5, D6, D11, D12, D18, D19 and the existing G9, D13 and receipt
contracts). It has no command line: `k8s_runtime.py destroy` still refuses. Every
request goes through the 6c-B4a destroy transport or the G9 client, and only their
fakes can be opened; every wait runs on `FakeClock`. A COMPLETE is a Fake-only
Source/Offline result, never Live evidence.

**Preflight, before any write.**
- The fake clock and the fake transport only.
- The manifest and input SHA-256 pins, the rendered objects against the plan, and the
  runtime contract version.
- The repository's reviewed stage table is the only stage layout: the report and the
  bundle must equal it in stage names and order and in each stage's identities and
  their order (9 stages, 62 objects, 17 CRDs: 15 Istio, 2 controller), and the destroy
  order comes from it.
- One global 3600 s deadline for the whole run, never extended or reset.
- The D17 fingerprint read through the transport, then the runtime receipt of that
  fingerprint must exist and verify. A missing, corrupt or other-fingerprint receipt
  stops. The store is opened `existing_only` (`k8s_runtime_receipt.Store`, a new
  keyword; apply keeps its default): no directory, journal or HEADER is ever created,
  and a missing journal or snapshot is never repaired; only a verified stale snapshot
  is refreshed.
- An unresolved apply INTENT or any QUARANTINE stops.
- The G9 registration receipt of exactly this project and runtime fingerprint must hold
  all four Secrets REGISTERED with valid UIDs (a schema-valid INCOMPLETE receipt stops).
- After the lock, before the first journal write, everything is checked again
  (fingerprint, project, pins, journal and snapshot, phase, open INTENT, quarantine,
  G9); the DELETE map and the CRD verification map come only from that locked journal.
- The fingerprint is read again before every step and every G9 cleanup; G9's own
  `kube-system` read must show the runtime's UID or G9 stops before any Secret request.

**Order (D12).** The apply stages reversed, then `namespace_phase` with every
Namespace (`<project>-app`, `<project>-ingress`, `istio-system`). Inside a stage: the
TargetGroupBinding first, policy bindings before policies, webhook configurations
before their Deployments, then workloads, Services, RBAC, ServiceAccounts and
ConfigMaps. Gates:

| Before | Required |
| --- | --- |
| ingress | No TargetGroupBinding outside the receipt in `<project>-ingress` |
| admission | No TargetGroupBinding anywhere (the runtime one trusted absent, none listed in `<project>-ingress`, the TargetGroupBinding CRD's cluster-wide instance LIST empty or the CRD strictly never created); no LoadBalancer Service and no unknown Service in `<project>-ingress` (the runtime Service by exact resource, namespace, name and receipt UID; its `spec.type` from the specialised read) |
| controller | No TargetGroupBinding anywhere, as above |
| istiod, base | Every Istio CRD ZERO_INSTANCES or CRD_NOT_CREATED |
| namespace_phase | The G9 cleanup COMPLETE, including the `kube-system` webhook TLS Secret |

The same evidence is read fresh again right before every dependency-sensitive DELETE
(each admission and controller object, each Istio webhook, a Deployment once its
stage's webhook configurations are confirmed gone), not only at the start of a step.
The Terraform roots the TargetGroupBinding depends on (the controller's IAM role,
the target group, the ELBv2 and STS endpoints, the tunnel) are outside the engine
and must still exist (runbook section 7).

**Per object.** The plan identity, the journal's owned UID, no quarantine, a fresh
metadata read, the live UID equal to the journal UID, D13 field ownership OWNED
(`k8s_runtime_apply.d13_ownership` with the manifest's required paths), the gates,
the deadline and the journal's current step. Then DESTROY_INTENT (fsynced), the
UID-precondition DELETE, an independent read until a trusted NotFound, and
DESTROY_RESULT.
- 200 or 202 is only REQUESTED; a bare 404, 403, 5xx, timeout, invalid response or
  409 is never absence or success, and a DELETE error leaves the INTENT open.
- The TargetGroupBinding finalizer is waited for up to 600 s and a Namespace's
  termination up to 600 s, polling every 5 s; finalizers are never stripped.
- A recreated object is quarantined and never deleted or adopted; an object without
  a journal record is NOT_OWNED and stops.
- An object never created is judged on its own (no journal record, a trusted
  NotFound) and never counted as deleted; an owned object already absent gets an
  INTENT and `absent_confirmed`, never a DELETE.
- With the real controller or istiod managedFields entries D13 stays unverified, so
  destroy stops: there is no allowlist widening. Metadata carries no webhook values,
  so istiod's caBundle entry is never matched to a live webhook.

**Crash recovery.** An open DESTROY_INTENT is resolved first in its step, after the
step's gates: a trusted NotFound closes it `absent_confirmed`; another UID is
quarantined (`delete_unproven`); the same UID already terminating needs D13 and the
dependency gates again and then waits for absence under the same INTENT with no new
DELETE; the same UID not terminating is closed `failed` and gets a new INTENT through
the per-object checks (never an unconditional resend). Every wait keeps its own D11
bound on the fake clock: a read that completes after that local deadline is never
evidence, and a poll never sleeps past it. A stale snapshot is refreshed
from the journal. Completed steps are re-verified on resume and at the end; a
reappearing object is quarantined and stops.

**Namespaces (D3, D6, D18).** Right before each namespace DELETE: a fresh discovery
and a COMPLETE metadata inventory of every advertised group version, classified:

| Class | Rule | Effect |
| --- | --- | --- |
| runtime_object | A receipt UID | Stop |
| owned_child | ReplicaSet -> Deployment, Pod -> ReplicaSet -> Deployment, EndpointSlice -> Service; `controller: true` and the owner's identity, namespace and receipt UID | Never deleted directly; waited for up to 600 s, terminating ones included |
| allowed_leftover | Exactly the ServiceAccount `default`, the ConfigMaps `kube-root-ca.crt` and `istio-ca-root-cert`, Events | Allowed |
| istiod_leftover | `istio-system` Leases (names not confirmed Live) | Stop |
| k8s_certs_secret | One of the four Secrets | Stop |
| unknown_object | Anything else, any other Secret | Stop |

The owner chain is proven from the current inventory alone; a Pod whose ReplicaSet is
already gone cannot be chained to a receipt UID and stops. After DESTROY_INTENT a final
gate reads the namespace's identity, receipt UID and D13 ownership again, takes fresh
G9 evidence (D18) and, for `<project>-ingress`, the TargetGroupBinding gate, checks the
fingerprint, and then a last fresh inventory must equal the first in every safety
field (identity, resources, owners, deletion state, finalizers, class); a failed final
gate closes the INTENT `failed`. F06-R (PR #101) adds a Fake-only
Atomic Namespace Safety Gate: the transport issues a single-use, namespace/UID-bound
capability from its own complete inventory and validated Namespace metadata. The
fake compares current ownership, discovery and all contents at DELETE acceptance;
a delayed cascade rechecks the accepted snapshot and refuses unsafe changes.
There is no fallback to a normal Namespace DELETE or real API option.
`kube-system` is never inventoried or deleted. Real cascade atomicity stays NOT_VERIFIED.

**CRDs (D5).** No CRD DELETE exists. Each of the 17 is read with the specialised
CRD read and verified against the CRD receipt map, then its instances are listed
(`limit=1`) only when a fresh discovery maps exactly its group, storage version and
plural with its scope (the discovery evidence now keeps every resource's mapping):
ZERO_INSTANCES, or CRD_NOT_CREATED only with no creation evidence, no receipt UID, no
open INTENT, no quarantine, a trusted NotFound and a COMPLETE discovery that does not
serve its exact group and plural (another CRD of the same group being served is no
reason to refuse it). A claimed CRD that is missing or changed, a foreign CRD, a
missing or mismatched discovery mapping and creation evidence without a UID are
BLOCKED or UNKNOWN.

**Completion.** COMPLETE needs every destroy step in the journal, no open INTENT,
no quarantine, all 45 non-CRD objects confirmed absent again, the G9 cleanup
COMPLETE again (the four Secrets absent through G9's own reads), every CRD
ZERO_INSTANCES or CRD_NOT_CREATED, `kube-system` present with its fingerprint UID,
and the deadline not reached. The report separates deleted, absent_confirmed and
never_created objects, `retained_crds` (created, zero instances), `crd_zero_instances`
and `crd_not_created` (never counted as retained), the 15 Istio and 2 controller CRDs,
and every namespace (also on a rerun of a completed destroy, with fresh G9 evidence).

**G9 under the deadline.** Standalone G9 behavior remains unchanged; runtime destroy
pins the validated registration under the G9 cleanup lock and rechecks the fingerprint
before each runtime and Secret DELETE. The engine passes G9 a
deadline-bounded fake server: no request starts after the deadline and an answer at
or after it, or later than 20 s, is a timeout (G9: BLOCKED `transport_timeout`), and a
`kube-system` answer with another UID than the runtime fingerprint is refused, so G9
stops at its fingerprint check before any Secret request (`fingerprint_changed`).
G9's own `namespace_deletion: NOT_IMPLEMENTED` describes G9 alone; the engine reports
its namespace results separately.

**Tests.** `test_k8s_runtime_destroy.py`: expected 42 tests and 113 source mutations, each
required to be detected by an assertion (a crash is undetected), run inside the
`k8s_runtime_receipt_tests` suite with the pinned Helm render of the synthetic
fixture. A stateful fake API server answers both clients. The positive fixtures use
synthetic ownership evidence (journal and managedFields written by the test,
because the fake apply engine stops before the gateway): a full synthetic receipt
(45 objects deleted, 4 Secrets, 17 CRDs ZERO_INSTANCES) and a partial apply
(`namespaces` and `base`: 3 deleted, 42 never created, the 2 controller CRDs
CRD_NOT_CREATED). Neither is evidence of a real apply or destroy.

**NOT_VERIFIED / NOT_TESTED.** Real transport and authentication,
the real API server's cascade atomicity under races, garbage collection timing, the controller's
finalizer removal and target deregistration, the istiod and controller manager
names, discovery completeness on EKS and the istiod leader-election names.

### Registration UID receipt and safe Secret cleanup (G9, D19 Fake-only)

`k8s_certs_receipt.py` (Owner decision D19/G9, 2026-11-24) is Source/Offline code
with no command line. Every request goes through `k8s_runtime_transport`, where only
the fake can be opened (`real_transport_not_implemented` otherwise). It starts no
process, opens no socket, reads no token or kubeconfig and never calls kubectl or
the old `delete`. Its transport policy names exactly the four Secrets of
`k8s_certs.secret_layout` (the allowlist must equal that layout,
`secret_allowlist_mismatch` otherwise) and the `kube-system` namespace read of the
D17 fingerprint. The registration policy cannot delete.

**Registration UID receipt (`register_with_receipt`).**
- **Before any apply**, it reads the metadata of all four Secrets and compares them
  with the existing receipt. A Secret without a live receipt claim (no receipt, a
  NOT_VERIFIED entry or a cleaned-up entry) must be absent; a claimed Secret must be
  present with the claimed UID and the k8s_certs.py ownership. Any failure refuses
  the registration before the apply step is called, and nothing changes:
  `existing_secret_without_receipt`, `unverified_secret_present`,
  `recreated_after_cleanup`, `receipt_uid_absent`, `receipt_uid_mismatch`,
  `precondition_<check>`, and `precondition_unreadable` for a 403, timeout or
  invalid response, which is never read as absence. Labels, manager names and
  fields alone never make an existing Secret registrable.
- **The apply step** (`apply_fn(plan)`) receives a conditional plan per Secret: create
  only if absent, or update only the claimed UID. It returns the identity, outcome
  (`created` or `updated`) and UID it wrote. A conflict, another outcome, a missing,
  malformed or other UID, an unknown or repeated identity confirms nothing. The fake
  checks the condition atomically; on a real API server this is NOT_VERIFIED and no
  real apply transport exists.
- **After the apply**, a UID is recorded only when the metadata read shows the same
  UID the apply returned (`uid_changed_after_apply` otherwise),
  `app.kubernetes.io/managed-by: k8s_certs.py`, `app.kubernetes.io/part-of:
  <project>` and a single `<project>-k8s-certs` Apply entry owning exactly the
  registered labels, `type` and data keys.
- Otherwise the entry is NOT_VERIFIED with no UID and a fixed reason, and the
  result is INCOMPLETE. A failed apply, a foreign apply report, an unavailable UID
  and a failed save are never success.
- It never rebuilds a receipt from names or current UIDs, and never drops a UID that
  may still name a live Secret (`receipt_conflict`; the old receipt stays).

**Receipt store.** `<root>/<fingerprint id>/registration.json`, default root
`~/.local/state/<project>-k8s-certs`, separate from the runtime receipt (whose
Secret refusal is unchanged).
- Outside the repository; directory 0700, file 0600, current owner; symlinks are
  refused (the `k8s_runtime_receipt` file checks); an exclusive lock.
- Each write is validated first, then replaced atomically (temporary file, fsync,
  rename, directory fsync); a failed write leaves the previous receipt and no
  temporary file.
- Refused: missing, corrupt, non-canonical, over 64 KiB, unknown or missing fields,
  another schema, project, fingerprint or identity list, secret-like values.
- Schema `k8s-certs-registration-receipt-v1`: `project`, `cluster` (cluster ARN,
  `kube-system` UID, fingerprint id), `registered_at`, `result` (REGISTERED or
  INCOMPLETE) and, for each of the four Secrets in order, `identity` (apiVersion,
  kind, namespace, name), `uid`, `registration` (REGISTERED or NOT_VERIFIED),
  `reason` and `cleanup` (`state`, `reason`, `at`). No Secret value, key, token,
  kubeconfig, object body, label or annotation is stored.

**Cleanup (`cleanup`), per Secret, in this order.**
1. Receipt integrity, project, fingerprint and identity, before any Secret request
   (the fingerprint comes from the `kube-system` read through the same transport).
2. Metadata-only GET.
3. Label `app.kubernetes.io/managed-by: k8s_certs.py`.
4. Label `app.kubernetes.io/part-of: <project>`.
5. The `<project>-k8s-certs` Apply entry.
6. No other manager, operation or field ownership.
7. Live UID equal to the receipt UID.
8. DELETE with `preconditions.uid`; DELETE_REQUESTED is recorded first.
9. Metadata GET confirming NotFound.
10. The result recorded in the receipt.

States: DELETED (deleted and confirmed absent), ALREADY_ABSENT (NotFound before the
delete, after the receipt and fingerprint checks), BLOCKED with a fixed reason, and
DELETE_REQUESTED while a delete is in flight. A 200 or 202 alone is never success.
A 409 (`uid_precondition_failed`), 403, 5xx, timeout, invalid or full-Secret
response, a Secret still present or recreated after the delete or after an earlier
cleanup, a missing UID in the receipt and any failed check is BLOCKED: the Secret
stays, nothing is retried and no response body is kept. There is no full Secret
GET, no name-only delete and no namespace fallback.

**D18 (recorded, not implemented).** The report's `namespace_secret_condition` is
BLOCKED for `istio-system` or `<project>-ingress` while any of its Secrets is not
DELETED or ALREADY_ABSENT; MET is necessary, never sufficient (the section 5.1
inventory and D6 still apply). `kube-system` is `NEVER_DELETED`; its webhook TLS
Secret is its own completion condition (`kube_system_webhook_tls`).
`namespace_deletion` is `NOT_IMPLEMENTED` (6c-B4).

**Tests.** `test_k8s_certs_receipt.py` has 27 tests and 67 source mutations, run
inside the `k8s_runtime_receipt_tests` suite. A fake API server answers like the
API server: a GET without the metadata-only Accept header returns a full Secret
with a value marker, and a DELETE honours `preconditions.uid`. A mutation counts as
detected only when an assertion fails; a crash is reported as undetected. The tests
cover the allowlist, the request and response contract, real-transport and
real-operation refusal, the registration preconditions (an existing Secret without
a receipt, all four existing with matching labels and manager, a UID mismatch, a
claimed Secret gone or changed, unreadable metadata, a Secret recreated after
cleanup, a NOT_VERIFIED entry; none calls the apply step), the apply evidence (a
Secret created just before the apply, a rewritten plan, a UID changed after the
apply, a missing or wrong UID in the result), the receipt store (missing, corrupt, non-canonical,
tampered, modes, symlinks, owner, repository location, lock, fingerprint, project
and identity), partial registration, save failure, replacement rules, every
cleanup step and refusal, and the absence of any fallback.

### Fake apply engine for the first two stages (item 6c-B3b-Apply-A, offline only)

`k8s_runtime_apply.py` applies the `namespaces` (2 objects) and `base` (16 objects)
stages, and nothing else.
- It runs only against an in-memory `FakeAdapter` and `FakeClock`.
- It has no command line. `k8s_runtime.py apply` still refuses
  (`operation_not_approved`).
- Any other adapter is refused, and `RealAdapter` cannot be constructed.
- No kubectl, API call, cluster, AWS or Emulator is involved.

It implements the Owner decisions of 2026-11-22 for Source/Offline use only. None
of them is Live evidence.
- **D2.** Secrets stay metadata-only fakes. The first two stages read none.
- **D3.**
  - The apply read scope is limited to the approved stages' objects and the
    `kube-system` namespace. The fake refuses anything else
    (`read_out_of_scope`).
  - The Pods, Nodes, EndpointSlices and ConfigMap reads of later stages are
    design scope only.
  - Destroy discovery and inventory reads are not approved.
- **D9.** `classify_admission` reduces a dry-run or probe answer to exactly one
  class:
  - `allowed`
  - `authz_denied`
  - `webhook_denied:<name>`
  - `vap_denied:<name>`
  - `schema_invalid`
  - `webhook_unreachable`
  - `dry_run_unsupported`
  - `unknown`

  A probe passes only on the exact expected class. `dry_run_permitted` requires
  every webhook to declare `None` or `NoneOnDryRun` side effects.
- **D11.** Timeouts are applied through the fake clock, with no unbounded retry:

  | Wait | Value | On expiry |
  | --- | --- | --- |
  | API read | 20 s | `api_timeout`, exit 3 |
  | CRD established | 120 s | `crd_not_established`, exit 5 |
  | Deployment ready | 600 s | Defined; unused by these stages |
  | CRD poll interval | 5 s | Not a timeout; a cadence inside the 120 s bound |

- **D13.** `d13_ownership` implements the section 10 allowlist, using
  field-level evidence. A manager name alone never proves ownership.
  - The runtime's Apply entry must own exactly the leaf field paths its manifest
    sets.
    - Paths are nested `f:`/`k:` paths and are never collapsed to the top level.
    - Missing, empty, partial or extra fields give `OWNERSHIP_NOT_VERIFIED`.
    - This applies to every Namespace, CRD and webhook, on both the
      `REAPPLY_SAFE` and the `CONSISTENT` path.
  - Verified: only the structural status rule, which is a `status`-subresource
    Update touching only `f:status` paths on a kind with status.
  - The istiod and controller manager names are unverified, so their entries
    give `OWNERSHIP_NOT_VERIFIED`.
  - Any other manager or field gives `FOREIGN_FIELD`.
  - Conflicts are never forced.

**Flow.**
1. Gate: fake adapter, approved stage.
2. Pins, plus the hash of the given manifests against the plan's manifest SHA-256,
   plus the receipt HEADER pins.
3. D17 fingerprint.
4. Receipt reconcile, using the D13 ownership hook. Stops before any write:

   | Verdict | Exit and reason |
   | --- | --- |
   | QUARANTINED | 4 |
   | QUARANTINE_REQUIRED | Quarantine recorded, then 4 |
   | UID_CHANGED | 4 |
   | NOT_OWNED | 4 `foreign_owner` |
   | OWNERSHIP_NOT_VERIFIED | 4 |
   | FOREIGN_FIELD | 4 |
   | UNKNOWN | 3 |

   An interrupted INTENT whose object is provably safe gets a `failed` RESULT (not
   confirmed) before a new INTENT. Recorded ownership is kept.
5. Per stage:
   - pre-apply: `base` needs `namespaces` accepted, and no Istio webhook may carry
     a `caBundle` (C1);
   - a fake server-side dry-run of every object;
   - per object: INTENT, then fake server-side apply without force, then the
     readback and the D13 ownership check, then RESULT. Every write is
     conditional:
     - create only if the object is absent; update only on the recorded UID;
     - an object that appears where none was recorded stops the run before its
       INTENT (`foreign_object_appeared`);
     - a change between the engine's read and the write fails the fake's atomic
       check (`precondition_failed`), and the foreign object is left byte for byte
       unchanged;
     - the same atomic check refuses an update unless the object's ownership
       still proves OWNED under D13, the check the engine applies to its
       readback. The runtime's own Apply entry is verified too, not skipped by
       name. The object, its `resourceVersion`, its `managedFields` and the
       fake's write serial stay unchanged, the RESULT is `failed` (not a
       quarantine) and the run stops with exit 4:

       | D13 verdict at write time | Example | Stop reason |
       | --- | --- | --- |
       | FOREIGN_FIELD | another manager owns a field | `foreign_field_refused` |
       | NOT_OWNED | `managedFields` or the runtime's Apply entry is missing | `not_owned_refused` |
       | OWNERSHIP_NOT_VERIFIED | the runtime entry is partial, empty, has extra paths or is malformed; an unverified manager | `ownership_not_verified_refused` |
     - how a real API server would enforce the same conditions is NOT_VERIFIED;
   - after a write lands, the success RESULT (and the newly owned UID) is
     recorded only when the readback proves OWNED. Otherwise the outcome is
     quarantined and the run stops with exit 4, never recorded as "not
     applied":

     | Readback | QUARANTINE reason | Stop reason |
     | --- | --- | --- |
     | Object absent | `creation_unproven` (create) or `uid_changed` (update) | `apply_not_observed` |
     | Another UID | `uid_changed` | `uid_changed` |
     | Foreign owner, foreign field or too few runtime fields | `ownership_unproven` | `foreign_owner`, `foreign_field` or `ownership_not_verified` |

     A readback timeout leaves the INTENT open; the rerun quarantines it as
     `QUARANTINE_REQUIRED`. A quarantined object is never re-applied or adopted.
   - minimal completion: Namespace Active with its labels, CRD Established and
     NamesAccepted, webhook without a runtime `caBundle`;
   - STAGE_DONE.

   A closed stage is re-verified on a rerun, not re-applied.

**Results.**
- `base` leaves the istiod-default-validator serving deferred to the `istiod`
  stage. A full run therefore ends in exit 6 `APPLIED_WITH_DEFERRED`, with `base`
  final acceptance `DEFERRED` and runtime final acceptance `NOT_REACHED`, never
  PASS.
- A later stage's STAGE_DONE never resolves a deferred item on its own. Webhook
  serving needs its own verification evidence. With no evidence source, the item
  stays `DEFERRED` / NOT_VERIFIED. Adding that evidence is an acceptance gate for
  Apply-B.
- `namespaces` alone ends in exit 0.
- Other exits:

  | Code | Status | Meaning |
  | --- | --- | --- |
  | 1 | REFUSED | Gate refused the request |
  | 2 | STOPPED | Pins, fingerprint or receipt |
  | 3 | UNDETERMINED | Timeout or unknown observation |
  | 4 | APPLY_FAILED | Conflict, foreign ownership, UID change, quarantine, C1 or denied dry-run |
  | 5 | READINESS_TIMEOUT | A readiness wait expired |

**Journal schema: unchanged.** No record type was added. The QUARANTINE record
gained the reason `ownership_unproven`.
- Deferral is derived from the journal: a closed stage whose resolving stage is not
  closed.
- The only new use of an existing record is the `failed` RESULT that closes an
  interrupted INTENT.
- `receipt verify` keeps its strict ownership. The D13 hook (`ownership_fn`) is
  used only by the engine.

**Tests.** `test_k8s_runtime_apply.py` has 31 tests and 52 source mutations.
- A mutant counts only when a contract assertion fails and the code under test did
  not crash. A mutant that only raises an exception is reported separately and
  fails the suite.
- It covers:
- success with deferred readiness, and the namespaces-only run;
- a rerun without writes, and an allowed status manager;
- pins, a changed bundle, tampered manifests and the fingerprint;
- the gates and plan order;
- a damaged or missing journal;
- a crash before and after the apply (re-apply, then quarantine);
- UID changes, including a race before the write;
- a foreign owner, a foreign field (after the run and during the apply), and an
  unverified manager;
- an SSA conflict and stage order;
- the CRD timeout and API read timeout, and an inactive Namespace;
- C1;
- dry-run denial and the D9 classes;
- D13 cases;
- the fake's read scope and force refusal, the `apply` CLI refusal, and no
  network or process imports;
- a foreign object appearing before the apply or just before the write, an update
  whose UID changed, a normal owned update, and writes without a precondition;
- incomplete ownership on the `CONSISTENT` and `REAPPLY_SAFE` paths: an empty
  `fieldsV1`, metadata without spec, missing webhook fields, unknown nested paths,
  nested status paths;
- deferred items that a later STAGE_DONE does not resolve;
- ownership proven before the success RESULT: a foreign manager or too few
  runtime fields in the readback, a UID change after an owned update, and a
  readback that fails after the write, each quarantined with no newly owned UID
  and no adoption on rerun;
- the fake's write-time ownership check: a foreign manager added to the same UID
  just before the write (namespace labels, CRD spec) is refused with the object
  unchanged, while a status-subresource update and a normal owned update proceed;
- the runtime's own ownership lost on the same UID just before the write, on a
  namespace and a CRD: `managedFields` removed, the runtime's Apply entry removed
  (a status entry kept), a required nested path dropped, an emptied entry, an
  extra path and malformed evidence. Each is refused with the object and the
  write serial unchanged, no new success RESULT, no STAGE_DONE, the owned UID
  kept, and a rerun that neither writes nor adopts.

### Controller and istiod stages (item 6c-B3b-Apply-B1, offline only)

The same fake engine also applies the `controller` (13 objects) and `istiod` (12
objects) stages (Owner instruction 2026-11-23). `through` may be `controller` or
`istiod`; `gateway` and later stages are refused (`stage_not_approved`). It is
still fake-only, with no command line, real adapter, cluster, AWS or Emulator.

**Pre-apply** (design section 4.1). Each check stops before the stage is dry-run,
journaled or applied:

| Check | Evidence | Stop |
| --- | --- | --- |
| Base minimal completion | `base` closed (not its deferred item) | 2 `pre_apply_not_verified:base_not_accepted` |
| Controller CA | Each controller webhook `caBundle` equals the pinned input's public CA | 3 `pre_apply_not_verified:webhook_ca_bundle` or `bundle_ca_differs` |
| Required Secrets (D2) | Metadata-only read: `PartialObjectMetadata`, name and namespace, the `k8s_certs.py` labels and the `<project>-k8s-certs` Apply entry | 3 `secret_absent`, `secret_not_registered`; a full Secret or any `data`/`stringData` gives 3 `secret_metadata_only_unsupported`, discarded unprinted |
| ECR (D4) | Only a `FakeRegistry`: the locked index exists as an index and its `linux/amd64` child equals the lock | 3 `ecr_evidence_unavailable` without a registry; `ecr_index_missing`; `digest_not_verified:ecr_platform_child`; another registry type gives 1 `real_registry_not_approved` |
| Image lock | Each bundle image is `<account>.dkr.ecr.<region>.amazonaws.com/<project>-dev-ecr-<purpose>@<index>` of the lock | 3 `digest_not_verified:bundle_image_not_locked` |
| Nodes (D3) | A Ready `amd64` node in the Deployment's zone | 3 `pre_apply_not_verified:nodes` |
| Dry-run side effects | Every bundle webhook up to the stage has `sideEffects` `None` or `NoneOnDryRun` | 3 `dry_run_unsupported` |

**Minimal completion.** The 2 controller CRDs Established and NamesAccepted; RBAC,
Services, ConfigMaps and the Deployment present; the ServiceAccount IRSA
annotation equals the bundle (`irsa_annotation_differs`). The controller webhooks
keep the bundle `caBundle`. The runtime never claims an Istio webhook `caBundle`
(`istio_cabundle_ownership_unsafe`); istiod may fill it later with its own entry.

**In-stage readiness** within the D11 Deployment bound (600 s, polled every 5 s;
no new timeout). It must hold before the next stage starts, and a closed stage is
re-verified on a rerun. A timeout gives exit 5 with the first unmet reason:
`deployment_not_ready` (Available, observed generation current, every replica
ready), `pods_not_ready`, `endpoints_not_ready` (controller 9443; istiod 15017
and 15012) or, for istiod, `cabundle_not_populated` on the three Istio webhooks.

**Digests** (design section 9). Each Pod's spec image must equal the bundle
(`digest_mismatch:spec_image`). The `imageID` digest must be the lock's amd64
digest on an amd64 node (`MATCH_PLATFORM`). `MATCH_INDEX`, a missing or
unparseable `imageID` or another node architecture give 3
`digest_not_verified`; any other digest gives 4 `digest_mismatch`.

**Ownership.** The controller webhooks must stay OWNED by the runtime with the
bundle value (`controller_webhook_cabundle_not_runtime_owned`). D13 enforces the
design section 10 rows element by element. Inside a row the result is
`OWNERSHIP_NOT_VERIFIED` (the manager name is unconfirmed); anything outside is
`FOREIGN_FIELD`:

| Row | Manager, operation | Object | Fields and values |
| --- | --- | --- | --- |
| Status | Any manager, Update, `subresource: status` | CRD, Deployment, ValidatingAdmissionPolicy, TargetGroupBinding | `f:status` only (verified) |
| istiod | `pilot-discovery`, Update, no subresource | Exactly `ValidatingWebhookConfiguration/istiod-default-validator`, `ValidatingWebhookConfiguration/istio-validator-<project>-v1-istio-system`, `MutatingWebhookConfiguration/istio-sidecar-injector-<project>-v1` (cluster-scoped) | `f:webhooks[name=<fixed>].f:clientConfig.f:caBundle` of a fixed webhook on the live object (`validation.istio.io`; `rev.validation.istio.io`; `rev.namespace.sidecar-injector.istio.io`, `rev.object.sidecar-injector.istio.io`), or its `f:failurePolicy` while the live value is `Fail` |
| Controller | `aws-load-balancer-controller`, Update, no subresource | `TargetGroupBinding/<project>-gateway` in `<project>-ingress` | Exactly the finalizer `elbv2.k8s.aws/resources`; any other finalizer on a TargetGroupBinding is foreign |

Malformed evidence gives `OWNERSHIP_NOT_VERIFIED`, never ownership: managedFields
that is not a list of well-formed entries, a fieldsV1 tree that is not mappings
with `f:`/`k:`/`v:`/`i:` keys, a duplicate manager/operation/subresource entry, or
a malformed webhook or finalizer list.

After istiod has written the `caBundle`, the istiod stage re-checks the three
Istio webhooks: `failurePolicy` must still be `Fail`
(`istio_failure_policy_not_fail`), and their ownership must not be foreign or lost
(`foreign_field`, `foreign_owner`). The names stay NOT_VERIFIED, so:
- after istiod has filled the Istio webhook `caBundle`, every rerun stops before
  any write (`ownership_not_verified`) and nothing is adopted;
- istiod filling a `caBundle` before the engine's readback is quarantined
  (`ownership_unproven`).

**Probes** (D9, fake only). After istiod is ready, probe F must be denied by the
base validator's webhook and probe G must be allowed with the injected
`istio-proxy` at the locked image. A wrong class stops (`probe_F:<class>`,
`probe_G:<class>` or `probe_G:injection_missing`). A fake pass is recorded as
`CLASSIFIED_FAKE_ONLY`; an absent answer as `NOT_RUN`. Neither meets a Live
requirement (D20).

**Deferred items.** Every requirement must be MET. Live-only (D20, D21) and BLOCKED
(D1, ingress) requirements have a fixed status, so none of these can pass and a run
through `controller` or `istiod` ends in exit 6 `APPLIED_WITH_DEFERRED`:

| Stage | Item | Requirements |
| --- | --- | --- |
| base | Validator serving (resolved by istiod) | `caBundle` populated (fake MET); istiod manager verified (NOT_VERIFIED); istiod endpoints (fake MET); Live probe F (NOT_VERIFIED) |
| controller | Webhook serving (resolved by admission) | Live probe B (NOT_VERIFIED) |
| controller | IRSA and AWS calls (resolved by ingress) | BLOCKED |
| istiod | CA in use, D21 (resolved after istiod) | Live root comparison (NOT_VERIFIED; the input has no public root yet) |
| istiod | Injection (resolved by gateway) | Live probe G (NOT_VERIFIED) |

The report's `evidence` lists what the fake observed (digests, `caBundle`,
endpoints, fake probe classes).

**Tests.** `test_k8s_runtime_apply.py` now has 45 tests and 109 source mutations
(14 tests and 57 mutations for Apply-B1). They cover:
- a run through istiod and through controller, a rerun, and the rerun stop after
  istiod;
- each pre-apply check (Secret absent, full or leaking, unregistered; no, foreign
  or wrong ECR evidence; unlocked image; nodes; CA; side effects), each with no
  write of the stage;
- each readiness failure and the 600 s bound, and istiod never starting while the
  controller is not ready;
- the digest classes;
- the IRSA annotation and the controller webhook ownership;
- every element of the section 10 rows (kind, object name, scope, project, webhook
  name, manager, operation, subresource, path, `failurePolicy` value, the
  TargetGroupBinding name, namespace and finalizer) with malformed evidence, races
  at write time and after the write, the istiod-stage re-check and reruns;
- each probe misclassification and missing injection;
- the fake read scope (Pods, EndpointSlices and Secret metadata).

Still NOT_VERIFIED or NOT_TESTED (Live): every read and write on a real cluster;
the real ECR read (D4); the istiod and controller manager names; what `imageID`
reports; probes on a real cluster (D20); the CA in use (D21); IRSA and AWS calls
(BLOCKED until ingress).

### Gateway stage (item 6c-B3b-Apply-B2, offline only)

The fake engine also covers the `gateway` stage (5 objects; Owner instruction
2026-11-23, Source/Offline only). `through` may be `gateway` (and, since Apply-B3,
`mesh_security`); `admission` and later stages are refused. There is still no command line, real adapter, cluster,
AWS or Emulator.

**The gateway is unreachable today, by design.** Design section 4.1 says that
when the base validator serving is not verified after istiod, the run stops
before the gateway. That item needs Live probe F (D20) and a confirmed istiod
manager name (D13). No fake can supply either, so every run through `gateway`
stops before any gateway dry-run, INTENT or write:

| Order | Pre-apply check | Stop |
| --- | --- | --- |
| 1 | istiod in-stage readiness in this run | 3 `pre_apply_not_verified:istiod_not_ready` |
| 2 | Injector `caBundle` populated | 3 `pre_apply_not_verified:injector_cabundle` |
| 3 | Both gateway Secrets (metadata only, D2) | 3 `secret_absent`, `secret_not_registered` or `secret_metadata_only_unsupported` |
| 4 | Locked `istio-proxy` index and amd64 child (fake ECR, D4) | 3 `ecr_index_missing:istio-proxy` or `digest_not_verified:ecr_platform_child:istio-proxy` |
| 5 | Base validator serving resolved | 3 `deferred_readiness_unresolved:base_validator_serving` (always, today) |

A rerun cannot reach it either: after istiod has written the `caBundle`,
reconcile stops with `ownership_not_verified` (D13).

**The stage contract behind the gate** is implemented and tested directly
against a fake that already holds the gateway objects:
- minimal completion: ServiceAccount, Role, RoleBinding, Service and Deployment
  present;
- in-stage readiness within the D11 Deployment bound: Deployment Available and
  Pods ready (`deployment_not_ready`, `pods_not_ready`);
- revision injection: every Pod carries `sidecar.istio.io/status` and an
  `istio-proxy` container with the locked image (`injection_missing`, exit 4);
- digest: `MATCH_PLATFORM` only (`digest_not_verified`, `digest_mismatch`);
- deferred: gateway TLS serving (resolved by ingress) stays BLOCKED, so the
  gateway's final acceptance can never be PASS while ingress is BLOCKED.

**Tests.** `test_k8s_runtime_apply.py` has 48 tests and 120 source mutations
(3 tests and 11 mutations for Apply-B2): the unreachable gate and the rerun stop,
each gateway pre-apply check, and the contract behind the gate (injection,
digest, readiness, deferred TLS).

### mesh_security stage (item 6c-B3b-Apply-B3, offline only)

The fake engine also covers the `mesh_security` stage (5 objects: the
`<project>-app` Namespace, its ServiceAccount, a STRICT PeerAuthentication, an
empty-rules AuthorizationPolicy and a default-deny NetworkPolicy; Owner instruction
2026-11-23, Source/Offline only). `binding_writer` and later stages are refused
(since Apply-B4).

**Unreachable today.** A run through `mesh_security` stops at the gateway gate
first (`deferred_readiness_unresolved:base_validator_serving`), with no gateway or
mesh_security write. The stage's own pre-apply gate (design section 4.1) would
stop it too:

| Order | Check | Stop |
| --- | --- | --- |
| 1 | istiod in-stage readiness in this run | 3 `pre_apply_not_verified:istiod_not_ready` |
| 2 | Base validator serving resolved ("validator not serving: stop before apply") | 3 `deferred_readiness_unresolved:base_validator_serving` |

Item 2 needs Live probe F (D20) and a confirmed istiod name (D13); even evidence
claiming every fake-observable requirement MET leaves it shut.

**Behind the gate** (tested directly against a fake holding the five objects):
- minimal completion: `<project>-app` Active with its labels, the ServiceAccount
  and the three policies present (`namespace_not_active`, `namespace_labels_differ`,
  `object_not_present`);
- final acceptance inputs, for all five objects: D13 ownership OWNED
  (`foreign_field`, `foreign_owner`, `ownership_not_verified`) and no drift
  (`drift_detected:<kind>/<name>`, exit 4). Drift means a value the manifest sets
  is missing or different on the live object: mappings key by key (server-set
  extras are allowed), lists and scalars exactly. Examples: PeerAuthentication
  `PERMISSIVE`, an AuthorizationPolicy rule or `DENY`, a NetworkPolicy egress rule,
  a missing `ingress`, changed `policyTypes`, `automountServiceAccountToken: true`;
- deferred: mTLS and authorization enforcement needs traffic and is fixed
  NOT_TESTED, so the stage's final acceptance is never PASS.

**Tests.** `test_k8s_runtime_apply.py` has 51 tests and 133 source mutations
(3 tests and 13 mutations for Apply-B3): the unreachable run, the gate itself, and
the contract behind it (minimal completion, ownership, drift, NOT_TESTED).

### admission stage (item 6c-B3b-Apply-B4, offline only)

The fake engine also covers the `admission` stage (4 objects: the
`<project>-no-lb-service` and `<project>-target-registration`
ValidatingAdmissionPolicies and their bindings; Owner instruction 2026-11-23,
Source/Offline only). `ingress` is refused (since Apply-B5, `binding_writer` is
covered).

**Unreachable today.** A run through `admission` stops at the gateway gate first
(`deferred_readiness_unresolved:base_validator_serving`); nothing from the gateway
onward is written and no admission probe is sent.

**Behind the gate** (tested directly against a fake holding the four objects),
design sections 4.1 and 11:

| Point | Check | Stop |
| --- | --- | --- |
| Pre-apply | Controller accepted, and the TargetGroupBinding CRD Established and NamesAccepted | 3 `pre_apply_not_verified:controller_not_accepted` / `tgb_crd_not_established` |
| Minimal completion | Each policy reports type checking without warnings. No report is NOT_VERIFIED (no timeout is approved for it) | 4 `policy_type_warnings`; 3 `policy_type_check_not_verified` |
| Minimal completion | Each binding is exactly `validationActions: ["Deny"]` on its own policy | 4 `binding_not_deny` |
| Final acceptance input | All four objects present, D13 OWNED and without drift | `object_not_present`, `foreign_field`, `drift_detected:<kind>/<name>` |
| Final acceptance input | Probes A (LoadBalancer Service), A' (Ingress) and B (TargetGroupBinding), classified against the fake | See below |

Each probe answer must be the whole text of a 403 policy denial, one line,
optionally after the API server's `<resource> "<name>" is forbidden: ` prefix:
`ValidatingAdmissionPolicy '<policy>' with binding '<binding>' denied request: <message>`.

| Answer | Stop |
| --- | --- |
| Missing | 3 `probe_<name>:not_run` (never ready) |
| Not a `(status, body)` pair of int and text | 3 `probe_<name>:unknown` |
| A policy denial mixed with other text or lines | 4 `probe_<name>:denial_not_exact` |
| Another policy | 4 `probe_<name>:vap_denied:<policy>` |
| A binding that is not one of the expected policy's bindings | 4 `probe_<name>:wrong_binding` |
| A message that is not one of that policy's reviewed messages, verbatim (no substring, suffix, truncation or case change) | 4 `probe_<name>:message_mismatch` |
| Any other outcome (`authz_denied`, a webhook denial, `schema_invalid`, `allowed`, `webhook_unreachable`, `unknown`, `dry_run_unsupported`) | `probe_<name>:<class>` (3 for unreachable, unknown or dry-run, else 4) |

A fake pass is recorded as `CLASSIFIED_FAKE_ONLY`. The Live probes (D20) are a
deferred item fixed at NOT_VERIFIED, so the stage is never PASS.

**Tests.** `test_k8s_runtime_apply.py` has 55 tests and 152 source mutations
(4 tests and 19 mutations for Apply-B4): the unreachable run, pre-apply, type
checking, bindings, ownership, drift, and each probe answer above.

### binding_writer stage (item 6c-B3b-Apply-B5, offline only)

The fake engine also covers the `binding_writer` stage (3 objects: the
`<project>-binding-writer` ServiceAccount, Role and RoleBinding in
`<project>-ingress`; Owner instruction 2026-11-23, Source/Offline only). `ingress`
stays refused (`stage_not_approved:ingress`).

**Unreachable today.** A run through `binding_writer` stops at the gateway gate
first; nothing from the gateway onward is written.

**Behind the gate** (tested directly against a fake holding the objects), design
sections 4.1, 7, 10 and 11:

| Point | Check | Stop |
| --- | --- | --- |
| Pre-apply | `admission` accepted, and its minimal completion re-verified on the live objects (type checking without warnings, bindings exactly `Deny`) | 3 `pre_apply_not_verified:admission_not_accepted`; `policy_type_warnings`, `policy_type_check_not_verified`, `binding_not_deny`, `object_not_present` |
| Minimal completion | The three objects present; the ServiceAccount's `automountServiceAccountToken` is exactly boolean `false` (missing, `true`, `"false"` or `0` stop) | 3 `object_not_present`; 4 `sa_automount_token_not_false` |
| Final acceptance input | D13 OWNED and no drift for all three (Role rules, RoleBinding subjects and roleRef, the ServiceAccount) | `foreign_field`, `foreign_owner`, `ownership_not_verified`, `drift_detected:<kind>/<name>` |
| Writes | A field conflict is never forced | 4 `field_conflict` (failed RESULT) |

The ServiceAccount check applies to every ServiceAccount whose manifest sets
`automountServiceAccountToken: false`.

**D1 is undecided.** The binding writer's effective permissions, impersonation and
probes C to E (design section 7) are a deferred item fixed at NOT_TESTED. No fake
probe C, D or E is sent or read, and evidence claiming any of them MET is ignored,
so the stage is never PASS.

**Tests.** `test_k8s_runtime_apply.py` has 58 tests and 163 source mutations
(3 tests and 11 mutations for Apply-B5).

### Apply and destroy: preconditions and open decisions (not implemented)

`apply` and `destroy` are not implemented as commands (both subcommands refuse; the
Fake-only apply and destroy engines above have no command line and no real transport). This records what they must respect,
taken from the reviewed plan and the
[6c-B2 design record](../../docs/k8s-runtime-apply-destroy-design.md). That record
holds the full contracts and the Owner Decision Matrix D1–D23. Every decision
there is **open**; nothing here decides an execution method.

- **Readiness levels.** Passing the offline tests and Full CI (Source/Offline
  PASS) does not allow an apply against a real cluster. A mandatory precondition
  that is NOT_VERIFIED stops the command before it changes anything. That covers
  Secrets, webhooks, ECR images, ownership and digests.
- **Ownership.**
  - The runtime owns `<project>-ingress`, `<project>-app` and `istio-system`, the 15
    Istio CRDs and the 2 AWS Load Balancer Controller CRDs. `kube-system` is never
    created or deleted.
  - Ownership is proven by an ownership receipt kept outside the repository. Each
    object needs its UID in the receipt, its exact identity, and only the field
    managers the design record allows. A field manager name alone is never proof.
  - An object that already exists without that evidence stops apply
    (`foreign_owner`). It is never adopted automatically and never deleted.
  - Objects are deleted only by exact identity with a UID precondition. Never with
    `--all`, label selectors, `--force`, `--grace-period=0` or by stripping a
    finalizer.
  - No DELETE is enabled until the Owner decides how a UID-precondition delete is
    sent (D19).
- **Istio `caBundle` (C1, finding F23).**
  - Renderer contract 5 (6c-B3b-C1, Owner decision D23) guarantees that the three
    Istio webhooks carry no `caBundle`, so the runtime never owns the field istiod
    writes.
  - The controller webhook keeps its public CA.
  - A conflict is never forced.
  - istiod's real behaviour stays NOT_VERIFIED.
- **CRDs.** Destroy keeps every CRD by default. Deleting a CRD removes every
  custom resource of that kind in the cluster, so CRD deletion needs a separate
  approval (**open**). The CRDs go with the EKS cluster.
- **Order and readiness.** Stages apply in plan order. Each stage has pre-apply
  conditions, a minimal completion, deferred readiness that a later stage resolves,
  and a final acceptance (design record §4.1). This is needed to bootstrap: the
  namespaces must exist before the Secrets are registered, and the base stage's
  Istio webhook cannot serve until the istiod stage runs. Deferred readiness is
  never a final PASS. The controller and istiod webhooks fail closed, so
  their Deployments and webhook endpoints must be ready before objects that pass
  through those webhooks are applied. The current `status` reports Deployment
  readiness, lists webhook serving as an unverified condition, and does not wait.
- **Secrets and certificates.**
  - `k8s_certs.py register` applies the four Secrets after the namespaces stage. It
    does not read them back, so what is stored in the cluster stays NOT_VERIFIED.
  - The runtime never reads Secret contents, and never falls back to reading a
    full Secret.
  - `public.json` dates are not proof of validity.
- **Secret cleanup (G9, finding F22).** `k8s_certs.py delete` is retired and
  refuses. The safe cleanup (`k8s_certs_receipt.cleanup`: receipt UID, ownership
  checks, UID-precondition DELETE, confirmed absence) exists as Source/Offline code
  against the fake transport only. Deleting a namespace also deletes its Secrets,
  so namespace deletion stays BLOCKED (6c-B4, D3, D6), and never happens while a
  Secret remains (D18). The `kube-system` webhook TLS Secret is its own cleanup
  condition.
- **Ingress stop condition.** The ingress stage stays BLOCKED until all of these
  are approved and in place:
  - a way for the operator to act as `<project>-binding-writer`. Impersonation is
    NOT_TESTED and needs two separate authorizations: the operator's permission to
    impersonate, and the service account's own RBAC. TokenRequest is not approved
    (**open**);
  - the `elasticloadbalancing` endpoint in the network output (finding F21);
  - a decision on whether target health is read from AWS (**open**).
- **Destroy order and finalizers.** Destroy runs in reverse stage order:
  - the operator deletes the TargetGroupBinding first, while the controller, its
    webhooks, its IAM role, the target group, the endpoints and the tunnel still
    exist. Then it waits (bounded) for the controller to remove its finalizer and
    deregister the targets;
  - delete the admission policies only when no TargetGroupBinding remains;
  - delete webhook configurations before their Deployments, so a fail-closed webhook
    is never left without a server;
  - clean up the Secrets and confirm they are absent before deleting their
    namespace;
  - delete Namespaces last, only when a metadata-only inventory of every listable
    resource in them is complete, with no Secret and nothing outside the inventory
    left. An incomplete or forbidden read is UNKNOWN or BLOCKED, never empty. `<project>-app` stops on any Secret or unknown object.
    Deleting a namespace that still holds a Secret needs a separate Owner approval.
- **Partial failure.**
  - Neither apply nor destroy rolls back automatically. A failed stage stops the
    run.
  - A write-ahead journal records each object's intent and result. After a crash,
    an object whose creation cannot be proven is quarantined, not adopted.
  - A rerun re-verifies every earlier stage (presence, ownership, diff, readiness)
    before continuing.
  - The current `status` only reports observed objects. It does not read the
    receipt, and it leaves field ownership and drift NOT_VERIFIED. Showing where a
    run stopped, and verifying drift, are future capabilities.
  - Whether a version change of the bundle may be upgraded in place is **open**;
    the initial design stops on any difference.

## Image mirror (`mirror_images.py`)

The Kubernetes runtime pulls its three images from private ECR repositories by digest,
so node egress stays closed (finding F18). The parts fit together like this:
- [`kubernetes/images.lock.json`](../../kubernetes/images.lock.json) is the only image
  inventory (B2);
- the [`registry` root](../../infra/services/dev/ca-central-1/registry/README.md)
  creates one repository per locked purpose (B1);
- this script copies the images in (B3).

It is code only: it has never been run against AWS, a registry or real images.

| Purpose | Copied from (pinned digest) | Copied to |
| --- | --- | --- |
| `istio-pilot` | `docker.io/istio/pilot@sha256:5383df36…` (tag `1.32.0`) | `<account>.dkr.ecr.ca-central-1.amazonaws.com/<project>-dev-ecr-istio-pilot:1.32.0` |
| `istio-proxy` | `docker.io/istio/proxyv2@sha256:b8d47c6d…` (tag `1.32.0`) | `…/<project>-dev-ecr-istio-proxy:1.32.0` |
| `lbc` | `public.ecr.aws/eks/aws-load-balancer-controller@sha256:fd51f0ec…` (tag `v3.6.2`) | `…/<project>-dev-ecr-lbc:v3.6.2` |

### Commands

The default command is an offline plan. It re-proves the lock with the Kubernetes
validator's own check (`verify_image_lock`: raw manifest bytes, index digests, every
platform and child manifest, the pinned chart versions) and prints each copy. It
starts no process and makes no network, registry or AWS call, so it also runs in CI:

```bash
python3 scripts/local-workflow/mirror_images.py
```

`--project`, `--account-id` and `--purpose <purpose>` (repeatable) fill in or narrow
the plan. A purpose that is not in the lock is refused.

`mirror` copies and verifies, from the operator's workstation only. Prerequisites:
- skopeo with `--preserve-digests`;
- AWS CLI v2 with your own profile;
- the applied `registry` root, with its `local.auto.tfvars`.

Run it from the repository:

```bash
python3 scripts/local-workflow/mirror_images.py mirror --project <project> --account-id <account ID>
```

### Checks before anything is copied

Any failed check stops the run with a fixed `Stopped:` or `Refused (...)` code.
1. **Where it runs.** `mirror` is refused with the same markers as `run.py`: CI, cloud
   sessions, the placeholder credentials, an AWS endpoint override. It is also refused
   when `AWS_REGION` or `AWS_DEFAULT_REGION` names another Region.
2. **Values.** The project and account must be valid and not placeholders. They must
   equal the registry root's `local.auto.tfvars` and its applied `registry` output:
   - the host;
   - the repository name, ARN and URL for every locked purpose;
   - nothing else.
3. **Caller.** `aws sts get-caller-identity` must return that account.
4. **Repositories.** `aws ecr describe-repositories` must find the three repositories
   in that account, each with:
   - the expected ARN and URL;
   - `IMMUTABLE` tags without exclusions;
   - AES256 encryption.

   The script never creates a repository; a missing one stops the run.
5. **Upstream tags.** Each upstream tag must still resolve to the locked index, byte
   for byte (`skopeo inspect --raw --no-creds`). A moved tag stops the run before any
   copy. Updating the lock is a reviewed change to `kubernetes/images.lock.json` and
   its raw manifest.
6. **Destination state.** For each repository (`aws ecr describe-images`):
   - The locked tag on the locked index is already done: it is skipped and verified.
   - The locked tag on any other digest stops the run (`destination_tag_conflict`).
     The tags are immutable, and the script never overwrites one.
   - An image that is neither the locked index nor one of its child manifests, or a
     tag other than the locked one, also stops the run.

After a typed confirmation (the project name), each missing image is copied by the
locked digest, never by the tag:

```bash
skopeo --policy <temporary policy> copy --all --preserve-digests --src-no-creds --src-tls-verify=true --dest-tls-verify=true --dest-authfile <temporary authfile> docker://<source>@<digest> docker://<host>/<project>-dev-ecr-<purpose>:<tag>
```

- **All platforms.** `--all` keeps every platform in the index; the copy is never
  reduced to `linux/amd64`.
- **No conversion.** `--preserve-digests` makes skopeo fail rather than change a
  manifest. No conversion, recompression or signature option is passed, and the script
  refuses such options in any skopeo call.
- **Policy.** The temporary policy rejects every image except the three locked
  upstream repositories. Integrity comes from the pinned digests, not from signatures.

### Verification after each copy

The copy is read back in two independent ways:
- **Raw bytes.** The index from ECR (`skopeo inspect --raw`) must equal the committed
  raw manifest, so its SHA-256, media type, platforms and child digests equal the lock.
- **ECR API.** `aws ecr describe-images` must list exactly:
  - the locked index, with the locked tag;
  - every child manifest, each with its media type.

Anything else is not success. A converted or single-platform copy, or a missing child
manifest, stops the run.

### Credentials

- **ECR token.** It goes from `aws ecr get-login-password` straight into `skopeo login
  --password-stdin`. It never appears in an argument, in output, in Git or in
  Terraform.
- **Work directory.** The authfile and the policy live in a new 0700 directory under
  `TMPDIR`, which must be outside the repository. The directory is deleted when the
  run ends, also after a failure or `SIGTERM`.
- **Deletion is checked.** If the directory cannot be deleted, or still exists
  afterwards, the run is never successful. It stops with `authfile_cleanup_failed`
  and a non-zero exit code. The code is followed by the original stop code if there
  was one, and the output names the directory to delete. A failure to create the
  directory stops with `workdir_unavailable` before any login. Either way, the umask
  and signal handlers the script changed are restored. No message contains the token.
- **Upstream access.** Upstream registries are read anonymously, and TLS verification
  stays on everywhere.
- **AWS calls.** Only the read-only `sts get-caller-identity`, `ecr
  describe-repositories` and `ecr describe-images`, plus `ecr get-login-password`, are
  allowed. Pushing happens only through `skopeo copy` into the three locked
  repositories.
- **No endpoint redirection.** `AWS_ENDPOINT_URL*` variables are refused before
  anything runs. Every AWS CLI call also runs with
  `AWS_IGNORE_CONFIGURED_ENDPOINT_URLS=true`, so an `endpoint_url` in your AWS config
  or profile cannot send it elsewhere. No call passes `--endpoint-url`.

### Re-runs and recovery

`mirror` is idempotent. It stops at the first failure and reports:
- which images are verified;
- which image failed;
- which images were not attempted.

It never reports a partial copy as success, and it never deletes or overwrites an
image or a repository. It never sets `force_delete`.

| Stopped with | What to do |
| --- | --- |
| `copy_failed`, `interrupted`, `upstream_unavailable`, `ecr_login_failed`, `registry_login_failed` | Fix the cause (network, credentials) and run `mirror` again. Verified images are skipped. Child manifests that a failed copy left behind belong to the locked index and are accepted |
| `upstream_tag_moved` | Copy nothing. Re-pinning is a reviewed lock change (B2 procedure), never a script option |
| `destination_tag_conflict`, `destination_unexpected_image`, `destination_unexpected_tag` | Copy nothing more. Find out what wrote the image. Removing it needs an Owner decision, for example the registry root's teardown switch (runbook §7); the script deletes nothing |
| `destination_digest_mismatch`, `destination_index_mismatch`, `destination_children_missing` | Do not use the image. The copy changed or lost a manifest (check the skopeo version). Clean-up needs an Owner decision, as above |
| `repository_missing`, `repository_*`, `registry_root_values_mismatch`, `registry_output_mismatch`, `caller_account_mismatch` | Apply the registry root with the same project and account, or correct the values or the AWS profile |
| `authfile_cleanup_failed` | Delete the directory named in the output now: it holds an ECR login, valid for up to 12 hours. Treat the run as failed even if images were copied. Run `mirror` again to verify them |
| `workdir_unavailable`, `workdir_inside_repository` | Point `TMPDIR` to a writable directory outside the repository and run `mirror` again |

### Not covered

These are NOT_TESTED and outside this script:
- creating the repositories in real AWS;
- real image pulls and pushes, and a multi-platform mirror into ECR;
- the nodes' pull through the ECR interface endpoints and S3 over NAT;
- admission and an image allowlist (F20, an improvement candidate);
- the registry-level scanning configuration and its Amazon Inspector charges.

OCI referrers are not copied or verified. Nothing here claims that signatures, SBOMs
or attestations reached ECR.

`test_mirror_images.py` (Full CI) covers the plan with process creation and sockets
disabled, and the mirror against fake `aws`, `skopeo` and `terraform` executables:
- the exact copy arguments and the verified result;
- re-runs and partial failures;
- moved tags, conflicting tags, unexpected images, converted, single-platform and
  incomplete copies;
- account, Region, project and repository mismatches;
- the token and the authfile, including a failed deletion of the authfile and a failed creation of the work
  directory, with the umask and signal handlers restored;
- a profile `endpoint_url` in the AWS config, which must not redirect any AWS CLI call;
- the refusal in CI and cloud sessions.

It also applies source mutations that each remove one guard, and requires every one
to be detected.
