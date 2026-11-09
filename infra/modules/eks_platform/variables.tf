variable "expected_scope" {
  description = "Explicit workload scope; provider restrictions belong to Root. Initial catalog is commercial ca-central-1."
  type        = object({ environment = string, partition = string, region = string, account_id = string })
  nullable    = false
  validation {
    condition     = contains(["dev", "stg", "prod"], var.expected_scope.environment) && var.expected_scope.partition == "aws" && var.expected_scope.region == "ca-central-1" && can(regex("^[0-9]{12}$", var.expected_scope.account_id))
    error_message = "Expected scope must identify dev/stg/prod, aws, ca-central-1 and an explicit 12-digit account."
  }
}
variable "network_reference" {
  description = "Reviewed minimal subset of Network v1 outputs, including public exclusion IDs and routing metadata. This is not discovery or provenance/authentication."
  type = object({
    interface_version                 = number
    scope                             = object({ environment = string, partition = string, region = string, account_id = string })
    routing_mode                      = string
    vpc_id                            = string
    vpc_cidr                          = string
    private_subnet_ids                = map(string)
    public_subnet_ids                 = map(string)
    subnet_azs                        = object({ private = map(string) })
    private_route_table_ids_by_subnet = map(string)
    public_route_table_id             = string
    nat_gateway_ids_by_az             = map(string)
  })
  nullable = false
  validation {
    condition     = try(var.network_reference.interface_version == 1 && var.network_reference.scope == var.expected_scope && var.network_reference.routing_mode == "per_az", false)
    error_message = "Network interface/version/environment/account/partition/Region and per-AZ routing must match expected scope."
  }
  validation {
    condition = try(can(regex("^vpc-([0-9a-f]{8}|[0-9a-f]{17})$", var.network_reference.vpc_id)) &&
      cidrnetmask(var.network_reference.vpc_cidr) != "" &&
      tonumber(split("/", var.network_reference.vpc_cidr)[1]) >= 16 && tonumber(split("/", var.network_reference.vpc_cidr)[1]) <= 28 &&
    cidrhost(var.network_reference.vpc_cidr, 0) == split("/", var.network_reference.vpc_cidr)[0], false)
    error_message = "Network must contain a syntactically valid VPC ID and canonical IPv4 VPC /16-/28."
  }
  validation {
    condition = try(length(var.network_reference.private_subnet_ids) >= 2 && length(var.network_reference.public_subnet_ids) > 0 &&
      toset(keys(var.network_reference.private_subnet_ids)) == toset(keys(var.network_reference.subnet_azs.private)) &&
      toset(keys(var.network_reference.private_subnet_ids)) == toset(keys(var.network_reference.private_route_table_ids_by_subnet)) &&
      alltrue([for k, id in var.network_reference.private_subnet_ids : trimspace(k) != "" && can(regex("^subnet-([0-9a-f]{8}|[0-9a-f]{17})$", id))]) &&
      alltrue([for k, id in var.network_reference.public_subnet_ids : trimspace(k) != "" && can(regex("^subnet-([0-9a-f]{8}|[0-9a-f]{17})$", id))]) &&
      length(distinct(concat(values(var.network_reference.private_subnet_ids), values(var.network_reference.public_subnet_ids)))) == length(var.network_reference.private_subnet_ids) + length(var.network_reference.public_subnet_ids) &&
      alltrue([for az in values(var.network_reference.subnet_azs.private) : can(regex("^${var.expected_scope.region}[a-z]$", az))]) &&
      alltrue([for id in values(var.network_reference.private_route_table_ids_by_subnet) : can(regex("^rtb-([0-9a-f]{8}|[0-9a-f]{17})$", id)) && id != var.network_reference.public_route_table_id]) &&
      can(regex("^rtb-([0-9a-f]{8}|[0-9a-f]{17})$", var.network_reference.public_route_table_id)) &&
      alltrue(flatten([for k, az in var.network_reference.subnet_azs.private : [for j, other in var.network_reference.subnet_azs.private : (az == other) == (var.network_reference.private_route_table_ids_by_subnet[k] == var.network_reference.private_route_table_ids_by_subnet[j])]])) &&
      length(distinct(values(var.network_reference.nat_gateway_ids_by_az))) == length(var.network_reference.nat_gateway_ids_by_az) &&
    alltrue([for az, id in var.network_reference.nat_gateway_ids_by_az : can(regex("^${var.expected_scope.region}[a-z]$", az)) && can(regex("^nat-([0-9a-f]{8}|[0-9a-f]{17})$", id))]), false)
    error_message = "Network needs unique private/public IDs, complete private AZ/table maps, correct AZ Region and private tables distinct from the public table."
  }
}
variable "cluster_name" {
  description = "Required approved operational cluster name; conservative <=40 characters leaves room for dedicated IAM/LT names."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$", var.cluster_name))
    error_message = "cluster_name must be 1-40 conservative name characters starting with alphanumeric."
  }
}
variable "kubernetes_version" {
  description = "Required reviewed EKS version (initial Linux catalog >=1.30). Syntax is not proof of service availability/support."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.kubernetes_version)) && try(tonumber(split(".", var.kubernetes_version)[1]) >= 30, false)
    error_message = "Supply an explicit Kubernetes 1.xx version >=1.30 and verify actual EKS support externally."
  }
}
variable "service_ipv4_cidr" {
  description = "Approved Kubernetes service CIDR, private /12-/24, disjoint from VPC and separately reviewed connected networks."
  type        = string
  nullable    = false
  validation {
    condition = try(cidrnetmask(var.service_ipv4_cidr) != "" && cidrhost(var.service_ipv4_cidr, 0) == split("/", var.service_ipv4_cidr)[0] &&
      tonumber(split("/", var.service_ipv4_cidr)[1]) >= 12 && tonumber(split("/", var.service_ipv4_cidr)[1]) <= 24 &&
      (startswith(var.service_ipv4_cidr, "10.") || (startswith(var.service_ipv4_cidr, "172.") && tonumber(split(".", var.service_ipv4_cidr)[1]) >= 16 && tonumber(split(".", var.service_ipv4_cidr)[1]) <= 31) || (startswith(var.service_ipv4_cidr, "192.168.") && tonumber(split("/", var.service_ipv4_cidr)[1]) >= 16)) &&
    cidrhost("${split("/", var.service_ipv4_cidr)[0]}/${min(tonumber(split("/", var.service_ipv4_cidr)[1]), tonumber(split("/", var.network_reference.vpc_cidr)[1]))}", 0) != cidrhost("${split("/", var.network_reference.vpc_cidr)[0]}/${min(tonumber(split("/", var.service_ipv4_cidr)[1]), tonumber(split("/", var.network_reference.vpc_cidr)[1]))}", 0), false)
    error_message = "service_ipv4_cidr must be canonical private /12-/24 and not overlap the supplied VPC."
  }
}
variable "cluster_subnet_keys" {
  description = "Approved private control-plane keys in at least two distinct AZs; available IPs and supported AZ IDs require external evidence."
  type        = set(string)
  nullable    = false
  validation {
    condition     = try(length(var.cluster_subnet_keys) >= 2 && alltrue([for k in var.cluster_subnet_keys : contains(keys(var.network_reference.private_subnet_ids), k)]) && length(toset([for k in var.cluster_subnet_keys : var.network_reference.subnet_azs.private[k]])) >= 2, false)
    error_message = "Select private cluster subnet keys in at least two distinct approved AZs."
  }
}
variable "node_group" {
  description = "Explicit EC2 Managed Node Group allocation, AL2023 strategy/release, disk and integer capacity; no production defaults or capacity claim."
  type        = object({ name = string, subnet_keys = set(string), instance_type = string, ami_type = string, release_version = string, disk_size_gib = number, min_size = number, desired_size = number, max_size = number })
  nullable    = false
  validation {
    condition = try(can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$", var.node_group.name)) && length(var.node_group.subnet_keys) > 0 &&
      length(setsubtract(var.node_group.subnet_keys, var.cluster_subnet_keys)) == 0 &&
      alltrue([for k in var.node_group.subnet_keys : contains(keys(var.network_reference.private_subnet_ids), k)]) &&
      can(regex("^[a-z][a-z0-9-]*\\.[a-z0-9]+$", var.node_group.instance_type)) &&
      contains(["AL2023_x86_64_STANDARD", "AL2023_ARM_64_STANDARD"], var.node_group.ami_type) &&
      can(regex("^1\\.[0-9]+\\.[0-9]+-[0-9]{8}$", var.node_group.release_version)) && startswith(var.node_group.release_version, "${var.kubernetes_version}.") &&
      var.node_group.disk_size_gib >= 20 && floor(var.node_group.disk_size_gib) == var.node_group.disk_size_gib &&
      var.node_group.min_size >= 1 && var.node_group.min_size <= var.node_group.desired_size && var.node_group.desired_size <= var.node_group.max_size &&
    alltrue([for n in [var.node_group.min_size, var.node_group.desired_size, var.node_group.max_size] : floor(n) == n]), false)
    error_message = "Node group requires approved private cluster subnets, explicit AL2023 instance/release strategy, disk >=20 GiB and integers 1 <= min <= desired <= max."
  }
}
variable "bootstrap_admin_role_arn" {
  description = "Required existing approved initial cluster administrator role, separate from cluster/node/CNI roles. No creator backdoor."
  type        = string
  nullable    = false
  validation {
    condition = (can(regex("^arn:aws:iam::${var.expected_scope.account_id}:role/([A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}$", var.bootstrap_admin_role_arn)) &&
      !strcontains(var.bootstrap_admin_role_arn, ":role/aws-service-role/") &&
    !contains([for suffix in ["cluster", "nodes", "cni"] : "arn:aws:iam::${var.expected_scope.account_id}:role/${var.cluster_name}-${suffix}"], var.bootstrap_admin_role_arn))
    error_message = "Bootstrap must be an explicit same-account non-service-linked role distinct from platform machine identities."
  }
}
variable "namespace_access" {
  description = "Optional approved existing roles: namespace-scoped view/edit only, no implicit additional cluster administrators or Kubernetes groups."
  type        = map(object({ principal_arn = string, policy = string, namespaces = set(string) }))
  default     = {}
  nullable    = false
  validation {
    condition = try(length(distinct([for v in values(var.namespace_access) : v.principal_arn])) == length(var.namespace_access) && alltrue([for k, v in var.namespace_access :
      can(regex("^[A-Za-z0-9_-]+$", k)) && contains(["view", "edit"], v.policy) && length(v.namespaces) > 0 &&
      alltrue([for n in v.namespaces : length(n) <= 63 && can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", n)) && !startswith(n, "kube-") && n != "default"]) &&
      can(regex("^arn:aws:iam::${var.expected_scope.account_id}:role/([A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}$", v.principal_arn)) &&
      !strcontains(v.principal_arn, ":role/aws-service-role/") && v.principal_arn != var.bootstrap_admin_role_arn &&
      !contains([for suffix in ["cluster", "nodes", "cni"] : "arn:aws:iam::${var.expected_scope.account_id}:role/${var.cluster_name}-${suffix}"], v.principal_arn)
    ]), false)
    error_message = "Additional entries need distinct same-account role identities, view/edit and explicit non-system namespaces without wildcards."
  }
}
variable "api_client_cidrs" {
  description = "Approved private administrative network source CIDRs; routes/VPN/identity are not created or inferred."
  type        = set(string)
  nullable    = false
  validation {
    condition = length(var.api_client_cidrs) > 0 && alltrue([for c in var.api_client_cidrs : try(cidrnetmask(c) != "" && cidrhost(c, 0) == split("/", c)[0] && tonumber(split("/", c)[1]) >= 8 && tonumber(split("/", c)[1]) <= 32 &&
    (startswith(c, "10.") || (startswith(c, "172.") && tonumber(split(".", c)[1]) >= 16 && tonumber(split(".", c)[1]) <= 31 && tonumber(split("/", c)[1]) >= 12) || (startswith(c, "192.168.") && tonumber(split("/", c)[1]) >= 16)), false)])
    error_message = "API clients require explicit canonical private IPv4 ranges; no public/world ingress."
  }
}
variable "node_https_egress_cidrs" {
  description = "Reviewed bounded IPv4 destinations for required AWS HTTPS flows via NAT/endpoints. No world default; actual service coverage is an external prerequisite."
  type        = set(string)
  nullable    = false
  validation {
    condition     = length(var.node_https_egress_cidrs) > 0 && alltrue([for c in var.node_https_egress_cidrs : try(cidrnetmask(c) != "" && cidrhost(c, 0) == split("/", c)[0] && tonumber(split("/", c)[1]) >= 8 && tonumber(split("/", c)[1]) <= 32, false)])
    error_message = "Supply explicit canonical IPv4 HTTPS destinations with /8-/32 prefixes, never unrestricted 0.0.0.0/0."
  }
}
variable "addon_versions" {
  description = "Required externally verified version triple for this Kubernetes version/architecture. No most_recent discovery or unpinned bootstrap."
  type        = object({ vpc_cni = string, coredns = string, kube_proxy = string })
  nullable    = false
  validation {
    condition     = alltrue([for v in values(var.addon_versions) : can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+-eksbuild\\.[0-9]+$", v))])
    error_message = "Each managed add-on needs an explicit vX.Y.Z-eksbuild.N version; availability/compatibility must be verified outside Codex."
  }
}
variable "cluster_kms_key_arn" {
  description = "Optional approved same-account/Region symmetric customer key for secrets; null retains EKS >=1.28 AWS-owned envelope encryption. No key/grants created."
  type        = string
  default     = null
  validation {
    condition     = var.cluster_kms_key_arn == null ? true : can(regex("^arn:aws:kms:${var.expected_scope.region}:${var.expected_scope.account_id}:key/[0-9a-f-]{36}$", var.cluster_kms_key_arn))
    error_message = "Optional KMS reference must be a key ARN in the expected account and Region, not an alias or arbitrary cross-account key."
  }
}
variable "deletion_protection" {
  description = "Cluster and cluster log deletion protection default true. Disabling requires separate reviewed external plan/teardown approval."
  type        = bool
  default     = true
  nullable    = false
}
variable "tags" {
  description = "Non-secret metadata; module Name and root governance tags take precedence."
  type        = map(string)
  default     = {}
  nullable    = false
}
