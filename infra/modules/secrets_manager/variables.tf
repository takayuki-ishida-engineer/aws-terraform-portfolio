variable "name" {
  description = "Stable non-sensitive secret name; never include credential or confidential connection information."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9/_+=.@-]{1,512}$", var.name)) && !can(regex("-[A-Za-z0-9]{6}$", var.name))
    error_message = "name must be non-null, 1-512 supported ASCII characters, and must not end in a hyphen followed by six alphanumeric characters."
  }
}

variable "description" {
  description = "Optional visible, non-sensitive metadata description; never include secret values."
  type        = string
  default     = null

  validation {
    condition     = var.description == null || try(length(var.description) <= 2048, false)
    error_message = "description must be null or at most 2048 characters."
  }
}

variable "project_tag" {
  description = "Required Project authorization tag, owned by the module and verified by root configuration."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.project_tag))
    error_message = "project_tag must be non-null, 1-63 lowercase letters/digits/hyphens and start with a letter."
  }
}

variable "tags" {
  description = "Additional visible, non-sensitive tags; canonical Name and Project inputs are overridden by module-owned values."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition     = alltrue([for key in keys(var.tags) : !contains(["name", "project"], lower(key)) || contains(["Name", "Project"], key)])
    error_message = "Use only canonical Name and Project tag spelling; case variants would make authorization metadata ambiguous."
  }

  validation {
    condition = alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") && try(length(value) <= 256, false)
    ]) && length(setunion(toset(keys(var.tags)), toset(["Name", "Project"]))) <= 50
    error_message = "Tags require 1-128-character keys without the reserved aws: prefix, non-null values up to 256 characters, and at most 50 merged tags."
  }
}

variable "recovery_window_in_days" {
  description = "Deletion recovery period; only whole days from 7 through 30 are permitted."
  type        = number
  default     = 30
  nullable    = false

  validation {
    condition     = var.recovery_window_in_days >= 7 && var.recovery_window_in_days <= 30 && var.recovery_window_in_days == floor(var.recovery_window_in_days)
    error_message = "recovery_window_in_days must be an integer from 7 through 30; immediate force deletion is not supported."
  }
}

variable "kms_key_arn" {
  description = "Optional existing symmetric customer-managed KMS key ARN; null leaves the AWS-managed Secrets Manager key selection to the service."
  type        = string
  default     = null

  validation {
    condition = var.kms_key_arn == null || can(regex(
      "^arn:(aws|aws-us-gov|aws-cn):kms:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:key/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})$",
      var.kms_key_arn
    ))
    error_message = "kms_key_arn must be null or a complete KMS key ARN with an explicit supported partition, region, 12-digit account and UUID or multi-region key ID; aliases and wildcards are rejected."
  }
}
