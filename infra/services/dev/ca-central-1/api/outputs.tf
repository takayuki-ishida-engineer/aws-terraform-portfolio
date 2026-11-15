output "authentication" {
  value = module.cognito_auth.authentication
}
output "rest_core" {
  value = module.api_gateway_rest.rest_core
}
