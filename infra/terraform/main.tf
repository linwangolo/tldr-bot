locals {
  lambda_zip_path = "${path.module}/${var.lambda_zip_filename}"
  layer_zip_path  = "${path.module}/${var.layer_zip_filename}"

  name_prefix = lower("${var.project_name}-${var.environment}")

  generated_bucket_name = lower(replace(
    "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${var.aws_region}",
    "_",
    "-"
  ))
  effective_bucket_name = var.artifacts_bucket_name != "" ? var.artifacts_bucket_name : local.generated_bucket_name

  lambda_role_name   = "${local.name_prefix}-lambda-role"
  lambda_policy_name = "${local.name_prefix}-lambda-inline"
  lambda_name        = "${local.name_prefix}-pipeline"
  layer_name         = "${local.name_prefix}-deps-layer"
  event_rule_name    = "${local.name_prefix}-daily"
  event_target_id    = "lambda-target"
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.effective_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-30-days"
    status = "Enabled"
    filter {}

    expiration {
      days = 30
    }
  }
}

data "aws_iam_policy_document" "artifacts_public_read" {
  statement {
    sid    = "PublicReadSummariesAndAudioOnly"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/summaries/*",
      "${aws_s3_bucket.artifacts.arn}/audio/*"
    ]
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts_public_read.json
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = local.lambda_role_name
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_inline" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject*",
      "s3:GetBucket*",
      "s3:List*",
      "s3:DeleteObject*",
      "s3:PutObject",
      "s3:PutObjectLegalHold",
      "s3:PutObjectRetention",
      "s3:PutObjectTagging",
      "s3:PutObjectVersionTagging",
      "s3:Abort*"
    ]
    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*"
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:tldr-bot*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["polly:SynthesizeSpeech"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_inline" {
  name   = local.lambda_policy_name
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_inline.json
}

resource "aws_lambda_layer_version" "deps" {
  layer_name          = local.layer_name
  description         = "BeautifulSoup4 and lxml for TLDR parser"
  filename            = local.layer_zip_path
  source_code_hash    = filebase64sha256(local.layer_zip_path)
  compatible_runtimes = ["python3.11"]
}

resource "aws_lambda_function" "pipeline" {
  function_name    = local.lambda_name
  filename         = local.lambda_zip_path
  source_code_hash = filebase64sha256(local.lambda_zip_path)
  role             = aws_iam_role.lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 512
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      ARTIFACTS_BUCKET           = aws_s3_bucket.artifacts.id
      GMAIL_SECRET_NAME          = "tldr-bot/gmail-app-password"
      GMAIL_ADDRESS_SECRET_NAME  = "tldr-bot/gmail-address"
      SLACK_SECRET_NAME          = "tldr-bot/slack-webhook-url"
      TLDR_TARGET_DAYS_AGO       = "1"
      BEDROCK_MODEL_ID           = "anthropic.claude-3-haiku-20240307-v1:0"
      BULLET_BEDROCK_MODEL_ID    = "anthropic.claude-3-haiku-20240307-v1:0"
      FALLBACK_BEDROCK_MODEL_ID  = "openai.gpt-oss-120b-1:0"
      SUMMARY_MAX_TOKENS         = "6000"
      OPENAI_CONTINUATION_PASSES = "1"
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_inline,
    aws_iam_role_policy_attachment.lambda_basic_execution
  ]
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = local.event_rule_name
  description         = "Trigger TLDR pipeline daily"
  schedule_expression = var.schedule_expression
  state               = var.schedule_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily.name
  target_id = local.event_target_id
  arn       = aws_lambda_function.pipeline.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "${local.name_prefix}-allow-eventbridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pipeline.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily.arn
}
