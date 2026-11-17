# Reusable HTTP API with dedicated access logging — R2

Own exactly six resources: aws_apigatewayv2_api.this, aws_apigatewayv2_integration.this,
aws_apigatewayv2_route.this, aws_apigatewayv2_stage.this, aws_lambda_permission.this
and aws_cloudwatch_log_group.this. No nested logging helper, providers, backends,
IAM roles, KMS resources, Lambda functions, REST API, authorizers, CORS, networking,
artifact publication or secret values. This is the historical AWS_IAM HTTP API,
independent of the future Architecture v2 REST/Cognito target.

R2 adopts the existing API access log source ownership; Lambda application logging
stays separately owned by lambda_workload. Generic cloudwatch_logs/51 tests remain
unchanged and independently tested, with no DEV root consumer. Its retirement needs
separate review. R3/R4 and new features are not implemented here.

## Inputs and effective configuration

Root Override is a supplied caller value, Module Default is an omitted optional
input's declared default, and Module Fixed is implementation without an override.

| Input | Source/default and validation |
| --- | --- |
| api_name | Required Root Override; 1–128 ASCII letters/digits/underscore/dot/hyphen, starting with letter/digit |
| lambda_function_arn | Required Root Override; actual unqualified aws/aws-us-gov function ARN ≤140 characters, explicit 12-digit account and reviewed canonical Region; GovCloud east/west only |
| lambda_invoke_arn | Required Root Override; actual invocation ARN for exactly that function/partition/Region, 2015-03-31/functions/.../invocations |
| access_log_group_name | Required Root Override; explicit 1–512 supported Logs name characters, no literal aws/ prefix, no random suffix |
| tags | Module Default {}; API/Stage tags only, ≤50 entries with existing API Unicode/key/value/non-null/reserved-prefix validation; effective provider-default merges retain original postconditions |
| access_log_retention_in_days | Module Default 30; Root Override accepts only finite supported values below |
| access_log_deletion_protection_enabled | Module Default true; explicit Root Override false is an intentional lifecycle decision |
| access_log_kms_key_arn | Module Default null; optional exact existing key ARN ≤256 characters, UUID or mrk identifier, no aliases/bare IDs/wildcards; retains generic Logs syntax validation |
| access_log_tags | Module Default {}; independent log caller tags, ≤50 entries, keys 1–128 and non-null values ≤256 characters; Unicode letters/separators/numbers and _.:/=+@-, no case-insensitive aws: prefix |

The removed access_log_group_arn input is neither retained nor ignored. No fabricated
actual ARN is used: Stage and log outputs read the owned provider resource. Its
postcondition verifies the exact bare ARN/name against Lambda partition/Region/account.
Actual API execution ARN retains its independent ID/scope postcondition. The root
must configure/restrict its provider account; these checks authenticate no account.

Finite retention days: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545,
731, 1096, 1827, 2192, 2557, 2922, 3288, 3653. Zero/indefinite, unsupported values,
fractions and negatives are rejected. Shortening retention may expire historical
events irreversibly; account policies and service expiry timing remain external.

KMS reference syntax retains the generic aws/aws-us-gov/aws-cn shapes, including
separate syntax-only GovCloud/China key cases. This does not expand the API's
reviewed aws/GovCloud workload scope or prove that a cross-Region/partition/account
key is usable. An authorized external owner must verify compatible key scope,
symmetric enabled key, regional Logs principal, key policy/encryption context,
caller permissions and continued historical-key access before real use. No key,
policy, grant or secret value is created; normal service encryption is requested
when null. Key rotation/disassociation does not re-encrypt historical events.

## Fixed HTTP API and security behavior

| Module Fixed setting | Effective contract |
| --- | --- |
| API/endpoint | HTTP, public execute-api endpoint enabled; no CORS or quick-create body/target |
| Integration | AWS_PROXY / POST / payload 2.0 / INTERNET, actual lambda_invoke_arn, no execution role or transformations |
| Route | $default, AWS_IAM, actual integration target; no anonymous/alternate authorization |
| Stage | $default, auto_deploy=true, rate=10 and burst=20, no payload tracing/route overrides |
| Lambda permission | apigateway.amazonaws.com / lambda:InvokeFunction, exact actual unqualified function; API-ID-derived statement ID |
| Invoke source | "${aws_apigatewayv2_api.this.execution_arn}/$default/$default"; no wildcard broadening |
| Log storage | STANDARD, skip_destroy=false, owned explicit name and actual bare ARN |
| Stage log destination | aws_cloudwatch_log_group.this.arn, expressing an effective graph dependency |
| Readiness | Stage explicitly waits for Route and Invoke Permission; Route references Integration; original three API outputs retain Stage/Permission dependencies |

Log JSON contains exactly seven metadata fields with corresponding $context values:
requestId, routeKey, httpMethod, status, responseLatency, integrationLatency,
responseLength. No headers, Authorization tokens, credentials or bodies. This fixed
format is not application redaction or proof that runtime logs contain no sensitive
data. Lambda logs must remain separate; the DEV root verifies both identities.
The reusable API module cannot discover an existing function's arbitrary custom
application log group. It owns only the explicitly supplied API-log name.

Clients need SigV4 and separately granted scoped execute-api:Invoke. This module
creates no human/client IAM grant; a reachable endpoint proves no authorization.
An external deployment identity must review API/Logs activation permissions and
delivery/resource policies/quotas, KMS usability and Lambda permission propagation.
No broad CloudWatch role or REST-only aws_api_gateway_account is created here.

## Provider-backed outputs and DEV composition

| Output | Actual resource attribute |
| --- | --- |
| api_id | aws_apigatewayv2_api.this.id; Stage/Permission readiness retained |
| invoke_url | aws_apigatewayv2_stage.this.invoke_url; actual provider URL, not a reconstructed API endpoint |
| execution_arn | aws_apigatewayv2_api.this.execution_arn; Stage/Permission readiness retained |
| access_log_group_name | aws_cloudwatch_log_group.this.name |
| access_log_group_arn | aws_cloudwatch_log_group.this.arn; bare identity, not :log-stream:* permission scope |
| access_log_retention_in_days | aws_cloudwatch_log_group.this.retention_in_days |
| access_log_deletion_protection_enabled | aws_cloudwatch_log_group.this.deletion_protection_enabled |
| access_log_group_class | aws_cloudwatch_log_group.this.log_group_class |
| access_log_kms_key_arn | aws_cloudwatch_log_group.this.kms_key_id |

DEV root supplies the API name `<project>-dev-apigw-http` and the path-form access-log name `/<project>/dev/apigw/http`,
plus actual lambda_workload function/invoke outputs (Root Override). Logging defaults
remain 30/protected/null/empty caller tags (Module Default); root provider default
tags are separate. The module adds `Name` and `service = apigw` (Module Fixed,
winning over caller tags): the API name, `<api name>-default` for the stage and the
access log group name (first 256 characters, `#` replaced by `-`) for the log group,
so each caller map accepts 48 other tags; see [deployment configuration](../../../docs/deployment-configuration.md#5-tags). All eight root operational outputs retain names,
types and effective values. No output exposes secret values.

## Migration, operation and limits

[Root moved.tf](../../services/dev/ca-central-1/serverless-api/moved.tf) adds
module.api_access_logs.aws_cloudwatch_log_group.this →
module.http_api.aws_cloudwatch_log_group.this. All four R1 declarations stay intact.
Root moves from five to four module instances with 17 resources; exactly one R2
address changes and sixteen post-R1 addresses remain. No real state move/import,
refresh-only mutation or authenticated plan occurs in Codex. Existing real users
need separately approved ownership/state evidence and a real external plan review;
empty-state mock creates cannot prove no replacement or a successful live move.

Before authorized teardown, disable log deletion protection through a reviewed
configuration/apply outside Codex, then review later deletion. skip_destroy=false
never hides an orphan. R2's log is now owned here: a future authorized module teardown
includes the group and its history, API configuration and scoped Lambda permission;
it must preserve the external function/role/application logs. Review every deletion,
client migration, delivery cleanup, costs and historical key access; teardown is not
atomic. No destroy, deployment, credential use or state operation is authorized here.

The catch-all handler owns application routing/errors. External validation must
exercise unsigned/wrongly signed/insufficiently authorized clients and valid scoped
SigV4 requests; IAM denial is commonly 403. Correlate permission/integration 5xx and
application errors through approved metadata, never payload logging. Throttling is
best-effort token-bucket behavior, not a hard cost cap/quota reservation; review 429
backoff and API/Lambda/logging/KMS/data-transfer costs separately.

DEV Live remains subject to G01–G07 approval, cumulative actual spending ≤JPY 10,000
and verified complete cleanup within 72 hours with no ongoing exercise charges.
Unchanged secret 30-day recovery is still an unresolved complete-deletion blocker.
No deployed authorization, propagation, log delivery or live state outcome is claimed.

## Offline verification and coverage

Use Terraform 1.17.0 and unchanged root AWS 6.72.0 lock/cache; copy only a transient
child lock for backend-disabled readonly-lock init/validate. Native tests are
mock_provider AWS and command=plan only. [coverage.json](tests/coverage.json) retains
all former 47 HTTP API cases/purposes and adds 51 integrated logging adaptations
plus two owned-identity negatives; generic original 51 cases remain unchanged.
Full captures classify actual rejected partial inventories in
[rejected_shapes.json](tests/rejected_shapes.json), never as deployable workloads.

The checker inspects every actual resource, critical known fields, API/IAM/owned-log
bindings and all nine outputs. Source/dependency/move guards supplement actual plans,
not replace them. Actual local counts: 100 native cases (26 positive, 74 rejected); 28 semantic
mutations, 25 capture faults and four source-dependency mutations pass.
Complete result counts and local R2 comparison are recorded in the
[migration record](../../../docs/repository-structure-strategy.md). Full unrelated
regression remains GitHub Actions; no pending CI is a pass. No mock verifies a full
deployed Lambda resource policy or effective AWS authorization.

## References

- [HTTP API Lambda troubleshooting and exact default SourceArn](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-troubleshooting-lambda.html)
- [HTTP API Lambda payload format 2.0](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html)
- [HTTP API IAM authorization](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-access-control-iam.html)
- [HTTP API access logging and activation permissions](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html)
- [HTTP API logging variables](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging-variables.html)
- [HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [API Gateway tagging restrictions](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-tagging-supported-resources.html)
- [API Gateway in GovCloud](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/govcloud-abp.html)
- [AWS Provider 6.72.0 API](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/apigatewayv2_api.html.markdown)
- [AWS Provider 6.72.0 integration](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/apigatewayv2_integration.html.markdown)
- [AWS Provider 6.72.0 route](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/apigatewayv2_route.html.markdown)
- [AWS Provider 6.72.0 stage](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/apigatewayv2_stage.html.markdown)
- [AWS Provider 6.72.0 Lambda permission](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/lambda_permission.html.markdown)
- [AWS Provider 6.72.0 Lambda permission input validation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/lambda/validate.go)
- [Current AWS AddPermission API](https://docs.aws.amazon.com/lambda/latest/api/API_AddPermission.html)
