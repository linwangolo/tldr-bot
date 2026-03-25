"""
Summarize parsed TLDR newsletter content using Bedrock Claude 3.5 Haiku.
Produces a conversational 2-3 minute spoken briefing.
"""
import json
import logging
import os
import boto3
from typing import Any

logger = logging.getLogger(__name__)

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
FALLBACK_BEDROCK_MODEL_ID = os.environ.get("FALLBACK_BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
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


def _fallback_summary(issues: list[dict[str, Any]]) -> str:
    parts = ["Here's your TLDR fallback briefing for today."]
    for issue in issues[:6]:
        name = issue.get("newsletter_name") or "TLDR"
        title = issue.get("title") or "Untitled issue"
        parts.append(f"{name}: {title}.")

        items = issue.get("items") or []
        if items:
            top_titles = []
            for item in items[:3]:
                item_title = (item.get("title") or "").strip()
                if item_title:
                    top_titles.append(item_title)
            if top_titles:
                parts.append("Highlights include " + "; ".join(top_titles) + ".")

    parts.append("This version was generated without Bedrock because the model call was unavailable.")
    parts.append("That's your TLDR for today.")
    return " ".join(parts)


def _invoke_anthropic(client, prompt: str, model_id: str) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()


def _invoke_amazon_nova(client, prompt: str, model_id: str) -> str:
    body = {
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        "inferenceConfig": {
            "max_new_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        },
    }
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"].strip()


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
    try:
        return _invoke_anthropic(client, full_prompt, BEDROCK_MODEL_ID)
    except Exception as e:
        logger.warning("bedrock_summary_failed model_id=%s error=%s", BEDROCK_MODEL_ID, str(e))
    try:
        logger.info("bedrock_summary_fallback_start model_id=%s", FALLBACK_BEDROCK_MODEL_ID)
        return _invoke_amazon_nova(client, full_prompt, FALLBACK_BEDROCK_MODEL_ID)
    except Exception as e:
        logger.warning("bedrock_summary_fallback_failed model_id=%s error=%s", FALLBACK_BEDROCK_MODEL_ID, str(e))
        return _fallback_summary(issues)
