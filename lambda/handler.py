"""
TLDR daily pipeline: Gmail -> parse -> summarize -> save summary + audio to S3 -> post to Slack.
"""
import os
import json
from datetime import datetime, timezone

import boto3

from email_reader import get_secret, fetch_tldr_emails
from parser import parse_emails_to_issues
from summarizer import summarize
from tts import synthesize_to_s3
from slack_notifier import post_briefing


ARTIFACTS_BUCKET = os.environ["ARTIFACTS_BUCKET"]
GMAIL_SECRET_NAME = os.environ["GMAIL_SECRET_NAME"]
GMAIL_ADDRESS_SECRET_NAME = os.environ["GMAIL_ADDRESS_SECRET_NAME"]
SLACK_SECRET_NAME = os.environ["SLACK_SECRET_NAME"]
POLLY_S3_ROLE_ARN = os.environ.get("POLLY_S3_ROLE_ARN") or ""
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

PRESIGNED_EXPIRY = 86400  # 24 hours


def lambda_handler(event, context):
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s3 = boto3.client("s3", region_name=AWS_REGION)

    gmail_user = get_secret(GMAIL_ADDRESS_SECRET_NAME)
    gmail_pass = get_secret(GMAIL_SECRET_NAME)
    slack_webhook = get_secret(SLACK_SECRET_NAME)

    emails = fetch_tldr_emails(gmail_user, gmail_pass, since_days=1)
    if not emails:
        return {"status": "no_emails", "date": date_str}

    issues = parse_emails_to_issues(emails)
    if not issues:
        return {"status": "no_issues", "date": date_str}

    summary_text = summarize(issues, region=AWS_REGION)

    summary_key = f"summaries/{date_str}.json"
    summary_doc = {
        "date": date_str,
        "newsletter_sources": [i.get("newsletter_name") for i in issues],
        "issues": [
            {
                "newsletter_name": i.get("newsletter_name"),
                "title": i.get("title"),
                "url": i.get("url"),
                "sections": i.get("sections"),
            }
            for i in issues
        ],
        "summary_text": summary_text,
        "metadata": {"generated_at": datetime.now(timezone.utc).isoformat()},
    }
    s3.put_object(
        Bucket=ARTIFACTS_BUCKET,
        Key=summary_key,
        Body=json.dumps(summary_doc, indent=2),
        ContentType="application/json",
    )

    audio_key = f"audio/{date_str}.mp3"
    synthesize_to_s3(
        summary_text,
        ARTIFACTS_BUCKET,
        audio_key,
        polly_role_arn=POLLY_S3_ROLE_ARN or None,
        region=AWS_REGION,
    )

    summary_presigned = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": ARTIFACTS_BUCKET, "Key": summary_key},
        ExpiresIn=PRESIGNED_EXPIRY,
    )
    audio_presigned = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": ARTIFACTS_BUCKET, "Key": audio_key},
        ExpiresIn=PRESIGNED_EXPIRY,
    )

    post_briefing(
        webhook_url=slack_webhook,
        summary_text=summary_text,
        summary_json_url=summary_presigned,
        audio_url=audio_presigned,
        date_str=date_str,
    )

    return {
        "status": "success",
        "date": date_str,
        "summary_key": summary_key,
        "audio_key": audio_key,
        "issues_count": len(issues),
    }
