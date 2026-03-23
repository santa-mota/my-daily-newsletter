"""Structured digest output — kept in sync with `prompts/daily_digest_system.md`."""

from pydantic import BaseModel, Field


class DigestItem(BaseModel):
    title: str
    url: str
    why_it_matters_one_line: str = Field(
        ...,
        description="Single scannable line; no paragraph.",
    )
    estimated_read_minutes: int = Field(ge=1, le=120)
    tags: list[str] = Field(default_factory=list)


class DigestSection(BaseModel):
    title: str
    summary_bullets: list[str] = Field(default_factory=list)
    items: list[DigestItem] = Field(default_factory=list)


class DigestResult(BaseModel):
    intro_markdown: str = Field(
        ...,
        description="At most 2–3 short paragraphs; no bare URL list here.",
    )
    sections: list[DigestSection] = Field(min_length=1)
    clarification_question: str | None = Field(
        default=None,
        description="If user prefs conflict or are unclear, ask one short question instead of guessing.",
    )
