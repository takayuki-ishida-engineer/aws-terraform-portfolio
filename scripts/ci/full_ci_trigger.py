#!/usr/bin/env python3
"""Verify why and on what a Full CI run started, before anything else runs.

Full CI (Owner decision 2026-11-23) runs only:

* on ``pull_request`` to main when a high-risk path changes (the workflow's path
  filter): the checkout must be the merge commit whose second parent is the event's
  exact pull request HEAD;
* on ``workflow_dispatch`` by the Owner for a designated milestone: dispatched on the
  pull request branch, with the target pull request number, the exact 40-hex HEAD
  SHA, which must equal the dispatched commit, and a reason. The branch must contain
  the current main, so the tested tree is the tree a squash merge produces while
  main stays unchanged.

Any other event (a push to main included) fails closed. The tested commit, its tree
and the base main are written to the job summary for SHA management and the
post-merge tree check. Read-only; nothing here calls AWS or the GitHub API.
"""
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
SHA = re.compile(r"^[0-9a-f]{40}$")
NUMBER = re.compile(r"^[1-9][0-9]{0,6}$")
REASONS = ("owner-milestone", "claude-final-task", "codex-root-completion", "high-risk-change")


class TriggerError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise TriggerError(message)


def run_git(args):
    """Return (exit code, stripped stdout) of one git command."""
    process = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return process.returncode, process.stdout.strip()


def verify(env, runner=run_git):
    def git(*args):
        code, output = runner(list(args))
        require(code == 0, "git_failed:" + " ".join(args[:2]))
        return output

    event = env.get("EVENT_NAME", "")
    run_sha = env.get("RUN_SHA", "")
    require(SHA.match(run_sha), "run_sha_invalid")
    head = git("rev-parse", "HEAD")
    require(head == run_sha, "checkout_is_not_the_run_commit")
    record = {"event": event, "run_sha": run_sha, "run_attempt": env.get("RUN_ATTEMPT", "")}
    if event == "pull_request":
        require(env.get("BASE_REF") == "main", "pull_request_base_not_main")
        number, event_head = env.get("PR_NUMBER", ""), env.get("PR_HEAD_SHA", "")
        require(NUMBER.match(number) and SHA.match(event_head), "pull_request_event_fields_invalid")
        parents = git("rev-list", "--parents", "-n", "1", "HEAD").split()
        require(len(parents) == 3 and parents[0] == head, "pull_request_checkout_is_not_a_merge_commit")
        require(parents[2:3] == [event_head], "merge_commit_does_not_contain_the_pull_request_head")
        record.update(mode="high-risk pull request (automatic path filter)", pull_request=int(number), head_sha=event_head,
                      base_main_sha=parents[1], tested_tree=git("rev-parse", "HEAD^{tree}"),
                      head_tree=git("rev-parse", event_head + "^{tree}"))
    elif event == "workflow_dispatch":
        owner = env.get("OWNER", "")
        require(owner and env.get("ACTOR") == owner and env.get("TRIGGERING_ACTOR") == owner, "dispatch_actor_not_owner")
        ref = env.get("REF", "")
        require(ref.startswith("refs/heads/") and ref != "refs/heads/main", "dispatch_ref_must_be_a_pull_request_branch")
        number, expected, reason = env.get("INPUT_PR", ""), env.get("INPUT_SHA", ""), env.get("INPUT_REASON", "")
        require(NUMBER.match(number), "dispatch_pull_request_number_invalid")
        require(SHA.match(expected), "dispatch_expected_head_sha_invalid")
        require(expected == run_sha, "dispatch_expected_head_sha_is_not_the_dispatched_commit")
        require(reason in REASONS, "dispatch_reason_invalid")
        main = git("rev-parse", "refs/remotes/origin/main")
        require(SHA.match(main), "origin_main_unavailable")
        require(runner(["merge-base", "--is-ancestor", main, "HEAD"])[0] == 0,
                "dispatch_branch_does_not_contain_current_main (update the branch, then dispatch for its new HEAD)")
        record.update(mode="Owner-designated milestone (workflow_dispatch)", pull_request=int(number), head_sha=expected,
                      reason=reason, base_main_sha=main, tested_tree=git("rev-parse", "HEAD^{tree}"),
                      head_tree=git("rev-parse", "HEAD^{tree}"))
    else:
        raise TriggerError("event_not_allowed_for_full_ci:" + event)
    return record


def main():
    try:
        record = verify(os.environ)
    except TriggerError as error:
        print("Full CI trigger refused: " + str(error), file=sys.stderr)
        return 1
    print("Full CI trigger:", json.dumps(record, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("## Full CI trigger\n\n| Field | Value |\n| --- | --- |\n")
            for key in sorted(record):
                output.write(f"| {key} | `{record[key]}` |\n")
            output.write("\nFull CI PASS applies only to this exact HEAD; a new HEAD needs a new Full CI run.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
