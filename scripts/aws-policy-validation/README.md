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
- `simulation_projection.py`: conservative exact-action projection and independent
  structural equivalence verification for each request.
- `guardrail_verification.py`: independent, deliberately limited static proofs
  and semantic negative mutations for protected VPC tags and secret creation.
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

## Missing-context classification correction (Phase 3-3.6)

The owner reported a complete authorized CloudShell capture from the previous
tool: four ValidatePolicy checks and three GetContextKeys checks passed; 21
supported simulations passed, 29 supported simulations were inconclusive with
missing context, and four intentionally unsupported cases stayed inconclusive.
No actionable authorization mismatch was reported. These are the owner's
observations, not an AWS run performed or independently revalidated by Codex.
No raw CloudShell capture, real identifier or session detail is committed here.

Each Developer simulation previously received both its EC2 inline and Secrets
Manager policy. AWS reported keys from unrelated statements, for example Secrets
Manager replica/deletion keys for `developer-vpc-unapproved-region`. Discovery
of a key in the complete composition does not establish that the key can affect
every action. The correction narrows **requests**, not approved permissions or
the strict response missing-context rule.

For each case, the tool derives an action-only projection from the actual
Terraform-generated documents. It omits only statements whose plain exact Action
values provably cannot match the tested action; IAM action names/prefixes are
case-insensitive. Every retained statement is copied whole, including all
Resources, Conditions and Allow/Deny effects. It does not filter by resource,
evaluate condition values or build a generic IAM evaluator. Ambiguous wildcard,
NotAction or unknown action selectors cannot justify omission or static absence.
The approved bundle's existing exact-action/Allow validation is unchanged.

A separate structural verifier checks the complete retained/omitted partition
against the original documents and rejects changed resources, conditions, added
statements or dropped matching Allow/Deny statements. Case/profile, source and
projected document hashes and the exact request hash bind the evidence to its
original bundle. ActionNames, all requested resource ARNs and ContextEntries are
preserved. **No context values are invented**: Null/IfExists absence remains
intentional, and same-action alternatives are retained even when they may need
additional context.

The current 54-case bundle has three distinct paths:

| Evidence path | Cases | Interpretation |
| --- | --- | --- |
| Projected AWS requests | 35 | Requires later actual AWS responses; any returned missing context remains inconclusive |
| Static action-inventory checks | 15 | No statement can match the action in this reviewed set; no simulator call and no claimed AWS Deny |
| Intentionally unsupported protections | 4 | Remain inconclusive; never converted to static or passing Deny results |

The 35 request candidates comprise nine Developer EC2 cases, 20 Developer
Secrets Manager cases, three Operator metadata cases and three Access Admin
assignment cases. In particular, `developer-vpc-unapproved-region` and the other
Developer EC2 requests no longer include Secrets Manager statements or their
unrelated keys. Each is safely eligible for simulation of the projected set;
that does not guarantee a conclusive AWS response. Same-action alternatives such
as TagResource/CreateTags and intentionally absent Null/IfExists keys still keep
any reported missing context inconclusive.

The 15 static checks cover Developer unrelated EC2/IAM writes and the eight
forbidden secret/KMS actions, Operator secret-value/write/IAM/Identity Center
actions, and Access Admin unrelated account creation. The earlier aggregate
21/29 results do not identify which individual cases belonged to each outcome;
no per-case resolution of that historical capture is inferred here.

Static absence means only `not_granted_by_reviewed_policy_set`. It is separate
from AWS-simulated evidence and does not exclude grants from other policies.
A positive case whose action disappeared fails rather than passing statically.
Missing account, region, Project/tag, recovery or other context from potentially
applicable statements remains inconclusive; malformed/paginated/multi-resource
checks and unexpected-Allow/deny protections remain strict.

New captures use format version 2 and the action-projection/request identity.
Original policy bundles remain format version 1 and unchanged. Replay of a legacy
version-1 capture retains its full-policy simulation interpretation and strict
missing-context classification, including unexpected-Allow detection. It cannot
silently become evidence of a new projected request. New-format records with
missing or mismatched request proof are unverified, and extra simulator records
for static-only cases are rejected rather than ignored.

That correction did not itself resolve the reported 29 inconclusive cases. The
owner subsequently reported a new run; its aggregate results are recorded below.
Even a projected request can remain inconclusive for a same-action alternative or
intentionally absent key. The four inherent limitations and live authorization
gaps remain.

## Independent guardrail verification (Phase 3-3.7)

The owner reported the following latest authenticated CloudShell results. Codex
has not executed or independently reproduced these AWS calls, and no raw capture,
account identifier or session data is committed.

| Evidence category | Owner-reported result |
| --- | --- |
| ValidatePolicy / GetContextKeys | Four passed / three passed |
| AWS Simulator, supported cases | 33 passed, two missing-context inconclusive |
| Existing static action inventory | 15 passed; separate from AWS simulation |
| Intentionally unsupported protections | Four inconclusive |
| Findings requiring changes / overall | Zero / `review_required` |

The two AWS cases are `developer-vpc-project-tag-change` and
`developer-secret-replica-overwrite`. **Their AWS classifications remain
inconclusive.** The new independent proof is additional static evidence; it never
edits a capture, suppresses MissingContextValues or upgrades a simulator result.
Actual deployed-role authorization and production readiness remain unverified.

`offline-check`, the default offline `run`, and response `parse` now include a
separate `guardrail_proofs` section. Its input is the unchanged successful native
mock-plan export: both Developer inline and account-owned Secrets Manager
documents, not a handwritten replacement policy. The oracle imports neither the
projection helper nor the AWS response parser. It considers every potentially
matching Allow and Deny for the two exact actions; unsupported selectors,
operators or ambiguous structure make the proof inconclusive and cause a nonzero
offline validation result. Semantic regressions fail validation.

The proof is intentionally limited to these properties and condition operators:

| Property | Independent check |
| --- | --- |
| Existing-resource Project tag | A direct `ec2:CreateTags` request lacks `ec2:CreateAction`. Every applicable creation-only statement must reject that absence; `EditNonAuthorizationTags` excludes Project keys case-insensitively and requires nonempty TagKeys. Test `Project`, `project`, `pRoJeCt` and mixed tag sets. |
| Legitimate tags | An ordinary tag edit on a matching project resource and supported resource-creation tagging with correct CreateAction/Project context remain eligible within the reviewed set. |
| Replica absence | `Null` true for AddReplicaRegions requires its absence/null semantics. A nonempty replica list is rejected independently of overwrite. |
| Overwrite prevention | `BoolIfExists` false accepts absent or false overwrite context and rejects true, independently of replica absence. Both unsafe inputs are also tested together. |
| Scope restrictions | Resource, caller account, requested region and project conditions remain meaningful; isolated negative contexts and guard mutations test these boundaries. |

For each guard-removal/weakening mutation, the oracle supplies a synthetic witness
whose other relevant conditions match. In particular, removing a creation-action
guard must expose direct adoption of another project's resource with a matching
requested Project tag; replica tests keep overwrite false, and overwrite tests
keep replica context absent. A detected mutation must expose the unsafe static
authorization change, rather than merely differ from a fixed checksum. Finite
scenarios supplement conservative inspection of every relevant statement; they
do not justify ignoring an additional possible grant.

JSON evidence identifies source policy names, canonical JSON SHA-256 hashes and
the export manifest's raw-file SHA-256 hashes (these hash different encodings),
applicable statement IDs/effects, relevant conditions, synthetic contexts,
expected/actual decisions, and negative mutation results. Markdown shows a
separate source/statement/scenario/mutation summary. Outputs retain the existing
private-directory rules; no reports or artifacts are uploaded by CI.

The current two-account mock export produces six per-statement structural checks,
181 synthetic scenarios and 36 mutation witnesses. Every witness must change a
baseline non-Allow into an Allow after only its targeted unsafe mutation. These
counts are independent of the unchanged 54 AWS/inventory/unsupported cases.
The creation-only path tests missing or incorrect CreateAction as well as caller,
requested-region and resource-scope safeguards for all four resource types.

These are policy-set proofs for explicitly modeled synthetic contexts, **not AWS
Simulator successes, deployed-session authorization or a general IAM evaluator**.
Real request context, resource state, other policies, SCPs, boundaries, KMS,
Identity Center propagation and dependent API authorizations remain outside the
proof. The 54 cases, 35 simulation candidates, 15 inventory checks and four
unsupported protections are unchanged. No context is inserted into an AWS
request and intentional Null/IfExists absence remains absent.

Official semantics used by the oracle:

- [IAM condition operators, Null and IfExists](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html)
- [Single/multivalued context and set operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-single-vs-multi-valued-context-keys.html)
- [EC2 tagging during creation and CreateAction](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/supported-iam-actions-tagging.html)
- [Secrets Manager authorization reference and condition-key types](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html)

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
fixture's explicit region. It submits four full-policy validations, three full-composition context
discoveries and 35 action-projected simulations, plus required pagination. The
15 static inventory checks make no simulator call; four unsupported cases remain
inconclusive.
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

`results.json` and `summary.md` separate AWS simulations, `static_checks` and
`guardrail_proofs`, record request mode/proof and contain sanitized findings, decisions, actionable
authorization mismatches, API names and fixture/hash identities. Full private
responses and request files exist only in the private manual output directory;
**do not upload raw responses, request files or session metadata to GitHub**.
Redaction removes ARN/account/identity/token-like strings from shareable details.
Review sanitized reports before sharing; generic redaction is not a guarantee
against every possible confidential value in an external error message.

Reprocess a recorded private capture offline without any AWS CLI invocation
(legacy captures keep their original conservative classification):

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

The 153 tests preserve all prior 110 (the original 70 plus 40 action-projection
regressions) and add 35 independent guardrail tests plus eight report/CLI
integration tests. They cover
actual mock-plan export, inventories, quotas, attachment
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
