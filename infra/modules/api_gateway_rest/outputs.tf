output "rest_core" {
  description = "Nonsecret actual resource references; no invoke path or runtime authorization claim."
  value = {
    interface_version      = 1
    scope                  = var.expected_scope
    rest_api_id            = aws_api_gateway_rest_api.this.id
    authorizer_id          = aws_api_gateway_authorizer.this.id
    user_pool_arn          = one(aws_api_gateway_authorizer.this.provider_arns)
    approved_custom_scopes = var.authentication.approved_custom_scopes
  }
}
