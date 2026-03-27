"""
Streaming API for digest delivery (chat-like behavior).

Returns digest as a stream of individual messages, similar to WhatsApp:
- Intro message
- Individual link messages (one per link)
- Clarification question (if any)

This mimics the WhatsApp behavior where each link is sent as a separate message.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.base import get_db
from newsletter.digest.agent_generator import generate_digest_with_agent

log = logging.getLogger(__name__)

router = APIRouter()


async def generate_digest_stream(db: Session) -> AsyncGenerator[str, None]:
    """
    Generate digest and yield as stream of messages.

    Each yield is a JSON object with 'type' and 'content'.

    Message types:
    - "intro": Intro paragraph
    - "link": Individual link with metadata
    - "clarification": Clarification question (if any)
    - "done": End of stream
    """
    try:
        # Generate digest (this takes 30-60 seconds)
        yield json.dumps({"type": "status", "content": "Generating your digest..."}) + "\n"
        await asyncio.sleep(0.1)  # Small delay for client to receive

        result = generate_digest_with_agent(db)

        # Send intro
        yield json.dumps(
            {
                "type": "intro",
                "content": result.intro_markdown,
            }
        ) + "\n"
        await asyncio.sleep(0.5)  # Small delay between messages

        # Send individual links
        for section in result.sections:
            for item in section.items:
                link_msg = {
                    "type": "link",
                    "section": section.title,
                    "title": item.title,
                    "url": item.url,
                    "why": item.why_it_matters_one_line,
                    "minutes": item.estimated_read_minutes,
                    "tags": item.tags,
                }
                yield json.dumps(link_msg) + "\n"
                await asyncio.sleep(0.3)  # Small delay between links

        # Send clarification if any
        if result.clarification_question:
            yield json.dumps(
                {
                    "type": "clarification",
                    "content": result.clarification_question,
                }
            ) + "\n"
            await asyncio.sleep(0.3)

        # Send completion
        yield json.dumps({"type": "done", "content": "Digest complete"}) + "\n"

    except Exception as e:
        log.exception("Digest streaming failed")
        yield json.dumps({"type": "error", "content": f"Error: {e}"}) + "\n"


@router.get("/api/digest/stream")
async def stream_digest(
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Stream digest as individual messages (chat-like behavior).

    Returns a stream of JSON objects, one per line (newline-delimited JSON).

    Example usage with curl:
        curl -N http://localhost:8000/api/digest/stream

    Example usage with JavaScript:
        const response = await fetch('/api/digest/stream');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const {value, done} = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\\n').filter(l => l.trim());

            for (const line of lines) {
                const msg = JSON.parse(line);
                console.log(msg.type, msg);

                if (msg.type === 'intro') {
                    // Display intro
                } else if (msg.type === 'link') {
                    // Display link
                } else if (msg.type === 'done') {
                    // Done
                }
            }
        }

    Response format:
        Each line is a JSON object with 'type' field:

        {"type": "status", "content": "Generating your digest..."}
        {"type": "intro", "content": "Here's your daily AI digest..."}
        {"type": "link", "section": "Research", "title": "...", "url": "...", "why": "...", "minutes": 5, "tags": [...]}
        {"type": "link", "section": "News", "title": "...", "url": "...", "why": "...", "minutes": 3, "tags": [...]}
        {"type": "clarification", "content": "Are you still interested in GPT-5 news?"}
        {"type": "done", "content": "Digest complete"}
    """
    return StreamingResponse(
        generate_digest_stream(db),
        media_type="application/x-ndjson",  # Newline-delimited JSON
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/api/digest/preview")
async def preview_digest(db: Session = Depends(get_db)) -> dict:
    """
    Generate digest and return as complete JSON (non-streaming).

    Use this for testing or when you want the full digest at once.

    Returns:
        {
            "intro": "...",
            "sections": [
                {
                    "title": "Research",
                    "items": [
                        {
                            "title": "...",
                            "url": "...",
                            "why": "...",
                            "minutes": 5,
                            "tags": [...]
                        }
                    ]
                }
            ],
            "clarification": "..." or null
        }
    """
    try:
        result = generate_digest_with_agent(db)

        return {
            "status": "ok",
            "intro": result.intro_markdown,
            "sections": [
                {
                    "title": section.title,
                    "summary": section.summary_bullets,
                    "items": [
                        {
                            "title": item.title,
                            "url": item.url,
                            "why": item.why_it_matters_one_line,
                            "minutes": item.estimated_read_minutes,
                            "tags": item.tags,
                        }
                        for item in section.items
                    ],
                }
                for section in result.sections
            ],
            "clarification": result.clarification_question,
        }

    except Exception as e:
        log.exception("Digest preview failed")
        return {"status": "error", "error": str(e)}
