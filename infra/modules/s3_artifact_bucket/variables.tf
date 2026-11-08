variable "bucket_name" {
  description = "Explicit stable general-purpose bucket name in the shared namespace; uniqueness and ownership must be verified externally."
  type        = string

  validation {
    condition = try(
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name)) &&
      alltrue([for prefix in ["xn--", "sthree-", "amzn-s3-demo-"] : !startswith(var.bucket_name, prefix)]) &&
      alltrue([for suffix in ["-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3", "-an"] : !endswith(var.bucket_name, suffix)]),
      false
    )
    error_message = "bucket_name must be 3-63 lowercase letters, numbers or hyphens, start and end with a letter or number, and avoid AWS-reserved prefixes/suffixes; periods, partial names and account-regional namespace names are unsupported."
  }
}

variable "tags" {
  description = "Optional visible non-secret bucket tags; root-owned provider default_tags also count toward the effective 50-tag limit."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(var.tags) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      try(length(value) <= 256, false)
    ])
    error_message = "tags must contain at most 50 non-secret entries with 1-128-character non-reserved keys and non-null values up to 256 characters; the aws: prefix is reserved."
  }
}
