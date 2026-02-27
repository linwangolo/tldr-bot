"""
Summarize parsed TLDR newsletter content using Bedrock Claude 3.5 Haiku.
Produces a conversational 2-3 minute spoken briefing.
"""
import json
import boto3
from typing import Any

BEDROCK_MODEL_ID = "anthropic.claude-3-5-haiku-20241022-v1:0"
MAX_TOKENS = 2048
TEMPERATURE = 0.3


def _build_combined_content(issues: list[dict[str, Any]]) -> str:
    """Combine multiple newsletter issues into one text for summarization."""
    parts = []
    for i, issue in enumerate(issues, 1):
        name = issue.get("newsletter_name") or "TLDR"
        title = issue.get("title") or ""
        content = issue.get("content") or ""
        parts.append(f"--- Newsletter {i}: {name} ---\n{title}\n\n{content}\n")
    return "\n".join(parts)


def summarize(issues: list[dict[str, Any]], region: str | None = None) -> str:
    """
    Call Bedrock Claude 3.5 Haiku to produce a concise spoken briefing from parsed TLDR content.
    Returns the summary text (for TTS and for storing in S3 / Slack).
    """
    if not issues:
        return "No TLDR newsletters to summarize today."

    combined = _build_combined_content(issues)
    prompt = """You are a tech news anchor. Below is content from one or more TLDR newsletters (tech/AI/dev news). Create a single, conversational 2-3 minute spoken briefing that:

1. Opens with a one-line hook (e.g. "Here's your TLDR for today.")
2. Groups highlights by theme where it makes sense (e.g. AI updates, industry moves, research).
3. Mentions the most important headlines and one-sentence takeaways—no need to list every link.
4. Uses natural spoken language: short sentences, minimal jargon, as if you're talking to a colleague.
5. Ends with a brief sign-off.

Write only the script. No bullet points or markdown in the output—plain paragraphs for reading aloud.
Keep total length to about 300–450 words.

Content:
"""
    full_prompt = prompt + combined

    client = boto3.client("bedrock-runtime", region_name=region or "us-east-1")
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [{"role": "user", "content": full_prompt}],
    }
    response = client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    return text.strip()
