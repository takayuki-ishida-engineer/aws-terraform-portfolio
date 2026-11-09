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

variable "private_routing" {
  description = "Explicit layout and optional zonal NAT mappings. Omitted private AZs have no NAT default; null NAT creates isolated per-AZ tables."
  type = object({
    mode = optional(string, "legacy_shared")
    nat = optional(object({
      public_subnet_key_by_nat_az = map(string)
      nat_az_by_private_az        = map(string)
    }))
  })
  default  = {}
  nullable = false

  validation {
    condition     = contains(["legacy_shared", "per_az"], var.private_routing.mode)
    error_message = "private_routing.mode must be legacy_shared or per_az."
  }
  validation {
    condition     = var.private_routing.nat == null ? true : try(length(var.private_routing.nat.public_subnet_key_by_nat_az) > 0 && length(var.private_routing.nat.nat_az_by_private_az) > 0, false)
    error_message = "Use null to disable NAT; an enabled NAT object must contain nonempty gateway and routing maps."
  }
}

variable "expected_scope" {
  description = "Required for opt-in extensions: expected commercial ca-central-1 account scope, checked against the actual VPC ARN. Not authentication."
  type        = object({ partition = string, region = string, account_id = string })
  default     = null
  validation {
    condition     = var.expected_scope == null ? true : try(var.expected_scope.partition == "aws" && var.expected_scope.region == "ca-central-1" && can(regex("^[0-9]{12}$", var.expected_scope.account_id)), false)
    error_message = "Extension scope must be aws/ca-central-1 and an explicit 12-digit account ID. Other extension catalogs require separate review."
  }
}

variable "gateway_endpoints" {
  description = "Optional reviewed S3 Gateway Endpoint. Explicit private AZ tables and a scoped read-only role/bucket policy are required; no implicit full-access policy."
  type = map(object({
    private_route_table_azs = set(string)
    policy_json             = string
  }))
  default  = {}
  nullable = false
  validation {
    condition     = alltrue([for service, endpoint in var.gateway_endpoints : service == "s3" && try(length(endpoint.private_route_table_azs) > 0, false)])
    error_message = "Only the use-justified S3 gateway service is implemented; select at least one explicit private AZ table."
  }
  validation {
    condition = alltrue([for endpoint in var.gateway_endpoints : try(
      jsondecode(endpoint.policy_json).Version == "2012-10-17" &&
      startswith(jsonencode(jsondecode(endpoint.policy_json).Statement), "[") &&
      length(setsubtract(toset(keys(jsondecode(endpoint.policy_json))), toset(["Version", "Statement"]))) == 0 &&
      length(jsondecode(endpoint.policy_json).Statement) > 0 &&
      alltrue([for statement in jsondecode(endpoint.policy_json).Statement :
        statement.Effect == "Allow" &&
        length(setsubtract(toset(keys(statement)), toset(["Sid", "Effect", "Principal", "Action", "Resource"]))) == 0 &&
        toset(keys(statement.Principal)) == toset(["AWS"]) &&
        length(try(tolist(statement.Principal.AWS), [statement.Principal.AWS])) > 0 &&
        alltrue([for principal in try(tolist(statement.Principal.AWS), [statement.Principal.AWS]) : can(regex("^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$", principal))]) &&
        length(try(tolist(statement.Action), [statement.Action])) > 0 &&
        alltrue([for action in try(tolist(statement.Action), [statement.Action]) : contains(["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket", "s3:GetBucketLocation"], action)]) &&
        length(try(tolist(statement.Resource), [statement.Resource])) > 0 &&
        alltrue([for resource in try(tolist(statement.Resource), [statement.Resource]) : can(regex("^arn:aws:s3:::[a-z0-9][a-z0-9.-]{1,61}[a-z0-9](/[^*?]*\\*?)?$", resource))]) &&
        alltrue([for action in try(tolist(statement.Action), [statement.Action]) : alltrue([for resource in try(tolist(statement.Resource), [statement.Resource]) : contains(["s3:ListBucket", "s3:GetBucketLocation"], action) ? !strcontains(resource, "/") : strcontains(resource, "/")])])
    ]), false)])
    error_message = "Endpoint policy must be explicit 2012-10-17 Allow statements with exact AWS role principals, scoped bucket/object ARNs and supported read-only actions; no wildcards in actions/principals/bucket names, unsupported keys or mixed bucket/object scopes."
  }
}
