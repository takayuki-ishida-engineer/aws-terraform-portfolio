# Committed non-secret DEV values (docs/deployment-configuration.md section 1).
# Environment-specific values below are documented placeholders. Put the real
# values only in the untracked local.auto.tfvars (copy local.auto.tfvars.example);
# the local workflow refuses to plan or apply while a placeholder remains.

project        = "project"      # placeholder
aws_account_id = "123456789012" # placeholder

# Application URLs use the placeholder domain example.com.
callback_urls        = ["https://app.example.com/callback"]
logout_urls          = ["https://app.example.com/logout"]
default_redirect_uri = "https://app.example.com/callback"
allow_dev_loopback   = false

feature_plan               = "ESSENTIALS"
resource_server_identifier = "portfolio-api"
scopes = {
  read  = "Read approved records"
  write = "Write approved records"
}
approved_scope_names    = ["read"]
mfa_configuration       = "ON"
password_minimum_length = 14
access_token_minutes    = 15
id_token_minutes        = 15
refresh_token_hours     = 8
