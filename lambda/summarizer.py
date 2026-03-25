"""
Summarize parsed TLDR newsletter content using Bedrock.
Uses Claude 3 Haiku first and falls back to Meta Llama 70B.
"""
import json
import logging
import os
import re
import boto3
from typing import Any

logger = logging.getLogger(__name__)

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
BULLET_BEDROCK_MODEL_ID = os.environ.get("BULLET_BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
FALLBACK_BEDROCK_MODEL_ID = os.environ.get("FALLBACK_BEDROCK_MODEL_ID", "openai.gpt-oss-120b-1:0")
SUMMARY_MAX_TOKENS = int(os.environ.get("SUMMARY_MAX_TOKENS", "6000"))
BULLET_MAX_TOKENS = 1024
TEMPERATURE = 0.3
OPENAI_CONTINUATION_PASSES = int(os.environ.get("OPENAI_CONTINUATION_PASSES", "1"))
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))
LLAMA_MAX_TOKENS = int(os.environ.get("LLAMA_MAX_TOKENS", "2048"))
OPENAI_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "6000"))


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


def _fallback_bullet_summary(issues: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for issue in issues[:5]:
        name = issue.get("newsletter_name") or "TLDR"
        items = issue.get("items") or []
        refs = []
        seen_urls: set[str] = set()
        for item in items:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            refs.append(f"<{url}|{title[:100]}>")
            if len(refs) == 2:
                break
        if refs:
            lines.append(f"• *{name}*: " + " ; ".join(refs))
    return "\n".join(lines)


def _invoke_model_with_fallback(
    client,
    prompt: str,
    primary_model_id: str,
    fallback_model_id: str,
    primary_max_tokens: int,
    fallback_max_tokens: int | None = None,
    openai_continuation_passes: int | None = None,
    log_prefix: str = "bedrock_generation",
) -> str:
    try:
        return _invoke_bedrock_model(
            client,
            prompt,
            primary_model_id,
            primary_max_tokens,
            openai_continuation_passes=openai_continuation_passes,
        )
    except Exception as e:
        logger.warning("%s_failed model_id=%s error=%s", log_prefix, primary_model_id, str(e))
    if not fallback_model_id:
        raise
    try:
        logger.info("%s_fallback_start model_id=%s", log_prefix, fallback_model_id)
        return _invoke_bedrock_model(
            client,
            prompt,
            fallback_model_id,
            fallback_max_tokens or primary_max_tokens,
            openai_continuation_passes=openai_continuation_passes,
        )
    except Exception as e:
        logger.warning("%s_fallback_failed model_id=%s error=%s", log_prefix, fallback_model_id, str(e))
        raise


def _invoke_anthropic(client, prompt: str, model_id: str, max_tokens: int) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": min(max_tokens, ANTHROPIC_MAX_TOKENS),
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


def _invoke_meta_llama(client, prompt: str, model_id: str, max_tokens: int) -> str:
    body = {
        "prompt": f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n",
        "max_gen_len": min(max_tokens, LLAMA_MAX_TOKENS),
        "temperature": TEMPERATURE,
    }
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
    )
    result = json.loads(response["body"].read())
    return result["generation"].strip()


def _invoke_openai_oss(
    client,
    prompt: str,
    model_id: str,
    max_tokens: int,
    continuation_passes: int | None = None,
) -> str:
    token_budget = min(max_tokens, OPENAI_MAX_TOKENS)
    allowed_continuations = OPENAI_CONTINUATION_PASSES if continuation_passes is None else continuation_passes
    messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    combined_parts: list[str] = []

    for pass_idx in range(allowed_continuations + 1):
        body = {
            "messages": messages,
            "max_completion_tokens": token_budget,
            "temperature": TEMPERATURE,
            "stream": False,
        }
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"OpenAI response missing choices for model_id={model_id}")

        choice0 = choices[0]
        message = choice0.get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if text:
                        parts.append(text)
            content = "\n".join(parts)
        elif not isinstance(content, str):
            content = str(content)

        # Bedrock OpenAI responses can prefix reasoning in XML-like tags.
        cleaned = re.sub(r"(?s)^<reasoning>.*?</reasoning>\s*", "", content).strip()
        text_part = cleaned or content.strip()
        if text_part:
            combined_parts.append(text_part)

        finish_reason = (choice0.get("finish_reason") or "").lower()
        if finish_reason not in {"length", "max_tokens"}:
            break
        if pass_idx >= allowed_continuations:
            logger.warning("openai_summary_continuation_exhausted model_id=%s", model_id)
            break

        logger.info("openai_summary_continuation pass=%s model_id=%s", pass_idx + 1, model_id)
        partial = "\n\n".join(combined_parts).strip()
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": partial},
            {
                "role": "user",
                "content": (
                    "Continue exactly where you stopped. Do not repeat prior text. "
                    "Finish the remaining script and include a brief sign-off."
                ),
            },
        ]

    return "\n\n".join(combined_parts).strip()


def _invoke_bedrock_model(
    client,
    prompt: str,
    model_id: str,
    max_tokens: int,
    openai_continuation_passes: int | None = None,
) -> str:
    if model_id.startswith("anthropic."):
        return _invoke_anthropic(client, prompt, model_id, max_tokens)
    if model_id.startswith("meta.llama"):
        return _invoke_meta_llama(client, prompt, model_id, max_tokens)
    if model_id.startswith("openai."):
        return _invoke_openai_oss(
            client,
            prompt,
            model_id,
            max_tokens,
            continuation_passes=openai_continuation_passes,
        )
    raise ValueError(f"Unsupported model family for model_id={model_id}")


def _build_bullet_candidates(issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for issue in issues:
        for item in (issue.get("items") or [])[:4]:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append({"title": title[:120], "url": url})
            if len(candidates) >= 18:
                return candidates
    return candidates


def _normalize_bullet_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("• "):
            lines.append(line)
            continue
        if line.startswith("- ") or line.startswith("* "):
            lines.append("• " + line[2:].strip())
            continue
        if re.match(r"^\d+[.)]\s+", line):
            normalized = re.sub(r"^\d+[.)]\s+", "", line).strip()
            lines.append("• " + normalized)
    return lines


def _line_has_slack_link(line: str) -> bool:
    return bool(re.search(r"<https?://[^>|]+(?:\|[^>]+)?>", line))


def _ensure_links_per_bullet(lines: list[str], candidates: list[dict[str, str]]) -> list[str]:
    if not lines:
        return lines

    out: list[str] = []
    candidate_idx = 0
    for line in lines:
        if _line_has_slack_link(line):
            out.append(line)
            continue

        if candidate_idx < len(candidates):
            c = candidates[candidate_idx]
            candidate_idx += 1
            out.append(f"{line} <{c['url']}|{c['title']}>")
        else:
            out.append(line)
    return out


def generate_bullet_summary(full_summary: str, issues: list[dict[str, Any]], region: str | None = None) -> str:
    if not issues:
        return "• No newsletter items available."

    candidates = _build_bullet_candidates(issues)
    if not candidates:
        return _fallback_bullet_summary(issues)

    candidate_text = "\n".join(
        f"{idx}. <{candidate['url']}|{candidate['title']}>" for idx, candidate in enumerate(candidates, 1)
    )
    prompt = f"""You are writing a Slack summary for a tech briefing.

Use the long-form summary below to produce 4 to 6 concise Slack bullet points.
Each bullet should be one short sentence followed by 1 or 2 relevant inline source links from the candidate source list.
Write bullets directly in Slack mrkdwn format.

Rules:
1. Return ONLY the bullet list.
2. Every line must start with "• ".
3. Do not output JSON.
4. Do not add a title or introduction.
5. Use only candidate links listed below. Do not invent links.
6. Keep each bullet under 220 characters before links when possible.

Long-form summary:
{full_summary}

Candidate sources:
{candidate_text}
"""

    client = boto3.client("bedrock-runtime", region_name=region or "us-east-1")
    try:
        raw = _invoke_model_with_fallback(
            client,
            prompt,
            BULLET_BEDROCK_MODEL_ID,
            FALLBACK_BEDROCK_MODEL_ID,
            BULLET_MAX_TOKENS,
            BULLET_MAX_TOKENS,
            openai_continuation_passes=0,
            log_prefix="bedrock_bullet_summary",
        )
        lines = _normalize_bullet_lines(raw)

        if len(lines) >= 4:
            lines = _ensure_links_per_bullet(lines[:6], candidates)
            return "\n".join(lines[:6])
        logger.warning("bullet_summary_too_short_or_malformed line_count=%s raw_len=%s", len(lines), len(raw))

        retry_prompt = f"""Rewrite the briefing into exactly 5 Slack bullet points.
Return ONLY 5 lines.
Each line MUST start with "• ".
Each line MUST include exactly one inline source link from the list below.
Do not add any intro or footer text.
Do not output JSON.

Long-form summary:
{full_summary}

Allowed links:
{candidate_text}
"""
        retry_raw = _invoke_model_with_fallback(
            client,
            retry_prompt,
            BULLET_BEDROCK_MODEL_ID,
            FALLBACK_BEDROCK_MODEL_ID,
            BULLET_MAX_TOKENS,
            BULLET_MAX_TOKENS,
            openai_continuation_passes=0,
            log_prefix="bedrock_bullet_summary_retry",
        )
        retry_lines = _normalize_bullet_lines(retry_raw)
        if len(retry_lines) >= 4:
            retry_lines = _ensure_links_per_bullet(retry_lines[:6], candidates)
            return "\n".join(retry_lines[:6])
        logger.warning(
            "bullet_summary_retry_too_short_or_malformed line_count=%s raw_len=%s",
            len(retry_lines),
            len(retry_raw),
        )
    except Exception as e:
        logger.warning("bullet_summary_generation_failed error=%s", str(e))

    return _fallback_bullet_summary(issues)


def summarize(issues: list[dict[str, Any]], region: str | None = None) -> str:
    """
    Call Bedrock to produce a spoken briefing from parsed TLDR content.
    Returns the summary text for TTS and storage.
    """
    if not issues:
        return "No TLDR newsletters to summarize today."

    combined = _build_combined_content(issues)
    prompt = """You are a tech news anchor. Below is content from one or more TLDR newsletters (tech/AI/dev news). Create a single, conversational 10-15 minute spoken briefing that:

1. Opens with a one-line hook (e.g. "Here's your TLDR for today.")
2. Groups highlights by theme where it makes sense (e.g. AI updates, industry moves, research).
3. Mentions the most important headlines and few-sentence takeaways -— no need to list every link.
4. Uses natural spoken language: short sentences, minimal jargon, as if you're talking to a colleague.
5. Ends with a brief sign-off.

Write only the script. No bullet points or markdown in the output—plain paragraphs for reading aloud.
Target 1000–1500 words and do not produce fewer than 1000 words unless the source material is too limited to support it.

Content:
"""
    full_prompt = prompt + combined

    client = boto3.client("bedrock-runtime", region_name=region or "us-east-1")
    try:
        summary_text = _invoke_model_with_fallback(
            client,
            full_prompt,
            BEDROCK_MODEL_ID,
            FALLBACK_BEDROCK_MODEL_ID,
            SUMMARY_MAX_TOKENS,
            SUMMARY_MAX_TOKENS,
            log_prefix="bedrock_summary",
        )
        return summary_text
    except Exception:
        return _fallback_summary(issues)
