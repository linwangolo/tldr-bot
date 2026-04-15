output "tf_backend_bucket" {
  value       = aws_s3_bucket.tf_state.id
  description = "Use as TF_BACKEND_BUCKET secret in GitHub."
}

output "tf_backend_dynamodb_table" {
  value       = aws_dynamodb_table.tf_lock.name
  description = "Use as TF_BACKEND_DDB_TABLE secret in GitHub."
}

output "terraform_deploy_role_arn" {
  value       = aws_iam_role.terraform_deploy.arn
  description = "Use as AWS_TERRAFORM_DEPLOY_ROLE_ARN secret in GitHub."
}

output "oidc_subject_pattern" {
  value       = local.effective_oidc_sub_pattern
  description = "Subject pattern allowed by IAM trust policy."
}

