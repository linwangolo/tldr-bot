"""
TLDR daily pipeline: Gmail -> parse -> summarize -> save summary + audio to S3 -> post to Slack.
"""
import logging
import os
from urllib.parse import quote

# Lambda defaults to WARNING; set root logger and its handlers so INFO appears in CloudWatch
_root = logging.getLogger()
_root.setLevel(logging.INFO)
for _h in _root.handlers:
    _h.setLevel(logging.INFO)

import json
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

from email_reader import get_secret, fetch_tldr_emails
from parser import parse_emails_to_issues
from summarizer import summarize, generate_bullet_summary
from tts import synthesize_to_s3
from slack_notifier import post_briefing


ARTIFACTS_BUCKET = os.environ["ARTIFACTS_BUCKET"]
GMAIL_SECRET_NAME = os.environ["GMAIL_SECRET_NAME"]
GMAIL_ADDRESS_SECRET_NAME = os.environ["GMAIL_ADDRESS_SECRET_NAME"]
SLACK_SECRET_NAME = os.environ["SLACK_SECRET_NAME"]
POLLY_S3_ROLE_ARN = os.environ.get("POLLY_S3_ROLE_ARN") or ""
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _collect_references(issues: list[dict]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for issue in issues:
        for item in issue.get("items") or []:
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            references.append({"title": title[:150], "url": url})

    return references


def lambda_handler(event, context):
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y-%m-%d")
    weekday = now_utc.strftime("%A")

    if weekday in {"Sunday", "Monday"}:
        logger.info("skipping_fetch_no_expected_newsletters weekday=%s date=%s", weekday, date_str)
        return {"status": "skipped_no_newsletter_day", "date": date_str, "weekday": weekday}

    s3 = boto3.client("s3", region_name=AWS_REGION)

    gmail_user = get_secret(GMAIL_ADDRESS_SECRET_NAME)
    gmail_pass = get_secret(GMAIL_SECRET_NAME)
    slack_webhook = get_secret(SLACK_SECRET_NAME)

    target_days_ago = int(os.environ.get("TLDR_TARGET_DAYS_AGO", "1"))
    emails = fetch_tldr_emails(gmail_user, gmail_pass, target_days_ago=target_days_ago)
    emails_fetched = len(emails)
    logger.info("emails_fetched=%s", emails_fetched)
    if not emails:
        logger.warning("no_emails")
        return {"status": "no_emails", "date": date_str}

    issues = parse_emails_to_issues(emails)
    issues_count = len(issues)
    logger.info("issues_count=%s", issues_count)
    if not issues:
        logger.warning("no_issues_after_parse emails_fetched=%s", emails_fetched)
        return {"status": "no_issues", "date": date_str}

    summary_text = summarize(issues, region=AWS_REGION)
    references = _collect_references(issues)
    bullet_summary_text = generate_bullet_summary(summary_text, issues, region=AWS_REGION)

    summary_key = f"summaries/{date_str}.json"
    full_summary_key = f"summaries/{date_str}.txt"
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
        "references": references,
        "summary_text": summary_text,
        "metadata": {"generated_at": datetime.now(timezone.utc).isoformat()},
    }
    s3.put_object(
        Bucket=ARTIFACTS_BUCKET,
        Key=summary_key,
        Body=json.dumps(summary_doc, indent=2),
        ContentType="application/json",
    )
    s3.put_object(
        Bucket=ARTIFACTS_BUCKET,
        Key=full_summary_key,
        Body=summary_text,
        ContentType="text/plain; charset=utf-8",
    )

    audio_key = f"audio/{date_str}.mp3"
    synthesize_to_s3(
        summary_text,
        ARTIFACTS_BUCKET,
        audio_key,
        polly_role_arn=POLLY_S3_ROLE_ARN or None,
        region=AWS_REGION,
    )

    full_summary_url = f"https://{ARTIFACTS_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{quote(full_summary_key)}"
    audio_url = f"https://{ARTIFACTS_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{quote(audio_key)}"

    logger.info("slack_post_start date=%s", date_str)
    post_briefing(
        webhook_url=slack_webhook,
        bullet_summary_text=bullet_summary_text,
        full_summary_url=full_summary_url,
        audio_url=audio_url,
        date_str=date_str,
    )
    logger.info("slack_post_success date=%s", date_str)

    return {
        "status": "success",
        "date": date_str,
        "summary_key": summary_key,
        "full_summary_key": full_summary_key,
        "audio_key": audio_key,
        "issues_count": len(issues),
    }
