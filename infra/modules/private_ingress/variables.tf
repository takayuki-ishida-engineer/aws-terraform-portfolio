variable "expected_scope" {
  type     = object({ environment = string, partition = string, region = string, account_id = string })
  nullable = false
  validation {
    condition     = contains(["dev", "stg", "prod"], var.expected_scope.environment) && var.expected_scope.partition == "aws" && var.expected_scope.region == "ca-central-1" && can(regex("^[0-9]{12}$", var.expected_scope.account_id))
    error_message = "Supply an explicit approved environment/account and aws/ca-central-1 scope."
  }
}
variable "network_reference" {
  description = "Minimal declared Network interface subset, not proof of provenance/existence. Public IDs are exclusion evidence only."
  type        = object({ interface_version = number, scope = object({ environment = string, partition = string, region = string, account_id = string }), vpc_id = string, private_subnet_ids = map(string), public_subnet_ids = map(string), subnet_azs = object({ private = map(string) }) })
  nullable    = false
  validation {
    condition     = try(var.network_reference.interface_version == 1 && var.network_reference.scope == var.expected_scope && can(regex("^vpc-([0-9a-f]{8}|[0-9a-f]{17})$", var.network_reference.vpc_id)) && length(var.network_reference.private_subnet_ids) > 0 && toset(keys(var.network_reference.private_subnet_ids)) == toset(keys(var.network_reference.subnet_azs.private)) && alltrue([for k, id in var.network_reference.private_subnet_ids : trimspace(k) != "" && can(regex("^subnet-([0-9a-f]{8}|[0-9a-f]{17})$", id))]) && alltrue([for id in values(var.network_reference.public_subnet_ids) : can(regex("^subnet-([0-9a-f]{8}|[0-9a-f]{17})$", id))]) && length(distinct(concat(values(var.network_reference.private_subnet_ids), values(var.network_reference.public_subnet_ids)))) == length(var.network_reference.private_subnet_ids) + length(var.network_reference.public_subnet_ids) && alltrue([for az in values(var.network_reference.subnet_azs.private) : can(regex("^${var.expected_scope.region}[a-z]$", az))]), false)
    error_message = "Network v1 scope, VPC, private/public unique IDs and complete Region-matching private AZ map are required."
  }
}
variable "name" {
  type     = string
  nullable = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,19}$", var.name)) && !startswith(var.name, "internal-") && !endswith(var.name, "-")
    error_message = "Approved name must be 1-20 lowercase name characters, not internal-* or ending with a hyphen."
  }
}
variable "subnet_keys" {
  type     = set(string)
  nullable = false
  validation {
    condition     = try(length(var.subnet_keys) > 0 && length(setsubtract(var.subnet_keys, toset(keys(var.network_reference.private_subnet_ids)))) == 0 && length(toset([for k in var.subnet_keys : var.network_reference.subnet_azs.private[k]])) == length(var.subnet_keys), false)
    error_message = "Select one existing private subnet per distinct AZ; unknown/public keys or repeated AZs are rejected."
  }
}
variable "backend_target_port" {
  description = "Explicit reviewed Gateway Pod target port, distinct concept from listener/Service 443."
  type        = number
  nullable    = false
  validation {
    condition     = var.backend_target_port >= 1 && var.backend_target_port <= 65535 && floor(var.backend_target_port) == var.backend_target_port
    error_message = "Backend target port must be an explicit integer TCP port 1-65535."
  }
}
variable "eks_security_groups" {
  description = "Actual attached EKS custom control/Node SG IDs; never the AWS-managed Cluster SG. Root binds resource-backed outputs."
  type        = object({ cluster = string, nodes = string })
  nullable    = false
  validation {
    condition     = try(var.eks_security_groups.cluster != var.eks_security_groups.nodes && alltrue([for id in values(var.eks_security_groups) : can(regex("^sg-([0-9a-f]{8}|[0-9a-f]{17})$", id))]), false)
    error_message = "Two distinct syntactically valid custom Cluster/Node SG IDs are required; actual ownership requires external verification."
  }
}
variable "cross_zone_enabled" {
  description = "Explicit reviewed NLB cross-zone choice. DEV Root fixes false; other consumers must review AZ capacity/transfer/failure behavior."
  type        = bool
  nullable    = false
}
variable "deletion_protection" {
  type     = bool
  default  = true
  nullable = false
}
variable "tags" {
  type     = map(string)
  default  = {}
  nullable = false
}

variable "controller_oidc" {
  description = "Actual EKS issuer/provider; exact kube-system/aws-load-balancer-controller IRSA subject is fixed."
  type        = object({ issuer = string, provider_arn = string })
  nullable    = false
  validation {
    condition     = try(can(regex("^https://oidc[.]eks[.]${var.expected_scope.region}[.]amazonaws[.]com/id/[A-Za-z0-9]+$", var.controller_oidc.issuer)) && var.controller_oidc.provider_arn == "arn:${var.expected_scope.partition}:iam::${var.expected_scope.account_id}:oidc-provider/${replace(var.controller_oidc.issuer, "https://", "")}", false)
    error_message = "Supply the actual same-account EKS OIDC provider ARN matching the exact Region issuer; no wildcard or unreviewed external issuer."
  }
}
