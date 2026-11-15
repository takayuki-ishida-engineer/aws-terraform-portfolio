# Fixture provenance

`startup-1.0.385.json` is source-derived, not a new captured Emulator run. The
user reported nested fields in the failed v1.0.385 run. AWS release v1.0.385
commit `813af480bf7f16d5418b64e4f5644a74a7da11c5` confirms the event and fields:
[core/router/src/main.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/core/router/src/main.rs)
installs tracing-subscriber `.json()` without flattening;
[vendor/server/src/lib.rs](https://github.com/aws/aws-emulator/blob/v1.0.385/vendor/server/src/lib.rs)
lines 1296-1303 publish the endpoint/health/config/CA/truststore event. The actual
JSON formatter example and default nested `fields` layout are in
[tracing-subscriber 0.3.20 json.rs](https://github.com/tokio-rs/tracing/blob/tracing-subscriber-0.3.20/tracing-subscriber/src/fmt/format/json.rs),
blob `3ef0fcd653d42b68dc0397b75f060d004c5bc41b`. Timestamp/paths are synthetic.
A fixture event alone cannot pass readiness: strict generated-file, TLS/health,
process-alive and authentication checks are exercised separately.

`native-vpc-create-change.json` is the resource-change projection emitted by real
Terraform 1.17.0 `test -json -verbose`, command=plan, mock_provider AWS 6.72.0,
using the actual adapter in an external temporary Root. No Apply/Destroy or AWS
API ran. Only this public synthetic VPC change was retained; no Saved Plan, Raw
State, provider schema dump, secret or credential is included. Test envelopes use
Terraform's documented JSON structures from v1.17.0
[internal/command/jsonplan/plan.go](https://github.com/hashicorp/terraform/blob/v1.17.0/internal/command/jsonplan/plan.go)
(blob `fbefe31eeea0d6bd59f5644275120994951aacd9`, format 1.2). Public upstream
no-op/destroy plan examples were also reviewed. Update/state/API responses are
schema-based simulation, not new real Provider lifecycle evidence. Historical
VPC proof recorded Plan inventory/lifecycle summaries only; its raw plans/state
were not retained under policy and cannot establish new version compatibility.

`sts-1.0.385.json` is an independent source-derived service oracle, not captured
raw response material. Pinned STS service blob `360b86ea65f621e19067df7b979dc28e9330f3a4`
explicitly distinguishes held-key signature mismatch from unresolved-key
InvalidClientTokenId, including an unsigned request. The namespace/envelope comes
from that service and pre_dispatch blob `8c519d7f06dda714f8dc88227c3cd4de393f0c03`.
CLI envelopes use ClientError's documented template inside AWS CLI 2.35.0
`write_error()` (`aws: [ERROR]: ` prefix, errorformat.py blob
`3f7e01429df94c3a25fadeb963a6d57e10a05b2e`); messages are synthetic.
The separately labeled observed_run contains only allowlisted receipts read from
Run 43715108794 at 406b468c820ed7ed7db86c9d38b578184811453d: signature PASS and
unknown-key AUTH_UNEXPECTED_INVALID_TOKEN/254. The latter code is inferred from
the reviewed baseline classifier, not a retained raw HTTP/CLI response. Production
constants are not used to construct these expected results. CONTRACTS.md links
all upstream sources and distinguishes source, simulation and historical run evidence.
