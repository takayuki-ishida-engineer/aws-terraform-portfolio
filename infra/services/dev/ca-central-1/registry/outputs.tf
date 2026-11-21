output "registry" {
  description = "For the operator's mirror copy (B3): the private registry host and, per locked purpose, the repository name, ARN and URL. No credentials or tokens."
  value = {
    host         = "${var.aws_account_id}.dkr.ecr.${local.region}.amazonaws.com"
    repositories = module.repositories.repositories
  }

  precondition {
    # The lock's registry contract must be the one this root implements, and each
    # purpose must appear once, so no repository is silently merged or invented.
    condition = (
      local.image_lock.lock_version == 1 &&
      local.image_lock.registry == {
        region     = local.region
        host       = "$${account_id}.dkr.ecr.ca-central-1.amazonaws.com"
        repository = "$${project}-dev-ecr-$${purpose}"
        reference  = "digest"
      } &&
      length(local.purposes) > 0 &&
      length(distinct(local.purposes)) == length(local.purposes) &&
      alltrue([for purpose, repository in module.repositories.repositories : repository.name == "${local.name_prefix}-ecr-${purpose}"])
    )
    error_message = "kubernetes/images.lock.json must use registry contract version 1 (ca-central-1, <project>-dev-ecr-<purpose>, digest references) with each purpose once, and every repository must carry its purpose's name."
  }
}
