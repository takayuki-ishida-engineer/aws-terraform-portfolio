variable "project" {
  description = "Project token for resource names and the project tag; the committed placeholder is project. Lowercase, starts with a letter, at most 10 characters, no aws, amazon or cognito."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,8}[a-z0-9])?$", var.project)) && !can(regex("(aws|amazon|cognito)", var.project))
    error_message = "project must be 1-10 lowercase letters, digits or hyphens, start with a letter, not end with a hyphen and not contain aws, amazon or cognito."
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
    condition     = alltrue([for key in keys(var.private_subnets) : can(regex("^private[1-9][0-9]*$", key))])
    error_message = "private_subnets keys must be private1, private2, ... as the tier number in resource names."
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
  description = "Required nonempty DEV public subnet allocation for the explicitly requested NAT/IGW path. Automatic public IPv4 assignment remains disabled."
  type = map(object({
    cidr_block        = string
    availability_zone = string
  }))
  nullable = false

  validation {
    condition     = length(var.public_subnets) > 0 && alltrue([for key in keys(var.public_subnets) : trimspace(key) != ""])
    error_message = "DEV public_subnets must be nonempty with no blank keys for the NAT/IGW path."
  }

  validation {
    condition     = alltrue([for key in keys(var.public_subnets) : can(regex("^public[1-9][0-9]*$", key))])
    error_message = "public_subnets keys must be public1, public2, ... as the tier number in resource names."
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
  description = "Optional extra caller tags. project, env and managed come from provider default_tags and Name and service from the module, so those keys are rejected here."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition     = length(setintersection(toset(keys(var.tags)), toset(["project", "env", "service", "managed", "Name"]))) == 0
    error_message = "tags must not set project, env, service, managed or Name; those are owned by default_tags and the module."
  }
}


variable "aws_account_id" {
  description = "Required expected dedicated non-management workload account; verify approval externally. No credentials."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly 12 decimal digits."
  }
}
variable "active_workload_az" {
  description = "Required single active DEV worker AZ; real enabled AZ/allocation approval is external."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^ca-central-1[a-z]$", var.active_workload_az)) && contains([for subnet in var.private_subnets : subnet.availability_zone], var.active_workload_az)
    error_message = "The active DEV AZ must be a configured private ca-central-1 AZ."
  }
}
variable "nat" {
  description = "Exactly one public NAT in the active DEV AZ. Explicit private-AZ mappings show every cross-AZ consumer; mappings are not proof of approval."
  type = object({
    public_subnet_key_by_nat_az = map(string)
    nat_az_by_private_az        = map(string)
  })
  nullable = false
  validation {
    condition = try(length(var.nat.public_subnet_key_by_nat_az) == 1 &&
      toset(keys(var.nat.public_subnet_key_by_nat_az)) == toset([var.active_workload_az]) &&
    var.nat.nat_az_by_private_az[var.active_workload_az] == var.active_workload_az, false)
    error_message = "DEV requires exactly one public NAT in the active AZ and a same-AZ active workload route. Additional cross-AZ routes must be explicit."
  }
}

variable "gateway_endpoints" {
  description = "Optional S3 gateway configuration forwarded to the child, which exclusively validates its policy, scope and selected-table contract."
  type = map(object({
    private_route_table_azs = set(string)
    policy_json             = string
  }))
  default  = {}
  nullable = false
}
