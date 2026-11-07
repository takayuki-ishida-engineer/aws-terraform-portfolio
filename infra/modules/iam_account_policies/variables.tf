variable "account_id" {
  description = "Explicit workload account that must own this policy; the owning root must select and restrict the provider to that account."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be an explicit 12-digit workload account ID without wildcards."
  }
}

variable "region" {
  description = "Explicit Secrets Manager authorization region; existence and partition compatibility require external verification."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.region))
    error_message = "region must be an explicit AWS region identifier without wildcards."
  }
}

variable "project_tag" {
  description = "Required Project authorization tag shared with the owning root's reviewed secret metadata."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.project_tag))
    error_message = "project_tag must be 1-63 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "partition" {
  description = "Explicit ARN partition; this setting does not choose the provider or discover an account."
  type        = string
  default     = "aws"
  nullable    = false

  validation {
    condition     = contains(["aws", "aws-us-gov", "aws-cn"], var.partition)
    error_message = "partition must be aws, aws-us-gov or aws-cn."
  }
}

variable "tags" {
  description = "Additional non-sensitive policy inventory tags; module-owned Name and Project values take precedence."
  type        = map(string)
  default     = {}
  nullable    = false
}
