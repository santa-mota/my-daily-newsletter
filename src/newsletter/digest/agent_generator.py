"""
Agent-driven digest generator with tool calling.

The LLM agent decides which APIs to call, how to search, and what content to include.
This gives the agent full autonomy to adapt based on user preferences and current events.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from newsletter.config import get_settings
from newsletter.db.models import PreferenceEntry
from newsletter.schemas.digest import DigestResult
from newsletter.tools.arxiv import ARXIV_TOOL_SCHEMA, search_arxiv
from newsletter.tools.hackernews import HACKERNEWS_TOOL_SCHEMA, search_hackernews
from newsletter.tools.rss import RSS_TOOL_SCHEMA, fetch_rss_feed

log = logging.getLogger(__name__)

# Map tool names to Python functions
TOOL_FUNCTIONS = {
    "search_arxiv": search_arxiv,
    "search_hackernews": search_hackernews,
    "fetch_rss_feed": fetch_rss_feed,
}

# Tool schemas for OpenAI function calling
TOOL_SCHEMAS = [
    ARXIV_TOOL_SCHEMA,
    HACKERNEWS_TOOL_SCHEMA,
    RSS_TOOL_SCHEMA,
]


def _load_system_prompt() -> str:
    """Load the digest system prompt."""
    path = Path(__file__).resolve().parents[1] / "prompt_data" / "daily_digest_system.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt file at {path}")
    return path.read_text(encoding="utf-8")


def _preferences_block(db: Session) -> str:
    """Pull recent preference rows into a compact block for the user message."""
    from sqlalchemy import select

    q = select(PreferenceEntry).order_by(PreferenceEntry.created_at.desc()).limit(25)
    rows = db.scalars(q).all()
    if not rows:
        return "(no personalization yet — use defaults from the system prompt)"
    lines: list[str] = []
    for r in rows:
        exp = f" expires={r.expires_at.isoformat()}" if r.expires_at else ""
        lines.append(f"- [{r.kind}]{exp}: {r.raw_text}")
    return "\n".join(lines)


def _call_agent_with_tools(*, system: str, user: str, max_iterations: int = 5) -> dict[str, Any]:
    """
    Call OpenAI Chat Completions API with function calling enabled.

    The agent can make multiple tool calls across iterations to gather information.

    Args:
        system: System prompt
        user: User message with preferences and task
        max_iterations: Maximum agent reasoning loops (default: 5)

    Returns:
        Final digest JSON from the agent
    """
    s = get_settings()
    url = f"{s.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {s.openai_api_key}",
        "Content-Type": "application/json",
    }

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    with httpx.Client(timeout=180) as client:  # Longer timeout for multi-turn
        for iteration in range(max_iterations):
            log.info(f"Agent iteration {iteration + 1}/{max_iterations}")

            payload = {
                "model": s.openai_model,
                "temperature": 0.5,
                "messages": messages,
                "tools": TOOL_SCHEMAS,
                "tool_choice": "auto",  # Agent decides when to call tools
            }

            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            response_data = r.json()

            choice = response_data["choices"][0]
            message = choice["message"]
            finish_reason = choice["finish_reason"]

            # Add assistant's response to conversation
            messages.append(message)

            # If agent finished (no tool calls), we're done
            if finish_reason == "stop":
                # Extract final JSON response
                content = message.get("content", "")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    log.error(f"Agent returned non-JSON response: {content[:200]}")
                    raise ValueError("Agent did not return valid JSON")

            # If agent wants to call tools
            if finish_reason == "tool_calls":
                tool_calls = message.get("tool_calls", [])
                log.info(f"Agent requesting {len(tool_calls)} tool calls")

                for tool_call in tool_calls:
                    tool_id = tool_call["id"]
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])

                    log.info(f"Calling tool: {function_name}({function_args})")

                    # Execute the tool
                    try:
                        tool_function = TOOL_FUNCTIONS[function_name]
                        result = tool_function(**function_args)
                        result_str = json.dumps(result)
                    except Exception as e:
                        log.error(f"Tool {function_name} failed: {e}")
                        result_str = json.dumps({"error": str(e)})

                    # Add tool result to conversation
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result_str,
                        }
                    )

                # Continue to next iteration for agent to process tool results
                continue

            # Unexpected finish reason
            log.warning(f"Unexpected finish_reason: {finish_reason}")
            break

    # If we exhaust iterations, raise error
    raise RuntimeError(f"Agent did not complete after {max_iterations} iterations")


def _mock_digest() -> DigestResult:
    """Deterministic placeholder for testing without API keys."""
    return DigestResult.model_validate(
        {
            "intro_markdown": (
                "Here is a **mock digest** (set `OPENAI_API_KEY` for real content). "
                "Section A is news-shaped; Section B nudges toward systems and research."
            ),
            "sections": [
                {
                    "title": "Pulse & headlines (mock)",
                    "summary_bullets": ["Mock item — replace with live model output."],
                    "items": [
                        {
                            "title": "OpenAI newsroom (example)",
                            "url": "https://openai.com/news",
                            "why_it_matters_one_line": (
                                "Official channel for model and product announcements."
                            ),
                            "estimated_read_minutes": 5,
                            "tags": ["news"],
                        }
                    ],
                },
                {
                    "title": "Ideas, research, and interview depth (mock)",
                    "summary_bullets": ["Mock item — RAG / inference angle."],
                    "items": [
                        {
                            "title": "arXiv cs.AI recent (example)",
                            "url": "https://arxiv.org/list/cs.AI/recent",
                            "why_it_matters_one_line": (
                                "Primary research feed — pick 1–2 papers after scanning titles."
                            ),
                            "estimated_read_minutes": 10,
                            "tags": ["research", "RAG"],
                        }
                    ],
                },
            ],
            "clarification_question": None,
        }
    )


def generate_digest_with_agent(db: Session) -> DigestResult:
    """
    Generate digest using an agent with tool-calling capabilities.

    The agent:
    1. Receives user preferences and current date
    2. Decides which news sources to query (arXiv, HN, RSS feeds)
    3. Calls tools to fetch fresh content
    4. Selects, ranks, and formats the best items
    5. Returns structured JSON digest

    This is the RECOMMENDED approach as it gives the LLM full control over
    what to fetch and how to curate based on user preferences.
    """
    system = _load_system_prompt()
    prefs = _preferences_block(db)
    schema = json.dumps(DigestResult.model_json_schema(), indent=2)

    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d %A")

    user = f"""## Today's date
{today}

## Available tools
You have access to these tools to fetch fresh content:
1. **search_arxiv** - Search arXiv for research papers (AI, ML, CS topics)
2. **search_hackernews** - Search Hacker News for AI discussions and popular stories
3. **fetch_rss_feed** - Fetch recent posts from AI company blogs (OpenAI, Anthropic, Google AI, etc.)

## Your task
1. **Decide what to fetch**: Based on the personalization context below, determine which sources to query and with what search terms
2. **Call tools**: Use the tools to gather fresh content. You can call multiple tools and make multiple searches
3. **Curate content**: From all tool results, select the BEST 5-8 links that match the user's interests and the two-section structure (Pulse & Headlines + Research & Depth)
4. **Generate digest**: Return a structured JSON digest following the schema below

## Personalization context (most recent first)
{prefs}

## Output schema (JSON only — match these keys)
{schema}

## Important guidelines
- **Aim for 15-30 min total reading time** (5-8 links)
- **Two sections**: Roughly half news, half research/depth
- **Fresh content**: Use tool results, not your training data
- **Quality over quantity**: Better to have 5 excellent links than 10 mediocre ones
- **Respect preferences**: If user says "tomorrow I want X", prioritize X in tool searches
- **Clarification**: If preferences conflict severely, set `clarification_question` field

Start by deciding which tools to call and with what parameters. Think step-by-step.
"""

    if not get_settings().openai_api_key:
        log.warning("OPENAI_API_KEY missing — returning mock digest.")
        return _mock_digest()

    try:
        raw = _call_agent_with_tools(system=system, user=user, max_iterations=5)
        return DigestResult.model_validate(raw)
    except Exception:
        log.exception("Agent-based digest generation failed; falling back to mock digest.")
        return _mock_digest()
