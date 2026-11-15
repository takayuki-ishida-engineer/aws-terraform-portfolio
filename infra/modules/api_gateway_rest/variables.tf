variable "expected_scope" {
  type     = object({ environment = string, partition = string, account_id = string, region = string })
  nullable = false
  validation {
    condition     = try(contains(["dev", "stg", "prod"], var.expected_scope.environment) && var.expected_scope.partition == "aws" && var.expected_scope.region == "ca-central-1" && can(regex("^[0-9]{12}$", var.expected_scope.account_id)), false)
    error_message = "Provide an approved AWS scope in ca-central-1."
  }
}
variable "name" {
  type     = string
  nullable = false
  validation {
    condition     = try(can(regex("^[a-z][a-z0-9-]{2,100}$", var.name)) && startswith(var.name, "${var.expected_scope.environment}-"), false)
    error_message = "Provide a bounded environment-prefixed API name."
  }
}
variable "authentication" {
  description = "Existing Cognito resource-derived public contract; no tokens or secrets."
  type = object({
    interface_version          = number
    scope                      = object({ environment = string, partition = string, account_id = string, region = string })
    user_pool_id               = string
    user_pool_arn              = string
    resource_server_identifier = string
    approved_custom_scopes     = list(string)
  })
  nullable = false
  validation {
    condition = try(
      var.authentication.interface_version == 1 && var.authentication.scope == var.expected_scope &&
      can(regex("^ca-central-1_[A-Za-z0-9]+$", var.authentication.user_pool_id)) &&
      var.authentication.user_pool_arn == "arn:aws:cognito-idp:${var.expected_scope.region}:${var.expected_scope.account_id}:userpool/${var.authentication.user_pool_id}" &&
      can(regex("^[A-Za-z0-9-]+$", var.authentication.resource_server_identifier)) &&
      length(var.authentication.approved_custom_scopes) > 0 &&
      length(distinct(var.authentication.approved_custom_scopes)) == length(var.authentication.approved_custom_scopes) &&
    alltrue([for s in var.authentication.approved_custom_scopes : can(regex("^${var.authentication.resource_server_identifier}/[A-Za-z0-9._-]+$", s))]), false)
    error_message = "Require version 1, matching scope, exact Cognito ARN/ID and nonempty unique approved custom scopes."
  }
}
variable "tags" {
  type     = map(string)
  default  = {}
  nullable = false
}
