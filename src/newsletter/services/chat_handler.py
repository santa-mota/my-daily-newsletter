"""
Intelligent chat handler for understanding user intent.

Uses LLM to classify user messages and route to appropriate actions:
- Saving links/articles via natural language ("store that RAG article")
- Retrieving saved links ("show me RAG papers from last week")
- Setting preferences ("tomorrow I want news about GPT-5")
- General queries about saved content

This is cost-efficient: uses single LLM call to classify intent,
then executes deterministic functions without additional LLM calls.
"""

import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.services.tagging import (
    format_saved_links_for_display,
    save_link_from_api,
    search_saved_links_by_date,
    search_saved_links_by_tags,
    search_saved_links_by_text,
)

log = logging.getLogger(__name__)


class ChatIntent(BaseModel):
    """Classification of user chat message intent."""

    type: Literal["save_link", "retrieve_links", "preference", "general"]
    save_url: str | None = None
    save_title: str | None = None
    search_query: str | None = None
    search_type: Literal["text", "tags", "date"] | None = None
    confidence: float  # 0.0 to 1.0


def _classify_chat_intent(message: str) -> ChatIntent:
    """
    Use LLM to classify user intent from chat message.

    This is the ONLY LLM call for chat handling.
    After classification, we use deterministic functions.

    Args:
        message: User's message text

    Returns:
        ChatIntent with classified type and extracted parameters
    """
    settings = get_settings()

    system = """You are a chat intent classifier for a newsletter bot.

Classify user messages into one of these intents:
1. "save_link": User wants to save an article/link for later
   Examples:
   - "Store that RAG article"
   - "Save this for me: https://arxiv.org/abs/2401.12345"
   - "Remember this paper"

2. "retrieve_links": User wants to find previously saved links
   Examples:
   - "Show me RAG papers from last week"
   - "Find that GPT-5 article I saved"
   - "What did I save about transformers?"

3. "preference": User is setting preferences for future digests
   Examples:
   - "Tomorrow I want news about GPT-5"
   - "I'm interested in RAG techniques"
   - "More papers about inference optimization"

4. "general": General queries, greetings, or unclear intent
   Examples:
   - "Hello"
   - "What is RAG?"
   - "How do I use this?"

Extract parameters based on intent type:
- For save_link: extract URL if present, title if mentioned
- For retrieve_links: extract search query and determine if it's text/tags/date
- For preference: no extraction needed (handled by preference interpreter)

Return JSON with: type, save_url, save_title, search_query, search_type, confidence."""

    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Classify this message and extract parameters:\n\n{message}",
            },
        ],
        "temperature": 0.0,  # Deterministic classification
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{settings.openai_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)

        return ChatIntent.model_validate(data)

    except Exception as e:
        log.exception("Intent classification failed")
        # Default to general with low confidence
        return ChatIntent(type="general", confidence=0.0)


def handle_chat_message(db: Session, message: str) -> str:
    """
    Handle user chat message with intelligent intent detection.

    This is the main entry point for chat-based interactions.
    Uses ONE LLM call to classify intent, then executes appropriate action.

    Args:
        db: Database session
        message: User's message text

    Returns:
        Response text to send back to user
    """
    # Classify intent (single LLM call)
    intent = _classify_chat_intent(message)

    log.info(f"Classified intent: {intent.type} (confidence: {intent.confidence:.2f})")

    # Route to appropriate handler (no more LLM calls)
    if intent.type == "save_link":
        return _handle_save_link(db, intent)
    elif intent.type == "retrieve_links":
        return _handle_retrieve_links(db, intent)
    elif intent.type == "preference":
        # This is handled by the preference interpreter in inbound.py
        return "Got it! I'll consider this preference for your next digest."
    else:
        # General/unclear intent
        if intent.confidence < 0.5:
            return (
                "I'm not sure what you want me to do. You can:\n"
                "• Save a link: 'Store that RAG article' or paste a URL\n"
                "• Find saved links: 'Show me papers about GPT-5'\n"
                "• Set preferences: 'Tomorrow I want news about AI safety'\n"
                "• List all saved: 'List saved'"
            )
        return "I understand, but I'm not sure how to help with that yet."


def _handle_save_link(db: Session, intent: ChatIntent) -> str:
    """
    Handle save link intent.

    Args:
        db: Database session
        intent: Classified intent with save_url and save_title

    Returns:
        Confirmation message
    """
    if not intent.save_url:
        return (
            "I'd be happy to save that for you! "
            "Please provide the URL you want to save."
        )

    # Save link (no LLM call - tags would be pre-computed from digest)
    saved = save_link_from_api(
        db=db,
        url=intent.save_url,
        title=intent.save_title,
        tags=None,  # Will be empty; ideally extract from recent digest
        context_summary=intent.save_title,
    )

    tags_info = f" (Tags: {', '.join(saved.tags)})" if saved.tags else ""

    return f"✓ Saved: {saved.title or saved.url}{tags_info}"


def _handle_retrieve_links(db: Session, intent: ChatIntent) -> str:
    """
    Handle retrieve links intent.

    Args:
        db: Database session
        intent: Classified intent with search_query and search_type

    Returns:
        Formatted search results
    """
    if not intent.search_query:
        # Default to recent links
        results = search_saved_links_by_date(db, days_back=7, limit=10)
        return format_saved_links_for_display(results)

    # Determine search type
    search_type = intent.search_type or "text"

    if search_type == "tags":
        # Split comma-separated tags
        tags = [t.strip() for t in intent.search_query.split(",")]
        results = search_saved_links_by_tags(db, tags, limit=20)
    elif search_type == "date":
        try:
            days_back = int(intent.search_query)
        except ValueError:
            days_back = 7  # Default to last week
        results = search_saved_links_by_date(db, days_back=days_back, limit=20)
    else:
        # Text search (default)
        results = search_saved_links_by_text(db, intent.search_query, limit=20)

    return format_saved_links_for_display(results)
