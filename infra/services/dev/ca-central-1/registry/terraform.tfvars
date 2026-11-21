# Committed non-secret DEV values (docs/deployment-configuration.md section 1).
# Environment-specific values below are documented placeholders. Put the real
# values only in the untracked local.auto.tfvars (copy local.auto.tfvars.example);
# the local workflow refuses to plan or apply while a placeholder remains.
# The repositories come from kubernetes/images.lock.json, not from a variable.

project        = "project"      # placeholder
aws_account_id = "123456789012" # placeholder
