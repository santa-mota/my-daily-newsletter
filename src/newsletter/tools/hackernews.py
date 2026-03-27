"""
Hacker News tool for fetching AI discussions and articles.

Uses the Algolia HN Search API: https://hn.algolia.com/api
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

HN_API = "https://hn.algolia.com/api/v1"


def search_hackernews(
    query: str = "",
    tags: str = "story",
    min_points: int = 50,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Search Hacker News for AI-related stories and discussions.

    This tool finds popular HN posts about AI, ML, and tech topics.

    Args:
        query: Search terms (e.g., "artificial intelligence", "LLM", "RAG")
            Leave empty to get top stories by tags
        tags: Filter by tags. Options:
            - "story" - Submitted stories (default)
            - "show_hn" - Show HN posts
            - "ask_hn" - Ask HN posts
            Multiple: "story,show_hn"
        min_points: Minimum upvotes (default: 50). Higher = more popular
        max_results: Maximum stories to return (default: 10)

    Returns:
        List of story dictionaries with keys:
        - title: Story title
        - url: Link to external article (if available)
        - hn_url: Link to HN discussion
        - points: Upvote count
        - num_comments: Number of comments
        - author: Username of submitter
        - created_at: Submission timestamp
        - story_text: Text content (for Ask HN, Show HN)

    Examples:
        >>> search_hackernews("GPT-4", min_points=100)  # Popular GPT-4 stories
        >>> search_hackernews("", tags="show_hn", min_points=50)  # Show HN projects
        >>> search_hackernews("RAG retrieval", min_points=20, max_results=5)
    """
    try:
        params = {
            "tags": tags,
            "hitsPerPage": max_results,
            "numericFilters": f"points>={min_points}",
        }

        if query:
            params["query"] = query

        with httpx.Client(timeout=30) as client:
            response = client.get(f"{HN_API}/search", params=params)
            response.raise_for_status()
            data = response.json()

        stories = []
        for hit in data.get("hits", []):
            story = {
                "title": hit.get("title", ""),
                "url": hit.get("url"),  # External link (may be None for Ask/Show HN)
                "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "points": hit.get("points", 0),
                "num_comments": hit.get("num_comments", 0),
                "author": hit.get("author", ""),
                "created_at": hit.get("created_at", ""),
                "story_text": hit.get("story_text", ""),  # For Ask/Show HN
            }

            # If no external URL, use HN discussion link
            if not story["url"]:
                story["url"] = story["hn_url"]

            stories.append(story)

        log.info(
            f"HN search for '{query}' (tags={tags}, min_points={min_points}) "
            f"returned {len(stories)} stories"
        )
        return stories

    except Exception as e:
        log.error(f"Hacker News API error: {e}")
        return []


def get_top_hackernews_stories(
    topic: str = "AI",
    min_points: int = 100,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Get top Hacker News stories on a specific topic.

    Convenience wrapper around search_hackernews for trending content.

    Args:
        topic: Topic keyword (e.g., "AI", "machine learning", "GPT")
        min_points: Minimum upvotes (default: 100 for high-quality content)
        max_results: Maximum stories (default: 10)

    Returns:
        List of top stories (same format as search_hackernews)

    Examples:
        >>> get_top_hackernews_stories("large language models", min_points=150)
        >>> get_top_hackernews_stories("RAG", min_points=50, max_results=5)
    """
    return search_hackernews(query=topic, tags="story", min_points=min_points, max_results=max_results)


# OpenAI function calling schema
HACKERNEWS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_hackernews",
        "description": (
            "Search Hacker News for AI and tech discussions. Use this to find popular stories, "
            "Show HN projects, or Ask HN threads about AI, ML, and software engineering topics. "
            "Returns titles, URLs, upvotes, and comment counts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search terms (e.g., 'GPT-4', 'RAG', 'AI safety'). "
                        "Leave empty to get top stories by tags only."
                    ),
                    "default": "",
                },
                "tags": {
                    "type": "string",
                    "description": (
                        "Filter by HN tags: 'story' (default), 'show_hn', 'ask_hn'. "
                        "Multiple: 'story,show_hn'"
                    ),
                    "default": "story",
                },
                "min_points": {
                    "type": "integer",
                    "description": (
                        "Minimum upvotes to filter quality. Use 50 for good content, "
                        "100+ for highly popular, 20 for more results (default: 50)"
                    ),
                    "default": 50,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum stories to return (default: 10, max: 20)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
}
