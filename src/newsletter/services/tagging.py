"""
Cost-efficient tagging and retrieval service for saved links.

Strategy to minimize LLM costs:
1. Tags are generated ONCE during digest creation (batch, not per save)
2. When user reacts to WhatsApp message, tags are copied from OutgoingMessage
3. Retrieval uses simple keyword matching (no LLM needed for 100-200 items)
4. LLM only called for complex natural language queries
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.db.models import OutgoingMessage, SavedLink

log = logging.getLogger(__name__)


def extract_tags_from_digest_item(item: dict[str, Any]) -> tuple[list[str], str]:
    """
    Extract tags and summary from digest item.

    This is called during digest generation, NOT on save.
    The agent already generates tags as part of DigestItem schema.

    Args:
        item: DigestItem dict with 'tags', 'title', 'why_it_matters_one_line'

    Returns:
        (tags, context_summary) tuple
    """
    tags = item.get("tags", [])

    # Context summary is the "why it matters" one-liner from the digest
    context_summary = item.get("why_it_matters_one_line", item.get("title", ""))

    return tags, context_summary


def save_link_from_reaction(
    db: Session,
    whatsapp_wamid: str,
    reaction_emoji: str,
) -> SavedLink | None:
    """
    Save a link when user reacts to WhatsApp message.

    Tags are copied from OutgoingMessage (no LLM call needed).

    Args:
        db: Database session
        whatsapp_wamid: WhatsApp message ID that was reacted to
        reaction_emoji: Emoji used (e.g., "👍", "❤️")

    Returns:
        SavedLink instance or None if message not found
    """
    # Look up the outgoing message
    msg = db.get(OutgoingMessage, whatsapp_wamid)
    if not msg:
        log.warning(f"Outgoing message {whatsapp_wamid} not found for reaction")
        return None

    # Check if already saved
    existing = db.scalars(
        select(SavedLink).where(SavedLink.whatsapp_wamid == whatsapp_wamid)
    ).first()

    if existing:
        log.info(f"Link already saved: {existing.url}")
        return existing

    # Create saved link with pre-computed tags (no LLM call)
    saved = SavedLink(
        url=msg.url,
        title=msg.title,
        whatsapp_wamid=whatsapp_wamid,
        reaction_emoji=reaction_emoji,
        tags=msg.tags,  # Copy from OutgoingMessage
        context_summary=msg.context_summary,  # Copy from OutgoingMessage
    )

    db.add(saved)
    db.commit()

    log.info(f"Saved link via reaction: {saved.url} (tags: {saved.tags})")
    return saved


def save_link_from_api(
    db: Session,
    url: str,
    title: str | None = None,
    tags: list[str] | None = None,
    context_summary: str | None = None,
) -> SavedLink:
    """
    Save a link via API endpoint.

    If tags are not provided, the link is saved without tags.
    For cost efficiency, consider having the frontend/user provide tags
    or extract them from the original digest.

    Args:
        db: Database session
        url: URL to save
        title: Optional title
        tags: Optional pre-computed tags
        context_summary: Optional summary

    Returns:
        SavedLink instance
    """
    # Check if already saved
    existing = db.scalars(
        select(SavedLink).where(SavedLink.url == url)
    ).first()

    if existing:
        log.info(f"Link already saved: {url}")
        return existing

    saved = SavedLink(
        url=url,
        title=title,
        tags=tags or [],
        context_summary=context_summary,
    )

    db.add(saved)
    db.commit()

    log.info(f"Saved link via API: {url} (tags: {tags})")
    return saved


def search_saved_links_by_tags(
    db: Session,
    query_tags: list[str],
    limit: int = 20,
) -> list[SavedLink]:
    """
    Search saved links by tags (simple keyword matching, no LLM).

    This is efficient for 100-200 items and doesn't cost tokens.

    Args:
        db: Database session
        query_tags: List of tags to search for (e.g., ["RAG", "GPT-5"])
        limit: Max results

    Returns:
        List of matching SavedLink instances, sorted by created_at desc
    """
    # SQLite JSON operations are limited, so we load all and filter in Python
    # For 100-200 items this is fine
    all_saved = db.scalars(
        select(SavedLink).order_by(SavedLink.created_at.desc())
    ).all()

    # Normalize query tags to lowercase for case-insensitive matching
    query_tags_lower = [tag.lower() for tag in query_tags]

    matches = []
    for link in all_saved:
        if not link.tags:
            continue

        # Check if any query tag matches any link tag (case-insensitive)
        link_tags_lower = [tag.lower() for tag in link.tags]
        if any(qtag in link_tags_lower for qtag in query_tags_lower):
            matches.append(link)
            if len(matches) >= limit:
                break

    return matches


def search_saved_links_by_text(
    db: Session,
    query_text: str,
    limit: int = 20,
) -> list[SavedLink]:
    """
    Search saved links by text (title, tags, context_summary).

    Simple keyword matching, no LLM needed.

    Args:
        db: Database session
        query_text: Search text (e.g., "RAG paper", "GPT-5 inference")
        limit: Max results

    Returns:
        List of matching SavedLink instances
    """
    # Load all saved links
    all_saved = db.scalars(
        select(SavedLink).order_by(SavedLink.created_at.desc())
    ).all()

    # Normalize query to lowercase
    query_lower = query_text.lower()

    matches = []
    for link in all_saved:
        # Check title
        if link.title and query_lower in link.title.lower():
            matches.append(link)
            continue

        # Check context summary
        if link.context_summary and query_lower in link.context_summary.lower():
            matches.append(link)
            continue

        # Check tags
        if link.tags:
            tags_str = " ".join(link.tags).lower()
            if query_lower in tags_str:
                matches.append(link)
                continue

        if len(matches) >= limit:
            break

    return matches


def search_saved_links_by_date(
    db: Session,
    days_back: int = 7,
    limit: int = 20,
) -> list[SavedLink]:
    """
    Get saved links from recent days.

    Args:
        db: Database session
        days_back: Number of days to look back
        limit: Max results

    Returns:
        List of SavedLink instances
    """
    from datetime import UTC, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days_back)

    results = db.scalars(
        select(SavedLink)
        .where(SavedLink.created_at >= cutoff)
        .order_by(SavedLink.created_at.desc())
        .limit(limit)
    ).all()

    return list(results)


def format_saved_links_for_display(links: list[SavedLink]) -> str:
    """
    Format saved links for display in chat or API response.

    Args:
        links: List of SavedLink instances

    Returns:
        Markdown-formatted string
    """
    if not links:
        return "No saved links found."

    lines = [f"Found {len(links)} saved link(s):\n"]

    for i, link in enumerate(links, 1):
        tags_str = ", ".join(link.tags) if link.tags else "no tags"
        date_str = link.created_at.strftime("%Y-%m-%d")

        lines.append(f"{i}. **{link.title or 'Untitled'}**")
        lines.append(f"   {link.url}")
        lines.append(f"   📅 {date_str} | 🏷️ {tags_str}")

        if link.context_summary:
            lines.append(f"   💡 {link.context_summary}")

        if link.reaction_emoji:
            lines.append(f"   {link.reaction_emoji}")

        lines.append("")

    return "\n".join(lines)
