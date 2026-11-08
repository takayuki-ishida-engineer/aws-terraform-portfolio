variable "role_name" {
  description = "Stable explicit workload execution-role name; no generated suffix or human-access role is created."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_+=,.@-]{1,64}$", var.role_name))
    error_message = "role_name must contain 1-64 supported IAM role-name characters without paths, ARNs or wildcards."
  }
}

variable "partition" {
  description = "Explicit supported AWS partition. China and other partitions are deliberately outside this phase's reviewed Lambda trust contract."
  type        = string

  validation {
    condition     = can(regex("^(aws|aws-us-gov)$", var.partition))
    error_message = "partition must be aws or aws-us-gov; aws-cn and other partitions are not supported by this phase."
  }
}

variable "account_id" {
  description = "Expected workload account for all resource references; the owning root must select and restrict the provider to this account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be an explicit 12-digit AWS account ID without wildcards."
  }
}

variable "region" {
  description = "Explicit workload region, consistent with the selected partition; existence and provider selection are verified externally."
  type        = string

  validation {
    condition = try(length(var.region) <= 63 && can(regex("^[a-z]{2}(-[a-z0-9]+)+-[0-9]+$", var.region)) &&
      (!can(regex("^(aws|aws-us-gov)$", var.partition)) ||
        (var.partition == "aws-us-gov" ? startswith(var.region, "us-gov-") :
    !can(regex("^(cn-|us-gov-|us-iso|eu-iso)", var.region)))), false)
    error_message = "region must be an explicit supported-shape region of at most 63 characters and use the selected partition's region family."
  }
}

variable "log_group_arn" {
  description = "Exact existing bare log-group ARN returned by the CloudWatch Logs module; no wildcard, API :* suffix or log-stream ARN."
  type        = string

  validation {
    condition = can(regex(local.log_group_pattern, var.log_group_arn)) && try(
      !startswith(regex(local.log_group_pattern, var.log_group_arn)[3], "aws/"), false
    )
    error_message = "log_group_arn must be a complete bare supported-partition CloudWatch Log Group ARN with a valid explicit name and no wildcard, :* or log-stream suffix."
  }

  validation {
    condition = !local.scope_is_valid || try(
      split(":", var.log_group_arn)[1] == var.partition &&
      split(":", var.log_group_arn)[3] == var.region &&
      split(":", var.log_group_arn)[4] == var.account_id, false
    )
    error_message = "log_group_arn must match the configured partition, workload region and expected account."
  }
}

variable "enable_secret_read" {
  description = "Genuine optional runtime permission for one exact secret; false grants no Secrets Manager or KMS access."
  type        = bool
  default     = false
  nullable    = false
}

variable "secret_arn" {
  description = "Optional actual resource-generated full secret ARN with its six-character suffix; never a secret value or reconstructed partial ARN."
  type        = string
  default     = null

  validation {
    condition     = var.enable_secret_read ? var.secret_arn != null : var.secret_arn == null
    error_message = "secret_arn is required when enable_secret_read is true and must be null when secret reading is disabled."
  }

  validation {
    condition     = var.secret_arn == null || can(regex(local.secret_pattern, var.secret_arn))
    error_message = "secret_arn must be null or a complete supported-partition Secrets Manager ARN with a valid name and generated six-character suffix; partial ARNs and wildcards are rejected."
  }

  validation {
    condition = var.secret_arn == null || !local.scope_is_valid || try(
      split(":", var.secret_arn)[1] == var.partition &&
      split(":", var.secret_arn)[3] == var.region &&
      split(":", var.secret_arn)[4] == var.account_id, false
    )
    error_message = "secret_arn must match the configured partition, workload region and expected account."
  }
}

variable "secret_kms_key_arn" {
  description = "Optional exact existing customer-managed KMS key ARN for the authorized secret; null adds no KMS permission and does not discover the key type."
  type        = string
  default     = null

  validation {
    condition     = var.secret_kms_key_arn == null || (var.enable_secret_read && var.secret_arn != null)
    error_message = "secret_kms_key_arn is permitted only with enable_secret_read true and an explicit secret_arn."
  }

  validation {
    condition = var.secret_kms_key_arn == null || try(
      length(var.secret_kms_key_arn) <= 256 && can(regex(local.key_pattern, var.secret_kms_key_arn)), false
    )
    error_message = "secret_kms_key_arn must be null or a complete supported-partition KMS key ARN of at most 256 characters with a UUID or mrk identifier; aliases, partial IDs and wildcards are rejected."
  }

  validation {
    condition = var.secret_kms_key_arn == null || !local.scope_is_valid || try(
      split(":", var.secret_kms_key_arn)[1] == var.partition &&
      split(":", var.secret_kms_key_arn)[3] == var.region &&
      split(":", var.secret_kms_key_arn)[4] == var.account_id, false
    )
    error_message = "secret_kms_key_arn must match the configured partition, workload region and expected account."
  }
}

variable "tags" {
  description = "Optional visible non-secret role tags, passed through without invented Name or Project metadata; root default_tags remain root-owned."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(var.tags) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256 && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value)), false)
    ])
    error_message = "tags must have at most 50 non-secret entries; keys 1-128 and values 0-256 permitted Unicode characters, no null values or reserved aws: prefix."
  }
}
