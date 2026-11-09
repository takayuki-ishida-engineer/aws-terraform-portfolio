# Development live-validation readiness
See the [bootstrap decision plan](dev-bootstrap-decision-plan.md) for conditional Gate 1–3 recommendations; all gates remain OPEN.

This is a planning and approval artifact, not an executable deployment procedure.
The [offline acceptance audit](offline-mvp-acceptance.md) accepts source/mock/static
contracts at main `89755c30508b78527fd46fa18593d5d5b11150f1`, using successful
[baseline CI](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42527556115).
It provides no live AWS evidence. All seven gates below are **OPEN**. Approval
owners are responsibilities to assign, not named people or assumed approvals.

**No live AWS operations are authorized by this documentation.**

A future live task requires separate explicit authorization in an approved
execution environment outside Codex Cloud. Never request/use AWS credentials,
run authenticated account APIs/plans, apply or destroy in Codex Cloud. No account,
principal, budget, artifact or operational success is assumed here.

## Architecture v2 alignment — approved policy, execution OPEN

Current operating policy is user-approved Master Policy v11 (2026-11-09).
Historical v10 (2026-11-08) and its approved security/cost clarifications are the
recorded provenance of the [design](architecture-v2.md) and
[verification contract](portfolio-verification-policy.md). The external v11 PDF is
unavailable here and not reproduced, revised or claimed independently reviewed in
full; no undocumented equivalence/content or Live approval is inferred.
Current post-R2 main df5ef4b2e03bd55109b0490b1e63d1d4199b663b passed
[CI 42618561148](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42618561148), 491/153.
That current result and the historical CI above remain offline-only HTTP API evidence,
not REST/NLB/Istio/mTLS tests or a complete future Live inventory. Existing gate
material below is retained and extended; all G01–G07 gates remain OPEN. Approval
of the limited Live policy does not approve any specific account, certificate,
plan, resource, execution estimate or scenario. No Live AWS operations occur here.

### G01–G05 extensions: trust, identity, ownership and secrets

- Keep dedicated non-management account/Region/identity checks, single-writer
  state and exclusive ownership, import/recovery and approved artifact bootstrap.
  Preserve root-owned providers/backends, DEV local state and separately reviewed
  STG/PROD remote state. User dummy.zip is a candidate only; verify digest/version/
  provenance/ownership before any approved bootstrap. Never reuse customer-project
  ZIP code/private information; no application/build implementation is added here.
- Distinguish human/deploy/upload/execution/API-client and Kubernetes ServiceAccount
  identities. Review IAM/OIDC/PassRole, RBAC/NetworkPolicy and egress. Terraform owns
  internal NLB/listeners/target groups/network/VPC Link; Kubernetes-side control owns
  Gateway Pod registration. TargetGroupBinding, Pod IP mode, health checks, controller
  rights and compatibility remain OPEN; no double ownership of a load balancer.
- Browser HTTPS and Cognito AWS-managed login domain use environment User Pools/
  Google federation, Authorization Code + PKCE S256 and OIDC. No browser client
  certificates or Cognito custom domain; *.cloudfront.net viewer domain is allowed.
- Origin mTLS needs a Regional REST custom domain and versioned S3 truststore in
  ca-central-1, with suitable clientAuth certificate in ACM us-east-1 for CloudFront.
  Prefer a free subdomain only after DNS control/renewal/validation/terms review;
  no FQDN/provider chosen or purchased, Route 53 not mandatory for every record.
  Incompatibility requires revised approval, not weakened TLS.
- Review client/server certificate issuance, EKU, truststore ownership, versioning,
  rotation/expiry and private-key handling. API stage ACM backend client certificate
  is preferred only after actual provider/integration support is verified; ordinary
  ACM public certificates must not be assumed suitable. No PKI is implemented.
- Actual Google/DB/telemetry secrets, keys and certificate private material stay out
  of Terraform inputs/data/plans/state/outputs and Git/CI artifacts. Metadata only
  remains Terraform-owned; external approved processes own values and rotation.
  Istio CA is initial candidate; roots/intermediates, short-lived SPIFFE certificates,
  ServiceAccount boundaries and revocation-equivalent handling remain review gates.

### Inbound mTLS identity / revocation feasibility — OPEN

[API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-mutual-tls.html)
validates supported client certificate properties, chain and validity but **does not
automatically check revocation**. A trusted CA may issue other valid certificates;
CA trust is not an allowlist for the expected CloudFront origin client certificate.
Review minimum trusted CA/issuance scope, expected-client identity, unauthorized
certificate denials, compromise response, rotation, expiration monitoring and
revocation-equivalent controls. Transport handshake validation, certificate identity
authorization, revocation and Cognito user authorization remain distinct.

Any additional certificate authorization must have an owner, failure behavior and
verification evidence compatible with Cognito User Pool Authorizer/OAuth scopes.
Do not assume a Lambda Authorizer can coexist alongside Cognito on the same REST
method. No revocation/identity mechanism is selected; feasibility, operational
responsibility and security boundaries remain OPEN in the relevant implementation PR.

### Approved DEV Live limits and cost feasibility — G07 OPEN

**Total actual cumulative DEV Live spending must remain within JPY 10,000 across
the approved validation period. All testing and verified complete teardown must
finish within 72 hours from approved Live start.** Prefer shorter runs. Old monthly
budget examples are not limits or sizing approvals. No operation is authorized here.

CloudFront Origin mTLS supports **Business, Premium and Pay-as-you-go**, not Free.
Before implementation or Live, verify the applicable plan/feature and current
fixed/usage charges, certificate lifecycle, all other services, Region/runtime,
tax/FX, retained charges, contingency and teardown implications. No plan is selected
or purchased. The 72-hour window is not a cost guarantee. If the validated estimate
cannot meet the cap including contingency/cleanup, do not authorize that scenario;
keep it OPEN or Offline-only. AWS Budgets/alerts are not real-time enforcement or
guaranteed cutoff. Assign monitoring, manual stop authority, inventory and timeline;
stop early enough to avoid exceeding the limit.

Prioritize feasible creation/inventory, positive/negative Istio STRICT mTLS and
REST VPC Link V2 → internal NLB TCP:443 → Istio Gateway backend certificate auth.
Delivery/rollback/events run only in remaining approved affordable scope. Do not
mandate a full simultaneous CloudFront/Cognito/RDS/delivery stack when infeasible.
All unexecuted cases stay OPEN or Offline-only, never passed; selected scenarios
must retain their security checks. All seven gates still require actual evidence.

Complete teardown requires actual deletion/removal verification of **all resources
created for the exercise**, including externally created/service-managed dependencies.
Inventory applicable EKS control planes/nodes, ENIs/EBS, NLB, NAT/EIPs/endpoints,
RDS/backups/snapshots, S3 versions, ECR images, logs, secrets, API/custom domains,
ACM, WAF, KMS, AMIs and related dependencies. Check deletion protection, delayed
deletion/recovery, retained data and external resources before approval. Avoid
new CMKs or other unavoidable delays incompatible with 72 hours. The unchanged
historical secret module's 30-day recovery blocks complete deletion within this
window if created for Live; resolve the applicable scenario/lifecycle first, not
by silently weakening protection or assuming terraform destroy is sufficient.

Start teardown early; independently reconcile actual AWS inventory, state and
external records before the deadline. Stopping EC2 or a successful destroy alone
is insufficient. Preserve approved redacted audit evidence outside AWS first;
never delete pre-existing shared resources. No exercise resources should remain
producing ongoing charges after cleanup; delayed historical usage billing and FX
can still produce later invoices, so no literal zero-subsequent-billing promise.

## Gate 1 — Dedicated workload account

Independently establish a dedicated non-management workload account, ownership,
intended use, actual authenticated identity, Region ca-central-1 and resource scope.
Identify the approved deployment principal and separate human operational,
deployment, workload execution and client identities. Review effective SCPs,
session policies, permission boundaries and organization restrictions where
applicable, including explicit denials and cross-account limitations.

Evidence needed: account owner's approval, verified identity/Region and a reviewed
access-boundary record through a separately authorized process. Do not record
credentials in repository evidence. A configured allowed_account_ids guard and
synthetic mock account do not prove real ownership or effective authorization.
Destructive testing in the AWS Organizations Management Account is prohibited.
A dedicated workload account has not been established by this audit.

## Gate 2 — Terraform state and resource ownership

The dev root retains a local backend. Assign one state custodian, secure encrypted
storage/access controls, backups, recovery tests and versioned audit evidence.
Local locking is limited to processes sharing the same state/storage; it does not
coordinate independent copies or CI runners. Require a single authorized writer,
external concurrency coordination and a reviewed handoff procedure. Local state
has limitations for collaboration, automation, availability and auditability.

Inventory existing resources before any future operation. Decide which require
import into the workload state and verify name/identity before importing. Two
states must never simultaneously claim the same bucket, role, log group or other
resource. Reconcile bootstrap ownership explicitly, retaining recovery snapshots
and evidence of each transfer. Plan state recovery and code rollback separately:
restoring a state backup does not roll back live resources, and secret/object
versions or partially completed operations require service-specific recovery.
No remote backend or state migration is implemented or approved here.

## Gate 3 — Artifact bootstrap

Lambda requires an approved existing ZIP and immutable non-null S3 object version.
An initially empty bucket cannot contain it. The integrated root is therefore not
a safe single-operation deployment from an empty account. No temporary feature
flag, unversioned artifact or dependency bypass may conceal this prerequisite.

Candidates requiring an explicit design decision:

| Candidate | Benefit | Trade-off and required decision |
| --- | --- | --- |
| Separately reviewed bucket-only bootstrap configuration, followed by ownership transfer/import into the integrated root | Clear provisioning boundary before external publication | Requires explicit state reconciliation, removal of old ownership and recovery checkpoints; never manage the bucket in two states |
| Import an independently approved, already provisioned compatible bucket into the workload state | Allows an existing approved artifact location | Must verify ownership and all six security/versioning resources, reconcile every resource identity and avoid conflicting creation; no existing suitable bucket is assumed |
| Separately reviewed staged execution against the integrated configuration | Can retain one eventual root/state boundary | Selective targeting can omit dependencies and is not a routine deployment strategy; needs explicit expert review and a later complete plan, not an implementation in this task |

No candidate is selected or authorized. Before selection, decide and record:

1. Who provisions the initial bucket and all security controls, and from which state.
2. How ownership, imports and state reconciliation avoid dual management.
3. How effective versioning and security are verified after propagation.
4. Who externally packages the approved ZIP, reviews runtime/handler/architecture
   compatibility and verifies integrity/provenance against an approved digest.
5. Which narrowly authorized identity uploads it; separate that identity from the
   Lambda execution role and deployment role where appropriate.
6. How exact S3 key, immutable non-null version and integrity evidence are captured
   securely outside committed private-account configuration.
7. How Lambda receives those approved references and a full plan is reviewed.
8. How partial provisioning/upload/import failures are recovered without data loss,
   duplicate ownership or accidental teardown; retain rollback artifact versions.

No packaging, upload, AWS lookup, provisioning, import or selective execution is
performed by this document. See the [root contract](../infra/services/dev/ca-central-1/serverless-api/README.md)
for required inputs and existing dependency ordering.

## Gate 4 — Deployment IAM

For the historical 17-resource MVP, review the exact API actions/resources/conditions needed for creation, reads,
updates and any separately approved deletion of the 17 resources: S3 bucket
security/versioning/policy, secret metadata, two log groups, IAM role and inline
policy, Lambda, HTTP API/integration/route/stage and Lambda resource permission.
Include provider refresh/tagging needs and service-specific authorization checks;
this list is a historical permission-category assessment, not a complete v2 inventory or sufficient deployable policy. Extend separately for REST/NLB/Istio, certificates, EKS, scaling and Scheduler/controller/watchdog roles.

Review scoped iam:PassRole for only the intended Lambda execution role and service,
artifact/version-read authorization for the deployment path, and distinct external
upload authorization. Do not substitute AdministratorAccess, unrestricted IAM or
unrestricted PassRole for a reviewed policy. Evaluate effective denials and
propagation using the Gate 1 boundary evidence.

Human IAM Identity Center access, workload execution-role log/optional-secret
rights, API Gateway's Lambda resource permission, and client execute-api:Invoke
are independent boundaries. Assigning a Permission Set in an ordinary member
account does not itself establish Identity Center administrative prerequisites.
No principal, policy, attachment or permission grant is created here.

## Gate 5 — Secrets and KMS

Use Secrets Manager approach A only: Terraform owns metadata; an approved external
identity initializes actual values. Values must never enter Terraform inputs,
configuration, plans, state or outputs, including through ephemeral/write-only
alternatives. Lambda application code must retrieve values at runtime using an
approved AWS SDK flow; such code is outside this task.

Verify initialization and AWSCURRENT externally without copying plaintext into
repository evidence. Review exact-secret resource authorization, actual runtime
retrieval and expected denial of unrelated secrets. Secret reading defaults off;
enabling it changes IAM and environment configuration and requires plan review.
The enabled root grants only GetSecretValue/DescribeSecret on the actual ARN and
passes SECRET_ARN; it grants no customer-managed KMS decrypt permission.

The current root selects no explicit CMK. Any future CMK change is a separate
review covering key ownership, key policy, grants, scoped identity permissions,
service/encryption-context conditions, rotation and recovery constraints. Do not
assume that an IAM statement alone makes a key usable. No values or runtime code
are added here.

## Gate 6 — API and logging

Historical HTTP API operational evidence remains absent: earlier ARN/scope/log
contracts are not proof of live invocation or delivery. Future v2 authorization
uses Cognito access tokens/method scopes; SigV4 remains appropriate for managed
AWS APIs/identities, not a replacement for the approved user model.

Before any scoped Live protocol, require expected/actual outcomes and redacted
request/certificate/workload correlation for applicable boundaries:

- Standard browser HTTPS; CloudFront origin mTLS; Regional custom domain and WAF;
  default execute-api bypass prevention, stage mappings/deployment and DNS/SNI.
- Chain/validity plus expected client identity; missing/invalid/untrusted/expired/
  unauthorized certificates, compromise/rotation/revocation-equivalent handling and
  Cognito coexistence evidence. No claim of automatic API revocation checking.
- API backend client certificate, Gateway server CA/hostname/SNI verification,
  NLB TCP passthrough and private target/health/controller boundaries. Reject wrong
  termination, insecureSkipVerification, unrestricted trust or plaintext fallback.
- Istio STRICT/SPIFFE/AuthorizationPolicy: positive traffic and denials for absent
  cert, wrong CA/SAN/identity/principal, plaintext and expiry; restrictive RBAC,
  NetworkPolicy and short-lived certificate lifecycle with reviewed failure handling.
- Valid scoped access tokens, missing/invalid/expired/wrong-scope and wrong-owner/
  cross-tenant denial; access tokens rather than ID-token substitution.
- Actual application and API log delivery, separate destinations, safe metadata,
  delivery permissions/service configuration, retention/protection and redaction.
  Mock destinations do not prove delivery. Review PostgreSQL CA/hostname TLS and
  approved DB auth if DB is in the approved scenario; no custom certificate mTLS
  imposed on standard RDS/browser/managed APIs/local same-Pod/control-plane links.

For relevant delivery scenarios, verify immutable digest/version, private CodeBuild
access, release health, actual rollback identity and EventBridge notification
success/failure with independent delivery-failure handling. Infrastructure, app and
DB recovery are distinct. Unexecuted or unaffordable cases remain OPEN/Offline-only.

The approved administration EC2 contract is America/Toronto weekday
START cron(0 8 ? * MON-FRI *) and STOP cron(0 19 ? * MON-FRI *), weekends stopped,
no holiday calendar, timezone-aware DST. Scheduler → SQS Command Queue → Controller
Lambda → EC2, with separate Watchdog, CloudWatch detection and SNS notification.
Review Scheduler failure/missing heartbeat, stale commands/retries/DLQ, Controller
errors/timeouts/idempotency, EC2 API/state/SSM readiness mismatch, unexpected running,
Watchdog and notification failures, including non-execution of either START/STOP.
Thresholds, redrive counts and permissions remain OPEN. Packer/Ansible provenance
and SSM-only/no-public-SSH/RDP access require review. This schedule does not replace
72-hour full teardown or stop EKS/NLB/NAT/RDS billing. No Live results are recorded.

## Gate 7 — Cost and teardown

The historical lifecycle considerations below do not authorize retention of
exercise-created AWS resources past the absolute Live teardown deadline.

Review S3 storage/requests and retained versions, Secrets Manager, log ingestion
and retention, API Gateway and Lambda charges, plus any separately approved
services. No precise prices or charges are asserted without verified current
pricing and usage assumptions. Throttling 10/20 is not a hard budget cap; finite
retention does not cap ingestion and object versions can accumulate.

Within the approved JPY 10,000 cumulative cap and 72-hour complete-teardown
limit, assign cost ownership and approve the scenario estimate, billing-alert
delivery and escalation,
and define a stop condition before live operations. Keep a verified resource and
state inventory. Approve rollback and controlled teardown ordering, coordinating
client access, API entry points/invoke permission, Lambda, IAM and retained data.
Revoke temporary deployment/upload/client access deliberately and confirm removal.

Review CloudWatch deletion protection before any approved change/deletion;
skip_destroy=false is not a bypass. Review the secret's 30-day recovery window
and name/recovery obligations. S3 force_destroy=false requires separately approved
version/delete-marker cleanup or retention before bucket deletion; it does not
prevent partial removal of other security resources. Plan partial-failure recovery,
retained artifact rollback versions, state backups and audit/log retention before
revoking access or destroying evidence. No cleanup or teardown is executed here.

## Approval and readiness matrix

All owners below must be designated and explicitly approve their decisions in a
future process. None of these role descriptions represents an approval.

| Gate | Required decision | Current evidence | Status | Approval owner |
| --- | --- | --- | --- | --- |
| G01 — Account | Dedicated non-management account, ownership, Region and effective identity boundaries | Fixed root guard and synthetic tests only; no verified live account | OPEN | Workload account owner and security approver — unassigned |
| G02 — State | Custodian, storage/backups, concurrency, imports, recovery and exclusive ownership | Local backend/source contract; no operational state evidence | OPEN | State/operations owner — unassigned |
| G03 — Artifact | Select bootstrap approach, state reconciliation, integrity/upload identity, exact key/version and recovery | Required immutable reference; no approved ZIP/bucket/publication evidence | OPEN | Artifact owner and infrastructure reviewer — unassigned |
| G04 — IAM | Approve least-privilege deployment/upload/workload roles, restricted trust, PassRole and effective resource permissions | Offline execution-role/API scopes; no deployment policy or effective authorization | OPEN | IAM/security approver — unassigned |
| G05 — Secrets/KMS | External values/runtime retrieval/rotation, encryption ownership and certificate/key handling; no incompatible deletion delays | Metadata-only root; secret reads off; no initialized value or runtime verification | OPEN | Secret/application owner and security approver — unassigned |
| G06 — API/logging | Approve scoped REST/origin/backend mTLS, Istio and Cognito positive/negative protocols, identity/revocation feasibility, log correlation/redaction | Mock/static contracts only; no live operational results | OPEN | Application/operations and security reviewers — unassigned |
| G07 — Cost/teardown | JPY 10,000 cumulative cap, 72-hour deadline, feasible plan/cert costs, complete inventory/cleanup/recovery and independent removal verification | Approved policy limits only; no validated scenario estimate, selected pricing plan or operational approval | OPEN | Cost owner and operations approver — unassigned |

**No live AWS operations are authorized by this documentation.**
