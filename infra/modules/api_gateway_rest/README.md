# Regional REST API core + Cognito Authorizer

Owns only aws_api_gateway_rest_api.this and aws_api_gateway_authorizer.this.
Root owns provider, account guard, region, backend/State and environment selection.
The DEV API Root passes the actual module.cognito_auth.authentication object in the
same State. No fixture ARN, authenticated discovery or second Cognito writer.

Module Fixed: REGIONAL; disable_execute_api_endpoint=true; COGNITO_USER_POOLS;
rest_api_id derived from this API; provider_arns from authentication.user_pool_arn;
method.request.header.Authorization; required Environment/Service/Project/ManagedBy
values override caller tags. Module Default: tags={} only. Root Override: name,
expected_scope, actual authentication and tags. All other inputs are mandatory.
Version 1, exact scope and Cognito ARN/ID, nonempty unique approved custom scopes,
and bounded environment-prefixed name are validated. Only aws/ca-central-1 and
reviewed dev/stg/prod scopes are accepted; this does not select provider identity.

rest_core version 1 exports actual API/Authorizer IDs, authorizer pool ARN, scope
and approved custom scopes. No secret, token, invoke URL or lifecycle-readiness
claim. No Method/path/Integration/Deployment/Stage/VPC Link/Backend/Custom Domain.
Scopes are future Method metadata; authorizer creation does not enforce them.
No TLS/runtime, IAM effectiveness, actual service behavior or deployment is proven.
Emulator Lifecycle NOT_TESTED; namespace environment BLOCKED. Real AWS prohibited.
P0-01–04, P1-02 and NP-2B/NP-3 remain OPEN.

## Offline checks

Use Terraform 1.17.0 and the API Root's committed AWS 6.72.0 lock, transiently copied
for this Child as in CI. Use backend=false and lockfile=readonly for init; validate.
Run terraform test -json -verbose -no-color, compact via the existing EKS checker,
and pass events to tests/check_rest_core.py --events FILE. For API events add --root.
The checker requires complete native status/manifest/plan evidence, exact inventory,
resource-derived references/outputs and fixed security settings, and executes
security mutations and malformed/missing evidence rejection. Run
python3 tests/check_source.py /absolute/path/to/terraform for actual mutant mock
plans, validation-removal and missing-input rejections. Existing Cognito child/root
checks remain active; the root verifier checks all seven resources before projecting
its original five-resource Cognito security contract. Full CI adds these REST
checks without removing prior coverage. Actual results belong to the PR HEAD.

Local V7-A results: Child20 native (1 positive/19 rejected), Root46 existing native
(5 positive/41 rejected), REST security mutations13 and evidence faults9 per scope,
source mutations6 and missing required inputs3 rejected. Existing Cognito Child49,
security32/evidence13 per Cognito scope, source mutations10 and Root required-input
rejections16 retained. Full CI on the new PR HEAD must independently confirm these
results; they are not real AWS, runtime or Emulator evidence.
