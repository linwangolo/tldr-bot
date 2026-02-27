"""
Gmail IMAP reader: connect, search for TLDR newsletters in the last 24 hours, return raw email content.
"""
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from typing import Any
import boto3


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
    since_days: int = 1,
    from_domain: str = "tldrnewsletter.com",
) -> list[dict[str, Any]]:
    """
    Connect to Gmail via IMAP, search for emails from TLDR in the last `since_days`, return list of
    { "subject", "html_body", "date", "newsletter_name" }.
    """
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        mail.login(gmail_address, app_password)
        mail.select("INBOX")

        # IMAP SINCE date is in format DD-Mon-YYYY; combine criteria in one string
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(FROM "{from_domain}" SINCE {since})')
        if status != "OK" or not messages[0]:
            return []

        id_list = messages[0].split()
        results = []

        for uid in id_list:
            status, data = mail.fetch(uid, "(RFC822)")
            if status != "OK" or not data:
                continue
            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_mime_header(msg.get("Subject"))
            html_body = extract_html_body(msg)
            if not html_body:
                continue

            date_str = msg.get("Date") or ""
            # Infer newsletter name from subject (e.g. "TLDR AI 2026-02-25" -> "TLDR AI")
            newsletter_name = "TLDR"
            if "TLDR AI" in subject or "tldr ai" in subject.lower():
                newsletter_name = "TLDR AI"
            elif "TLDR DevOps" in subject or "devops" in subject.lower():
                newsletter_name = "TLDR DevOps"
            elif "TLDR Web Dev" in subject or "web dev" in subject.lower():
                newsletter_name = "TLDR Web Dev"
            elif "TLDR" in subject:
                # Default to Tech for plain "TLDR" or "TLDR 2026-02-25"
                newsletter_name = "TLDR Tech"

            results.append({
                "subject": subject,
                "html_body": html_body,
                "date": date_str,
                "newsletter_name": newsletter_name,
            })

        return results
    finally:
        try:
            mail.logout()
        except Exception:
            pass
