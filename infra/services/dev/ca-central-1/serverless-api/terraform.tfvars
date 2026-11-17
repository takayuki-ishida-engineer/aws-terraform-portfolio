# Committed non-secret DEV values (docs/deployment-configuration.md section 1).
# Environment-specific values below are documented placeholders. Put the real
# values only in the untracked local.auto.tfvars (copy local.auto.tfvars.example);
# the local workflow refuses to plan or apply while a placeholder remains.

project        = "project"      # placeholder
aws_account_id = "123456789012" # placeholder

# The committed package in function/ (main.handler, Python).
lambda_runtime = "python3.13"
lambda_handler = "main.handler"
artifact_key   = "lambda/function.zip"

# Placeholder: the S3 object version recorded after function.zip is uploaded to
# the artifact bucket. Replace it in local.auto.tfvars.
artifact_object_version = "placeholder-object-version"
