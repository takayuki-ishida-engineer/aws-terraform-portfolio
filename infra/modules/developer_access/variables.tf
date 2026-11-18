variable "name_prefix" {
  description = "Name prefix <project>-<env>; every name derives from it (docs/deployment-configuration.md section 4)."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,18}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 2-20 lowercase letters, digits or hyphens, start with a letter and not end with a hyphen."
  }
}

variable "vpc_id" {
  description = "VPC of the private subnet that hosts the instance (network root output)."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^vpc-[0-9a-f]{8,17}$", var.vpc_id))
    error_message = "vpc_id must look like vpc- followed by 8-17 hexadecimal characters."
  }
}

variable "vpc_cidr" {
  description = "VPC IPv4 CIDR; the only HTTPS egress destination (interface endpoints for Session Manager and the private EKS endpoint)."
  type        = string
  nullable    = false
  validation {
    condition     = try(cidrnetmask(var.vpc_cidr) != "" && cidrhost(var.vpc_cidr, 0) == split("/", var.vpc_cidr)[0] && tonumber(split("/", var.vpc_cidr)[1]) >= 16 && tonumber(split("/", var.vpc_cidr)[1]) <= 28, false)
    error_message = "vpc_cidr must be a canonical IPv4 network CIDR from /16 to /28."
  }
}

variable "subnet_id" {
  description = "Private subnet for the instance; it gets no public IP and needs no internet route."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^subnet-[0-9a-f]{8,17}$", var.subnet_id))
    error_message = "subnet_id must look like subnet- followed by 8-17 hexadecimal characters."
  }
}

variable "ami_id" {
  description = "Amazon Linux 2023 AMI ID (the root resolves the AWS public SSM parameter); the SSM agent is preinstalled."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.ami_id))
    error_message = "ami_id must look like ami- followed by 8-17 hexadecimal characters."
  }
}

variable "instance_type" {
  description = "Instance type; port forwarding needs very little capacity."
  type        = string
  default     = "t3.micro"
  nullable    = false
  validation {
    condition     = contains(["t3.nano", "t3.micro", "t3.small"], var.instance_type)
    error_message = "instance_type must be t3.nano, t3.micro or t3.small (x86_64, matching the AL2023 x86_64 AMI)."
  }
}

variable "default_tags" {
  description = "The root's provider default tags (project, env, managed), repeated on the root volume because provider default tags do not reach volumes created with an instance."
  type        = map(string)
  default     = {}
  nullable    = false
  validation {
    condition     = length(setsubtract(keys(var.default_tags), ["project", "env", "managed"])) == 0
    error_message = "default_tags may hold only project, env and managed."
  }
}

variable "tags" {
  description = "Optional extra caller tags. Name and service are module owned and the aws: prefix is reserved, so those keys are rejected."
  type        = map(string)
  default     = {}
  nullable    = false
  validation {
    condition = length(setunion(keys(var.tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") && !contains(["Name", "service"], key) &&
      try(length(value) <= 256, false)
    ])
    error_message = "tags must not set Name, service or an aws: key and, with Name and service, hold at most 50 entries with 1-128-character keys and values up to 256 characters."
  }
}
