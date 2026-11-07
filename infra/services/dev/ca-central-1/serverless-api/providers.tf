provider "aws" {
  region              = local.region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Environment = local.environment
      Service     = local.service
      Project     = local.project
      ManagedBy   = "Terraform"
    }
  }
}
