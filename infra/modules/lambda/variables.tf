variable "function_name" {
  description = "Stable non-sensitive Lambda name; qualified names, ARNs and aliases are not accepted."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,64}$", var.function_name))
    error_message = "function_name must contain 1-64 ASCII letters, digits, underscores or hyphens."
  }
}

variable "description" {
  description = "Optional visible, non-sensitive function description."
  type        = string
  default     = null

  validation {
    condition     = var.description == null || try(length(var.description) <= 256, false)
    error_message = "description must be null or at most 256 characters."
  }
}

variable "execution_role_arn" {
  description = "Existing Lambda execution role ARN with reviewed trust and workload permissions; this module grants nothing."
  type        = string

  validation {
    condition = can(regex(
      "^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/([A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}$",
      var.execution_role_arn
    )) && try(length(var.execution_role_arn) <= 2048, false)
    error_message = "execution_role_arn must be a complete IAM role ARN in a supported partition, with an explicit 12-digit account and role name; users, STS sessions and wildcard ARNs are rejected."
  }
}

variable "s3_bucket" {
  description = "Name of an existing general-purpose S3 artifact bucket; the caller verifies versioning, access and region compatibility."
  type        = string

  validation {
    condition = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.s3_bucket)) && try(
      !can(regex("\\.\\.|\\.-|-\\.", var.s3_bucket)) &&
      !can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.s3_bucket)) &&
      !startswith(var.s3_bucket, "xn--") && !startswith(var.s3_bucket, "sthree-") &&
      !startswith(var.s3_bucket, "amzn_s3_demo_") &&
      !can(regex("(-s3alias|--ol-s3|\\.mrap|--x-s3|--table-s3|--vector-s3)$", var.s3_bucket)),
      false
    )
    error_message = "s3_bucket must be a 3-63-character lowercase DNS bucket name, not an ARN, URI, IP address, reserved bucket form or malformed dotted name."
  }
}

variable "s3_key" {
  description = "Exact existing ZIP object's S3 key, not a URI or local filename to build/upload; non-secret and at most 1024 UTF-8 bytes."
  type        = string

  validation {
    condition = try(
      length(trimspace(var.s3_key)) > 0 &&
      !can(regex("^[A-Za-z][A-Za-z0-9+.-]*://", var.s3_key)) &&
      !can(regex("[\\x00-\\x1f\\x7f]", var.s3_key)) &&
      (length(base64encode(var.s3_key)) / 4 * 3 - (endswith(base64encode(var.s3_key), "==") ? 2 : endswith(base64encode(var.s3_key), "=") ? 1 : 0)) <= 1024,
      false
    )
    error_message = "s3_key must be a nonblank literal S3 object key of at most 1024 UTF-8 bytes, without URI prefixes or control characters."
  }
}

variable "s3_object_version" {
  description = "Explicit immutable version ID of the existing ZIP object; the S3 null version is forbidden."
  type        = string

  validation {
    condition     = can(regex("^[!-~]+$", var.s3_object_version)) && try(length(var.s3_object_version) <= 1024 && lower(var.s3_object_version) != "null", false)
    error_message = "s3_object_version must be an explicit nonblank 1-1024-character printable ASCII version ID, without whitespace; the null-version sentinel is not allowed."
  }
}

variable "runtime" {
  description = "Explicit reviewed managed ZIP runtime: nodejs22.x, python3.13 or java21; artifact compatibility is verified externally."
  type        = string

  validation {
    condition     = contains(["nodejs22.x", "python3.13", "java21"], var.runtime)
    error_message = "runtime must be one of the reviewed managed ZIP runtimes: nodejs22.x, python3.13 or java21."
  }
}

variable "handler" {
  description = "Explicit handler compatible with the selected runtime and existing ZIP artifact; syntax validation cannot inspect code."
  type        = string

  validation {
    condition = try(
      length(var.handler) >= 1 && length(var.handler) <= 128 &&
      (var.runtime == "java21" ? can(regex("^[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)*(::[A-Za-z_$][A-Za-z0-9_$]*)?$", var.handler)) :
        var.runtime == "python3.13" ? can(regex("^[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)+$", var.handler)) :
        var.runtime == "nodejs22.x" ? can(regex("^[A-Za-z0-9_./-]+\\.[A-Za-z_$][A-Za-z0-9_$]*$", var.handler)) :
      !can(regex("\\s", var.handler))),
      false
    )
    error_message = "handler must be 1-128 non-whitespace characters using the selected runtime's supported syntax: Python module.function, Node.js file.export, or Java Class[::method]."
  }
}

variable "architecture" {
  description = "One instruction-set architecture; compatible code, dependencies and layers must already exist."
  type        = string
  default     = "x86_64"
  nullable    = false

  validation {
    condition     = contains(["x86_64", "arm64"], var.architecture)
    error_message = "architecture must be x86_64 or arm64."
  }
}

variable "memory_size" {
  description = "Memory allocation in MB for standard Lambda execution, not Lambda Managed Instances."
  type        = number
  default     = 128
  nullable    = false

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240 && var.memory_size == floor(var.memory_size)
    error_message = "memory_size must be an integer from 128 through 10240 MB."
  }
}

variable "timeout" {
  description = "Maximum invocation duration in whole seconds; real downstream timeouts must be reviewed by the caller."
  type        = number
  default     = 10
  nullable    = false

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 900 && var.timeout == floor(var.timeout)
    error_message = "timeout must be an integer from 1 through 900 seconds."
  }
}

variable "ephemeral_storage_size" {
  description = "Ephemeral /tmp capacity in MB; allocations above the included 512 MB can incur additional charges."
  type        = number
  default     = 512
  nullable    = false

  validation {
    condition     = var.ephemeral_storage_size >= 512 && var.ephemeral_storage_size <= 10240 && var.ephemeral_storage_size == floor(var.ephemeral_storage_size)
    error_message = "ephemeral_storage_size must be an integer from 512 through 10240 MB."
  }
}

variable "environment_variables" {
  description = "Non-secret configuration only, including optional secret ARN/name references. Never pass secret values: Terraform records these inputs in plans/state."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = alltrue([for key in keys(var.environment_variables) :
      can(regex("^[A-Za-z][A-Za-z0-9_]+$", key)) && !contains([
        "AWS_DEFAULT_REGION", "AWS_REGION", "AWS_EXECUTION_ENV", "AWS_LAMBDA_FUNCTION_NAME",
        "AWS_LAMBDA_FUNCTION_MEMORY_SIZE", "AWS_LAMBDA_FUNCTION_VERSION", "AWS_LAMBDA_INITIALIZATION_TYPE",
        "AWS_LAMBDA_LOG_GROUP_NAME", "AWS_LAMBDA_LOG_STREAM_NAME", "AWS_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_LAMBDA_RUNTIME_API", "LAMBDA_TASK_ROOT",
        "LAMBDA_RUNTIME_DIR", "AWS_LAMBDA_MAX_CONCURRENCY", "AWS_LAMBDA_METADATA_API", "AWS_LAMBDA_METADATA_TOKEN"
      ], key)
    ]) && alltrue([for value in values(var.environment_variables) : value != null])
    error_message = "Environment keys must start with a letter, contain at least two letters/digits/underscores, and not be reserved Lambda runtime/credential keys; values must be non-null non-secret configuration."
  }

  validation {
    condition = try(sum(concat([0], [for text in concat(keys(var.environment_variables), values(var.environment_variables)) :
      length(base64encode(text)) / 4 * 3 - (endswith(base64encode(text), "==") ? 2 : endswith(base64encode(text), "=") ? 1 : 0)
    ])) <= 4096, false)
    error_message = "Environment variable keys and values together must fit within Lambda's 4096-byte UTF-8 limit; this does not detect or permit secret values."
  }
}

variable "layers" {
  description = "Up to five distinct existing versioned Lambda layer ARNs, in application order; runtime/architecture/region and access compatibility are external prerequisites."
  type        = list(string)
  default     = []
  nullable    = false

  validation {
    condition = try(length(var.layers) <= 5 && length(distinct(var.layers)) == length(var.layers) && alltrue([
      for arn in var.layers : length(arn) <= 140 && can(regex(
        "^arn:(aws|aws-us-gov|aws-cn):lambda:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:layer:[A-Za-z0-9_-]+:[1-9][0-9]*$", arn
      ))
    ]), false)
    error_message = "layers must contain at most five distinct complete Lambda layer-version ARNs, each at most 140 characters with an explicit supported partition, region, account and positive version."
  }

  validation {
    condition = !can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/", var.execution_role_arn)) || try(
      alltrue([for arn in var.layers : split(":", arn)[1] == split(":", var.execution_role_arn)[1]]),
      false
    )
    error_message = "Every layer ARN must use the same AWS partition as the execution role; the caller must separately verify the Lambda region and compatibility."
  }
}

variable "reserved_concurrent_executions" {
  description = "Optional whole-number reserved concurrency; null leaves the unreserved account pool unchanged, while zero intentionally disables invocation."
  type        = number
  default     = null

  validation {
    condition     = var.reserved_concurrent_executions == null || try(var.reserved_concurrent_executions >= 0 && var.reserved_concurrent_executions <= 2147483647 && var.reserved_concurrent_executions == floor(var.reserved_concurrent_executions), false)
    error_message = "reserved_concurrent_executions must be null or a whole number from 0 through the API int32 maximum 2147483647; account quotas and remaining unreserved capacity are external constraints."
  }
}

variable "subnet_ids" {
  description = "Optional distinct existing VPC subnet IDs; provide together with security_group_ids and externally reviewed ENI permissions/network access."
  type        = list(string)
  default     = []
  nullable    = false

  validation {
    condition     = length(var.subnet_ids) <= 16 && length(distinct(var.subnet_ids)) == length(var.subnet_ids) && alltrue([for id in var.subnet_ids : can(regex("^subnet-([0-9a-f]{8}|[0-9a-f]{17})$", id))])
    error_message = "subnet_ids must contain at most 16 distinct valid subnet IDs using either eight or 17 lowercase hexadecimal characters."
  }
}

variable "security_group_ids" {
  description = "Optional distinct existing VPC security group IDs; an empty subnet list requires an empty group list, and attachment requires both."
  type        = list(string)
  default     = []
  nullable    = false

  validation {
    condition     = length(var.security_group_ids) <= 5 && length(distinct(var.security_group_ids)) == length(var.security_group_ids) && alltrue([for id in var.security_group_ids : can(regex("^sg-([0-9a-f]{8}|[0-9a-f]{17})$", id))])
    error_message = "security_group_ids must contain at most five distinct valid security group IDs using either eight or 17 lowercase hexadecimal characters."
  }

  validation {
    condition     = (length(var.subnet_ids) == 0) == (length(var.security_group_ids) == 0)
    error_message = "VPC attachment requires both nonempty subnet_ids and security_group_ids; leave both lists empty to disable attachment."
  }
}

variable "log_group_name" {
  description = "Name of an already provisioned CloudWatch Log Group; retention, access and ordering are owned outside this module."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_./#-]{1,512}$", var.log_group_name)) && try(!startswith(var.log_group_name, "aws/"), false)
    error_message = "log_group_name must be 1-512 supported CloudWatch name characters and must not start with the Lambda-reserved literal prefix aws/."
  }
}

variable "tags" {
  description = "Optional visible, non-secret function tags, passed through without module-added keys; provider default_tags are owned by the root."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(var.tags) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") && try(length(value) <= 256, false)
    ])
    error_message = "tags must have at most 50 entries, 1-128-character non-reserved keys and non-null values of at most 256 characters."
  }
}
