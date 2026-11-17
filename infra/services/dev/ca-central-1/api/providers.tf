provider "aws" {
  region              = "ca-central-1"
  allowed_account_ids = [var.aws_account_id]
  default_tags { tags = local.default_tags }
}
