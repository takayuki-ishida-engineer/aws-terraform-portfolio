variable "aws_account_id" {
  type     = string
  nullable = false
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Supply the approved workload account ID."
  }
}
variable "project" {
  description = "Required project name used in every resource name (<project>-dev-<type>[-<purpose>]) and the project tag. The tracked placeholder is project; replace it before a real deployment."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,8}[a-z0-9])?$", var.project)) && !can(regex("(aws|amazon|cognito)", var.project))
    error_message = "project must be 1-10 lowercase letters, digits or hyphens, start with a letter, end with a letter or digit and not contain aws, amazon or cognito."
  }
}
variable "feature_plan" {
  type     = string
  nullable = false
  validation {
    condition     = try(contains(["ESSENTIALS", "PLUS"], var.feature_plan), false)
    error_message = "Invalid or unsafe feature_plan; provide explicitly reviewed configuration."
  }
}
variable "allow_dev_loopback" {
  type     = bool
  nullable = false
  validation {
    condition     = try(!var.allow_dev_loopback || "dev" == "dev", false)
    error_message = "Invalid or unsafe allow_dev_loopback; provide explicitly reviewed configuration."
  }
}
variable "callback_urls" {
  type     = list(string)
  nullable = false
  validation {
    condition     = try(alltrue([for u in var.callback_urls : try(tonumber(regex(":([0-9]+)", u)[0]) > 0 && tonumber(regex(":([0-9]+)", u)[0]) <= 65535, true)]) && length(var.callback_urls) > 0 && length(var.callback_urls) <= 10 && length(distinct(var.callback_urls)) == length(var.callback_urls) && alltrue([for u in var.callback_urls : can(regex("^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$", u)) || (var.allow_dev_loopback && can(regex("^http://(localhost|127[.]0[.]0[.]1)(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$", u)))]), false)
    error_message = "Invalid or unsafe callback_urls; provide explicitly reviewed configuration."
  }
}
variable "logout_urls" {
  type     = list(string)
  nullable = false
  validation {
    condition     = try(alltrue([for u in var.logout_urls : try(tonumber(regex(":([0-9]+)", u)[0]) > 0 && tonumber(regex(":([0-9]+)", u)[0]) <= 65535, true)]) && length(var.logout_urls) > 0 && length(var.logout_urls) <= 10 && length(distinct(var.logout_urls)) == length(var.logout_urls) && alltrue([for u in var.logout_urls : can(regex("^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$", u)) || (var.allow_dev_loopback && can(regex("^http://(localhost|127[.]0[.]0[.]1)(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$", u)))]), false)
    error_message = "Invalid or unsafe logout_urls; provide explicitly reviewed configuration."
  }
}
variable "default_redirect_uri" {
  type     = string
  nullable = false
  validation {
    condition     = try(contains(var.callback_urls, var.default_redirect_uri), false)
    error_message = "Invalid or unsafe default_redirect_uri; provide explicitly reviewed configuration."
  }
}
variable "resource_server_identifier" {
  type     = string
  nullable = false
  validation {
    condition     = try(can(regex("^[a-z][a-z0-9-]{2,50}$", var.resource_server_identifier)), false)
    error_message = "Invalid or unsafe resource_server_identifier; provide explicitly reviewed configuration."
  }
}
variable "scopes" {
  type     = map(string)
  nullable = false
  validation {
    condition     = try(length(var.scopes) > 0 && length(var.scopes) <= 10 && alltrue([for k, v in var.scopes : can(regex("^[a-z][a-z0-9_-]{0,31}$", k)) && length(trimspace(v)) > 0 && length(v) <= 256]), false)
    error_message = "Invalid or unsafe scopes; provide explicitly reviewed configuration."
  }
}
variable "approved_scope_names" {
  type     = set(string)
  nullable = false
  validation {
    condition     = try(length(var.approved_scope_names) > 0 && alltrue([for s in var.approved_scope_names : contains(keys(var.scopes), s)]), false)
    error_message = "Invalid or unsafe approved_scope_names; provide explicitly reviewed configuration."
  }
}
variable "mfa_configuration" {
  type     = string
  nullable = false
  validation {
    condition     = try(contains(["ON", "OPTIONAL"], var.mfa_configuration), false)
    error_message = "Invalid or unsafe mfa_configuration; provide explicitly reviewed configuration."
  }
}
variable "password_minimum_length" {
  type     = number
  nullable = false
  validation {
    condition     = try(var.password_minimum_length >= 14 && var.password_minimum_length <= 99 && floor(var.password_minimum_length) == var.password_minimum_length, false)
    error_message = "Invalid or unsafe password_minimum_length; provide explicitly reviewed configuration."
  }
}
variable "access_token_minutes" {
  type     = number
  nullable = false
  validation {
    condition     = try(var.access_token_minutes >= 5 && var.access_token_minutes <= 60 && floor(var.access_token_minutes) == var.access_token_minutes, false)
    error_message = "Invalid or unsafe access_token_minutes; provide explicitly reviewed configuration."
  }
}
variable "id_token_minutes" {
  type     = number
  nullable = false
  validation {
    condition     = try(var.id_token_minutes >= 5 && var.id_token_minutes <= 60 && floor(var.id_token_minutes) == var.id_token_minutes, false)
    error_message = "Invalid or unsafe id_token_minutes; provide explicitly reviewed configuration."
  }
}
variable "refresh_token_hours" {
  type     = number
  nullable = false
  validation {
    condition     = try(var.refresh_token_hours >= 1 && var.refresh_token_hours <= 24 && floor(var.refresh_token_hours) == var.refresh_token_hours, false)
    error_message = "Invalid or unsafe refresh_token_hours; provide explicitly reviewed configuration."
  }
}
variable "tags" {
  description = "Additional non-secret tags. project, env and managed come from provider default_tags; modules own Name and service."
  type        = map(string)
  default     = {}
  nullable    = false
  validation {
    condition     = length(setintersection(keys(var.tags), ["project", "env", "service", "managed", "Name"])) == 0
    error_message = "tags must not set project, env, service, managed or Name; the root and modules own those keys."
  }
}
