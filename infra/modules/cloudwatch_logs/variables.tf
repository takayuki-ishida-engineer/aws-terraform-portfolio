variable "name" {
  description = "Stable, explicitly supplied non-sensitive log group name; no name prefix or random suffix is generated."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_./#-]{1,512}$", var.name)) && try(!startswith(var.name, "aws/"), false)
    error_message = "name must contain 1-512 supported CloudWatch Logs name characters and must not start with the Lambda-incompatible literal prefix aws/."
  }
}

variable "service" {
  description = "Resource-type token for the module-owned service tag: the token in the log group path, for example lambda for /aws/lambda/<name> or apigw for /<project>/<env>/apigw/<purpose>."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,30}[a-z0-9])?$", var.service))
    error_message = "service must be a lowercase resource-type token of 1-32 letters, digits or hyphens that starts with a letter and does not end with a hyphen."
  }
}

variable "retention_in_days" {
  description = "Explicit finite retention period in supported whole days; indefinite retention is not exposed by this module."
  type        = number
  default     = 30
  nullable    = false

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545,
      731, 1096, 1827, 2192, 2557, 2922, 3288, 3653
    ], var.retention_in_days)
    error_message = "retention_in_days must be one of 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288 or 3653; zero/indefinite retention is forbidden."
  }
}

variable "deletion_protection_enabled" {
  description = "Protect the log group from deletion by default; an authorized owner must first disable and apply this setting before a later destroy."
  type        = bool
  default     = true
  nullable    = false
}

variable "kms_key_arn" {
  description = "Optional existing symmetric customer-managed KMS key ARN; key usability, region, permissions and historical-log access are external responsibilities."
  type        = string
  default     = null

  validation {
    condition = var.kms_key_arn == null || (
      can(regex(
        "^arn:(aws|aws-us-gov|aws-cn):kms:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:key/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})$",
        var.kms_key_arn
      )) && try(length(var.kms_key_arn) <= 256, false)
    )
    error_message = "kms_key_arn must be null or a complete KMS key ARN up to 256 characters with an explicit supported partition, region, 12-digit account and UUID or multi-region key ID; aliases, bare IDs and wildcards are rejected."
  }
}

variable "tags" {
  description = "Optional visible, non-secret caller tags; Name and service are module owned and rejected here. Provider default_tags remain root-owned."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") && !contains(["Name", "service"], key) &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256, false) && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value))
    ])
    error_message = "tags must not set Name or service and, with those two module-owned tags, hold at most 50 entries with 1-128-character keys without the reserved aws: prefix and non-null values up to 256 characters; only Unicode letters, separators, numbers and _ . : / = + @ - are supported."
  }
}
