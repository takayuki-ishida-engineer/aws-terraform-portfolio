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
  # The reviewed image lock (finding F18, item 6b-B2) is the only image inventory:
  # one private repository per locked purpose, named by the lock's own contract.
  image_lock = jsondecode(file("${path.module}/../../../../../kubernetes/images.lock.json"))
  purposes   = [for image in local.image_lock.images : image.purpose]
}

module "repositories" {
  source = "../../../../modules/ecr_repository"

  name_prefix    = local.name_prefix
  purposes       = toset(local.purposes)
  expected_scope = { account_id = var.aws_account_id, region = local.region }
  force_delete   = var.force_delete
  tags           = var.tags
}
