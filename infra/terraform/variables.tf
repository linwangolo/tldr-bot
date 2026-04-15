variable "aws_region" {
  description = "AWS region for deployment."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Project/service name used as name prefix."
  type        = string
  default     = "tldrbot"
}

variable "environment" {
  description = "Environment name (e.g. dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "artifacts_bucket_name" {
  description = "Optional explicit bucket name. Leave empty to auto-generate from project/env/account/region."
  type        = string
  default     = ""
}

variable "schedule_expression" {
  description = "EventBridge schedule expression."
  type        = string
  default     = "cron(30 7 * * ? *)"
}

variable "schedule_enabled" {
  description = "Whether daily EventBridge schedule is enabled."
  type        = bool
  default     = true
}

variable "lambda_zip_filename" {
  description = "Relative path from this module to packaged lambda zip."
  type        = string
  default     = "dist/lambda_function.zip"
}

variable "layer_zip_filename" {
  description = "Relative path from this module to packaged layer zip."
  type        = string
  default     = "dist/lambda_layer.zip"
}
