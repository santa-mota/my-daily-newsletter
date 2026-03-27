"""Handle inbound WhatsApp events (text + reactions)."""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from newsletter.db.models import OutgoingMessage, PreferenceEntry, SavedLink
from newsletter.memory.recall import recent_saved_markdown
from newsletter.preferences.interpreter import classify_message
from newsletter.services.tagging import save_link_from_reaction
from newsletter.whatsapp.client import send_text_message
from newsletter.whatsapp.payload import ReactionEvent, TextMessage

log = logging.getLogger(__name__)


def handle_text_message(db: Session, msg: TextMessage, owner_e164: str) -> None:
    """
    Handle text messages with intelligent intent detection.

    Uses LLM to understand if user wants to:
    - Save a link ("store that RAG article")
    - Retrieve saved links ("show me papers about GPT-5")
    - Set preferences ("tomorrow I want news about AI")
    - General query

    Single-user v0: Only owner can send messages.
    """
    if msg.from_e164.strip() != owner_e164.strip():
        log.info("Ignoring message from non-owner %s", msg.from_e164)
        return

    body = msg.body.strip()

    # Legacy command: list saved
    if body.lower().startswith("list saved"):
        send_text_message(to_e164=owner_e164, body=recent_saved_markdown(db))
        return

    # Use intelligent chat handler to understand intent
    from newsletter.services.chat_handler import handle_chat_message

    try:
        response = handle_chat_message(db, body)

        # If it's a preference message, also store in preferences table
        if "preference" in response.lower() or "next digest" in response.lower():
            classified = classify_message(body)
            db.add(
                PreferenceEntry(
                    raw_text=classified.raw_text,
                    kind=classified.kind,
                    expires_at=classified.expires_at,
                )
            )
            db.commit()

        send_text_message(to_e164=owner_e164, body=response)

    except Exception as e:
        log.exception("Chat handler failed")
        # Fallback to old behavior
        classified = classify_message(body)
        db.add(
            PreferenceEntry(
                raw_text=classified.raw_text,
                kind=classified.kind,
                expires_at=classified.expires_at,
            )
        )
        db.commit()
        send_text_message(
            to_e164=owner_e164,
            body=(
                "Got it — I'll fold that into the next digest generation. "
                f"(stored as {classified.kind})"
            ),
        )


def handle_reaction(db: Session, ev: ReactionEvent, owner_e164: str) -> None:
    """
    Map a reaction to the originating URL via `OutgoingMessage` and save for recall.

    Tags are copied from OutgoingMessage (no LLM call needed).
    Any emoji counts as "interesting" for now; filter to 👍/❤️ later if desired.
    """
    if ev.from_e164.strip() != owner_e164.strip():
        return

    # Use tagging service to save link with pre-computed tags
    saved = save_link_from_reaction(
        db=db,
        whatsapp_wamid=ev.reacted_to_message_id,
        reaction_emoji=ev.emoji,
    )

    if not saved:
        send_text_message(
            to_e164=owner_e164,
            body="I couldn't match that reaction to a recent link message.",
        )
        return

    # Show tags in confirmation message
    tags_str = ", ".join(saved.tags) if saved.tags else "no tags"
    send_text_message(
        to_e164=owner_e164,
        body=f"Saved for later: {saved.title or saved.url}\n🏷️ Tags: {tags_str}",
    )
