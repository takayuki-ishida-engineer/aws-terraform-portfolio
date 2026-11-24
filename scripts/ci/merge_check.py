#!/usr/bin/env python3
"""Post-merge tree check (Owner decision 2026-11-23): no Full CI re-run after a squash merge.

The evidence is the tree that CI actually verified, copied from the run record:

* Full CI: ``tested_tree`` and ``evidence`` in the trigger record ("Full CI evidence"
  in the Summarize step log and the job summary);
* PR Safety CI: ``tested_tree`` in the impact report (the verify step log and the job
  summary), with ``evidence`` = ``pull_request``.

After an Owner-approved squash merge, all of these must hold, or the merge stops for
investigation:

1. the squash commit has exactly one parent, the reviewed base ``main``;
2. its tree equals the verified tree;
3. the verified tree belongs to the reviewed pull request HEAD:
   - ``pull_request`` evidence (a merge-commit run): it equals the merge of that HEAD
     into that base (``git merge-tree --write-tree``), so the run tested this base;
   - ``dispatch`` evidence (a run on the branch HEAD): it equals the HEAD's own tree,
     and the base is an ancestor of that HEAD.

A recomputed merge tree alone is never accepted: the squash tree is compared with
the tree CI recorded. Usage (full 40-hex SHAs present in the local clone):

  python3 scripts/ci/merge_check.py --squash <main SHA> --reviewed-head <PR HEAD> \\
      --base <reviewed base main> --verified-tree <tested_tree> --evidence pull_request|dispatch

Read-only git only; no network.
"""
import argparse
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
SHA = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE = ("pull_request", "dispatch")


class MergeError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise MergeError(message)


def run_git(args):
    process = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return process.returncode, process.stdout.strip()


def verify(squash, reviewed_head, base, verified_tree, evidence, runner=run_git):
    for label, value in (("squash", squash), ("reviewed_head", reviewed_head), ("base", base), ("verified_tree", verified_tree)):
        require(SHA.match(value or ""), label + "_sha_invalid")
    require(evidence in EVIDENCE, "evidence_kind_invalid")

    def git(*args):
        code, output = runner(list(args))
        require(code == 0, "git_failed:" + " ".join(args[:2]))
        return output

    parents = git("rev-list", "--parents", "-n", "1", squash).split()
    require(len(parents) == 2 and parents[0] == squash, "squash_commit_must_have_exactly_one_parent")
    require(parents[1:2] == [base], "squash_parent_is_not_the_reviewed_base_main")
    squash_tree = git("rev-parse", squash + "^{tree}")
    require(squash_tree == verified_tree, "squash_tree_differs_from_the_tree_ci_verified (stop and investigate before any further merge)")
    if evidence == "pull_request":
        merged = git("merge-tree", "--write-tree", base, reviewed_head).split("\n")[0].strip()
        require(merged == verified_tree, "verified_tree_is_not_the_merge_of_the_reviewed_head_into_the_base")
    else:
        require(git("rev-parse", reviewed_head + "^{tree}") == verified_tree, "verified_tree_is_not_the_reviewed_head_tree")
        require(runner(["merge-base", "--is-ancestor", base, reviewed_head])[0] == 0, "reviewed_head_does_not_contain_the_base")
    return {"status": "passed", "squash": squash, "parent": base, "reviewed_head": reviewed_head, "tree": squash_tree,
            "evidence": evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--squash", required=True)
    parser.add_argument("--reviewed-head", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--verified-tree", required=True)
    parser.add_argument("--evidence", required=True, choices=EVIDENCE)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.squash, args.reviewed_head, args.base, args.verified_tree, args.evidence)))
    except MergeError as error:
        print("Post-merge tree check failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
