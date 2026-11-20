# Step 2 emulator rehearsal harness

Rehearses a real DEV root in the official AWS Emulator under all fourteen
[mandatory controls](../../AGENTS.md#mandatory-official-aws-emulator-safety-controls).
Step 2 of the [step plan](../../docs/deployment-configuration.md#8-step-plan);
recorded runs are in [Step 2 emulator rehearsals](../../docs/step2-emulator-rehearsals.md).

Nothing here touches real AWS, an operational root or its State. Since the Owner
decision of 2026-11-20 the GitHub Actions workflow runs automatically on merged
`main`; local runs still need the Owner's authorization.

The current scenario is the network root (the real `vpc` module) with its committed
values. `no-interface-endpoints` leaves the interface endpoints out. The `full`
scenario stops at create because of an emulator gap; see the
[rehearsal record](../../docs/step2-emulator-rehearsals.md).

## Where runs happen

| Mode | Use | Evidence |
| --- | --- | --- |
| **GitHub Actions** ([`aws-emulator-rehearsal.yml`](../../.github/workflows/aws-emulator-rehearsal.yml)): automatic on every push to `main` that changes `infra/` or the rehearsal code, or dispatched by the Owner | Formal runs | Each run's log (gate rows) and job summary on GitHub, the README badge, and milestone records in `docs/step2-emulator-rehearsals.md` with the run link. Logs expire, so the record keeps the summary |
| Local (`launch.sh`) | Preliminary or diagnostic runs | Only the record in the docs; no third-party log |

Every push and pull request runs `test_rehearse.py` offline in the
`AWS Emulator offline contracts` workflow. That workflow never starts the
emulator.

## Files

| File | Role |
| --- | --- |
| `prepare.py` | Host step with network. Runs only locally or in the rehearsal workflow on `main` (push or the Owner's dispatch); in Actions it first checks the run (main, the Owner, public visibility, first attempt, checked-out SHA), a standard runner with enough CPU, memory and disk, and a local Docker daemon. It then: downloads the artifacts pinned in [`versions.json`](../emulator-verification/versions.json); checks SHA-256 and the publisher GPG fingerprints with the repository's own verifier; extracts them into `STEP2_BASE` (no system install); builds the locked AWS provider mirror; records the public STS and EC2 probe addresses. With `--docker-context` it also assembles the image context and hashes every file in it |
| `Dockerfile` | Temporary local image on the same digest-pinned Ubuntu as the representative workflow. It checks the context hashes, installs the tools under `/opt/step2-tools` and runs `rehearse.py` as uid 1000. Never pushed |
| `launch.sh` | Local mode. Stages the tools and the network root and `vpc` module from `TESTED_SHA` (`git archive`). Starts `rehearse.py` in a fresh network and mount namespace on a private tmpfs, as uid 1000 with no capabilities and `no_new_privs`. Refused in CI |
| `rehearse.py` | The run inside the isolated environment: isolation, startup, authentication, the disposable root, the lifecycle, independent API checks, recovery and cleanup. stdout carries only non-secret gate rows, ending with a `summary-record` row |
| `summarize.py` | Turns the gate rows into the job summary: the CI run link, tested SHA, versions, the 14 controls, the lifecycle operations and the cleanup receipts. Exits non-zero unless everything is PASS |
| `workflow_contract.py` | Static contract of the workflow (push to `main` on exact paths or the Owner's dispatch only, read-only token, standard runner, run gate before checkout, pinned credential-free checkout, no secrets, artifacts, caches or pushes, exact container isolation flags) |
| `test_rehearse.py` | Offline negative and mutation tests of the plan, refresh, context, summary and workflow gates |

## Controls

| # | How the harness meets it |
| --- | --- |
| 1 | Pinned emulator DEB, AWS CLI and Terraform, SHA-256 and GPG publisher fingerprint verified; context hashes checked during the image build; versions checked again inside the isolated environment |
| 2 | `--bind 127.0.0.1 --port 9297`; the startup record must name exactly `https://127.0.0.1:9297` |
| 3 | Emulator-generated credentials in a fresh tmpfs home, `--auth on`. Signed STS must succeed; a changed secret (`SignatureDoesNotMatch`), a changed key (`InvalidClientTokenId`) and an unsigned request must be rejected |
| 4 | Generated CA with hostname checks; the system trust store must reject the emulator certificate |
| 5 | `--telemetry off` and `EMULATOR_TELEMETRY=off`, with no external route |
| 6 | Actions: `docker run --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000` with tmpfs only and no mounts. Local: `unshare --net --mount`. Either way the harness requires only `lo`, every IPv4 and IPv6 route on `lo` and loopback, a namespace different from the host's, zero capabilities and `no_new_privs` |
| 7 | Direct TCP to the pre-resolved public STS and EC2 addresses must fail with `ENETUNREACH` or `EHOSTUNREACH` |
| 8 | Signed `GetCallerIdentity` must return account `000000000000` and `arn:aws:iam::000000000000:user/emulator` |
| 9 | Disposable override sets the EC2 and STS endpoints to `https://127.0.0.1:9297`, the emulator CA and `allowed_account_ids = ["000000000000"]`; every plan is rejected unless it shows exactly that |
| 10 | Disposable copy on the tmpfs with local State; `init -lockfile=readonly` from the local provider mirror; State must start empty |
| 11 | Every saved plan is inspected before apply: the exact reviewed resource inventory and actions, the provider guard, the run tags and, for updates, tag-only changes. The plan hash is checked again before apply |
| 12 | Every State ID must exist in the API with the run's `VerificationRun` tag and must not be in the baseline; any other new object must be an AWS side effect inside the owned VPC. Destroy targets must equal the State IDs |
| 13 | Independent `describe-*` checks after create, update and destroy; the baseline must be unchanged |
| 14 | Destroy uses only the reviewed saved destroy plan. On failure, recovery destroys only State resources with the run tag and verifies absence. The emulator is stopped, the tmpfs (credentials, CA, State, plans, logs) is emptied, and the host removes the container, image and context |

## Formal runs in GitHub Actions

Automatic runs need no action: merging a change to `infra/` or the rehearsal code
into `main` starts one (Owner decision 2026-11-20, no per-run billing attestation).
The run gate still requires `main`, the Owner as actor, a public repository, the
first attempt, a standard runner with enough capacity and a local Docker daemon.

The Owner can also start a run manually: Actions → **AWS Emulator Step 2
rehearsal** → Run workflow on `main`, choosing `scenario` `no-interface-endpoints`
or `full`. The `full` scenario stops at create on the known security group gap.

Read the job summary. A run that changes a root's status (first PASS, new gap or
failure, fix) is recorded in
[Step 2 emulator rehearsals](../../docs/step2-emulator-rehearsals.md) with its run link.

## Local run (Owner-authorized only)

The session's network policy must allow `downloads.aws.com`, which needs the Owner's
approval. Run as root, from the repository root:

```bash
STEP2_BASE=<directory outside the repository> python3 scripts/emulator-rehearsal/prepare.py
```

```bash
STEP2_BASE=<same directory> TESTED_SHA=<merged main SHA> SCENARIO=no-interface-endpoints bash scripts/emulator-rehearsal/launch.sh
```

`STEP2_PROVIDER_MIRROR` can point to an existing filesystem mirror with the locked
`aws` 6.72.0 package when the Terraform Registry is not reachable. The summary JSON
(non-secret) is copied to `$STEP2_BASE/evidence/`.

Emulator success is never evidence of real AWS behavior, IAM enforcement,
networking, cost or availability.
