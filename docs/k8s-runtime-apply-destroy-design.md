# Kubernetes runtime apply and destroy: design record (item 6c-B2)

This is the design record for the staged Kubernetes runtime `apply` and `destroy`
of Step 1 item 6c. It has four parts:

- the design contracts;
- the mandatory corrections that later pull requests must make;
- the Owner Decision Matrix D1–D23;
- the gates between the implementation pull requests.

**Status: design only.**

- `apply` and `destroy` are not implemented. Nothing here was executed against a
  cluster, AWS or the Emulator.
- Review history:
  - 2026-11-22: independent design review of the first draft, REQUEST DESIGN
    CHANGES.
  - Same day: review of the revision, CONDITIONAL APPROVE.
- The Owner approved only the creation of this documentation pull request.
- No decision D1–D23 is adopted. Every recommendation below is a proposal until the
  Owner approves it explicitly, at the time given in the matrix.
- Baseline: `main` at `c96ec9d` (after 6c-B1, PR #87).

Related records:
- [script description](../scripts/local-workflow/README.md#apply-and-destroy-preconditions-and-open-decisions-not-implemented)
- [runbook §7](dev-runbook.md#7-teardown)
- [step plan](deployment-configuration.md#8-step-plan)
- [audit report](step1-audit-report.md) (findings F22 and F23)

## 1. Vocabulary and readiness levels

Source/offline quality and permission to run against a real cluster are separate
statements. Neither implies the other.

| Level | Meaning | Who establishes it |
| --- | --- | --- |
| Source/Offline PASS | The code and its fake-kubectl or fake-API tests, negative and mutation checks, Full CI and Offline Contracts pass on the exact pull request HEAD | Pull request CI and independent review |
| Live verification approved | The Owner has approved a specific Live verification scope (method, budget, G01–G07, teardown) outside Codex Cloud | Owner decision |
| Operational apply allowed | Every mandatory precondition of a stage is verified on the real cluster, not NOT_VERIFIED | Live evidence, then Owner acceptance |

Rules:
- Completing 6c-B3b, or 6c-B4, is Source/Offline PASS only. It is never described
  as "Live deploy ready" or "deployable".
- A mandatory precondition that is NOT_VERIFIED fails closed. This covers Secrets,
  webhooks, ECR images, ownership, digests and the TLS boundary. The command stops
  before changing anything. It never proceeds on an assumption.
- Results use the repository vocabulary: PASS, FAIL, BLOCKED, NOT_TESTED,
  NOT_VERIFIED, UNVERIFIED. An emulator result is never Live evidence; the
  Kubernetes runtime is outside the Emulator scope.

## 2. Facts the design relies on

| # | Fact | Source |
| --- | --- | --- |
| E1 | The Istio validating webhooks render `caBundle: ""` (`base.validationCABundle` defaults to empty). The chart comment says istiod patches the `caBundle` at run time. The injector omits `caBundle` when it is empty | `base` and `istiod` 1.32.0 templates in `kubernetes/vendor/` |
| E2 | The bundle references every image as `<ecr>/<repository>@<index digest>`. `images.lock.json` also holds the per-platform digests and `required_platform: linux/amd64` | `kubernetes/tools/common.py` `image_refs`, `kubernetes/images.lock.json` |
| E3 | `k8s_certs.py register` checks the local material, the context and that the three namespaces exist. It then applies the four Secrets with field manager `<project>-k8s-certs`. It never reads them back | `scripts/local-workflow/k8s_certs.py` `register` |
| E4 | `k8s_certs.py delete` deletes by name with `--ignore-not-found`. It has no UID precondition, no ownership check and no absence check afterwards | `k8s_certs.py` `delete` |
| E5 | Ownership of the resources the runtime depends on is split across roots:<br>• platform: NLB, target group, controller IRSA role<br>• network: ELBv2 and STS endpoints<br>• developer-access: tunnel | Root sources, runbook §7 |
| E6 | Webhooks and policies do not intercept DELETE:<br>• all webhooks are `failurePolicy: Fail`<br>• the TargetGroupBinding webhooks and both policies cover CREATE and UPDATE only<br>• the sidecar injector covers Pod CREATE only | Offline render of a synthetic fixture with the pinned Helm |
| E7 | The bootstrap role's access entry is STANDARD, with `AmazonEKSClusterAdminPolicy` at cluster scope. The authentication mode is `API` and audit logs are kept for 30 days | `infra/modules/eks_platform` |
| E8 | The controller's IAM allows only:<br>• EC2 Describe calls<br>• `DescribeTargetGroups` and `DescribeTargetHealth`<br>• Register and Deregister on the platform target group | `infra/modules/private_ingress/iam.tf` |

The statement that EKS access policy permissions do not carry over to an
impersonated identity comes from the independent review. It could not be read
from the AWS documentation in this session, so it is NOT_VERIFIED here (section 7).

## 3. Mandatory corrections before implementation

### C1 / D23: Istio `caBundle` ownership (finding F23)

**Problem.** With the current bundle the runtime's server-side apply would own
`caBundle: ""` on two webhooks:
- `istiod-default-validator`
- `istio-validator-<project>-v1-istio-system`

istiod then writes the real bundle. A later apply sets the field back to a
different value than the one istiod owns, which is a field conflict. Forcing the
apply would erase the bundle. Both webhooks fail closed, so every Istio resource
write would then fail.

**Field ownership versus conflict.**
- *Ownership*: a manager's entry in `managedFields` for a field.
- *Conflict*: an apply that sets a field to a value different from the one another
  manager owns.
- An apply that sets the same value shares ownership and does not conflict.
- An apply that omits a field makes no claim on it. A field the applier owned
  alone and now omits is removed.
- An Update by another manager that changes a value takes that field's ownership
  away from the applier.

**Required behaviour, by phase:**

| Phase | Required behaviour |
| --- | --- |
| First apply | The applied configuration of the two validators and of `istio-sidecar-injector-<project>-v1` contains no `caBundle`, so the runtime never owns it |
| istiod sets the CA | istiod writes `caBundle` through an Update, so istiod owns it. The runtime does not wait for or assume this |
| Re-apply | The applied configuration still omits `caBundle`, so there is neither a change nor a conflict. If any applied configuration claims `caBundle` on these webhooks, apply stops before sending (`istio_cabundle_ownership_unsafe`). It is never forced |
| Readiness | Each of the three webhooks must have a non-empty `caBundle` owned only by the allowed Istio manager (section 10). Any other state is NOT_READY or UNVERIFIED |

**Requirements on later pull requests:**
- The bundle change (omit the empty `caBundle` on these three webhooks) is a
  renderer contract change, candidate contract version 5. It is **not**
  implemented here. It is a mandatory entry condition of the first pull request
  that enables `apply` for the base or istiod stage (6c-B3b), with plan tests that
  pin it.
- Until then, `apply` must refuse the base and istiod stages.
- The AWS Load Balancer Controller webhook keeps the `caBundle` the renderer sets
  from the public CA. The runtime owns it, and any other manager on it stops apply.
- Live behaviour is NOT_VERIFIED and never inferred as PASS. This covers istiod's
  manager name, its Update and whether it also writes `failurePolicy`.

### G9: safe Secret cleanup (finding F22)

**Problem.** The current `k8s_certs.py delete` must not be used by the runtime
destroy, because it does not check UIDs (E4). Deleting a namespace deletes its
Secrets, so namespace deletion stays BLOCKED until this is fixed.

A safe cleanup must, for each of the four Secrets:
1. read metadata only (section 8);
2. check:
   - the label `app.kubernetes.io/managed-by: k8s_certs.py`;
   - that the `<project>-k8s-certs` Apply entry is present;
   - that no unexpected manager is present;
   - the UID recorded for the registration (a new k8s_certs receipt);
3. delete with a UID precondition (D19);
4. confirm NotFound;
5. record the result.

A Secret that fails any check is reported and left in place. A Secret in
`kube-system` cannot be removed by deleting a namespace, so its cleanup is its own
completion condition.

| Option | Advantages | Disadvantages |
| --- | --- | --- |
| Inside 6c-B4 | One pull request for all destroy behaviour | Mixes Secret handling with the stage destroy engine; a larger security review |
| **Independent pull request before 6c-B4 (recommended)** | Small, security-focused review of a different script; `register` can gain its UID receipt in the same change; 6c-B4 then depends on a merged, reviewed cleanup | One more pull request |

### D19: DELETE with a UID precondition

`DeleteOptions.preconditions.uid` closes the window between the ownership check
and the deletion. `kubectl delete` is not known to accept preconditions (NOT_VERIFIED,
believed unsupported). **No DELETE is enabled until the Owner decides the method.**

| Option | Description | Advantages | Risks |
| --- | --- | --- | --- |
| Kubernetes API client library | A pinned, vendored client sends `DELETE` with a `DeleteOptions` body and metadata-only GETs | Complete API support | Large new dependency and supply-chain surface; its kubeconfig loader runs exec plugins itself, so the existing kubeconfig verification has to be reproduced around it |
| **Limited direct API (recommended)** | Standard-library HTTPS with exactly two verbs: `DELETE` with `preconditions.uid` (and `resourceVersion` where useful), and `GET` with `Accept: application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1`. Paths are built only from the 62 inventory identities and the four Secret identities | No new dependency; the allowlist is narrow and testable with a fake server | Own TLS and HTTP code that must be reviewed and tested |
| kubectl | `kubectl delete` (and `--raw`) | Existing tool | Preconditions and request bodies are not supported or not verified; not acceptable unless proven |

Any method must keep the existing verification boundary:
- the kubeconfig check in `k8s_certs.check_kubeconfig`:
  - server `https://127.0.0.1:<port>` through the developer-access tunnel;
  - the cluster's own `certificate-authority-data`;
  - `tls-server-name` equal to the platform endpoint host;
  - `aws eks get-token` for that cluster;
- TLS verification against that CA and server name, never disabled;
- the token held in memory only: never in arguments, files, logs or receipts;
- refusal of automation and of any context other than `<project>-dev-eks`.

## 4. Apply design contract

**Command:**

```bash
k8s_runtime.py apply --input <runtime-input.json> --helm <pinned helm> --expect-manifest-sha256 <sha> --expect-input-sha256 <sha> [--from STAGE] [--through STAGE]
```

1. **Gate.**
   - Refuses automation, an unapproved scope and a mismatched typed project
     confirmation.
   - Refuses any range that includes ingress (`ingress_execution_gate_blocked`).
   - Refuses the base and istiod stages until C1 is implemented.
2. **Pinning.**
   - Re-runs `plan()`; the manifest and input SHA-256 must equal the expected values.
   - Never accepts a bundle from outside.
3. **Cluster re-verification.**
   - Uses the same preflight as `status`.
   - Adds the cluster fingerprint (D17), which must match the receipt.
4. **Receipt.** Takes the receipt lock and reconciles the journal (section 6). Any
   QUARANTINED entry stops the run.
5. **Per stage, in plan order:**
   - write-ahead INTENT;
   - ownership check (section 10);
   - server-side apply with field manager `<project>-k8s-runtime`, without
     `--force-conflicts` (D8);
   - RESULT with UID;
   - readiness by kind;
   - admission probes, where Live approval exists (section 11);
   - `STAGE_DONE`.
6. **Preconditions.**
   - Mandatory: Secrets, the public CA, image digests in ECR, webhook endpoints,
     Ready nodes in the selected zones, and the ELBv2 endpoint for ingress.
   - Any of these that is NOT_VERIFIED stops the run (section 1). It is never
     treated as met.
7. **Exit codes.**

   | Code | Meaning |
   | --- | --- |
   | 0 | Applied and observed ready |
   | 1 | Refused |
   | 2 | Preflight stop |
   | 3 | Undetermined or NOT_VERIFIED |
   | 4 | Apply failure: conflict, foreign owner, foreign field, API error |
   | 5 | Readiness timeout |

   Reason codes include:
   - `field_conflict`
   - `foreign_owner`
   - `foreign_field`
   - `quarantined`
   - `uid_changed`
   - `istio_cabundle_ownership_unsafe`
   - `secret_metadata_only_unsupported`
   - `dry_run_unsupported`
   - `digest_not_verified`
8. **No automatic rollback and no adoption.**
   - A rerun with `--from` re-verifies every earlier stage.
   - A bundle that differs from the applied one stops (D10).

Readiness by kind:

| Kind | Ready when |
| --- | --- |
| Namespace | Active, with the expected labels |
| CRD | Established and NamesAccepted |
| Webhook configurations | Their Deployment and endpoints are ready, and the C1 condition holds for the Istio webhooks |
| Deployment | Available, `observedGeneration` current, all Pods ready, digest checked (section 9) |
| Service | It has endpoints |
| RBAC | Present, with no diff |
| ValidatingAdmissionPolicy | Type checking has no warnings, its binding is `Deny`, and the probes classify correctly |
| TargetGroupBinding | BLOCKED (D1) |

## 5. Destroy design contract

1. The same gate, pinning, preflight and fingerprint checks as apply. A missing
   receipt stops the run (`receipt_missing`); nothing is deleted.
2. **Reverse stage order, one exact identity at a time.**
   - Each deletion requires all three to agree:
     - the receipt UID;
     - the live UID;
     - the runtime's Apply entry plus only allowed managers (section 10).
   - Then it deletes with a UID precondition (D19).
   - Forbidden: `--all`, label selectors, `--force`, `--grace-period=0` and
     stripping finalizers.
3. **Ingress.**
   - The operator deletes the TargetGroupBinding while the controller, its
     webhooks, the admission policies, the IRSA role, the target group, the ELBv2
     and STS endpoints and the tunnel all still exist. The controller removes its
     finalizer through an UPDATE that passes those webhooks and the policies.
   - Wait, bounded, for the finalizer removal (`tgb_finalizer_stuck`).
   - A TargetGroupBinding not in the receipt is foreign and stops the run.
   - Creation is by the binding writer; deletion is by the operator. No policy or
     webhook intercepts DELETE (E6).
4. **Webhook configurations before their Deployments.**
   - Delete the admission policies only when no TargetGroupBinding remains and the
     ingress namespace has no LoadBalancer Service.
   - Delete the istiod webhooks only when no Istio custom resource remains.
5. **Secret cleanup before namespace deletion** (G9; BLOCKED until G9 and D19 are
   implemented).

   | Namespace | Required before deletion |
   | --- | --- |
   | `istio-system` | • The receipt UID matches<br>• `cacerts` cleaned up and confirmed absent<br>• no Secret at all remains, including a self-signed `istio-ca-secret`<br>• only allowed leftovers remain |
   | `<project>-ingress` | • The receipt UID matches<br>• no TargetGroupBinding, and the finalizer is confirmed gone<br>• both gateway Secrets cleaned up and confirmed absent<br>• no other Secret, only allowed leftovers |
   | `<project>-app` | • The receipt UID matches<br>• it holds no k8s_certs Secret, and **any** Secret or any object outside the inventory stops destroy, because it protects future applications |
   | `kube-system` | Never deleted. The webhook TLS Secret is cleaned up explicitly and confirmed absent, as its own completion condition. Controller leases are reported, not deleted |

   The allowed leftovers are:
   - the default ServiceAccount;
   - the ConfigMaps `kube-root-ca.crt` and `istio-ca-root-cert`;
   - istiod leader leases and ConfigMaps;
   - Events;
   - ReplicaSets, Pods and EndpointSlices whose `ownerReferences` chain to a
     receipt UID.

   Deleting a namespace that still holds a Secret needs a separate explicit Owner
   approval (D18).
6. **CRDs are kept** (D5).
   - Runtime destroy is complete when all of these hold:
     - the 45 non-CRD objects are absent;
     - the four Secrets are absent;
     - every one of the 17 CRDs has zero custom resources;
     - the retained CRDs are listed.
   - The CRDs go with the EKS cluster.
7. **Partial failure.**
   - Absent objects are confirmed by NotFound and UID before being skipped.
   - A rerun continues from the receipt.

## 6. Ownership receipt and crash recovery (D7, D16, D17)

- **Location.**
  - Outside the repository, default `~/.local/state/<project>-k8s-runtime/<cluster fingerprint>/`.
  - Directory 0700; files 0600, created with `O_EXCL`.
  - Symlinks and foreign owners are refused.
- **Content.**
  - Recorded: identities, UIDs, `resourceVersion`, `generation`, the manifest and
    input SHA-256, the cluster ARN and fingerprint, timestamps and result codes.
  - Never recorded: Secret values, object bodies, tokens or kubeconfig contents.
  - Fields are allowlisted, and secret-like values are rejected, as in the evidence
    ledger.
- **Write-ahead journal.**
  - `journal.jsonl` is appended and fsynced per record.
  - Each object gets, in order:
    1. INTENT: sequence, stage, identity, the prior state (absent, or present with
       UID and ownership) and the planned action;
    2. the apply;
    3. RESULT, read back with UID, `resourceVersion`, `generation` and the
       runtime's managedFields entry.
  - Then `STAGE_DONE`.
  - `receipt.json` is a snapshot written to a temporary file, fsynced, renamed and
    the directory fsynced. The journal wins on any disagreement.
- **Reconciliation on restart.**

  | Journal | Cluster | Result |
  | --- | --- | --- |
  | INTENT only, prior absent | absent | Not applied; retry |
  | INTENT only, prior absent | present | **QUARANTINED**: creation cannot be proven; never adopted |
  | INTENT only, prior owned | same UID | Re-apply (idempotent) |
  | RESULT | same UID | Consistent |
  | RESULT | different UID or absent | `uid_changed`: recreated by someone; stop |

- **Recovery rules.**
  - Only an explicit Owner action with the expected UID releases a QUARANTINED
    entry. The action and its reason are recorded in the journal (D16).
  - A missing receipt stops destroy, and stops apply wherever objects exist.
  - The resolution is the platform destroy or an Owner-approved procedure.
  - Unapproved objects are never adopted. A managedFields manager name alone is
    never proof of ownership.
- **Cluster fingerprint.** The `kube-system` namespace UID plus the cluster ARN
  (D17), so a receipt never applies to a recreated cluster with the same name. It
  needs the read scope in D3.
- **Preconditions.**
  - Deletion uses `preconditions.uid` (D19).
  - Putting `metadata.uid` in the applied configuration as an update precondition
    is NOT_VERIFIED and is not relied on.

## 7. Binding writer authorization (D1)

Impersonation (option A) is authorized in two separate steps.

| Step | Identity evaluated | Authorizers | Permission |
| --- | --- | --- | --- |
| 1. Impersonate | The operator (the IAM principal of the access entry) | EKS access policy authorizer plus RBAC | `impersonate` on `serviceaccounts`, namespace `<project>-ingress`, name `<project>-binding-writer` |
| 2. The request | `system:serviceaccount:<project>-ingress:<project>-binding-writer` with its automatic groups | **Kubernetes RBAC only.** Per the review, access policy permissions do not carry over (NOT_VERIFIED here) | The binding-writer Role: `create` on TargetGroupBindings, plus `get`, `update`, `patch` and `delete` limited to `<project>-gateway` |

**What the RBAC grants and what it cannot limit.** RBAC cannot limit `create` by
name. The admission policy limits the binding's name, fields and actor.

**No additional RBAC is needed when both hold:**
- step 1 is granted by the access policy;
- the service account's effective permissions equal the expected set: the Role
  plus the Kubernetes discovery and self-review defaults.

**If step 1 is not granted:**
- Add a Role and RoleBinding in `<project>-ingress`: `impersonate` on
  `serviceaccounts`, `resourceNames: [<project>-binding-writer]`.
- Bind it to a Kubernetes group set through the access entry's
  `kubernetes_groups`. The username can vary by session, so it is not a stable
  subject.
- That is a Terraform and RBAC change with its own approval.
- A ClusterRole or ClusterRoleBinding would be needed only for user, group or UID
  impersonation. `--as-group`, users and `--as-uid` are forbidden, so none is
  needed.

**Live checks (separately approved, not run):**
1. `kubectl auth can-i impersonate serviceaccounts/<project>-binding-writer -n <project>-ingress`.
2. `kubectl auth can-i --list` as the service account, in the namespace and cluster
   wide. The result must exactly equal the expected set; anything broader stops
   with `unexpected_sa_permissions`.
3. Probes C to E (section 11).
4. Audit log entries with the operator as user and the service account as
   `impersonatedUser` (a CloudWatch Logs read, D4).

Option A stays the first candidate and is not approved. TokenRequest (B) and a
one-off in-cluster Job (C) stay alternatives. Ingress stays BLOCKED.

## 8. Secret verification boundary (D2)

- **Metadata only shows:**
  - presence, name, namespace, UID, `resourceVersion`;
  - labels and annotations;
  - creation and deletion timestamps;
  - `managedFields`.
- **What `managedFields` adds.** An Apply entry of `<project>-k8s-certs` that owns
  `f:type` and `f:data.f:<key>` shows that manager applied those fields. It is
  supporting evidence only, not a check of the stored type or keys.
- **NOT_VERIFIED:**
  - the stored `type` and key set;
  - certificate and CA content;
  - key-to-certificate match;
  - expiry.
- **`register` guarantees** the local material checks, the context checks, that the
  namespaces exist and that the server accepted the apply (E3). It does not
  guarantee what is stored.
- **Indirect non-secret evidence** (Live, needs D3 and D21):

  | Secret | Evidence |
  | --- | --- |
  | `cacerts` | The `istio-ca-root-cert` ConfigMap's root certificate equals the local public root. istiod readiness is not evidence: without `cacerts` it falls back to a self-signed CA |
  | Webhook TLS | A server-side dry-run through the controller webhook succeeds, which proves the chain to the public CA only |
  | Gateway TLS | Needs ingress, so BLOCKED |

- **Fail closed.**
  - The method must provably request `PartialObjectMetadata`.
  - A response whose `kind` is not `PartialObjectMetadata` (or its list), or that
    contains `data` or `stringData`, is discarded unprinted and stops the run
    (`secret_metadata_only_unsupported`). The value has already been transferred by
    then; that residual risk is why the method must be proven first.
  - **Never fall back automatically to reading the full Secret.**

## 9. Image digest verification

| Layer | Value | Check |
| --- | --- | --- |
| Lock | Index digest and `linux/amd64` platform digest | Source of truth |
| Bundle | `@<index digest>` | Pinned by `plan` |
| ECR | The index digest exists as a manifest list, and the amd64 child exists | AWS read (D4) |
| Node | `nodeInfo.architecture` is `amd64` | Node read (D3) |
| Pod | Spec image equals the bundle reference, including the injected proxy; `imageID` digest | Pod read (D3) |

How the `imageID` digest is classified:

| `imageID` digest | Result |
| --- | --- |
| Equals the index digest | `MATCH_INDEX`. The running child manifest is not proven, so the platform stays NOT_VERIFIED, even with an amd64 node and the ECR child present |
| Equals the platform digest, on an amd64 node | `MATCH_PLATFORM`: matched down to the platform |
| Any other digest | `digest_mismatch`: stop |
| Missing or unparseable | NOT_VERIFIED, which fails closed |

## 10. Field ownership

Only the runtime manager `<project>-k8s-runtime` (operation Apply) and the entries
below are allowed. Any other manager, operation, kind, name or field path stops
the run (`foreign_field`).

| Manager | Operation | Kind and name | Field paths | On drift |
| --- | --- | --- | --- | --- |
| Any manager with `subresource: status` | Update | Kinds with a status subresource (CRD, Deployment, ValidatingAdmissionPolicy, TargetGroupBinding) | `f:status` only | Read for readiness only |
| istiod (manager name NOT_VERIFIED) | Update | The three Istio webhooks of C1 | `f:webhooks[name=<fixed>].f:clientConfig.f:caBundle`; `f:failurePolicy` only with value `Fail` | Any other path or value stops |
| AWS Load Balancer Controller (manager name NOT_VERIFIED) | Update | TargetGroupBinding `<project>-gateway` only | `f:metadata.f:finalizers` entry `elbv2.k8s.aws/resources` | Any other finalizer stops |
| `<project>-k8s-certs` | Apply | The four Secrets only | The whole Secret | Outside the 62 runtime objects |

How drift is handled:
- A drifted runtime-owned field is restored by re-apply.
- A field the runtime shares with another manager at a different value is a
  conflict, so apply stops (D8, D13).
- `status` reports DRIFT.
- Destroy tolerates drift in runtime-owned fields, but stops when another manager
  owns any spec field.

## 11. Server-side dry-run and admission probes (D9, D20)

**These are real API calls.**
- `--dry-run=server` and `kubectl diff --server-side` pass authentication,
  authorization, the mutating and validating webhooks and the admission policies.
- They are recorded in the audit log.
- A webhook backend may itself call AWS. For example, the controller webhook may
  read the target group.
- They are implemented and tested only against fakes. They are **never run against
  a real cluster** without the Live approval in D20.

**Side effects.**
- The API server rejects a dry-run unless every matching webhook declares
  `sideEffects: None` or `NoneOnDryRun`.
- Bundle webhooks are checked in advance. Webhooks outside the bundle cannot be
  known (NOT_VERIFIED).
- A rejection stops the run (`dry_run_unsupported`); it is never a pass.

| Probe | Identity | Request | Expected |
| --- | --- | --- | --- |
| A | Operator | LoadBalancer Service in `<project>-ingress` | Denied by the `no_lb_service` policy with its message |
| A' | Operator | Ingress in `<project>-ingress` | Same |
| B | Operator (not the writer) | TargetGroupBinding | Denied by the TargetGroupBinding policy: "Only the reviewed Platform binding/identity is permitted." |
| F | Operator | Invalid Istio resource | Denied by webhook `validation.istio.io` |
| G | Operator | Pod in `<project>-app` | Allowed; the returned object contains the injected proxy with the bundle image |
| C–E | Binding writer | Section 7 | BLOCKED (D1) |

A probe passes only when the outcome class and the source name or message match
exactly. Any other class is FAIL or UNVERIFIED, even if it is a denial. For
example, `authz_denied` for probe B does not prove the policy.

| Class | Recognised by |
| --- | --- |
| `authz_denied` | 403, "cannot `<verb>` resource" |
| `webhook_denied:<name>` | `admission webhook "<name>" denied` |
| `vap_denied:<name>` | `ValidatingAdmissionPolicy '<name>' with binding '<name>' denied request` |
| `webhook_unreachable` | `failed calling webhook`; stop |
| `schema_invalid` | 422 |

## 12. Complete teardown order (D12)

Target order (runbook §7 keeps the current procedure until runtime destroy exists):

1. api
2. serverless-api
3. Runtime destroy, ingress stage: delete the TargetGroupBinding and confirm the
   finalizer is removed and the targets are deregistered (D4).
4. Runtime destroy, remaining stages in reverse order, with the Secret cleanup (G9)
   before the namespaces and the `kube-system` webhook TLS Secret cleanup.
5. developer-access (the tunnel goes away)
6. platform
7. registry
8. network
9. tfstate

Until the TargetGroupBinding finalizer is gone, nothing it depends on is removed:
the controller, its IRSA role and policy, the target group, the ELBv2 and STS
endpoints, and the tunnel. Skipping steps 3–4 needs an explicit Owner approval,
and target deregistration is then NOT_VERIFIED.

Complete teardown within 72 hours requires **all** of:
- an empty `terraform state list` for every root;
- the runbook's tag search showing only the secret scheduled for deletion;
- type-by-type AWS reads (D4) of what the tag search may not show:
  - the EKS cluster;
  - the NLB and target group;
  - IAM roles;
  - EKS-created security groups and network interfaces;
  - log groups;
  - ECR repositories;
  - S3 buckets;
  - VPC endpoints;
- local cleanup:
  - kubeconfig;
  - the runtime input directory;
  - the certificate material;
  - receipts, kept or archived per D22;
- a Billing check.

Deleting the EKS cluster alone is not complete teardown.

## 13. Owner Decision Matrix D1–D23

**Status of every row: OPEN (not decided).** The Owner's approval of 2026-11-22
covers only this documentation pull request. "Needed by" is the latest point at
which the Owner must decide.

### Category 1: before Source/Offline implementation

| ID | Decision | Recommended (proposal) | Risk | Affects | Needed by |
| --- | --- | --- | --- | --- | --- |
| D7 | Ownership evidence | Receipt UID plus identity plus the section 10 allowlist; never the manager name alone | A lost receipt blocks destroy (by design) | 6c-B3a, 6c-B4 | Before 6c-B3a starts |
| D8 | Server-side apply conflicts | Never `--force-conflicts`; stop | A stop on legitimate co-ownership | 6c-B3a | Before 6c-B3a starts |
| D10 | Applying a different bundle version | Stop on any difference | Upgrades need a later design | 6c-B3a | Before 6c-B3a starts |
| D16 | Releasing QUARANTINED objects | Strict: an explicit Owner action with the expected UID only | Manual work after a crash | 6c-B3a | Before 6c-B3a starts |
| D17 | Cluster fingerprint | `kube-system` namespace UID plus the cluster ARN | Needs a small read-scope addition (D3) | 6c-B3a | Before 6c-B3a starts |
| D19 | DELETE with a UID precondition | Limited direct API (section 3) | Own TLS and HTTP code to review | 6c-B3a (design of the transport boundary), G9, 6c-B4 | Before 6c-B3a starts (method); DELETE stays disabled until implemented |
| D23 | Istio `caBundle` ownership (C1) | Omit the empty `caBundle` on the three Istio webhooks (renderer contract 5) | A renderer contract change | 6c-B3b | Before 6c-B3b starts |
| D3 | Read-scope expansion (Pods, Nodes, EndpointSlices, the `istio-ca-root-cert` ConfigMap, the `kube-system` namespace) | Fixed namespaces and labels only | A wider read surface | 6c-B3a (fingerprint), 6c-B3b | Before 6c-B3a starts (fingerprint part); before 6c-B3b (rest) |
| D2 | Secret verification method | Not in 6c-B3b: report NOT_VERIFIED, which fails closed for operational apply; never read full Secrets | Operational apply stays blocked until a method is proven | 6c-B3b, G9 | Before 6c-B3b starts |
| D13 | Allowed secondary managers | Section 10 table | False stops until Live names are confirmed | 6c-B3b | Before 6c-B3b starts |
| D9 | Dry-run and probe design | Implemented and tested against fakes only; Live use is D20 | Audit-log entries once used Live | 6c-B3b | Before 6c-B3b starts |
| D11 | Timeouts | Per-stage limits (for example CRD 2 min, Deployment 10 min, finalizer 10 min) | Too short gives false stops | 6c-B3b, 6c-B4 | Before 6c-B3b starts |
| D5 | CRD deletion | Keep; deletion only with separate approval | CRDs remain until platform destroy | 6c-B4 | Before 6c-B4 starts |
| D6 | Namespace deletion conditions | Section 5 | Wrongly deleting future application data if loosened | 6c-B4 | Before 6c-B4 starts |
| D18 | Deleting a namespace that still holds a Secret | Not allowed without a separate explicit Owner approval | Cascade deletion of unmanaged Secrets | G9, 6c-B4 | Before 6c-B4 starts |
| D12 | Runbook teardown order | Section 12 | Unobserved deregistration if skipped | 6c-B4 (runbook) | Before 6c-B4 starts |

### Category 2: before Live verification

| ID | Decision | Recommended (proposal) | Risk | Affects | Needed by |
| --- | --- | --- | --- | --- | --- |
| D1 | Binding-writer method | A, after the section 7 checks | Section 7 | Ingress enablement, Live plan | Before any Live verification of ingress |
| D4 | AWS read APIs (ECR, ELBv2 target health, CloudWatch Logs, teardown checks) | Read only, around apply and destroy | Real AWS calls | Live verification | Before Live verification |
| D15 | Controller IAM sufficiency | Verify Live; any gap in a separate Terraform pull request | Reconcile failure | Live, a possible Terraform pull request | Before Live verification |
| D20 | Running server-side dry-run and probes against the real cluster | Inside the approved Live scope only | Audit-log entries; webhook-side AWS reads | Live verification | Before Live verification |
| D21 | Adding the public Istio root to the input provenance | Add (input contract change) | A contract change | A later input pull request | Before Live verification of `cacerts` |

### Category 3: can wait for later features

| ID | Decision | Recommended (proposal) | Risk | Affects | Needed by |
| --- | --- | --- | --- | --- | --- |
| D14 | Apply only the Gateway resource of the ingress stage early | No; ingress stays BLOCKED as a whole | A partial state | Ingress | When ingress is enabled |
| D22 | Receipt retention and archiving | Keep until complete teardown, then archive locally outside the repository | Lost evidence | Destroy and teardown | Before the first Live teardown |

The alternatives stay open in Category 3:
- `--delete-crds` for D5;
- an upgrade path for D10;
- TokenRequest or a Job for D1.

## 14. Implementation pull requests and gates

Each pull request below needs its own Owner approval to start. Each stops for
independent review and Owner Squash Merge approval.

| Pull request | Scope | Acceptance criteria | Stop conditions |
| --- | --- | --- | --- |
| 6c-B2 (this) | Design record, runbook, step plan and audit report | Docs only; Full CI and Offline Contracts pass on the exact HEAD | Code, renderer, CI or workflow changes |
| 6c-B3a | Gate, pinning, cluster fingerprint, journal and receipt store, reconciliation, QUARANTINED, read-only `receipt verify`, and the D19 transport boundary if the Owner decides it here. **`apply` stays refused** | Fake tests (negative and mutation) for:<br>• crash between INTENT and RESULT<br>• UID change<br>• missing receipt<br>• modes, symlinks and owners<br>• secret-like values<br>• atomic replace<br>Existing plan 29/39 and status 21/32 kept; Full CI and Offline Contracts pass | Any need for `infra/**`, renderer, RBAC or admission changes; enabling `apply` |
| 6c-B3b | `apply` for stages 1–8, ingress refused, plus C1 (renderer contract 5), readiness, ownership table, digest classification, probe classification against fakes, and the read scope | Fake tests (negative and mutation) for:<br>• conflict<br>• foreign field<br>• C1 refusal<br>• digest mismatch or NOT_VERIFIED<br>• probe misclassification<br>• timeout<br>• `dry_run_unsupported`<br>• ingress refusal<br>• NOT_VERIFIED preconditions failing closed<br>Plan tests pin contract 5. It is Source/Offline PASS only, never "Live deploy ready" | Enabling ingress; impersonation or TokenRequest code; reading full Secrets |
| G9 (independent, recommended) | Safe Secret cleanup and the registration UID receipt in `k8s_certs.py`, using the D19 transport | Fake-API tests for:<br>• UID mismatch<br>• foreign manager<br>• missing label<br>• absence after delete<br>• no full Secret read<br>• no fallback | Namespace deletion stays BLOCKED until merged |
| 6c-B4 | `destroy`: reverse order, UID preconditions, finalizer wait, namespace and Secret conditions, kept CRDs, runbook §7 | Fake tests (negative and mutation) for:<br>• UID mismatch<br>• missing receipt<br>• leftover Secret or object<br>• finalizer timeout<br>• forbidden force options<br>• `kube-system` never deleted | Without a merged D19 transport and G9 cleanup, deletion is not enabled; namespaces with Secrets only with D18 approval |
| 6c-B5 | Source/offline closure audit of item 6c | Docs; lists every NOT_TESTED, BLOCKED and NOT_VERIFIED item | No COMPLETE declaration |
| Live verification (separate) | Sections 7, 8, 9 and 11, F18, F21, D15 | Owner-approved procedure, budget and G01–G07, outside Codex Cloud | Never in Codex Cloud |

6c-B3b may be split if it grows: namespaces, base, controller and istiod first;
gateway, mesh_security, admission and binding_writer second.

## 15. Remaining BLOCKED, NOT_VERIFIED and NOT_TESTED

- **BLOCKED:**
  - ingress (D1);
  - `apply` and `destroy` (not implemented);
  - apply of the base and istiod stages until C1;
  - DELETE until D19;
  - namespace deletion until G9;
  - operational apply while any mandatory precondition is NOT_VERIFIED.
- **NOT_VERIFIED:**
  - the AWS documentation statement on impersonation (could not be read in this
    session);
  - whether the access policy grants `impersonate`;
  - the service account's effective permissions;
  - a metadata-only Secret read and whether kubectl can do it;
  - UID-precondition DELETE through kubectl;
  - `metadata.uid` as an apply precondition;
  - istiod and controller manager names and paths;
  - side effects of webhooks outside the bundle;
  - which digest `imageID` reports;
  - tag-search coverage of IAM and other types;
  - controller IAM sufficiency;
  - State freshness;
  - X.509 content.
- **NOT_TESTED (Live):**
  - `status` on a real cluster;
  - impersonation and TokenRequest;
  - RBAC;
  - admission, CEL and webhooks;
  - dry-run probes;
  - F18 (ECR pull and digest);
  - F21 (ELBv2 connectivity, registration and deregistration);
  - finalizers;
  - Secret cleanup;
  - complete-teardown residual checks.
