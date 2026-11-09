# Portfolio verification policy — Definition of Done

## Evidence states and completion boundary

AWS Terraform is the primary portfolio. Architecture v2 is a
[defined target](architecture-v2.md), not proof that future components are deployed.
Use these labels per component/environment, with source revision and evidence links:

| State | Required evidence | What it does not prove |
| --- | --- | --- |
| Implemented and tested offline | Existing source plus successful mock/static/security/CI evidence | Account ownership, effective AWS authorization or deployed service behavior |
| Implemented and tested on DEV AWS | Separately authorized external execution, actual plan/apply and recorded scenario outcomes | STG/PROD deployment or untested availability, scale or recovery |
| Defined but not deployed | Documented architecture/environment contracts | Source implementation or a passed test |
| Proposed or awaiting approval | Explicit decision and missing approvals/evidence | Authorized implementation, deployment or acceptance |

Current nine-module/seven-instance/17-resource MVP is implemented and tested
offline; no component is claimed tested on DEV AWS. REST/Cognito/EKS/database and
new delivery components are defined or proposed. STG/PROD implementations and all
v2 live evidence remain future work. Historical
[acceptance](offline-mvp-acceptance.md) is not v2 operational acceptance.

Portfolio completion requires implemented, reviewed environment configurations
and the offline checks below for **DEV, STG and PROD**, plus the limited DEV live
evidence below after separate approval. STG/PROD definitions alone are not
implemented/tested configurations; record outstanding work honestly.

## All three environments — offline gate

For each implemented environment root and module change, require:

- Terraform initialization and configuration validation using reviewed versions
  and dependency locks, with backend-disabled credential-free execution as appropriate.
- Mocked plan/resource-contract verification with actual module implementations,
  explicit resource inventories and cross-module identity/dependency/output bindings.
- Proportionate positive cases and negative/input-boundary tests. Intentional
  rejection is negative evidence, not a successfully planned resource configuration.
- Security mutations proving changed unsafe behavior is rejected; malformed,
  missing, skipped, failed and incomplete evidence must fail closed.
- IAM trust, permission boundary and effective planned scope inspection; scoped
  PassRole, OIDC conditions and separation of human/deployment/workload/client roles.
  Static policies do not prove actual effective AWS authorization.
- Secrets/state-exposure checks, including Google federation, application/database
  and telemetry/notification secrets; sensitive marking alone is insufficient.
- Network exposure checks across WAF/origin, API authorization/scopes, private
  integrations/ALB/EKS/database, SSM access and intended egress boundaries.
- Provider/account/Region restrictions and env/Region/service state separation;
  root-owned providers/backends, exclusive resource ownership and lifecycle guards.
- Retention, deletion protection, artifact/image immutability, rollback ownership
  and state-recovery contracts; no destructive behavior inferred safe from mocks.
- Full existing GitHub Actions offline regression, including Terraform, Python,
  IAM reference/equivalence/negative checks, mutations and independent guardrails.

New modules require proportionate positive, negative, mutation and security tests
for their actual behavior; do not merely copy old counters or mirrored assertions.
Extend environment-specific checks for DEV capacity and STG/PROD AZ distribution,
NAT routing, database/replica topology and security differences. Unexecuted checks
remain OPEN; mocks cannot test live failover, service propagation or credential use.

### Historical floor and local/CI responsibilities

Preserve the recorded **384 Terraform native tests and 153 Python tests** from
the [offline acceptance evidence](offline-mvp-acceptance.md). These are historical
baseline results, not an upper limit or an assertion that new v2 coverage exists.
Root 12 rejected inputs, 35 mutations and 22 evidence injections, and HTTP API 17
mutations/19 evidence failures remain separate categories. Do not remove, disable,
skip or weaken existing CI security checks for efficiency or migration. Keep the
historical HTTP API tests valid until explicit replacement/extension is reviewed;
Cognito/REST tests must establish their own contract.

Codex Cloud performs implementation, affected local validation/security checks
and PR creation. Full regression belongs to GitHub Actions. Independent reviewers
verify completed PR CI and authorize merge. Do not rerun unrelated successful
local suites, repeatedly analyze successful logs or poll/wait for CI completion.
Documentation-only changes use consistency/link/scope/secret/diff checks; this PR
adds no infrastructure tests and changes no workflow. CI success for a previous
revision is not a claim that this PR's CI passed.

## DEV only — required future live evidence

All entries below are currently **OPEN**. Only a later separately approved external
workflow may use AWS authentication, live Terraform plans/apply or deployment.
Codex Cloud remains prohibited from requesting/using AWS credentials, authenticated
AWS APIs/plans, state imports/manipulation, apply, destroy or deployments.
Approval requires account/state/artifact ownership, deployment IAM, cost/stop
conditions and recovery/teardown decisions; DEV testing is not authorized here.
Never use the Organizations Management Account for workload/destructive testing.

| Required DEV evidence | Acceptance record and minimum verification |
| --- | --- |
| Authenticated Terraform plan and apply | Exact revision, approved account/Region/provider/state scope, reviewed complete plan, approved execution and actual outcome; explain partial failures or unexpected changes |
| CloudFront → REST API → Lambda | Actual controlled requests reach correct function via intended domain; correlate redacted request IDs and logs; identify direct-origin bypass status |
| REST API → VPC Link V2 → internal ALB → EKS | Actual private routing/health to intended workload and release; verify scope/targets rather than accepting a generic HTTP success |
| EKS → RDS PostgreSQL | Basic authorized DB connectivity for intended workload and approved credentials; no plaintext evidence; not a backup/failover/load test |
| Protected route token behavior | Minimum valid access-token/scoped-method acceptance and missing-token rejection; relevant wrong-scope, wrong-owner and invalid/expired-token negatives follow changed security contracts; never log actual tokens |
| GitHub Actions Lambda build/deploy/rollback | Approved source/build provenance, exact artifact/version and alias targets, successful health check and actual rollback verification; Terraform/release ownership reconciled |
| GitHub Actions EKS build/deploy/rollback | Pipeline build/test and immutable ECR digest; authorized private CodeBuild release; reviewed Helm/equivalent mechanism, health verification and verified rollback to known release |
| Pipeline event notifications | Relevant build, deployment and rollback outcomes for both delivery paths correlated through EventBridge/notification Lambda; at least one approved DEV destination receives verified events, and delivery-failure handling is evidenced separately |

Required checks are proportionate integration evidence, not broad performance or
resilience certification. Record both successful and unsuccessful results; failed
attempts remain failures until a correction is separately evidenced. An executed
rollback is not a pass until workload health/release identity is checked. An
application rollback is not infrastructure recovery or database recovery.

Store redacted evidence with source/build revisions, timestamps, reviewer and
approval references, execution identity class, resource references, artifact
version/image digest, scenario, expected/actual result and failure follow-up.
Secrets, keys, credentials, tokens, sensitive payloads, state and unredacted plans
must not enter Git or public CI artifacts. Actual private account/resource details
belong in the approved evidence store; publish sanitized references only.

## STG and PROD — offline implementation, no live requirement

Portfolio completion requires the defined two-active-AZ architecture implemented
and verified offline, including two NATs, EC2 Managed Node Groups, at least two
AZ-distributed application replicas and Aurora PostgreSQL Provisioned writer/reader
placement across AZs. It requires **no AWS apply, authenticated AWS plan or live
failover, penetration, load, monitoring or recovery test** in STG/PROD. Label these
architectures “defined but not deployed” until implemented offline, and then
“implemented and tested offline”; never claim live test success.

A real production project would additionally need independently scoped security
and penetration testing, load/capacity/cost measurements, token/ownership abuse
cases, alert routing and observability validation, AZ/node/DB failover and drain
checks, backup restore/database recovery drills, release/schema rollback, state
recovery, incident response, access revocation and controlled teardown exercises.
Agree SLOs/RTO/RPO, data/privacy requirements and service quotas with owners and
measure them; none are guaranteed or passed by this portfolio's offline design.
Cross-region DR remains a separate scope decision, not an implied feature.

## Review and evidence handoff

Review source, environment differences, security ownership and actual evidence
before declaring a component complete. Preserve old results at their revisions;
link new evidence rather than rewriting historical acceptance. All missing design
approvals and live outcomes remain OPEN. Independent review and successful
completed CI are required for merge authorization, without automatic merging or
branch deletion. This documentation task ends after commit, push and PR creation;
no live execution or subsequent phase is authorized.
