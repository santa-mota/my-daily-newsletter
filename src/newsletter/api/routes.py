"""FastAPI routes: WhatsApp webhook, health, manual digest trigger, saved links API."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.base import get_db
from newsletter.jobs.scheduler import run_digest_job
from newsletter.services.inbound import handle_reaction, handle_text_message
from newsletter.services.tagging import (
    format_saved_links_for_display,
    save_link_from_api,
    search_saved_links_by_date,
    search_saved_links_by_tags,
    search_saved_links_by_text,
)
from newsletter.whatsapp.payload import ReactionEvent, TextMessage, iter_incoming_events
from newsletter.whatsapp.verify import verify_meta_signature

log = logging.getLogger(__name__)

router = APIRouter()


# --- Request/Response Models for API ---


class SaveLinkRequest(BaseModel):
    """Request to save a link via API."""

    url: str
    title: str | None = None
    tags: list[str] | None = None
    context_summary: str | None = None


class SaveLinkResponse(BaseModel):
    """Response after saving a link."""

    status: str
    link_id: int
    url: str
    title: str | None
    tags: list[str]
    context_summary: str | None


class SearchLinksRequest(BaseModel):
    """Request to search saved links."""

    query: str
    search_type: str = "text"  # "text", "tags", or "date"
    limit: int = 20


class SearchLinksResponse(BaseModel):
    """Response with search results."""

    status: str
    count: int
    results: list[dict]
    formatted: str


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


# --- Saved Links API ---


@router.post("/api/save-link", response_model=SaveLinkResponse)
def save_link(
    request: SaveLinkRequest,
    db: Session = Depends(get_db),
) -> SaveLinkResponse:
    """
    Save a link via API (no WhatsApp reaction needed).

    If tags are not provided, the link is saved without tags.
    For cost efficiency, provide tags from the digest or extract manually.

    Example:
        POST /api/save-link
        {
            "url": "https://arxiv.org/abs/2401.12345",
            "title": "New RAG technique",
            "tags": ["RAG", "retrieval", "transformers"],
            "context_summary": "Novel approach to RAG with 2x speedup"
        }
    """
    saved = save_link_from_api(
        db=db,
        url=request.url,
        title=request.title,
        tags=request.tags,
        context_summary=request.context_summary,
    )

    return SaveLinkResponse(
        status="saved",
        link_id=saved.id,
        url=saved.url,
        title=saved.title,
        tags=saved.tags or [],
        context_summary=saved.context_summary,
    )


@router.post("/api/search-links", response_model=SearchLinksResponse)
def search_links(
    request: SearchLinksRequest,
    db: Session = Depends(get_db),
) -> SearchLinksResponse:
    """
    Search saved links by text, tags, or date.

    Search types:
    - "text": Search title, context_summary, and tags by keyword
    - "tags": Search by exact tag matches (case-insensitive)
    - "date": Get links from recent days (query should be integer, e.g., "7")

    Examples:
        # Search by text
        POST /api/search-links
        {"query": "RAG paper", "search_type": "text", "limit": 10}

        # Search by tags
        POST /api/search-links
        {"query": "RAG,GPT-5", "search_type": "tags", "limit": 20}

        # Get links from last 7 days
        POST /api/search-links
        {"query": "7", "search_type": "date", "limit": 20}
    """
    if request.search_type == "text":
        results = search_saved_links_by_text(db, request.query, limit=request.limit)
    elif request.search_type == "tags":
        # Split comma-separated tags
        tags = [t.strip() for t in request.query.split(",")]
        results = search_saved_links_by_tags(db, tags, limit=request.limit)
    elif request.search_type == "date":
        try:
            days_back = int(request.query)
        except ValueError:
            raise HTTPException(status_code=400, detail="For date search, query must be integer days")
        results = search_saved_links_by_date(db, days_back=days_back, limit=request.limit)
    else:
        raise HTTPException(status_code=400, detail="search_type must be: text, tags, or date")

    # Format results as dicts for JSON response
    results_dicts = [
        {
            "id": link.id,
            "url": link.url,
            "title": link.title,
            "tags": link.tags or [],
            "context_summary": link.context_summary,
            "created_at": link.created_at.isoformat(),
            "reaction_emoji": link.reaction_emoji,
        }
        for link in results
    ]

    # Also provide formatted markdown for display
    formatted = format_saved_links_for_display(results)

    return SearchLinksResponse(
        status="ok",
        count=len(results),
        results=results_dicts,
        formatted=formatted,
    )


@router.get("/api/saved-links")
def list_saved_links(
    limit: int = 20,
    days_back: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """
    List saved links (most recent first).

    Query params:
    - limit: Max results (default 20)
    - days_back: Only show links from last N days (optional)

    Example:
        GET /api/saved-links?limit=10&days_back=7
    """
    if days_back is not None:
        results = search_saved_links_by_date(db, days_back=days_back, limit=limit)
    else:
        from newsletter.db.models import SavedLink
        from sqlalchemy import select

        results = list(
            db.scalars(select(SavedLink).order_by(SavedLink.created_at.desc()).limit(limit)).all()
        )

    results_dicts = [
        {
            "id": link.id,
            "url": link.url,
            "title": link.title,
            "tags": link.tags or [],
            "context_summary": link.context_summary,
            "created_at": link.created_at.isoformat(),
            "reaction_emoji": link.reaction_emoji,
        }
        for link in results
    ]

    formatted = format_saved_links_for_display(results)

    return {
        "status": "ok",
        "count": len(results),
        "results": results_dicts,
        "formatted": formatted,
    }
