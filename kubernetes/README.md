# V5 private Kubernetes ingress runtime foundation

Credential-free source and offline verification, not a deployed cluster. The
accepted starting main is `a4f0a9b8b0a810976c7ab305001729463443b27b`, with
[post-V4 CI42757339642](https://github.com/takayuki-ishida-engineer/aws-terraform-portfolio/actions/runs/42757339642)
(678 native / 153 toolkit tests; 13 initialized Terraform configurations).
Master Policy v11 requirements supplied by the user govern this work; the external
PDF was unavailable and is not claimed independently read.

## Ownership and artifacts

| Owner | Contract |
| --- | --- |
| Platform Terraform / private_ingress | Existing internal NLB, TCP443 listener, IP target group, static SG rules; dedicated controller IRSA Role and inline policy. No individual Pod registrations. |
| Kubernetes platform operator | Pinned controller, ServiceAccounts, Istio base/istiod/gateway, ClusterIP Service, guarded TargetGroupBinding (TGB), mesh policies. No second load balancer or Terraform-owned setting writer. |
| Controller | Register/deregister Pod IPs on the one approved target group; no ELB creation/deletion/modification or SG writes. |
| Future application release | Real image, workloads, routes, exact SPIFFE allow rules, readiness and rollback. No fake application is included. |
| External PKI/secret custodian | Server/client trust, webhook credentials and Istio CA initialization/renewal/compromise response; no secret values in this repository or Terraform. |

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
| namespaces | 2 | istio-system and istio-ingress, restricted Pod security and revision labels |
| base | 16 | 15 pinned Istio CRDs and validator; CRDs established before custom resources |
| controller | 13 | 2 pinned LBC CRDs, Deployment/Service, external-IRSA SA, narrowed cluster and namespaced RBAC, two webhooks; external TLS Secret, role effectiveness and webhook readiness required |
| istiod | 12 | revision portfolio-v1, SA, config, roles, Deployment/Service, injector/validator; required external cacerts and ready injection/validation CA |
| gateway | 5 | SA, Deployment, ClusterIP Service, Role/Binding; wait for actual revision injection, SDS and readiness |
| mesh_security | 4 | application Namespace, identity SA, STRICT PeerAuthentication and deny-default AuthorizationPolicy |
| admission | 4 | two ValidatingAdmissionPolicies and enforcing Deny bindings; verify actual admission health before TGB writes |
| binding_writer | 3 | dedicated SA, exact-name Role and Binding |
| ingress | 2 | MUTUAL Gateway and exact TGB; writer SA submits TGB only after controller/Service/admission ready |
| Total | 61 | 17 CRDs, 3 Deployments and 3 ClusterIP Services; no application, Secret, LoadBalancer Service or VirtualService |

These are review/deployment stages, not authorization to run apply/install. Do not
submit the entire List with an unrestricted human actor: the TGB guard accepts
only the exact binding-writer SA and controller SA. The future approved workflow
must submit ordered subsets with the appropriate identities and readiness waits.
There is no Helm release/cluster deployment in V5. A later deployment owner must
review post-render apply/upgrade/rollback custody, CRD preservation and admission
bootstrap; installing unmodified Helm releases alongside these objects is double
ownership and unsupported.

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
watch-namespace=istio-ingress, Service/Gateway feature gates off, no Service
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

NLB remains internal TCP443 passthrough. TGB ip targets select Service443, whose
required targetPort equals the actual Terraform target group backend port. The
Gateway chart Deployment exposes that port; selectors match actual Pod labels.
No Proxy Protocol, NLB TLS termination, automatic LB or Pod-IP Terraform resource
is added. TCP health checks cannot establish TLS, authorization or application health.

Istio Gateway has one HTTPS server on Service443, exact hostname, MUTUAL,
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
positive configurations, validate 122 objects, reject 58 rendered security
mutations, 18 invalid input contracts and 19 missing/malformed/fabricated evidence
cases. Core schemas come from pinned Kubernetes v1.34.1 OpenAPI; CRD schemas are
from the exact pinned charts. Published IntOrString/quantity representations are
normalized. No external schema fetch, live CEL/admission execution or API-server
validation is claimed. Vendored parser/schema libraries (whitespace-normalized only) are hash-verified before
import and retain their upstream licenses.

Affected Terraform evidence: Child36 native, Root38 native and EKS Child52 native;
61 ingress semantic / 12 IAM / 21 capture-fault / 8 dependency checks per Child and
Root scope; 12 actual unsafe Terraform source cases; Root15 required inputs and
11 Network fields rejected. EKS73/21/10 per scope remain intact. These categories
are separate from native counts. Expected independent full CI is 686 native
(678+8), 153 toolkit, 13 initialized configurations / one locked AWS6.72.0 binary.
Local checks are not completed exact-HEAD GitHub Actions evidence.

All G01–G07 remain OPEN. No account/resource existence, State custody, publication,
private deployment path, effective IAM/RBAC, runtime capacity, pricing or teardown
is established. DEV Live requires separate authorization, cumulative actual cost
<=JPY10,000 and complete verified removal within72 hours. The Secrets Manager
30-day recovery conflict remains unresolved. No authenticated AWS/Kubernetes calls,
real State, apply/destroy/import, cluster Helm/kubectl operations, merge or V6.

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
