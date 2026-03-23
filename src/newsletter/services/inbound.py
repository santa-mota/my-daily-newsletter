"""Handle inbound WhatsApp events (text + reactions)."""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from newsletter.db.models import OutgoingMessage, PreferenceEntry, SavedLink
from newsletter.memory.recall import recent_saved_markdown
from newsletter.preferences.interpreter import classify_message
from newsletter.whatsapp.client import send_text_message
from newsletter.whatsapp.payload import ReactionEvent, TextMessage

log = logging.getLogger(__name__)


def handle_text_message(db: Session, msg: TextMessage, owner_e164: str) -> None:
    """Persist preference text and acknowledge (single-user v0)."""
    if msg.from_e164.strip() != owner_e164.strip():
        log.info("Ignoring message from non-owner %s", msg.from_e164)
        return

    body = msg.body.strip()
    if body.lower().startswith("list saved"):
        send_text_message(to_e164=owner_e164, body=recent_saved_markdown(db))
        return

    classified = classify_message(msg.body)
    db.add(
        PreferenceEntry(
            raw_text=classified.raw_text,
            kind=classified.kind,
            expires_at=classified.expires_at,
        )
    )
    send_text_message(
        to_e164=owner_e164,
        body=(
            "Got it — I’ll fold that into the next digest generation. "
            f"(stored as {classified.kind})"
        ),
    )


def handle_reaction(db: Session, ev: ReactionEvent, owner_e164: str) -> None:
    """
    Map a reaction to the originating URL via `OutgoingMessage` and save for recall.

    Any emoji counts as “interesting” for now; filter to 👍/❤️ later if desired.
    """
    if ev.from_e164.strip() != owner_e164.strip():
        return

    row = db.get(OutgoingMessage, ev.reacted_to_message_id)
    if not row:
        send_text_message(
            to_e164=owner_e164,
            body="I couldn’t match that reaction to a recent link message.",
        )
        return

    db.add(
        SavedLink(
            url=row.url,
            title=row.title,
            whatsapp_wamid=ev.reacted_to_message_id,
            reaction_emoji=ev.emoji,
        )
    )
    send_text_message(
        to_e164=owner_e164,
        body=f"Saved for later: {row.title or row.url}",
    )
