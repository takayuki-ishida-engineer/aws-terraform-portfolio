# STS correction and remaining runtime contract review

## Follow-up: AWS CLI error prefix root cause (Runs 43723761085 and 43733987794)

Run [43733987794](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43733987794)
on merged main `16a94b5f18c02b63d9aec54c5a87f00ac05ec7f9` again BLOCKED at
`auth-invalid-signature` (`AUTH_STRUCTURED_REJECTION_UNPROVEN`, exit 254).
The cause of both runs is now source-verified. AWS CLI 2.35.0
`ClientErrorHandler` [S5] writes every ClientError through `write_error()` in
[awscli/errorformat.py](https://github.com/aws/aws-cli/blob/2.35.0/awscli/errorformat.py)
(blob `3f7e01429df94c3a25fadeb963a6d57e10a05b2e`), which emits
`\naws: [ERROR]: <botocore ClientError text>\n` in both the default `enhanced`
and the `legacy` error format. `cli_error_code` anchored its full match at
`An error occurred`, so it refused every real envelope. Historical Run 43715108794
classified the code only because its substring search ignored the prefix.
Emulator wording for both refusals is fixed single-line text
([authentication_refusal.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/services/common/src/authentication_refusal.rs)),
and STS models neither code, so the enhanced format adds no detail lines.

`cli_error_code` now requires that exact prefix once, followed by the unchanged
single-record ClientError grammar. Arbitrary leading text, the unprefixed form,
a duplicated or different-level prefix, extra spacing and enhanced detail blocks
remain refused. The fix also covers the post-Destroy `InvalidVpcID.NotFound`
absence oracle, which shares the parser and would otherwise have blocked after a
successful Destroy. Fixtures and test literals use the 2.35.0 rendering; the
pre-fix parser fails 20 tests and 1 error against them, including the complete
lifecycle test.

The structured loopback fallback also returned False in Run 43733987794. Its
failing step is not observable from the allowlisted receipts. The fixed-request
signer was cross-checked locally against botocore `SigV4Auth` with identical
inputs (signatures match), and the Emulator's source 403 template matches
`sts_rejection`, so the signed success response or transport remain unproven
candidates. The fallback stays fail-closed and is no longer reached when the real
CLI envelope parses. Runtime results after this fix are NOT_TESTED until a fresh
Owner-approved dispatch.

## Follow-up: unclassified AWS CLI diagnostic in Run 43723761085

Run [43723761085](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43723761085)
on merged main `785f68af4d915378d17e3528635e6abbe26b7ced`
passed package validation, Docker, isolation, startup and signed STS. The
wrong-secret probe exited 254 but its human-facing CLI stderr failed the
single-line `cli_error_code` parser and was reported
`AUTH_UNCLASSIFIED_REJECTION`. The raw stderr is intentionally unavailable:
the exact formatting mismatch and actual server error code are **not
independently proven by that log**. Do not claim the Emulator accepted an
invalid secret, or that the prior expected code was definitely returned.

To avoid relying on human-facing CLI text, an unclassifiable exit-254 STS
negative probe now requires an **independent structured loopback HTTPS proof**:
a fixed-request, pure-standard-library SigV4 signer must first authenticate the
original Emulator-issued key and secret successfully and return the exact
synthetic STS identity; only then may the mutated credential pass if a separately
signed request returns HTTP 403 with exactly the expected namespace-aware,
single-error STS XML code. Unknown key requires `InvalidClientTokenId`;
wrong secret requires `SignatureDoesNotMatch`. An unexpected CLI exit code,
recognized but incorrect CLI error, failed signed baseline, HTTP 2xx/404,
malformed XML or wrong code is BLOCKED. The successful alternative is recorded
with the fixed `AUTH_WIRE_FALLBACK_VERIFIED` diagnostic; failed proof is
`AUTH_STRUCTURED_REJECTION_UNPROVEN`, with no raw response or secret exposure.

The fixed deterministic SigV4 request vector was checked independently
against Botocore SigV4Auth (reference test; the runtime has no Botocore
dependency). The pure signing and XML parsers plus integrated real-Run mock
transport are tested by positive/negative/mutation cases. This does **not**
establish installed Emulator/Provider interoperability or a successful live
lifecycle, which remain `RUNTIME_NOT_TESTED`. No new network destination is
introduced: the request URL is hard-coded to `https://127.0.0.1:9297/`,
and the existing strict CA/hostname validation, proxy prohibition and
network isolation still apply.


Baseline main: `406b468c820ed7ed7db86c9d38b578184811453d`.
Reviewed on 2026-11-15 (Asia/Tokyo). Historical failed
[Run 43715108794](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43715108794)
passed startup, signed synthetic STS and the bad-secret probe; it stopped at the
unknown-key probe (exit 254, `AUTH_UNEXPECTED_INVALID_TOKEN`). No Emulator,
Docker, real AWS, Terraform Apply/Destroy or manual dispatch runs in this PR.
The source review below preceded the production changes.

## Confirmed defects and fixes

1. `Run.authenticate()` and the integrated mock both expected generic
   `AccessDenied` for an unknown STS Access Key. The STS service translates the
   framework's structural Unauthenticated refusal: a held key is
   `SignatureDoesNotMatch`, an unresolved/absent key is `InvalidClientTokenId`.
   Source [S1] explicitly tests both, including a one-character key mutation.
   Production now requires the service-specific code **and CLI exit 254**.
   Changing the expectation does not accept an invalid credential: PASS denotes
   successful proof of rejection, after successful exact synthetic signed STS.
2. Error substring matching could accept an embedded CLI error-looking string,
   duplicate errors or malformed XML with a matching `<Code>` fragment. This was
   reproduced offline. A single full CLI ClientError envelope (empty stdout)
   and a parsed STS namespace/ErrorResponse/Sender/code envelope are now required.
   Unexpected format, code, 2xx, 404 or exit remains BLOCKED. XML is bounded;
   DTD/entities and duplicate/nested error elements are rejected. The same CLI
   envelope parser prevents an embedded NotFound string from proving absence.
   Official optional ClientError retry wording is supported [S5]. No raw response,
   message, credential, State, Plan or arbitrary exception is printed.
3. An unexpectedly accepted invalid credential caused the generic command
   helper to emit an intermediate auth-invalid-*-aws/PASS before the probe
   correctly BLOCKED. Suppress that premature receipt for both negative probes;
   only the verified rejection may produce their PASS. Accepted-credential
   tests now reject any PASS receipt for that probe, including command receipts.

No further statically confirmed interoperability defect was established. Provider
supporting reads and default VPC side effects were explicitly examined, rather
than equating one Terraform resource with one EC2 API. Runtime-only risks below
are not bypassed to make a future run succeed. GPG, startup, package/tool versions,
Docker, both CI workflows and all policy/security configuration are unchanged.

## Evidence meanings

`UPSTREAM_SOURCE_VERIFIED`: pinned upstream code was read; not a local runtime
result. `TERRAFORM_SCHEMA_VERIFIED`: real 1.17.0 / 6.72.0 validate/schema/Native
Mock command=plan evidence, **not** real API/Apply. `REAL_RUN_VERIFIED`: only the
specific historical run receipts. `SIMULATED_ONLY`: local synthetic transport,
Plan/State or process test. `RUNTIME_NOT_TESTED`: the complete installed
Provider/Emulator interaction remains unexecuted here. Multiple labels describe
different aspects of one row; none promotes simulation to runtime success.

The independent [STS fixture](tests/fixtures/sts-1.0.385.json) contains literal
source-derived responses and separately labeled sanitized historical gate
receipts. It imports no production constants. The integrated model consumes that
fixture instead of inventing an error code. An explicit mutation restores the
old production expectation and must BLOCK the otherwise healthy real `Run`.
A real **fake CLI Python subprocess**, with synthetic data only, exercises actual
subprocess capture, error parsing and `Run.authenticate()`; it is not AWS CLI or
Emulator execution. Existing local TLS/GPG/fake-Docker tests remain separately
classified as local protocol/process tests.

## Contract verification matrix

| Operation / gate | Required behavior | Authoritative evidence | Production | Oracle / fixture provenance | Classification and residual risk |
| --- | --- | --- | --- | --- | --- |
| Signed STS / identity | Signed success, Account `000000000000`, exact `arn:aws:iam::000000000000:user/emulator` | S1; historical Run 43715108794 control-8 | authenticate, identity_gate | Independent STS fixture; identity mutations | REAL_RUN_VERIFIED (historical signed STS); SIMULATED_ONLY (new regression); runtime not replayed |
| Wrong Secret | Held key + bad secret => SignatureDoesNotMatch, CLI 254 | S1 unauthenticated_refusal/test; S5; Run signature PASS | authenticate | Separate wrong_secret fixture and probe; changed key remains constant | UPSTREAM_SOURCE_VERIFIED; REAL_RUN_VERIFIED (historical); SIMULATED_ONLY |
| Unknown Access Key | Unresolved key => InvalidClientTokenId, CLI 254 | S1 account_holds_credential/override_refusal; S5; Run classified token/254 | authenticate | Independent unknown_key fixture, reject AccessDenied and restored-old-predicate mutation | UPSTREAM_SOURCE_VERIFIED; REAL_RUN_VERIFIED (historical rejection, old gate BLOCKED); new gate SIMULATED_ONLY |
| Unsigned STS routing/error | Host names STS, POST Action/Version; HTTP 403 STS ErrorResponse Sender/InvalidClientTokenId | S1 can_handle/addresses_unattributed_query_request; S2; S3 service_from_host | authenticate, unsigned_sts_rejected | Source-derived namespaced XML; malformed/2xx/404/code/namespace/DTD mutations | UPSTREAM_SOURCE_VERIFIED; SIMULATED_ONLY; RUNTIME_NOT_TESTED (route/wire behavior) |
| Authentication disabled / unexpected reply | Any accepted invalid/unsigned request, other code, wrong exit or malformed envelope blocks | S1/S2/S5; explicit security contract | authenticate, cli_error_code | Independent fault injection; accepted credentials, duplicate/embedded messages, unexpected stdout | SIMULATED_ONLY; actual auth-mode failure not induced |
| CA / hostname / generated credentials | Private generated CA/0600 files; no system trust, no hostname bypass | S3; historical startup-ready PASS | startup, generated_file, http | Existing local TLS and material mutations; unchanged startup fixture | REAL_RUN_VERIFIED (historical startup); SIMULATED_ONLY/local TLS; current invocation RUNTIME_NOT_TESTED |
| Provider account discovery | Validation enabled => STS identity; exact allowed account, no skip/IAM fallback | S6 provider Configure/GetAwsAccountIDAndPartition | adapter/main.tf | Installed 6.72 schema; existing source/adapter checks, integrated init simulation | UPSTREAM_SOURCE_VERIFIED; TERRAFORM_SCHEMA_VERIFIED; RUNTIME_NOT_TESTED (installed Provider handshake) |
| Offline init / isolated State | Backend=false, readonly committed lock, filesystem mirror only; empty disposable local State | S6/S7; unchanged prepare mirror | setup, state, adapter | Real external-temp locked init/validate; integrated init/initial-State faults | TERRAFORM_SCHEMA_VERIFIED; SIMULATED_ONLY; actual image/mirror runtime not replayed |
| EC2 DescribeVpcs / baseline | Regional inventory, tags/IDs; default network may be initialized on first read | S8 DescribeVpcs handle; state ensure_default_network | vpcs, baseline_preserved; snapshot before create | Synthetic API inventories, tag-order and duplicate mutations | UPSTREAM_SOURCE_VERIFIED; SIMULATED_ONLY; RUNTIME_NOT_TESTED (SDK pagination/serialization/default side effects) |
| EC2 CreateVpc | Exact CIDR/run tags, create ID, pending->available and default dependent objects | S8 create_vpc/state; S6 resourceVPCCreate/wait | reviewed plan + state/API check | Native create-change projection; simulated API creation | UPSTREAM_SOURCE_VERIFIED; TERRAFORM_SCHEMA_VERIFIED (plan only); RUNTIME_NOT_TESTED |
| Provider supporting reads | DescribeVpcAttribute for DNS hostnames/support/network metrics; default ACL, main route table, default SG reads | S6 resourceVPCRead/resourceVPCFlatten; S8 corresponding handlers | Provider-driven inside apply/read; loopback EC2 endpoint | Source inspection plus actual Provider schema; no claim integrated mock executes these APIs | UPSTREAM_SOURCE_VERIFIED; RUNTIME_NOT_TESTED (eventual consistency, computed values, retry deadlines) |
| EC2 tag update | Provider tag interception uses CreateTags/DeleteTags; only Phase changes | S6 tags_interceptor.go/tags_gen.go; S8 create_tags/delete_tags | inventory update, api_owner | Schema-derived update fixture, independent tag verification/failure injection | UPSTREAM_SOURCE_VERIFIED; SIMULATED_ONLY; RUNTIME_NOT_TESTED |
| Create plan / apply | Exactly aws_vpc.proof; reviewed hash unchanged; create then capture State ID | S7 jsonplan; S6 create | inventory, apply_plan, plan_gate | Actual Native Mock create-change projection, synthetic outer plan and saved-file tamper tests | TERRAFORM_SCHEMA_VERIFIED (create projection); SIMULATED_ONLY; RUNTIME_NOT_TESTED (Apply) |
| Read / refresh-only | Saved refresh-only plan exit 0, exact ID/CIDR/run tags and no drift/deferred | S7 JSON plan; S6 read | execute, refresh_gate | Source-shaped refresh fixture, drift mutation | UPSTREAM_SOURCE_VERIFIED (format); SIMULATED_ONLY; RUNTIME_NOT_TESTED |
| Update plan / apply | Exact owned ID, only Phase tags change; independent updated tags | S7 plan format; S6/S8 tag behavior | plan_gate/update/api_owner | Synthetic update/before/after; partial-update recovery integration | UPSTREAM_SOURCE_VERIFIED; SIMULATED_ONLY; RUNTIME_NOT_TESTED |
| No-op plan | Exact single no-op change; no resource drift/deferred/error | S7 change actions/format and public no-op example | inventory(no-op), plan_gate | Source-shaped no-op; actual Native projection is create only | UPSTREAM_SOURCE_VERIFIED (JSON representation); SIMULATED_ONLY; RUNTIME_NOT_TESTED |
| Destroy plan / apply | Exact one owned delete; after=null, empty planned inventory; hash recheck | S7 JSON plan/destroy example; S6 resourceVPCDelete | destroy, plan_gate, apply_plan | Synthetic reviewed delete and failed-destroy/recovery tests | UPSTREAM_SOURCE_VERIFIED; SIMULATED_ONLY; RUNTIME_NOT_TESTED |
| Raw State / identity | Raw version 4/resources array; exact default-provider single aws_vpc.proof instance; no deposed/index/foreign output | S7 statefile version4 | state, state_id | Schema-shaped raw State fixtures + mutations, never formatted show JSON | UPSTREAM_SOURCE_VERIFIED (format); SIMULATED_ONLY; no new real raw State retained |
| Ownership / baseline | State/API ID, CIDR, run markers agree; no pre-existing changes/deletion | S8 API structures plus policy ownership boundary | api_owner/baseline_preserved | Independent baseline sentinel, duplicate ID/tag and mismatched State/API tests | SIMULATED_ONLY; RUNTIME_NOT_TESTED (actual Provider inventory) |
| DeleteVpc / NotFound | Delete only verified owned ID, State empty; exact DescribeVpcs InvalidVpcID.NotFound/254 | S8 delete/describe/state code; S5 CLI envelope | destroy, absence | Literal CLI fixture; malformed/embedded NotFound refusal | UPSTREAM_SOURCE_VERIFIED; SIMULATED_ONLY; RUNTIME_NOT_TESTED (external error serialization) |
| Partial failure recovery | Only one positively identified new ID; State must match; no-State API cleanup labeled separately | S6 partial create sets ID before waits; S8 delete; policy | recover/finish | Real Run orchestration with partial-create/update, ambiguity, failed Destroy and crash injection | UPSTREAM_SOURCE_VERIFIED (failure possibilities); SIMULATED_ONLY; unknown/tainted IDs remain FAIL |
| Independent resource cleanup | API absence + baseline unchanged + empty State; no attempt => NOT_TESTED | S8 and policy | finish/absence/evidence_gate | Auth failure prevents init/apply/delete; failed recovery never complete | SIMULATED_ONLY; historical Run resource cleanup NOT_TESTED; RUNTIME_NOT_TESTED |
| Process / material cleanup | Stop owned process, remove private Root/CA/credentials/State/Plans, separate receipts | S3 generated paths; Python subprocess/tempfile filesystem contracts | finish | Local temp filesystem; simulated process/kill/material failures, SIGTERM | REAL_RUN_VERIFIED (historical receipts); SIMULATED_ONLY; forced host loss/OOM not guaranteed |
| Host cleanup / complete evidence | Own image/container only, checked Docker results, complete receipts + SHA/Run required | Docker CLI contract and unchanged workflow reviewed in AUDIT.md | host_evidence / workflow cleanup | Existing actual Bash with fake Docker, corruption/OOM-exit/cleanup mutations | SIMULATED_ONLY (new orchestration); REAL_RUN_VERIFIED (historical host cleanup); live Docker not run here |

## Pinned source register

AWS sources below are release **v1.0.385**, commit
`813af480bf7f16d5418b64e4f5644a74a7da11c5`, not latest/main assumptions.

- **S1** [STS service.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/services/service-com-amazonaws-sts-awssecuritytokenservicev20110615/src/service.rs),
  blob `360b86ea65f621e19067df7b979dc28e9330f3a4`, lines 76-81 namespace,
  476-518 credential-dependent error translation, 530-582 routing/refusal,
  821-877 independent upstream regression cases (including no credential).
- **S2** [pre_dispatch.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/vendor/smithy-server-runtime/src/pre_dispatch.rs),
  blob `8c519d7f06dda714f8dc88227c3cd4de393f0c03`, 343 and 350-392:
  Unauthenticated HTTP 403, escaped ErrorResponse/Error/Type/Code/Message.
  [query_error_envelope.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/services/common/src/query_error_envelope.rs),
  blob `5b4531fc7e3b2af594d33e9334fb95d20073dfce`: optional sibling RequestId.
- **S3** [server lib.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/vendor/server/src/lib.rs),
  blob `cb6ba870cd5ddbee9d7c77237f16f988266d4e8c`, service_from_host,
  generated material and startup fields; unchanged startup audit in AUDIT.md.
- **S5** [AWS CLI 2.35.0 errorhandler.py](https://github.com/aws/aws-cli/blob/2.35.0/awscli/errorhandler.py),
  blob `e09d4c740220dc4d4532732db87c12e223d228a7`, ClientErrorHandler/RC 254.
  [AWS CLI 2.35.0 errorformat.py](https://github.com/aws/aws-cli/blob/2.35.0/awscli/errorformat.py),
  blob `3f7e01429df94c3a25fadeb963a6d57e10a05b2e`, `write_error()` `aws: [ERROR]: ` prefix.
  [botocore ClientError format](https://github.com/boto/botocore/blob/1.42.46/botocore/exceptions.py#L517),
  blob `294bbf4020cf94067b8637c0607c93ed707dcffc`, message/retry template;
  this is authoritative template evidence, not proof of the embedded CLI library
  version. Historical Run separately demonstrates exit/classification.
- **S6** [Provider 6.72.0 vpc_.go](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/vpc_.go),
  blob `e3ccfd730dec506c66842f185f0cc03a3d620157`, create/read/update/delete/flatten;
  [conns/config.go](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/conns/config.go)
  blob `5676e23745bcdb96f4a9ed402ce62c00e22d313d` restores configured validation.
  SDK base [v2.0.0-beta.76 aws_config.go](https://github.com/hashicorp/aws-sdk-go-base/blob/v2.0.0-beta.76/aws_config.go#L299)
  requires STS on the non-skip path. Provider tagging uses
  internal/provider/sdkv2/tags_interceptor.go (blob `ad5b2e1b48109a71d1287805243f122c110dc2cf`)
  and internal/service/ec2/tags_gen.go (blob `ae3e2e4bb90ac78d6874ea7974542258007814cd`).
- **S7** [Terraform 1.17.0 JSON plan](https://github.com/hashicorp/terraform/blob/v1.17.0/internal/command/jsonplan/plan.go),
  blob `fbefe31eeea0d6bd59f5644275120994951aacd9`; raw
  [statefile/version4.go](https://github.com/hashicorp/terraform/blob/v1.17.0/internal/states/statefile/version4.go),
  blob `13574c0e5b620e53676abb6447324a7c40cd3987`. Real Native Mock create
  projection and public no-op/destroy examples: tests/fixtures/README.md.
- **S8** EC2 [ops directory](https://github.com/aws/aws-emulator/tree/v1.0.385/services/service-com-amazonaws-ec2-amazonec2/src/ops):
  create_vpc `3eaa04d56e3235880ce6881754d2e7dca7291750`,
  describe_vpcs `ed60274bbbe39368c533e22ec95b862f6e4ce68e`,
  delete_vpc `f4f6f120644fff3cc59b70289a695a66248daa5c`,
  create_tags `ccb1a49541f0cf2a75565c13c7be83b4ff1af771`,
  delete_tags `b4ed08bf142b920474d3756cea18cf304cb9bc6f`,
  describe_vpc_attribute `f9c20d2b243d7cd4ae98f32e21c8232f2441e0bb`,
  describe_network_acls `79e56632a187e66f3e5123077d13492a92c4d682`,
  describe_route_tables `62cc0dc3dd2f8d4972c25f3bbf2dfc9003fd5aab`,
  describe_security_groups `c30388e9809697e304fae53aaac6ac43e6a47102`;
  [state.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/services/service-com-amazonaws-ec2-amazonec2/src/state.rs)
  blob `fe89d74d7d2c5e8000ccf98437ed85dde95131c3` and its VPC state modules.

## Acceptance boundary

The previous 51 method names remain, with twelve added STS/parser/integration
methods (63 total), including a negative control that restores the prior bug.
PASS means the specified Offline checks succeed; it does not demonstrate installed
AWS Provider and Emulator interoperability. A future separately Owner-authorized
merged-main run must still establish unsigned STS wire behavior, Provider account
validation and all supporting EC2 reads, real Plan/State representations after
Apply, update/no-op/destroy, independent absence and every cleanup stage.
Service serialization, computed fields, tag consistency, eventual consistency,
process timing, Provider retries, free capacity and abrupt runner/container loss
remain runtime risks. No milestone or future success guarantee is declared.
All 14 conditions, $0 attestations, isolation, strict TLS/authentication/account
and ownership guards, exact SHA, manual dispatch, readonly token and Full CI remain.
