# Kubernetes runtime apply and destroy: design record (item 6c-B2)

This is the design record for the staged Kubernetes runtime `apply` and `destroy`
of Step 1 item 6c. It has four parts:

- the design contracts;
- the mandatory corrections that later pull requests must make;
- the Owner Decision Matrix D1–D23;
- the gates between the implementation pull requests.

**Status: design record; 6c-B3a foundation, the 6c-B3b-Apply-A and Apply-B1 to Apply-B5 fake engine, G9 with the D19 Fake-only Secret extension, and the 6c-B4a destroy safety foundation implemented offline. The 6c-B4b destroy engine is not implemented.**

- `apply` and `destroy` are not implemented. Nothing here was executed against a
  cluster, AWS or the Emulator.
- 6c-B3a (Owner Decision Gate, 2026-11-22) implemented these, as Source/Offline
  code only (see section 13):
  - the receipt, write-ahead journal and crash reconciliation of section 6;
  - the fingerprint;
  - the D19 transport interface with a fake;
  - a read-only `receipt verify`.

  See the [script description](../scripts/local-workflow/README.md#receipt-crash-recovery-and-transport-boundary-item-6c-b3a-offline-foundation).
- 6c-B3b-Apply-A (Owner, 2026-11-22) added a fake-only apply engine for the
  `namespaces` and `base` stages, with no command line. See the
  [script description](../scripts/local-workflow/README.md#fake-apply-engine-for-the-first-two-stages-item-6c-b3b-apply-a-offline-only).
  - It ends in exit 6 `APPLIED_WITH_DEFERRED`, because `base`'s validator serving
    waits for `istiod`.
  - Deviation from section 4.1: deferral is derived instead of journaled with a new
    `DEFERRED` record. The journal schema is unchanged.
  - Constraint (review of PR #91): a later stage's STAGE_DONE never resolves a
    deferred item.
    - Webhook serving needs its own verification evidence (`caBundle` populated
      by the allowed manager, endpoints, a classified probe).
    - Without that evidence the item stays DEFERRED / NOT_VERIFIED.
    - Supplying that evidence is an acceptance gate for Apply-B.
  - Writes are conditional (create only if absent, update only on the recorded
    UID) and checked atomically by the fake; the Live mechanism is NOT_VERIFIED.
  - D13 ownership needs field-level evidence: the runtime must own exactly the
    manifest's nested leaf paths.
  - Review of PR #91 (P1-07): a success RESULT, and with it a newly owned UID, is
    written only after the readback proves OWNED. A write that landed but whose
    ownership or UID is unproven is quarantined (`ownership_unproven`,
    `uid_changed`, `creation_unproven`), never recorded as "not applied". It is
    neither re-applied nor adopted without the Owner (D16).
  - Review of PR #91 (P1-08): the fake's conditional write also checks field
    ownership. An update proceeds only while the object still proves OWNED
    under D13, including the runtime's own Apply entry (exactly the required
    paths). A foreign manager, a missing or partial runtime entry, or malformed
    evidence refuses the write before anything changes (`foreign_field_refused`,
    `not_owned_refused`, `ownership_not_verified_refused`). This is a property
    of the fake. Real API atomicity is NOT_VERIFIED.
- 6c-B3b-Apply-B1 (Owner, 2026-11-23) extends the fake engine to the `controller`
  and `istiod` stages, Source/Offline only, under the decisions already approved
  (D2, D3, D9, D11, D13). See the
  [script description](../scripts/local-workflow/README.md#controller-and-istiod-stages-item-6c-b3b-apply-b1-offline-only).
  - Pre-apply as in section 4.1. ECR (D4, a Category 2 decision) is read only
    from an in-memory fake; without it the stage stops NOT_VERIFIED.
  - In-stage readiness shares the D11 Deployment bound (600 s); the istiod
    `caBundle` wait introduces no new timeout.
  - Section 9 digest classification; only `MATCH_PLATFORM` passes.
  - Section 10 rows are enforced element by element (kind, object name and
    scope, fixed webhook name present on the object, manager, operation,
    subresource, path, the `failurePolicy` value `Fail`, the TargetGroupBinding
    `<project>-gateway` in `<project>-ingress` and its single finalizer).
    Outside a row is `FOREIGN_FIELD`; malformed evidence is
    `OWNERSHIP_NOT_VERIFIED`. The istiod stage re-checks the three Istio
    webhooks after the `caBundle` is written. Their names stay NOT_VERIFIED, so a rerun
    after istiod has filled a `caBundle` stops (`ownership_not_verified`), and
    istiod filling one before the engine's readback is quarantined. This is the
    accepted D13 risk ("false stops until Live names are confirmed").
  - Probes F and G are classified against the fake only (D9). A fake pass is
    recorded and never meets a Live requirement (D20).
  - Deferred items: base validator serving, controller webhook serving (probe B)
    and IRSA/AWS calls (BLOCKED), istiod CA in use (D21) and injection (probe G).
    Each needs every requirement MET; Live and BLOCKED requirements have a fixed
    status, so none can pass here.
- 6c-B3b-Apply-B2 (Owner, 2026-11-23) adds the `gateway` stage to the fake
  engine, Source/Offline only. See the
  [script description](../scripts/local-workflow/README.md#gateway-stage-item-6c-b3b-apply-b2-offline-only).
  - Pre-apply: istiod in-stage readiness in the same run, the injector
    `caBundle`, both gateway Secrets (metadata only), the `istio-proxy` digests
    (fake ECR). Then the base row's rule: validator serving not verified after
    istiod stops before the gateway.
  - That item needs Live probe F (D20) and a confirmed istiod manager name
    (D13), so the gateway is unreachable today. Every run stops with
    `deferred_readiness_unresolved:base_validator_serving` before any gateway
    write, and a rerun stops at reconcile (`ownership_not_verified`). Neither
    is bypassed.
  - The stage contract behind the gate is implemented and tested directly:
    minimal completion, readiness, revision injection (`sidecar.istio.io/status`
    and the locked `istio-proxy`), digest. The deferred gateway TLS serving
    stays BLOCKED while ingress is BLOCKED.
- 6c-B3b-Apply-B3 (Owner, 2026-11-23) adds the `mesh_security` stage, Source/Offline
  only. See the
  [script description](../scripts/local-workflow/README.md#mesh_security-stage-item-6c-b3b-apply-b3-offline-only).
  - Pre-apply: istiod in-stage readiness and the base validator serving resolved;
    the latter needs Live evidence, and a run stops at the gateway first, so the
    stage is unreachable today.
  - Behind the gate, tested directly: minimal completion, D13 ownership and the
    first drift verification ("no diff": every manifest value present and equal on
    the live object). It is limited to these five objects and the fake.
  - mTLS and authorization enforcement is fixed NOT_TESTED, never PASS.
- 6c-B3b-Apply-B4 (Owner, 2026-11-23) adds the `admission` stage, Source/Offline
  only. See the
  [script description](../scripts/local-workflow/README.md#admission-stage-item-6c-b3b-apply-b4-offline-only).
  - A run stops at the gateway gate first, so admission is unreachable today.
  - Behind it, tested directly: controller accepted and the TargetGroupBinding
    CRD Established; policy type checking without warnings (an absent report is
    NOT_VERIFIED, since no timeout is approved for it); bindings exactly `Deny`;
    ownership and no drift; probes A, A' and B classified against the fake. Each
    answer must be the whole 403 policy denial naming exactly the expected
    policy, one of its own bindings and one of its reviewed messages verbatim. A
    missing answer stops (`not_run`) and is never ready.
  - Live probes (D20) are fixed NOT_VERIFIED, so the stage is never PASS.
- 6c-B3b-Apply-B5 (Owner, 2026-11-23) adds the `binding_writer` stage, Source/Offline
  only. See the
  [script description](../scripts/local-workflow/README.md#binding_writer-stage-item-6c-b3b-apply-b5-offline-only).
  - A run stops at the gateway gate first; the stage is unreachable today.
    Ingress stays refused.
  - Behind it, tested directly: admission minimal completion re-verified at
    pre-apply; the three objects present, owned and without drift; the
    ServiceAccount's `automountServiceAccountToken` exactly `false`.
  - D1 is undecided: effective permissions, impersonation and probes C to E are
    fixed NOT_TESTED, never PASS, and no fake answer is read for them.
- Review history:
  - 2026-11-22: independent design review of the first draft, REQUEST DESIGN
    CHANGES.
  - Same day: review of the revision, CONDITIONAL APPROVE.
  - Pull request review of this record, REQUEST CHANGES (documentation only).
    That review added:
    - the stage lifecycle (4.1);
    - the destroy inventory verification (5.1);
    - the distinction between the current `status` and future drift verification;
    - the operational D22.
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
| Source/Offline PASS | The code and its fake-kubectl or fake-API tests, negative and mutation checks, PR Safety CI (and Full CI where the CI execution policy of 2026-11-23 requires it) and Offline Contracts pass on the exact pull request HEAD | Pull request CI and independent review |
| Live verification approved | Not available under Master Policy v14.5 §15: real AWS/EKS Live verification and enabling real Apply/Destroy are outside the current scope. A future scope would need a new Owner cost and execution decision and independent review (the earlier G01–G07 and budget conditions are historical) | Owner decision (none current) |
| Operational apply allowed | Every mandatory precondition of a stage is verified on the real cluster, not NOT_VERIFIED | Live evidence, then Owner acceptance |

Rules:
- Completing 6c-B3b, or 6c-B4, is Source/Offline PASS only. It is never described
  as "Live deploy ready" or "deployable".
- A mandatory condition that is NOT_VERIFIED fails closed, at the point the
  section 4.1 lifecycle assigns to it. It never proceeds on an assumption.
  - Conditions include Secrets, webhooks, ECR images, ownership, digests and the
    TLS boundary.
  - A NOT_VERIFIED pre-apply condition stops the run before that stage changes
    anything.
  - A NOT_VERIFIED in-stage readiness item stops the run before the next stage
    starts.
  - A deferred item that its resolving stage cannot verify stops the run there.
- Bootstrap needs this staging. The namespaces exist before the Secrets can be
  registered, and the base stage's webhook cannot serve before the istiod stage
  runs. So a single "verify everything first" gate cannot work.
- Deferred readiness is never a final PASS.
- Results use the repository vocabulary: PASS, FAIL, BLOCKED, NOT_TESTED,
  NOT_VERIFIED, UNVERIFIED. An emulator result is never Live evidence; the
  Kubernetes runtime is outside the Emulator scope.

## 2. Facts the design relies on

| # | Fact | Source |
| --- | --- | --- |
| E1 | **Corrected in 6c-B3b-C1.** The vendored `base` and `istiod` 1.32.0 templates emit `caBundle` only when `base.validationCABundle` (validators) or `istiodRemote.injectionCABundle` (injector) is non-empty (`{{- if ... }}`). Both default to empty, so the rendered bundle never carried a `caBundle` on the three Istio webhooks. The first version of this record said the validators render `caBundle: ""`; that was wrong (the guarding condition was missed). The chart comment says istiod patches the `caBundle` at run time C1 was therefore a latent risk (a non-empty value or changed chart default would make the runtime claim the field), now closed by contract 5 | `base` and `istiod` 1.32.0 templates in `kubernetes/vendor/`; offline render of the fixture |
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

**Status: resolved in Source/Offline by 6c-B3b-C1 (Owner decision D23, 2026-11-22),
renderer contract 5. Live behaviour NOT_VERIFIED.**

**Problem.** Correction: the pinned charts already omitted the field, because it is
rendered only for a non-empty value (E1). The risk was latent. If a value or chart
default ever made the bundle carry a `caBundle` (empty or not) on:
- `istiod-default-validator`
- `istio-validator-<project>-v1-istio-system`
- `istio-sidecar-injector-<project>-v1`

then the runtime's server-side apply would own it, and istiod writes the real bundle. A later apply sets the field back to a
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

**Implemented in 6c-B3b-C1 (renderer contract 5):**
- The renderer pins `base.validationCABundle` and `istiodRemote.injectionCABundle`
  to empty for both Istio charts, instead of relying on chart defaults. It stops if
  any of the three Istio webhooks would carry a `caBundle`.
- The validator independently requires, for each of the three webhooks:
  - the exact reviewed webhook entries;
  - a `clientConfig` with only `service`, pointing at `istiod-<project>-v1` in
    `istio-system`, so no `caBundle` and no URL;
  - and, for the controller webhooks, exactly one entry each with the public CA.
- Bundle impact: the three webhooks are byte-identical to contract 4. The only
  changed object is istiod's own Helm values record, `values-<project>-v1`, which now
  lists the two pinned empty values. The 9 stages and 62 objects are unchanged.
- Evidence moves to `runtime_contract_version` 5. Contract-4 evidence is refused by
  `check_runtime.py` and by `k8s_runtime.py plan`.
- There is still no `apply`. The phases above remain the contract for 6c-B3b; no
  path forces or overwrites a `caBundle`.
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

**Implemented (Owner decision D19/G9, 2026-11-24), Source/Offline only**, as the
recommended independent pull request: `scripts/local-workflow/k8s_certs_receipt.py`
(see the [script description](../scripts/local-workflow/README.md#registration-uid-receipt-and-safe-secret-cleanup-g9-d19-fake-only)).
- **Registration UID receipt.** A dedicated store
  (`~/.local/state/<project>-k8s-certs/<fingerprint id>/registration.json`), with the
  same file safety as the runtime receipt: outside the repository, 0700 and 0600,
  owner check, symlink refusal, exclusive lock, validated atomic replace. Schema
  `k8s-certs-registration-receipt-v1`: project, D17 fingerprint, the four
  identities, the UID at registration and the result.
  - Before any apply, all four Secrets are read (metadata only) and compared with
    the receipt: a Secret without a live claim must be absent, a claimed one present
    with the claimed UID and ownership. An unknown Secret, a UID difference, a
    missing claimed Secret or an unreadable read refuses the registration before the
    apply step runs (review of PR #99: no adoption of unknown Secrets).
  - The apply step gets a conditional plan (create if absent, update only the
    claimed UID) and returns the identity and UID it wrote; a UID is recorded only
    when the later metadata read shows that same UID, both labels and a single
    `<project>-k8s-certs` Apply entry owning exactly the registered fields. The
    condition is atomic in the fake and NOT_VERIFIED on a real API server.
  - Anything less is NOT_VERIFIED with no UID and the result INCOMPLETE, never
    success; a failed save is never success. A receipt is never rebuilt from names
    or current UIDs and never drops a UID that may still name a live Secret.
- **Cleanup.** The ten steps of the Owner decision: receipt, project, fingerprint and
  identity; metadata GET; both labels; the Apply entry; no other manager, operation
  or field; the receipt UID; DELETE with `preconditions.uid` (DELETE_REQUESTED
  recorded first); NotFound confirmed; the result recorded (DELETED, ALREADY_ABSENT
  or BLOCKED with a fixed reason). A 200 or 202 alone, a 409, 403, 5xx, timeout, a
  full or annotated Secret response, a Secret still present or recreated, and every
  failed check are BLOCKED. There is no full Secret read, no retry, no name-only
  delete and no namespace fallback.
- **The old delete.** `k8s_certs.py delete` refuses on every path
  (`name_based_delete_retired`) after the unchanged automation refusal.
- **Not changed.** The real `register` (no receipt, no read-back), the runtime
  receipt's Secret refusal, the real transport (not implemented) and namespace
  deletion (not implemented, D18 below).
- **Still NOT_TESTED or NOT_VERIFIED.** Any real Secret read or delete; whether a
  real server-side apply can be made conditional (create only if absent, update only
  a given UID) without a race; the exact
  managedFields a server-side applied Secret carries (the Apply entry's field set
  is assumed to be the labels, `type` and the data keys, so a different real shape
  fails closed); whether a 202 leaves a Secret present for a while (BLOCKED now;
  waiting would need a new timeout, D11).

| Option | Advantages | Disadvantages |
| --- | --- | --- |
| Inside 6c-B4 | One pull request for all destroy behaviour | Mixes Secret handling with the stage destroy engine; a larger security review |
| **Independent pull request before 6c-B4 (recommended)** | Small, security-focused review of a different script; `register` can gain its UID receipt in the same change; 6c-B4 then depends on a merged, reviewed cleanup | One more pull request |

### D19: DELETE with a UID precondition

`DeleteOptions.preconditions.uid` closes the window between the ownership check
and the deletion. `kubectl delete` is not known to accept preconditions (NOT_VERIFIED,
believed unsupported). **No DELETE is enabled until the Owner decides the method.**

**Decided (Owner, 2026-11-24), for the G9 Source/Offline implementation only:** the
limited direct API's Fake contract gains the metadata-only GET and the
UID-precondition DELETE of the four `k8s_certs.py` Secret identities (`v1` `Secret`
in `istio-system`, `kube-system` and `<project>-ingress`, by name). No arbitrary
path, resource, namespace or verb is added. The real HTTPS client, TLS, token
retrieval and any real request stay unimplemented (`real_transport_not_implemented`).
Metadata LIST, discovery and the section 5.1 inventory stay OPEN (D3 and D19,
before 6c-B4).

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
   - Requires renderer contract 5 (C1, implemented in 6c-B3b-C1); any bundle that claims an Istio webhook `caBundle` is refused.
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
   - Every condition belongs to one stage and one lifecycle point (section 4.1):
     pre-apply, minimal completion, deferred readiness or final acceptance.
   - There is no global "verify everything first" gate, because it cannot
     bootstrap.
   - A NOT_VERIFIED condition stops the run at its point (section 1). It is never
     treated as met.
7. **Exit codes.**

   | Code | Meaning |
   | --- | --- |
   | 0 | Every stage in the range reached final acceptance; no deferred item remains |
   | 6 | Applied, but deferred readiness remains for a stage outside the range. Not a PASS |
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
   - `deferred_readiness_unresolved`
   - `pre_apply_not_verified`
8. **No automatic rollback and no adoption.**
   - A rerun with `--from` re-verifies every earlier stage.
   - A bundle that differs from the applied one stops (D10).

Readiness by kind:

| Kind | Ready when |
| --- | --- |
| Namespace | Active, with the expected labels |
| CRD | Established and NamesAccepted |
| Webhook configurations | Object applied (minimal). **Serving** is separate and may be deferred (section 4.1). Serving means all of: the backing Deployment is ready; its Service has ready endpoints; the `caBundle` is populated and owned as in C1; and a probe classifies correctly. A CRD being Established says nothing about webhook serving |
| Deployment | Available, `observedGeneration` current, all Pods ready, digest checked (section 9) |
| Service | It has endpoints |
| RBAC | Present, with no diff |
| ValidatingAdmissionPolicy | Type checking has no warnings, its binding is `Deny`, and the probes classify correctly |
| TargetGroupBinding | BLOCKED (D1) |

### 4.1 Stage lifecycle and bootstrap

Each stage's conditions sit at five points:

1. **Pre-apply**: verified before the stage changes anything. A NOT_VERIFIED
   result stops the run (`pre_apply_not_verified`).
2. **Minimal completion**: checked right after the stage is applied. The next stage
   may start only after it passes.
3. **Deferred readiness**: cannot be true until a later stage has run. It is
   recorded in the journal as `DEFERRED` with its resolving stage, and checked
   when that stage completes. If it cannot be verified there, the run stops
   (`deferred_readiness_unresolved`).
4. **Final acceptance**: minimal completion, in-stage readiness and every deferred
   item verified. Only this counts as PASS for the stage.
5. **Stop on NOT_VERIFIED**: where the run stops, as listed in each row.

The 9 stages and 62 objects are unchanged.

`k8s_certs.py register` runs between the namespaces and base stages. It needs
`istio-system`, `kube-system` and `<project>-ingress` to exist. It is a manual
step outside the runtime command, and the runtime does not assume it happened.
The stages that consume a Secret check its presence in their own pre-apply
condition.

Abbreviations in the table:
- **Ownership**: the receipt UID plus only the allowed managers (section 10).
- **Secret presence**: metadata-only presence plus the `<project>-k8s-certs`
  manager and label. Its method is still open (D2), so until D2 is decided this
  condition is NOT_VERIFIED, and every stage that needs it stops before apply.
- **Digest**: classification per section 9.
- **Nodes**: Ready nodes in the selected zones (D3).
- **ECR**: the AWS read in D4.

| Stage | 1. Pre-apply | 2. Minimal completion | 3. Deferred readiness (resolved by) | 4. Final acceptance | 5. Stop on NOT_VERIFIED |
| --- | --- | --- | --- | --- | --- |
| namespaces (2) | • Gate, pinning, preflight, fingerprint<br>• Receipt reconciled<br>• Both namespaces absent, or present with ownership | Active; expected labels; UID recorded | None | Minimal completion plus ownership | Fingerprint or ownership: stop before apply |
| *(manual)* `k8s_certs.py register` | Namespaces minimal completion | Exit 0 of `register` (E3); nothing is assumed from it | — | — | — |
| base (16) | • Namespaces accepted<br>• CRDs absent, or present with ownership<br>• C1 implemented (no `caBundle` claim), else refused | • 15 CRDs Established and NamesAccepted<br>• `istiod-default-validator` applied with runtime-owned fields only (no `caBundle`) | **Validator serving** (resolved by istiod):<br>• `caBundle` populated and owned only by the allowed Istio manager<br>• istiod Service has endpoints<br>• probe F (Live, D20) | All CRD conditions plus validator serving verified | • CRD conditions unknown: stop before controller<br>• Validator serving not verified after istiod: stop before gateway and mesh_security. With `caBundle` empty and `failurePolicy: Fail`, every Istio resource write fails |
| controller (13) | • Base minimal completion (not its deferred items)<br>• Webhook TLS Secret presence in `kube-system`<br>• Bundle `caBundle` equals the input's public CA (plan)<br>• LBC index and amd64 digests in ECR<br>• Nodes | • 2 CRDs Established and NamesAccepted<br>• RBAC, ServiceAccount and IRSA annotation present<br>• Deployment applied | **LBC webhook serving** (resolved by admission): probe B reaches the policy, not `webhook_unreachable` (Live, D20).<br>**IRSA and AWS calls** (resolved by ingress): BLOCKED | • In-stage: Deployment Available, observed generation, Pods ready, Service endpoints, `MATCH_PLATFORM`<br>• Webhook `caBundle` owned only by the runtime<br>• Deferred items verified | • Secret, ECR or nodes: stop before apply<br>• Digest NOT_VERIFIED or Pods not ready: stop before istiod |
| istiod (12) | • Base minimal completion<br>• `cacerts` presence in `istio-system`<br>• istio-pilot digests in ECR<br>• Nodes | Objects applied with runtime-owned fields only (no `caBundle` on the validator or injector) | **CA in use** (resolved after this stage, Live): `istio-ca-root-cert` equals the local public root (D21).<br>**Injection** (resolved by gateway, or probe G) | • In-stage: Deployment Available, Pods ready, endpoints on 15017 and 15012, digest<br>• `caBundle` populated on the istiod validator and injector, and on the base validator (resolving base)<br>• Deferred items verified | • `caBundle` not populated within the timeout, or Pods not ready: stop before gateway and mesh_security |
| gateway (5) | • istiod in-stage readiness, including the injector `caBundle`<br>• Both gateway Secrets present in `<project>-ingress`<br>• istio-proxy digests in ECR | Deployment applied | **Gateway TLS serving** (resolved by ingress): BLOCKED, so NOT_VERIFIED | • In-stage: Deployment Available, Pods injected with the bundle proxy image, digest<br>• Deferred item verified, which is impossible while ingress is BLOCKED | • Injection missing or digest NOT_VERIFIED: stop before mesh_security<br>• Final acceptance stays NOT_VERIFIED while ingress is BLOCKED |
| mesh_security (5) | • Base validator serving resolved<br>• istiod in-stage readiness | `<project>-app` Active; Istio policies present with no diff | **Enforcement** (mTLS and authorization): needs traffic, NOT_TESTED | Present, no diff, ownership. Enforcement is recorded as NOT_TESTED, never PASS | Validator not serving: stop before apply |
| admission (4) | Controller minimal completion (the TargetGroupBinding CRD Established) | Policies type-checked without warnings; bindings `Deny` | **Probes A, A' and B** (Live, D20) | Probes classified exactly (section 11) | Probe class unexpected or unknown: stop before binding_writer |
| binding_writer (3) | Admission minimal completion | Present; no diff; ServiceAccount `automountServiceAccountToken: false` | **Effective permissions and impersonation** (D1, Live): NOT_TESTED | Not reachable until D1 | Never treated as PASS without D1 |
| ingress (2) | BLOCKED (D1, F21, D4) | — | — | — | Refused (`ingress_execution_gate_blocked`) |

**Run results.**
- A run whose range ends with DEFERRED items exits 6 (`APPLIED_WITH_DEFERRED`).
  That is not a PASS.
- The runtime as a whole has no final PASS today. While ingress is BLOCKED, none
  of these can reach final acceptance:
  - the controller (IRSA and AWS calls);
  - gateway TLS;
  - binding_writer;
  - ingress.

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
5. **Secret cleanup before namespace deletion** (G9 and the D19 Secret extension
   implemented Source/Offline on 2026-11-24; namespace deletion stays BLOCKED until
   6c-B4, the section 5.1 inventory and D6).

   | Namespace | Required before deletion |
   | --- | --- |
   | `istio-system` | • The receipt UID matches<br>• `cacerts` cleaned up and confirmed absent<br>• no Secret at all remains, including a self-signed `istio-ca-secret`<br>• only allowed leftovers remain |
   | `<project>-ingress` | • The receipt UID matches<br>• no TargetGroupBinding, and the finalizer is confirmed gone<br>• both gateway Secrets cleaned up and confirmed absent<br>• no other Secret, only allowed leftovers |
   | `<project>-app` | • The receipt UID matches<br>• it holds no k8s_certs Secret, and **any** Secret or any object outside the inventory stops destroy, because it protects future applications |
   | `kube-system` | Never deleted. The webhook TLS Secret is cleaned up explicitly and confirmed absent, as its own completion condition. Controller leases are reported, not deleted |

   "Only allowed leftovers remain" is decided by the inventory verification in
   section 5.1, never assumed. Its result must be COMPLETE. UNKNOWN or BLOCKED
   stops destroy before the namespace is deleted.

   D18 (Owner, 2026-11-24): a namespace that still holds a Secret is not deleted,
   and while the cleanup of its k8s_certs Secrets is incomplete its deletion is
   BLOCKED. Unknown Secrets are never deleted or adopted automatically. `kube-system`
   is never deleted; its webhook TLS Secret is its own completion condition. The G9
   cleanup report records this condition per namespace
   (`namespace_secret_condition`); namespace deletion itself is not implemented.
6. **CRDs are kept** (D5).
   - Runtime destroy is complete when all of these hold:
     - the 45 non-CRD objects are absent;
     - the four Secrets are absent;
     - every one of the 17 CRDs has zero custom resources, by the section 5.1
       CRD check with result COMPLETE;
     - the retained CRDs are listed.
   - The CRDs go with the EKS cluster.
   - Deleting any CRD (only with separate D5 approval) also requires a COMPLETE
     zero-count result for that CRD.
7. **Partial failure.**
   - Absent objects are confirmed by NotFound and UID before being skipped.
   - A rerun continues from the receipt.

### 5.1 Inventory verification for destroy (D3, D19)

Destroy must prove two negatives before it deletes a namespace or a CRD:
- nothing unknown is left in the namespace;
- no custom resource of a CRD exists.

A read that cannot prove the negative is never read as "none".

**Common rules.**
- **Transport.** Every list uses the limited direct API of D19 with
  `Accept: application/json;as=PartialObjectMetadataList;g=meta.k8s.io;v=v1`.
  - It returns object metadata only, for every kind, so no ConfigMap data and no
    Secret value is transferred.
  - kubectl cannot set that header, so these reads depend on the D19 transport and
    on the D3 read scope.
- **Secrets.**
  - Listed metadata-only like every other kind.
  - A response whose `kind` is not `PartialObjectMetadataList`, or that contains
    `data` or `stringData`, is discarded unprinted. The result is BLOCKED
    (`secret_metadata_only_unsupported`).
  - Reading full Secret objects is forbidden, and there is no fallback.
- **Expected response.**
  - HTTP 200 with `kind: PartialObjectMetadataList` and `apiVersion: meta.k8s.io/v1`.
  - Items carry `metadata.name`, `uid`, `ownerReferences`, `labels`,
    `managedFields` and `deletionTimestamp`.
  - Paging uses `limit=500` and `continue`; the list is complete only when the
    final page has no `continue` token.
- **Completeness.**

  | Response | Result |
  | --- | --- |
  | 403 | BLOCKED (`inventory_forbidden`) |
  | 404 for a listed resource | UNKNOWN |
  | 410 Gone while paging | Restart that list from the beginning, at most twice, then UNKNOWN |
  | Timeout, 5xx, or a response that is not a `PartialObjectMetadataList` | UNKNOWN |
  | Any failing API group in discovery | UNKNOWN for the whole namespace, because an unreadable group could hold objects |

- **Identity and permissions.** The operator's own identity, never impersonation.
  - Needed: `get` and `list` on the resources below, plus discovery.
  - Not needed: `watch`, and any write.
  - Whether the access policy grants these is NOT_VERIFIED until Live. A 403 is
    BLOCKED, never "empty".
- **No ownership inference.**
  - Only the 62 runtime objects, matched by receipt UID, are runtime-owned.
  - Everything else found is classified below, and is never adopted.
  - Destroy never deletes an object found only through this inventory.

**Namespace inventory.** Runs for `istio-system`, `<project>-ingress` and
`<project>-app` immediately before each namespace deletion.

1. **Discovery.** `GET /api` and `GET /apis`, then each group version's resource
   list.
   - Keep every resource with `namespaced: true` and the `list` verb, excluding
     subresources (names containing `/`).
   - A namespaced resource without `list` is UNKNOWN, unless it is in the fixed
     allowlist of virtual, non-persisted resources:
     - `bindings` (core);
     - `localsubjectaccessreviews.authorization.k8s.io`.
   - `events` (core) and `events.events.k8s.io` are the same objects; both are
     listed.
2. **List.** For each kept resource, `GET /api/v1/namespaces/<ns>/<resource>` or
   `GET /apis/<group>/<version>/namespaces/<ns>/<resource>`, using the preferred
   version.
3. **Classification of every item:**

   | Class | Rule | Effect |
   | --- | --- | --- |
   | `runtime_object` | One of the 62 objects whose UID equals the receipt UID | Must already be deleted by its stage; if present, stop |
   | `owned_child` | `ownerReferences` with `controller: true` chain to a receipt UID (ReplicaSet → Deployment, Pod → ReplicaSet, EndpointSlice → Service) | Must be gone or terminating within the D11 timeout after its owner was deleted; otherwise stop. Never deleted directly |
   | `allowed_leftover` | Exact allowlist: ServiceAccount `default`; ConfigMaps `kube-root-ca.crt` and `istio-ca-root-cert`; Events | Allowed |
   | `istiod_leftover` | istiod leader election Leases and ConfigMaps in `istio-system`, by exact name | Allowed only after the names are confirmed Live and added to the allowlist by review. Until then they are `unknown_object` |
   | `k8s_certs_secret` | One of the four Secrets | Must have been cleaned up first (G9). If present, stop |
   | `unknown_object` | Anything else, including any other Secret, in any namespace and especially in `<project>-app` | Stop |

4. **Result.**
   - COMPLETE (namespace may be deleted) only when discovery and every list are
     complete and every item is `allowed_leftover`, or a confirmed
     `istiod_leftover`.
   - Otherwise UNKNOWN, BLOCKED or `inventory_not_empty`. The namespace is not
     deleted.

**CRD custom-resource count.** Runs for each of the 17 CRDs before the run reports
completion, and before any CRD deletion that D5 may approve.

1. Read the CRD itself, one of the 62 objects, and check:
   - it is Established;
   - its UID matches the receipt;
   - its group, plural, scope and storage version.
2. List cluster-wide:
   `GET /apis/<group>/<storage version>/<plural>?limit=1`, metadata-only.
   - For a namespaced CRD this is the all-namespaces list. It is allowlisted only
     for these 17 plurals; the `status` allowlist keeps refusing
     `--all-namespaces`.
3. Expect HTTP 200, `items: []` and no `continue` token, which is a zero count.
   - Any item means `crd_instances_remain`, and the run stops.
   - 403 means BLOCKED.
   - 404, or a CRD that is not Established, means UNKNOWN, never zero.
   - The 15 Istio CRDs and the 2 controller CRDs are checked separately, and each
     needs its own COMPLETE result.

`kube-system` is never inventoried for deletion. Only the controller's runtime
objects (by receipt UID) and the webhook TLS Secret (metadata-only, G9) are read
there.

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
- The current read-only `status` (6c-B1) does **not** verify field ownership or
  drift. It lists both as unverified conditions, so they stay NOT_VERIFIED in its
  output.
- Drift verification is a future capability, planned for 6c-B3b and subject to
  D13. Only once it is implemented and reviewed may a command report DRIFT.
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
  - receipts, kept during operation per D22 and archived per the D22 archive part;
- a Billing check.

Deleting the EKS cluster alone is not complete teardown.

## 13. Owner Decision Matrix D1–D23

**Status.** "Needed by" is the latest point at which the Owner must decide.

- **Approved (Owner Decision Gate, 2026-11-22), for the 6c-B3a Source/Offline
  implementation only:**
  - **D7**: identity, UID, receipt and allowed field ownership together; never the
    manager name alone;
  - **D8**: no forced conflict resolution and no `--force-conflicts`;
  - **D10**: an unapproved change of manifest, input or version stops;
  - **D16**: no automatic quarantine release or adoption. A release needs a
    separate Owner approval naming the UID and the reason;
  - **D17**: the cluster ARN plus the `kube-system` namespace UID;
  - **D19**: the limited direct API as the design candidate. In 6c-B3a only its
    interface and fake exist; the real HTTPS client, token retrieval, and any real
    GET or DELETE need a separate Owner approval;
  - **D3**, in part: only the `kube-system` namespace read for the fingerprint.
- **Approved (Owner, 2026-11-22), for the 6c-B3b-C1 Source/Offline implementation
  only:** **D23**. istiod owns the `caBundle` of the three Istio webhooks, the
  runtime never claims it, the controller webhook keeps its public CA, there is no
  `--force-conflicts`, and the renderer moves to contract 5. istiod's field manager,
  real CA rotation and webhook serving stay NOT_VERIFIED.
- **Approved (Owner, 2026-11-22), for the 6c-B3b-Apply-A Source/Offline
  implementation only** (none of these is Live evidence):
  - **D2**: Secrets are metadata-only fakes. Their Live content, ownership and
    presence stay NOT_VERIFIED, and full Secret reads are forbidden.
  - **D3**: the apply read contract adds Pods, Nodes, EndpointSlices and the named
    ConfigMap, strictly limited by namespace and label, as design scope. There is
    no real cluster access. Destroy discovery and inventory reads stay unapproved.
  - **D9**: server-side dry-run and admission probe classification, against fakes
    only. Live use needs D20.
  - **D11**: API read 20 s, CRD established 120 s, Deployment ready 600 s, tested
    with a fake clock, with no unbounded retry. Any other timeout is presented
    before it is implemented. The 5 s CRD poll interval is a cadence inside
    the 120 s bound.
  - **D13**: the section 10 allowlist as a Source/Offline contract.
    - Unconfirmed manager names and field paths are not treated as confirmed.
    - An unknown manager, a foreign field or unclear ownership fails closed.
    - There is no `--force-conflicts`.
- **Approved (Owner, 2026-11-24), for the G9 Source/Offline implementation only:**
  - **D19**, Secret part: the Fake metadata-only GET and UID-precondition DELETE of
    the four `k8s_certs.py` Secret identities (section 3);
  - **D18**: no namespace deletion while a Secret remains; incomplete cleanup of the
    four Secrets blocks it; unknown Secrets are never deleted or adopted;
    `kube-system` is never deleted. Recorded as a contract, not implemented.
- **Approved (Owner, 2026-11-24), for 6c-B4. Only 6c-B4a is authorized for
  implementation; the 6c-B4b parts are approved as design:**
  - **D3**: Fake-only discovery and metadata-only LIST. Namespaces `istio-system`,
    `<project>-ingress` and `<project>-app` only; cluster-wide LIST only for the 17
    reviewed CRD plurals; no `kube-system` inventory for deletion; discovery grants no
    deletion. Every advertised group version is read, not only the preferred one; a
    missing group version, an unknown mapping or a namespaced resource without `list`
    (outside the virtual allowlist) is UNKNOWN; the same resource under several versions
    is merged by verified identity (UID with the same name and namespace).
  - **D5**: the 17 CRDs are kept; no CRD DELETE, `--delete-crds`, forced deletion or
    adoption of a foreign CRD. Option (b) of 6c-B4-PRE is **rejected**: a 200 on a LIST
    is never evidence of Established or the storage version. A specialised Fake CRD read
    of the 17 reviewed identities returns only the identity, UID, group, plural, scope,
    versions and Established, compared with the reviewed manifest. Instance count: a
    cluster-wide metadata LIST (`limit=1`) at the verified storage version: 200, no items,
    no continue is ZERO_INSTANCES; instances are BLOCKED; anything incomplete is UNKNOWN or
    BLOCKED. CRD_NOT_CREATED is a separate class, only with no creation evidence, no open
    INTENT, a trusted NotFound and a discovery that does not serve the plural; a claimed
    CRD that is missing or has another UID, and a foreign CRD, are BLOCKED.
  - **D6**: every namespace (including `<project>-app` from `mesh_security`) is deleted in
    a final namespace phase, only when its receipt identity, UID and ownership match, G9
    and D18 hold, the inventory is COMPLETE and only allowed leftovers remain (no unknown
    object, no terminating owned child). `kube-system` is never deleted. The renderer, the
    stage table and the 62 objects are unchanged. A namespace UID precondition does not
    make its contents immutable: an object or Secret added after the inventory is a
    6c-B4b failure path, and real-API cascade safety under races is NOT_VERIFIED.
  - **D11** (destroy): DELETE request 20 s, confirmation GET 20 s, TargetGroupBinding
    finalizer 600 s, owned children 600 s, namespace termination 600 s, polling every 5 s,
    LIST pages of 500, at most 100 pages per logical LIST (restarts included), at most two
    410 restarts, and a global 3600 s FakeClock deadline that no operation extends or
    resets; after it no new DELETE starts. A missing or empty continue on the last page
    ends the list; a repeated non-empty or malformed token, the page limit or a snapshot
    change is UNKNOWN; a 410 discards the partial list.
  - **D12**: the section 12 teardown order; dependency safety wins over plain reverse
    order (nothing the TargetGroupBinding needs goes before it is confirmed gone; policy
    bindings before policies; Istio webhooks only after no Istio custom resource remains;
    webhook configurations before their Deployments; namespaces last). An unknown Service
    in `<project>-ingress` is BLOCKED; for a runtime Service a specialised Fake read checks
    `spec.type` directly (never inferred from metadata). Ordering and the runbook are
    6c-B4b.
  - **D19** (remaining): Fake discovery, PartialObjectMetadataList, namespace and CRD
    instance LIST, runtime UID-precondition DELETE, finalizer and deletionTimestamp reads,
    the D5 and D12 specialised reads, strict validation, bounded pagination and fake error
    injection, with separate scopes (see section 15 note and the script description).
  - Receipt and journal: additive destroy records under FORMAT 1 (DESTROY_BEGIN,
    DESTROY_INTENT, DESTROY_RESULT, DESTROY_STAGE_DONE), with the phase, write-ahead,
    crash-recovery and backward-compatibility conditions of the Owner decision.
- **Every other row is OPEN (not decided).** That includes every Category 2 and 3
  decision.

### Category 1: before Source/Offline implementation

| ID | Decision | Recommended (proposal) | Risk | Affects | Needed by |
| --- | --- | --- | --- | --- | --- |
| D7 | Ownership evidence | Receipt UID plus identity plus the section 10 allowlist; never the manager name alone | A lost receipt blocks destroy (by design) | 6c-B3a, 6c-B4 | Before 6c-B3a starts |
| D8 | Server-side apply conflicts | Never `--force-conflicts`; stop | A stop on legitimate co-ownership | 6c-B3a | Before 6c-B3a starts |
| D10 | Applying a different bundle version | Stop on any difference | Upgrades need a later design | 6c-B3a | Before 6c-B3a starts |
| D16 | Releasing QUARANTINED objects | Strict: an explicit Owner action with the expected UID only | Manual work after a crash | 6c-B3a | Before 6c-B3a starts |
| D17 | Cluster fingerprint | `kube-system` namespace UID plus the cluster ARN | Needs a small read-scope addition (D3) | 6c-B3a | Before 6c-B3a starts |
| D19 | Transport for DELETE with a UID precondition and for metadata-only reads (Secrets, section 5.1 inventory) | Limited direct API (section 3) | Own TLS and HTTP code to review | 6c-B3a (design of the transport boundary), G9, 6c-B4 | Before 6c-B3a starts (method); DELETE and the inventory reads stay disabled until implemented |
| D23 | Istio `caBundle` ownership (C1) | **APPROVED 2026-11-22 for Source/Offline; implemented in 6c-B3b-C1 (contract 5).** The three Istio webhooks carry no `caBundle` (istiod owns it); the controller webhook keeps the public CA; no `--force-conflicts` | A renderer contract change | 6c-B3b-C1 | Done (Live behaviour NOT_VERIFIED) |
| D3 | Read-scope expansion. Apply: Pods, Nodes, EndpointSlices, the `istio-ca-root-cert` ConfigMap and the `kube-system` namespace. Destroy (section 5.1): discovery, metadata-only lists of every listable namespaced resource in the three runtime namespaces (Secrets metadata-only, never full objects), and cluster-wide metadata-only lists of the 17 CRD plurals | Apply reads limited to fixed namespaces and labels. Destroy reads metadata-only, limited to those three namespaces and 17 plurals; incomplete results are UNKNOWN or BLOCKED | A wider read surface; future application metadata in `<project>-app` becomes visible (names only) | 6c-B3a (fingerprint), 6c-B3b, 6c-B4 | Before 6c-B3a starts (fingerprint part); before 6c-B3b (apply reads); before 6c-B4 (destroy inventory) |
| D2 | Secret verification method | Not in 6c-B3b: report NOT_VERIFIED, which fails closed for operational apply; never read full Secrets | Operational apply stays blocked until a method is proven | 6c-B3b, G9 | Before 6c-B3b starts |
| D13 | Allowed secondary managers | Section 10 table | False stops until Live names are confirmed | 6c-B3b | Before 6c-B3b starts |
| D9 | Dry-run and probe design | Implemented and tested against fakes only; Live use is D20 | Audit-log entries once used Live | 6c-B3b | Before 6c-B3b starts |
| D11 | Timeouts | Per-stage limits (for example CRD 2 min, Deployment 10 min, finalizer 10 min) | Too short gives false stops | 6c-B3b, 6c-B4 | Before 6c-B3b starts |
| D5 | CRD deletion | Keep; deletion only with separate approval | CRDs remain until platform destroy | 6c-B4 | Before 6c-B4 starts |
| D6 | Namespace deletion conditions | Section 5 | Wrongly deleting future application data if loosened | 6c-B4 | Before 6c-B4 starts |
| D18 | Deleting a namespace that still holds a Secret | **APPROVED 2026-11-24 as a contract**: not allowed; blocked while the k8s_certs Secret cleanup is incomplete; `kube-system` never deleted | Cascade deletion of unmanaged Secrets | G9, 6c-B4 | Decided |
| D12 | Runbook teardown order | Section 12 | Unobserved deregistration if skipped | 6c-B4 (runbook) | Before 6c-B4 starts |

### Category 2: before Live verification

| ID | Decision | Recommended (proposal) | Risk | Affects | Needed by |
| --- | --- | --- | --- | --- | --- |
| D1 | Binding-writer method | A, after the section 7 checks | Section 7 | Ingress enablement, Live plan | Before any Live verification of ingress |
| D4 | AWS read APIs (ECR, ELBv2 target health, CloudWatch Logs, teardown checks) | Read only, around apply and destroy | Real AWS calls | Live verification | Before Live verification |
| D15 | Controller IAM sufficiency | Verify Live; any gap in a separate Terraform pull request | Reconcile failure | Live, a possible Terraform pull request | Before Live verification |
| D20 | Running server-side dry-run and probes against the real cluster | Inside the approved Live scope only | Audit-log entries; webhook-side AWS reads | Live verification | Before Live verification |
| D21 | Adding the public Istio root to the input provenance | Add (input contract change) | A contract change | A later input pull request | Before Live verification of `cacerts` |
| D22 | Operational receipt and journal policy: protection, retention while the runtime exists, and recovery when lost | Protection: the section 6 local store only (0700 and 0600, outside the repository, never uploaded to CI, GitHub or a ticket); an optional operator-held copy is encrypted and outside the repository. Retention: from the first apply until complete teardown is verified. Loss: never reconstructed from the cluster or adopted; destroy stops (`receipt_missing`); recovery is the platform destroy or an Owner-approved procedure | Loss blocks destroy (by design); a leaked receipt exposes identities and UIDs, never secrets | 6c-B3a (store), 6c-B4, Live | Before the first Live apply |

### Category 3: can wait for later features

| ID | Decision | Recommended (proposal) | Risk | Affects | Needed by |
| --- | --- | --- | --- | --- | --- |
| D14 | Apply only the Gateway resource of the ingress stage early | No; ingress stays BLOCKED as a whole | A partial state | Ingress | When ingress is enabled |
| D22 (archive part only) | What happens to the receipt and journal after complete teardown is verified | Archive locally outside the repository, or delete with a recorded reason | Lost historical evidence | Teardown records | After the first verified teardown |

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
| 6c-B3b | `apply` for stages 1–8, ingress refused, plus C1 (renderer contract 5), the section 4.1 lifecycle (pre-apply, minimal completion, deferred readiness, final acceptance), ownership table, digest classification, probe classification against fakes, and the read scope | Fake tests (negative and mutation) for:<br>• conflict<br>• foreign field<br>• C1 refusal<br>• digest mismatch or NOT_VERIFIED<br>• probe misclassification<br>• timeout<br>• `dry_run_unsupported`<br>• ingress refusal<br>• NOT_VERIFIED preconditions failing closed at their lifecycle point<br>• deferred items never reported as PASS (exit 6)<br>Plan tests pin contract 5. It is Source/Offline PASS only, never "Live deploy ready" | Enabling ingress; impersonation or TokenRequest code; reading full Secrets |
| G9 (independent, recommended; **implemented Source/Offline 2026-11-24** in `k8s_certs_receipt.py`) | Safe Secret cleanup and the registration UID receipt, using the D19 transport | Fake-API tests for:<br>• UID mismatch<br>• foreign manager<br>• missing label<br>• absence after delete<br>• no full Secret read<br>• no fallback | Namespace deletion stays BLOCKED until merged |
| 6c-B4a (**implemented Source/Offline 2026-11-24**, pending review; review of PR #100 addressed: policy authorisation at the send boundary, discovery-bound LISTs with complete target coverage, one global deadline and per-request timeouts on every request, strict metadata and cross-version consistency, sealed CRD verification evidence; second review: CRD verification bound to a separate receipt CRD map and invalidated by every new read, required core resources in discovery, the global deadline checked independently of the request timeout, one UID per logical identity across versions) | Destroy transport scopes, discovery, metadata LIST and bounded pagination, the specialised CRD and Service reads, runtime DELETE guards, the D11 constants and deadline, the receipt/journal destroy phase and the apply phase guard. No destroy engine | Contract tests (positive, negative, mutation, regression) | Any need for a full Secret read, a D13 relaxation, a G9 change, workflow or CI map changes |
| 6c-B4b | `destroy`: reverse order, UID preconditions, finalizer wait, namespace and Secret conditions, the section 5.1 inventory verification, kept CRDs, runbook §7 | Fake tests (negative and mutation) for:<br>• UID mismatch<br>• missing receipt<br>• leftover Secret or object<br>• finalizer timeout<br>• forbidden force options<br>• `kube-system` never deleted<br>• inventory reads that are incomplete, forbidden, paged with a stale continue token, missing a discovery group, or answered with a full Secret, each UNKNOWN or BLOCKED and never empty<br>• unknown objects never adopted<br>• a non-zero or unknown CRD count | Without a merged D19 transport and G9 cleanup, deletion is not enabled; namespaces with Secrets only with D18 approval |
| 6c-B5 | Source/offline closure audit of item 6c | Docs; lists every NOT_TESTED, BLOCKED and NOT_VERIFIED item | No COMPLETE declaration |
| Live verification (separate) | Sections 7, 8, 9 and 11, F18, F21, D15 | Outside the current scope (Master Policy v14.5 §15); not part of the remaining work | Never in Codex Cloud; no current authorization |

6c-B3b may be split if it grows: namespaces, base, controller and istiod first;
gateway, mesh_security, admission and binding_writer second.

## 15. Remaining BLOCKED, NOT_VERIFIED and NOT_TESTED

- **BLOCKED:**
  - ingress (D1);
  - `apply` and `destroy` (not implemented);
  - real DELETE: only the Fake UID-precondition DELETE of the four Secrets exists
    (D19, 2026-11-24); the real transport is not implemented;
  - namespace deletion: G9 is implemented offline, but deletion needs 6c-B4, the
    section 5.1 inventory and D6, and never happens while a Secret remains (D18);
  - operational apply while any mandatory precondition is NOT_VERIFIED;
  - namespace and CRD deletion until the section 5.1 inventory returns COMPLETE;
  - final acceptance of the runtime as a whole while ingress is BLOCKED.
- **NOT_VERIFIED:**
  - the AWS documentation statement on impersonation (could not be read in this
    session);
  - whether the access policy grants `impersonate`;
  - the service account's effective permissions;
  - a metadata-only Secret read and whether kubectl can do it;
  - the managedFields a server-side applied Secret really carries (the G9 checks
    assume one `<project>-k8s-certs` Apply entry owning the labels, `type` and data
    keys);
  - whether a Secret DELETE answered 202 leaves the Secret present for a while;
  - UID-precondition DELETE through kubectl;
  - `metadata.uid` as an apply precondition;
  - istiod and controller manager names and paths;
  - side effects of webhooks outside the bundle;
  - which digest `imageID` reports;
  - the access policy granting the destroy inventory reads, discovery completeness
    on EKS, and the exact istiod leader-election object names;
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
