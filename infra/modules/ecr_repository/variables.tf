variable "name_prefix" {
  description = "<project>-<env> prefix; every repository is named <name_prefix>-ecr-<purpose> (docs/deployment-configuration.md section 4)."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,8}[a-z0-9])?-(dev|stg|prod)$", var.name_prefix))
    error_message = "name_prefix must be <project>-<env>: a 1-10 character lowercase project token that starts with a letter, then -dev, -stg or -prod."
  }
}

variable "purposes" {
  description = "Repository purposes, one private repository each. The DEV registry root passes the purposes of kubernetes/images.lock.json, the only image inventory (finding F18)."
  type        = set(string)
  nullable    = false

  validation {
    condition = length(var.purposes) >= 1 && length(var.purposes) <= 10 && alltrue([for purpose in var.purposes :
      can(regex("^[a-z][a-z0-9]*(-[a-z0-9]+)*$", purpose)) && length(purpose) <= 40
    ])
    error_message = "purposes must hold 1-10 lowercase hyphenated tokens of at most 40 characters that start with a letter."
  }
}

variable "expected_scope" {
  description = "Account and Region the repositories must belong to; the provider-reported registry ID, ARN and URL are checked against them after planning or applying."
  type = object({
    account_id = string
    region     = string
  })
  nullable = false

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_scope.account_id)) && can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]$", var.expected_scope.region))
    error_message = "expected_scope needs a 12-digit account_id and an AWS Region name such as ca-central-1."
  }
}

variable "force_delete" {
  description = "Teardown switch only. false keeps Terraform from deleting a repository that still holds images; set true in the root's untracked local.auto.tfvars immediately before an approved destroy."
  type        = bool
  default     = false
  nullable    = false
}

variable "tags" {
  description = "Optional extra caller tags. Name and service are module owned and the aws: prefix is reserved, so those keys are rejected."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") && !contains(["Name", "service"], key) &&
      try(length(value) <= 256, false)
    ])
    error_message = "tags must not set Name, service or an aws: key and, with the module-owned Name and service, hold at most 50 entries with 1-128-character keys and values up to 256 characters."
  }
}
