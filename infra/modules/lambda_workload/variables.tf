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
    condition = !can(regex("^(aws|aws-us-gov)$", var.partition)) || try(
      alltrue([for arn in var.layers : split(":", arn)[1] == var.partition]),
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
  description = "Stable non-secret name of the dedicated log group owned by this workload."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_./#-]{1,512}$", var.log_group_name)) && try(!startswith(var.log_group_name, "aws/"), false)
    error_message = "log_group_name must be 1-512 supported CloudWatch name characters and must not start with the Lambda-reserved literal prefix aws/."
  }
}


variable "tags" {
  description = "Optional visible, non-secret function tags; the module-owned Name and service tags win, and provider default_tags are owned by the root."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") && try(length(value) <= 256, false)
    ])
    error_message = "tags plus the module-owned Name and service must have at most 50 entries, 1-128-character non-reserved keys and non-null values of at most 256 characters."
  }
}

variable "policy_name" {
  description = "Stable explicit name of the one inline workload policy on the execution role, for example <project>-<env>-policy-lambda."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_+=,.@-]{1,128}$", var.policy_name))
    error_message = "policy_name must contain 1-128 supported IAM policy-name characters without paths, ARNs or wildcards."
  }
}

variable "role_name" {
  description = "Stable explicit workload execution-role name; no generated suffix or human-access role is created."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_+=,.@-]{1,64}$", var.role_name))
    error_message = "role_name must contain 1-64 supported IAM role-name characters without paths, ARNs or wildcards."
  }
}


variable "partition" {
  description = "Explicit supported AWS partition. China and other partitions are deliberately outside this phase's reviewed Lambda trust contract."
  type        = string

  validation {
    condition     = can(regex("^(aws|aws-us-gov)$", var.partition))
    error_message = "partition must be aws or aws-us-gov; aws-cn and other partitions are not supported by this phase."
  }
}


variable "account_id" {
  description = "Expected workload account for all resource references; the owning root must select and restrict the provider to this account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be an explicit 12-digit AWS account ID without wildcards."
  }
}


variable "region" {
  description = "Explicit workload region, consistent with the selected partition; existence and provider selection are verified externally."
  type        = string

  validation {
    condition = try(length(var.region) <= 63 && can(regex("^[a-z]{2}(-[a-z0-9]+)+-[0-9]+$", var.region)) &&
      (!can(regex("^(aws|aws-us-gov)$", var.partition)) ||
        (var.partition == "aws-us-gov" ? startswith(var.region, "us-gov-") :
    !can(regex("^(cn-|us-gov-|us-iso|eu-iso)", var.region)))), false)
    error_message = "region must be an explicit supported-shape region of at most 63 characters and use the selected partition's region family."
  }
}


variable "enable_secret_read" {
  description = "Genuine optional runtime permission for one exact secret; false grants no Secrets Manager or KMS access."
  type        = bool
  default     = false
  nullable    = false
}


variable "secret_arn" {
  description = "Optional actual resource-generated full secret ARN with its six-character suffix; never a secret value or reconstructed partial ARN."
  type        = string
  default     = null

  validation {
    condition     = var.enable_secret_read ? var.secret_arn != null : var.secret_arn == null
    error_message = "secret_arn is required when enable_secret_read is true and must be null when secret reading is disabled."
  }

  validation {
    condition     = var.secret_arn == null || can(regex(local.secret_pattern, var.secret_arn))
    error_message = "secret_arn must be null or a complete supported-partition Secrets Manager ARN with a valid name and generated six-character suffix; partial ARNs and wildcards are rejected."
  }

  validation {
    condition = var.secret_arn == null || !local.scope_is_valid || try(
      split(":", var.secret_arn)[1] == var.partition &&
      split(":", var.secret_arn)[3] == var.region &&
      split(":", var.secret_arn)[4] == var.account_id, false
    )
    error_message = "secret_arn must match the configured partition, workload region and expected account."
  }
}


variable "secret_kms_key_arn" {
  description = "Optional exact existing customer-managed KMS key ARN for the authorized secret; null adds no KMS permission and does not discover the key type."
  type        = string
  default     = null

  validation {
    condition     = var.secret_kms_key_arn == null || (var.enable_secret_read && var.secret_arn != null)
    error_message = "secret_kms_key_arn is permitted only with enable_secret_read true and an explicit secret_arn."
  }

  validation {
    condition = var.secret_kms_key_arn == null || try(
      length(var.secret_kms_key_arn) <= 256 && can(regex(local.key_pattern, var.secret_kms_key_arn)), false
    )
    error_message = "secret_kms_key_arn must be null or a complete supported-partition KMS key ARN of at most 256 characters with a UUID or mrk identifier; aliases, partial IDs and wildcards are rejected."
  }

  validation {
    condition = var.secret_kms_key_arn == null || !local.scope_is_valid || try(
      split(":", var.secret_kms_key_arn)[1] == var.partition &&
      split(":", var.secret_kms_key_arn)[3] == var.region &&
      split(":", var.secret_kms_key_arn)[4] == var.account_id, false
    )
    error_message = "secret_kms_key_arn must match the configured partition, workload region and expected account."
  }
}


variable "role_tags" {
  description = "Optional visible non-secret role tags; the module-owned Name and service tags win, and root default_tags remain root-owned."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.role_tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.role_tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256 && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value)), false)
    ])
    error_message = "tags plus the module-owned Name and service must have at most 50 non-secret entries; keys 1-128 and values 0-256 permitted Unicode characters, no null values or reserved aws: prefix."
  }
}

variable "log_retention_in_days" {
  description = "Explicit finite retention period in supported whole days; indefinite retention is not exposed by this module."
  type        = number
  default     = 30
  nullable    = false

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545,
      731, 1096, 1827, 2192, 2557, 2922, 3288, 3653
    ], var.log_retention_in_days)
    error_message = "log_retention_in_days must be one of 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288 or 3653; zero/indefinite retention is forbidden."
  }
}


variable "log_deletion_protection_enabled" {
  description = "Protect the log group from deletion by default; an authorized owner must first disable and apply this setting before a later destroy."
  type        = bool
  default     = true
  nullable    = false
}


variable "log_kms_key_arn" {
  description = "Optional existing symmetric customer-managed KMS key ARN; key usability, region, permissions and historical-log access are external responsibilities."
  type        = string
  default     = null

  validation {
    condition = var.log_kms_key_arn == null || (
      can(regex(
        "^arn:(aws|aws-us-gov):kms:[a-z]{2}(-[a-z0-9]+)+-[0-9]+:[0-9]{12}:key/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|mrk-[0-9a-f]{32})$",
        var.log_kms_key_arn
      )) && try(length(var.log_kms_key_arn) <= 256, false)
    )
    error_message = "log_kms_key_arn must be null or a complete KMS key ARN up to 256 characters with an explicit supported partition, region, 12-digit account and UUID or multi-region key ID; aliases, bare IDs and wildcards are rejected."
  }
  validation {
    condition = var.log_kms_key_arn == null || !local.scope_is_valid || try(
      split(":", var.log_kms_key_arn)[1] == var.partition &&
      split(":", var.log_kms_key_arn)[3] == var.region &&
      split(":", var.log_kms_key_arn)[4] == var.account_id, false
    )
    error_message = "The dedicated workload log key must match expected partition, Region and account; generic logging syntax remains independently supported."
  }
}


variable "log_tags" {
  description = "Optional visible, non-secret log group tags; the module-owned Name and service tags win, and provider default_tags remain root-owned."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = length(setunion(keys(var.log_tags), ["Name", "service"])) <= 50 && alltrue([for key, value in var.log_tags :
      length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
      can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
      try(length(value) <= 256, false) && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value))
    ])
    error_message = "tags plus the module-owned Name and service must have at most 50 entries, 1-128-character keys without the reserved aws: prefix, and non-null values up to 256 characters; only Unicode letters, separators, numbers and _ . : / = + @ - are supported."
  }
}
