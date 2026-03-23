"""
Parse WhatsApp webhook JSON into small internal events.

Shape follows Meta's webhook reference (messages, statuses, reactions).
https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class TextMessage:
    from_e164: str
    body: str
    message_id: str


@dataclass(frozen=True)
class ReactionEvent:
    from_e164: str
    emoji: str
    reacted_to_message_id: str


def iter_incoming_events(payload: dict[str, Any]) -> Iterator[TextMessage | ReactionEvent]:
    """
    Yield parsed events from a webhook POST body.
    Ignores statuses and unknown types.
    """
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                from_id = msg.get("from", "")
                mid = msg.get("id", "")
                mtype = msg.get("type")
                if mtype == "text":
                    body = (msg.get("text") or {}).get("body") or ""
                    if from_id and mid:
                        yield TextMessage(from_e164=f"+{from_id}", body=body, message_id=mid)
                elif mtype == "reaction":
                    reaction = msg.get("reaction") or {}
                    emoji = reaction.get("emoji") or ""
                    reacted_id = reaction.get("message_id") or ""
                    if from_id and reacted_id:
                        yield ReactionEvent(
                            from_e164=f"+{from_id}",
                            emoji=emoji,
                            reacted_to_message_id=reacted_id,
                        )
