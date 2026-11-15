# DEV API Root — Cognito + V7-A REST core

V7-A adds module.api_gateway_rest with exactly aws_api_gateway_rest_api.this and
aws_api_gateway_authorizer.this in this same local State. It consumes
module.cognito_auth.authentication directly; existing five Cognito addresses and
the authentication Output remain unchanged. rest_core is a separate public Output.

REST Module Fixed: REGIONAL, disable_execute_api_endpoint=true,
COGNITO_USER_POOLS, Authorization header identity source and required tags.
Root Override: name=${pool_name}-rest, expected dev/aws/ca-central-1/account scope,
actual authentication contract and tags. Module Default: tags={} only.
No Method, path Resource, Integration, Deployment/Stage, VPC Link, Backend or Custom
Domain exists here; no invoke path or runtime token enforcement is demonstrated.
Emulator Lifecycle NOT_TESTED; namespace isolation environment BLOCKED. P0-01–04,
P1-02 and NP-2B/NP-3 remain OPEN for their dependent scopes. serverless-api is unchanged.
See [REST module](../../../../modules/api_gateway_rest/README.md) for tests and limits.

## Historical V6 foundation and validation

# DEV API Root — V6 Cognito only

This Root owns the future Architecture v2 API-facing State; V6 composes only
[the Cognito child](../../../../modules/cognito_auth/README.md). No REST API,
CloudFront, user, Google secret/federation or frontend is implemented. The historical
serverless-api Root and HTTP API resources are unchanged and independent.

Provider Region is fixed ca-central-1 with allowed_account_ids=[aws_account_id],
local DEV backend and committed Terraform~>1.17.0/AWS~>6.72.0 lock identical to the
existing Root lock. One writer/custodian and local State protection/backup remain
external operational approvals. No remote-state reader or authenticated discovery.

Root Override: required aws_account_id plus every child input except expected_scope,
which is fixed dev/aws/ca-central-1/account. Required pool name/domain/feature plan,
callback/logout lists/default redirect, explicit DEV loopback approval, Resource
Server/scopes/approved subset, TOTP MFA/password and token lifetimes have no defaults.
Tags defaults to{}; required Environment=dev, Service=api, Project and ManagedBy
values override caller collisions. Module Default: child tags={} only. Module
Fixed: protected admin-managed email pool, TOTP, public code-only Cognito client,
revocation, managed-login2/default branding and no secret/Google IdP. See child
README for exact validation, operational responsibilities and all five addresses.

One module.cognito_auth owns five resources; output authentication transparently
exports the resource-derived versioned public contract. Future api_gateway_rest
will consume this output in the same Root without moving Cognito addresses/State.
No cross-State output publication is selected. Configure all actual values through
a separately reviewed non-secret input file outside Git; never use fixture account,
domain or callback allocations. Domain control, email identity verification,
Google secret ownership, browser S256/state/nonce, backend owner/tenant checks,
IAM effectiveness/cost and full teardown remain OPEN.

Root46 native:5 complete positive plans/41 expected validation rejections; independent
plan/security/evidence checks supplement child49. Required-input omission tests must
reject every16 required Root input without accepting positive partial plans. No
unrelated local suite is rerun; historical full781 native/153 toolkit/15 configurations is
for independent GitHub Actions review, not claimed completed here.

G01–G07 remain OPEN. No AWS/State/deployment operations. Future Live needs separate
approval, cumulative actual JPY10,000 limit and complete verified removal within
72 hours; ACTIVE pool deletion protection needs explicit source/plan review before
teardown. The Secrets Manager recovery blocker remains unresolved. No STG/PROD Root,
API deployment or Google activation is authorized by this source.
