"""
Extract TLDR web version URLs from email HTML, fetch pages, and parse into structured sections
(Headlines & Launches, Deep Dives & Analysis, etc.) for multiple newsletter formats.
"""
import re
import urllib.request
from typing import Any
from bs4 import BeautifulSoup


# Match TLDR web version URLs (various query params)
WEB_VERSION_PATTERN = re.compile(
    r"https://a\.tldrnewsletter\.com/web-version\?[^\s\"'<>]+",
    re.IGNORECASE,
)


def extract_web_link(html: str) -> str | None:
    """Extract the first TLDR web-version URL from email HTML."""
    match = WEB_VERSION_PATTERN.search(html)
    return match.group(0).split("'")[0].split('"')[0].strip() if match else None


def fetch_html(url: str, timeout_seconds: int = 15) -> str:
    """Fetch URL and return response text."""
    req = urllib.request.Request(url, headers={"User-Agent": "TLDR-Bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _text(elem) -> str:
    if elem is None:
        return ""
    return elem.get_text(separator=" ", strip=True)


def _parse_tldr_page(html: str, newsletter_name: str, url: str) -> dict[str, Any]:
    """
    Parse TLDR web version HTML into structured sections.
    TLDR uses h1/h2 for section titles (e.g. "Headlines & Launches", "Deep Dives & Analysis").
    """
    soup = BeautifulSoup(html, "lxml")
    title = _text(soup.find("title")) or soup.find("h1")
    if title and hasattr(title, "get_text"):
        title = title.get_text(separator=" ", strip=True)
    elif not isinstance(title, str):
        title = str(title) if title else ""

    sections: dict[str, list[dict[str, str]]] = {}
    current_section = "Intro"
    sections[current_section] = []

    # Find all headings (h1, h2) and following content
    for tag in soup.find_all(["h1", "h2", "h3", "p", "a"]):
        name = tag.name
        text = _text(tag)

        if name in ("h1", "h2", "h3") and text:
            # Start new section (skip generic "TLDR" or "Together With")
            if "TLDR" in text and len(text) < 25:
                current_section = "Intro"
            elif "Together With" in text or "Sign Up" in text:
                continue
            else:
                current_section = text
                if current_section not in sections:
                    sections[current_section] = []
            continue

        if name == "a" and text and current_section:
            href = tag.get("href") or ""
            if href.startswith("http") and "tldr" not in href.lower().split("/")[2]:
                item = {"title": text[:500], "url": href}
                # Optional: get next sibling for description
                next_el = tag.find_next_sibling()
                if next_el and next_el.name == "p":
                    item["description"] = _text(next_el)[:1000]
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(item)

    # Also collect paragraph text for sections that don't rely only on links
    flat_items = []
    for section_name, items in sections.items():
        for it in items:
            flat_items.append({"section": section_name, **it})

    # Build plain text content for LLM (truncate to stay within context)
    content_parts = [f"# {title}\n\n"]
    for section_name, items in sections.items():
        if not items and section_name == "Intro":
            continue
        content_parts.append(f"## {section_name}\n\n")
        for it in items:
            content_parts.append(f"- {it.get('title', '')}")
            if it.get("description"):
                content_parts.append(f"  {it['description']}")
        content_parts.append("\n")

    full_text = "".join(content_parts)
    if len(full_text) > 15000:
        full_text = full_text[:15000] + "\n\n[Content truncated...]"

    return {
        "url": url,
        "newsletter_name": newsletter_name,
        "title": title,
        "sections": sections,
        "content": full_text,
        "items": flat_items,
    }


def crawl_issue(url: str, newsletter_name: str = "TLDR") -> dict[str, Any]:
    """Fetch TLDR web version URL and return structured issue data."""
    html = fetch_html(url)
    return _parse_tldr_page(html, newsletter_name, url)


def parse_emails_to_issues(
    emails: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For each email (with html_body, newsletter_name), extract web link, fetch and parse.
    Returns list of issue dicts (content, title, url, newsletter_name, sections, items).
    """
    issues = []
    seen_urls: set[str] = set()
    for em in emails:
        link = extract_web_link(em.get("html_body") or "")
        if not link or link in seen_urls:
            continue
        seen_urls.add(link)
        try:
            issue = crawl_issue(link, em.get("newsletter_name") or "TLDR")
            issues.append(issue)
        except Exception:
            continue
    return issues
