# Comprehensive lifecycle preflight audit

Base main: `e1c7b4e2faec4215ab82e8bd60553196a2d4d125`. Failed real Run:
[43703888134](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43703888134).
This audit implements source/Offline changes only. No Docker, Emulator, real
Provider lifecycle, Apply/Destroy, manual dispatch or real AWS API is run here.
Success of a future lifecycle **cannot be guaranteed** by these checks.

## Classification and disposition

| Classification | Finding / evidence | Disposition / regression evidence |
| --- | --- | --- |
| VERIFIED PASS | Run passed Owner/SHA/capacity, signed fixed packages, CLI/Terraform/provider preparation and Docker build | prepare.py, GPG verification, Dockerfile, package Versions/hashes/key and operational locks are byte-identical |
| VERIFIED PASS | Run emitted control-6/7 PASS and exact tool version checks before startup BLOCKED | Existing network-none/no capabilities/read-only/nonroot flags, namespace/route/TCP-denial and tool checks preserved |
| CONFIRMED DEFECT | Top-level message lookup cannot consume v1.0.385 tracing-subscriber nested fields | startup_record reads fields.message/endpoint/health/material paths; source-derived fixture, nested/invalid/fake-ready mutations |
| CONFIRMED DEFECT | Startup and other errors collapsed to generic execution/BLOCKED | Fixed allowlisted diagnostics for timeout, process exit, JSON, material, TLS, authentication, command and cleanup failures; no raw logs/exception strings |
| CONFIRMED DEFECT | Ready event was not a retried health acceptance; CA path/credential permissions checks were incomplete | Live process + strict CA/hostname HTTPS health 200/ok + untrusted-CA rejection; regular UID-owned 0600 canonical files, no symlink aliases; no Ready PASS beforehand |
| PROBABLE DEFECT | An unsigned EC2 request is not a universal 403 authentication proof; official documentation permits UnknownService 404 | Successful signed CLI STS identity, wrong secret SignatureDoesNotMatch and unknown key AccessDenied required; explicitly routed unsigned STS 403/InvalidClientTokenId; 404 is rejected with an explicit AUTH_UNSIGNED_UNRESOLVED receipt; unexpected rejection/acceptance is classified with fixed per-probe diagnostics, never raw CLI error text. Healthy and failed-auth orchestration covered; real API behavior remains NOT_TESTED |
| CONFIRMED DEFECT | Disposable empty State was implicit; Refresh/no-op checked exit only | Explicit initial empty State receipt; saved Refresh JSON validates exact planned resource/ID/tags and no drift; no-op saved Plan reviewed; real Terraform Native Mock change projection plus official JSON implementation |
| CONFIRMED DEFECT | Wrong JSON State shape could appear empty; indexed/deposed instances and duplicate API tags could masquerade as exact ownership | Require raw State resources array/no unexpected outputs/provider; reject ambiguous instance addresses and duplicate tags; exact State/API/Plan ID and run-marker checks preserved |
| PROBABLE DEFECT | Tag list ordering could falsely change the baseline | Normalize only the API Tags map ordering, rejecting duplicate keys; reordered baseline regression passes |
| PROBABLE DEFECT | Default provider retries could consume the outer command budget | Adapter max_retries=2 is supported by the actual 6.72.0 schema; CLI connect/read timeouts and two standard attempts; outer subprocess timeout remains 120s. No unsupported VPC timeout blocks added |
| CONFIRMED DEFECT | Startup failure emitted resource-cleanup/PASS and control-14/PASS despite no lifecycle (visible in failed Run) | No creation attempt => resource cleanup NOT_TESTED; material/process/resource cleanup recorded separately; control 14 requires confirmed resource and material/process cleanup |
| CONFIRMED DEFECT | Recovery could overwrite failed Destroy operation receipts and produce a completion marker after failed execution | Recovery receipts are separate; lifecycle_ok and failure latch required for completion; partial Apply/API cleanup and successful destroy-retry cannot become lifecycle PASS |
| CONFIRMED DEFECT | Cleanup exception paths could skip material removal; SIGTERM could lose its diagnostic inside command handling | Stop/kill errors do not prevent material removal; INTERRUPTED preserved and previous signal handler restored; process/kill/material failures and SIGTERM tested |
| PROBABLE DEFECT | Docker inspect failure was indistinguishable from absence; Summary trusted a completion token without complete receipt/identity validation | Exact owned-name query failures fail host cleanup; explicit host receipt; Summary requires all 14 controls/operations, SHA/Run identity, execution success and final host-cleanup receipt; corruption/duplicates/failed history reject |
| CONFIRMED DEFECT | Offloading Summary to a script would fail when checkout was skipped | Inline fixed CHECKOUT_UNAVAILABLE fallback; tested with missing checkout; existing Owner/SHA/$0 consent logic unchanged |
| VERIFIED PASS (source) | Provider 6.72.0 restores credential validation before GetAwsAccountIDAndPartition; SDK base beta.76 requires STS when validation is on | EC2/STS loopback endpoints and allowed_account_ids remain. IAM fallback occurs only on the prohibited skip-validation path, so no speculative IAM endpoint or skip was added |
| RUNTIME-ONLY RISK | Installed Provider API/read/update consistency, STS error wording/routing, startup timing, capacity, actual SIGKILL/OOM/runner cancellation | NOT_TESTED here; strict guards and safe diagnostics remain, no security fallback or compatibility PASS |

## Evidence and test boundaries

The original 34 test methods remain. Seventeen audit methods bring the total to
51, with multiple fault/mutation subcases. Only transport/process/OS responses are
simulated in the integrated model: the real Run constructor, setup, execute,
finish, command construction, filesystem/Plan hashing, gate logic and evidence
coordination execute together. Actual tools called by the model are simulated;
no AWS/Emulator/Docker/resource operation occurs.

The normal sequence is asserted independently: initial empty State -> Create
Plan/inventory/hash -> Apply -> State/API ID -> Refresh -> tag Update Plan/Apply
-> independent tags -> no-op reviewed Plan -> Destroy Plan/Apply -> State empty
-> API absence/original inventory -> material cleanup. Existing saved-plan
integrity negative tests remain. Plan configuration/resource_changes/planned_values,
immutable IDs/CIDR/run tags and delete after=null are checked. During verified
owned-resource recovery, only an exact create-to-updated Phase-tag drift is
accepted; arbitrary drift, different ID, additional resource or deposed/indexed
State is refused. Partial resources with insufficient ownership evidence remain
FAIL/BLOCKED rather than being deleted blindly.

Failures injected include malformed/absent startup events, early process exit,
wrong generated path/mode/symlink, invalid CA, unhealthy endpoint, unexpected
system trust, disabled/ineffective auth, unsigned UnknownService, wrong STS
identity, Provider init/initial State/inventory failure, partial create with and
without State, partial update, ID mismatch, refresh drift, Destroy failure and
successful recovery, process crash, command timeout, SIGTERM, process kill and
material cleanup failure. All fail the lifecycle result even when safe recovery
succeeds. Resource absence checks require the exact CLI error code/operation;
shutdown alone is never a Destroy receipt.

A separate real Python loopback HTTPS server verifies production HTTP transport
with an ephemeral CA/server certificate: trusted CA succeeds, system trust and
wrong hostname fail, malformed CA fails, redirects cannot reach outside hosts.
This is local TLS evidence, not Emulator TLS/API evidence. Test certificates and
private keys are removed. Existing real temporary-GPG-key tests are unchanged.

The actual workflow Bash is exercised with a temporary **fake** docker executable
(no real Docker startup), including normal exit, exit 137, daemon query failure,
container removal failure and image removal failure. Exit 137 is not asserted to
prove OOM; it may also be SIGKILL. Missing/truncated lifecycle receipts and host
cleanup failure cannot make Summary succeed. Workflow mutations cover runner/
permissions/events, capabilities, mounts, environment forwarding (including compact
flags), networking, swap/PID bounds, cleanup bypass and fake Summary outcomes.
Secret sentinels in command outputs, exceptions, material and corrupt reports must
never appear in stdout/stderr or Summary. No Raw State/Plan/private key/artifact is
published. Fixtures and synthetic receipts are never runtime success evidence.

## Sources and independently obtained format evidence

- AWS Emulator [release v1.0.385](https://github.com/aws/aws-emulator/tree/v1.0.385),
  commit `813af480bf7f16d5418b64e4f5644a74a7da11c5`: router main installs `.json()`;
  server lib blob `cb6ba870cd5ddbee9d7c77237f16f988266d4e8c` publishes the event;
  request_authentication.rs blob `51fd3f96bb3b0ebcdd5b670c824cf0e3bbf555a1` defines
  the signature/credential errors; server service_from_host supports explicit STS routing.
- [Official CLI output/authentication documentation](https://docs.aws.amazon.com/emulator/latest/userguide/cli-reference.html)
  and [health/CA instructions](https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html).
  Raw startup output from the failed container was not retained; the fixture is
  explicitly source-derived, with provenance in [fixtures/README.md](tests/fixtures/README.md).
- Terraform 1.17.0 Native Mock command=plan actually executed against the adapter
  in an external temporary local-backend Root, with readonly approved lock and
  AWS Provider 6.72.0. Its real resource-change projection is retained as public
  synthetic fixture; no Apply/Destroy ran. The test renderer is not the entire
  saved-Plan envelope. Envelope/state simulations follow the upstream JSON
  implementation and public no-op/destroy examples, not fabricated live evidence.
- Provider schema was actually queried with installed 6.72.0. It supports
  max_retries and does **not** expose VPC timeout blocks. Source:
  [config.go v6.72.0](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/conns/config.go),
  blob `5676e23745bcdb96f4a9ed402ce62c00e22d313d` and
  [SDK base v2.0.0-beta.76](https://github.com/hashicorp/aws-sdk-go-base/blob/v2.0.0-beta.76/aws_config.go).
- Terraform raw State v4 writer source `internal/states/statefile/version4.go`
  at v1.17.0, blob `13574c0e5b620e53676abb6447324a7c40cd3987`: resources are
  initialized as an array and outputs as a map; formatted show JSON is not raw State.
- Historical VPC proof has inventory/lifecycle summaries, not retained raw plans or
  State; it cannot validate this new version/HEAD's full Provider behavior.

## Preserved boundaries and remaining acceptance work

No changes to required Full CI, Offline-contract workflow triggers, AGENTS.md,
MASTER POLICY, package/CLI/Terraform/provider versions, Lockfiles, Dockerfile,
Runner label, capacity minima, 14 conditions, Owner attestation/$0 Budgets, token
permissions or network/capability/readonly/tmpfs limits. Manual workflow changes
are confined to host cleanup/evidence. Operational infra is untouched.

A future separately Owner-authorized merged-main run must still establish startup,
real generated material/TLS/authentication/STS, Provider configuration and all VPC
API operations, independent absence and all cleanup receipts. No exact live
Provider interoperability or complete cleanup under forced runner destruction can
be guaranteed by source/Offline tests. Ambiguous/tainted partial State, service
incompatibility, API eventual consistency, insufficient free memory/disk/time,
clock skew or abrupt container/host loss may remain BLOCKED/FAIL. Never waive
identity, TLS, isolation, ownership, cost or cleanup to force success. Billing is
Owner-attested, not API-audited. No PORTFOLIO COMPLETE or EMULATOR DEMONSTRATED
milestone is declared by this PR.
