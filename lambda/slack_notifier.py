"""
Post TLDR daily briefing to Slack: inline summary text, link to summary JSON, and link to audio MP3.
"""
import urllib.request
import json
from typing import Any


def post_briefing(
    webhook_url: str,
    summary_text: str,
    summary_json_url: str,
    audio_url: str,
    date_str: str,
) -> None:
    """
    Send a rich Slack message with the daily briefing.
    - Inline summary text (in a section block, truncated if needed for Slack limits).
    - Link to full summary JSON (S3 presigned).
    - Link to audio MP3 (S3 presigned) for playback.
    """
    # Slack section block text limit is 3000 chars; keep summary readable
    max_section = 2900
    if len(summary_text) > max_section:
        summary_display = summary_text[:max_section] + "…"
    else:
        summary_display = summary_text

    payload: dict[str, Any] = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"TLDR Daily Briefing — {date_str}", "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary*\n\n{summary_display}"},
            },
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
                        "text": f"*:page_facing_up: Full summary*\n<{summary_json_url}|Download JSON>",
                    },
                ],
            },
        ]
    }

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
