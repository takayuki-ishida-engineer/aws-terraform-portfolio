locals {
  required_tags = { Environment = var.expected_scope.environment, Service = "api", Project = "aws-terraform-portfolio", ManagedBy = "Terraform" }
}
resource "aws_api_gateway_rest_api" "this" {
  name                         = var.name
  disable_execute_api_endpoint = true
  endpoint_configuration { types = ["REGIONAL"] }
  tags = merge(var.tags, local.required_tags)
}
resource "aws_api_gateway_authorizer" "this" {
  name            = "${var.name}-cognito"
  rest_api_id     = aws_api_gateway_rest_api.this.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.authentication.user_pool_arn]
  identity_source = "method.request.header.Authorization"
}
