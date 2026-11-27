# Initial Career Portfolio Evidence

This record binds existing observations to the commit, workflow, run and
attempt that produced them. The release source baseline is
[`1a5e3d41da208407caaf8ac9a4702c3458367a18`](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/commit/1a5e3d41da208407caaf8ac9a4702c3458367a18),
Tree `b91ef273126464718b5b541c79b8bc5483665138`. Historical counts belong to
their original runs. The checks on a future documentation PR have their own
HEAD, base, tree and run records.

## Run Index

| Run / attempt | Exact GitHub run head | Workflow / result | Tested scope | Limitation |
| --- | --- | --- | --- | --- |
| [43347607972](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43347607972) / 1 | `be79be6a64a6ef2e78f76e920afb335c59bbd49d` | Terraform offline CI / success | Historical main push: 781 Terraform Native tests, 153 Python toolkit tests, and eight pinned Helm renders across two configurations. | This run covers an earlier source revision. AWS behavior and live Kubernetes enforcement are unverified. |
| [45453872145](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/45453872145) / 1 | `b9edba4920a257a91c6bdd26c7f8eca66d532a4d` | Terraform offline CI / success | Owner-designated Step 1 audit Full CI for [PR #102](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/pull/102), with the tested tree matched to PR Safety CI and verified at squash merge. | Source/Offline regression at that PR. Live operations and resource-wide Emulator behavior remain outside the result. |
| [43791639228](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43791639228) / 1 | `5c62dba517c7eb97394f77aaff6479a1315c524e` | AWS Emulator representative verification / success | One disposable `aws_vpc.proof` lifecycle, fourteen safety controls, independent resource checks and cleanup. Separately reviewed and accepted. | The result covers one test resource. The complete VPC Module and real AWS behavior remain outside the demonstrated scope. |
| [44988721098](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/44988721098) / 1 | `a3cf9bcf4de277656c9664bb1a8bf91b57ee6b24` | AWS Emulator Step 2 rehearsal / success | `network` with 16 resources and no interface endpoints, and `api` with seven resources. All fourteen controls, required lifecycle operations, independent checks and resource/material/process/host cleanup passed. | API-state rehearsal. Packet forwarding, DNS, Cognito sign-in, REST invocation, EKS and the other DEV Roots remain outside this result. |
| [45910291601](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/45910291601) / 1 | `1a5e3d41da208407caaf8ac9a4702c3458367a18` | AWS Emulator offline contracts / success | The exact release source tree. 67 Offline verification tests, 18 rehearsal-gate tests, 43 ledger tests and 18 ledger records checked. | Static/offline contracts only. A different workflow supplies Full CI and separate Emulator runs exercise resource lifecycles. |

The earlier full CI counts and date are retained in the
[baseline README verification records](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/blob/1a5e3d41da208407caaf8ac9a4702c3458367a18/README.md#validation-and-ci).
The source evidence for run 45910291601 is the
[Offline Contracts job](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/45910291601/job/140216754354).
The [CI policy](portfolio-verification-policy.md#ci-execution-policy--owner-decision-2026-11-23)
describes when PR Safety CI, Full CI and Offline Contracts apply.

## Step 1 and Step 2 Acceptance

- **Step 1 — Source / Offline complete.** The Owner's OD-01 closure on 2026-11-24
  accepted the DEV source and offline audit. The
  [Step 1 audit and acceptance record](step1-audit-report.md#714-subsequent-owner-decisions-and-policy-release-post-audit)
  ties the PR #102 results to its tested tree and lists remaining runtime,
  governance and deployment questions.
- **Step 2 — closed with limited Emulator evidence.** The Owner accepted the
  measured network and API scenarios and documented residual risks, including
  the F21 eight-versus-nine service mismatch. The
  [Step 2 closure record](step2-emulator-rehearsals.md#closure-owner-decision-2026-11-24)
  retains the scope, earlier runs, compatibility limits, and untested DEV Roots.
- **Representative VPC demonstration.** The
  [accepted record](portfolio-verification-policy.md#representative-emulator-run-43791639228)
  documents independent review and Owner acceptance for the single-resource
  scenario and retains its limits.

## Durable Records and Verification Limits

The [sanitized Emulator ledger](evidence/emulator-runs/index.md) records formal
runs with their exact attempts, isolation controls, operations, independent
observations, cleanup and unresolved constraints. Its comparison uses a
committed Actions snapshot. The
[record for run 44988721098, attempt 1](evidence/emulator-runs/44988721098-attempt-1.json)
retains the four cleanup outcomes and exclusions. GitHub may expire its run
logs and job summaries.

- `network-full` remains Emulator compatibility blocked. The existing harness
  differs from the committed interface-endpoint inventory and has an observed
  security-group default-egress revoke limitation.
- `tfstate` remains Emulator compatibility blocked by the S3 Control host-prefix
  and TLS gap. The preliminary trial did not verify Terraform resource cleanup.
  `serverless-api`, `platform`, `developer-access` and `registry` are untested
  for the Step 2 Emulator lifecycle.
- Full Step 2 end-to-end lifecycle and Kubernetes runtime E2E are untested.
  IAM enforcement, real network behavior, Cognito login and production deployment
  remain outside the evidence. Fake-only receipts establish behavior of the
  tested contract and fixtures.
- [Architecture limits and roadmap](mvp-release-scope.md#security-hardening-and-full-architecture-roadmap)
  and [original offline MVP acceptance](offline-mvp-acceptance.md) retain the
  boundaries for broader or earlier milestones. CORE PORTFOLIO COMPLETE and
  PORTFOLIO COMPLETE remain undeclared.
