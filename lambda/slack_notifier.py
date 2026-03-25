"""
Post TLDR daily briefing to Slack: inline summary text, link to summary JSON, and link to audio MP3.
"""
import urllib.request
import json
from typing import Any


SECTION_LIMIT = 2900


def _chunk_text_blocks(text: str) -> list[dict[str, Any]]:
    if not text:
        return []

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current_lines and current_len + line_len > SECTION_LIMIT:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_len = 0
        current_lines.append(line)
        current_len += line_len

    if current_lines:
        chunks.append("\n".join(current_lines))

    return [{"type": "section", "text": {"type": "mrkdwn", "text": chunk}} for chunk in chunks]


def post_briefing(
    webhook_url: str,
    bullet_summary_text: str,
    full_summary_url: str,
    audio_url: str,
    date_str: str,
) -> None:
    """
    Send a rich Slack message with the daily briefing.
    - Inline bullet summary text with source links.
    - Link to full summary text file (S3 presigned).
    - Link to audio MP3 (S3 presigned) for playback.
    """
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"TLDR Daily Briefing — {date_str}", "emoji": True},
        },
        *_chunk_text_blocks(f"*Summary*\n\n{bullet_summary_text}"),
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*:headphones: Listen*\n<{audio_url}|Play audio (MP3)>",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*:page_facing_up: Full summary*\n<{full_summary_url}|Read full summary text>",
                },
            ],
        },
    ]

    payload: dict[str, Any] = {"blocks": blocks}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"Slack webhook returned {resp.status}: {resp.read()!r}")
