"""
APScheduler wiring for daily digest + optional follow-ups.

Run the API process on a server whose clock matches `DIGEST_TIMEZONE`, or adjust
cron to UTC and convert your desired local 8:30 into UTC offsets.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from newsletter.config import get_settings
from newsletter.db.base import get_session_factory
from newsletter.digest.delivery import deliver_digest
from newsletter.digest.agent_generator import generate_digest_with_agent
from newsletter.digest.generator import generate_digest  # Fallback for non-agent mode

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_digest_job() -> None:
    """
    Generate and send the digest; safe to call from cron or manual trigger.

    Uses agent-based generation (with tool calling) by default.
    """
    settings = get_settings()
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Use agent-based generator (agent decides which APIs to call)
        result = generate_digest_with_agent(db)
        deliver_digest(db, result)
        db.commit()
        log.info("Digest job completed (agent mode).")
    except Exception:
        log.exception("Digest job failed.")
        db.rollback()
    finally:
        db.close()


def maybe_ping_expiring_preferences() -> None:
    """
    Placeholder for the “still want news about X?” interactive loop.

    Implement by querying `PreferenceEntry` rows nearing `expires_at` and
    sending a short WhatsApp prompt.
    """
    to = get_settings().user_whatsapp_e164
    if not to:
        return
    # Intentionally minimal — extend with SQL against `preference_entries`.
    return


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    s = get_settings()
    tz = ZoneInfo(s.digest_timezone)
    sched = BackgroundScheduler(timezone=tz)

    sched.add_job(
        run_digest_job,
        CronTrigger(
            hour=s.digest_local_hour,
            minute=s.digest_local_minute,
            timezone=tz,
        ),
        id="daily_digest",
        replace_existing=True,
    )

    # Weekly nudge placeholder — tune or remove
    sched.add_job(
        maybe_ping_expiring_preferences,
        CronTrigger(day_of_week="sun", hour=10, minute=0, timezone=tz),
        id="preference_followup_ping",
        replace_existing=True,
    )

    sched.start()
    _scheduler = sched
    log.info(
        "Scheduler started: daily digest at %02d:%02d %s",
        s.digest_local_hour,
        s.digest_local_minute,
        s.digest_timezone,
    )
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
