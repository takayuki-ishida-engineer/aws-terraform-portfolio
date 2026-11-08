# API Gateway HTTP API

This child module exposes one existing Lambda function through an IAM-authorized
HTTP API. It owns exactly five API/permission resources. It creates no Lambda
function, execution role, access Log Group, deployment resource, authorizer,
domain, certificate, client identity, networking or service-root composition.
Providers and backends remain root-owned. No AWS deployment occurs in this phase.

## Inventory and effective configuration

| Resource | Module Fixed configuration |
| --- | --- |
| `aws_apigatewayv2_api.this` | `HTTP`; default execute-api endpoint enabled; no quick-create target, OpenAPI body or CORS |
| `aws_apigatewayv2_integration.this` | One `AWS_PROXY` Lambda integration; `POST`; payload `2.0`; `INTERNET` connection |
| `aws_apigatewayv2_route.this` | One `$default` catch-all route; `AWS_IAM`; target is the actual integration |
| `aws_apigatewayv2_stage.this` | `$default`; automatic deployment; mandatory access logs; rate 10, burst 20 |
| `aws_lambda_permission.this` | One exact-function `lambda:InvokeFunction` permission for `apigateway.amazonaws.com` |

| Configuration | Source | Effective value |
| --- | --- | --- |
| `api_name` | Root Override, required | Explicit stable name; no generated suffix |
| Existing Lambda function/invocation ARNs and access Log Group ARN | Root Override, required | Actual externally managed references; no data-source discovery |
| `tags` | Module Default `{}` / Root Override | Visible, non-secret tags on the API and stage; no module-owned tags |
| API/integration/route/stage/permission settings above | Module Fixed | No security, route, logging, CORS or throttling override switches |
| Provider Region, authenticated account, `allowed_account_ids` and `default_tags` | Root Override, outside this interface | Selected and reviewed by the future owning root |

## Input contract

There are four required strings and one optional map:

| Input | Validation and responsibility |
| --- | --- |
| `api_name` | 1–128 ASCII letters/digits/underscore/period/hyphen; first character a letter or digit |
| `lambda_function_arn` | Actual complete unqualified Lambda function ARN, at most 140 characters under the pinned provider; no alias, version, wildcard or partial ARN |
| `lambda_invoke_arn` | Actual Lambda module `invoke_arn`; exact `apigateway:<region>:lambda:path/2015-03-31/functions/<function-arn>/invocations` form for the same function |
| `access_log_group_arn` | Actual existing bare Log Group ARN; no `:*`, log-stream suffix, wildcard or reserved literal `aws/` name |
| `tags` | `map(string)`, default `{}`, `nullable = false`; an explicit null map uses the default |

The API-name character set is a deliberately conservative **module** constraint;
AWS/provider documentation specifies the 128-character limit without this full
character restriction. Names and tags must not contain secrets or sensitive data.
GovCloud configuration metadata must also follow its export-control restrictions.

References must use the same partition, account and Region. Reviewed partitions
are `aws` and `aws-us-gov`; China and isolated/unreviewed partitions are rejected.
GovCloud Regions are limited to `us-gov-east-1` and `us-gov-west-1`. The reviewed
Region form is `^[a-z]{2}(-[a-z]+){1,2}-[1-9]$`, at most 63 characters, with
unsupported partition-specific Region families rejected. This checks syntax
without claiming that every matching Region exists or supports the required
services. Qualified Lambda ARNs are rejected. The logging name contract matches
the existing CloudWatch Logs module.

The whole function-ARN limit of 140 characters comes from AWS Provider 6.72.0's
Lambda permission validator. The current AWS `AddPermission` API reference permits
256 characters, but that does not relax this pinned provider's stricter limit.
This module follows the pinned implementation used by its tests and CI.

Tags allow at most 50 entries, keys of 1–128 Unicode characters, and non-null
values of 0–256 characters. Characters are Unicode letters, numbers, separators
and `_ . : / = + @ -`; the reserved `aws:` prefix is rejected case-insensitively.
API and stage `tags_all` postconditions also check root-owned provider defaults.
Matching caller keys override provider defaults. Computed effective tags can
remain unknown until creation, so postconditions may fail afterward without
rolling resources back. The root must review the merged tag sets beforehand.

ARN consistency does not authenticate the provider or prove existence/ownership.
An API postcondition compares its actual execution ARN, including actual API ID,
with the Lambda reference's partition/Region/account. This prevents dependent
permission/stage creation after a detected mismatch, but can fail only after the
API has been created. It is not a substitute for root provider account/Region
restrictions and external ownership checks.

## Three separate permission boundaries

1. **Client to API Gateway:** the `$default` route requires `AWS_IAM`. Clients must
   sign requests with SigV4 and possess appropriately scoped `execute-api:Invoke`
   permission for this API/stage/route. This module creates no client identity or
   IAM policy. The enabled execute-api endpoint remains internet reachable;
   IAM authorization does not make it a private API.
2. **API Gateway to Lambda:** the single Lambda permission targets the exact
   unqualified function ARN and service principal `apigateway.amazonaws.com`.
   Its source is the actual API execution ARN plus `/$default/$default`, as
   documented for this HTTP API stage/route combination. It grants no other API,
   stage, route or function access and uses no `/*/*` source wildcard. The
   statement ID is `AllowHttpApi` plus the full SHA-256 of the actual API ID,
   avoiding a shared fixed ID without randomness. This is one planned permission
   statement, not an offline-rendered copy of the full deployed Lambda policy.
3. **Lambda to AWS services:** the existing Lambda execution role controls logging,
   secret reads and any other reviewed runtime access. This module does not change
   that role, human Permission Sets, account policies, `iam:PassRole` or VPC ENI
   permissions. Invocation permission does not expand the application's role.

Existing Lambda resource-policy statements, SCPs, identity/resource policies and
other applicable controls still affect real access. The module does not claim
exclusive ownership of the function's entire resource-based policy. A separate
review is required for cross-account or qualified-function designs.

## Integration and access logging

The integration uses the existing Lambda module's actual `invoke_arn`, not a
predicted endpoint. The function must accept HTTP API payload format **2.0** and
return a compatible response. This format differs from REST/API Gateway payload
1.0, including header/query-string and cookie handling. AWS can infer a 200 JSON
response for valid JSON without `statusCode`; applications needing explicit
status/headers/body must return the documented 2.0 response structure. Mock plans
cannot establish handler correctness, artifact compatibility or application safety.

The destination is an explicitly supplied **API access** Log Group. Provision it
separately, for example with the existing CloudWatch Logs module; do not implicitly
reuse the Lambda application Log Group. This interface cannot prove that the root
has selected a distinct, existing group. Retention, deletion protection, encryption,
key policies, log access and cost management belong to that group's owner.

The fixed single-line JSON format contains only:

| JSON field | HTTP API logging variable |
| --- | --- |
| `requestId` | `$context.requestId` |
| `routeKey` | `$context.routeKey` |
| `httpMethod` | `$context.httpMethod` |
| `status` | `$context.status` |
| `responseLatency` | `$context.responseLatency` |
| `integrationLatency` | `$context.integrationLatency` |
| `responseLength` | `$context.responseLength` |

These are string fields after substitution; unavailable metrics can have placeholder
values. There is no request body, Authorization header, cookie, credential,
response body or application-error-message logging. Additional diagnostic fields
require a separate review; consumers must not assume every metric parses as a number.

The external provisioning principal needs reviewed API Gateway management and
Lambda permission-management authority, plus permissions to activate HTTP API
access logging. AWS's HTTP-specific activation example lists log-delivery and
resource-policy operations (`CreateLogDelivery`, `UpdateLogDelivery`,
`DeleteLogDelivery`, `GetLogDelivery`, `ListLogDeliveries`, `PutResourcePolicy`,
`DescribeResourcePolicies`), and setup/view operations (`CreateLogGroup`,
`DescribeLogGroups`, `DescribeLogStreams`, `GetLogEvents`, `FilterLogEvents`).
Some operations in that published example require wildcard resources. Review the
applicable operations and resource scope for the external workflow; the example
is not a new policy granted by this module or an extension to existing humans.
The destination Log Group must already be provisioned externally; this module
does not verify its existence. Verify delivery configuration, resource
policies/quotas and any KMS prerequisites externally. No `aws_api_gateway_account`
or broad CloudWatch role is created; the HTTP API logging guide governs this
contract rather than silently copying a REST API logging-role setup.

## Ordering, outputs and future composition

Stage creation explicitly depends on the route and Lambda invoke permission.
The route itself references the integration. This orders initial automatic
deployment after the required resources; it does not guarantee AWS propagation,
effective invocation authorization or successful access-log delivery.

| Output | Actual provider resource attribute |
| --- | --- |
| `api_id` | `aws_apigatewayv2_api.this.id` |
| `invoke_url` | `aws_apigatewayv2_stage.this.invoke_url` for the managed `$default` stage |
| `execution_arn` | `aws_apigatewayv2_api.this.execution_arn` |

All three outputs explicitly depend on the stage and invoke permission. IDs,
URLs and ARNs are resource-derived; an output is not a live-readiness result.

Future owning-root composition, for documentation only:

```hcl
module "http_api" {
  source = "../../../../modules/api_gateway_http"

  api_name             = var.api_name
  lambda_function_arn  = module.lambda.function_arn
  lambda_invoke_arn    = module.lambda.invoke_arn
  access_log_group_arn = module.api_access_logs.log_group_arn
  tags                 = var.tags
}
```

The root must separately compose and order the Lambda's complete execution-role
policy, application logs, artifact references and API access-log module. It must
use an explicitly authorized workload-account provider with the intended Region
and `allowed_account_ids`. This example implements no service root and authorizes
no AWS credentials or deployment in Codex Cloud.

## Operation, errors, imports and teardown

The default route intentionally catches all paths/methods. Application routing,
input validation and error responses remain the handler's responsibility. Test
unsigned, wrongly signed and insufficiently authorized clients; IAM denial is
commonly a 403, and a reachable endpoint is not evidence that a request was allowed.
Test valid SigV4 callers separately. API/integration 5xx errors can result from
permission propagation, unavailable functions or incompatible responses; correlate
the request ID with authorized operational evidence rather than logging payloads.

Default throttling targets 10 requests/second and a burst of 20. AWS applies
throttling on a best-effort token-bucket basis; these are not hard request ceilings,
an absolute cost cap or a quota reservation. Account/Region limits also apply.
Handle 429 responses with bounded client backoff and separately review request,
Lambda invocation, logging ingestion/storage and data-transfer costs.

Reconcile drift through a reviewed real plan outside Codex Cloud. Before import,
inventory the existing API, integration, route, stage, Lambda permission statement
and logging delivery ownership. Import/reconcile all five resources under one
owner; an API-only import does not adopt its routes/stages. Fixed AWS_IAM/logging
settings can change existing access. Extra externally managed routes or Lambda
policy statements are not proven safe by this module.

A future authorized teardown removes this API configuration and its named Lambda
permission statement. It must preserve the external function, execution role and
Log Group; retained logs/costs follow the external owner's policy. Stop or migrate
clients first, review all deletions and delivery cleanup, and allow for in-flight
requests and propagation. Teardown is not atomic. No real deletion is authorized
in this phase.

## Offline evidence and remaining prerequisites

Terraform 1.17.0 / AWS Provider 6.72.0 use the unchanged dev-root provider lock.
Native tests use `mock_provider "aws" {}` and explicit `command = plan`. The
independent standard-library checker inspects actual generated plans: complete
five-resource inventories, fixed authorization/integration/logging/throttle values,
Lambda permission **fields**, bindings and outputs. It exercises unsafe mutations
and malformed/incomplete captures. Rejected-input partial plans are classified
separately from valid positive configurations. Completed counts and exact-head
GitHub CI evidence are reported on the PR.

The native suite has **47 passing runs**: eight complete five-resource positive
configurations and 39 intentional input/postcondition rejections. Rejected plans
include 20 empty, six API+permission, eight API/integration/route/permission, four
API-only and one five-resource plan rejected for effective stage tags. These are
validation evidence, not successful configurations or created AWS resources.
All four missing mandatory inputs separately fail before any plan. The checker
rejects **17 unsafe mutations** and **19 capture/process/JSON faults** by the
violated invariant rather than changed hashes. Existing 332 native and 153 Python
regressions are preserved; the new native total is **379**.

The Lambda service generates the deployed resource-policy JSON. A mocked
`aws_lambda_permission` plan does not contain or validate that full deployed
policy. No mock establishes a real client session, effective AWS authorization,
provider account, application response or log delivery. Before a future deployment,
an independently authorized external workflow must verify existing ownership and
Region/account, provider restrictions, payload/response behavior, scoped SigV4
allow/deny cases, the effective Lambda policy, unrelated API/stage rejection,
access logs without sensitive content, throttling/error handling and recovery.
Do not use the Organizations Management Account for deployment tests.

No AWS credentials, authenticated APIs, live plans, apply/destroy, actual resources,
service-root integration, Phase 3-9 or Phase 4 are included.

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
