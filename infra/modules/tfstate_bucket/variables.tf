variable "bucket_name" {
  description = "Explicit general-purpose bucket name in the global namespace, ending in -s3-tfstate (<project>-<env>-s3-tfstate); uniqueness and ownership are verified outside Terraform."
  type        = string
  nullable    = false

  validation {
    condition = try(
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name)) &&
      endswith(var.bucket_name, "-s3-tfstate") &&
      alltrue([for prefix in ["xn--", "sthree-", "amzn-s3-demo-"] : !startswith(var.bucket_name, prefix)]),
      false
    )
    error_message = "bucket_name must be 3-63 lowercase letters, numbers or hyphens, start and end with a letter or number, end in -s3-tfstate and avoid AWS-reserved prefixes; periods are unsupported."
  }
}

variable "noncurrent_version_retention_days" {
  description = "Days a superseded State object version is kept before S3 expires it; earlier State versions are the recovery path after a bad apply."
  type        = number
  default     = 90
  nullable    = false

  validation {
    condition     = var.noncurrent_version_retention_days >= 30 && var.noncurrent_version_retention_days <= 365 && floor(var.noncurrent_version_retention_days) == var.noncurrent_version_retention_days
    error_message = "noncurrent_version_retention_days must be a whole number of days from 30 through 365."
  }
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
