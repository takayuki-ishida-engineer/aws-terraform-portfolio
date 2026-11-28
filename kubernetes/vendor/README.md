# Locked offline dependencies

Chart .tgz files are intentional source artifacts downloaded from the official
repositories, not executable tool binaries. Versions, URLs and published package
SHA-256 values are in [dependencies.lock.json](../dependencies.lock.json).
Istio package GETs used the official blob.istio.io → istio-release.r2.istio.io path.
Helm is downloaded to temporary storage and checked against upstream and locked
archive/executable hashes; no remote installer is executed.

pyyaml6.0.3 and fastjsonschema2.21.2 are pure-Python source subsets from
the exact upstream commits in the lock, with original and whitespace-normalized source hashes and
LICENSE files retained. No pip installation or external runtime dependency fetch
is needed. The schema subset contains the192-definition dependency closure of the
15 core kinds used here from Kubernetes v1.34.1 official OpenAPI; upstream Git blob
and full-source/subset hashes are recorded. Custom CRD schemas come from the
pinned charts. Nothing fetches schema refs over the network during validation.
These are structural/semantic offline checks, not a Kubernetes API server.

## Redistributed Helm charts

The following charts are redistributed as unmodified upstream archives. Their
published package SHA-256 values are recorded in `../dependencies.lock.json`.
All four are licensed under Apache License 2.0; the license text is provided
alongside the archives in [kubernetes.LICENSE](kubernetes.LICENSE).

| Archive | Upstream source | Copyright / attribution |
| --- | --- | --- |
| `aws-load-balancer-controller-3.6.2.tgz` | [aws/eks-charts, 3.6.2](https://github.com/aws/eks-charts/tree/ab312b0418cbd62d647439cae5a54ba0962f297c/stable/aws-load-balancer-controller) | Amazon.com, Inc. or its affiliates; AWS Load Balancer Controller contributors |
| `base-1.32.0.tgz` | [Istio 1.32.0, base](https://github.com/istio/istio/tree/19cc19624069db78ce5c6940b7be94c540eecfb0/manifests/charts/base) | Istio Authors |
| `istiod-1.32.0.tgz` | [Istio 1.32.0, istiod](https://github.com/istio/istio/tree/19cc19624069db78ce5c6940b7be94c540eecfb0/manifests/charts/istio-control/istio-discovery) | Istio Authors |
| `gateway-1.32.0.tgz` | [Istio 1.32.0, gateway](https://github.com/istio/istio/tree/19cc19624069db78ce5c6940b7be94c540eecfb0/manifests/charts/gateway) | Istio Authors |

The AWS chart's upstream [NOTICE](https://github.com/aws/eks-charts/blob/ab312b0418cbd62d647439cae5a54ba0962f297c/NOTICE) is reproduced below:

> Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.

The Istio Base chart includes generated CRDs based on the Apache-2.0-licensed
[Istio APIs](https://github.com/istio/api/tree/97748e4cb005). The chart archives
are not repacked or modified by this repository.
