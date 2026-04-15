output "bucket_name" {
  value = aws_s3_bucket.artifacts.id
}

output "lambda_function_name" {
  value = aws_lambda_function.pipeline.function_name
}

output "event_rule_name" {
  value = aws_cloudwatch_event_rule.daily.name
}

output "lambda_layer_arn" {
  value = aws_lambda_layer_version.deps.arn
}

output "summary_base_url" {
  value = "https://${aws_s3_bucket.artifacts.id}.s3.${var.aws_region}.amazonaws.com/summaries/"
}

output "audio_base_url" {
  value = "https://${aws_s3_bucket.artifacts.id}.s3.${var.aws_region}.amazonaws.com/audio/"
}
