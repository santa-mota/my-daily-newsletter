"""Thin wrapper around WhatsApp Cloud API HTTP endpoints."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from newsletter.config import get_settings

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"


def _headers() -> dict[str, str]:
    token = get_settings().whatsapp_access_token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def send_text_message(*, to_e164: str, body: str) -> dict[str, Any]:
    """
    Send a plain text message. `to_e164` must include country code, no spaces.

    API ref: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages
    """
    settings = get_settings()
    phone_id = settings.whatsapp_phone_number_id
    if not phone_id or not settings.whatsapp_access_token:
        log.warning("WhatsApp not configured; skipping send.")
        return {"skipped": True}

    # Cloud API expects digits only for `to`
    to_digits = "".join(c for c in to_e164 if c.isdigit())
    url = f"{GRAPH}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_digits,
        "type": "text",
        "text": {"preview_url": True, "body": body[:4096]},
    }
    with httpx.Client(timeout=60) as client:
        r = client.post(url, headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()
