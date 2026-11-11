output "authentication" {
  description = "Versioned public metadata only; not tokens, user data, publication or live OAuth evidence."
  value = {
    interface_version          = 1
    scope                      = var.expected_scope
    user_pool_id               = aws_cognito_user_pool.this.id
    user_pool_arn              = aws_cognito_user_pool.this.arn
    app_client_id              = aws_cognito_user_pool_client.this.id
    resource_server_identifier = aws_cognito_resource_server.this.identifier
    approved_custom_scopes     = [for s in sort(tolist(var.approved_scope_names)) : "${aws_cognito_resource_server.this.identifier}/${s}"]
    domain_prefix              = aws_cognito_user_pool_domain.this.domain
    issuer_url                 = "https://${aws_cognito_user_pool.this.endpoint}"
    managed_login_branding_id  = aws_cognito_managed_login_branding.this.managed_login_branding_id
  }
}
