#!/usr/bin/env python3
"""Post-merge tree check (Owner decision 2026-11-23): no Full CI re-run after a squash merge.

After an Owner-approved squash merge, the new main commit must be exactly the result
that was verified before the merge:

* its only parent is the base main SHA recorded at review (main did not move);
* its tree equals the tree of merging the reviewed pull request HEAD into that base
  (``git merge-tree --write-tree``); for a branch that already contained the base,
  this is the reviewed HEAD's own tree.

On a mismatch, stop and investigate: the merged content is not the verified content.
Usage (all three are full 40-hex SHAs present in the local clone):

  python3 scripts/ci/merge_check.py --squash <main SHA> --reviewed-head <PR HEAD SHA> --base <base main SHA>

Read-only git only; no network.
"""
import argparse
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
SHA = re.compile(r"^[0-9a-f]{40}$")


class MergeError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise MergeError(message)


def run_git(args):
    process = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return process.returncode, process.stdout.strip()


def verify(squash, reviewed_head, base, runner=run_git):
    for label, value in (("squash", squash), ("reviewed_head", reviewed_head), ("base", base)):
        require(SHA.match(value or ""), label + "_sha_invalid")

    def git(*args):
        code, output = runner(list(args))
        require(code == 0, "git_failed:" + " ".join(args[:2]))
        return output

    parents = git("rev-list", "--parents", "-n", "1", squash).split()
    require(len(parents) == 2 and parents[0] == squash, "squash_commit_must_have_exactly_one_parent")
    require(parents[1:2] == [base], "squash_parent_is_not_the_reviewed_base_main")
    squash_tree = git("rev-parse", squash + "^{tree}")
    expected_tree = git("merge-tree", "--write-tree", base, reviewed_head).split("\n")[0].strip()
    require(SHA.match(expected_tree), "reviewed_merge_result_unavailable")
    require(squash_tree == expected_tree,
            "squash_tree_differs_from_the_reviewed_merge_result (stop and investigate before any further merge)")
    return {"status": "passed", "squash": squash, "parent": base, "reviewed_head": reviewed_head, "tree": squash_tree}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--squash", required=True)
    parser.add_argument("--reviewed-head", required=True)
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.squash, args.reviewed_head, args.base)))
    except MergeError as error:
        print("Post-merge tree check failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
