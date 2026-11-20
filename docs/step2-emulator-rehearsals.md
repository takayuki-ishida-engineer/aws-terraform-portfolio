# Step 2 emulator rehearsals

Step 2 of the [step plan](deployment-configuration.md#8-step-plan): rehearse the
real DEV roots in the official AWS Emulator under all fourteen
[mandatory controls](../AGENTS.md#mandatory-official-aws-emulator-safety-controls),
then an end-to-end apply and destroy. Automatic runs on `main` stay within the
limited standing authorization of Master Policy v14.4 §13.2: only the reviewed
scenarios in `all` of an Owner merge-approved pull request. Every other run (manual
dispatch, local or cloud run, unapproved scenario) needs the Owner's approval each
time ([AGENTS.md](../AGENTS.md#emulator-verification-workflow-and-evidence)).
The harness and its controls are described in
[`scripts/emulator-rehearsal`](../scripts/emulator-rehearsal/README.md).

Emulator results are never evidence of real AWS deployment, IAM enforcement,
networking, DNS, cost, availability or recovery. Formal acceptance of each
rehearsal needs independent review and an Owner decision. CORE PORTFOLIO
COMPLETE and PORTFOLIO COMPLETE remain undeclared.

## How to read the evidence

| Where | What it shows |
| --- | --- |
| [`aws-emulator-rehearsal.yml`](../.github/workflows/aws-emulator-rehearsal.yml) | The exact steps every formal run executes: the run gate (main, the Owner, a public repository), verified downloads, an isolated `--network none` container, strict host cleanup and the job summary |
| [Workflow runs](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/workflows/aws-emulator-rehearsal.yml) and the README badge | Every formal run's log, with every gate row, and its job summary. GitHub deletes logs, job summaries and run records after its retention period: at most 90 days on a public repository, with the actual setting confirmed by the Owner. The badge shows only the latest automatic run. Neither the badge, a run URL nor a job summary is permanent evidence |
| `docs/evidence/emulator-runs/` (v14.4 §13.4, not yet implemented) | The evidence ledger. Every formal run gets a sanitized entry per Run ID and Attempt, whether it passed, failed or stopped early. Each entry records the SHA, versions, roots and resource addresses, the 14 controls, per-operation results, independent API checks, cleanup, failure cause, untested scope and residual risk. The ledger is a third-party-traceable audit record, not a copy of the full logs. It arrives with `harvest.py` and reconciliation in a dedicated pull request; entries for the runs below are backfilled there |
| This page | The human-readable narrative: the formal run list, per-root status, emulator gaps, untested items and residual risk. Local container runs are recorded here as LOCAL PRELIMINARY, separately from formal runs |

Until the ledger exists, this page lists every formal run. A formal run never
counts as success unless its record shows it. A run that is late or missing from
the record, or whose evidence cannot be retrieved, is recorded as EVIDENCE_GAP or
INSUFFICIENT_EVIDENCE, never inferred.

## Formal runs (GitHub Actions)

Reconciled on 2026-11-20 against the Actions run list of
`aws-emulator-rehearsal.yml`: 3 runs, each on attempt 1, all on `main`, all
started by the Owner (actor and triggering actor).

| Run | Trigger | Head SHA | Scenario | Result |
| --- | --- | --- | --- | --- |
| [44279371023](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44279371023) (attempt 1, 2026-11-18 09:48 UTC) | Manual dispatch | `0a16e486dd37c40358a122aef47a215a8c6a4ab7` | n/a | **BLOCKED**: stopped at the billing confirmation gate (`Require owner cost confirmation and reviewed main SHA`) before checkout. Every later step was skipped and no resource was created. GitHub shows the run as `failure`. No `summary-record` was produced, so no control or lifecycle result exists |
| [44279751946](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44279751946) (attempt 1, 2026-11-18 09:50 UTC) | Manual dispatch with per-run billing attestation | `0a16e486dd37c40358a122aef47a215a8c6a4ab7` | Network root without interface endpoints (16 resources) | **PASS** (network only): all 14 controls, all 13 lifecycle operations and every cleanup receipt ([details](#formal-run-1-network-root-without-interface-endpoints)) |
| [44664010985](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44664010985) (attempt 1, 2026-11-20 02:54 UTC) | Automatic, on the push of PR #74 to `main` | `70a5868272c19d0d0803e2eabd3fa92ce781d32b` | The same network root scenario (16 resources), with the harness on that commit | **PASS** (network only): the job concluded `success`. `summarize.py` exits non-zero unless every control, lifecycle operation and cleanup receipt is PASS. Its field-level entry is part of the ledger backfill |

The representative workflow's accepted run
[43791639228](portfolio-verification-policy.md#representative-emulator-run-43791639228)
(disposable `aws_vpc.proof` only) is recorded in the verification policy. The
ledger pull request checks it against the Actions history and registers it, or
records why it cannot.

### Status per root (v14.4 §13.3 snapshot)

| Root | Status |
| --- | --- |
| network (without interface endpoints) | Formal PASS in runs 44279751946 and 44664010985 |
| network with interface endpoints (`network-full`) | EMULATOR_COMPATIBILITY_BLOCKED: [default egress revoke gap](#emulator-fidelity-gap-default-egress-rule-revoke) |
| api | Formal NOT_TESTED. Only a local preliminary report exists, in unmerged PR #75 |
| tfstate | EMULATOR_COMPATIBILITY_BLOCKED: the provider reads bucket tags through S3 Control, whose account-ID host prefix the emulator certificate cannot serve under strict TLS. In the local preliminary trial (PR #75), Terraform resource cleanup was FAIL. Discarding emulator memory at shutdown is not a successful Terraform destroy |
| serverless-api | NOT_TESTED. The same S3 Control gap is expected but has not been run |
| platform, developer-access | NOT_TESTED in Actions. The security group gap is expected; EKS and AMI paths are untested |

A known gap that keeps a root out of scope is not a formal FAIL measured in a
run. Real AWS IAM, networking, EKS, cost, deletion and availability are not
verified for any root. PR #75's `all` covers only `network` and `api`. It is not
evidence for the other roots.

### Formal run 1: network root without interface endpoints

| Item | Value |
| --- | --- |
| Executed by | GitHub Actions run [44279751946](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44279751946), attempt 1, job `rehearsal`, workflow `.github/workflows/aws-emulator-rehearsal.yml@refs/heads/main`, GitHub-hosted `ubuntu-24.04` |
| Dispatched | By the Owner, 2026-11-18 09:50:55 UTC (job 09:50:58–09:54:01 UTC). The Owner's billing attestation was given at `2026-11-18T18:49:53+09:00` (Owner-attested; not API-audited) |
| Tested SHA | `0a16e486dd37c40358a122aef47a215a8c6a4ab7`: `infra/services/dev/ca-central-1/network` and `infra/modules/vpc` from that commit |
| Scenario | Network root (real `vpc` module) with its committed values and `interface_endpoints = null`; synthetic `project = "step2"` and account `000000000000` |
| Harness | `scripts/emulator-rehearsal/rehearse.py`, SHA-256 `58a1a15405c945ce23d7e8f04d70df0f38f772bb6e9a32e97c9df34592e4109c` |
| Versions | Emulator 1.0.385, Terraform 1.17.0, AWS provider 6.72.0, AWS CLI 2.35.0; all hash and signature verified in the preparation step; provider mirror built from the committed lock |
| Isolation | Temporary local image; `docker run --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000`, tmpfs only. Public STS and EC2 probes gave `ENETUNREACH` |

Results:

| Area | Result |
| --- | --- |
| Controls 1–14 | All PASS |
| Lifecycle | All PASS: plan (16 resources), create, independent API identity, read (reviewed EIP and route-table convergence, then a clean refresh), tag-only update plan, update, API update check, no-op plan, reviewed destroy plan, destroy, empty State, API absence and unchanged baseline |
| Authentication | Changed secret rejected with `SignatureDoesNotMatch`; changed key rejected with `InvalidClientTokenId`; unsigned request rejected |
| Security group probe | The provider-form revoke (protocol `-1`, ports `0`) returned `InvalidPermission.NotFound`; the same revoke without ports was accepted. This confirms the gap described below |
| Interface endpoint probe | Direct API `CreateVpcEndpoint` (`sts`, private DNS) returned `available` with 3 DNS entries; deletion verified |
| Cleanup | Resources, material (credentials, CA, State, plans and logs on tmpfs), emulator process, and host (container, image, context): all PASS |
| Not used | AWS credentials, secrets, artifacts, caches, registry pushes |

Status: every operation in this scenario was measured PASS in a third-party-visible
CI run. Accepting it as AWS EMULATOR DEMONSTRATED for this scenario needs
independent review and an Owner decision; the AGENTS.md status statements are
unchanged. The security group paths, the 8 interface endpoints through Terraform,
the `full` scenario and the other roots remain NOT_TESTED (see below).

## Preliminary rehearsal 1: network root (2026-11-18, Claude Code container) — LOCAL PRELIMINARY

This preliminary local run shaped the harness and found the security group gap.
It is not a CI run: no third party can inspect its log, and the formal record
comes from GitHub Actions above.

**Authorization:** the Owner's instruction of 2026-11-18 to start the emulator
verification once everything up to Step 2 was in order. The Owner also approved,
through the session's environment approval prompt, a personal cloud environment
that allows only `downloads.aws.com` for the pinned emulator package. No AWS API
host and no credential were added.

### Tested code and tools

| Item | Value |
| --- | --- |
| Tested SHA (Terraform source) | `ec3519069ef0fa710e94012ba9db06578e15cf13` (main after PR #70): `infra/services/dev/ca-central-1/network` and `infra/modules/vpc`, copied with `git archive` |
| Harness | `scripts/emulator-rehearsal/rehearse.py`, SHA-256 `0769389771cb7adeea5507ab3be08e5dca0e514ebc36b1decb169c08b58709dc`, as committed in PR #71 |
| Emulator | 1.0.385 (`1.0.385-1` amd64 DEB, SHA-256 `5344b39e…3f5`, publisher `98BCF336A3BE53B734E967C52E5BF49BD940F624`), as pinned in `versions.json` |
| Terraform / AWS provider / AWS CLI | 1.17.0 (SHA-256 verified) / 6.72.0 (committed network lock, `init -lockfile=readonly` from a local mirror) / 2.35.0 (SHA-256 and GPG verified) |
| Execution environment | Claude Code cloud container. The emulator, Terraform and the AWS CLI ran in a fresh `unshare --net --mount` namespace, as uid 1000 with no capabilities and `no_new_privs`, on a namespace-private tmpfs. No Docker and no GitHub Actions minutes were used for the lifecycle |
| Inputs | Committed `terraform.tfvars` of the network root, with `project = "step2"`, `aws_account_id = "000000000000"` and the run tags `VerificationRun` and `Phase` in a disposable tfvars file. The operational root and its State were not touched |

### Results

| Run | Scenario | Resources | Result |
| --- | --- | --- | --- |
| `20261118080527-1` | A: committed values without `interface_endpoints` | 16: VPC, 4 subnets, Internet gateway, public and 2 per-AZ private route tables, 4 associations, NAT EIP, NAT gateway, NAT route | **Every operation PASS, all 14 controls PASS** |
| `20261118080742-1` | B: committed values (full) | 26: scenario A plus the endpoint security group, its HTTPS rule and 8 interface endpoints | Plan PASS. Create **BLOCKED by an emulator fidelity gap** (below). Recovery destroyed the 17 created resources with a reviewed destroy plan and verified absence; controls 1–11 and 14 PASS |

Scenario A operations, in order:

| Operation | Result | Evidence |
| --- | --- | --- |
| Isolation (controls 6, 7) | PASS | Only `lo`, loopback routes only, separate namespace; public STS and EC2 addresses `ENETUNREACH` |
| Startup, TLS, telemetry (1, 2, 4, 5) | PASS | Exact `https://127.0.0.1:9297`; CA-verified health; the system trust store rejects the emulator certificate |
| Authentication (3, 8) | PASS | Signed STS gives `000000000000` / `user/emulator`; a changed secret gives `SignatureDoesNotMatch`; a changed key gives `InvalidClientTokenId`; an unsigned request is rejected |
| Provider guard, disposable root (9, 10) | PASS | Override with loopback EC2 and STS endpoints, the emulator CA and `allowed_account_ids = ["000000000000"]`; readonly lock; empty State |
| Plan (11) | PASS | Exactly the 16 reviewed addresses, all `create`, run and default tags on every taggable resource; plan hash checked again before apply |
| Create, API identity (12) | PASS | All 16 State IDs found by `describe-*` with the run tag (where taggable) and not in the baseline; every other new object belonged to the owned VPC (AWS side effects of creating it, such as its main route table and default security group) |
| Read (refresh) | PASS | First refresh: only the reviewed computed fields changed, matching the API. The EIP's association, network interface and private IP came from the NAT gateway. The private route table's computed `route` list came from the separate `aws_route`. Real AWS shows the same. After applying the refresh, a second refresh shows no change |
| Update | PASS | Plan: `update` on the 11 taggable resources, `no-op` on the 4 associations and the route, tags only; the API shows `Phase = updated` |
| No-op plan | PASS | Every resource `no-op` |
| Destroy (13) | PASS | Reviewed saved destroy plan, targets equal to the State IDs; State empty; every owned ID absent from the API; the pre-existing default VPC, subnets, route table, security group and rules unchanged |
| Cleanup (14) | PASS | Emulator stopped; tmpfs with credentials, CA, State, plans and logs emptied, then unmounted with the namespace; no emulator process left on the host |

### Emulator fidelity gap: default egress rule revoke

The AWS provider creates `aws_security_group` and then revokes the default IPv4
egress rule with `IpProtocol=-1, FromPort=0, ToPort=0, CidrIp=0.0.0.0/0`. AWS
treats that as the default rule. Emulator 1.0.385 stores the default rule with no
ports and answers that request with HTTP 400 `InvalidPermission.NotFound`.

A direct API probe in run `20261118080527-1` (an owned, tagged probe group in the
owned VPC, deleted afterwards) recorded:
- `CreateSecurityGroup` adds one egress rule: `-1`, `FromPort` and `ToPort` null, `0.0.0.0/0`;
- the provider-form revoke with ports 0: `InvalidPermission.NotFound`;
- the same revoke without ports: accepted, after which no egress rule remains.

This is not a Terraform defect, and the module is not changed for the emulator.
With this emulator and provider pair, **any root that creates an
`aws_security_group` cannot complete create in the emulator**. That covers the
network root's interface endpoints, and most likely the platform (EKS) and
developer-access roots.

The same probe also exercised one interface endpoint directly through the API
(`com.amazonaws.ca-central-1.sts`, private DNS, one subnet, the probe group). It
returned `available` with 3 DNS entries, and its deletion was verified. That is an
API probe, not a Terraform result.

### Not tested and residual risk

| Item | Status |
| --- | --- |
| `aws_security_group.endpoints`, its ingress rule and the 8 interface endpoints through Terraform | NOT_TESTED (blocked by the gap above) |
| Packet forwarding, NAT, routing, DNS resolution, endpoint reachability | NOT_TESTED; the emulator models API state only |
| Real AWS behavior, quotas, costs, IAM | NOT_TESTED; no real AWS access |
| Other roots (tfstate, platform, developer-access, serverless-api, api) and the end-to-end apply and destroy | NOT_TESTED; each needs its own Owner authorization |

Other residual points:
- The run used a local cloud container, not GitHub Actions. Its evidence is the
  gate output summarized here; raw State, plans, credentials and logs were never
  kept or uploaded. The formal runs above replace it as evidence.
- The refresh allowlist is a reviewed judgment that this computed-field
  convergence is normal. It is covered by the offline mutation tests in
  `test_rehearse.py`.
- Options for the security group gap:
  1. accept NOT_TESTED for the security-group paths;
  2. retest with a later emulator release, which needs a reviewed
     `versions.json` update;
  3. report the gap to the emulator maintainers.

  The production modules stay unchanged in every case.
