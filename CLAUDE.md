@AGENTS.md

# Claude Code harness

The current MASTER_POLICY and the exact authorized Owner decision govern each task.
AGENTS.md (imported above) remains the shared repository instruction source under that
policy; this section only adds Claude Code operating rules. Creating this file stops
Claude Code from reading AGENTS.md natively, so the import above must stay first.

## Effort
- Default effort is `medium` (`effortLevel` in `.claude/settings.json`).
- Use `low` for mechanical edits, formatting and status checks.
- Use `high` for design decisions, security review and root-cause analysis, or where
  the task decision requires it. Use `xhigh` or `max` only when the policy or the
  exact decision explicitly requires it.

## Context discipline
- Read only the files and line ranges the task needs. Use `grep`/`sed -n` ranges and
  do not re-read unchanged files. Write long logs to a scratch file and read failures.
- Do not paste large tool output into replies; report verdict, evidence path and the
  lines that matter.
- Record progress and decisions in the PR description or the existing project docs,
  not only in the conversation.
- Keep across compaction: the authorized scope and decision IDs, the exact file
  manifest, branch, base and exact HEAD, CI run IDs and attempts, open stop
  conditions and pending Owner decisions.

## Skills and subagents
- `verify-change` skill: check the full change set against the authorized manifest,
  map it to CI, run eligible local checks and prepare the PR report.
- `evidence-package` skill (on demand only): build and publish a formal evidence package.
- `code-reviewer` and `security-reviewer` subagents: read-only (Read, Grep, Glob)
  advisory review of a finished, non-trivial diff. The parent supplies command output.
- One subagent at a time unless the work is truly independent. No agent teams and no
  recursive delegation. A subagent verdict is not independent review or merge approval.

## Enforcement
- Absolute prohibitions are denied, not turned into prompts: pushes to `main`, force
  pushes (including force-with-lease), merges and auto-merge, destructive Git
  operations, real AWS/SSO/STS/API calls, Terraform plan/apply/destroy/import and State
  access, Kubernetes/EKS operations, credential or secret exposure, edits to existing
  evidence, and shell mutation of protected governance files. Native deny rules in
  `.claude/settings.json` and `.claude/hooks/pre_tool_guard.py` enforce them.
- Edits to protected governance, CI, lock, harness and evidence paths ask for
  confirmation. A confirmation approves only a file change inside the exact authorized
  scope; it is never a policy waiver or an operation authorization.
- A denial or an unexpected question means stop and report. Never work around the guard.
- The guard is defense in depth, not a sandbox; server-side branch protection, the
  required check and the Owner merge remain the binding controls.

## Completion and stop conditions
- State the completion condition before starting. Done means the required commands
  exited 0 and, for a PR, the required CI succeeded on the exact HEAD. Self-assessment
  alone is never completion.
- At most two integrated correction cycles per task. Then stop and report the failures,
  their evidence and the open questions.
- A `/goal` turn limit (at most 20 turns, stated in the condition) is an instructional
  bound unless the runtime enforces it. Never use `/goal` for approvals, merge, CI
  dispatch or scope changes.

## Rollback
- Before commit: restore only the files of the exact new-file manifest (remove those
  specific new files, or `git restore -- <path>` for an authorized tracked file).
- After commit: a scoped corrective commit, or a reviewed revert through the normal PR.
- Never use blanket deletion of `.claude/`, `git reset --hard` or `git clean`, and
  keep unrelated local changes. `/rewind` checkpoints do not track files changed by Bash.
