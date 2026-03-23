"""FastAPI routes: WhatsApp webhook, health, manual digest trigger."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.base import get_db
from newsletter.jobs.scheduler import run_digest_job
from newsletter.services.inbound import handle_reaction, handle_text_message
from newsletter.whatsapp.payload import ReactionEvent, TextMessage, iter_incoming_events
from newsletter.whatsapp.verify import verify_meta_signature

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Meta subscription verification — must echo `hub.challenge` when token matches."""
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        if hub_challenge:
            return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw_body=raw, signature_header=sig):
        raise HTTPException(status_code=403, detail="Bad signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    settings = get_settings()
    owner = settings.user_whatsapp_e164

    for ev in iter_incoming_events(payload):
        if isinstance(ev, TextMessage):
            handle_text_message(db, ev, owner)
        elif isinstance(ev, ReactionEvent):
            handle_reaction(db, ev, owner)

    return {"received": "true"}


@router.post("/internal/run-digest")
def manual_run_digest(
    x_trigger_secret: Annotated[str | None, Header(alias="X-Trigger-Secret")] = None,
) -> dict[str, str]:
    """
    On-demand digest for testing. Set `TRIGGER_SECRET` in the environment; the
    header must match. If `TRIGGER_SECRET` is empty, the endpoint is open (dev only).
    """
    settings = get_settings()
    expected = (settings.trigger_secret or "").strip()
    if expected and (x_trigger_secret or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_digest_job()
    return {"status": "ok"}
