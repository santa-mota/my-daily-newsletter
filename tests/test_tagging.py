"""
Tests for tagging and retrieval functionality.

Tests cover:
- Tag extraction from digest items
- Saving links from WhatsApp reactions
- Saving links via API
- Searching by tags, text, and date
"""

import pytest
from datetime import UTC, datetime, timedelta

from newsletter.db.base import get_session_factory, init_db
from newsletter.db.models import OutgoingMessage, SavedLink
from newsletter.services.tagging import (
    extract_tags_from_digest_item,
    format_saved_links_for_display,
    save_link_from_api,
    save_link_from_reaction,
    search_saved_links_by_date,
    search_saved_links_by_tags,
    search_saved_links_by_text,
)


@pytest.fixture
def db_session():
    """Create a test database session."""
    init_db()
    SessionLocal = get_session_factory()
    session = SessionLocal()
    yield session
    # Clean up all saved links after each test
    session.query(SavedLink).delete()
    session.query(OutgoingMessage).delete()
    session.commit()
    session.close()


def test_extract_tags_from_digest_item():
    """Test tag extraction from digest item."""
    item = {
        "title": "New RAG technique",
        "url": "https://arxiv.org/abs/2401.12345",
        "why_it_matters_one_line": "Novel approach to RAG with 2x speedup",
        "tags": ["RAG", "retrieval", "transformers"],
    }

    tags, summary = extract_tags_from_digest_item(item)

    assert tags == ["RAG", "retrieval", "transformers"]
    assert summary == "Novel approach to RAG with 2x speedup"


def test_save_link_from_reaction(db_session):
    """Test saving a link from WhatsApp reaction."""
    # Create outgoing message
    msg = OutgoingMessage(
        whatsapp_wamid="wamid123",
        url="https://example.com",
        title="Test Article",
        tags=["AI", "GPT-5"],
        context_summary="Important AI news",
    )
    db_session.add(msg)
    db_session.commit()

    # Save link from reaction
    saved = save_link_from_reaction(
        db=db_session,
        whatsapp_wamid="wamid123",
        reaction_emoji="👍",
    )

    assert saved is not None
    assert saved.url == "https://example.com"
    assert saved.title == "Test Article"
    assert saved.tags == ["AI", "GPT-5"]
    assert saved.context_summary == "Important AI news"
    assert saved.reaction_emoji == "👍"


def test_save_link_from_reaction_not_found(db_session):
    """Test saving a link from reaction when message not found."""
    saved = save_link_from_reaction(
        db=db_session,
        whatsapp_wamid="nonexistent",
        reaction_emoji="👍",
    )

    assert saved is None


def test_save_link_from_api(db_session):
    """Test saving a link via API."""
    saved = save_link_from_api(
        db=db_session,
        url="https://arxiv.org/abs/2401.67890",
        title="Research Paper",
        tags=["RAG", "transformers"],
        context_summary="Novel RAG technique",
    )

    assert saved.url == "https://arxiv.org/abs/2401.67890"
    assert saved.title == "Research Paper"
    assert saved.tags == ["RAG", "transformers"]
    assert saved.context_summary == "Novel RAG technique"


def test_save_link_from_api_duplicate(db_session):
    """Test saving duplicate link via API."""
    # Save first time
    saved1 = save_link_from_api(
        db=db_session,
        url="https://example.com/article",
        title="Article",
    )

    # Save again (should return existing)
    saved2 = save_link_from_api(
        db=db_session,
        url="https://example.com/article",
        title="Article Updated",
    )

    assert saved1.id == saved2.id


def test_search_by_tags(db_session):
    """Test searching saved links by tags."""
    # Create test links
    save_link_from_api(
        db=db_session,
        url="https://example.com/rag1",
        title="RAG Paper 1",
        tags=["RAG", "retrieval"],
    )
    save_link_from_api(
        db=db_session,
        url="https://example.com/gpt5",
        title="GPT-5 News",
        tags=["GPT-5", "LLM"],
    )
    save_link_from_api(
        db=db_session,
        url="https://example.com/rag2",
        title="RAG Paper 2",
        tags=["RAG", "transformers"],
    )

    # Search by RAG tag
    results = search_saved_links_by_tags(db_session, ["RAG"])
    assert len(results) == 2
    assert all("RAG" in link.tags for link in results)

    # Search by GPT-5 tag
    results = search_saved_links_by_tags(db_session, ["GPT-5"])
    assert len(results) == 1
    assert results[0].title == "GPT-5 News"

    # Case-insensitive search
    results = search_saved_links_by_tags(db_session, ["rag"])
    assert len(results) == 2


def test_search_by_text(db_session):
    """Test searching saved links by text."""
    # Create test links
    save_link_from_api(
        db=db_session,
        url="https://example.com/1",
        title="RAG Paper about retrieval",
        tags=["RAG"],
        context_summary="Novel approach to RAG",
    )
    save_link_from_api(
        db=db_session,
        url="https://example.com/2",
        title="GPT-5 Release",
        tags=["GPT-5"],
        context_summary="New model from OpenAI",
    )

    # Search by title
    results = search_saved_links_by_text(db_session, "RAG Paper")
    assert len(results) == 1
    assert results[0].title == "RAG Paper about retrieval"

    # Search by context summary
    results = search_saved_links_by_text(db_session, "OpenAI")
    assert len(results) == 1
    assert results[0].title == "GPT-5 Release"

    # Search by tag
    results = search_saved_links_by_text(db_session, "GPT-5")
    assert len(results) == 1

    # Case-insensitive search
    results = search_saved_links_by_text(db_session, "rag paper")
    assert len(results) == 1


def test_search_by_date(db_session):
    """Test searching saved links by date."""
    # Create link from 5 days ago
    old_link = SavedLink(
        url="https://example.com/old",
        title="Old Article",
        tags=["AI"],
        created_at=datetime.now(UTC) - timedelta(days=5),
    )
    db_session.add(old_link)

    # Create recent link
    recent_link = SavedLink(
        url="https://example.com/recent",
        title="Recent Article",
        tags=["AI"],
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(recent_link)
    db_session.commit()

    # Search last 3 days (should only get recent)
    results = search_saved_links_by_date(db_session, days_back=3)
    assert len(results) == 1
    assert results[0].title == "Recent Article"

    # Search last 7 days (should get both)
    results = search_saved_links_by_date(db_session, days_back=7)
    assert len(results) == 2


def test_format_saved_links_for_display():
    """Test formatting saved links for display."""
    links = [
        SavedLink(
            id=1,
            url="https://example.com/1",
            title="Article 1",
            tags=["AI", "RAG"],
            context_summary="Important paper",
            created_at=datetime.now(UTC),
            reaction_emoji="👍",
        ),
        SavedLink(
            id=2,
            url="https://example.com/2",
            title="Article 2",
            tags=["GPT-5"],
            created_at=datetime.now(UTC),
        ),
    ]

    formatted = format_saved_links_for_display(links)

    assert "Found 2 saved link(s)" in formatted
    assert "Article 1" in formatted
    assert "Article 2" in formatted
    assert "https://example.com/1" in formatted
    assert "AI, RAG" in formatted
    assert "GPT-5" in formatted
    assert "👍" in formatted
    assert "Important paper" in formatted


def test_format_empty_links():
    """Test formatting empty list."""
    formatted = format_saved_links_for_display([])
    assert formatted == "No saved links found."
