resource "aws_api_gateway_rest_api" "this" {
  name                         = "${var.name_prefix}-apigw-rest"
  disable_execute_api_endpoint = true
  endpoint_configuration { types = ["REGIONAL"] }
  # Names and tags follow docs/deployment-configuration.md sections 4 and 5;
  # project, env and managed come from the root provider default_tags.
  tags = merge(var.tags, { Name = "${var.name_prefix}-apigw-rest", service = "apigw" })
}
resource "aws_api_gateway_authorizer" "this" {
  name            = "${var.name_prefix}-apigw-rest-cognito"
  rest_api_id     = aws_api_gateway_rest_api.this.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.authentication.user_pool_arn]
  identity_source = "method.request.header.Authorization"
}
