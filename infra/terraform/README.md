# Terraform Deployment

This folder deploys the TLDR bot infrastructure from scratch with Terraform.

## Resources created

- S3 bucket for artifacts (`summaries/*`, `audio/*`) with 30-day lifecycle
- S3 public-read policy for `summaries/*` and `audio/*` only
- IAM role + inline policy for Lambda
- Lambda layer (from packaged deps zip)
- Lambda function (pipeline)
- EventBridge schedule + target + invoke permission

## Naming convention

Names are generated from:

- `project_name` (default `tldrbot`)
- `environment` (default `prod`)

Examples:

- Lambda: `tldrbot-prod-pipeline`
- Event rule: `tldrbot-prod-daily`
- Role: `tldrbot-prod-lambda-role`

Bucket name:

- If `artifacts_bucket_name` is empty, Terraform generates:
  `"{project_name}-{environment}-{account_id}-{region}"`

## Package Lambda artifacts

From repo root:

```bash
chmod +x scripts/package_lambda_assets.sh
./scripts/package_lambda_assets.sh
```

This creates:

- `infra/terraform/dist/lambda_function.zip`
- `infra/terraform/dist/lambda_layer.zip`

## Backend init

```bash
cd infra/terraform
terraform init \
  -backend-config="bucket=<tf-state-bucket>" \
  -backend-config="key=tldr-bot/terraform.tfstate" \
  -backend-config="region=eu-west-2" \
  -backend-config="dynamodb_table=<tf-lock-table>" \
  -backend-config="encrypt=true"
```

## Required bootstrap (outside this module)

Create bootstrap resources once per account before running CI or local apply:

- S3 bucket for Terraform state (`TF_BACKEND_BUCKET`)
- DynamoDB table for Terraform state locking (`TF_BACKEND_DDB_TABLE`)
- IAM role for GitHub OIDC deploys (`AWS_TERRAFORM_DEPLOY_ROLE_ARN`)

Use:

- `infra/bootstrap` (see [bootstrap README](/Users/irene/Documents/lin/tldr-bot/infra/bootstrap/README.md))

## Deploy

```bash
terraform plan
terraform apply
```

## Optional parallel rollout safety

To avoid duplicate scheduled posts while testing in parallel, disable schedule first:

```bash
terraform apply -var='schedule_enabled=false'
```

Then test with manual lambda invoke, and enable schedule later:

```bash
terraform apply -var='schedule_enabled=true'
```
