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
The old CA is no longer trusted. `delete` removes the four Secrets
(`kubectl delete secret --ignore-not-found`); destroying the cluster removes them too.

`test_k8s_certs.py` runs `generate` with real OpenSSL in temporary directories and
`register`/`delete` against a fake `kubectl`. It checks, among other things, that no
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
- **Secrets** are refused entirely here; their metadata reads belong to G9.
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
  - no Secrets without G9.

**Tests.** `test_k8s_runtime_receipt.py` has 39 tests and 58 source mutations, each
detected. It uses temporary stores outside the repository, the fake transport, and
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
- Secret cleanup (G9);
- the Istio `caBundle` renderer change (C1).

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
   - per object: INTENT, then fake server-side apply without force, then RESULT
     with the UID read back, then the D13 ownership check. Every write is
     conditional:
     - create only if the object is absent; update only on the recorded UID;
     - an object that appears where none was recorded stops the run before its
       INTENT (`foreign_object_appeared`);
     - a change between the engine's read and the write fails the fake's atomic
       check (`precondition_failed`), and the foreign object is left byte for byte
       unchanged;
     - how a real API server would enforce the same condition is NOT_VERIFIED;
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

**Journal schema: unchanged.** No record type was added.
- Deferral is derived from the journal: a closed stage whose resolving stage is not
  closed.
- The only new use of an existing record is the `failed` RESULT that closes an
  interrupted INTENT.
- `receipt verify` keeps its strict ownership. The D13 hook (`ownership_fn`) is
  used only by the engine.

**Tests.** `test_k8s_runtime_apply.py` has 24 tests and 40 source mutations.
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
- deferred items that a later STAGE_DONE does not resolve.

### Apply and destroy: preconditions and open decisions (not implemented)

`apply` and `destroy` are not implemented (6c-B3a added only the receipt foundation
above, and both subcommands refuse). This records what they must respect,
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
- **Secret cleanup (G9, finding F22).** The current `k8s_certs.py delete` deletes
  by name without a UID check, so the runtime destroy must not use it. Deleting a
  namespace also deletes its Secrets, so namespace deletion stays BLOCKED until a
  safe cleanup exists. That cleanup needs a UID precondition, an ownership check and
  an absence check afterwards. The `kube-system` webhook TLS Secret needs its own
  cleanup.
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
