"""
arXiv tool for fetching recent research papers.

The agent can call this tool with search queries to find relevant papers.
Uses the arXiv API: http://export.arxiv.org/api_help/docs/user-manual.html
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"


def search_arxiv(
    query: str,
    max_results: int = 10,
    days_back: int = 7,
    sort_by: str = "submittedDate",
) -> list[dict[str, Any]]:
    """
    Search arXiv for research papers.

    This tool allows the agent to find recent AI/ML research papers based on search terms.

    Args:
        query: Search query. Examples:
            - "cat:cs.AI" - All AI papers
            - "cat:cs.LG" - Machine Learning papers
            - "RAG OR retrieval augmented generation"
            - "ti:transformer AND abs:attention"
        max_results: Maximum papers to return (default: 10)
        days_back: Only return papers from last N days (default: 7)
        sort_by: Sort order - "submittedDate" or "relevance" (default: submittedDate)

    Returns:
        List of paper dictionaries with keys:
        - title: Paper title
        - authors: List of author names
        - summary: Abstract text
        - pdf_url: Direct link to PDF
        - arxiv_url: Link to arXiv page
        - published: Publication date (ISO format)
        - categories: List of arXiv categories (e.g., ["cs.AI", "cs.LG"])

    Examples:
        >>> search_arxiv("cat:cs.AI AND (RAG OR retrieval)", max_results=5)
        >>> search_arxiv("attention mechanism", days_back=3, sort_by="relevance")
    """
    try:
        params = {
            "search_query": query,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }

        with httpx.Client(timeout=30) as client:
            response = client.get(ARXIV_API, params=params)
            response.raise_for_status()

        # Parse Atom XML feed
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        cutoff_date = datetime.now() - timedelta(days=days_back)
        papers = []

        for entry in root.findall("atom:entry", ns):
            # Parse publication date
            published_str = entry.findtext("atom:published", namespaces=ns)
            if published_str:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                if published < cutoff_date:
                    continue  # Skip old papers

            # Extract paper metadata
            title = entry.findtext("atom:title", namespaces=ns, default="").strip()
            summary = entry.findtext("atom:summary", namespaces=ns, default="").strip()

            # Authors
            authors = [
                author.findtext("atom:name", namespaces=ns, default="")
                for author in entry.findall("atom:author", ns)
            ]

            # Links (PDF and abstract page)
            pdf_url = None
            arxiv_url = None
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href")
                elif link.get("type") == "text/html":
                    arxiv_url = link.get("href")

            # Categories
            categories = [
                cat.get("term")
                for cat in entry.findall("arxiv:primary_category", ns)
                + entry.findall("atom:category", ns)
            ]

            papers.append(
                {
                    "title": title,
                    "authors": authors[:3],  # Limit to first 3 authors
                    "summary": summary[:400],  # Truncate long abstracts
                    "pdf_url": pdf_url,
                    "arxiv_url": arxiv_url,
                    "published": published_str,
                    "categories": list(set(categories)),  # Deduplicate
                }
            )

        log.info(f"arXiv search for '{query}' returned {len(papers)} papers")
        return papers

    except Exception as e:
        log.error(f"arXiv API error: {e}")
        return []


# OpenAI function calling schema
ARXIV_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_arxiv",
        "description": (
            "Search arXiv for recent AI/ML research papers. Use this to find papers on specific topics "
            "like RAG, transformers, inference optimization, or any AI research area. "
            "Returns paper titles, authors, abstracts, and PDF links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. Examples: 'cat:cs.AI' for all AI papers, "
                        "'RAG OR retrieval augmented generation' for keyword search, "
                        "'ti:transformer' for title search. Use arXiv query syntax."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return (default: 10, max: 20)",
                    "default": 10,
                },
                "days_back": {
                    "type": "integer",
                    "description": "Only return papers from last N days (default: 7)",
                    "default": 7,
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["submittedDate", "relevance"],
                    "description": "Sort by submission date (newest first) or relevance (default: submittedDate)",
                    "default": "submittedDate",
                },
            },
            "required": ["query"],
        },
    },
}
