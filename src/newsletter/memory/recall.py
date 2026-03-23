"""Retrieve saved items for WhatsApp replies or LLM-augmented Q&A."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.db.models import SavedLink


def recent_saved_markdown(db: Session, *, limit: int = 15) -> str:
    """Return a short markdown list of recently saved URLs (for chat replies)."""
    q = select(SavedLink).order_by(SavedLink.created_at.desc()).limit(limit)
    rows = db.scalars(q).all()
    if not rows:
        return "No saved links yet — react with an emoji on a link message to save it."
    lines = []
    for r in rows:
        title = r.title or r.url
        lines.append(f"- {title}\n  {r.url}")
    return "\n".join(lines)
