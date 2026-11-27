# Public verification evidence

This branch is dedicated to public verification evidence.
This branch has an independent Git history.
Never merge this branch into main.
Never merge main into this branch.
Never modify previously published evidence artifacts.
Only owner-authorized, public-safe evidence may be added.
No GitHub Actions workflows are stored in this branch.
Evidence status does not imply task acceptance or production readiness.

| Rule | Operating requirement |
| --- | --- |
| EB-01 | Use the `evidence` branch. |
| EB-02 | Maintain its independent orphan Git history. |
| EB-03 | Prohibit pull requests and merges with main. |
| EB-04 | Preserve published evidence bytes and paths. |
| EB-05 | Prohibit force pushes and remote branch deletion. |
| EB-06 | Append at new paths. Add index entries while preserving earlier entries. |
| EB-07 | Maintain an evidence index, package manifests and SHA-256 digests. |
| EB-08 | Exclude credentials, secrets and real Terraform state. |
| EB-09 | Exclude CI workflows. |
| EB-10 | Require a public-disclosure review and explicit Owner authorization for each publication. |
| EB-11 | Independently retrieve the published bytes and verify their digests. |
| EB-12 | Verify the main HEAD, tree, protection and CI state after a push. |

These rules govern publication. Independent review remains pending until the
reviewer retrieves and verifies the commit-pinned artifacts.
