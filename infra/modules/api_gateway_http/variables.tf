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

variable "access_log_group_arn" {
  description = "Actual existing bare access Log Group ARN; separately provisioned API access-log storage, not an implicit Lambda application group."
  type        = string

  validation {
    condition = can(regex(local.log_pattern, var.access_log_group_arn)) && try(
      !startswith(split(":", var.access_log_group_arn)[6], "aws/"), false
    )
    error_message = "access_log_group_arn must be a complete bare aws/aws-us-gov CloudWatch Log Group ARN with a supported explicit name; no wildcard, trailing :*, log-stream suffix or reserved aws/ name."
  }

  validation {
    condition = !local.function_reference_is_valid || try(
      split(":", var.access_log_group_arn)[1] == local.partition &&
      split(":", var.access_log_group_arn)[3] == local.region &&
      split(":", var.access_log_group_arn)[4] == local.account_id, false
    )
    error_message = "access_log_group_arn must use the same AWS partition, Region and account as the existing Lambda function."
  }
}

variable "tags" {
  description = "Optional visible non-secret tags on the API and stage; provider default_tags remain root-owned and count toward each effective tag limit."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(var.tags) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256 && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value)), false)
    ])
    error_message = "tags must have at most 50 non-secret entries, 1-128-character non-reserved keys and non-null values of at most 256 characters; use Unicode letters, separators, numbers and _ . : / = + @ - only, without the reserved aws: prefix."
  }
}
