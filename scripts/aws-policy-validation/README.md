# Offline policy export and optional owner-run AWS validation

This standard-library toolkit exports the **actual rendered IAM JSON** from
successful native mocked Terraform tests. It prepares reproducible synthetic
policy-context checks and can later call three official read-only validation
APIs through the repository owner's existing authorized AWS CLI v2 session.
It creates no identities, policies, analyzers, assignments or other AWS resources.

Codex Cloud and GitHub Actions run **offline commands only**. No live validation
has been performed by preparing this toolkit. Existing account/session access,
effective authorization, deployment and production readiness remain unverified.

## Files and contract

- `policy_validation.py`: exporter, checksum/quota checks, guarded manual API
  runner, pagination handling, response parser and sanitized reports.
- `policy_cases.py`: deterministic reviewed cases generated from the exported
  synthetic scope, never duplicated standalone policy JSON.
- `tests/`: deterministic stdlib tests using synthetic documents and mocked
  subprocess/transport responses. They never depend on an AWS account.

The exporter requires complete passing JSONL streams from `iam_access` and
`iam_account_policies`. It verifies exactly three Permission Sets, three inline
policies and one Developer-only customer-managed attachment in the first stream,
and exactly one `aws_iam_policy` in the second. The fixed managed-policy name
`Portfolio-Developer-SecretsManager` and path `/` must match the reference.

The generated private bundle contains four documents: Access Admin inline,
Developer EC2 inline, Operator inline and the account-specific Developer Secrets
Manager managed policy. `manifest.json` records actual SHA-256 identities,
source test results, resource inventories, quota sizes/headroom and attachment
identity. `cases.json` is generated from that scope and checksum-bound.
No Terraform plan, state or secret payload is copied into the bundle.

Limits checked independently are 10,240 non-whitespace bytes / 32,768 total
bytes for each Identity Center inline document and 6,144 non-whitespace
characters for the managed policy. One attachment is checked against a
conservative portfolio budget of ten and Identity Center's documented limit of
25. The portfolio budget is not a claim about an account's current IAM role
quota. AWS's current IAM quota table and Identity Center footnote differ on the
default; verify the actual target-account quota before provisioning.

## Export actual synthetic policies

Use Terraform 1.17.0 / AWS Provider 6.72.0 and the repository's transient copies
of its unchanged root lock. First perform backend-disabled initialization and
validation as described by the [IAM module](../../infra/modules/iam_access/README.md)
and [per-account module](../../infra/modules/iam_account_policies/README.md).
Native tests must remain mocked with explicit `command = plan`; do not run a
normal Terraform plan, apply or destroy to prepare these files.

From the repository root, after initialization:

```sh
set -euo pipefail
umask 077
validation_tmp=$(mktemp -d)
terraform -chdir=infra/modules/iam_access test -no-color -json -verbose > "$validation_tmp/iam-tests.jsonl"
terraform -chdir=infra/modules/iam_account_policies test -no-color -json -verbose > "$validation_tmp/account-tests.jsonl"
python3 scripts/aws-policy-validation/policy_validation.py export \
  --iam-test-events "$validation_tmp/iam-tests.jsonl" \
  --account-test-events "$validation_tmp/account-tests.jsonl" \
  --output-dir "$validation_tmp/bundle" \
  --fixture-version terraform-mock-v1
python3 scripts/aws-policy-validation/policy_validation.py offline-check \
  --bundle "$validation_tmp/bundle"
python3 scripts/aws-policy-validation/policy_validation.py run \
  --bundle "$validation_tmp/bundle" \
  --output-dir "$validation_tmp/offline-results"
```

`run` without `--execute-aws` makes **zero AWS CLI subprocess calls and zero AWS
API calls**, including STS. It requests no credentials and only writes offline
results. It checks structure, hashes, synthetic fixtures, quotas and reviewed
case generation; it does not simulate IAM locally or claim AWS validation.
The independent official-reference checker remains a separate CI check.

Output directories must be empty and outside a Git checkout. They are created
with mode 0700 and files with mode 0600. Use `/tmp` or another approved private
location. Keep transient child locks, verbose test JSONL and bundles out of Git;
CI does not upload them. Bundles accept only format-valid synthetic account IDs,
not real account/session data. Policy names, resource ARNs and context fixtures
are not a deployment or actual workforce session.

## Reviewed simulation coverage and limits

The current generator produces **54 cases**: 50 supported synthetic policy-context
expectations and four explicitly unverified desired protections. Coverage includes:

- Developer EC2 allow/deny checks for account, region, Project, protected tags,
  parent VPC/new subnet and both IGW/VPC resources, plus unrelated-service denial.
- All six Secrets Manager actions, creation and dependent tagging, Project
  adoption prevention, ordinary tag edits/removal, recovery windows and force
  deletion, replication guards, account/region/Project rejection, and forbidden
  values, UpdateSecret, RestoreSecret, KMS and policy edits.
- Operator VPC/secret metadata visibility and denied value, mutation and
  administration actions.
- Access Admin assignment/profile/account scoping with instance, Permission Set
  and account resources represented together; unrelated operations are denied.

CreateSecret's positive case models policy conditions only. It cannot prove
payload absence or that the live service supplies the same creation-tag context.
The dependent TagResource authorization is a separate case, not an inferred
successful CreateSecret call. Synthetic context must not be described as a real
role session or effective authorization.

The four unverified desired protections are prevention of main-route-table
replacement, VPC Boolean-value changes, self-assignment and CreateSecret payloads.
They have no invented condition keys or dummy payloads. The runner does not turn
these into passing Deny assertions or claim that AWS simulation resolves them.
Their risks require explicit design/operational review or live verification as
applicable. Identity Center propagation, actual KMS/key policy evaluation,
resource policies, organization controls and workload connectivity remain outside
the simulator's evidence.

## Later manual owner execution in CloudShell

**Do not run this section from Codex Cloud or GitHub Actions.** The executable
rejects the live flag in those environments; do not remove its guards. A user
must initiate this later in AWS CloudShell or an already approved local CLI v2
session, using existing Console/Identity Center authorization. No IAM user,
access key, GitHub secret or new execution identity is required or created.
If a suitable session/permission does not exist, record that missing prerequisite;
do not use the root account for routine validation.

The session needs only the reviewed validation permissions for this toolkit:

| IAM permission | Resource scope | CLI operation |
| --- | --- | --- |
| `access-analyzer:ValidatePolicy` | `*` (no resource-level support) | `aws accessanalyzer validate-policy` |
| `iam:GetContextKeysForCustomPolicy` | `*` (no resource-level support) | `aws iam get-context-keys-for-custom-policy` |
| `iam:SimulateCustomPolicy` | `*` (no resource-level support) | `aws iam simulate-custom-policy` |

CloudShell launch/session authorization is a separate existing Console prerequisite
(`cloudshell:CreateEnvironment`, `CreateSession`, `GetEnvironmentStatus`,
`StartEnvironment`, and Console credential forwarding `PutCredentials` where
needed). The toolkit calls none of these APIs and does not configure identity
permissions. Review access through the owner's existing approved process.

After privately generating or transferring a synthetic bundle and the reviewed
toolkit, the owner may explicitly run, from their separate authorized session:

```sh
python3 scripts/aws-policy-validation/policy_validation.py run \
  --bundle /tmp/REPLACE_WITH_PRIVATE_BUNDLE_DIRECTORY \
  --output-dir /tmp/REPLACE_WITH_NEW_PRIVATE_RESULTS_DIRECTORY \
  --execute-aws
```

These path labels are documentation placeholders, not active Terraform values.
The CLI uses `--cli-input-json file://...`, `--no-paginate`, JSON output and the
fixture's explicit region. It submits only four policy validations, three context
discoveries and the 50 supported simulation cases, plus required pagination.
There are no STS, account/credential-discovery, write or deployment calls. No CallerArn,
ResourceOwner or resource-policy simulation is injected or inferred.

The parser uses actual responses. ValidatePolicy ERROR findings fail; SECURITY_WARNING,
WARNING and SUGGESTION counts remain separate and require human review rather
than secure-success labeling. GetContextKeys discovers keys; keys used in Null
or IfExists conditions may intentionally be absent. Actual MissingContextValues
at either evaluation level are reported as inconclusive.

SimulateCustomPolicy returns an aggregate per action. For multiple requested
resources the toolkit requires complete, unique ResourceSpecificResults and
consistent decisions. One isolated Allow is insufficient. A complete unexpected
Allow fails even if missing context is also reported; unexpected Deny fails a
fully supported positive case. Explicit and implicit Deny remain distinct.
Unsupported, permission-error, malformed, missing or truncated results never
become fabricated passes. Native nextToken/Marker pagination is bounded and
repeated/missing tokens are rejected.

Exit status 0 means offline readiness, or only fully supported checked results;
1 means failed checks/unexpected authorization; 2 means review/incomplete evidence.
With the current four intentionally unverified protections, even otherwise clean
manual API results retain review status 2. This is not production readiness.

## Results and safe replay

`results.json` and `summary.md` contain sanitized findings, decisions, actionable
authorization mismatches, API names and fixture/hash identities. Full private
responses and request files exist only in the private manual output directory;
**do not upload raw responses, request files or session metadata to GitHub**.
Redaction removes ARN/account/identity/token-like strings from shareable details.
Review sanitized reports before sharing; generic redaction is not a guarantee
against every possible confidential value in an external error message.

Reprocess the recorded private capture offline without any AWS CLI invocation:

```sh
python3 scripts/aws-policy-validation/policy_validation.py parse \
  --bundle /tmp/REPLACE_WITH_PRIVATE_BUNDLE_DIRECTORY \
  --responses /tmp/REPLACE_WITH_PRIVATE_RESULTS_DIRECTORY/responses.private.json \
  --output-dir /tmp/REPLACE_WITH_NEW_PRIVATE_REPLAY_DIRECTORY
```

Replay requires the exact matching bundle hash. Interrupted, incomplete or wrong
fixture results remain incomplete/rejected. Parsed responses are not signed
attestations of a real session and never prove live deployment authorization.

## Offline self-tests

```sh
python3 -B -m unittest discover -s scripts/aws-policy-validation/tests -v
```

The 70 tests cover actual mock-plan export, inventories, quotas, attachment
identity, tampering, expected/unexpected decisions, complete multi-resource
semantics, missing context, unsupported responses, all finding severities,
pagination, permission errors, interruption, redaction, CI/live-mode guards and
default zero-AWS-call execution. All subprocess responses in these tests are
mocked. No authenticated AWS validation has been run by these tests.

## Official references

- [Identity Center quotas](https://docs.aws.amazon.com/singlesignon/latest/userguide/limits.html)
- [Customer-managed policy matching](https://docs.aws.amazon.com/singlesignon/latest/userguide/howtocmp.html)
- [IAM quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
- [ValidatePolicy API](https://docs.aws.amazon.com/access-analyzer/latest/APIReference/API_ValidatePolicy.html)
- [CLI ValidatePolicy](https://docs.aws.amazon.com/cli/latest/reference/accessanalyzer/validate-policy.html)
- [CLI SimulateCustomPolicy](https://docs.aws.amazon.com/cli/latest/reference/iam/simulate-custom-policy.html)
- [CLI GetContextKeysForCustomPolicy](https://docs.aws.amazon.com/cli/latest/reference/iam/get-context-keys-for-custom-policy.html)
- [CloudShell existing-identity authentication](https://docs.aws.amazon.com/cloudshell/latest/userguide/sec-auth-with-identities.html)
