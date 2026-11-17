resource "aws_s3_bucket" "this" {
  bucket           = var.bucket_name
  bucket_namespace = "global"
  force_destroy    = false
  # Module-owned Name and service tags (docs/deployment-configuration.md section 5).
  tags = merge(var.tags, { Name = var.bucket_name, service = "s3" })

  lifecycle {
    postcondition {
      condition = length(self.tags_all) <= 50 && alltrue([for key, value in self.tags_all :
        length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
        try(length(value) <= 256, false)
      ])
      error_message = "Effective bucket tags, including root-owned provider default_tags, must contain at most 50 non-secret tags with 1-128-character non-reserved keys and non-null values up to 256 characters."
    }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
      Condition = {
        Bool = {
          "aws:SecureTransport"       = "false"
          "aws:PrincipalIsAWSService" = "false"
        }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.this]
}
