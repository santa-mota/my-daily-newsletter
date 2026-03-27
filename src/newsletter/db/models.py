"""ORM models — kept small; extend as features grow."""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.db.base import Base


class PreferenceEntry(Base):
    """
    User-originated instructions affecting future digests.

    * `kind` distinguishes quick overrides vs longer-running tuning.
    * `payload` holds structured hints (e.g. {\"more\": [\"RAG\"], \"less\": [\"gaming\"]}) after NLP.
    """

    __tablename__ = "preference_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="tomorrow_override | multi_day | feedback_reply | other",
    )
    # When set, entry is ignored after this time (e.g. multi-day prefs expire)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional structured form once the interpreter fills it in
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SavedLink(Base):
    """A URL the user signaled interest in (e.g. WhatsApp reaction on a link message)."""

    __tablename__ = "saved_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    whatsapp_wamid: Mapped[str | None] = mapped_column(
        String(128), nullable=True, doc="WhatsApp message id for traceability"
    )
    reaction_emoji: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Tags for efficient retrieval (pre-generated during digest creation)
    tags: Mapped[list | None] = mapped_column(
        JSON, nullable=True, doc="List of topic tags: ['RAG', 'GPT-5', 'inference']"
    )
    # Short context summary for better recall
    context_summary: Mapped[str | None] = mapped_column(
        String(512), nullable=True, doc="One-line summary: 'New RAG technique for faster retrieval'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DigestRun(Base):
    """One generated digest (intro + items stored as JSON for audit)."""

    __tablename__ = "digest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intro_text: Mapped[str] = mapped_column(Text, nullable=False)
    items_json: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


class OutgoingMessage(Base):
    """
    Maps a WhatsApp server message id to the URL we sent, so reactions can bookmark the link.
    Tags are pre-generated during digest creation to avoid LLM calls on every save.
    """

    __tablename__ = "outgoing_messages"

    whatsapp_wamid: Mapped[str] = mapped_column(String(128), primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Pre-generated tags (created during digest, reused when saved)
    tags: Mapped[list | None] = mapped_column(
        JSON, nullable=True, doc="Pre-computed tags to avoid LLM calls on save"
    )
    context_summary: Mapped[str | None] = mapped_column(
        String(512), nullable=True, doc="Pre-computed summary for retrieval"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ClarificationThread(Base):
    """Open question to the user when intent is ambiguous (optional follow-up)."""

    __tablename__ = "clarification_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
