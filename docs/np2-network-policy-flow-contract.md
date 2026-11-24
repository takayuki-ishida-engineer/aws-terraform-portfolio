# NP-2A NetworkPolicy flow contract and VPC CNI compatibility

> **Naming update (Step 1 item 6b-A, finding F11, 2026-11-20).** This contract
> quotes object names as they were when it was written. The runtime now names every
> object the project creates `<project>-<purpose>`: `portfolio-app` is `<project>-app`,
> `portfolio-application` is `<project>-application`, `istio-ingress` is
> `<project>-ingress`, revision `portfolio-v1` is `<project>-v1` (so `istiod-portfolio-v1`
> is `istiod-<project>-v1`), `portfolio-gateway` is `<project>-gateway`, and the
> application `default-deny` policies are `<project>-default-deny`. Upstream names
> (`istio-system`, `kube-system`, `aws-load-balancer-controller`, `cacerts`) are
> unchanged. Flows, selectors, ports and the policy semantics below are unchanged;
> renderer evidence is runtime_contract_version 5 (C1 left the Istio webhook `caBundle` to istiod; F18 used 4, F11 used 3). See the
> [mapping](../kubernetes/README.md#step-1-item-6b-a-project-derived-names-and-dev-certificates).
> DEV certificates are now generated and registered by `k8s_certs.py` (finding F4);
> the PKI lifecycle obligations in section 4 still apply.

## NP-2P source implementation status

The user explicitly approved option A for NP-2P from main
`df7b5370e5c502c6768b6bb53a7e9f551428e416`. Current runtime source derives all
Kubernetes Gateway backend ports from private_ingress.backend_target_port, p:
Service.port=p, targetPort=p, Pod=p, TGB serviceRef.port=p, Gateway HTTPS server=p
and admission CEL requires exactly p. NLB listener remains TCP443; TG/backend
port, SG rules, traffic-port health check and probe15021 remain unchanged.
Names, namespaces, selectors, MUTUAL/TLS1.2+/CA/SPKI, STRICT/default-deny mesh and
NP-1 network policies, non-root UID1337/restricted PSS and resource writers remain.
Synthetic8443 and alternate9444 fixtures are retained, not Live selections.

The existing minimal input and nested Terraform reference schemas stay version1;
no new or duplicated port input is added. Generated port semantics are versioned
as **runtime_contract_version2** in renderer evidence and test reports. Capture
requires2 and checks actual manifests, rejecting legacy evidence or a rehashed
old443/partially changed bundle. Kubernetes v1/List and resource API versions are
unchanged. The [runtime compatibility/migration/rollback contract](../kubernetes/README.md#np-2p-gateway-port-alignment-and-compatibility)
identifies in-repository consumers and requires separate external-consumer/custody
review; no actual deployment or migration is assumed. Runtime now restricts p to
integer1024–65535, reserving15000–15090 for Istio control/probe use. Platform's
general1–65535 interface remains unchanged and is explicitly wider than this
runtime profile. Unsupported inputs fail closed before rendering.

Affected local suite: two actual configurations/eight pinned Helm renders,
62 resources each/124 full-bundle schema validations,97 rejected rendered
mutations (the existing77 plus20 Gateway cases across both ports),38 rejected
input cases and26 rejected evidence cases. These are source/offline results, not
successful exact-HEAD CI or runtime connectivity. No Terraform/policy/SG/CNI/
webhook ownership changes or new network allowances are part of NP-2P.

**P0-PORT source alignment is implemented; external behavior remains OPEN.**
Actual Envoy listeners, LBC target registration, TLS/health and packets remain
NOT_TESTED. P0-WEBHOOK and P0-CNI remain OPEN; Gateway alignment alone does not
establish cluster-wide NetworkPolicy compatibility. Emulator NOT_APPLICABLE;
Kubernetes Live communication/CNI enforcement NOT_TESTED. No NP-2B/NP-3/V7-A
authorization follows. Sections below retain the NP-2A design baseline and its
pre-NP-2P comparisons; current linked runtime source incorporates this status.

## Authority, baseline and evidence boundary

> The controlling policy is now the latest Owner-approved MASTER_POLICY, identified under
> the rule in [AGENTS.md](../AGENTS.md); the authority statement below is historical.
> NP-2B and NP-3 stay PAUSED (Owner decision 2026-11-24, OD-11).

At that time (historical), Master Policy v14 (2026-11-12) alone governed, using the user-authorized full
24-page text. Original PDF SHA-256 remains unverified. Starting/latest main at
entry: `5f007e8ee4f61cebc7b0aae835ab10e055f744a6`; working tree clean, no open PRs.
NP-2A was documentation/design only; NP-2P's separate approval and implemented
scope are recorded above, without approving any additional phase.
Architecture v2, Terraform1.17.0/AWS6.72.0, all resource addresses, State writers,
NP-1 deny policies, chart versions, manifests and CI remain unchanged.

**NP-2A baseline verdict, before NP-2P:** the Service443 → Pod8443 fixture is supported as a port
translation by Istio/LBC source, but conflicts with the documented Amazon VPC CNI
NetworkPolicy Service/container-port equality requirement. It is **not accepted
as CNI NetworkPolicy-compatible**. This is not a measured packet failure: NP-1
only selects portfolio-app, which has no application Pod/Service; Gateway is in
istio-ingress and CNI enforcement has not been enabled or verified. Block affected
CNI enablement and port-dependent allow implementation until P0 decisions resolve.
Do not disable policies or TLS to make a mock/render appear usable.

Emulator Lifecycle: **NOT_APPLICABLE**. Kubernetes communications, policy-agent
behavior, API admission, injection, TLS handshakes and enforcement: **NOT_TESTED**.
One source-inspection render used four actual pinned charts and verified the
existing62-object bundle; this does not replace completed exact-HEAD CI or prove
that a Pod ever started. No Terraform/emulator regression or live operation ran.

Source-access prerequisite **RESOLVED** on resumption (2026-11-13 JST). The original
S3 GET returned `Tunnel connection failed: 403 Forbidden`. After the user saved
and published the kubernetes.io permission, a fresh verified-HTTPS GET of that
exact official URL returned HTTP200 without a redirect or proxy bypass. Fresh
S1/S2 GETs also returned200 and retain the port-equality/startup constraints below.
The same branch and four uncommitted Markdown changes survived the environment
transition; they were preserved. Latest main still matches the starting SHA and
no competing open PR exists. This closes only the source-access blocker, not any
P0 technical or Live gate.

## 1. Current source, versions and ownership

| Evidence | Actual contract and limitation |
| --- | --- |
| [Application security](../kubernetes/platform/istio/application-security.yaml) | One portfolio-app Namespace, portfolio-application SA, STRICT PeerAuthentication, empty-ALLOW AuthorizationPolicy and all-Pod Ingress/Egress default-deny NetworkPolicy. No application Pod, Service, route, image or DB exists |
| [Renderer](../kubernetes/tools/render.py), [validator](../kubernetes/tools/validate.py), [tests](../kubernetes/tests/check_runtime.py) | Revision portfolio-v1; pinned gateway injection template; exact selectors, Service443/Pod backend port/TGB443 and TLS contracts. NP-1 accepts exactly one NetworkPolicy in the bundle; NP-2B must explicitly extend the approved policy inventory/semantics, not merely remove that protection |
| [Pins](../kubernetes/dependencies.lock.json), [fixture](../kubernetes/tests/fixtures/runtime.json) | Helm3.22.1, Istio1.32.0, LBC3.6.2; Kubernetes1.34 and backend8443 are synthetic, not actual EKS allocation. Alternate runtime test uses1.35/backend9444; no Live selection follows |
| [EKS add-ons](../infra/modules/eks_platform/addons.tf), [version inputs](../infra/modules/eks_platform/variables.tf) | eks_platform exclusively owns VPC CNI/CoreDNS/kube-proxy add-ons. Versions are required inputs; configuration_values=jsonencode({}). Neither actual version compatibility nor enableNetworkPolicy/strict mode is established. v1.20.0-eksbuild.1 in native fixtures is not an operational pin |
| [NLB/TG/listener](../infra/modules/private_ingress/main.tf), [SG rules](../infra/modules/private_ingress/security.tf) | private_ingress owns internal IPv4 NLB TCP443, IP TCP target group on backend_target_port, TCP traffic-port health checks, static SG paths and controller IAM. preserve_client_ip=false, proxy_protocol_v2=false. LBC alone registers Pod IP/port; Terraform owns no dynamic target attachment |
| [Architecture](architecture-v2.md), [V7 contract](v7-rest-private-integration-feasibility.md) | Regional REST/Cognito/private VPC Link → NLB TCP443 → Gateway MUTUAL → STRICT mesh remains the target. V7 ARN/hostname/SNI/ACM identity/output-custody OPENs are not resolved by NetworkPolicy |

Network/platform/api/serverless-api DEV Roots retain separate local State and
single writers. Runtime operator owns rendered policy/Gateway/Service/TGB objects;
application release owner later owns app Pods/Services/labels; EKS owns add-on
configuration. No new Terraform/Kubernetes provider, Root, remote-state reader or
controller SG/TG-settings writer is proposed. Minimal Platform reference provenance
and runtime publication remain separately approved OPENs.

### Kubernetes specification cross-check

The recovered official S3 page and pinned Kubernetes v1.34.1 API definitions S15
agree with the following contract. Current website guidance is not evidence that
a particular EKS add-on implements all optional features or startup guarantees.

- Ingress and egress isolation are independent. For an isolated source/destination
  Pod pair, source egress **and** destination ingress must allow the connection.
  Rule ports and peer conditions must both match; return traffic for an allowed
  connection is implicitly permitted, not a reason to grant arbitrary ingress.
- Standard namespace NetworkPolicies grant a **union** of permissions. Evaluation
  order does not override another allow policy. A default-deny object cannot
  cancel an extra allow-all policy. Deployment order still matters for bootstrap,
  and AWS admin-policy tiers are a separate version-dependent mechanism, not an
  authority to change NP-1's model.
- The subject podSelector selects Pods in the policy's namespace; an empty subject
  selects them all. A peer podSelector alone also means the policy's namespace.
  A peer namespaceSelector alone selects all Pods in matching namespaces; empty
  namespaceSelector means **all namespaces**, not the current namespace. Both
  selectors in the same peer mean AND; separate peers mean OR. Namespace name
  matching uses a verified namespace label, not a fictional namespace field.
- Default-deny egress also blocks DNS. Review actual resolver Pods/labels, DNS
  Service/Pod ports and UDP/TCP53 plus NodeLocal/node-source behavior before an
  exception; no automatic DNS, certificate-renewal or xDS allowance exists.
- Same-Pod/loopback and resident-Node traffic are not fully blockable by this API.
  Generic hostNetwork behavior depends on implementation; AWS specifically
  excludes host-network Pods from its strict-startup default deny. Do not claim
  Node or hostNetwork isolation using these namespaced policies.
- The filtering point relative to Service/source/destination NAT is not portable.
  ipBlock matching can observe a rewritten source or destination; do not infer
  browser, NLB, API-server or ClusterIP identity from topology alone.
- Standard NetworkPolicy does not authenticate TLS/ServiceAccounts, enforce HTTP
  paths, select external FQDNs, provide native security-event logging, or guarantee
  immediate revocation of an already established connection. TCP/UDP and supported
  SCTP are the L4 model; ARP/ICMP and plugin-specific features need separate review.
- S3 requires isolation throughout selected Pods' lifecycle, including init and
  sidecar containers, but gives no generic Kubernetes-API indication of completed
  plugin reconciliation. AWS's documented standard-mode startup allow window
  must not be mistaken for fail-closed enforcement. P0-CNI includes the actual
  agent/version/startup proof and strict-mode prerequisites; creating the policy
  before the Pod or observing readiness alone does not close that gate.

## 2. Gateway port compatibility decision

S1 explicitly says: “For any of your Kubernetes services, the service port must be
the same as the container port. If you’re using named ports, use the same name in
the service spec too.” The pinned CNI v1.20.0 FAQ S5 independently answers that a
container port cannot differ from the Service port. Named-port equality is an
additional naming requirement, not evidence waiving numeric equality. No rule
allowing both443 and8443 cures this documented support limitation.
The existing Gateway Service and Container port are already both named
https-backend; their numeric values still differ.

Current fixture path:

```text
VPC Link client -> internal NLB listener TCP443
  -> registered Gateway Pod IP:8443 (TG backend_target_port8443)
Kubernetes Service443 -> targetPort8443 supplies endpoint discovery/mapping
TGB serviceRef443 -> matching Service -> endpoint port8443
Istio Gateway server443 -> Service-target translation -> Envoy listener8443
```

In IP mode the NLB sends to registered Pod IPs; the ClusterIP Service is not a
second mandatory forwarding hop. LBC3.6.2 endpoint resolver S6 matches Service
port/name to EndpointSlice/Endpoints ports; registration S7 uses endpoint.IP and
endpoint.Port. Istio1.32 resolvePorts S8 translates Gateway Service port into its
targetPort; listener code S9 checks the resolved bind port. Thus these components
can describe443→8443 while the CNI documentation separately disallows the
Service/container mismatch. No claim about actual DNAT/conntrack/enforcement
behavior is made from these code paths.

| Candidate | Future changes / ownership | Security, tests and rollback | Decision |
| --- | --- | --- | --- |
| **A — align Kubernetes to the existing reviewed high backend port** | Keep NLB listener443, actual TG backend port and static SG backend rules. Derive Service.port, targetPort, Pod port, TGB serviceRef and Istio Gateway server port from the same approved backend_target_port. For the fixture only, all become8443. Runtime owns Service/Gateway/TGB; Terraform resources need no port change when backend port is preserved | Keeps UID1337/dropALL/non-root/read-only and TCP passthrough/MUTUAL. Tests must capture actual endpoints, registered port and Envoy listener plus negative mismatches. Update runtime templates, render/validate, CEL TGB port guard, fixtures/tests, inventory assertions if affected and READMEs together. Approve existing Service443 contract revision and consumer compatibility; stop traffic/deregister/reconcile old targets during a separately approved rollback, restore a coherent prior bundle, never claim the old mismatch CNI-safe | **Preferred candidate**, approval required. Select a reviewed unprivileged port >=1024 excluding reserved platform ports, not a new guessed default. Actual backend port remains a required deployment input |
| B — align Service and Pod to443 | Keep NLB443, Service443, TGB443, Gateway server443; future approved Platform backend_target_port443 changes target group/SG port values and runtime Pod port. Preserve resource writers, review Provider plan/replacement/target registration and ownership effects externally | A non-root bind to443 is not inherently incompatible with restricted PSS: the pinned chart already renders pod sysctl net.ipv4.ip_unprivileged_port_start=0; S10/S11 support this approach. Actual admission/node/runtime and Istio listener metadata must be verified. Do not add root/privilege escalation/capabilities as a shortcut. Terraform/native/security fixtures and runtime checks need explicit443 coverage, target/deregistration/SG rollback and low-port tests | Feasible candidate only with node/admission/Envoy evidence and approved TG-port lifecycle. Broader infrastructure impact than A; not selected |
| C — keep443→8443 and only rename ports or add more allow ports | No numeric alignment; same name may help EndpointSlice resolution but does not remove the documented CNI restriction | Cannot claim enforcement/support from Helm, mock plans or emulator. IP targets avoiding ClusterIP does not prove an exemption. Require authoritative version-specific AWS clarification before relying on one | **Not acceptable on present evidence** |

A preserves Architecture v2's external TCP443/mTLS boundary; a Kubernetes Service
port contract is still a reviewed compatibility change, not automatically approved
by this recommendation. Do not add a proxy, second LB, TLS termination, hostNetwork,
plaintext, relaxed PSS or another CNI as an unapproved workaround. Decide runtime
interface/revision and old consumer handling before changing hard-coded443 checks;
no silent semantic change to the existing versioned contract.
Under A, external clients and any future VPC Link HTTPS URI still target NLB443;
the Kubernetes discovery port is not the external listener port. Existing TG
backend metadata and SG rules keep their actual resource-backed values.

**Additional P0:** the render also contains Istiod Service443→Pod15017 and LBC
webhook Service443→named webhook-server→Pod9443. This includes a named-port mapping
already and still has numeric inequality. Fixing the Gateway alone does not prove
cluster-wide CNI compatibility. Determine the equality requirement's exact scope
for API-server/webhook traffic and selected namespaces/agent version, or approve
coherent webhook Service/clientConfig port changes with pinned chart/controller
support. Never blindly change webhook443 or rely on node exemptions to dismiss
it. API-server reachability, CA validation, fail-closed webhooks and SG paths must
survive; no speculative webhook change is authorized by NP-2A.

**Health-check impact:** A preserves the TG backend port and TCP traffic-port
health check, existing NLB/Node SG target-port rules and Gateway readiness/liveness
15021. B changes the TG traffic-port health destination to443 together with its
actual target/SG configuration; Gateway probes remain15021 unless separately
reviewed. In either case, ensure real registered targets and the Envoy listener
match, keep health/probe permissions narrowly scoped, and do not equate TCP health
with MUTUAL TLS, certificate identity or application readiness. Standard
NetworkPolicy has no NLB-SG selector that could replace the existing SG boundary.

## 3. Actual traffic matrix

All rows below are **contracts to resolve, not new allow grants**. “Both” means
source egress and destination ingress must permit a connection when their Pods
are isolated; enabling strict startup globally creates additional bootstrap
obligations even where no namespace policy existed before. Return traffic is not
a separate authorization grant, and NAT/node-source effects require enforcement
evidence. Hostname text is not a native NetworkPolicy FQDN selector.

Known source identities/selectors:

- **APP:** portfolio-app, existing SA portfolio-application is only an identity
  contract; no app Pod/Service/Pod labels or actual runtime Role is present.
- **GW:** istio-ingress, SA portfolio-gateway, Pod labels app=portfolio-gateway and
  istio=portfolio-gateway, revision portfolio-v1; Service selector matches these.
- **ISTIOD:** istio-system, SA istiod-portfolio-v1, Pod selector app=istiod AND
  istio.io/rev=portfolio-v1; Service istiod-portfolio-v1.
- **LBC:** kube-system, SA aws-load-balancer-controller, Pod selector
  app.kubernetes.io/name=aws-load-balancer-controller AND
  app.kubernetes.io/instance=controller. Dedicated registration-only IRSA.
- CoreDNS runtime Namespace/labels, service IP, NodeLocal DNS and Node/control-plane
  source addresses are **not source-proven allocations**. Do not invent labels,
  CIDRs or trust a common kube-dns selector without deployment evidence.

| Flow / current versus future | Source -> destination namespace, selector/address | Protocol; Service -> Pod port / direction | Required policy sides and identity boundary | Implementation status / evidence |
| --- | --- | --- | --- | --- |
| APP -> CoreDNS | Future APP -> actual DNS Pods/namespace/Service or NodeLocal path OPEN; DNS owned by EKS CoreDNS add-on | UDP53 and TCP53; actual Service/container equality and resolver path must be checked; APP egress | APP E required; DNS I if isolated/strict and on enforceable Pod path. Constrain actual resolver selectors/addresses, not all kube-system or arbitrary DNS. DNS response is not authenticated application authorization | OPEN selector/path; no allow until resolved. Current add-on source plus S1/S2 |
| APP -> Istiod xDS/CA | Future APP -> ISTIOD, istiod-portfolio-v1.istio-system.svc from pinned injection config | TCP15012 ->15012; APP egress | APP E + ISTIOD I when isolated/strict. Require actual sidecar identity, trusted CA/token flow, exact revision; forbid opening plaintext xDS15010 merely because chart declares it | Existing destination/port; app selectors, sidecar/bootstrap and renewal behavior OPEN. Renderer and pinned injection S10 |
| GW -> future backend | Existing GW -> future APP; no app Service, selector, hostname, port or route exists | Backend protocol/Service/Pod port OPEN; Gateway egress and APP ingress | APP I and GW E when isolated/strict; require exact workload selectors plus SPIFFE/AuthorizationPolicy and tenant/owner authorization. MUTUAL backend TLS to GW does not grant access to every app | OPEN; **no fabricated backend or allow**. Application-security/Gateway source |
| NLB -> GW targets | Terraform internal NLB -> GW Pod IPs in istio-ingress; NLB source IPs/actual subnet CIDRs not supplied | TCP443 listener -> actual backend port; fixture8443; Service443 ->8443; TCP health traffic-port same target | GW I if isolated/strict; source NLB is not a namespace/Pod selector. preserve_client_ip=false means do not use browser IP as presumed source. Retain NLB/Node SG references; determine actual source/SNAT and narrowly scoped policy match externally. SG identity is not a NetworkPolicy selector | P0 port/source contract. private_ingress + S6/S7; no broad VPC-wide CIDR substitute |
| API server -> Istio webhook | Managed control-plane actor, no invented source Pod/Namespace -> ISTIOD | TCP Service443 ->15017; clientConfig injector443, validator default443 | Destination I if enforced; source is outside namespace E policy. Need proven API-server/node/SNAT source and existing paired custom ClusterSG/NodeSG15017; service TLS/CA and fail-closed admission remain mandatory | P0 webhook port applicability/source; no guessed API-server CIDR. Actual render, SG source, S1 |
| API server -> LBC webhook | Same managed actor -> LBC | TCP Service443 ->named webhook-server ->9443; clientConfig default443 | LBC I if enforced, outside-Pod E not a namespace rule. Existing ClusterSG/NodeSG9443 and CA/admission ownership remain separate from NetworkPolicy | P0 webhook mapping, bootstrap readiness and source. Actual render + S1/S6 |
| Node/kubelet -> probes/health | Actual Node/kubelet identity/address OPEN -> GW / ISTIOD / LBC; NLB health is the distinct row above | GW HTTP /healthz/ready and TCP liveness15021; ISTIOD HTTP /ready8080 and TCP liveness15014; LBC HTTP /readyz and /healthz61779. Future APP probes OPEN | Node/host-origin exemptions mean a namespace policy alone cannot prove denial; do not claim node traffic is fully isolated or add all-node CIDRs as convenience. Confirm probe rewrites after sidecar injection and source handling | Existing probe declarations, actual Node behavior NOT_TESTED; S1/S2/S5 |
| APP -> PostgreSQL TLS | Future APP -> future private DB endpoint/SG; no DB resource/hostname/CIDR exists | TCP5432 target contract; no Kubernetes Service/Pod for managed RDS/Aurora | APP E plus DB SG/network path, not a nonexistent destination NetworkPolicy. Require server CA/hostname verification, reviewed DB auth, owner/tenant authorization; no password in Terraform | OPEN allocations, DNS/IP changes, SG/DB owner and auth. Architecture v2/v14; no allow now |
| APP -> necessary AWS APIs | Future APP -> specific approved AWS endpoints only; exact service/IRSA/endpoint/VPC path OPEN | Normally verified HTTPS443, exact API requirements unset; no destination Pod Service | APP E conditional on real API need; IAM least privilege/OIDC separate from IP policy. FQDNs, endpoint-IP changes/NAT and DNS need a reviewed mechanism, not default0.0.0.0/0 or IMDS access | OPEN; do not invent app AWS permissions. Controller IRSA STS plus actual ELB/EC2 API needs are separate existing runtime/bootstrap dependencies for NP-3 |
| Monitoring/logging/telemetry | Scraper/collector/namespace/SA absent; existing metrics endpoints on GW/ISTIOD/LBC | GW declared15090, annotations reference15020; ISTIOD15014; LBC8080. Actual scrape listeners, collection agents and external destinations/ports OPEN | Selected Pod I for real scraper and collector E as appropriate; app exporter E only if actually selected. Authentication/redaction/retention/cost remain separate. Do not open metrics to all namespaces | OPEN consumer/actual injected ports; no monitoring bundle or broad egress |
| ISTIOD dependencies / certificates | ISTIOD -> actual Kubernetes API endpoint and DNS; external cacerts Secret owned by PKI custodian. External CA/JWKS endpoints not configured | API verified HTTPS443, DNS TCP/UDP53; incoming CA/xDS15012 and webhooks15017 treated above. External provider-specific ports OPEN | ISTIOD E and API/DNS destination path where enforced. Secret access/RBAC/CA custody not granted by NetworkPolicy. Permit renewal/control-plane watches only after actual dependency proof; missing CA must fail closed | OPEN API/DNS/source/cert lifecycle; no generic internet/JWKS allow from chart defaults. Existing external cacerts requirement + S10/S12 |

NetworkPolicy cannot authenticate a ServiceAccount, TLS certificate, SPIFFE
principal or Cognito token. Selectors must use reviewed immutable-in-practice
labels and namespace boundaries; combining namespaceSelector and podSelector in
one peer means AND, whereas separate peers grant OR. Restrict who can mutate
labels, workload templates, SAs and policies, then verify effective authorization
across every ClusterRoleBinding/admission path. No selector/cert is operationally
trusted merely because a manifest declares it.

## 4. Version-aware VPC CNI / Istio prerequisites for NP-3

1. **Choose an actual supported version tuple, not fixture values.** Pinned CNI
   v1.20.0 README S12 says standard NetworkPolicy starts at1.14 and identifies
   NETWORK_POLICY_ENFORCING_MODE from1.17.1. Its chart has agent1.2.3, standard mode
   and enableNetworkPolicy=false; this is upstream comparison, not the EKS add-on's
   approved deployment configuration. Its compatibility table stops at Kubernetes
   1.33; absence of1.34 is neither compatibility proof nor proof of rejection.
   Current S1/S2 discuss1.21 for standard+admin policies while retaining1.14 setup
   examples. Do not project new admin-policy/feature claims onto v1.20 or silently
   upgrade. Require reviewed EKS build/platform/Kubernetes/AMI/kernel/agent/add-on
   configuration-schema evidence before NP-3; authenticated discovery is outside
   Codex and separately authorized. No admin ClusterNetworkPolicy is proposed.
2. **Activation and startup are distinct.** enableNetworkPolicy must be explicitly
   supported/enabled and agent/controller ready; strict startup additionally needs
   NETWORK_POLICY_ENFORCING_MODE=strict. Standard mode has a default-allow startup
   window; strict mode starts new eligible Pods deny-all until rules converge.
   NP-1 all-deny alone does not provide DNS/xDS/CA readiness. Cover CoreDNS,
   istiod, LBC, Gateway and other affected non-hostNetwork system Pods before any
   global strict-mode change; validate policy installation/programming before
   launching future apps. Removing the agent with strict mode still set can
   prevent Pod creation (S12). No startup/renewal failure may be hidden by allow-all.
3. **Node/agent prerequisites and exclusions.** S1/S2 require EC2 Linux, kernel5.10+
   and supported EKS platform; Fargate/Windows and hostNetwork are not equivalent
   enforcement paths. The present IPv4 cluster must use applicable IPv4 policy.
   Review eth0 versus additional interfaces/Multus, controller-owned Pod
   ownerReferences, supported workload controllers, SG-for-Pods mode and TC/eBPF
   conflicts such as bandwidth plugin (S5/S12); do not assume universal coverage
   or silently change CNI/Node security to force it. Node traffic and non-TCP/UDP
   protocols need explicit residual-risk treatment.
4. **PolicyEndpoint is not a Terraform/runtime writer opportunity.** EKS manages
   policyendpoints.networking.k8s.aws and generated PolicyEndpoint objects (S1).
   Verify controller reconciliation and BPF/agent readiness/8162 metrics/8163
   health without manually owning/deleting them; inspect quotas including the
   documented24 port/protocol combinations per CIDR across all policies.
5. **Pinned Istio behavior, not latest defaults.** S4 is contextual current guidance;
   S13/S14 pinned1.32 chart templates already contain optional NetworkPolicies.
   They permit port-based ingress without source peers and allow-all egress; they
   are disabled in the current bundle and **not suitable to enable as-is** under
   this contract. Do not add them alongside reviewed policies: allowances add.
   Gateway injection does not create a namespace policy for portfolio-app or prove
   effective data-plane filtering. Preserve revision/PSS and external cacerts/SDS,
   inspect actual injected endpoints/probes and the safe low-port model if B is
   chosen. Standard app-sidecar initialization under restricted PSS still needs
   a separately reviewed Istio CNI/equivalent; no privileged init shortcut.
6. **Lifecycle security.** Denying DNS/API/xDS/CA can block IRSA, certificate renewal,
   admission and recovery even after initial startup succeeds. Test fresh nodes,
   Pod restarts, CA/key rollover and control-plane outage/restoration; cache-hit
   health is insufficient. Review current agent/version fixes for policy deletion,
   connection tracking and fail-closed behavior; no expiry/revocation guarantee
   follows from a NetworkPolicy. No real PKI generation or import is authorized.

## 5. NP-2B responsibilities and staged implementation gates

- Runtime owner retains the existing NP-1 default-deny resource/address and mesh
  authentication/authorization policies. Add only independently reviewed flows to
  explicit namespaced resources; no duplicate writer or broad chart policy.
- First resolve P0 port semantics and actual DNS/revision/bootstrap selectors.
  A minimal proven DNS/xDS app egress contract may be independently implementable
  after those decisions, but an app Service/backend ingress cannot be invented
  to fill missing ports/labels. Defer any flow without an approved consumer.
- Policies for istio-system, istio-ingress or kube-system are distinct ownership
  and bootstrap changes. They require explicit scope, both-end flow evidence and
  exact resource inventories; portfolio-app scope is not blanket authority.
- NP-2B must extend the current exact-one-policy validator to an exact approved
  policy/flow graph. Preserve unsolicited/additive allow rejection, forbidden
  wildcard peers, both-direction isolation, Namespace identity and mesh checks.
  Inventory, expected stages and CI counts derive from actual expanded renders;
  no CI change or policy exception is implemented by this design PR.
- NP-3 alone may propose add-on/schema/configuration changes in the existing EKS
  owner. Retain pinned Terraform/provider, one State writer and explicit Root
  choices. Approve activation independently from the policy manifests.

## 6. Positive / negative / mutation verification plan

These are **proposed tests, not executed PASS counts**:

| Layer | Required evidence |
| --- | --- |
| Offline positive | Actual pinned renders, complete inventory, exact scopes/selectors, Namespace-before-policy ordering, approved flow graph and resolved Service/Pod/TGB/Gateway/TG/SG port consistency; preserve NP-1/STRICT/empty-ALLOW until an app authorization contract is approved |
| Offline negatives | Missing real selector/port/namespace/endpoint metadata; wrong account/scope/reference; Service443/Pod8443 or any partially applied candidate; wrong TGB ServiceRef or CEL guard; wildcard/OR-expanded peers; app/DB/telemetry flow with no owner; unsupported activation tuple; duplicate/missing/failed/malformed evidence |
| Security mutations | Delete deny, narrow its selector, remove either direction, add unrestricted allow policy,0.0.0.0/0 or all-namespace peer, allow plaintext15010, corrupt DNS TCP/UDP coverage, broaden xDS sources, weaken mesh/TLS/PSS, fabricate CIDRs/endpoint or swap labels. Prove rejection by independent generated-manifest/flow checks, not source strings only |
| Port candidate tests | For A: preserve NLB443/backend resource identities and actual endpoint port, change all runtime Service/TGB/Gateway guards coherently; for B: prove safe non-root443 binding/admission/Envoy listener and reviewed Terraform port plan. Test partial changes, duplicate endpoint writers, stale consumers and rollback manifests |
| NP-3 configuration | Actual locked-provider mock-plan JSON for unchanged owners and explicit supported CNI settings; negatives for mode/agent mismatch, wrong version/schema, missing system bootstrap policies. Preserve all Terraform/Python/IAM/security/mutation regressions |
| Separately approved real enforcement | Actual packet allow/deny from selected/nonselected Pods, both policy sides, Node/hostNetwork limitations, fresh-Pod startup with no policy-ready gap, DNS/xDS/webhook/probe/API behavior, no-policy deletion/agent failure/upgrade/reboot and established-connection handling. No emulator/mock/Helm result is substituted for these observations |

## 7. OPEN decisions, owners and acceptance gates

| ID | Alternatives / risk | Resolution and approver |
| --- | --- | --- |
| P0-PORT — source aligned by NP-2P; runtime OPEN | User approved A; current runtime aligns ports, preserves Terraform and rejects partial/legacy bundles. B and C remain unselected historical comparisons | Independent exact-HEAD source/CI review and external consumer/operational verification still required; no actual registration/TLS/packet or CNI-compatibility acceptance follows |
| P0-WEBHOOK | Istiod443→15017 and LBC443→9443, control-plane source treatment and CNI equality applicability | AWS version-specific clarification or proven supported equal-port webhook/clientConfig arrangement; EKS/runtime/security owners approve, preserve CA/fail-closed and SG ownership before NP-3 |
| P0-CNI | Fixturev1.20/EKS1.34 versus newer documented1.21 behavior, actual build/kernel/agent/schema unspecified | User/EKS owner approve evidence-backed EKS/add-on/Node tuple and all system bootstrap flows. Do not assume latest docs certify old builds or auto-enable admin policies |
| P1-DNS-XDS | Actual DNS namespace/labels/Service/NodeLocal path and app source selectors unknown; renewal/bootstrap can deadlock | Network/runtime/app owners approve exact both-end graph and verified behavior; DNS/xDS are not broad namespace egress grants |
| P1-APP-DB-AWS | Backend workload/ports/Service/identities, DB endpoint/SG, actual AWS API and monitoring consumers absent | Application/database/identity owners supply real approved contracts. Defer every unproven allow; scoped token/tenant and TLS/DB auth remain separate |
| P1-PRIVILEGE | Label/SA/policy mutations, other installed additive/admin policies, Node/hostNetwork exemptions, restricted-PSS sidecar setup | Platform/security owners approve effective RBAC/admission/drift/audit coverage and residual risk; offline validation is not runtime enforcement |
| P1-LIFECYCLE | Strict-mode startup, CA/IRSA renewal, webhook readiness, CNI/agent transition and rollback | Runtime/EKS/operations owners approve staged rollout and failure/recovery tests before activation. No unsafe permissive recovery shortcut |
| P1-V7 | Existing REST ARN/backend hostname/SNI/client-certificate and minimal-output provenance decisions | Retain V7 contract gates; API/PKI/State owners decide separately, no assumption that NP fixes mTLS feasibility |
| P2-ACCESS — RESOLVED | Historical kubernetes.io403; same official S3 URL now returns200 after user Save/Publish | Fresh verified HTTPS and official-specification cross-check completed. No bypass/mirror; this access result closes no technical P0 or runtime approval |
| P2-OBSERVATION | Policy drop telemetry, quotas, log redaction/retention, capacity and cost | Operations/security owners approve bounded evidence/monitoring; no telemetry resource or fixed allocation here |

## 8. Safe order, rollback and unperformed work

1. Independently review NP-2A and explicitly approve the selected port contract,
   DNS/xDS/system scope, owners and remaining P0 resolution. Do not start NP-2B
   merely because this documentation PR exists or CI succeeds.
2. In a separately authorized implementation, reconcile port/interfaces and their
   guards atomically, then create only approved deny/allow bundles and affected
   positive/negative/mutation evidence. Keep no-app/unknown-flow areas fail-closed.
3. Before any actual activation, approve version tuple, private recovery access,
   source inventory and backup/known-good bundle; pre-stage all affected system
   policies, then validate policy controller/agent and enforcement readiness.
   Exact canary/upgrade steps depend on supported EKS add-on semantics, not a
   guessed parallel CNI installation. No second add-on writer.
4. Only then, under separate external execution authority, activate reviewed CNI
   configuration/strict mode with node/Pod restart and bootstrap checks, followed
   by genuine denial/renewal/health tests. Apply app policies before future app
   rollout; a readiness probe alone is insufficient acceptance.
5. On failure, quiesce/isolate affected application traffic, use the approved
   private recovery identity, preserve diagnostics, restore a coherent known-good
   policy/port/CNI tuple and verify target registration and system readiness.
   Review supported BPF/conntrack/agent cleanup/restarts before rollback; do not
   delete deny policies/PolicyEndpoints, remove a strict-mode agent, add allow-all,
   disable TLS or downgrade CNI blindly. Unsupported safe rollback blocks rollout.

No allow manifest, port change, add-on activation, Terraform/State operation,
AWS/Kubernetes authentication, certificate/secret generation or cluster connection
is part of NP-2A. No successful communication/enforcement/capacity/price/teardown
claim follows from source inspection. G01–G07 remain OPEN; any separately selected
DEV Live retains cumulative JPY10,000, complete verified72-hour removal and the
unresolved Secrets Manager30-day recovery conflict. No merge, branch deletion,
NP-2B/NP-3/V7-A auto-start or policy PDF update.

## Official references and pinned source

- **S1:** [EKS NetworkPolicy considerations](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html).
- **S2:** [EKS configuration and strict startup](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html).
- **S3:** [Kubernetes NetworkPolicy concepts](https://kubernetes.io/docs/concepts/services-networking/network-policies/) — fresh direct retrieval HTTP200 after approved domain publication; cross-check recorded above.
- **S4:** [Current Istio NetworkPolicy guide](https://istio.io/latest/docs/setup/additional-setup/network-policy/) — contextual; pinned templates below control version-specific findings.
- **S5:** [VPC CNI v1.20.0 NetworkPolicy FAQ](https://github.com/aws/amazon-vpc-cni-k8s/blob/v1.20.0/docs/network-policy-faq.md). Legacy GPU/AMI and rollback comments are version/context-limited, not universal current operating instructions.
- **S6:** [LBC v3.6.2 endpoint resolver](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.2/pkg/backend/endpoint_resolver.go).
- **S7:** [LBC v3.6.2 registration manager](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.2/pkg/targetgroupbinding/resource_manager.go).
- **S8:** [Istio1.32.0 Service-to-listener port resolution](https://github.com/istio/istio/blob/1.32.0/pilot/pkg/model/gateway.go).
- **S9:** [Istio1.32.0 Gateway listener construction](https://github.com/istio/istio/blob/1.32.0/pilot/pkg/networking/core/gateway.go).
- **S10:** [Istio1.32.0 Gateway injection template](https://github.com/istio/istio/blob/1.32.0/manifests/charts/istio-control/istio-discovery/files/gateway-injection-template.yaml).
- **S11:** [Kubernetes v1.34.1 safe-sysctl admission check](https://github.com/kubernetes/kubernetes/blob/v1.34.1/staging/src/k8s.io/pod-security-admission/policy/check_sysctls.go). Static compatibility, not actual admission evidence.
- **S12:** [VPC CNI v1.20.0 README](https://github.com/aws/amazon-vpc-cni-k8s/blob/v1.20.0/README.md) and [chart settings](https://github.com/aws/amazon-vpc-cni-k8s/blob/v1.20.0/charts/aws-vpc-cni/values.yaml).
- **S13:** [Istio1.32.0 Gateway chart NetworkPolicy](https://github.com/istio/istio/blob/1.32.0/manifests/charts/gateway/templates/networkpolicy.yaml).
- **S14:** [Istio1.32.0 Istiod chart NetworkPolicy](https://github.com/istio/istio/blob/1.32.0/manifests/charts/istio-control/istio-discovery/templates/networkpolicy.yaml).
- **S15:** [Kubernetes v1.34.1 NetworkPolicy API types](https://github.com/kubernetes/kubernetes/blob/v1.34.1/staging/src/k8s.io/api/networking/v1/types.go) — pinned additive/selector/port API semantics; no claim of live API validation.
