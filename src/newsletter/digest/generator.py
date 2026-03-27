"""
Build the daily digest by combining the system prompt file + user context + LLM.

Replace `generate_digest` internals with your preferred model stack; the public
contract is `DigestResult`.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.models import PreferenceEntry
from newsletter.schemas.digest import DigestResult
from newsletter.sources.aggregator import NewsAggregator, NewsItem

log = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    # Packaged alongside the `newsletter` package so editable and wheel installs resolve reliably.
    path = Path(__file__).resolve().parents[1] / "prompt_data" / "daily_digest_system.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt file at {path}")
    return path.read_text(encoding="utf-8")


def _preferences_block(db: Session) -> str:
    """Pull recent preference rows into a compact block for the user message."""
    q = (
        select(PreferenceEntry)
        .order_by(PreferenceEntry.created_at.desc())
        .limit(25)
    )
    rows = db.scalars(q).all()
    if not rows:
        return "(no personalization yet — use defaults from the system prompt)"
    lines: list[str] = []
    for r in rows:
        exp = f" expires={r.expires_at.isoformat()}" if r.expires_at else ""
        lines.append(f"- [{r.kind}]{exp}: {r.raw_text}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _cached_fresh_sources(cache_key: str) -> dict[str, list[NewsItem]]:
    """
    Fetch and cache fresh sources for 6 hours.

    Cache key is based on 6-hour windows (e.g., "2026-03-26_0" for 00:00-06:00).
    This avoids hammering APIs on every digest generation.
    """
    log.info(f"Fetching fresh sources (cache_key={cache_key})...")
    aggregator = NewsAggregator()
    try:
        sources = aggregator.fetch_today()
        log.info(
            f"Fetched {len(sources['news'])} news, "
            f"{len(sources['research'])} research, "
            f"{len(sources['discussions'])} discussions"
        )
        return sources
    finally:
        aggregator.close()


def _get_fresh_sources() -> dict[str, list[NewsItem]]:
    """Get fresh sources with 6-hour caching."""
    now = datetime.now(UTC)
    # Cache key changes every 6 hours: "2026-03-26_0", "2026-03-26_1", etc.
    cache_key = f"{now.date()}_{now.hour // 6}"
    return _cached_fresh_sources(cache_key)


def _format_sources_for_llm(sources: dict[str, list[NewsItem]]) -> str:
    """
    Convert NewsItem objects to LLM-friendly markdown.

    The LLM will select the most relevant items based on user preferences
    and the two-section structure (news vs research).
    """
    lines = []

    # Section 1: News & Announcements
    if sources["news"]:
        lines.append("### News & Announcements (AI blogs, product launches)")
        for item in sources["news"][:15]:  # Limit to 15 per section
            lines.append(f"\n**{item.title}**")
            lines.append(f"- URL: {item.url}")
            lines.append(f"- Source: {item.source}")
            if item.summary:
                lines.append(f"- Summary: {item.summary[:200]}...")
            if item.published:
                lines.append(f"- Published: {item.published.strftime('%Y-%m-%d')}")

    # Section 2: Research Papers
    if sources["research"]:
        lines.append("\n\n### Research Papers (arXiv, Hugging Face)")
        for item in sources["research"][:15]:
            lines.append(f"\n**{item.title}**")
            lines.append(f"- URL: {item.url}")
            lines.append(f"- Source: {item.source}")
            if item.authors:
                lines.append(f"- Authors: {', '.join(item.authors[:3])}")
            if item.summary:
                lines.append(f"- Summary: {item.summary[:250]}...")
            if item.published:
                lines.append(f"- Published: {item.published.strftime('%Y-%m-%d')}")

    # Section 3: Discussions & Community
    if sources["discussions"]:
        lines.append("\n\n### Discussions & Community (HN, Reddit)")
        for item in sources["discussions"][:10]:
            lines.append(f"\n**{item.title}**")
            lines.append(f"- URL: {item.url}")
            lines.append(f"- Source: {item.source}")
            if item.score:
                lines.append(f"- Score: {item.score} points")
            lines.append(f"- {item.summary}")

    return "\n".join(lines)


def _call_openai(*, system: str, user: str) -> dict[str, Any]:
    s = get_settings()
    url = f"{s.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {s.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": s.openai_model,
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    with httpx.Client(timeout=120) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def _mock_digest() -> DigestResult:
    """Deterministic placeholder so you can run the pipeline without API keys."""
    return DigestResult.model_validate(
        {
            "intro_markdown": (
                "Here is a **mock digest** (set `OPENAI_API_KEY` for real content). "
                "Section A is news-shaped; Section B nudges toward systems and research."
            ),
            "sections": [
                {
                    "title": "Pulse & headlines (mock)",
                    "summary_bullets": ["Mock item — replace with live model output."],
                    "items": [
                        {
                            "title": "OpenAI newsroom (example)",
                            "url": "https://openai.com/news",
                            "why_it_matters_one_line": (
                                "Official channel for model and product announcements."
                            ),
                            "estimated_read_minutes": 5,
                            "tags": ["news"],
                        }
                    ],
                },
                {
                    "title": "Ideas, research, and interview depth (mock)",
                    "summary_bullets": ["Mock item — RAG / inference angle."],
                    "items": [
                        {
                            "title": "arXiv cs.AI recent (example)",
                            "url": "https://arxiv.org/list/cs.AI/recent",
                            "why_it_matters_one_line": (
                                "Primary research feed — pick 1–2 papers after scanning titles."
                            ),
                            "estimated_read_minutes": 10,
                            "tags": ["research", "RAG"],
                        }
                    ],
                },
            ],
            "clarification_question": None,
        }
    )


def generate_digest(db: Session) -> DigestResult:
    """
    Produce a `DigestResult`. Uses OpenAI-compatible Chat Completions when
    `OPENAI_API_KEY` is set; otherwise returns a mock digest for local testing.

    Now fetches REAL-TIME news/research from multiple APIs and passes them to the LLM
    for intelligent selection and curation based on user preferences.
    """
    system = _load_system_prompt()
    prefs = _preferences_block(db)

    # STEP 1: Fetch fresh sources from APIs (cached for 6 hours)
    try:
        sources = _get_fresh_sources()
        sources_text = _format_sources_for_llm(sources)
        log.info(
            f"Digest generation: using {len(sources['news'])} news, "
            f"{len(sources['research'])} research, {len(sources['discussions'])} discussions"
        )
    except Exception:
        log.exception("Failed to fetch fresh sources; LLM will use fallback knowledge.")
        sources_text = (
            "**Note**: Fresh source fetching failed. Please generate digest from "
            "your knowledge base, focusing on evergreen AI/ML resources and recent trends."
        )

    # STEP 2: Build user prompt with fresh sources + preferences + schema
    schema = json.dumps(DigestResult.model_json_schema(), indent=2)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    user = f"""## Fresh sources for today ({today})

{sources_text}

## Personalization context (most recent first)
{prefs}

## Output schema (JSON only — match these keys)
{schema}

## Today's task

Using the **fresh sources above**, generate today's digest JSON. Follow these guidelines:

1. **Select the MOST relevant items** (NOT all of them) based on:
   - User personalization preferences (tomorrow_override, multi_day preferences)
   - Two-section structure: "Pulse & headlines" (news) + "Ideas, research, interview depth" (papers)
   - 15-30 minute total reading time (aim for 5-8 links total)

2. **Prioritize**:
   - Recent items (last 3-7 days)
   - High-quality sources (arXiv, official blogs, high-score HN/Reddit)
   - Diverse topics (don't duplicate similar content)

3. **If personalization conflicts are severe**, set `clarification_question` to a single
   concise question and still provide a best-effort digest.

4. **Include estimated_read_minutes** for each item (be realistic: papers=10-15min, news=3-5min).

Generate the digest now.
"""

    # STEP 3: Call LLM or return mock
    if not get_settings().openai_api_key:
        log.warning("OPENAI_API_KEY missing — returning mock digest.")
        return _mock_digest()

    try:
        raw = _call_openai(system=system, user=user)
        return DigestResult.model_validate(raw)
    except Exception:
        log.exception("LLM call failed; falling back to mock digest.")
        return _mock_digest()
