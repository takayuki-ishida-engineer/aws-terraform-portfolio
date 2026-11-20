# Emulator run evidence ledger tooling

`harvest.py` maintains the evidence ledger in
[`docs/evidence/emulator-runs/`](../../docs/evidence/emulator-runs/index.md). Master Policy v14.4 §13.4
requires one sanitized entry per run and attempt for every formal run of
[`aws-emulator-rehearsal.yml`](../../.github/workflows/aws-emulator-rehearsal.yml) and
[`aws-emulator-verification.yml`](../../.github/workflows/aws-emulator-verification.yml), whether the run
passed, failed or stopped early. The rules are in
[AGENTS.md](../../AGENTS.md#emulator-verification-workflow-and-evidence).

GitHub deletes run logs and job summaries after its retention period (at most 90 days on a public
repository). The ledger keeps the structured, sanitized result for longer. It is not a copy of the full log.

The tool reads local files only. It makes no network call, starts no emulator, needs no credential and
never writes to GitHub. It sits outside the rehearsal workflow's trigger paths, so changing it or the
ledger starts no Emulator run.

## Files

| File | Role |
| --- | --- |
| `harvest.py` | `build` turns one run's metadata and job log into an entry. `index` regenerates `index.md`. `check` validates every entry, the index and the comparison with the run list snapshot. `KNOWN_HARNESSES` pins the harness versions whose runs can be PASS |
| `test_harvest.py` | Offline negative, mutation and tamper tests. The `AWS Emulator offline contracts` workflow runs them, and `harvest.py check`, on every pull request and `main` push |
| `docs/evidence/emulator-runs/<run_id>-attempt-<n>.json` | One entry per run and attempt |
| `docs/evidence/emulator-runs/actions-runs.json` | Static snapshot of the Actions run list of both workflows, retrieved by the operator at the time in its `retrieved_at` field and committed with the entries |
| `docs/evidence/emulator-runs/index.md` | Generated table of every entry, with the result of comparing the ledger with that snapshot |

## What an entry holds

| Field | Content | Source |
| --- | --- | --- |
| `workflow`, `run`, `job` | Workflow file, run ID, attempt, number, event, branch, head SHA, conclusion, timestamps, whether the Owner was the actor and the triggering actor, runner label, job steps and their conclusions, run and job URLs | GitHub Actions run and job metadata. Step names are checked against the workflow file at the head SHA |
| `source` | Whether the full log, a verbatim excerpt or no log was harvested; log line count; structured rows found; whether a `summary-record` row exists | The job log |
| `tested` | Tested SHA, harness path and SHA-256, whether the harness was read from git at that SHA (and, for Step 2, equals the run's recorded hash), the harness's required lifecycle operations (its `OPERATIONS` list at that SHA), tool versions, scenario | Structured rows, and git at the tested SHA |
| `controls` | Each of the 14 controls | Structured rows only. NOT_TESTED when the run recorded nothing |
| `roots` | Each rehearsed root (or the representative disposable adapter): result, Terraform resource addresses and where they come from, per-operation results, independent API IDs, resource cleanup. `evidence` holds the plan gate status, the resource count the plan gate recorded, the counts of owned resources the independent API identity checks recorded after create and update, and the SHA-256 of the sorted address list | Structured rows. Addresses come from the reviewed inventory in the harness (or the adapter's resource blocks) at the tested SHA, which the run's plan gate enforces |
| `out_of_scope_roots` | Every other DEV root, as NOT_TESTED or EMULATOR_COMPATIBILITY_BLOCKED | Fixed. Never PASS |
| `cleanup` | Resource, material, process and host cleanup receipts | Structured rows |
| `result` | PASS, FAIL, BLOCKED or INSUFFICIENT_EVIDENCE; the basis (summary record, gate rows or run metadata); the failing step, stage, diagnostic code and cause | Structured rows, otherwise job metadata and fixed log patterns of the run gate |
| `observations`, `untested`, `residual_risk`, `evidence_gaps` | Sanitized probe results, untested scope, residual risk, and what evidence is missing | Derived from the above; gaps are explicit |
| `harvest` | Harvest time and whether the entry is the initial backfill or a regular registration | The operator |

## Safety and honesty rules (enforced by `validate`)

- **Allowlist.** Only allowlisted keys at every level, and only allowlisted fields of the harness's
  `summary-record` and gate rows. An unknown key rejects the entry.
- **Size limits.** At most 64 KiB per entry, 4 MiB and 20,000 lines per log, 64 KiB per row, 400 characters
  per string and 64 items per list.
- **Rejected content.** Strings must be one line of a safe character set. The tool rejects:
  - AWS access key IDs, private keys, AWS secret fields, authorization headers, GitHub tokens and JWTs;
  - email addresses;
  - Terraform State or plan forms;
  - secret-like fields;
  - real 12-digit account IDs (only `000000000000` passes);
  - opaque high-entropy tokens.
- **Identity.**
  - The record's run ID, attempt, repository, workflow, event, URL and tested SHA must match the run metadata.
  - The harness hash must equal the harness file at the tested SHA.
  - The plan and API resource counts must match the reviewed inventory.
  - A DEV root's path must match its name.
- **No inferred success.** PASS needs all of the following, for every rehearsed root:
  - a successful run and job, and the full log;
  - all 14 controls and every cleanup receipt PASS;
  - a harness verified against git, whose version is pinned in `KNOWN_HARNESSES` for that workflow;
  - the required operation list of that harness version, recorded and equal to the pinned list, and every one
    of those operations present and PASS. A missing operation key is never PASS;
  - a scenario pinned for that harness version, whose resource count and address digest equal the pinned
    inventory;
  - plan evidence: the plan gate PASS and, where the harness records counts (Step 2), a plan resource count
    equal to the inventory;
  - independent API evidence: the resource ID (`vpc_id`) and, where the harness records counts (Step 2), the
    owned-resource counts after create and update equal to the inventory;
  - for Step 2, the `summary-record`.

  At harvest time, measured PASS results with any of this missing become INSUFFICIENT_EVIDENCE, with each
  missing item listed in `evidence_gaps`. A run without a structured record keeps all 14 controls NOT_TESTED and
  is BLOCKED, FAIL or INSUFFICIENT_EVIDENCE. Every entry's address digest must match its address list, so a
  changed count, address list or digest is rejected.
- **Comparison with the run list snapshot.** `check` compares the ledger with `actions-runs.json`. That file is
  a static snapshot: the comparison makes no network call, and passing it shows only that the ledger matches
  the run list as it was at the snapshot's `retrieved_at` time, not the live GitHub run list. `check` reports:
  - unregistered runs and missing earlier attempts;
  - entries that are not in the run list, or that disagree with it;
  - runs still in progress;
  - runs whose log could not be retrieved.

  It fails unless the ledger matches the snapshot (unavailable logs are only reported). It also fails if
  `index.md` differs from the regenerated index.
- **Append-only.** `build` refuses to overwrite an existing entry. A correction is a new reviewed pull
  request that states its reason.

## Registering a run

Register each run in its own pull request, before the next `main` change or within 7 days of the run,
whichever comes first. Anything late or unrecoverable is recorded as EVIDENCE_GAP.

1. Wait until the run has completed.
2. Read the run's metadata, its job and its job log through the GitHub API (in Claude Code, the GitHub
   connector), and the run list of both workflows.
3. Write a meta file with the run, the job and its steps, and the log kind and line count. Use the field
   names of an existing entry's `run` and `job`, without the URLs. Keep the raw log outside the repository.
4. Run the build:

   ```bash
   python3 scripts/emulator-evidence/harvest.py build --meta META.json --log JOB.log --repo . --out docs/evidence/emulator-runs --harvested-at YYYY-MM-DDTHH:MM:SSZ
   ```

   `--registration` defaults to `regular`; `initial-backfill` was used only for the 2026-11-20 migration.

5. Replace `actions-runs.json` with the run list just retrieved, with its `retrieved_at` time. Then regenerate
   the index and check:

   ```bash
   python3 scripts/emulator-evidence/harvest.py index docs/evidence/emulator-runs
   ```

   ```bash
   python3 scripts/emulator-evidence/harvest.py check docs/evidence/emulator-runs
   ```

6. Open the pull request. It needs Full CI, independent review and Owner merge approval.

The workflows never write the ledger: they keep `contents: read` and push nothing.

## Multi-root summary records (consolidated harness)

The consolidated Step 2 harness (`step2-multi-root-v2`) rehearses every root in `all` (`network`, then `api`)
in one run. Its single `summary-record` has `roots` (per root: status, operations, per-root controls 9 to 13,
resource cleanup, failure) and `known_gaps`, and no top-level `operations` or `resource_cleanup`. `harvest.py`
turns it into one entry with one `roots[]` item per rehearsed root:

- **Scope.** The rehearsed roots must equal the harness's `ALL` (or the dispatched root), read from git at the
  tested SHA. Every other DEV root is listed out of scope. Its reason is the `known_gaps` text where the harness
  reports one.
- **Inventory and operations.** Each root's addresses come from `SCENARIOS[<root>]['expected']`, and its
  required operations from `OPERATIONS`, with `teardown_plan` and `teardown` added for a root that has a
  teardown switch (`api`). Both are evaluated from literals, never by running the harness. The root records its
  own `required_operations`.
- **Per-root evidence.** Gate rows are attributed to a root by their `root` field or, if they have none, by the
  latest `root-start` before the next `root-result`. That gives each root its plan count, its independent API
  identity counts after create and update, and its IDs: `vpc_id` for `network`; `user_pool_id` and
  `rest_api_id` for `api`. Each ID is format-checked and must not change between create and update.
- **PASS.** PASS needs every root in the pinned scenario with every required operation, controls 9 to 13, the
  pinned inventory, plan count, API counts, required IDs and resource cleanup PASS, plus the run-level controls,
  material, process and host cleanup.
- **Failures.** A measured root failure keeps the harness status: FAIL, BLOCKED or PARTIAL-SKIP. Missing evidence
  makes the entry INSUFFICIENT_EVIDENCE.

`test_harvest.py` checks that the current `scripts/emulator-rehearsal/rehearse.py` is pinned with matching
inventories and operation lists. Changing the harness therefore requires reviewing and pinning the new version
in `KNOWN_HARNESSES`.

The ID patterns follow the AWS formats, and the emulator's IDs observed in the local preliminary run match them.
If a later emulator release uses another format, `build` fails closed (`summary-api-id`) until a reviewed
change updates the pattern.

## Limitations

- The metadata and the run list snapshot are transcribed from the GitHub API by the operator. The
  following checks catch inconsistencies but cannot prove the transcription:
  - the run identity recorded inside the log;
  - step names against the workflow file;
  - timestamp order;
  - comparison with the run list snapshot.

  Reviewers can compare any entry with the run page while GitHub keeps the run.
- Where only part of a log was harvested (`source.log` = `excerpt`), the lines are copied verbatim from the
  API response, and the entry lists this as an evidence gap. Such an entry can never be PASS.
- The ledger records what the harness measured. Emulator results are never evidence of real AWS
  deployment, IAM enforcement, networking, cost or availability.
