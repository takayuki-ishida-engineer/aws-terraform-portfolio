output "instance_id" {
  description = "Instance ID, the Session Manager target for port forwarding."
  value       = aws_instance.this.id
}

output "security_group_id" {
  description = "Security group of the host (no inbound rules)."
  value       = aws_security_group.this.id
}

output "role_arn" {
  description = "Instance role ARN (AmazonSSMManagedInstanceCore only)."
  value       = aws_iam_role.this.arn
}

output "private_ip" {
  description = "Private IPv4 address; private service security groups can allow it."
  value       = aws_instance.this.private_ip
}
