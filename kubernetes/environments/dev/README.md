# Required DEV runtime input

No deployable account values are committed here. Supply a separately reviewed
JSON document to [the renderer](../../tools/render.py), with exactly these fields:

- `interface_version: 2`, `fixture: false`.
- `controller_identity`: the exact additional Platform output (interface_version,
  scope, role_arn, oidc_issuer, oidc_provider_arn, namespace, service_account,
  target_group_arn, cluster_name, kubernetes_version, active_workload_az).
- `private_ingress`: an approved minimal projection containing only
  interface_version, scope, target_group_arn, vpc_id, backend_target_port.
- `runtime`: project, backend_hostname, gateway_tls_secret, gateway_client_ca_secret,
  expected_client_spki, trust_domain, webhook_tls_secret, webhook_ca_bundle,
  istio_ca_secret and resources.

`project` (finding F11) follows the DEV roots' project rule and names every
Kubernetes object the project creates `<project>-<purpose>` (for example
`<project>-ingress`, `<project>-gateway`, `<project>-app`, revision `<project>-v1`).
It must match the Platform output: cluster_name `<project>-dev-eks` and role_arn
ending `:role/<project>-dev-role-lbc`. Both gateway Secret names start with
`<project>-`. [`k8s_certs.py generate`](../../../scripts/local-workflow/README.md#kubernetes-certificates-k8s_certspy)
writes every certificate-derived runtime value (Secret names, SPKI pin, webhook CA
bundle) to its `public.json`; the resources and Platform values come from elsewhere.

Each scope is exactly environment/account_id/partition/region; environment=dev,
partition=aws and region=ca-central-1 must match. Target-group/account/OIDC references
must agree. Resources requires explicit controller/istiod/gateway requests and
limits (cpu and memory); these are reviewed selections, not capacity approval.
Gateway CA name must end -cacert and differ from the server credential name;
Istio CA name is cacerts and webhook Secret name is aws-load-balancer-controller-tls.
expected_client_spki is one or two base64 SHA-256 public-key hashes. webhook_ca_bundle
is only the base64 public CA certificate, never any private key or Secret payload.
All actual Secret initialization is external; missing referenced Secrets must fail
startup closed. No Terraform output/State or committed environment file contains them.

The [synthetic fixture](../../tests/fixtures/runtime.json) uses fixture=true,
reserved test scope and non-secret placeholders. It is rejected without explicit
--fixture and must never become an operational manifest. Runtime input rejects
unknown/missing fields, unresolved tokens, mismatched scopes, invalid names, ports,
pins and incompatible software versions. Declared network references are not
proof of AWS resource existence. Output publication/authenticity/access and
single-writer State custody remain OPEN; do not distribute complete State.

NP-2P retained this input schema/version1 and the nested Platform version1; F11
moved the input to version 2 (adding `runtime.project`) and refuses version 1. The
backend port must be an integer1024–65535 outside the conservatively reserved
Istio range15000–15090. Platform's general1–65535 schema is unchanged; its wider
range is not permission to use low/control ports in this runtime profile.
All Kubernetes Gateway backend ports now use that one input; NLB remains443.
Generated evidence requires runtime_contract_version3 (F11; NP-2P used 2). Review and migrate old
Service/TGB/Gateway443 consumers as a coordinated versioned bundle; old evidence
or a partial manifest update is rejected. The [compatibility and rollback contract](../../README.md#np-2p-gateway-port-alignment-and-compatibility)
does not implement publication or prove any deployed consumer has been migrated.

See [runtime ownership, stages and operational barriers](../../README.md).
The renderer connects to neither Kubernetes nor AWS. Only `k8s_certs.py register`
and `delete` reach the cluster, from the operator's workstation.
