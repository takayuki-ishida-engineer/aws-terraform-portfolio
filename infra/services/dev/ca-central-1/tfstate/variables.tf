variable "project" {
  description = "Project token for resource names and the project tag; the committed placeholder is project. Lowercase, starts with a letter, at most 10 characters, no aws, amazon or cognito."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,8}[a-z0-9])?$", var.project)) && !can(regex("(aws|amazon|cognito)", var.project))
    error_message = "project must be 1-10 lowercase letters, digits or hyphens, start with a letter, not end with a hyphen and not contain aws, amazon or cognito."
  }
}

variable "aws_account_id" {
  description = "Required expected dedicated non-management workload account; verify approval externally. No credentials."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly 12 decimal digits."
  }
}

variable "tags" {
  description = "Optional extra caller tags. project, env and managed come from provider default_tags and Name and service from the module, so those keys are rejected here."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition     = length(setintersection(toset(keys(var.tags)), toset(["project", "env", "service", "managed", "Name"]))) == 0
    error_message = "tags must not set project, env, service, managed or Name; those are owned by default_tags and the module."
  }
}
