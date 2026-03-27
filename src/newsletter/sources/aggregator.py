"""
Aggregate fresh AI news and research from free/open APIs.

Data Sources (ALL FREE, NO API KEYS):
- arXiv API: Research papers (cs.AI, cs.LG, cs.CL)
- Hacker News Algolia API: Community discussions
- Reddit JSON API: r/MachineLearning, r/LocalLLaMA
- Hugging Face Papers: Daily papers feed
- RSS Feeds: OpenAI, Anthropic, Google AI blogs

All sources are scraped/queried in real-time daily.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)


class NewsItem:
    """Standardized news/research item."""

    def __init__(
        self,
        title: str,
        url: str,
        summary: str = "",
        source: str = "",
        score: int | None = None,
        published: datetime | None = None,
        authors: list[str] | None = None,
        tags: list[str] | None = None,
    ):
        self.title = title
        self.url = url
        self.summary = summary
        self.source = source
        self.score = score
        self.published = published
        self.authors = authors or []
        self.tags = tags or []

    def __repr__(self) -> str:
        return f"<NewsItem: {self.title[:50]}... from {self.source}>"


class NewsAggregator:
    """
    Fetch fresh AI content from multiple free sources.

    Usage:
        aggregator = NewsAggregator()
        sources = aggregator.fetch_today()
        # Returns: {"news": [...], "research": [...], "discussions": [...]}
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def fetch_today(self) -> dict[str, list[NewsItem]]:
        """
        Fetch categorized content for today's digest.

        Returns dict with keys: "news", "research", "discussions"
        Each value is a list of NewsItem objects.
        """
        try:
            return {
                "news": self._fetch_news(),
                "research": self._fetch_research(),
                "discussions": self._fetch_discussions(),
            }
        except Exception:
            log.exception("Failed to fetch news sources; returning empty sets.")
            return {"news": [], "research": [], "discussions": []}

    # -------------------------------------------------------------------------
    # RESEARCH SOURCES (Papers, arXiv, Hugging Face)
    # -------------------------------------------------------------------------

    def _fetch_research(self) -> list[NewsItem]:
        """Fetch research papers from arXiv and Hugging Face."""
        items: list[NewsItem] = []

        # arXiv: Last 3 days of cs.AI, cs.LG, cs.CL
        try:
            items.extend(self._fetch_arxiv())
        except Exception:
            log.exception("arXiv fetch failed")

        # Hugging Face Daily Papers (last 7 days)
        try:
            items.extend(self._fetch_huggingface_papers())
        except Exception:
            log.exception("Hugging Face papers fetch failed")

        # Sort by recency, limit to 15
        items.sort(key=lambda x: x.published or datetime.min.replace(tzinfo=UTC), reverse=True)
        return items[:15]

    def _fetch_arxiv(self, max_results: int = 20) -> list[NewsItem]:
        """
        Query arXiv API for recent AI/ML papers.

        API Docs: http://export.arxiv.org/api_help/docs/user-manual.html
        No API key required, free, but rate-limited (429 errors common).
        """
        # Last 3 days to avoid stale content
        cutoff = datetime.now(UTC) - timedelta(days=3)
        cutoff_str = cutoff.strftime("%Y%m%d")

        # Query: cs.AI OR cs.LG OR cs.CL (AI, ML, NLP)
        query = f"cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
        url = (
            f"http://export.arxiv.org/api/query?"
            f"search_query={query}&"
            f"sortBy=submittedDate&sortOrder=descending&"
            f"max_results={max_results}"
        )

        # arXiv requires 3-second delay between requests (rate limiting)
        import time
        time.sleep(3)

        try:
            response = self.client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                log.warning("arXiv rate limit hit (429); skipping arXiv this run.")
                return []
            raise

        # Parse Atom XML
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        items: list[NewsItem] = []
        for entry in root.findall("atom:entry", ns):
            title_elem = entry.find("atom:title", ns)
            summary_elem = entry.find("atom:summary", ns)
            published_elem = entry.find("atom:published", ns)
            id_elem = entry.find("atom:id", ns)

            # Extract authors
            authors = [
                author.find("atom:name", ns).text
                for author in entry.findall("atom:author", ns)
                if author.find("atom:name", ns) is not None
            ]

            # Extract categories/tags
            tags = [
                cat.get("term")
                for cat in entry.findall("atom:category", ns)
                if cat.get("term")
            ]

            if title_elem is not None and id_elem is not None:
                title = title_elem.text.strip().replace("\n", " ")
                summary = (
                    summary_elem.text.strip().replace("\n", " ")[:300] + "..."
                    if summary_elem is not None
                    else ""
                )
                published_str = published_elem.text if published_elem is not None else None
                published = (
                    datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    if published_str
                    else None
                )

                # Filter by date
                if published and published < cutoff:
                    continue

                # PDF link
                pdf_link = id_elem.text.replace("abs", "pdf")

                items.append(
                    NewsItem(
                        title=title,
                        url=pdf_link,
                        summary=summary,
                        source="arXiv",
                        published=published,
                        authors=authors[:3],  # Limit to 3 authors
                        tags=tags,
                    )
                )

        return items

    def _fetch_huggingface_papers(self) -> list[NewsItem]:
        """
        Fetch daily papers from Hugging Face.

        API: https://huggingface.co/api/daily_papers
        Free, no auth required.
        """
        url = "https://huggingface.co/api/daily_papers"
        try:
            response = self.client.get(url)
            response.raise_for_status()
            data = response.json()

            items: list[NewsItem] = []
            for paper in data[:10]:  # Limit to top 10
                title = paper.get("title", "")
                paper_id = paper.get("paper", {}).get("id", "")
                summary = paper.get("paper", {}).get("summary", "")[:300] + "..."
                authors_data = paper.get("paper", {}).get("authors", [])
                authors = [a.get("name", "") for a in authors_data if a.get("name")]

                # Hugging Face papers URL
                hf_url = f"https://huggingface.co/papers/{paper_id}"

                # Published date (if available)
                published_str = paper.get("publishedAt")
                published = (
                    datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    if published_str
                    else None
                )

                items.append(
                    NewsItem(
                        title=title,
                        url=hf_url,
                        summary=summary,
                        source="Hugging Face",
                        published=published,
                        authors=authors[:3],
                        tags=["research", "paper"],
                    )
                )

            return items
        except Exception:
            log.exception("Hugging Face papers API failed")
            return []

    # -------------------------------------------------------------------------
    # NEWS SOURCES (Blogs, RSS Feeds)
    # -------------------------------------------------------------------------

    def _fetch_news(self) -> list[NewsItem]:
        """Fetch AI news from blogs and RSS feeds."""
        items: list[NewsItem] = []

        # RSS Feeds (OpenAI, Google AI)
        # Note: Anthropic doesn't have a public RSS feed as of 2026
        rss_feeds = [
            ("https://openai.com/blog/rss.xml", "OpenAI Blog"),
            ("https://blog.google/technology/ai/rss/", "Google AI Blog"),
        ]

        for feed_url, source_name in rss_feeds:
            try:
                items.extend(self._fetch_rss(feed_url, source_name))
            except Exception:
                log.exception(f"RSS feed {source_name} failed")

        # Sort by recency, limit to 10
        items.sort(key=lambda x: x.published or datetime.min.replace(tzinfo=UTC), reverse=True)
        return items[:10]

    def _fetch_rss(self, feed_url: str, source_name: str) -> list[NewsItem]:
        """
        Parse RSS feed and extract recent items (last 7 days).

        Standard RSS 2.0 format.
        """
        cutoff = datetime.now(UTC) - timedelta(days=7)

        try:
            response = self.client.get(feed_url)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            items: list[NewsItem] = []
            for entry in root.findall(".//item"):
                title_elem = entry.find("title")
                link_elem = entry.find("link")
                desc_elem = entry.find("description")
                pub_elem = entry.find("pubDate")

                if title_elem is not None and link_elem is not None:
                    title = title_elem.text.strip() if title_elem.text else ""
                    url = link_elem.text.strip() if link_elem.text else ""
                    summary = desc_elem.text.strip()[:300] if desc_elem is not None else ""

                    # Parse pubDate (RFC 822 format: "Mon, 24 Mar 2026 12:00:00 GMT")
                    published = None
                    if pub_elem is not None and pub_elem.text:
                        try:
                            from email.utils import parsedate_to_datetime

                            published = parsedate_to_datetime(pub_elem.text)
                        except Exception:
                            pass

                    # Filter by date
                    if published and published < cutoff:
                        continue

                    items.append(
                        NewsItem(
                            title=title,
                            url=url,
                            summary=summary,
                            source=source_name,
                            published=published,
                            tags=["news", "blog"],
                        )
                    )

            return items
        except Exception:
            log.exception(f"RSS parsing failed for {source_name}")
            return []

    # -------------------------------------------------------------------------
    # DISCUSSIONS SOURCES (Hacker News, Reddit)
    # -------------------------------------------------------------------------

    def _fetch_discussions(self) -> list[NewsItem]:
        """Fetch high-quality discussions from HN and Reddit."""
        items: list[NewsItem] = []

        # Hacker News: AI-related stories with score > 100
        try:
            items.extend(self._fetch_hackernews())
        except Exception:
            log.exception("Hacker News fetch failed")

        # Reddit: r/MachineLearning, r/LocalLLaMA top posts
        try:
            items.extend(self._fetch_reddit())
        except Exception:
            log.exception("Reddit fetch failed")

        # Sort by score, limit to 10
        items.sort(key=lambda x: x.score or 0, reverse=True)
        return items[:10]

    def _fetch_hackernews(self, min_score: int = 100) -> list[NewsItem]:
        """
        Fetch Hacker News stories via Algolia API.

        API Docs: https://hn.algolia.com/api
        Free, no auth required.
        """
        # Search tags: story, AI/ML keywords, last 7 days
        query = "AI OR LLM OR machine learning OR GPT OR Claude OR neural"
        url = (
            f"https://hn.algolia.com/api/v1/search?"
            f"query={query}&"
            f"tags=story&"
            f"numericFilters=points>{min_score},created_at_i>{int((datetime.now(UTC) - timedelta(days=7)).timestamp())}"
        )

        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()

        items: list[NewsItem] = []
        for hit in data.get("hits", [])[:15]:
            title = hit.get("title", "")
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            external_url = hit.get("url", hn_url)
            score = hit.get("points", 0)
            num_comments = hit.get("num_comments", 0)

            # Published timestamp
            created_at = hit.get("created_at_i")
            published = (
                datetime.fromtimestamp(created_at, tz=UTC) if created_at else None
            )

            items.append(
                NewsItem(
                    title=title,
                    url=external_url,
                    summary=f"HN Discussion: {num_comments} comments",
                    source="Hacker News",
                    score=score,
                    published=published,
                    tags=["discussion", "community"],
                )
            )

        return items

    def _fetch_reddit(self) -> list[NewsItem]:
        """
        Fetch top posts from Reddit via JSON API (no auth needed for public data).

        Subreddits: r/MachineLearning, r/LocalLLaMA
        Time period: Last week
        """
        subreddits = ["MachineLearning", "LocalLLaMA"]
        items: list[NewsItem] = []

        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit=10"
            headers = {"User-Agent": "my-daily-newsletter/0.1"}

            try:
                response = self.client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                for post in data.get("data", {}).get("children", []):
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")
                    permalink = post_data.get("permalink", "")
                    reddit_url = f"https://www.reddit.com{permalink}"
                    score = post_data.get("score", 0)
                    num_comments = post_data.get("num_comments", 0)
                    created_utc = post_data.get("created_utc")

                    # Filter low-score posts
                    if score < 50:
                        continue

                    published = (
                        datetime.fromtimestamp(created_utc, tz=UTC) if created_utc else None
                    )

                    items.append(
                        NewsItem(
                            title=title,
                            url=reddit_url,
                            summary=f"r/{sub}: {num_comments} comments",
                            source=f"Reddit r/{sub}",
                            score=score,
                            published=published,
                            tags=["discussion", "reddit"],
                        )
                    )
            except Exception:
                log.exception(f"Reddit r/{sub} fetch failed")

        return items

    def close(self):
        """Close HTTP client."""
        self.client.close()
