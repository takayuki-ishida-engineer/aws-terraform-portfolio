terraform {
  required_version = "= 1.17.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.72.0" }
  }
  backend "local" {}
}
variable "ca_file" {
  type = string
}
variable "run_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]+-[0-9]+$", var.run_id))
    error_message = "Use the Actions run ID and attempt."
  }
}
variable "phase" {
  type = string
  validation {
    condition     = contains(["create", "updated"], var.phase)
    error_message = "Only the reviewed tag update is allowed."
  }
}
provider "aws" {
  region              = "ca-central-1"
  max_retries         = 2
  allowed_account_ids = ["000000000000"]
  custom_ca_bundle    = var.ca_file
  endpoints {
    ec2 = "https://127.0.0.1:9297"
    sts = "https://127.0.0.1:9297"
  }
}
resource "aws_vpc" "proof" {
  cidr_block           = "10.238.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = false
  tags = {
    Name            = "emulator-proof-${var.run_id}"
    VerificationRun = var.run_id
    Phase           = var.phase
  }
}
