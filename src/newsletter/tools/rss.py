"""
RSS feed tool for fetching AI news from official blogs.

Fetches recent posts from OpenAI, Anthropic, Google AI, and other AI company blogs.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Curated list of AI company and researcher blogs
RSS_FEEDS = {
    "openai": "https://openai.com/blog/rss.xml",
    "anthropic": "https://www.anthropic.com/news/rss.xml",
    "google_ai": "https://blog.google/technology/ai/rss/",
    "deepmind": "https://deepmind.google/blog/rss.xml",
    "meta_ai": "https://ai.meta.com/blog/rss/",
    "microsoft_ai": "https://blogs.microsoft.com/ai/feed/",
}


def fetch_rss_feed(
    source: str,
    days_back: int = 7,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch recent posts from an AI company blog RSS feed.

    This tool gets official announcements, research updates, and product launches
    from major AI labs.

    Args:
        source: RSS feed source. Options:
            - "openai" - OpenAI blog
            - "anthropic" - Anthropic news
            - "google_ai" - Google AI blog
            - "deepmind" - DeepMind blog
            - "meta_ai" - Meta AI blog
            - "microsoft_ai" - Microsoft AI blog
            - Or provide custom RSS URL
        days_back: Only return posts from last N days (default: 7)
        max_items: Maximum posts to return (default: 10)

    Returns:
        List of blog post dictionaries with keys:
        - title: Post title
        - url: Link to full article
        - summary: Post excerpt/description
        - published: Publication date (ISO format)
        - author: Post author (if available)
        - source: Feed source name

    Examples:
        >>> fetch_rss_feed("openai", days_back=14)  # OpenAI posts from last 2 weeks
        >>> fetch_rss_feed("anthropic", max_items=5)  # Latest 5 Anthropic posts
        >>> fetch_rss_feed("https://simonwillison.net/atom/everything/", days_back=3)
    """
    try:
        # Resolve source to URL
        if source.startswith("http"):
            feed_url = source
            source_name = source
        else:
            feed_url = RSS_FEEDS.get(source.lower())
            if not feed_url:
                log.error(f"Unknown RSS source: {source}")
                return []
            source_name = source

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(feed_url)
            response.raise_for_status()

        # Parse RSS/Atom feed
        root = ET.fromstring(response.content)

        # Try RSS 2.0 format first
        items = root.findall(".//item")
        if not items:
            # Try Atom format
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//atom:entry", ns)
            is_atom = True
        else:
            is_atom = False

        cutoff_date = datetime.now() - timedelta(days=days_back)
        posts = []

        for item in items[:max_items]:
            try:
                if is_atom:
                    # Atom format
                    title = item.findtext("{http://www.w3.org/2005/Atom}title", default="").strip()
                    link_elem = item.find("{http://www.w3.org/2005/Atom}link[@rel='alternate']")
                    url = link_elem.get("href") if link_elem is not None else ""
                    summary = item.findtext("{http://www.w3.org/2005/Atom}summary", default="").strip()
                    published_str = item.findtext("{http://www.w3.org/2005/Atom}published", default="")
                    if not published_str:
                        published_str = item.findtext("{http://www.w3.org/2005/Atom}updated", default="")
                    author_elem = item.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
                    author = author_elem.text if author_elem is not None else ""
                else:
                    # RSS 2.0 format
                    title = item.findtext("title", default="").strip()
                    url = item.findtext("link", default="").strip()
                    summary = item.findtext("description", default="").strip()
                    published_str = item.findtext("pubDate", default="")
                    author = item.findtext("author", default="")

                # Parse date
                if published_str:
                    # Try multiple date formats
                    for fmt in [
                        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
                        "%a, %d %b %Y %H:%M:%S %z",  # RFC 822
                        "%Y-%m-%d",  # Simple date
                    ]:
                        try:
                            published = datetime.strptime(published_str.replace("Z", "+0000"), fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        published = datetime.now()  # Fallback

                    if published < cutoff_date:
                        continue  # Skip old posts

                # Clean summary (strip HTML tags if present)
                import re
                summary = re.sub(r"<[^>]+>", "", summary)[:400]

                posts.append(
                    {
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "published": published_str,
                        "author": author,
                        "source": source_name,
                    }
                )

            except Exception as e:
                log.warning(f"Error parsing RSS item: {e}")
                continue

        log.info(f"RSS feed '{source_name}' returned {len(posts)} posts")
        return posts

    except Exception as e:
        log.error(f"RSS feed error for '{source}': {e}")
        return []


def fetch_all_ai_blogs(days_back: int = 7, max_per_source: int = 5) -> list[dict[str, Any]]:
    """
    Fetch recent posts from all major AI company blogs.

    Convenience function to get a comprehensive view of official AI news.

    Args:
        days_back: Only return posts from last N days (default: 7)
        max_per_source: Max posts per blog (default: 5)

    Returns:
        Combined list of blog posts from all sources

    Examples:
        >>> fetch_all_ai_blogs(days_back=14)  # All AI blog posts from last 2 weeks
    """
    all_posts = []
    for source in RSS_FEEDS.keys():
        posts = fetch_rss_feed(source, days_back=days_back, max_items=max_per_source)
        all_posts.extend(posts)

    # Sort by publication date (newest first)
    all_posts.sort(
        key=lambda x: x.get("published", ""), reverse=True
    )
    return all_posts


# OpenAI function calling schema
RSS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_rss_feed",
        "description": (
            "Fetch recent blog posts from AI company official blogs (OpenAI, Anthropic, Google AI, "
            "DeepMind, Meta AI, Microsoft AI). Use this to get official announcements, research updates, "
            "and product launches. Returns titles, URLs, and post summaries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["openai", "anthropic", "google_ai", "deepmind", "meta_ai", "microsoft_ai"],
                    "description": (
                        "AI blog source: 'openai', 'anthropic', 'google_ai', 'deepmind', "
                        "'meta_ai', or 'microsoft_ai'"
                    ),
                },
                "days_back": {
                    "type": "integer",
                    "description": "Only return posts from last N days (default: 7)",
                    "default": 7,
                },
                "max_items": {
                    "type": "integer",
                    "description": "Maximum posts to return (default: 10, max: 20)",
                    "default": 10,
                },
            },
            "required": ["source"],
        },
    },
}
