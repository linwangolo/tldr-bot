locals {
  name_prefix = lower("${var.project_name}-${var.environment}")

  generated_state_bucket_name = lower(replace(
    "${local.name_prefix}-tfstate-${data.aws_caller_identity.current.account_id}-${var.aws_region}",
    "_",
    "-"
  ))
  generated_lock_table_name = "${local.name_prefix}-terraform-locks"
  generated_deploy_role     = "${local.name_prefix}-terraform-deploy-role"

  effective_state_bucket_name = var.state_bucket_name != "" ? var.state_bucket_name : local.generated_state_bucket_name
  effective_lock_table_name   = var.lock_table_name != "" ? var.lock_table_name : local.generated_lock_table_name
  effective_deploy_role_name  = var.deploy_role_name != "" ? var.deploy_role_name : local.generated_deploy_role

  effective_oidc_sub_pattern = var.oidc_sub_pattern != "" ? var.oidc_sub_pattern : "repo:${var.github_org}/${var.github_repo}:*"
}

resource "aws_s3_bucket" "tf_state" {
  bucket        = local.effective_state_bucket_name
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = local.effective_lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.effective_oidc_sub_pattern]
    }
  }
}

resource "aws_iam_role" "terraform_deploy" {
  name               = local.effective_deploy_role_name
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json
}

data "aws_iam_policy_document" "terraform_deploy" {
  statement {
    sid    = "TerraformStateAccess"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketVersioning",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      aws_s3_bucket.tf_state.arn,
      "${aws_s3_bucket.tf_state.arn}/*"
    ]
  }

  statement {
    sid    = "TerraformLockAccess"
    effect = "Allow"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:UpdateItem"
    ]
    resources = [aws_dynamodb_table.tf_lock.arn]
  }

  statement {
    sid    = "InfraDeployAccess"
    effect = "Allow"
    actions = [
      "lambda:*",
      "events:*",
      "iam:*",
      "s3:*",
      "logs:*",
      "cloudwatch:*",
      "bedrock:*",
      "polly:*",
      "secretsmanager:GetSecretValue",
      "sts:GetCallerIdentity"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "terraform_deploy" {
  name   = "${local.name_prefix}-terraform-deploy-policy"
  role   = aws_iam_role.terraform_deploy.id
  policy = data.aws_iam_policy_document.terraform_deploy.json
}

