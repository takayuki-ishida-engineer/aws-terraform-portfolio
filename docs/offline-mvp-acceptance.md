# Offline MVP acceptance audit

## Decision and scope

**OFFLINE MVP ACCEPTED WITH DOCUMENTED LIMITATIONS**

The reviewed source and successful baseline CI meet the defined offline serverless
API MVP criteria. No contradictory implementation evidence was found in this
bounded audit. This decision accepts configuration, mock-plan and static/security
verification only; it neither establishes deployed functionality nor authorizes
live validation. All external prerequisites remain open in the
[live-validation readiness assessment](dev-live-validation-readiness.md).

## Evidence provenance

- Audited main: `89755c30508b78527fd46fa18593d5d5b11150f1`.
- [Post-merge baseline CI 42527556115](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42527556115): completed/success, with head SHA matching audited main. Its actual logs were inspected once; no regression suites were rerun locally for this documentation task.
- [Integration PR #18](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/18) and [efficiency policy PR #19](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/19) provide change provenance; acceptance relies on the post-merge baseline source and execution evidence rather than PR approval alone.
- **Source inspection:** root configuration, provider/backend, child interfaces, resource declarations, outputs and CI workflow.
- **Native mock-plan evidence:** actual child implementations, synthetic computed identities, four complete positive 17-resource plans and one intentional account-validation rejection.
- **Independent checker evidence:** actual plan JSONL, exact wiring/policies, unsafe mutations and malformed/incomplete capture rejection. This is static planned configuration evidence, not deployed IAM or service verification.
- **Actions execution evidence:** successful jobs and recorded test/checker/storage results at the baseline above.
- **Live AWS evidence:** none. No authenticated account operations, deployment, operational requests or destructive tests were performed.

Paths below refer to files at the audited baseline. A future implementation change
requires reassessment; this report does not certify arbitrary later revisions.

## Architecture inventory

Nine reusable modules exist under `infra/modules/`. Six sources compose seven
workload instances below. The independent [`vpc`](../infra/modules/vpc/README.md),
[`iam_access`](../infra/modules/iam_access/README.md) (human Identity Center access),
and [`iam_account_policies`](../infra/modules/iam_account_policies/README.md)
(account-scoped managed policies) remain outside this workload root.

Every address below is relative to `module.<instance>`; each resource is named
`this`. Counts describe complete positive configurations, not resources deployed.

| Integrated instance | Module source | Exact relative managed-resource inventory | Count |
| --- | --- | --- | ---: |
| `artifact_bucket` | [`s3_artifact_bucket`](../infra/modules/s3_artifact_bucket/README.md) | `aws_s3_bucket.this`, `aws_s3_bucket_versioning.this`, `aws_s3_bucket_public_access_block.this`, `aws_s3_bucket_ownership_controls.this`, `aws_s3_bucket_server_side_encryption_configuration.this`, `aws_s3_bucket_policy.this` | 6 |
| `secret_metadata` | [`secrets_manager`](../infra/modules/secrets_manager/README.md) | `aws_secretsmanager_secret.this` | 1 |
| `lambda_logs` | [`cloudwatch_logs`](../infra/modules/cloudwatch_logs/README.md) | `aws_cloudwatch_log_group.this` | 1 |
| `api_access_logs` | [`cloudwatch_logs`](../infra/modules/cloudwatch_logs/README.md) | `aws_cloudwatch_log_group.this` | 1 |
| `lambda_execution_role` | [`lambda_execution_role`](../infra/modules/lambda_execution_role/README.md) | `aws_iam_role.this`, `aws_iam_role_policy.this` | 2 |
| `lambda_function` | [`lambda`](../infra/modules/lambda/README.md) | `aws_lambda_function.this` | 1 |
| `http_api` | [`api_gateway_http`](../infra/modules/api_gateway_http/README.md) | `aws_apigatewayv2_api.this`, `aws_apigatewayv2_integration.this`, `aws_apigatewayv2_route.this`, `aws_lambda_permission.this`, `aws_apigatewayv2_stage.this` | 5 |
| **Total** | **Six sources, seven instances** | **No AWS data sources** | **17** |

## Acceptance evidence matrix

`PASS — verified offline` means only the evidence named in that row is accepted.
`OPEN — requires external verification` identifies an unresolved live prerequisite.
`FAIL — evidence contradicts requirement` would block acceptance; none was found.
`NOT APPLICABLE` is reserved for requirements outside this workload, not unknowns.

| Acceptance criterion | Evidence source | Result | Limitation |
| --- | --- | --- | --- |
| Fixed dev/ca-central-1/serverless-api identity, account guard and local backend | [root main](../infra/services/dev/ca-central-1/serverless-api/main.tf), [provider](../infra/services/dev/ca-central-1/serverless-api/providers.tf), [backend](../infra/services/dev/ca-central-1/serverless-api/backend.tf); baseline init/validate | PASS — verified offline | Mock execution does not authenticate account ownership or exercise real account restrictions. |
| Seven instances, exactly 17 managed resources, no data sources or VPC integration | Root source, inventory above, baseline root checker | PASS — verified offline | Four complete mock plans; no live resource inventory. |
| Cross-module references and ownership | Root main, child outputs, root actual-plan checker | PASS — verified offline | Bucket output waits for security/versioning; logs feed role/Lambda/API separately; role policy precedes Lambda; actual function/invoke ARNs feed API. Ordering does not prove propagation. |
| Explicit immutable artifact and input validation | [variables](../infra/services/dev/ca-central-1/serverless-api/variables.tf), Lambda/S3 interfaces, root tests and rejected-input checker | PASS — verified offline | Explicit bucket/key/version/runtime/handler; 12 separately rejected missing/malformed inputs do not establish actual ZIP contents or availability. |
| S3 versioning/private access safeguards | [S3 resources](../infra/modules/s3_artifact_bucket/main.tf), outputs, actual root/module checks | PASS — verified offline | Enabled versioning, four public-access blocks, BucketOwnerEnforced, AES256, HTTPS Deny and force_destroy=false are planned; ownership/propagation/object access remain external. |
| Lambda execution-role least privilege | [role policy](../infra/modules/lambda_execution_role/policies.tf), actual root/module policy checks | PASS — verified offline | Lambda-only trust and exact application-log stream writes; no deployment identity, artifact grants, PassRole or ENI permissions. Effective AWS authorization remains external. |
| Secrets Manager metadata-only management | [secret resource](../infra/modules/secrets_manager/main.tf), root inventory/output review | PASS — verified offline | No secret versions/values/rotation/replicas; metadata does not initialize AWSCURRENT. |
| Default-disabled optional exact-secret access | [feature configuration](../infra/services/dev/ca-central-1/serverless-api/features.auto.tfvars), root bindings, role policy and enabled/disabled actual plans | PASS — verified offline | Off: null secret ARN, no secret/KMS grant or secret environment reference. On: actual exact ARN, GetSecretValue/DescribeSecret and SECRET_ARN only, no CMK grant. Runtime retrieval is untested. |
| Separate protected log groups | [logs resource](../infra/modules/cloudwatch_logs/main.tf), root plan bindings | PASS — verified offline | Two distinct groups, 30 days, STANDARD, deletion protection, skip_destroy=false, no explicit CMK; no delivery or teardown operation tested. |
| HTTP API AWS_IAM authorization | [API resources](../infra/modules/api_gateway_http/main.tf), root/API checkers | PASS — verified offline | Default route, payload 2.0, throttling 10/20 and metadata-only logs; endpoint is internet-reachable and needs separately authorized SigV4 clients. |
| Exact Lambda invocation permission | API resource and actual-plan checker | PASS — verified offline | Exact function and actual API execution ARN + /$default/$default; route/permission precede stage. Not deployed policy or invocation evidence. |
| Operational outputs contain references only | [root outputs](../infra/services/dev/ca-central-1/serverless-api/outputs.tf), actual output-binding checks | PASS — verified offline | Eight direct references; no secret values, credentials or environment maps. References do not prove availability. |
| Offline root tests | [native tests](../infra/services/dev/ca-central-1/serverless-api/tests/root_integration.tftest.hcl), baseline root step | PASS — verified offline | Five passing native runs: four positive plans plus intentional invalid-account rejection; synthetic identities, no account authentication. |
| Existing Terraform regressions | Baseline module validation logs and [workflow](../.github/workflows/terraform-offline-ci.yml) | PASS — verified offline | 379 module tests + 5 root tests = 384; prior successful execution, not new local execution or live proof. |
| Python verification toolkit | [toolkit](../scripts/aws-policy-validation/README.md), baseline toolkit step | PASS — verified offline | 153 tests and offline export/check/dry-run; authenticated validation not performed. |
| Security mutations and malformed evidence | [root checker](../infra/services/dev/ca-central-1/serverless-api/tests/check_root_integration.py), [input checker](../infra/services/dev/ca-central-1/serverless-api/tests/check_required_inputs.py), [API checker](../infra/modules/api_gateway_http/tests/check_api_gateway_configuration.py); baseline logs | PASS — verified offline | Root 35 mutations/22 capture faults and 12 input rejections; HTTP API 17 mutations/19 faults. Existing IAM references, negatives, equivalence and independent guardrails passed; not a universal security proof. |
| Credential-free CI controls | Workflow and successful baseline execution | PASS — verified offline | Read-only contents, pinned actions, mock tests, /dev/null credential/config files, metadata disabled, no OIDC deployment or artifact uploads; does not establish a deployment principal. |
| Shared provider cache and storage checks | Workflow measurement steps and baseline storage log | PASS — verified offline | Ten initialized configurations reference one locked AWS 6.72.0 binary; cache 805,965,824 bytes, combined no-follow allocation 806,211,584 bytes, final available 35,441,754,112 bytes. Run-specific measurements, not future capacity guarantees. |
| Live account, artifact, authorization, secrets, invocation and logging | No live evidence; readiness gates 1–7 | OPEN — requires external verification | Dedicated account, identity, state ownership, artifact bootstrap, real IAM/secret/client/logging/cost/teardown approvals all required. |
| VPC or human/account IAM integration into this workload | Root source and module inventory | NOT APPLICABLE | Independent modules are retained; their deployment/administrative prerequisites are not accepted by this workload audit. |

## Recorded regression provenance

The successful baseline logs report VPC 16, Secrets Manager 31, account policies
24, human access 39, Lambda 70, CloudWatch Logs 51, execution role 64, artifact
bucket 37 and HTTP API 47: **379 module tests**. Root adds **5**, giving **384**.
The toolkit reports **153** Python tests. Input rejections, mutations and capture
injections are separate evidence categories and are not added to native totals.
No new test requirement or count has been introduced by this report.

## Acceptance limits and handoff

The configuration preserves the reviewed offline ownership and security contracts.
A newly created empty bucket cannot supply its required existing versioned ZIP;
bootstrap/state reconciliation must be decided externally. Local state is not a
collaborative remote backend. Secret metadata is not an initialized secret.
Account ownership, real permissions, IAM propagation, artifact compatibility,
API availability, unauthorized-request rejection and both log deliveries remain
unverified. Readiness gates remain OPEN, regardless of offline acceptance.

No live AWS operations are authorized by this documentation. Independent review
must verify this documentation PR and its CI separately; Codex stops after PR
creation without waiting or polling for completion.
