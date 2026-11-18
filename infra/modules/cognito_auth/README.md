# Cognito authentication foundation — V6

Credential-free Terraform source for a future Regional REST API; no users, tokens,
real login, Google federation, frontend or AWS deployment. Master Policy v11 user
requirements govern; the unavailable external PDF is not claimed read.

## Exclusive ownership and compatibility

Five addresses: `aws_cognito_user_pool.this`, `aws_cognito_user_pool_domain.this`,
`aws_cognito_resource_server.this`, `aws_cognito_user_pool_client.this` and
`aws_cognito_managed_login_branding.this`. DEV prefixes each with
`module.cognito_auth.` in the [API Root](../../services/dev/ca-central-1/api/README.md).
No new provider, external IdP writer, user resource, SES/SNS, certificate, custom
DNS or API Gateway. Provider6.72.0 actual schemas were inspected for all five
resources/arguments, including managed_login_version and branding default values.
Child compatible constraints follow repository conventions; Root pins Terraform
~>1.17.0/AWS~>6.72.0 with the unchanged existing lock identity.

Root owns provider/account restrictions/backend and environment settings. DEV
local State is scoped env/Region/api, with one authorized writer. Future REST
composition consumes this actual output inside the same Root, not remote State.
No existing serverless-api/HTTP API, Platform or Network resource changes owner.

## Inputs and effective settings

Every security/deployment input is required and non-null: expected_scope (environment,
partition, Region, account_id), name_prefix, feature_plan,
allow_dev_loopback, callback_urls, logout_urls, default_redirect_uri,
resource_server_identifier, scopes (name→description), approved_scope_names,
mfa_configuration, password_minimum_length, access_token_minutes,
id_token_minutes and refresh_token_hours. tags alone defaults to {}.

`name_prefix` is `<project>-<env>` (2–20 lowercase letters, digits or hyphens). It
must end with `-<expected_scope.environment>`, which keeps the former
environment-binding guard, and must not contain aws, amazon or cognito, which are
reserved in Cognito domain prefixes. Names follow [deployment configuration](../../../docs/deployment-configuration.md#4-resource-naming) (**Module Fixed**):
user pool `<prefix>-cognito` (Name tag and `service = cognito`, winning over caller
tags), app client `<prefix>-client` and domain prefix `<prefix>-auth`. The client,
domain, resource server and branding are not taggable. `project`, `env` and
`managed` come from the root's provider `default_tags`.

| Source | Effective contract |
| --- | --- |
| Root Override | All required inputs, including name_prefix `<project>-dev`; DEV scope aws/ca-central-1 and required account; caller tags only (reserved keys rejected by the root) |
| Module Default | tags={} only; no guessed paid plan, names, callbacks or token lifetime |
| Module Fixed | ACTIVE deletion protection; email username, case-insensitive; admin-only user creation/recovery; no automatic verification/delivery; mutable required email; TOTP enabled; code-only public client; Cognito-only IdP; revocation; default branding/domain v2 |

Scope permits dev/stg/prod but aws/ca-central-1 only in this initial contract;
no STG/PROD Root is created. Names must be environment-prefixed lowercase, domain
prefix AWS-valid syntax without reserved aws/amazon/cognito strings. Actual prefix
availability and name ownership require external review. Feature plan must be
ESSENTIALS or PLUS: managed login2 is not a Lite feature. Both selections require
cost approval before AWS execution; fixture Essentials/Plus does not approve payment.

Email is the login identity. To avoid unauthorized email delivery, no auto-verified
email, email MFA, SES config or delivery infrastructure is configured. An external
approved administrator must verify identity/email ownership and set email_verified
before any reliance on that assertion; V6 never claims verification occurred.
Self-registration is disabled. Recovery is admin_only, with a separately approved
identity-proofing/TOTP device-loss recovery process; no SMS/email recovery fallback.
The client reads email/email_verified and can write only non-identity name, not
email or its verification status. Required email remains mutable for later reviewed
federation/admin lifecycle. Schema mutation/replacement implications need external
plan review. Password length14–99 is explicit, all four character classes required,
temporary validity1 day. MFA ON or OPTIONAL is explicit; OFF/SMS rejected. Local
TOTP requirements do not enforce MFA on Google-federated identities.

## OAuth, URLs and scopes

Client generate_secret=false, code-only OAuth enabled, explicit_auth_flows only
ALLOW_REFRESH_TOKEN_AUTH; no implicit/client_credentials/password/admin-password
flows. Token revocation=true, existence errors=ENABLED, auth session3 minutes.
Access/ID lifetimes are required integer5–60 minutes; refresh1–24 hours. Token units
are explicit. Refresh rotation is not claimed; future rotation changes need review.

Callback/logout lists each contain1–10 unique reviewed entries. Full anchored URI
validation rejects wildcards, userinfo, fragments, query strings, empty entries,
unresolved tokens and unapproved non-HTTPS. Paths are deliberately conservative
ASCII; unsupported encodings/queries need reviewed contract changes. HTTP is only
localhost/127.0.0.1 with explicit DEV-only allow_dev_loopback=true. The default
redirect must be a callback member. A valid URI string is not proof of domain
control, open-redirect safety of its application, DNS or callback approval.

Resource Server has an explicit simple identifier and1–10 lowercase named scopes,
nonempty descriptions. Client custom scopes are only the approved subset of
actual resource-server identifier + validated scope name; OIDC scopes are fixed
openid/email. No root-fabricated duplicate namespace. Resource-server creation
precedes client; domain/pool/client precede default managed-login branding.
A domain alone is not branding/setup evidence for a programmatically created client.

Future REST Cognito User Pool Authorizer methods must require explicit API scopes
on access tokens. ID tokens do not substitute for scoped access authorization.
Custom scopes are not backend tenant/owner checks. The eventual browser must
implement S256 PKCE/challenge+verifier, state, nonce, redirect validation and secure
session/token handling. Terraform and mocks prove none of those handshakes.

## Output and endpoint contract

One inferred-typed `authentication` object, interface_version=1: validated scope,
resource-derived user_pool_id, user_pool_arn, app_client_id,
resource_server_identifier, approved_custom_scopes, domain_prefix, issuer_url and
managed_login_branding_id. No client secret/token/user dataset/complete State.
Publication/authenticity/consumer access remain OPEN if ever crossing ownership.

Prefix-domain convention: https://<prefix>.auth.ca-central-1.amazoncognito.com.
Paths: /oauth2/authorize, /oauth2/token, /logout and future /oauth2/idpresponse.
Issuer is the pool's actual public endpoint; discovery is issuer +
/.well-known/openid-configuration (JWKS is /.well-known/jwks.json). These are
conventions, not successful DNS, signature verification or login evidence.

## Google external integration — not operational

No aws_cognito_identity_provider or real/placeholder Google client_secret exists.
Future separately approved external owner must initialize/rotate Google OAuth
Client Secret outside Terraform variables/data/plans/State/outputs/Git/CI. Google
Client ID is non-secret but not yet allocated. Register the exact controlled
Cognito prefix-domain /oauth2/idpresponse URI with Google, request openid/email/profile,
review verified email and email_verified mappings to mutable Cognito attributes
and upstream assurance/account-linking behavior. Google MFA is an independent
upstream obligation. App Client currently enables COGNITO only. Enabling Google
requires a separately reviewed model coordinating this Terraform-owned setting
with external IdP lifecycle; do not use ignore_changes or a second writer to hide
drift. No Google sign-in is claimed.

## Verification and operations

Child49 native (5 positive/44 rejection), API Root47 (5/42, including the root-only reserved-tag-key rejection). Actual full mock plans
are checked independently for exact ownership, resource-linked IDs/scopes,
password/TOTP/admin policy, private-secret boundary, OAuth/lifetimes/URLs and output
inventory. Per scope32 unsafe plan mutations and13 evidence faults rejected.
Actual-source and required-input checks are in tests/check_rejections.py; counts
are reported from completed execution, not counted as native tests. Negative
partial plans are not accepted as successful five-resource configurations.

V6 added 95 native cases. Current totals and initialized configurations, all
sharing one locked AWS provider, are in the latest Full CI job summary ("Summarize actual validation results"). Complete
CI belongs to independent exact-HEAD review; local results are not full CI success.
Mocks do not prove Cognito/IAM behavior, delivery, token signatures, PKCE, cost,
feature availability, federation, quotas, prefix uniqueness or teardown.

G01–G07 OPEN. No AWS credentials/authenticated calls, real State, apply/destroy/import,
users or secrets. Dedicated workload account/identity, callback control, paid-plan
cost, State custody and actual external plan require separate authorization.
ACTIVE deletion protection requires an explicit reviewed source change before
future authorized deletion; it is not silently bypassed for cleanup. Inventory
users/domain/branding/client/pool and confirm full removal externally. DEV cumulative
actual cost<=JPY10,000, complete verified removal within72 hours. Secrets Manager
30-day recovery conflict remains OPEN; Cognito does not resolve it.

Official references consulted:

- https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa.html
- https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_CreateUserPoolClient.html
- https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_CreateManagedLoginBranding.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-social-idp.html

External user initialization must suppress automatic invitation delivery until a separately
approved communication/identity-proofing process exists. Revocation does not prove immediate
rejection of every already issued JWT; future REST/token validation must review expiry,
audience, token_use and revocation behavior independently.
