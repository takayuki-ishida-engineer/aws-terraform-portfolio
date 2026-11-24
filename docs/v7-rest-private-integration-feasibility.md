# V7-0 REST / private integration technical contract

> **Historical record.** Master Policy **v14.5** (2026-11-23) is the only current
> controlling policy, applied by [AGENTS.md](../AGENTS.md). Statements here that name
> an earlier policy (v10 to v14.4, the v14.2 alignment record) as current authority,
> or that describe optional DEV Live verification, G01–G07 gates or the JPY 10,000
> limit, are historical. Under v14.5 §15 real AWS/EKS Live verification is outside the
> current scope.

## V7-A source update — runtime not demonstrated

V7-A adds [api_gateway_rest](../infra/modules/api_gateway_rest/README.md) and composes Regional REST core plus Cognito
Authorizer with the actual existing authentication contract in the DEV API Root.
Exactly two REST resources are added; five Cognito resources/authentication remain.
REGIONAL and disable_execute_api_endpoint=true are fixed. No Method, path,
Integration, Deployment/Stage, VPC Link, Backend or Custom Domain is included.
Emulator Lifecycle NOT_TESTED; namespace isolation environment BLOCKED. No real
API invocation, Cognito enforcement or TLS communication is claimed. P0-01–04,
P1-02 and Runtime NP-2B/NP-3 remain OPEN. Earlier implementation-status statements
below are historical snapshots; their evidence is not a new V7-A test result.


## Current v14.2 acceptance overlay

The owner-authorized [v14.2 alignment record](policy-v14-2-alignment.md) governs
current acceptance. Earlier authority/baseline statements below record V7-0's
historical study, not today's main/PR state or governing edition. Technical P0
questions remain OPEN; the acceptance change does not resolve ARN, PKI or manifest
contracts. Current runtime source includes NP-1/NP-2P; historical absence statements
below are not a current inventory (see [runtime checks](../kubernetes/tests/README.md)).

Phase 1 is policy documentation only, with exact-HEAD Full CI and a stop for
independent review/owner approval. After its merge is observed and the owner resumes
Phase 2, V7-A is limited to the new REST core/Authorizer and actual Cognito ARN
reference, default endpoint disabled, with existing Cognito resources/outputs
preserved. No Method, Integration, Deployment/Stage, VPC Link, Backend or Custom
Domain is included. All affected offline checks and existing Full CI remain required.
Emulator lifecycle is NOT_TESTED and known namespace isolation is environment
BLOCKED; neither is a Core PR rejection by itself, a compatibility PASS or an API
skip. Representative lifecycle demonstration is still mandatory at portfolio level
under all fourteen controls, in a separately approved track. No implementation,
workflow, Emulator run, merge or portfolio completion is authorized by this PR.

## Authority, baseline and verdict

Documentation only. Starting main is `a8ae82e8265f577e2801f87ace6fa83da0a7bfaa`;
latest main matched and there were no open PRs at initial entry. On resumption,
GitHub main still matches; the only open PR is this existing V7-0 PR #36, with no
separate conflicting PR. Continue its branch rather than create a duplicate.
Master Policy v14 (2026-11-12) is the sole current normative authority. The user
supplied and authorized the complete 24-page text, which was read and compared
with repository rules and source. The PDF binary remains unavailable: original
PDF SHA-256 **NOT_VERIFIED**, expected
`75265a33d4882ce0e98cdce4ab31c2bd428ca8123562125c307fd08764d0885d`.
Text review is not original-PDF or hash verification; the user explicitly accepts
this limitation for V7-0. No earlier policy edition is used as current authority.
Permanent AGENTS rules remain byte-identical; v14 governs their application.

### Policy/source alignment on resumption

- v14 sections 3–7 preserve the documented Architecture v2, functional module
  ownership and environment/Region/service State boundaries. Actual source has
  eleven reusable children and four DEV ca-central-1 Roots: network, platform,
  api and the independent historical serverless-api. API currently owns only
  Cognito; no REST module, REST method or VPC Link is already implemented.
- All fourteen emulator controls apply together. In particular, review a **saved
  Plan** before Apply/Destroy, verify the generated STS identity as well as the
  synthetic account, and remove State **backups** with other temporary material.
  These clarify the shorter permanent AGENTS wording without changing it or
  authorizing any lifecycle operation in this documentation PR.
- Some unchanged documents still label v13 as current (verification policy and
  foundation design); permanent AGENTS also retains a historical v13 anchor.
  These are stale authority labels, not permission to use v13 as governing policy.
  Correction of those files/permanent rules is outside V7-0's authorized scope:
  record P2-02 and seek separately scoped correction; do not silently edit them.
- Existing [namespace security declarations](../kubernetes/platform/istio/application-security.yaml)
  contain deny-by-default Istio AuthorizationPolicy, not a Kubernetes NetworkPolicy.
  Source has no NetworkPolicy declaration. v14 section 9.2's
  default-deny NetworkPolicy target therefore remains unimplemented (P1-06),
  separate from already implemented mesh policy. Do not claim runtime security
  completion or change Kubernetes resources in V7-0.
- No substantive architectural or security prohibition conflict was found that
  prevents this documentation task. The P0 technical uncertainties below block
  their dependent implementation, not evidence collection. No requirement is
  weakened to close them. Codex documents/tests and submits; independent review
  and explicit user approval remain prerequisites to merge and later work.

**Verdict:** the pinned Provider can statically express the required REST and
certificate-reference model. End-to-end feasibility is conditional, not proven.
The NLB-versus-listener ARN conflict is **P0 OPEN**, as are backend server trust/SNI
and certificate lifecycle verification. No architecture change, security downgrade,
real AWS call or resource implementation is authorized here. V7-A must be separately
authorized and bounded as described below; this document does not close Live gates.

Toolchain remains Terraform 1.17.0 / AWS Provider 6.72.0 / ca-central-1. Existing
HTTP API `serverless-api/` remains separate from REST `api/`. Documentation checks
only; **Emulator Lifecycle: NOT_APPLICABLE (Documentation-only)**.

## 1. AWS specification / Provider 6.72.0 matrix

All Provider links below pin tag v6.72.0. Source inspection is not a runtime PASS.

| Contract | AWS requirement / pinned implementation finding | Decision / remaining evidence |
| --- | --- | --- |
| Regional REST | [RestApi source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/rest_api.go) exposes endpoint_configuration and disable_execute_api_endpoint; Create/Read/Update propagate them | Candidate aws_api_gateway_rest_api REGIONAL, never substitute an HTTP API or PRIVATE REST API |
| Cognito | [AWS method guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-enable-cognito-user-pool.html), [Authorizer source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/authorizer.go): COGNITO_USER_POOLS requires nonempty provider_arns; read/update preserve them | Consume actual module.cognito_auth.authentication.user_pool_arn within API Root, not a fabricated ARN |
| Method scopes | [Method source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/method.go) sends/reads authorization_scopes | Each protected method must have nonempty approved custom scopes, authorization=COGNITO_USER_POOLS and actual authorizer_id |
| Deployment/Stage | [Deployment](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/deployment.go), [Stage](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/stage.go) own snapshot and stage deployment_id separately | Reviewed deterministic redeployment trigger must cover resources/methods/authorizers/integrations and security changes; dependencies alone do not redeploy. Review create-before-destroy, rollback and retained deployments |
| VPC Link V2 | [AWS guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-vpc-links-v2.html), [Provider source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigatewayv2/vpc_link.go) | aws_apigatewayv2_vpc_link is used with REST aws_api_gateway_integration; this does not make the API HTTP/v2 |
| Integration target | [Provider Docs](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/api_gateway_integration.html.markdown) says ALB/NLB ARN; [Go source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/integration.go) uses generic verify.ValidARN, sends raw IntegrationTarget, reads it and patches /integrationTarget | No ARN conversion or semantic listener/LB validation. AWS documentation conflict remains P0-01 |
| HTTPS URI | [AWS private integration guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-private-integration.html) defines HTTPS uri as secure server name / Host header / certificate hostname validation; Provider passes uri directly | Required exact HTTPS backend hostname/port/path; not the NLB ARN as uri. REST tls_config has only insecure_skip_verification; no independent server_name_to_verify field |
| Backend client cert | [AWS ACM backend mTLS guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-acm-client-certificates.html) explicitly allows ACM ARN in clientCertificateId; [Stage source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/stage.go) has unvalidated string, UpdateStage replace /clientCertificateId and GetStage read-back | Statically representable by client_certificate_id=external ACM ARN. Actual ARN round-trip, propagation and presentation NOT_TESTED |
| Regional domain / mTLS | [Domain source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/domain_name.go) exposes regional_certificate_arn, mutual_tls_authentication.truststore_uri/version, ownership_verification_certificate_arn and enum-validated security_policy | Use external certificate references and versioned public-CA truststore; no private-key resource inputs |
| Mapping / WAF | [Base path mapping source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/apigateway/base_path_mapping.go), [AWS WAF guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html) | REST mapping targets actual REST API and Stage. Regional WAF associates with Stage, not CloudFront scope; bypass and error responses require separate tests |

### OAuth and authorization boundaries

Use the V6 `authentication` object from
[child outputs](../infra/modules/cognito_auth/outputs.tf) through the owning
[API Root](../infra/services/dev/ca-central-1/api/main.tf). Validate interface_version,
scope and the approved_custom_scopes subset. Resource-server identifiers/scopes
must remain derived from Cognito resources, never independently rebuilt in Root.

AWS treats a Cognito-authorized method without OAuth scopes as identity-token
usage. With configured scopes it uses access-token authorization, and **any one**
matching method scope is sufficient; this is not an AND policy. Do not leave
business-method scopes empty or treat ID tokens as scoped access tokens. Backend
must enforce tenant/owner/resource access and validate its trusted identity context;
valid mesh identity or one matching scope does not establish ownership. Issuer,
intended client/audience, token_use, expiry, revocation and claim propagation need
review for the chosen flow; do not apply an ID-token aud regex blindly to access
tokens. Browser S256 PKCE/state/nonce and Google federation remain outside this PR.
Do not combine a second Lambda Authorizer with Cognito on the same REST method.

Keep disable_execute_api_endpoint=true and ensure deployment reflects its change.
No temporary default-endpoint or HTTP fallback to create apparent connectivity.
Without the approved custom-domain entry path, absence of a working public invoke
path is expected and must not be hidden by disabling security. Deployment triggers,
Stage routing, access-log redaction/throttling and WAF errors need explicit contracts.

## 2. VPC Link V2 / ARN / endpoint contract

AWS's [REST guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-private-integration.html)
uses an LB ARN in integration-target. Provider Docs agree and its example uses
aws_lb.arn. In contrast, the [PutIntegration API reference](https://docs.aws.amazon.com/apigateway/latest/api/API_PutIntegration.html)
describes integrationTarget as “The ALB or NLB listener”. The Provider pins
[SDK apigateway v1.52.3](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/go.mod);
that [SDK input](https://github.com/aws/aws-sdk-go-v2/blob/service/apigateway/v1.52.3/service/apigateway/api_op_PutIntegration.go)
uses the same listener wording and a plain *string. Generic ARN validation accepts
both structural forms and proves neither service interpretation.

Therefore retain **actual NLB ARN and actual listener ARN**, with different names;
do not silently choose a listener because HTTP API examples do so, or assert LB
semantics from one REST example. P0-01 needs authoritative AWS contract clarification
and a reviewed Provider input/output validation decision. An emulator accepting an
ARN is only emulator evidence, not proof resolving contradictory AWS documentation.
No real AWS probe or support-account operation is authorized by this task.

Candidate REST integration: HTTP_PROXY, explicit integration_http_method,
connection_type=VPC_LINK, actual v2 link ID, integration_target selected only after
P0-01, and https://<reviewed-backend-host>:443/<reviewed-path>. URI controls Host
and certificate hostname checking, not LB selection. Exact SNI behavior and any
stage/base-path rewriting remain OPEN; REST has no independently configurable SNI
field in this Provider. Do not copy HTTP API tls_config/server_name_to_verify or
stage-prefix rewrite assumptions. Require SAN/Host/SNI alignment and reject IP,
NLB-generated-name or mismatched-host shortcuts unless the approved server identity
actually covers them. Never set insecure_skip_verification=true.

All participants must satisfy same account/Region and approved VPC/subnet/SG
relationships. AWS's v2 availability table lists ca-central-1 AZ IDs cac1-az1 and
cac1-az2. These are service support identifiers, **not actual approved allocations**;
AZ names alone do not prove them. Subnets must be private, have ENI/IP capacity and
supported AZ IDs; do not assume every platform/private subnet is eligible. DEV's
NLB stays one subnet in the active worker AZ; link subnet selection and cross-AZ
cost/failure behavior require review without asserting HA.

V2 subnets and SGs are immutable; Provider marks both ForceNew. Replace a link via
reviewed create/AVAILABLE → integration update/redeploy → old-link removal, with
rollback and no destructive reuse of active ENIs. AWS says 60 days without traffic
can make the link INACTIVE and remove ENIs; resumed traffic can fail while ENIs
reprovision. Do not claim permanent readiness from a Terraform create or mock plan.

## 3. TLS and identity contract

```text
Cognito scoped access token + separately reviewed inbound client identity
  -> Regional custom-domain inbound mTLS + Regional WAF
  -> REST method Cognito User Pool Authorizer + explicit API scope
  -> VPC Link V2 ENIs (Platform-owned client SG)
  -> internal NLB TCP443 (no certificate, no TLS termination)
  -> IP target group -> Gateway Service443 -> reviewed Pod target port
  -> Istio Gateway MUTUAL backend TLS + CA validation + expected-client SPKI
  -> STRICT mesh + separately authorized workload/application identity
```

Trusting a CA, matching a client key, revocation handling, Cognito user authorization
and backend tenant/owner checks are separate controls. Neither NLB health nor TCP
reachability proves them. Existing
[private ingress](../infra/modules/private_ingress/main.tf),
[TGB template](../kubernetes/platform/ingress/target-group-binding.template.json)
and [Gateway renderer](../kubernetes/tools/render.py) remain unchanged. Terraform
owns NLB/listener/TG/static SGs; controller owns Pod registration only. No new
LoadBalancer Service, Terraform Pod attachment, SG writer or TG-attribute writer.

### Backend client certificate and server trust

AWS supports imported ACM certificates or ACM-managed Private CA certificates in
the same account and Region, status ISSUED, valid dates and supported key algorithm;
maximum chain length 5. Supported leaf keys are RSA 2048/3072/4096 or ECDSA
P-256/P-384/P-521. Its leaf rules accept absent EKU/KU but require clientAuth
and digitalSignature/keyAgreement when those extensions are present. Prefer an
explicitly reviewed clientAuth leaf profile; do not exploit absent extensions as
an authorization shortcut. Public ACM certificates are not the backend-client
certificate model. An ACM PCA certificate ARN is not an ACM certificate ARN;
PCA-issued/imported material needs external ACM import before Stage association.

No client private key, Google Secret or operational credential may enter Terraform
inputs/data/plan/State/output/CI. External authorized PKI owns issuance/import/key
custody and returns only the approved ACM ARN. Do not use aws_acm_certificate
private_key or a legacy API Gateway-generated certificate just to pass emulator
validation. Provider Stage creation calls its update path when client_certificate_id
is set; update patches /clientCertificateId; read copies GetStage.ClientCertificateId
without stripping/converting ARN. The [AWS guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-acm-client-certificates.html)
explicitly requires GetStage for ACM association: GetClientCertificate(s) do not
return ACM certificates and are not a substitute. This is static correspondence,
not measured Read-back/presentation success.

The backend must request a client certificate for API Gateway to present it.
Istio Gateway remains MUTUAL, TLS>=1.2, exact backend hostname, server credential,
separate client CA credential ending -cacert and one/two reviewed SPKI hashes.
AWS does not validate the supplied leaf/intermediate chain or intermediate intent
for this association; Istio must validate trust chain and expected-client identity.
The server certificate is a **different trust direction**: API Gateway must trust
its issuer and verify hostname. It has a [supported CA list](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-supported-certificate-authorities-for-http-endpoints.html),
not a configurable arbitrary private backend CA bundle in this REST integration.
A private CA suitable for the client certificate is not automatically acceptable
for the Gateway server certificate. No self-signed/private-server fallback by
turning off verification. Actual public-chain/server SAN availability is P0-02.

ACM-managed Private CA renewal can be automatic; imported certs need external
renewal/reimport. AWS describes eventual propagation without Stage redeploy,
allowing old/new certs during rollover. Keep reviewed overlapping client pins/trust,
observe convergence before retiring old material, and account for key changes on
renewal. Expiry/rotation/compromise/revocation-equivalent response, emergency denial,
rollback ownership and proof remain OPEN; no mechanism is selected here. ACM cannot
delete an associated cert until every referencing Stage is detached. Teardown must
respect external certificate custody, costs and the 72-hour inventory obligation.

### Regional inbound mTLS and CloudFront boundary

Use a Regional custom domain with external same-Region ACM server-certificate
reference, S3 truststore URI **and reviewed object version**, REST base-path mapping,
Regional WAF Stage association and disabled default endpoint. No actual domain,
certificate, account or DNS control is assumed. Public truststore certificates are
not private keys; writer/access/version rollback responsibilities remain OPEN.
With imported/Private CA domain certificates AWS requires a separate valid public
ACM ownershipVerificationCertificate; it is not the handshake certificate.

The [mTLS guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-mutual-tls.html)
requires TLS_1_2. The [security-policy guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-custom-domain-tls-version.html)
says enhanced security policies cannot enable mTLS. Candidate is compatible legacy
TLS_1_2, not an unverified TLS13 enhanced policy. No weaker TLS/HTTP fallback or
unprovided v14 requirement is inferred; any new mandatory TLS-policy conflict
would stop implementation for owner decision.

API Gateway does not automatically check client-certificate revocation. Minimum
trusted-CA/issuance scope does not uniquely authorize one CloudFront client.
Expected identity/revocation-equivalent feasibility alongside Cognito is OPEN;
no second Lambda Authorizer is assumed on the same method. Future CloudFront Origin
mTLS plan/availability, origin certificate identity and costs are contract-only;
no distribution or plan selection. Existing JPY 10,000/72-hour and G01–G07 controls
persist. Emulator success cannot prove TLS, effective authorization or Live costs.

## 4. Root, State and minimal interface ownership

| Exclusive writer | Current / proposed responsibility |
| --- | --- |
| network Root / vpc child | Existing VPC, subnets, routing/NAT/endpoints; API must not recreate them |
| platform Root / eks_platform | Existing EKS/custom SG resources; no API ownership transfer |
| platform Root / private_ingress | Existing NLB, TCP listener, TG, NLB/client SG and static rules, controller IAM; API only consumes references and attaches client SG to its link |
| API Root / cognito_auth | Existing five V6 resources and authentication output; unchanged |
| API Root / proposed api_gateway_rest | Future REST API, resources/methods, authorizer, integrations, deployments/Stage and VPC Link V2 in the same API State; dedicated domain/mapping/WAF/log ownership must be approved before its PR |
| External PKI/DNS/truststore custodian | Client/server key and certificate lifecycle, approved references/public trust anchors and DNS authorization; no duplicate Terraform secret or State writer |
| Kubernetes runtime | Existing Gateway/TGB/Service/Pod registration and external Secret initialization; no Terraform NLB/SG/TG setting reconciliation |
| Application owner | Routes, images, tenant/owner logic, workload identities and authorization; no invented app here |

DEV Roots remain infra/services/dev/ca-central-1/{network,platform,api}/ with separate
local State; roots own providers/account guards/backend/env overrides, children own
resources/secure defaults/validation/outputs. Existing serverless-api is independent.
No remote-state reader or new Root/State/module wrapper is introduced.

Candidate required typed manifest version 1:

| Field | Provenance / validation |
| --- | --- |
| interface_version, scope{environment,partition,account_id,region} | Actual private_ingress version/scope; require dev/aws/ca-central-1 and owning API account |
| nlb_arn, listener_arn | Actual distinct Platform output fields; preserve both pending P0-01. Never synthesize one from the other |
| vpc_id | Actual scoped private_ingress VPC; declared metadata is not existence proof |
| vpc_link_subnet_ids plus key/AZ-name/AZ-ID metadata | Approved private Network references and selected Platform context; no assumed allocation. Current ingress output only contains selected NLB subnet IDs, not an approved link-subnet/AZ-ID contract |
| vpc_link_client_security_group_id | Actual Platform-owned SG; API attaches but never recreates/manages its rules |
| backend_target_port | Actual TG/Gateway Pod contract; not VPC Link/NLB listener port443 |

Reject missing/incompatible versions, cross-scope ARNs, duplicate or public subnets,
unknown/unsupported AZs, mismatched VPC/SGs and stale or contradictory evidence.
Do not invent a manifest by filling missing fields with examples. Producer identity,
publication location, signatures/digests, freshness/rollback, consumer read access
and State custodian are **not approved**. No whole Terraform State access. Separate
backend_hostname/client ACM ARN/PKI evidence inputs must satisfy the same scope and
certificate checks without carrying secret values.

## 5. Emulator API compatibility inventory

Baseline is Emulator 1.0.322 / Terraform 1.17.0 / AWS Provider 6.72.0 / CLI 2.35.0,
ca-central-1 / synthetic account `000000000000`. Only the historical disposable
aws_vpc.proof lifecycle is directly demonstrated. Every API below is **NOT_TESTED
in this study**. No HTTP 501 was measured; no PARTIAL-SKIP or UNSUPPORTED assertion
is made from a source comment, filename, issue title or missing test.

Evidence sources:

- [Pinned release and published score asset](https://github.com/aws/aws-emulator/releases/tag/v1.0.322).
  Published scores are supporting evidence only: service-score payload and its
  evaluation-suite revision were not independently reconciled here. No score/pass
  percentage is asserted and no new download host was needed.
- [Official fidelity manifest blob](https://github.com/aws/aws-emulator-evaluation-suite/blob/4df2823bafface2ada35f482c07ff6668cc078e1/manifest.jsonl),
  blob e18faa17fbb9f43d8c5e687bd1df4af19ed688f4,
  29,676 entries /18,231,197 bytes. Counts below are checks naming each operation,
  not counts of passed checks, not release-specific operation scores.
- [Pinned service sources](https://github.com/aws/aws-emulator/tree/v1.0.322/services).
  Per-service trees were read without truncation; the top-level recursive tree
  was truncated and was not used to infer absence. Selected REST/VPC-link/ELB/ACM/
  Cognito handlers contain state/validation implementations, not merely filenames.
  Generic scaffold NotImplemented comments also occur in implemented handlers.

| API family / operation (manifest check references) | Static evidence and compatibility risk | Current result |
| --- | --- | --- |
| REST API: CreateRestApi (653), GetRestApi (67), UpdateRestApi (23), DeleteRestApi (686) | CreateRestApi handler stores scoped API state; configuration-specific behavior unproven | NOT_TESTED |
| REST Resource: CreateResource (316), GetResource (21), UpdateResource (7), DeleteResource (55) | Control-plane operation files/manifest coverage; no route behavior claim | NOT_TESTED |
| Method: PutMethod (497), GetMethod (47), UpdateMethod (11), DeleteMethod (17) | Declarations do not prove JWT/scope or tenant authorization | NOT_TESTED |
| Authorizer: CreateAuthorizer (65), GetAuthorizer (21), UpdateAuthorizer (7), DeleteAuthorizer (26) | Creation handler present; Cognito token enforcement unverified | NOT_TESTED |
| Integration: PutIntegration (465), GetIntegration (39), UpdateIntegration (9), DeleteIntegration (13) | Inspected storage/bounds handlers do not settle AWS LB/listener ARN semantics or TLS | NOT_TESTED |
| Deployment: CreateDeployment (395), GetDeployment (21), UpdateDeployment (7), DeleteDeployment (7) | Snapshot/redeployment and rollback semantics need actual lifecycle | NOT_TESTED |
| Stage: CreateStage (171), GetStage (101), UpdateStage (67), DeleteStage (146) | ACM ARN association has a source-level risk described below | NOT_TESTED |
| VPC Link V2: CreateVpcLink (13), GetVpcLink (16), GetVpcLinks (7), UpdateVpcLink (4), DeleteVpcLink (13) | Inspected CRUD; CreateVpcLink resolves subnets through EC2, not arbitrary fixture strings. ENI/SG/idle behavior unproven | NOT_TESTED |
| NLB: CreateLoadBalancer (344), DescribeLoadBalancers (320), DescribeLoadBalancerAttributes (17), ModifyLoadBalancerAttributes (37), DeleteLoadBalancer (371) | Creation handler present; no real network/health/forwarding proof | NOT_TESTED |
| Listener: CreateListener (251), DescribeListeners (43), ModifyListener (23), DeleteListener (225) | Creation handler present; no TCP/TLS transport proof | NOT_TESTED |
| Target Group: CreateTargetGroup (294), DescribeTargetGroups (48), DescribeTargetGroupAttributes (19), ModifyTargetGroup (16), ModifyTargetGroupAttributes (63), DeleteTargetGroup (298) | Creation handler has protocol/target validations; dynamic registration remains outside V7 ownership | NOT_TESTED |
| ACM reference/lifecycle: DescribeCertificate (102), GetCertificate (23), RequestCertificate (68), ImportCertificate (247), DeleteCertificate (301) | Read handlers present; certificate issuance/validation/association and real PKI unproven; key-bearing operations are external-owned, not authorized here | NOT_TESTED |
| Regional domain/mTLS: CreateDomainName (53), GetDomainName (41), UpdateDomainName (4), DeleteDomainName (53) | Handler present; DNS/ISSUED/truststore/handshake behavior has known-source gaps | NOT_TESTED |
| Base path mapping: CreateBasePathMapping (27), GetBasePathMapping (25), UpdateBasePathMapping (5), DeleteBasePathMapping (26) | Control-plane records do not demonstrate bypass prevention | NOT_TESTED |
| Cognito Pool: CreateUserPool (726), DescribeUserPool (56), UpdateUserPool (34), DeleteUserPool (731) | Selected handler present; source existence does not prove effective authentication | NOT_TESTED |
| Cognito Client: CreateUserPoolClient (478), DescribeUserPoolClient (45), UpdateUserPoolClient (18), DeleteUserPoolClient (221) | V6 public-client/code/scopes/revocation assumptions need isolated lifecycle | NOT_TESTED |
| Cognito Domain: CreateUserPoolDomain (43), DescribeUserPoolDomain (29), UpdateUserPoolDomain (3), DeleteUserPoolDomain (43) | Published resolved branding/domain issue is not local runtime evidence | NOT_TESTED |
| Cognito Resource Server: CreateResourceServer (20), DescribeResourceServer (7), UpdateResourceServer (2), DeleteResourceServer (5) | Scope declarations are not real access-token enforcement | NOT_TESTED |
| Cognito Branding: CreateManagedLoginBranding (6), DescribeManagedLoginBranding (6), UpdateManagedLoginBranding (5), DeleteManagedLoginBranding (4) | Selected default-branding handler inspected; no real managed-login/Google proof | NOT_TESTED |

Specific pinned evidence and constraints:

- [Emulator UpdateStage handler](https://github.com/aws/aws-emulator/blob/v1.0.322/services/service-com-amazonaws-apigateway-backplanecontrolservice/src/ops/update_stage.rs)
  validates clientCertificateId against store.client_certificates keys. The reviewed
  context builds this set from API Gateway client-certificate records, with no ACM
  resolution visible in that path. This is a **potential behavioral incompatibility**
  for ACM ARN, not a measured 501. Later isolated ARN round-trip tests must retain
  errors and must not replace the required certificate model with a legacy cert.
- [V2 CreateVpcLink handler](https://github.com/aws/aws-emulator/blob/v1.0.322/services/service-com-amazonaws-apigatewayv2-apigatewayv2/src/ops/create_vpc_link.rs)
  resolves EC2 subnets and same-VPC membership. [Published open issue](https://github.com/aws/aws-emulator/blob/v1.0.322/issues/things-that-do-not-work/20261106T131339Z-apigatewayv2-2-net-new-root-causes-createvpclink-s.md)
  describes error-envelope/stage-variable divergences, not evidence that all link
  operations are unimplemented.
- [Published open ACM/mTLS scenario issue](https://github.com/aws/aws-emulator/blob/v1.0.322/issues/things-that-do-not-work/20261110T152935Z-acm-apigateway-s3-the-mutual-tls-regional-custom.md)
  reports a certificate remaining PENDING_VALIDATION, before domain/truststore/TLS
  behavior is exercised. Do not interpret it as proof that mTLS worked or failed.
- [Resolved Cognito branding/domain issue catalogue](https://github.com/aws/aws-emulator/blob/v1.0.322/issues/things-that-now-work/20261029T184956Z-cognito-idp-hosted-ui-branding-and-domain-reads.md)
  is supporting release information, not a V6 lifecycle PASS.
- [Resolved API Gateway VPC-link issue](https://github.com/aws/aws-emulator/blob/v1.0.322/issues/things-that-now-work/20261109T152222Z-apigateway-cloudformation-ec2-elbv2-aws-apigateway-vpclink-creates.md)
  concerns the older CloudFormation API Gateway link representation; do not
  transfer its result to REST/v2 integration or ARN semantics.

Future execution must follow all 14 permanent AGENTS controls. PASS requires actual
operation evidence; PARTIAL means only part demonstrated; PARTIAL-SKIP requires
actual evidence of the specific unsupported API (such as 501), not a whole-service
skip. FAIL is a Terraform/configuration defect requiring correction/retest;
BLOCKED is an unmet setup/network/isolation prerequisite; NOT_TESTED is unexecuted.
No emulator API response alone establishes real AWS IAM, routing, TLS or capacity.

## 6. OPEN register and decision owners

P0 blocks the affected implementation/integration acceptance; P1 must be resolved
before its dependent PR; P2 is documentation/operational follow-up. These are not
new approved architectural decisions. Any remaining technical or operational
decision not approved by v14 requires owner input.

| ID / priority | Decision and candidate alternatives | Risk / resolution evidence | Decision owner / gate |
| --- | --- | --- | --- |
| P0-01 | integration_target actual NLB ARN versus listener ARN | AWS guide/Provider Docs conflict with API/SDK wording. Preserve both; require authoritative specification clarification and reviewed input/Read-back checks. Emulator alone cannot settle actual service semantics | Architecture owner + independent reviewer; blocks V7-B target selection, not isolated V7-A REST core |
| P0-02 | Exact backend hostname/SAN, supported server CA and URI-driven SNI; external public-chain credential versus another explicitly approved compliant arrangement | No arbitrary private backend CA field. Require official SNI evidence and appropriate isolated TLS/negative proof; no insecure_skip_verification/HTTP fallback. If architecture/security must change, STOP | PKI/security + API/runtime owners; before private integration acceptance |
| P0-03 | ACM-managed Private CA versus imported client cert, exact key identity and ARN round-trip | Same account/Region/ISSUED/profile/chain conditions; no key in Terraform. Verify Stage Update/Get ARN preservation, Gateway request/presentation/CA/SPKI and old/new key overlap. Emulator store lookup may reject valid ACM ARN | PKI/API/runtime owners; external custody/rotation approval before V7-D; no real AWS probe here |
| P0-04 | Minimal manifest producer/consumer authorization, integrity/freshness and state custody | Existing output lacks approved link subnet AZ IDs. Options: separately reviewed signed/versioned minimal file or approved configuration service. No whole remote State. Need approved output provenance/selection and single writer before consuming operational values | Network/Platform/API custodians + user; before V7-B composition |
| P1-01 | Custom-domain public certificate/DNS/control, versioned truststore and inbound client identity | TLS_1_2/mTLS compatibility; ownership certificate if imported/private. Minimal CA is not a single-client allowlist; review revocation-equivalent checks compatible with Cognito, no second method authorizer assumption | PKI/security/DNS/API owners; before V7-C/D |
| P1-02 | Link subnet/AZ/ENI capacity, supported AZ IDs and replacement/idle recovery | Private scope and SG references, active DEV AZ, cross-zone cost/failure and complete teardown evidence; no allocation inferred | Network/Platform/API owners; before link implementation/operational selection |
| P1-03 | Deployment fingerprints, rollback, path/base-path/header mapping and logs | Deployment-snapshot security changes require redeploy; Stage/certificate updates and propagation are tracked separately. No secret/body logs or default endpoint bypass. Review account-wide API Gateway logging-role singleton before assigning its writer | API/application/security owners; V7-A schema and later B/C integration |
| P1-04 | Emulator feature-specific compatibility and release-score mapping | Every implementation PR retains affected mock/security/evidence checks. Separately approved representative demonstration requires isolated lifecycle and precise 501/validation/mismatch evidence, without production workarounds | Implementation + independent reviewer; separate demonstration track under v14.2 |
| P1-05 | API client and backend claim/tenant/owner policy | Any-one scope matching, expiry/token_use/client identity, no ID-token substitution, no wildcard app allow. Agree trusted claim propagation and negative cases without fictional app | Identity/application/security owners; before application authorization acceptance |
| P1-06 | v14 default-deny Kubernetes NetworkPolicy and scoped required traffic | Current application-security.yaml owns STRICT PeerAuthentication and empty-ALLOW AuthorizationPolicy, not NetworkPolicy. Review DNS/control-plane/webhook/mesh/application flows and enforcement support; require actual rendered-policy negative/mutation evidence in a separately authorized runtime PR | Runtime/network/security owners; before runtime security acceptance or optional Live; no Kubernetes changes in V7-0 |
| P2-01 | Certificate monitoring/expiry/revocation, emergency denial and teardown runbook | Credential overlap, propagation delay, detach-before-delete and certificate/CA/CloudFront expenses; no72-hour budget guarantee | Operational/PKI owners; before optional Live |
| P2-02 | Historical authority-label synchronization | The v14.2 Policy Alignment PR updates current authority and acceptance sections; historical v13/v14 study records and evidence remain scoped. No PDF verification is inferred | Repository owner + independent reviewer; policy PR approval/merge remains required |

## 7. Recommended staged implementation and V7-A entry gate

These are recommendations for separately authorized PRs, not permission to start.

| Stage | Proposed files/ownership | Inputs/outputs and checks | Gate / excluded work |
| --- | --- | --- | --- |
| V7-A REST core + Cognito contract | Future infra/modules/api_gateway_rest and existing api Root; preserve all V6 addresses/outputs | Regional API and Cognito authorizer from actual V6 output, default endpoint disabled and minimal outputs. Defer Method/Integration/Deployment/Stage/VPC Link/Backend/Custom Domain. Actual mock-plan inventory/output/reference checks, scope/config negatives, security/source mutations and evidence rejection; exact-HEAD Full CI | Observe Policy Alignment merge and owner resumption, then independent review/user approval. Emulator NOT_TESTED with namespace environment BLOCKED, separate representative track; no fake public invoke success |
| V7-B VPC Link/private HTTPS composition | Same API child/Root; consume Platform/Network minimal references only | V2 link and immutable subnet/SG selection; integration_target after P0-01; HTTPS URI/SNI/Host and TCP443, protected Methods plus actual Integrations/Deployment/Stage. Required certificate-reference contract must be respected before any connectivity claim. Wrong ARN family/scope/SG/AZ/URI/ownership/malformed-manifest and TLS-downgrade mutations; actual link/integration lifecycle where supported | Resolve P0-01/02/04 and P1-02. No NLB/TG/SG recreation or operational State reader |
| V7-C Regional custom domain/truststore/WAF | Approved API-owned domain/mapping/Stage WAF/log resources; external DNS/PKI/truststore writers explicitly assigned | External server certificate and versioned truststore reference, compatible TLS_1_2, mapping, WAF, disabled default endpoint. Negative trust/version/bypass/policy/ownership cases; supported isolated API lifecycle | Resolve P1-01/03; no domain/certificate existence, CloudFront plan or real AWS assumption |
| V7-D backend client identity and combined security acceptance | Verify/complete the existing API-owned Stage ACM ARN association plus separately owned external PKI/runtime contracts; no second Stage writer | ARN Read-back, external server/client trust and pin rotation; preserve Gateway MUTUAL/-cacert/SPKI and STRICT/default-deny. Wrong/expired/untrusted/other-client and no-client/SNI mismatch checks where genuinely executable; distinguish API storage from actual handshakes | Resolve P0-03 and remaining P0/P1. No private key in Terraform, no claimed real handshake from mocks/emulator storage, no automatic Live |

Minimum before V7-A: explicit user authorization after independent V7-0 review;
approve the narrowed REST-core scope and resource-writer map, method/scope and
redeployment schema, required non-secret inputs and output interface, logs/account
singleton decision or explicit deferral without a competing writer, concrete
positive/negative/mutation/evidence criteria. Representative Emulator planning and
execution belong to the separately approved track; they are not a blanket V7-A
implementation PR prerequisite under v14.2.
Keep P0-01/02/03/04 visible and exclude their dependent integrations, rather than
inventing target ARNs, certificates or output publication. Do not create a Deployment over methods with no integration, or add a fictional
MOCK/Lambda integration to make deployment pass. V7-A has no business Method,
Deployment or Stage resource until V7-B can supply the approved integration.
The core may be implemented offline without a functioning public endpoint; do not weaken default
endpoint or authorization controls to present it as usable end-to-end. If these
boundaries cannot be respected, V7-A remains blocked.

All existing Native/Mock/Python/IAM/security/negative/mutation/guardrail checks and
Terraform/provider locks stay intact. Derive future counts from execution. No new
permanent emulator CI dependency is introduced by this document. Significant
unsupported gaps must be reported, not converted to PASS or real AWS fallback.
Real AWS APIs/credentials/SSO/Plan/Apply/Destroy/Import remain prohibited in Codex.
G01–G07 remain OPEN; optional real verification requires separate approval outside
Codex, cumulative JPY 10,000 and full verified teardown within 72 hours. The Secrets
Manager recovery-window conflict remains OPEN. No AWS account, DNS, certificate,
application release, resource allocation or new phase is authorized here.
