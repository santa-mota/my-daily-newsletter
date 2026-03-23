"""
Heuristic classification of free-text WhatsApp commands.

Swap this module for an LLM-based interpreter when you need richer semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ClassifiedPreference:
    kind: str
    raw_text: str
    expires_at: datetime | None


_TOMORROW = re.compile(
    r"(?i)(for\s+)?tomorrow|next\s+digest|tonight\s+prep\s+for\s+tomorrow",
)
_MULTI_DAY = re.compile(
    r"(?i)(next\s+few\s+days|couple\s+of\s+days|this\s+week|for\s+a\s+while)",
)


def classify_message(text: str) -> ClassifiedPreference:
    """
    Map user text to a `PreferenceEntry.kind` and optional expiry.

    * **tomorrow_override** — strongest signal: user wants extra topics soon.
    * **multi_day** — sustained emphasis / de-emphasis for several days.
    * **other** — still stored; digest prompt may treat as soft hints.
    """
    t = text.strip()
    if not t:
        return ClassifiedPreference(kind="other", raw_text=t, expires_at=None)

    if _TOMORROW.search(t):
        # Expire “tomorrow boost” after ~36h so it does not linger.
        return ClassifiedPreference(
            kind="tomorrow_override",
            raw_text=t,
            expires_at=datetime.now(UTC) + timedelta(hours=36),
        )

    if _MULTI_DAY.search(t):
        return ClassifiedPreference(
            kind="multi_day",
            raw_text=t,
            expires_at=datetime.now(UTC) + timedelta(days=5),
        )

    return ClassifiedPreference(kind="other", raw_text=t, expires_at=None)
