# DEV API Root — Cognito + V7-A REST core

V7-A adds module.api_gateway_rest with exactly aws_api_gateway_rest_api.this and
aws_api_gateway_authorizer.this in this same local State. It consumes
module.cognito_auth.authentication directly; existing five Cognito addresses and
the authentication Output remain unchanged. rest_core is a separate public Output.

REST Module Fixed: REGIONAL, disable_execute_api_endpoint=true,
COGNITO_USER_POOLS, Authorization header identity source and module-owned
Name/service tags. Root Override: name_prefix `<project>-dev` (giving
`<project>-dev-apigw-rest`), expected dev/aws/ca-central-1/account scope, actual
authentication contract and caller tags. Module Default: tags={} only.
No Method, path Resource, Integration, Deployment/Stage, VPC Link, Backend or Custom
Domain exists here; no invoke path or runtime token enforcement is demonstrated.
Emulator Lifecycle NOT_TESTED; namespace isolation environment BLOCKED. P0-01–04,
P1-02 and NP-2B/NP-3 remain OPEN for their dependent scopes. serverless-api is unchanged.
See [REST module](../../../../modules/api_gateway_rest/README.md) for tests and limits.

## Input values (Step 1 item 3)

Values follow the [deployment configuration](../../../../../docs/deployment-configuration.md#1-where-values-live). The committed
`terraform.tfvars` holds every required input; environment-specific inputs there
are documented placeholders. Copy `local.auto.tfvars.example` to the untracked
`local.auto.tfvars` and set the real values: `project`, `aws_account_id`, `callback_urls`, `logout_urls` and `default_redirect_uri`. The
[local workflow](../../../../../scripts/local-workflow/README.md) preflight refuses a plan or apply while any of them is
missing locally or still a placeholder. Full CI plans this root with the committed
values under mocks. Never put a credential or secret value in any tfvars file.
State is local by default; for the optional S3 backend copy
`backend_override.tf.example` and `backend.s3.tfbackend.example` (both stay
untracked once copied) and run `run.py <root> migrate-state`.

| Committed value | Setting |
| --- | --- |
| Cognito | `ESSENTIALS`, MFA `ON`, password length 14, access/ID tokens 15 minutes, refresh 8 hours, no DEV loopback |
| Resource server | `portfolio-api`, scopes `read` and `write`, approved `read` |
| Cognito deletion protection | `deletion_protection` (bool, default `true` → `ACTIVE`; `false` → `INACTIVE` only as the first teardown step, finding F19). Root Override of the module default |

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
Names follow [deployment configuration](../../../../../docs/deployment-configuration.md#4-resource-naming):
required `project` (1–10 lowercase characters, starting with a letter, without
aws/amazon/cognito; tracked placeholder `project`) replaces `pool_name` and
`domain_prefix`; the root derives `name_prefix = <project>-dev` (**Root Override**),
giving user pool `<project>-dev-cognito`, app client `<project>-dev-client`, Cognito
domain prefix `<project>-dev-auth` and REST API `<project>-dev-apigw-rest`. The
Cognito domain prefix is globally unique and the placeholder `project` would
collide, so replace it first. Provider `default_tags` set only `project`, `env = dev`
and `managed = terraform` (**Root Override**); modules set `Name` and `service`.
Tags defaults to {} and may not set project, env, service, managed or Name. Module Default: child tags={} only. Module
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

Root47 native: 5 complete positive plans/42 expected validation rejections (including
the root-only reserved-tag-key case); independent plan/security/evidence checks
supplement child49. Required-input omission tests must reject every one of the 15
required Root inputs without accepting positive partial plans. No
unrelated local suite is rerun; historical full781 native/153 toolkit/15 configurations is
for independent GitHub Actions review, not claimed completed here.

G01–G07 remain OPEN. No AWS/State/deployment operations. Future Live needs separate
approval, cumulative actual JPY10,000 limit and complete verified removal within
72 hours; ACTIVE pool deletion protection needs explicit source/plan review before
teardown. The Secrets Manager recovery blocker remains unresolved. No STG/PROD Root,
API deployment or Google activation is authorized by this source.
