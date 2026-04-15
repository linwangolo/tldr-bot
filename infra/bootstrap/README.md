# Terraform Bootstrap

Creates prerequisite resources for GitHub Actions + Terraform deploys:

- S3 bucket for Terraform state
- DynamoDB table for state locking
- GitHub OIDC provider + IAM deploy role

## Usage

From repo root:

```bash
cd infra/bootstrap
terraform init
terraform apply \
  -var="github_org=<your-org-or-user>" \
  -var="github_repo=<your-repo>"
```

Optional overrides:

- `project_name`, `environment`
- `state_bucket_name`
- `lock_table_name`
- `deploy_role_name`
- `oidc_sub_pattern` (default: `repo:<org>/<repo>:*`)

## Wire outputs to GitHub

Take the Terraform outputs and set:

- GitHub Secret: `TF_BACKEND_BUCKET` = `tf_backend_bucket`
- GitHub Secret: `TF_BACKEND_DDB_TABLE` = `tf_backend_dynamodb_table`
- GitHub Secret: `AWS_TERRAFORM_DEPLOY_ROLE_ARN` = `terraform_deploy_role_arn`
- GitHub Variable: `AWS_REGION` = your deployment region (for this repo: `eu-west-2`)

Optional:

- GitHub Variable: `TF_PROJECT_NAME`
- GitHub Variable: `TF_ENVIRONMENT`

