variable "aws_region" {
  description = "AWS region for bootstrap resources."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Project/service name prefix."
  type        = string
  default     = "tldrbot"
}

variable "environment" {
  description = "Environment name."
  type        = string
  default     = "prod"
}

variable "github_org" {
  description = "GitHub organization or user name."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name."
  type        = string
}

variable "state_bucket_name" {
  description = "Optional explicit Terraform state bucket name. Leave empty to auto-generate."
  type        = string
  default     = ""
}

variable "lock_table_name" {
  description = "Optional explicit DynamoDB lock table name. Leave empty to auto-generate."
  type        = string
  default     = ""
}

variable "deploy_role_name" {
  description = "Optional explicit IAM deploy role name. Leave empty to auto-generate."
  type        = string
  default     = ""
}

variable "oidc_sub_pattern" {
  description = "OIDC subject pattern allowed to assume the role. Example: repo:org/repo:*"
  type        = string
  default     = ""
}

