locals {
  function_pattern = "^arn:(aws|aws-us-gov):lambda:[a-z]{2}(-[a-z0-9]+)+-[1-9][0-9]*:[0-9]{12}:function:[A-Za-z0-9_-]{1,64}$"
  invoke_pattern   = "^arn:(aws|aws-us-gov):apigateway:[a-z]{2}(-[a-z0-9]+)+-[1-9][0-9]*:lambda:path/2015-03-31/functions/arn:(aws|aws-us-gov):lambda:[a-z]{2}(-[a-z0-9]+)+-[1-9][0-9]*:[0-9]{12}:function:[A-Za-z0-9_-]{1,64}/invocations$"
  log_pattern      = "^arn:(aws|aws-us-gov):logs:[a-z]{2}(-[a-z0-9]+)+-[1-9][0-9]*:[0-9]{12}:log-group:[A-Za-z0-9_./#-]{1,512}$"
  function_parts   = try(split(":", var.lambda_function_arn), [])
  partition        = try(local.function_parts[1], "")
  region           = try(local.function_parts[3], "")
  account_id       = try(local.function_parts[4], "")
  function_reference_is_valid = can(regex(local.function_pattern, var.lambda_function_arn)) && try(
    length(var.lambda_function_arn) <= 140 && length(local.region) <= 63 &&
    can(regex("^[a-z]{2}(-[a-z]+){1,2}-[1-9]$", local.region)) && (local.partition == "aws-us-gov" ?
      contains(["us-gov-east-1", "us-gov-west-1"], local.region) :
    !can(regex("^(cn-|us-gov-|us-iso|eu-iso)", local.region))), false
  )
  expected_invoke_arn = "arn:${local.partition}:apigateway:${local.region}:lambda:path/2015-03-31/functions/${var.lambda_function_arn == null ? "" : var.lambda_function_arn}/invocations"
}

variable "api_name" {
  description = "Explicit stable non-secret API name; this module deliberately uses a conservative 1-128-character ASCII naming subset."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", var.api_name))
    error_message = "api_name must contain 1-128 ASCII letters, digits, underscores, periods or hyphens and start with a letter or digit; this is a conservative module naming contract."
  }
}

variable "lambda_function_arn" {
  description = "Actual unqualified existing Lambda function ARN; no alias/version, wildcard or predicted function identity."
  type        = string

  validation {
    # Refer to this input directly: deriving its validation through scope locals
    # creates a dependency cycle in Terraform's variable-validation graph.
    condition = can(regex(local.function_pattern, var.lambda_function_arn)) && try(
      length(var.lambda_function_arn) <= 140 && length(split(":", var.lambda_function_arn)[3]) <= 63 &&
      can(regex("^[a-z]{2}(-[a-z]+){1,2}-[1-9]$", split(":", var.lambda_function_arn)[3])) &&
      (split(":", var.lambda_function_arn)[1] == "aws-us-gov" ?
        contains(["us-gov-east-1", "us-gov-west-1"], split(":", var.lambda_function_arn)[3]) :
      !can(regex("^(cn-|us-gov-|us-iso|eu-iso)", split(":", var.lambda_function_arn)[3]))), false
    )
    error_message = "lambda_function_arn must be a complete unqualified aws/aws-us-gov Lambda function ARN of at most 140 characters for AWS Provider 6.72.0, with a 12-digit account, canonical supported region form and 1-64-character name; China/isolated partitions and unreviewed GovCloud regions are unsupported."
  }
}

variable "lambda_invoke_arn" {
  description = "Actual existing Lambda module invoke_arn, describing the same unqualified function, partition, Region and account as lambda_function_arn."
  type        = string

  validation {
    condition     = can(regex(local.invoke_pattern, var.lambda_invoke_arn))
    error_message = "lambda_invoke_arn must be a complete aws/aws-us-gov API Gateway Lambda invocation ARN using the documented 2015-03-31/functions/<unqualified-function-arn>/invocations form without wildcards."
  }

  validation {
    condition     = !local.function_reference_is_valid || try(var.lambda_invoke_arn == local.expected_invoke_arn, false)
    error_message = "lambda_invoke_arn must reference exactly lambda_function_arn and use the same AWS partition and Region in its API Gateway prefix."
  }
}

variable "access_log_group_name" {
  description = "Stable, explicitly supplied non-sensitive log group name; no name prefix or random suffix is generated."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_./#-]{1,512}$", var.access_log_group_name)) && try(!startswith(var.access_log_group_name, "aws/"), false)
    error_message = "name must contain 1-512 supported CloudWatch Logs name characters and must not start with the Lambda-incompatible literal prefix aws/."
  }
}

variable "access_log_retention_in_days" {
  description = "Explicit finite retention period in supported whole days; indefinite retention is not exposed by this module."
  type        = number
  default     = 30
  nullable    = false

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545,
      731, 1096, 1827, 2192, 2557, 2922, 3288, 3653
    ], var.access_log_retention_in_days)
    error_message = "retention_in_days must be one of 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288 or 3653; zero/indefinite retention is forbidden."
  }
}

variable "access_log_deletion_protection_enabled" {
  description = "Protect the log group from deletion by default; an authorized owner must first disable and apply this setting before a later destroy."
  type        = bool
  default     = true
  nullable    = false
}

variable "access_log_kms_key_arn" {
  description = "Optional existing symmetric customer-managed KMS key ARN; key usability, region, permissions and historical-log access are external responsibilities."
  type        = string
  default     = null

  validation {
    condition = var.access_log_kms_key_arn == null || (
      can(regex(
        "^arn:(aws|aws-us-gov|aws-cn):kms:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:key/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})$",
        var.access_log_kms_key_arn
      )) && try(length(var.access_log_kms_key_arn) <= 256, false)
    )
    error_message = "kms_key_arn must be null or a complete KMS key ARN up to 256 characters with an explicit supported partition, region, 12-digit account and UUID or multi-region key ID; aliases, bare IDs and wildcards are rejected."
  }
}

variable "access_log_tags" {
  description = "Optional visible, non-secret access log group tags; the module-owned Name and service tags win, and provider default_tags remain root-owned."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.access_log_tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.access_log_tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256, false) && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value))
    ])
    error_message = "tags plus the module-owned Name and service must have at most 50 entries, 1-128-character keys without the reserved aws: prefix, and non-null values up to 256 characters; only Unicode letters, separators, numbers and _ . : / = + @ - are supported."
  }
}

variable "tags" {
  description = "Optional visible non-secret tags on the API and stage; the module-owned Name and service tags win, and provider default_tags remain root-owned and count toward each effective tag limit."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256 && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value)), false)
    ])
    error_message = "tags plus the module-owned Name and service must have at most 50 non-secret entries, 1-128-character non-reserved keys and non-null values of at most 256 characters; use Unicode letters, separators, numbers and _ . : / = + @ - only, without the reserved aws: prefix."
  }
}
