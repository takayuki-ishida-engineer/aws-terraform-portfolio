locals {
  # These checks describe the explicit caller contract, not the authenticated
  # provider account. The owning root must restrict its selected AWS provider.
  scope_is_valid = (
    can(regex("^(aws|aws-us-gov)$", var.partition)) &&
    can(regex("^[0-9]{12}$", var.account_id)) &&
    try(length(var.region) <= 63 && can(regex("^[a-z]{2}(-[a-z0-9]+)+-[0-9]+$", var.region)) &&
      (var.partition == "aws-us-gov" ? startswith(var.region, "us-gov-") :
    !can(regex("^(cn-|us-gov-|us-iso|eu-iso)", var.region))), false)
  )

  log_group_pattern = "^arn:(aws|aws-us-gov):logs:([a-z]{2}(?:-[a-z0-9]+)+-[0-9]+):([0-9]{12}):log-group:([A-Za-z0-9_./#-]{1,512})$"
  secret_pattern    = "^arn:(aws|aws-us-gov):secretsmanager:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]{1,512}-[A-Za-z0-9]{6}$"
  key_pattern       = "^arn:(aws|aws-us-gov):kms:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:key/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})$"

  trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaServiceAssumeRole"
      Effect    = "Allow"
      Action    = ["sts:AssumeRole"]
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  # Null fallbacks only keep malformed inputs from causing interpolation errors
  # before their own variable validation reports the intended failure.
  workload_policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
        Sid      = "WriteExistingLogStreams"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${var.log_group_arn == null ? "" : var.log_group_arn}:log-stream:*"]
      }],
      var.enable_secret_read ? [{
        Sid      = "ReadAuthorizedSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
        Resource = [var.secret_arn]
      }] : [],
      var.enable_secret_read && var.secret_kms_key_arn != null ? [{
        Sid      = "DecryptAuthorizedSecret"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [var.secret_kms_key_arn]
        Condition = {
          StringEquals = {
            # AWS KMS ViaService uses .amazonaws.com in every AWS partition;
            # it is not the ordinary regional service DNS endpoint spelling.
            "kms:ViaService"                  = "secretsmanager.${var.region == null ? "" : var.region}.amazonaws.com"
            "kms:EncryptionContext:SecretARN" = var.secret_arn
            "kms:CallerAccount"               = var.account_id
          }
        }
      }] : []
    )
  })
}
