variable "name_prefix" {
  description = "Resource Name tag prefix: 1-63 letters, digits, underscores or hyphens, starting with a letter or digit."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$", var.name_prefix))
    error_message = "name_prefix must be 1-63 letters, digits, underscores or hyphens and start with a letter or digit."
  }
}

variable "vpc_cidr" {
  description = "Canonical IPv4 network CIDR for the VPC, with an AWS-supported prefix length from /16 to /28."
  type        = string
  nullable    = false

  validation {
    condition = try(
      cidrnetmask(var.vpc_cidr) != "" &&
      tonumber(split("/", var.vpc_cidr)[1]) >= 16 &&
      tonumber(split("/", var.vpc_cidr)[1]) <= 28 &&
      cidrhost(var.vpc_cidr, 0) == split("/", var.vpc_cidr)[0],
      false
    )
    error_message = "vpc_cidr must be a canonical IPv4 network CIDR with a prefix length from /16 to /28."
  }
}

variable "private_subnets" {
  description = "At least one private subnet, keyed by stable caller-chosen identity; each value supplies an IPv4 network CIDR and an explicit Availability Zone name."
  type = map(object({
    cidr_block        = string
    availability_zone = string
  }))
  nullable = false

  validation {
    condition     = length(var.private_subnets) > 0 && alltrue([for key in keys(var.private_subnets) : trimspace(key) != ""])
    error_message = "private_subnets must contain at least one subnet and no empty or whitespace-only keys."
  }

  validation {
    condition = alltrue([for subnet in var.private_subnets : try(
      cidrnetmask(subnet.cidr_block) != "" &&
      tonumber(split("/", subnet.cidr_block)[1]) >= 16 &&
      tonumber(split("/", subnet.cidr_block)[1]) <= 28 &&
      cidrhost(subnet.cidr_block, 0) == split("/", subnet.cidr_block)[0],
      false
    )])
    error_message = "Every private subnet must have a canonical IPv4 network CIDR with a prefix length from /16 to /28."
  }

  validation {
    condition     = alltrue([for subnet in var.private_subnets : can(regex("^[a-z]{2}(-[a-z0-9]+)+-[0-9]+[a-z]$", subnet.availability_zone))])
    error_message = "Every private subnet must supply a nonempty Availability Zone name, such as a region name followed by its zone letter."
  }
}

variable "public_subnets" {
  description = "Optional public subnets keyed by stable identity; an empty map omits the entire public networking path. Public IPv4 assignment remains disabled."
  type = map(object({
    cidr_block        = string
    availability_zone = string
  }))
  default  = {}
  nullable = false

  validation {
    condition     = alltrue([for key in keys(var.public_subnets) : trimspace(key) != ""])
    error_message = "public_subnets must not contain empty or whitespace-only keys."
  }

  validation {
    condition = alltrue([for subnet in var.public_subnets : try(
      cidrnetmask(subnet.cidr_block) != "" &&
      tonumber(split("/", subnet.cidr_block)[1]) >= 16 &&
      tonumber(split("/", subnet.cidr_block)[1]) <= 28 &&
      cidrhost(subnet.cidr_block, 0) == split("/", subnet.cidr_block)[0],
      false
    )])
    error_message = "Every public subnet must have a canonical IPv4 network CIDR with a prefix length from /16 to /28."
  }

  validation {
    condition     = alltrue([for subnet in var.public_subnets : can(regex("^[a-z]{2}(-[a-z0-9]+)+-[0-9]+[a-z]$", subnet.availability_zone))])
    error_message = "Every public subnet must supply a nonempty Availability Zone name, such as a region name followed by its zone letter."
  }
}

variable "tags" {
  description = "Caller tags; the module-owned Name tag takes precedence on every resource."
  type        = map(string)
  default     = {}
  nullable    = false
}
