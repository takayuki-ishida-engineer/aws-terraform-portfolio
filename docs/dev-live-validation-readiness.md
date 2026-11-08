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

Review the exact API actions/resources/conditions needed for creation, reads,
updates and any separately approved deletion of the 17 resources: S3 bucket
security/versioning/policy, secret metadata, two log groups, IAM role and inline
policy, Lambda, HTTP API/integration/route/stage and Lambda resource permission.
Include provider refresh/tagging needs and service-specific authorization checks;
this list is a permission-category assessment, not a sufficient deployable policy.

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

Define a future authorized test protocol with expected outcomes and redacted audit
evidence, not assumed results:

- Verify scoped client execute-api:Invoke and correct SigV4 service/Region signing.
  Confirm successful intended requests and rejection of unsigned, unauthorized,
  wrong-scope and otherwise invalid requests. AWS_IAM does not make the endpoint private.
- Verify actual HTTP API → Lambda invocation, payload 2.0 compatibility, handler
  behavior and the deployment artifact's compatibility. Offline tests execute no app.
- Inspect the deployed Lambda resource policy for the exact function, API and
  /$default/$default invocation scope, including no unexpected preexisting grants.
- Establish Lambda application log delivery using the actual protected group and
  stream-scoped role permissions. Establish API access-log delivery independently
  to its separate group with metadata-only fields and no sensitive payload/header logs.
- Review regional/service logging delivery requirements and the deployment
  principal's configuration rights, relevant CloudWatch Logs resource policies or
  service-linked-role requirements where applicable. A destination ARN alone is
  insufficient; verify the actual effective configuration and delivery evidence.
- Verify configured 30-day retention and deletion protection for both groups.
  Any destructive behavior check requires its own approval, safe resources and
  restoration plan; do not disable protections merely to complete a checklist.

Record actual status, redacted request/log correlation and resource scope only in
an authorized evidence store. No API, log delivery, propagation or deletion test
has been performed by this audit.

## Gate 7 — Cost and teardown

Review S3 storage/requests and retained versions, Secrets Manager, log ingestion
and retention, API Gateway and Lambda charges, plus any separately approved
services. No precise prices or charges are asserted without verified current
pricing and usage assumptions. Throttling 10/20 is not a hard budget cap; finite
retention does not cap ingestion and object versions can accumulate.

Assign cost ownership, approve a budget and billing-alert delivery and escalation,
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
| 1 — Account | Dedicated non-management account, ownership, Region and effective identity boundaries | Fixed root guard and synthetic tests only; no verified live account | OPEN | Workload account owner and security approver — unassigned |
| 2 — State | Custodian, storage/backups, concurrency, imports, recovery and exclusive ownership | Local backend/source contract; no operational state evidence | OPEN | State/operations owner — unassigned |
| 3 — Artifact | Select bootstrap approach, state reconciliation, integrity/upload identity, exact key/version and recovery | Required immutable reference; no approved ZIP/bucket/publication evidence | OPEN | Artifact owner and infrastructure reviewer — unassigned |
| 4 — IAM | Approve least-privilege deployment actions, scoped PassRole and artifact rights | Offline execution-role/API scopes; no deployment policy or effective authorization | OPEN | IAM/security approver — unassigned |
| 5 — Secrets/KMS | External initialization, AWSCURRENT/runtime retrieval and any separately proposed CMK design | Metadata-only root; secret reads off; no initialized value or runtime verification | OPEN | Secret/application owner and security approver — unassigned |
| 6 — API/logging | Approve SigV4, real invoke/deny tests, exact scope and separate delivery/retention checks | Mock/static contracts only; no live operational results | OPEN | Application/operations and security reviewers — unassigned |
| 7 — Cost/teardown | Budget, alerts, ownership, rollback, deletion/data handling, revocation and evidence retention | Documented module lifecycle settings; no budget or operational approval | OPEN | Cost owner and operations approver — unassigned |

**No live AWS operations are authorized by this documentation.**
