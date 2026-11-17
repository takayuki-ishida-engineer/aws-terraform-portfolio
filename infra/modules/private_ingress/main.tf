resource "aws_lb" "this" {
  name                                                         = "${var.name_prefix}-nlb"
  load_balancer_type                                           = "network"
  internal                                                     = true
  ip_address_type                                              = "ipv4"
  subnets                                                      = [for k in sort(tolist(var.subnet_keys)) : var.network_reference.private_subnet_ids[k]]
  security_groups                                              = [aws_security_group.nlb.id]
  enable_cross_zone_load_balancing                             = var.cross_zone_enabled
  enable_deletion_protection                                   = var.deletion_protection
  enforce_security_group_inbound_rules_on_private_link_traffic = "on"
  tags                                                         = merge(var.tags, { Name = "${var.name_prefix}-nlb", service = "nlb" })
  depends_on                                                   = [aws_vpc_security_group_ingress_rule.nlb_clients, aws_vpc_security_group_egress_rule.client_nlb, aws_vpc_security_group_egress_rule.nlb_targets, aws_vpc_security_group_ingress_rule.nodes_targets]
  lifecycle {
    postcondition {
      condition     = self.vpc_id == var.network_reference.vpc_id
      error_message = "Actual NLB VPC must match the approved network reference."
    }
  }
}
resource "aws_lb_target_group" "gateway" {
  name                              = "${var.name_prefix}-tg-gw"
  port                              = var.backend_target_port
  protocol                          = "TCP"
  target_type                       = "ip"
  ip_address_type                   = "ipv4"
  vpc_id                            = var.network_reference.vpc_id
  preserve_client_ip                = false
  proxy_protocol_v2                 = false
  load_balancing_cross_zone_enabled = "use_load_balancer_configuration"
  deregistration_delay              = 300
  connection_termination            = true
  health_check {
    enabled             = true
    protocol            = "TCP"
    port                = "traffic-port"
    interval            = 30
    healthy_threshold   = 3
    unhealthy_threshold = 3
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-tg-gw", service = "tg" })
}
resource "aws_lb_listener" "https_passthrough" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-nlb-tcp443", service = "nlb" })
}
