# Step 2 emulator rehearsal harness

Rehearses a real DEV root in the official AWS Emulator under all fourteen
[mandatory controls](../../AGENTS.md#mandatory-official-aws-emulator-safety-controls).
Step 2 of the [step plan](../../docs/deployment-configuration.md#8-step-plan);
recorded runs are in [Step 2 emulator rehearsals](../../docs/step2-emulator-rehearsals.md).

**Each run needs its own Owner authorization.** The scripts refuse to start in CI
and never touch real AWS, an operational root or its State. GitHub Actions runs
only `test_rehearse.py`, offline.

The current scenario is the network root (the real `vpc` module) with its committed
values. Interface endpoints can be left out with `SCENARIO=no-interface-endpoints`.
The full scenario stops at create because of an emulator gap; see the
[rehearsal record](../../docs/step2-emulator-rehearsals.md).

## Files

| File | Role |
| --- | --- |
| `prepare.py` | Host step with network. Downloads the artifacts pinned in [`versions.json`](../emulator-verification/versions.json), checks SHA-256 and the publisher GPG fingerprints with the repository's own verifier, extracts them into `STEP2_BASE` (no system install) and records the public STS and EC2 probe addresses |
| `launch.sh` | Stages the public tools under `/opt/step2-tools` and copies the network root and `vpc` module from `TESTED_SHA` (`git archive`). Starts `rehearse.py` in a fresh network and mount namespace on a private tmpfs, as uid 1000 with no capabilities and `no_new_privs`, then checks that the tmpfs and the emulator process are gone |
| `rehearse.py` | The run inside the namespace: isolation, startup, authentication, the disposable root, the lifecycle, independent API checks, recovery and cleanup. stdout carries only gate and status rows |
| `test_rehearse.py` | Offline negative and mutation tests of the plan inspection and refresh convergence gates |

## Controls

| # | How the harness meets it |
| --- | --- |
| 1 | Pinned emulator DEB, AWS CLI and Terraform, SHA-256 and GPG publisher fingerprint verified; version checked again inside the namespace |
| 2 | `--bind 127.0.0.1 --port 9297`; the startup record must name exactly `https://127.0.0.1:9297` |
| 3 | Emulator-generated credentials in a fresh tmpfs home, `--auth on`. Signed STS must succeed; a changed secret (`SignatureDoesNotMatch`), a changed key (`InvalidClientTokenId`) and an unsigned request must be rejected |
| 4 | Generated CA with hostname checks; the system trust store must reject the emulator certificate |
| 5 | `--telemetry off` and `EMULATOR_TELEMETRY=off`, inside a namespace with no external route |
| 6 | `unshare --net`: only `lo`, every IPv4 and IPv6 route on `lo` and loopback; namespace differs from the host's |
| 7 | Direct TCP to the pre-resolved public STS and EC2 addresses must fail with `ENETUNREACH` or `EHOSTUNREACH` |
| 8 | Signed `GetCallerIdentity` must return account `000000000000` and `arn:aws:iam::000000000000:user/emulator` |
| 9 | Disposable override sets the EC2 and STS endpoints to `https://127.0.0.1:9297`, the emulator CA and `allowed_account_ids = ["000000000000"]`; every plan is rejected unless it shows exactly that |
| 10 | Disposable copy on the namespace tmpfs with local State; `init -lockfile=readonly` from a local provider mirror; State must start empty |
| 11 | Every saved plan is inspected before apply: the exact reviewed resource inventory and actions, the provider guard, the run tags and, for updates, tag-only changes. The plan hash is checked again before apply |
| 12 | Every State ID must exist in the API with the run's `VerificationRun` tag and must not be in the baseline; any other new object must be an AWS side effect inside the owned VPC. Destroy targets must equal the State IDs |
| 13 | Independent `describe-*` checks after create, update and destroy; the baseline must be unchanged |
| 14 | Destroy uses only the reviewed saved destroy plan. On failure, recovery destroys only State resources with the run tag and verifies absence. Then the emulator is stopped and the tmpfs (credentials, CA, State, plans, logs) is emptied and unmounted |

## Run (Owner-authorized only)

The emulator download host `downloads.aws.com` must be allowed by the session's
network policy, which needs the Owner's approval. Run as root, from the repository
root:

```bash
STEP2_BASE=<directory outside the repository> python3 scripts/emulator-rehearsal/prepare.py
```

```bash
STEP2_BASE=<same directory> STEP2_PROVIDER_MIRROR=<filesystem mirror with the locked aws 6.72.0 package> TESTED_SHA=<merged main SHA> SCENARIO=no-interface-endpoints bash scripts/emulator-rehearsal/launch.sh
```

The summary JSON (non-secret) is copied to `$STEP2_BASE/evidence/`. Emulator
success is never evidence of real AWS behavior, IAM enforcement, networking, cost
or availability.
