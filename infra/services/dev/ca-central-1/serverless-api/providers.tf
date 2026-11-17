provider "aws" {
  region              = local.region
  allowed_account_ids = [var.aws_account_id]

  # Tag keys follow docs/deployment-configuration.md section 5; modules own Name
  # and service. The secret's project tag is also module-owned for IAM ABAC.
  default_tags {
    tags = {
      project = var.project
      env     = local.environment
      managed = "terraform"
    }
  }
}
