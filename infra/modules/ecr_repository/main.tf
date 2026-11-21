# Private ECR repositories for the digest-pinned runtime image mirror (finding F18,
# Step 1 item 6b-B1). Images are copied in by the operator with skopeo, keeping the
# upstream index digests; nodes pull through the existing ECR endpoints.
#
# Deliberately absent:
# - a repository policy: same-account IAM governs access; there is no public or
#   cross-account access;
# - a lifecycle policy: no automatic expiry, so no multi-architecture index, child
#   manifest or older digest needed for a rollback is ever removed automatically;
# - pull through cache rules, Secrets Manager secrets, KMS keys and IAM roles.
resource "aws_ecr_repository" "this" {
  for_each = var.purposes

  name = "${var.name_prefix}-ecr-${each.key}"
  # Tags never move: a digest-pinned reference and its tag stay the same image.
  image_tag_mutability = "IMMUTABLE"
  # Terraform refuses to delete a repository that still holds images unless the
  # root's teardown switch is set.
  force_delete = var.force_delete

  # Amazon ECR managed AES-256 encryption: no customer managed KMS key or cost.
  encryption_configuration {
    encryption_type = "AES256"
  }

  # Scanning stays off: its cost is not stated in the official documentation, and
  # the images are pinned by upstream digest (residual risk in the README).
  image_scanning_configuration {
    scan_on_push = false
  }

  # Module-owned Name and service tags (docs/deployment-configuration.md section 5).
  tags = merge(var.tags, { Name = "${var.name_prefix}-ecr-${each.key}", service = "ecr" })

  lifecycle {
    postcondition {
      condition = (
        self.region == var.expected_scope.region &&
        self.registry_id == var.expected_scope.account_id &&
        self.arn == "arn:aws:ecr:${var.expected_scope.region}:${var.expected_scope.account_id}:repository/${self.name}" &&
        self.repository_url == "${var.expected_scope.account_id}.dkr.ecr.${var.expected_scope.region}.amazonaws.com/${self.name}"
      )
      error_message = "The repository must belong to the expected account and Region: Region, registry ID, ARN and URL."
    }
  }
}
