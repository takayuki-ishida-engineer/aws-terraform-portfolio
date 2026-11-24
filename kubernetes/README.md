# Private Kubernetes runtime, NP-1 isolation and NP-2P Gateway ports

Credential-free source and offline verification, not a deployed cluster. The
accepted starting main is `a4f0a9b8b0a810976c7ab305001729463443b27b`, with
[post-V4 CI42757339642](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42757339642)
(678 native / 153 toolkit tests; 13 initialized Terraform configurations).
That is historical V5 provenance. Work then followed Master Policy v14
(2026-11-12) (historical; the controlling policy is the latest Owner-approved
MASTER_POLICY, identified under the rule in [AGENTS.md](../AGENTS.md)), using the user-authorized complete 24-page text; the original PDF
SHA-256 remains unverified. NP-1 starts from main
`684fe8ad69eb3d04bf8e44c65210343df70b2ae5`, whose
[push CI43175377665](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/43175377665)
completed successfully. That existing CI result does not establish this PR HEAD's
regression result or any Kubernetes Live behavior.

## Step 1 item 6b-A: project-derived names and DEV certificates

Finding F11 (2026-11-20): every Kubernetes object the project creates is named
`<project>-<purpose>` from a new required input, `runtime.project`, which follows the
DEV roots' project rule. The input moves to interface_version 2 (version 1 is
refused) and renderer evidence to runtime_contract_version 3 (4 since F18, 5 since C1, below). The project must match
the Platform output: cluster `<project>-dev-eks` and controller role
`<project>-dev-role-lbc`. Both gateway Secret names start with `<project>-`.

| Object | Before | Now |
| --- | --- | --- |
| Ingress namespace, controller `--watch-namespace` | `istio-ingress` | `<project>-ingress` |
| Istio revision (and the revision-suffixed Istio objects) | `portfolio-v1` | `<project>-v1` |
| Gateway Deployment, Service, ServiceAccount, Role and binding; TGB | `portfolio-gateway` | `<project>-gateway` |
| Istio Gateway | `portfolio-backend` | `<project>-backend` |
| Binding writer SA, Role, RoleBinding | `portfolio-binding-writer` | `<project>-binding-writer` |
| Controller Role and RoleBinding; TGB admission policy and binding | `portfolio-target-registration` | `<project>-target-registration` |
| Ingress-namespace admission policy and binding | `portfolio-no-lb-service` | `<project>-no-lb-service` |
| Reserved controller ingress class | `portfolio-disabled` | `<project>-disabled` |
| Application namespace / ServiceAccount | `portfolio-app` / `portfolio-application` | `<project>-app` / `<project>-application` |
| PeerAuthentication / AuthorizationPolicy / NetworkPolicy | `strict` / `default-deny` / `default-deny` | `<project>-strict-mtls` / `<project>-default-deny` / `<project>-default-deny` |
| Gateway server and client CA Secrets | free-form | `<project>-gateway-tls` / `<project>-gateway-client-cacert` |

Names the upstream products fix stay: `kube-system`, `istio-system`, the CRDs,
`aws-load-balancer-controller*` (including the webhook Service and its Secret
`aws-load-balancer-controller-tls`), Istio's `istiod-*`/`istio-*` objects (suffixed with
the revision), `istiod-default-validator` and the Istio CA Secret `cacerts`. The label
key `portfolio.runtime/ingress` is a label, not an object name, and is unchanged.
Object content, selectors, RBAC, admission, TLS and the inventory size (62) are
otherwise unchanged; only the names move. The source templates hold `${project}`
tokens that the renderer fills in.

Finding F4: [`scripts/local-workflow/k8s_certs.py`](../scripts/local-workflow/README.md#kubernetes-certificates-k8s_certspy)
creates the DEV certificates and keys on the operator's workstation and registers
the four Secrets this runtime references (`cacerts`, `aws-load-balancer-controller-tls`,
`<project>-gateway-tls`, `<project>-gateway-client-cacert`) directly in the cluster.
Nothing enters Git, Terraform or a CI log. Its `public.json` supplies the runtime's
certificate-derived inputs. The runtime is still not deployable: the nodes cannot
pull the public images while node egress stays closed (finding F18, open).

## Step 1 item 6b-B2: digest-pinned private images (F18)

Finding F18 (Owner-approved method, 2026-11-20): the runtime pulls its three images
from a private ECR mirror in the DEV account, pinned by the upstream index digest,
so node egress stays closed. This change covers the image lock, the renderer and the
validator only. The `registry` root that creates the repositories (B1) and the
operator script that copies the images with `skopeo copy --all --preserve-digests`
(B3) follow in their own pull requests. Nothing is created in AWS by this change.

| Purpose | Upstream (tag) | Index digest | `linux/amd64` child | Platforms |
| --- | --- | --- | --- | --- |
| `istio-pilot` | `docker.io/istio/pilot` (`1.32.0`) | `sha256:5383df36…acca78` | `sha256:13f71f5e…cbd7ad` | linux/amd64, linux/arm64 |
| `istio-proxy` | `docker.io/istio/proxyv2` (`1.32.0`) | `sha256:b8d47c6d…a688d0` | `sha256:ad94413f…8a9f76` | linux/amd64, linux/arm64 |
| `lbc` | `public.ecr.aws/eks/aws-load-balancer-controller` (`v3.6.2`) | `sha256:fd51f0ec…dc2d94` | `sha256:a2caa8b5…97c9f2` | linux/amd64, linux/arm64 |

- **Lock and proof.** [`images.lock.json`](images.lock.json) records each image's
  source, chart-pinned tag, index digest and media type (Docker manifest list v2),
  its platforms and their child digests, and where and when it was observed.
  [`image-manifests/`](image-manifests/) holds the raw index bytes as fetched
  anonymously from the registry (metadata only; no layer was pulled). Their SHA-256
  is the pinned digest, and the tests re-derive every digest, platform and the
  required `linux/amd64` child from those bytes. A single-platform manifest, an
  unknown manifest type, a missing `linux/amd64` entry, a tag different from the
  chart pin or any digest mismatch is refused. The LBC index was read on the
  operator's workstation because ECR Public refused the cloud session's anonymous GET
  (data limit); its SHA-256 equals the digest the cloud session observed by HEAD.
- **References.** The renderer derives
  `<account_id>.dkr.ecr.ca-central-1.amazonaws.com/<project>-dev-ecr-<purpose>@<digest>`
  from the input's account and project. It sets istiod's `image`, the injected proxy
  and init images (`global.proxy.image`, `global.proxy_init.image`), the gateway
  container and the controller container to these references, and points
  `global.hub` at the private registry so no unpinned fallback can reach a public
  one. Evidence moves to runtime_contract_version 4 and records the lock's SHA-256.
- **Istio webhook `caBundle` (finding F23, item 6c-B3b-C1, contract 5).** istiod
  writes the `caBundle` of its three webhooks at run time, so the bundle never carries
  one:
  - The renderer pins `base.validationCABundle` and `istiodRemote.injectionCABundle`
    to empty and stops if a `caBundle` appears.
  - The validator requires the exact webhook entries with a service-only
    `clientConfig`.
  - The controller webhook keeps the public CA.
  - Only istiod's `values-<project>-v1` record changes; evidence moves to
    runtime_contract_version 5.
- **Injection templates.** The pinned istiod chart ships eight injection templates.
  The renderer keeps `sidecar` (the default) and `gateway`, byte-for-byte as in the
  chart, and removes `grpc-simple`, `grpc-agent` (which uses the public
  `busybox:1.28`), `waypoint`, `kube-gateway`, `agentgateway` and
  `agentgateway-waypoint` (Gateway API and ambient, which are disabled). The default
  template, policy and selectors are unchanged.
- **Validation.** The validator, written separately from the renderer, re-proves the
  lock from the raw manifests and requires every image in the bundle to be exactly
  the reference for its workload. It checks that the injector values and the recorded
  Istio values use the same references, that only the two templates remain and equal
  the chart's files, and that no public registry name (or `busybox`) appears anywhere
  in the bundle. This is offline bundle validation, not Kubernetes admission.

**Verified and not verified.** The tests prove that the rendered bundle contains
only the pinned references and only the two templates. The following are NOT_TESTED:
- what Istio does with a Pod that names a removed template (the Istio documentation
  does not say), and with a `sidecar.istio.io/proxyImage` annotation;
- admission on a real cluster: no fail-closed behaviour is guaranteed there;
- the image pull itself, through the ECR endpoints and the S3 path over NAT.

An image allowlist admission policy and node IAM changes are out of scope. The
allowlist is recorded as a separate security improvement candidate in the
[audit report](../docs/step1-audit-report.md).

## NP-2P Gateway port alignment and compatibility

NP-2P implements the explicitly approved NP-2A option A from main
`df7b5370e5c502c6768b6bb53a7e9f551428e416`. Every Kubernetes backend port derives
from the existing reviewed private_ingress.backend_target_port input, **p**:

| Component | Previous runtime | NP-2P |
| --- | --- | --- |
| Terraform NLB listener | TCP443 | TCP443, unchanged |
| Terraform target group / static SG backend / TCP health | p / p / traffic-port | unchanged |
| Gateway Pod | p | p |
| Service.port / targetPort | 443 / p | p / p |
| TGB serviceRef.port | 443 | p |
| Istio Gateway HTTPS server | 443 | p |
| TGB admission port condition | 443 | exact p |
| Gateway readiness / liveness | 15021 | 15021, unchanged |

The primary8443 and alternate9444 are synthetic test selections, not approved Live
ports. NLB IP targets receive traffic directly on registered Pod IP:p; the
Service supplies endpoint discovery. External NLB clients still target443. TLS
terminates only at the MUTUAL Gateway; port alignment grants no network allowance.

Input JSON shape/version1 and nested Platform interface_version1 stay unchanged:
backend_target_port already means the actual backend port. No duplicate port input
or Terraform output is introduced. The **generated runtime semantics change**;
renderer evidence and test reports then required runtime_contract_version=2 (F11
later raised it to 3, above). The Kubernetes v1/List/API versions, names, selectors
and ownership were unchanged by NP-2P.
Current consumers are renderer CLI, independent validator/capture tests and the
existing CI report reconciliation. All are updated or verified against the new
semantics. No external publisher/consumer or deployed resource is assumed absent
or migrated; actual output custody/consumer approval remains OPEN.

Runtime inputs now reject low ports: integer1024–65535 only, with15000–15090
conservatively reserved for Istio control/admin/probe/DNS/metrics ports. This
does not claim every port in that interval is listening. The generic Platform
contract remains1–65535; this selected runtime profile deliberately accepts a
narrower subset. Previously accepted low/reserved inputs fail before Helm runs.
No Root validation or actual backend allocation is silently changed.

Migration requires reviewing each consumer, actual Platform backend provenance
and namespace/target inventory; pair a newly rendered contract2 evidence report
with its exact manifest/input hashes. Reject legacy reports even if tagged as
otherwise complete; reject old443 manifests even if their hashes are recomputed.
Never patch only Service, TGB, Gateway or CEL in an operational rollout. A future
approved operator must coordinate Service/endpoints, Gateway config, fail-closed
admission and TGB reconciliation, inspect deregistration/finalizers/health and
retain a coherent known-good bundle. Rollback restores the matching renderer,
validator, templates, manifest/evidence and admission contract together with
traffic quiesced as needed; old443→high-port output is not CNI-compatible merely
because it was restored. No CNI activation, enforcement bypass or IAM expansion
is an approved recovery step. No deployment/migration/rollback was executed here.

P0-PORT's **source alignment** is implemented and offline-tested; actual Envoy
listeners, target registration, TLS/health and packet behavior remain NOT_TESTED.
P0-WEBHOOK (Istiod443→15017/LBC443→9443) and P0-CNI (actual version/build/startup
enforcement) remain OPEN. This does not establish cluster-wide NetworkPolicy
compatibility. NP-2B/NP-3/V7-A, DNS/other allow policies and CNI activation require
separate authorization.

## Ownership and artifacts

| Owner | Contract |
| --- | --- |
| Platform Terraform / private_ingress | Existing internal NLB, TCP443 listener, IP target group, static SG rules; dedicated controller IRSA Role and inline policy. No individual Pod registrations. |
| Kubernetes platform operator | Pinned controller, ServiceAccounts, Istio base/istiod/gateway, ClusterIP Service, guarded TargetGroupBinding (TGB), mesh policies. No second load balancer or Terraform-owned setting writer. |
| Controller | Register/deregister Pod IPs on the one approved target group; no ELB creation/deletion/modification or SG writes. |
| Future application release | Real image, workloads, routes, exact SPIFFE allow rules, readiness and rollback. No fake application is included. |
| External PKI/secret custodian | Server/client trust, webhook credentials and Istio CA initialization/renewal/compromise response; no secret values in this repository or Terraform. In DEV, `k8s_certs.py` generates and registers them, and renewal means generating and registering new material. |

[dependencies.lock.json](dependencies.lock.json) locks official package URLs,
versions, published SHA-256 values and the Helm executable hash. Chart archives
are intentionally vendored to keep rendering independent of chart-repository
availability. No executable tool binary is committed. Official HTTPS/index
checksums were verified; no detached-signature verification is claimed.

| Artifact | Chart / application | SHA-256 of package |
| --- | --- | --- |
| Helm linux-amd64 | 3.22.1 | `896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea` |
| AWS Load Balancer Controller | 3.6.2 / v3.6.2 | `9255bf39873b6cb31106dbe61dc87c3617bff4197783b5b94381811a13f99c3c` |
| Istio base | 1.32.0 / 1.32.0 | `505ce0d9b6cf5d73a9998728fdf0821510a237470567e6c332164937c6850f05` |
| Istiod | 1.32.0 / 1.32.0 | `17d275e3661e2e943a1ab630386bacab0cda76ea007978351a3a10fe9f4050d4` |
| Istio gateway | 1.32.0 / 1.32.0 | `61d1d24cd0d6f79fbd8a3367c7e0e0b873989309db673b64c13a37c3fbc5c546` |

Official repositories are https://aws.github.io/eks-charts and
https://blob.istio.io/istio-release/charts. The latter redirects to
https://istio-release.r2.istio.io/charts; actual index and all three package GETs
succeeded through that path. The retiring Google-hosted repository is not used.

Istio1.32's published software matrix lists Kubernetes1.33–1.37. Offline cases use
1.34 and 1.35; these are synthetic compatibility fixtures, not an approved EKS
Live allocation. LBC3.6.2 requires Kubernetes1.22+; the actual chart values, CRDs,
flags and rendered resources were inspected. All images use exact release tags,
never latest. No claim of immutable image digest attestation or live version
availability is made. Live approval must verify EKS/add-on/node and image compatibility.

## Reproducible rendering and inputs

Use [the minimal input contract](environments/dev/README.md). It is an explicit
reviewed extract of Platform outputs plus required runtime selections, not whole
Terraform State. No authenticated discovery, remote-state data source, kubeconfig
or output publication service is introduced. Authenticity, read access, custody
and evidence of real resource existence remain OPEN.

The following commands are entirely local; `--fixture` explicitly permits only
the synthetic test contract. Real rendering must omit that flag and supply a
separately approved non-secret input file. Rendering never installs anything.

```sh
python3 kubernetes/tools/install_helm.py --destination /tmp/v5-tools/helm
PYTHONDONTWRITEBYTECODE=1 python3 kubernetes/tests/check_runtime.py --helm /tmp/v5-tools/helm
PYTHONDONTWRITEBYTECODE=1 python3 kubernetes/tools/render.py \
  --input kubernetes/tests/fixtures/runtime.json --fixture \
  --helm /tmp/v5-tools/helm --output /tmp/v5-runtime.json
```

The output is a Kubernetes `v1/List`. The renderer uses four real `helm template`
processes, offline capabilities with an explicit Kubernetes version and no API
validation, plugins or credential discovery. Reviewed post-render changes are
part of the source contract: remove unused controller CRDs and broad RBAC,
replace chart TLS sentinel output with external references, enforce fail-closed
webhooks, remove disabled Istiod Gateway API controller RBAC, require external
Istio CA, pin Gateway proxy image/probes/ports and add namespaced admission guards.
The upstream gateway injection template/revision is retained. Runtime injection
and readiness remain external prerequisites. Unreviewed raw chart installation
would bypass these controls and is not the supported deployment artifact.

The controller chart's certificate-generation branch is never entered: all three
webhookTLS inputs are non-secret sentinel strings, the exact sentinel Secret is
verified and removed, and no Secret is present in the resulting bundle. An
external public CA bundle is required for the webhook configurations; the
external chart-named webhook TLS Secret must exist before controller startup.

## Exact rendered inventory and deployment order

| Ordered stage | Objects | Responsibilities / external readiness barrier |
| --- | ---: | --- |
| namespaces | 2 | istio-system and `<project>-ingress`, restricted Pod security and revision labels |
| base | 16 | 15 pinned Istio CRDs and validator; CRDs established before custom resources |
| controller | 13 | 2 pinned LBC CRDs, Deployment/Service, external-IRSA SA, narrowed cluster and namespaced RBAC, two webhooks; external TLS Secret, role effectiveness and webhook readiness required |
| istiod | 12 | revision `<project>-v1`, SA, config, roles, Deployment/Service, injector/validator; required external cacerts and ready injection/validation CA |
| gateway | 5 | SA, Deployment, ClusterIP Service, Role/Binding; wait for actual revision injection, SDS and readiness |
| mesh_security | 5 | existing application Namespace, identity SA, STRICT PeerAuthentication, deny-default AuthorizationPolicy and all-Pod Ingress/Egress default-deny NetworkPolicy |
| admission | 4 | two ValidatingAdmissionPolicies and enforcing Deny bindings; verify actual admission health before TGB writes |
| binding_writer | 3 | dedicated SA, exact-name Role and Binding |
| ingress | 2 | MUTUAL Gateway and exact TGB; writer SA submits TGB only after controller/Service/admission ready |
| Total | 62 | previous 61 objects plus one NetworkPolicy; 17 CRDs, 3 Deployments and 3 ClusterIP Services; no application, Secret, LoadBalancer Service or VirtualService |

These are review/deployment stages, not authorization to run apply/install. Do not
submit the entire List with an unrestricted human actor: the TGB guard accepts
only the exact binding-writer SA and controller SA. The future approved workflow
must submit ordered subsets with the appropriate identities and readiness waits.
There is no Helm release/cluster deployment in V5. A later deployment owner must
review post-render apply/upgrade/rollback custody, CRD preservation and admission
bootstrap; installing unmodified Helm releases alongside these objects is double
ownership and unsupported.

## NP-1 application default deny and NP-2 / NP-3 gates

See the [NP-2A flow and VPC CNI compatibility contract](../docs/np2-network-policy-flow-contract.md)
for Service/Pod port conflicts, recommended alternatives and gated future flows;
this design does not modify the current bundle or authorize allow policies/CNI activation.

[application-security.yaml](platform/istio/application-security.yaml) adds exactly
one `networking.k8s.io/v1` NetworkPolicy, `<project>-app/<project>-default-deny`.
`podSelector: {}` selects every Pod in that namespace; both Ingress and Egress
are explicit and both rule lists are empty. The existing Namespace, ServiceAccount,
STRICT PeerAuthentication and empty-ALLOW AuthorizationPolicy retain their owners.
The existing renderer loads all five declarations into `mesh_security`, with the
Namespace before the policy. Future application releases must wait for policy
installation and verified enforcement before starting Pods. No application Pod,
allow rule, extra Namespace, Helm ownership or Terraform resource is introduced.

NetworkPolicy is network isolation; STRICT mTLS authenticates mesh transport and
AuthorizationPolicy controls mesh requests. None substitutes for the others.
Namespace NetworkPolicies grant traffic additively: an extra allow policy can
reopen traffic even while default-deny remains. The offline validator therefore
permits exactly this one policy in the entire current bundle, checks its complete
specification independently of inventory, and rejects extra policies. This is a
repository/rendered-bundle check, **not live admission enforcement**. Other cluster
policies, authorizers, RBAC, cluster admins and Node paths are not inspected here.
Runtime creation/update/deletion prevention, policy ownership/RBAC, enforcement
observability and drift checks require separately reviewed operational controls.

No CNI settings are changed. The existing
[VPC CNI add-on](../infra/modules/eks_platform/addons.tf) uses
`configuration_values = jsonencode({})`; this does not establish that NetworkPolicy
enforcement or strict startup mode is active. NP-1 does not enable either.
Without an enforcing plugin, a valid NetworkPolicy alone does not block packets.
With enforcement, this all-deny policy deliberately provides no application DNS,
xDS/CA, database or Gateway exceptions: future application sidecars/Pods must not
be represented as ready until the necessary reviewed paths exist.

The following are **OPEN communication contracts**, not approved allow policies
or permission to begin NP-2/NP-3:

| Future review | Required ownership / evidence before an allow or CNI change |
| --- | --- |
| CoreDNS TCP/UDP53 | Resolve actual DNS path, namespace/Pod labels, endpoints and possible NodeLocal/host-network behavior. Limit destination and both protocols; do not allow every kube-system Pod or arbitrary DNS resolver |
| Istiod xDS/CA | Review actual revision/Service/endpoints and required TCP15012, bootstrap/renewal and return traffic; keep exact source/destination selectors and mesh identity boundaries |
| Gateway application ingress | NP-2P aligns Service and Gateway backend port p; NLB stays443. Review actual Gateway namespace/Pod selectors, future application destination port and both-end policy selection. This grants no arbitrary ingress |
| Webhooks and health | Distinguish API-server-to-webhook paths, Node/kubelet probes, controller9443, Istio15017 and Gateway readiness15021/TCP target health as applicable; identify which namespaces/Pods and enforcement hooks each actually traverses |
| Application-to-application | Require actual workload and route inventory, protocol/ports, Pod labels and owner; exact SPIFFE/AuthorizationPolicy remains separate from L3/L4 allow rules |
| PostgreSQL TLS | Approve actual private endpoint/address semantics and TCP5432, server CA/hostname verification, DB identity and SG ownership. No DB address or Secret is invented |
| AWS APIs, metrics and logs | Identify actual IRSA/STS/image/API/telemetry dependencies and endpoint/NAT/DNS paths; review bounded egress, credential/redaction/cost controls and CNI capabilities, not a blanket public CIDR exception |
| Labels / ServiceAccounts | Define who may change Namespace/Pod labels and workload templates, selectors and SAs. Standard NetworkPolicy selectors are not native ServiceAccount authorization; do not infer identity isolation from a mutable label |
| VPC CNI enforcement / strict mode | Separately approve actual compatible add-on/node/kernel configuration, `enableNetworkPolicy` and `NETWORK_POLICY_ENFORCING_MODE=strict`, policy-agent readiness and cluster-wide startup impact including CoreDNS. Verify normal-mode startup gaps and strict-mode failure behavior; these are future changes, not enabled here |
| Node / hostNetwork / policy limits | Review supported EC2 Linux Pod paths, ownerReferences, hostNetwork/Node exemptions, SG interactions and other policy tiers. Standard namespaced NetworkPolicy is not complete Node or cluster traffic isolation |
| CNI transition / startup / rollback | Approve canary, baseline packet-denial tests, application/DNS/xDS readiness and reboot/upgrade coverage, failure detection and private recovery access. Roll back to a reviewed CNI/policy revision with workloads quiesced as needed; do not simply delete deny policies, switch to permissive startup or add allow-all to recover |

Before NP-2, approve the actual flow/selector/identity matrix and its negative tests.
Before NP-3, approve CNI enforcement/version support, ordering, startup failure,
operational mutation prevention, packet tests and rollback custody. Review the
[official EKS limitations](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html),
[strict-mode configuration](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html)
and [known issues](https://docs.aws.amazon.com/eks/latest/userguide/network-policies-troubleshooting.html)
for the selected future versions; no version upgrade or Live action is authorized.
All future traffic allowances remain absent and unapproved in NP-1.

For teardown, first remove future application traffic/releases and the TGB via
its approved writer, verify controller deregistration/finalizers and actual TG
inventory, then Gateway/mesh/controller runtime and webhooks/admission in safe
order. Retain required CRDs/permissions until all dependent objects are gone.
Only then may an independently approved workflow remove controller IAM/static
Platform infrastructure and finally Network resources. Inventory AWS-created and
Kubernetes-dependent resources explicitly; a Terraform graph alone is insufficient.

## Registration-only IAM and Kubernetes isolation

The exact IRSA subject is
`system:serviceaccount:kube-system:aws-load-balancer-controller`, audience
`sts.amazonaws.com`, actual EKS Federated provider and exact issuer condition keys.
Only RegisterTargets/DeregisterTargets writes are allowed, on the actual owned TG.
Six EC2/ELB Describe actions require wildcard resources under official service
reference data; aws:RequestedRegion limits them to ca-central-1. Describe access
is not claimed completely resource-scoped. No PassRole, AssumeRole, secret reads,
ModifyTargetGroup/Attributes, ELB creation/deletion or SG mutation is granted.

LBC has no universal TGB-only switch: main.go still registers Ingress
reconciliation. Layered defenses are therefore required: reserved class,
watch-namespace=`<project>-ingress`, Service/Gateway feature gates off, no Service
mutator, backend-SG management off, narrowed Kubernetes permissions, admission
and least-privilege AWS IAM. Region/VPC/cluster are explicit, avoiding IMDS discovery
with the existing hop-limit-one nodes. The controller can read scoped Service/Pod
metadata and update only the named binding/status; it cannot create arbitrary TGBs.
The separate binding-writer can CREATE (Kubernetes cannot resourceName-limit
CREATE), but a fail-closed cluster-wide admission policy constrains actor,
namespace/name, ARN, VPC, type, Service, port and disallows networking/AssumeRole.
Another admission policy forbids Ingress and external Services in the ingress
namespace. Existing cluster admins, other bindings/authorizers, CEL execution and
all live admission paths still require external review; these files do not prove
effective cluster-wide isolation.

Pinned TGB targets_manager.go uses registration/health operations rather than
ModifyTargetGroup/Attributes, so those example-policy writes are excluded.
networking_manager.go can still discover/garbage-collect controller-tagged SG
rules without TGB networking. The role cannot perform those writes. A clean
existing TGB/SG inventory is mandatory; reconciliation failure must not be solved
by silently expanding IAM. Any required ownership-conflicting privilege is a
separate review blocker, not implicitly approved by this implementation.

## TLS, mesh and connectivity

NLB remains internal TCP443 passthrough. TGB ip targets select Service port p,
whose port and targetPort equal the actual Terraform target group backend port. The
Gateway chart Deployment exposes that port; selectors match actual Pod labels.
No Proxy Protocol, NLB TLS termination, automatic LB or Pod-IP Terraform resource
is added. TCP health checks cannot establish TLS, authorization or application health.

Istio Gateway has one HTTPS server on Service/backend port p, exact hostname, MUTUAL,
TLS>=1.2, explicit server credentialName, explicit client CA credential and one or
two exact SHA-256 SPKI pins. CA trust and expected-client key authorization are
separate controls. caCertCredentialName must end `-cacert`: pinned Istio SDS
recognizes that suffix as a root-only CA request. Its referenced external Secret
contains the reviewed CA under supported ca.crt/cacert semantics; the server
credential must use a different, non-cacert Secret name. Do not use the offline
synthetic SPKI for deployment. No certificate or key values are rendered.

Istiod requires external `cacerts` with ca-cert.pem, ca-key.pem, root-cert.pem and
cert-chain.pem; missing data prevents startup rather than silently selecting an
unreviewed self-signed CA. External CA custody is distinct from Gateway TLS PKI.
Trust domain, hostname, pins and resource requests/limits are required inputs.
Rendered containers explicitly drop all capabilities, use RuntimeDefault seccomp,
non-root/read-only settings and no host namespaces. All three Deployments use one replica in the supplied DEV worker AZ. This is not
an approved capacity calculation or HA guarantee. The app namespace is restricted
PSS plus revision injection, STRICT and empty ALLOW rules (default deny). Future
application SPIFFE principals must be exact, reviewed allow policies. Standard
application sidecar iptables initialization needs a reviewed Istio CNI/equivalent
under restricted PSS; that future requirement is not permission to weaken security.

Four additional Terraform rules explicitly allow custom ClusterSG→NodeSG TCP15017
for Istio webhooks and NodeSG→NodeSG TCP15012 for Istiod XDS/CA, with paired ingress
and egress. Existing DNS/LBC9443 paths are unchanged. This does not prove Pod-SG,
AWS-managed EKS SG residual exposure, private API/ECR/STS/DNS, webhook or runtime
connectivity. Future app data/monitoring and NetworkPolicy paths require separate
scoped review, without blanket CIDRs/all-protocol rules.

Certificate issuance/trust scope, server hostname/SNI verification by the future
REST VPC Link V2 client, client certificate presentation compatibility, rotation,
expiration monitoring, compromise and revocation-equivalent controls remain OPEN.
No valid TLS/mTLS handshake or actual target registration is inferred from schemas.

## Offline evidence and limits

[Runtime tests](tests/README.md) perform eight actual Helm renders over two
positive configurations, validate 124 objects, reject129 rendered security
mutations (existing77 plus20 NP-2P,11 F11 and21 F18),54 invalid input contracts,29 missing/malformed/fabricated evidence
cases,38 image-lock faults (19 cases, each refused by the validator and by the renderer) and5 injection-template faults. Core schemas come from pinned Kubernetes v1.34.1 OpenAPI; CRD schemas are
from the exact pinned charts. NP-1 extends the selected schema definitions with
NetworkPolicy and its reference closure from the **same** v1.34.1 source, whose
existing SHA-256 and Git blob identity were checked. Only the derived subset hash
changes in dependencies.lock.json; Helm/chart versions/hashes, Python libraries
and Kubernetes fixtures are unchanged. Published IntOrString/quantity representations are
normalized. No external schema fetch, live CEL/admission execution or API-server
validation is claimed. Vendored parser/schema libraries (whitespace-normalized only) are hash-verified before
import and retain their upstream licenses.

Affected Terraform evidence: Child36 native, Root38 native and EKS Child52 native;
61 ingress semantic / 12 IAM / 21 capture-fault / 8 dependency checks per Child and
Root scope; 12 actual unsafe Terraform source cases; Root15 required inputs and
11 Network fields rejected. EKS73/21/10 per scope remain intact. These categories
are separate from native counts. Current Full CI totals, including the initialized
configurations sharing one locked AWS 6.72.0 binary, are in the latest Full CI job summary ("Summarize actual validation results").
Local checks are not completed exact-HEAD GitHub Actions evidence.

All G01–G07 remain OPEN. No account/resource existence, State custody, publication,
private deployment path, effective IAM/RBAC, runtime capacity, pricing or teardown
is established. DEV Live requires separate authorization, cumulative actual cost
<=JPY10,000 and complete verified removal within72 hours. The Secrets Manager
30-day recovery conflict remains unresolved. No authenticated AWS/Kubernetes calls,
real State, apply/destroy/import, cluster Helm/kubectl operations or merge.
NP-1 Emulator: **NOT_APPLICABLE** (Kubernetes offline change); Kubernetes Live
communications and CNI enforcement: **NOT_TESTED**. No NP-2/NP-3/V7-A is started.

## Consequential upstream sources

- [LBC chart and source v3.6.2](https://github.com/kubernetes-sigs/aws-load-balancer-controller/tree/v3.6.2)
- [LBC TGB target calls](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.2/pkg/targetgroupbinding/targets_manager.go)
- [LBC SG reconciliation](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.2/pkg/networking/networking_manager.go)
- [LBC installation and TGB policy example](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.2/docs/deploy/installation.md)
- [AWS service authorization data](https://servicereference.us-east-1.amazonaws.com/v1/elasticloadbalancing/elasticloadbalancing.json)
- [Istio support matrix](https://istio.io/latest/docs/releases/supported-releases/)
- [Istio Helm installation](https://istio.io/latest/docs/setup/install/helm/)
- [Pinned Istio Gateway API fields](https://github.com/istio/api/blob/1.32.0/networking/v1alpha3/gateway.proto)
- [Pinned SDS CA resource construction](https://github.com/istio/istio/blob/1.32.0/pilot/pkg/security/model/authentication.go)
- [Pinned SDS root-only response](https://github.com/istio/istio/blob/1.32.0/pilot/pkg/xds/sds.go)
- [Istio mutual ingress TLS](https://istio.io/latest/docs/tasks/traffic-management/ingress/secure-ingress/)
- [Istio external CA](https://istio.io/latest/docs/tasks/security/cert-management/plugin-ca-cert/)
- [Kubernetes admission policies](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
