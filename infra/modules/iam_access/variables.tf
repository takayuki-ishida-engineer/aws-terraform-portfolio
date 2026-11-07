variable "name_prefix" {
  description = "Inventory Name tag prefix; Permission Set identities remain fixed as Portfolio-Access-Admin, Portfolio-Developer, and Portfolio-Operator."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$", var.name_prefix))
    error_message = "name_prefix must be 1-63 letters, digits, underscores or hyphens, starting with a letter or digit."
  }
}

variable "instance_arn" {
  description = "Explicit existing organization IAM Identity Center instance ARN; this module does not discover or create an instance."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^arn:(aws|aws-us-gov|aws-cn):sso:::instance/ssoins-[A-Za-z0-9.-]{16}$", var.instance_arn))
    error_message = "instance_arn must identify an existing organization instance: arn:<partition>:sso:::instance/ssoins-<16-character-id>."
  }
}

variable "target_account_ids" {
  description = "Nonempty set of explicitly approved member AWS account IDs; existence, organization membership, and management-account exclusion require external verification."
  type        = set(string)
  nullable    = false

  validation {
    condition     = length(var.target_account_ids) > 0 && alltrue([for id in var.target_account_ids : can(regex("^[0-9]{12}$", id))])
    error_message = "target_account_ids must be a nonempty set of exactly 12-digit account ID strings."
  }
}

variable "administration_account_id" {
  description = "Management or registered IAM Identity Center delegated-administrator account in which Access Admin operates; not an assignment target. Registration must be verified externally."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{12}$", var.administration_account_id))
    error_message = "administration_account_id must be exactly 12 decimal digits."
  }

  validation {
    condition     = !contains(var.target_account_ids, var.administration_account_id)
    error_message = "The administration account must be separate from the approved workload assignment targets."
  }
}

variable "target_region" {
  description = "Explicit portfolio region for EC2 and Operator secret-metadata permissions; its existence and partition compatibility must be verified outside Codex Cloud."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.target_region))
    error_message = "target_region must be an explicit AWS region identifier without wildcards."
  }
}

variable "project_tag" {
  description = "Reviewed Project tag value used for EC2 and Operator secret-metadata conditions and Permission Set inventory; per-account managed policies must use the same project contract."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.project_tag))
    error_message = "project_tag must be 1-63 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "tags" {
  description = "Additional Permission Set tags; module-owned Name and Project tags take precedence."
  type        = map(string)
  default     = {}
  nullable    = false
}
