# Step 2 emulator rehearsals

Step 2 of the [step plan](deployment-configuration.md#8-step-plan): rehearse the
real DEV roots in the official AWS Emulator under all fourteen
[mandatory controls](../AGENTS.md#mandatory-official-aws-emulator-safety-controls),
then an end-to-end apply and destroy. Each run needs its own Owner authorization.
The harness and its controls are described in
[`scripts/emulator-rehearsal`](../scripts/emulator-rehearsal/README.md).

Emulator results are never evidence of real AWS deployment, IAM enforcement,
networking, DNS, cost, availability or recovery. Formal acceptance of each
rehearsal needs independent review and an Owner decision. CORE PORTFOLIO
COMPLETE and PORTFOLIO COMPLETE remain undeclared.

## Rehearsal 1: network root (2026-11-18)

**Authorization:** the Owner's instruction of 2026-11-18 to start the emulator
verification once everything up to Step 2 was in order. The Owner also approved,
through the session's environment approval prompt, a personal cloud environment
that allows only `downloads.aws.com` for the pinned emulator package. No AWS API
host and no credential were added.

### Tested code and tools

| Item | Value |
| --- | --- |
| Tested SHA (Terraform source) | `ec3519069ef0fa710e94012ba9db06578e15cf13` (main after PR #70): `infra/services/dev/ca-central-1/network` and `infra/modules/vpc`, copied with `git archive` |
| Harness | `scripts/emulator-rehearsal/rehearse.py`, SHA-256 `0769389771cb7adeea5507ab3be08e5dca0e514ebc36b1decb169c08b58709dc`, as committed in this pull request |
| Emulator | 1.0.385 (`1.0.385-1` amd64 DEB, SHA-256 `5344b39e…3f5`, publisher `98BCF336A3BE53B734E967C52E5BF49BD940F624`), as pinned in `versions.json` |
| Terraform / AWS provider / AWS CLI | 1.17.0 (SHA-256 verified) / 6.72.0 (committed network lock, `init -lockfile=readonly` from a local mirror) / 2.35.0 (SHA-256 and GPG verified) |
| Execution environment | Claude Code cloud container. The emulator, Terraform and the AWS CLI ran in a fresh `unshare --net --mount` namespace, as uid 1000 with no capabilities and `no_new_privs`, on a namespace-private tmpfs. No Docker and no GitHub Actions minutes were used for the lifecycle |
| Inputs | Committed `terraform.tfvars` of the network root, with `project = "step2"`, `aws_account_id = "000000000000"` and the run tags `VerificationRun` and `Phase` in a disposable tfvars file. The operational root and its State were not touched |

### Results

| Run | Scenario | Resources | Result |
| --- | --- | --- | --- |
| `20261118080527-1` | A: committed values without `interface_endpoints` | 16: VPC, 4 subnets, Internet gateway, public and 2 per-AZ private route tables, 4 associations, NAT EIP, NAT gateway, NAT route | **Every operation PASS, all 14 controls PASS** |
| `20261118080742-1` | B: committed values (full) | 26: scenario A plus the endpoint security group, its HTTPS rule and 8 interface endpoints | Plan PASS. Create **BLOCKED by an emulator fidelity gap** (below). Recovery destroyed the 17 created resources with a reviewed destroy plan and verified absence; controls 1–11 and 14 PASS |

Scenario A operations, in order:

| Operation | Result | Evidence |
| --- | --- | --- |
| Isolation (controls 6, 7) | PASS | Only `lo`, loopback routes only, separate namespace; public STS and EC2 addresses `ENETUNREACH` |
| Startup, TLS, telemetry (1, 2, 4, 5) | PASS | Exact `https://127.0.0.1:9297`; CA-verified health; the system trust store rejects the emulator certificate |
| Authentication (3, 8) | PASS | Signed STS gives `000000000000` / `user/emulator`; a changed secret gives `SignatureDoesNotMatch`; a changed key gives `InvalidClientTokenId`; an unsigned request is rejected |
| Provider guard, disposable root (9, 10) | PASS | Override with loopback EC2 and STS endpoints, the emulator CA and `allowed_account_ids = ["000000000000"]`; readonly lock; empty State |
| Plan (11) | PASS | Exactly the 16 reviewed addresses, all `create`, run and default tags on every taggable resource; plan hash checked again before apply |
| Create, API identity (12) | PASS | All 16 State IDs found by `describe-*` with the run tag (where taggable) and not in the baseline; every other new object belonged to the owned VPC (AWS side effects of creating it, such as its main route table and default security group) |
| Read (refresh) | PASS | First refresh: only the reviewed computed fields changed, matching the API. The EIP's association, network interface and private IP came from the NAT gateway. The private route table's computed `route` list came from the separate `aws_route`. Real AWS shows the same. After applying the refresh, a second refresh shows no change |
| Update | PASS | Plan: `update` on the 11 taggable resources, `no-op` on the 4 associations and the route, tags only; the API shows `Phase = updated` |
| No-op plan | PASS | Every resource `no-op` |
| Destroy (13) | PASS | Reviewed saved destroy plan, targets equal to the State IDs; State empty; every owned ID absent from the API; the pre-existing default VPC, subnets, route table, security group and rules unchanged |
| Cleanup (14) | PASS | Emulator stopped; tmpfs with credentials, CA, State, plans and logs emptied, then unmounted with the namespace; no emulator process left on the host |

### Emulator fidelity gap: default egress rule revoke

The AWS provider creates `aws_security_group` and then revokes the default IPv4
egress rule with `IpProtocol=-1, FromPort=0, ToPort=0, CidrIp=0.0.0.0/0`. AWS
treats that as the default rule. Emulator 1.0.385 stores the default rule with no
ports and answers that request with HTTP 400 `InvalidPermission.NotFound`.

A direct API probe in run `20261118080527-1` (an owned, tagged probe group in the
owned VPC, deleted afterwards) recorded:
- `CreateSecurityGroup` adds one egress rule: `-1`, `FromPort` and `ToPort` null, `0.0.0.0/0`;
- the provider-form revoke with ports 0: `InvalidPermission.NotFound`;
- the same revoke without ports: accepted, after which no egress rule remains.

This is not a Terraform defect, and the module is not changed for the emulator.
With this emulator and provider pair, **any root that creates an
`aws_security_group` cannot complete create in the emulator**. That covers the
network root's interface endpoints, and most likely the platform (EKS) and
developer-access roots.

The same probe also exercised one interface endpoint directly through the API
(`com.amazonaws.ca-central-1.sts`, private DNS, one subnet, the probe group). It
returned `available` with 3 DNS entries, and its deletion was verified. That is an
API probe, not a Terraform result.

### Not tested and residual risk

| Item | Status |
| --- | --- |
| `aws_security_group.endpoints`, its ingress rule and the 8 interface endpoints through Terraform | NOT_TESTED (blocked by the gap above) |
| Packet forwarding, NAT, routing, DNS resolution, endpoint reachability | NOT_TESTED; the emulator models API state only |
| Real AWS behavior, quotas, costs, IAM | NOT_TESTED; no real AWS access |
| Other roots (tfstate, platform, developer-access, serverless-api, api) and the end-to-end apply and destroy | NOT_TESTED; each needs its own Owner authorization |

Other residual points:
- The run used a local cloud container rather than the representative GitHub
  Actions workflow. Its evidence is the gate output summarized here; raw State,
  plans, credentials and logs were never kept or uploaded.
- The refresh allowlist is a reviewed judgment that this computed-field
  convergence is normal. It is covered by the offline mutation tests in
  `test_rehearse.py`.
- Options for the security group gap:
  1. accept NOT_TESTED for the security-group paths;
  2. retest with a later emulator release, which needs a reviewed
     `versions.json` update;
  3. report the gap to the emulator maintainers.

  The production modules stay unchanged in every case.
