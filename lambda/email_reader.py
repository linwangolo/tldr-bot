"""
Gmail IMAP reader: connect, search for TLDR newsletters in the last N days, return raw email content.
"""
import imaplib
import email
import logging
import time
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from typing import Any
import boto3

logger = logging.getLogger(__name__)
IMAP_LOGIN_ATTEMPTS = 3
IMAP_LOGIN_BACKOFF_SECONDS = 2


def get_secret(secret_name: str) -> str:
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_name)
    if "SecretString" in resp:
        return resp["SecretString"]
    raise ValueError(f"Secret {secret_name} has no SecretString")


def decode_mime_header(header: str | None) -> str:
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part or "")
    return " ".join(result).strip()


def extract_html_body(msg: email.message.Message) -> str | None:
    """Extract text/html part from a possibly multipart message."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
    return None


def fetch_tldr_emails(
    gmail_address: str,
    app_password: str,
    target_days_ago: int = 1,
    from_domain: str = "tldrnewsletter.com",
    from_address: str = "dan@tldrnewsletter.com",
) -> list[dict[str, Any]]:
    """
    Connect to Gmail via IMAP and search a single UTC calendar day window for TLDR emails.
    By default, this targets yesterday (target_days_ago=1) instead of the current day.
    Returns list of { "subject", "html_body", "date", "newsletter_name" }.
    Prefers Gmail X-GM-RAW search when available; falls back to FROM + SINCE + BEFORE.
    """
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        last_login_error: Exception | None = None
        for attempt in range(1, IMAP_LOGIN_ATTEMPTS + 1):
            try:
                mail.login(gmail_address, app_password)
                break
            except imaplib.IMAP4.error as e:
                last_login_error = e
                logger.warning("imap_login_failed attempt=%s error=%s", attempt, str(e))
                if attempt == IMAP_LOGIN_ATTEMPTS:
                    raise
                time.sleep(IMAP_LOGIN_BACKOFF_SECONDS * attempt)
        mail.select("INBOX")

        window_end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=target_days_ago - 1)
        window_start = window_end - timedelta(days=1)
        gmail_after = window_start.strftime("%Y/%m/%d")
        gmail_before = window_end.strftime("%Y/%m/%d")
        imap_since = window_start.strftime("%d-%b-%Y")
        imap_before = window_end.strftime("%d-%b-%Y")

        id_list: list[bytes] = []
        search_mode = "x-gm-raw"
        try:
            gmail_query = f'from:{from_address} after:{gmail_after} before:{gmail_before}'
            status, messages = mail.search(None, "X-GM-RAW", f'"{gmail_query}"')
            logger.info("xgmraw_search_status=%s raw_response=%s", status, messages)
            if status == "OK" and messages[0]:
                id_list = messages[0].split()
        except Exception as e:
            logger.warning("xgmraw_search_failed using_fallback error=%s", str(e))
        if not id_list:
            search_mode = "fallback-from-since"
            logger.info("using_fallback_imap_search")
            status, messages = mail.search(None, f'(FROM "{from_address}" SINCE {imap_since} BEFORE {imap_before})')
            logger.info("fallback_search_status=%s raw_response=%s", status, messages)
            if status != "OK" or not messages[0]:
                logger.warning(
                    "no_matching_emails search_mode=%s from_address=%s target_days_ago=%s window_start=%s window_end=%s",
                    search_mode,
                    from_address,
                    target_days_ago,
                    window_start.isoformat(),
                    window_end.isoformat(),
                )
                return []
            id_list = messages[0].split()

        logger.info(
            "imap_uid_count=%s search_mode=%s target_days_ago=%s window_start=%s window_end=%s",
            len(id_list),
            search_mode,
            target_days_ago,
            window_start.isoformat(),
            window_end.isoformat(),
        )
        results = []
        skipped_no_html = 0
        sample_subjects: list[str] = []

        for uid in id_list:
            status, data = mail.fetch(uid, "(RFC822)")
            if status != "OK" or not data:
                continue
            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_mime_header(msg.get("Subject"))
            html_body = extract_html_body(msg)
            if not html_body:
                skipped_no_html += 1
                continue

            date_str = msg.get("Date") or ""
            # Infer newsletter name from subject
            newsletter_name = "TLDR"
            if "TLDR AI" in subject or "tldr ai" in subject.lower():
                newsletter_name = "TLDR AI"
            elif "TLDR InfoSec" in subject or "infosec" in subject.lower():
                newsletter_name = "TLDR InfoSec"
            elif "TLDR DevOps" in subject or "devops" in subject.lower():
                newsletter_name = "TLDR DevOps"
            elif "TLDR Web Dev" in subject or "web dev" in subject.lower():
                newsletter_name = "TLDR Web Dev"
            elif "TLDR" in subject:
                newsletter_name = "TLDR Tech"

            if len(sample_subjects) < 5:
                sample_subjects.append(subject[:200])

            results.append({
                "subject": subject,
                "html_body": html_body,
                "date": date_str,
                "newsletter_name": newsletter_name,
            })

        if skipped_no_html:
            logger.info("skipped_no_html=%s", skipped_no_html)
        if sample_subjects:
            logger.info("matched_subjects_sample=%s", sample_subjects)
        logger.info("emails_returned=%s", len(results))
        return results
    finally:
        try:
            mail.logout()
        except Exception:
            pass
