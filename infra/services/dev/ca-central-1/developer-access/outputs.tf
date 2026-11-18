output "developer_access" {
  description = "Session Manager target and network identity of the developer access host; non-secret."
  value = {
    instance_id       = module.developer_access.instance_id
    private_ip        = module.developer_access.private_ip
    security_group_id = module.developer_access.security_group_id
    role_arn          = module.developer_access.role_arn
    region            = local.region
  }
}
