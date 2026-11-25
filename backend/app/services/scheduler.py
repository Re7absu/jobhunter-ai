"""APScheduler: runs the daily pipeline per user at the configured frequency (Asia/Riyadh hours)."""

import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal, utcnow
from app.models import AutomationSettings, User
from app.services.applications import LOCAL_OFFSET
from app.services.pipeline import run_pipeline

log = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def _job_id(user_id: int) -> str:
    return f"pipeline-user-{user_id}"


def _run_for_user(user_id: int) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user and user.is_active:
            run_pipeline(db, user, trigger="scheduled")
    finally:
        db.close()


def _next_start(s: AutomationSettings):
    """Next occurrence of run_hour (Riyadh local time) expressed in naive UTC."""
    local_now = utcnow() + LOCAL_OFFSET
    start_local = local_now.replace(hour=s.run_hour % 24, minute=0, second=0, microsecond=0)
    if start_local <= local_now:
        start_local += timedelta(days=1)
    return start_local - LOCAL_OFFSET


def schedule_user(s: AutomationSettings) -> None:
    jid = _job_id(s.user_id)
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    if s.paused or not s.auto_discovery:
        log.info("automation disabled for user %s", s.user_id)
        return
    hours = max(1, s.search_frequency_hours)
    trigger = IntervalTrigger(hours=hours, start_date=_next_start(s), timezone="UTC")
    scheduler.add_job(_run_for_user, trigger, args=[s.user_id], id=jid, max_instances=1, coalesce=True,
                      misfire_grace_time=3600)
    log.info("scheduled pipeline for user %s every %sh", s.user_id, hours)


def next_run_time(user_id: int):
    job = scheduler.get_job(_job_id(user_id))
    return job.next_run_time if job else None


def start() -> None:
    if scheduler.running:
        return
    scheduler.start()
    db = SessionLocal()
    try:
        for s in db.query(AutomationSettings).all():
            schedule_user(s)
    finally:
        db.close()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
