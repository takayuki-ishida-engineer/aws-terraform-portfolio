---
name: verify-change
description: Verify a finished change in this repository before commit and PR - compare every committed, staged, unstaged and untracked path with the authorized file manifest, map it to CI, run eligible local checks, check secrets and whitespace, and prepare the PR report. Use when a task's edits are done.
effort: medium
---

# Verify a change

1. Change set. Collect the union of all changed paths; `BASE...HEAD` alone misses
   uncommitted files:
   - `git status --porcelain=v1 --untracked-files=all`
   - `git diff --name-status --no-renames BASE...HEAD` (committed)
   - `git diff --cached --name-status --no-renames` (staged)
   - `git diff --name-status --no-renames` (unstaged)
   - `git ls-files --others --exclude-standard` (untracked, non-ignored)
   Compare the union with the exact authorized manifest. Any extra or missing path: stop.
2. Impact: `python3 scripts/ci/impact.py explain <paths>`. An `UNMAPPED` path fails
   PR Safety CI closed: stop; never widen the map outside the authorized scope. Record
   every `high_risk` category (Full CI required). Selection keeps all prerequisites
   and always-on checks.
3. Eligible local checks for the changed components only, using the existing entry
   points (`scripts/ci/README.md`, AGENTS.md "Codex execution efficiency"). For
   `scripts/ci/**`, workflows, the map or `.claude/**`, run the documented `ci_policy`
   entry point (`runtime_test_runner.py --clean-python-stdin` with `test_ci`) and its
   checks. Never skip IAM, network, secret, provider/state or Actions checks. Long
   output goes to a scratch file; read failures. A missing local prerequisite is
   recorded as a limitation, never as a PASS.
4. Hygiene for all intended commit content: `git diff --check BASE` and
   `git diff --cached --check`, a whitespace check of untracked files, and a secret
   check of every intended file. `check_tracked_files.py` covers tracked files only;
   check new files separately. Never read or print ignored secret files.
5. Failures: at most two integrated correction cycles for the task, then stop and report.
6. Report after push and PR: PR URL, exact HEAD SHA, changed files, local checks and
   exit codes, checks delegated to hosted CI, PR Safety CI result, Full CI result or
   `FULL CI NOT RUN`, Offline Contracts result. Local success never replaces required
   hosted CI; pending or running CI is never a pass.
