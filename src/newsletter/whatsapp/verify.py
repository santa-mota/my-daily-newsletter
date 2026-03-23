"""Verify `X-Hub-Signature-256` from Meta webhooks."""

from __future__ import annotations

import hashlib
import hmac

from newsletter.config import get_settings


def verify_meta_signature(*, raw_body: bytes, signature_header: str | None) -> bool:
    """
    Meta sends `sha256=<hex>` in `X-Hub-Signature-256`.

    If `WHATSAPP_APP_SECRET` is empty, verification is skipped (development only).
    """
    secret = get_settings().whatsapp_app_secret
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
