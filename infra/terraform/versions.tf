terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Configure with `terraform init -backend-config=...` (see infra/terraform/README.md)
  backend "s3" {}
}

