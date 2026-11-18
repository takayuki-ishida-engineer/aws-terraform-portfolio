variable "aws_account_id" {
  description = "Expected AWS account ID for the provider account restriction; supply only in an authorized execution environment outside Codex Cloud."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly 12 decimal digits."
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

variable "artifact_key" {
  description = "Exact non-secret ZIP object key recorded by the approved external artifact publication process; no upload or discovery occurs here."
  type        = string
  nullable    = false
}

variable "artifact_object_version" {
  description = "Exact immutable non-null S3 ZIP object version recorded after external publication; no fabricated or automatically discovered default."
  type        = string
  nullable    = false
}

variable "lambda_runtime" {
  description = "Explicit approved ZIP runtime: nodejs22.x, python3.13 or java21; the existing Lambda module validates this contract."
  type        = string
  nullable    = false
}

variable "lambda_handler" {
  description = "Actual handler selected for the approved ZIP artifact and runtime; syntax validation does not prove artifact compatibility."
  type        = string
  nullable    = false
}

variable "enable_secret_read" {
  description = "Allow runtime reads of only the actual secret metadata ARN and supply SECRET_ARN to Lambda; authorization-sensitive changes require plan review."
  type        = bool
  default     = false
  nullable    = false
}

variable "log_deletion_protection" {
  description = "Deletion protection for the Lambda and HTTP API log groups. Keep true; set false and apply only as the first teardown step, because a protected log group blocks terraform destroy."
  type        = bool
  default     = true
  nullable    = false
}
