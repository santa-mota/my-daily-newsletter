"""Send a digest as: intro first, then one WhatsApp message per link."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.models import DigestRun, OutgoingMessage
from newsletter.schemas.digest import DigestResult
from newsletter.services.tagging import extract_tags_from_digest_item
from newsletter.whatsapp.client import send_text_message

log = logging.getLogger(__name__)


def _extract_wamid(response: dict[str, Any]) -> str | None:
    try:
        msgs = response.get("messages") or []
        if msgs:
            mid = msgs[0].get("id")
            return str(mid) if mid else None
    except Exception:
        return None
    return None


def deliver_digest(db: Session, result: DigestResult) -> DigestRun:
    """
    Persist the run, send intro + per-link messages, record WhatsApp ids for reactions.
    """
    settings = get_settings()
    to = settings.user_whatsapp_e164
    if not to:
        log.warning("USER_WHATSAPP_E164 not set; skipping WhatsApp send.")

    items_flat: list[dict[str, Any]] = []
    for sec in result.sections:
        for it in sec.items:
            items_flat.append(
                {
                    "section": sec.title,
                    "title": it.title,
                    "url": it.url,
                    "why": it.why_it_matters_one_line,
                    "minutes": it.estimated_read_minutes,
                    "tags": it.tags,
                }
            )

    run = DigestRun(
        intro_text=result.intro_markdown,
        items_json=items_flat,
        sent=False,
    )
    db.add(run)
    db.flush()

    if result.clarification_question:
        body = f"{result.intro_markdown}\n\n❓ {result.clarification_question}"
    else:
        body = result.intro_markdown

    if to:
        intro_resp = send_text_message(to_e164=to, body=body)
        _ = _extract_wamid(intro_resp)

        for row in items_flat:
            title = row["title"]
            url = row["url"]
            why = row["why"]
            sec = row["section"]
            tags = row.get("tags", [])

            msg = f"*{sec}*\n*{title}*\n{url}\n_{why}_"
            resp = send_text_message(to_e164=to, body=msg)
            wamid = _extract_wamid(resp)
            if wamid:
                # Extract tags and context summary (no LLM call, already in digest)
                tags_list, context_summary = extract_tags_from_digest_item(row)

                db.add(
                    OutgoingMessage(
                        whatsapp_wamid=wamid,
                        url=url,
                        title=title,
                        tags=tags_list,
                        context_summary=context_summary,
                    )
                )

    run.sent = True
    db.add(run)
    return run
