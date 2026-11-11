output "private_ingress" {
  description = "Versioned, non-secret actual ingress references. Not state publication, registered-target or TLS evidence."
  value = {
    interface_version                 = 1
    scope                             = var.expected_scope
    nlb_arn                           = aws_lb.this.arn
    nlb_dns_name                      = aws_lb.this.dns_name
    nlb_zone_id                       = aws_lb.this.zone_id
    listener_arn                      = aws_lb_listener.https_passthrough.arn
    target_group_arn                  = aws_lb_target_group.gateway.arn
    target_group_name                 = aws_lb_target_group.gateway.name
    nlb_security_group_id             = aws_security_group.nlb.id
    vpc_link_client_security_group_id = aws_security_group.vpc_link_client.id
    private_subnet_ids                = { for k in var.subnet_keys : k => var.network_reference.private_subnet_ids[k] }
    vpc_id                            = aws_lb_target_group.gateway.vpc_id
    backend_target_port               = aws_lb_target_group.gateway.port
    cross_zone_enabled                = aws_lb.this.enable_cross_zone_load_balancing
  }
}

output "controller_identity" {
  description = "Actual registration-only IRSA identity; no credential or proof of live authorization."
  value = {
    interface_version = 1
    scope             = var.expected_scope
    role_arn          = aws_iam_role.controller.arn
    oidc_issuer       = var.controller_oidc.issuer
    oidc_provider_arn = var.controller_oidc.provider_arn
    namespace         = "kube-system"
    service_account   = "aws-load-balancer-controller"
    target_group_arn  = aws_lb_target_group.gateway.arn
  }
  depends_on = [aws_iam_role_policy.controller]
}
