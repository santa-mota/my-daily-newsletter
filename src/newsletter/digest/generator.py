"""
Build the daily digest by combining the system prompt file + user context + LLM.

Replace `generate_digest` internals with your preferred model stack; the public
contract is `DigestResult`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.models import PreferenceEntry
from newsletter.schemas.digest import DigestResult

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
    """
    system = _load_system_prompt()
    prefs = _preferences_block(db)
    schema = json.dumps(DigestResult.model_json_schema(), indent=2)
    user = f"""## Personalization context (most recent first)
{prefs}

## Output schema (JSON only — match these keys)
{schema}

## Today's task
Generate today's digest JSON. If personalization conflicts are severe, set
`clarification_question` to a single concise question and still provide a best-effort digest.
"""
    if not get_settings().openai_api_key:
        log.warning("OPENAI_API_KEY missing — returning mock digest.")
        return _mock_digest()
    try:
        raw = _call_openai(system=system, user=user)
        return DigestResult.model_validate(raw)
    except Exception:
        log.exception("LLM call failed; falling back to mock digest.")
        return _mock_digest()
