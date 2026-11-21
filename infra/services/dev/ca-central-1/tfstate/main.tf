locals {
  region      = "ca-central-1"
  environment = "dev"
  # Names and tags follow docs/deployment-configuration.md sections 4 and 5.
  name_prefix = "${var.project}-${local.environment}"
  default_tags = {
    project = var.project
    env     = local.environment
    managed = "terraform"
  }
  # Roots that may use the optional S3 backend; one State key per root (section 3).
  backend_roots = ["network", "platform", "serverless-api", "api", "developer-access", "registry"]
}

module "state_bucket" {
  source = "../../../../modules/tfstate_bucket"

  bucket_name = "${local.name_prefix}-s3-tfstate"
  tags        = var.tags
}
