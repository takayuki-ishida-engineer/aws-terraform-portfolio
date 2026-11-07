variable "aws_account_id" {
  description = "Expected AWS account ID for the provider account restriction; supply only in an authorized execution environment outside Codex Cloud."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly 12 decimal digits."
  }
}
