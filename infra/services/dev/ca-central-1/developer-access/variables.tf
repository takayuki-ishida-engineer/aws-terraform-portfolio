variable "project" {
  description = "Project token for resource names and the project tag; the committed placeholder is project. Lowercase, starts with a letter, at most 10 characters, no aws, amazon or cognito."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,8}[a-z0-9])?$", var.project)) && !can(regex("(aws|amazon|cognito)", var.project))
    error_message = "project must be 1-10 lowercase letters, digits or hyphens, start with a letter, not end with a hyphen and not contain aws, amazon or cognito."
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

variable "network_reference" {
  description = "Network root output (terraform -chdir=../network output -json network); only the fields below are used. Its scope must be this DEV account and Region."
  type = object({
    interface_version  = number
    scope              = object({ environment = string, partition = string, region = string, account_id = string })
    vpc_id             = string
    vpc_cidr           = string
    private_subnet_ids = map(string)
  })
  nullable = false
  validation {
    condition = (
      var.network_reference.interface_version == 1 &&
      var.network_reference.scope.environment == "dev" && var.network_reference.scope.partition == "aws" &&
      var.network_reference.scope.region == "ca-central-1" && var.network_reference.scope.account_id == var.aws_account_id
    )
    error_message = "network_reference must be interface version 1 for the dev environment in aws/ca-central-1 and this aws_account_id."
  }
}

variable "subnet_key" {
  description = "Private subnet key (from network_reference.private_subnet_ids) that hosts the instance; its CIDR must be in the platform root's api_client_cidrs to reach the private EKS endpoint."
  type        = string
  nullable    = false
  validation {
    condition     = contains(keys(var.network_reference.private_subnet_ids), var.subnet_key)
    error_message = "subnet_key must be a key of network_reference.private_subnet_ids."
  }
}

variable "instance_type" {
  description = "Instance type for the developer access host (validated by the module)."
  type        = string
  default     = "t3.micro"
  nullable    = false
}
