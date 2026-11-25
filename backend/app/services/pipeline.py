"""Daily automation workflow.

It discovers, analyzes, drafts and queues. It never sends an email or submits an application:
those happen only through the user's explicit per-application actions.
"""

import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, utcnow
from app.models import Application, AutomationRun, AutomationSettings, Company, JobMatch, User
from app.models.enums import ApplicationStatus
from app.services.analytics import build_daily_report
from app.services.applications import choose_method
from app.services.audit import audit
from app.services.discovery.engine import run_discovery, scan_company_boards, validate_jobs
from app.services.email_writer import generate_email
from app.services.enrichment import enrich_company
from app.services.matching import analyze_pending
from app.services.workflow import check_replies, refresh_followups

log = logging.getLogger(__name__)
_lock = threading.Lock()


def get_settings(db: Session, user: User) -> AutomationSettings:
    s = db.scalar(select(AutomationSettings).where(AutomationSettings.user_id == user.id))
    if s is None:
        s = AutomationSettings(user_id=user.id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def is_running() -> bool:
    return _lock.locked()


def run_pipeline(db: Session, user: User, trigger: str = "manual") -> AutomationRun:
    settings = get_settings(db, user)
    run = AutomationRun(user_id=user.id, trigger=trigger, stats={}, log=[])
    db.add(run)
    db.commit()

    def step(name: str, msg: str | None = None):
        run.current_step = name
        run.log = [*(run.log or []), {"at": utcnow().isoformat(timespec="seconds"), "step": name, "msg": msg}]
        db.commit()

    if settings.paused:
        run.status, run.finished_at = "skipped", utcnow()
        step("paused", "Automation is paused")
        return run
    if not _lock.acquire(blocking=False):
        run.status, run.finished_at = "skipped", utcnow()
        step("busy", "Another run is in progress")
        return run
    stats: dict = {}
    try:
        profile = user.profile
        # 1-5: search, discover companies, collect info, validate, dedupe (dedupe happens at ingest)
        if settings.auto_discovery or trigger == "manual":
            step("discover", "Searching job sources")
            d = run_discovery(db, user.id, settings, run_id=run.id, include_boards=False)
            stats["discovery"] = d.as_dict()
        step("enrich", "Collecting company information")
        to_enrich = db.scalars(select(Company).where(Company.last_enriched_at.is_(None)).limit(25)).all()
        for c in to_enrich:
            try:
                enrich_company(db, c)
            except Exception as e:  # never stop the pipeline for one company
                db.rollback()
                c.last_enriched_at, c.enrichment_error = utcnow(), str(e)[:500]
                db.commit()
        stats["companies_enriched"] = len(to_enrich)
        # Company boards: ATS boards detected from job links + career pages found during company research
        if settings.auto_discovery or trigger == "manual":
            step("boards", "Scanning company job boards and career pages")
            b = scan_company_boards(db, user.id, settings, run_id=run.id)
            stats["company_boards"] = b.as_dict()
        step("validate", "Checking job availability")
        stats["validation"] = validate_jobs(db, settings)

        if profile is None or profile.active_cv_id is None:
            step("analyze", "Skipped: upload your CV first")
            stats["note"] = "No CV profile yet — matching and email generation skipped"
        else:
            # 6: analyze
            step("analyze", "Matching jobs against your CV")
            matches = analyze_pending(db, profile, settings.min_match_score, settings.max_jobs_to_analyze_per_run)
            stats["analyzed"] = len(matches)
            stats["qualified"] = sum(1 for m in matches if m.should_apply)
            # 7-8: generate emails → approval queue
            generated = 0
            if settings.auto_generate_emails:
                step("emails", "Generating personalized emails")
                apps = db.scalars(
                    select(Application).join(JobMatch, JobMatch.id == Application.match_id).where(
                        Application.user_id == user.id, Application.status == ApplicationStatus.ANALYZED,
                        JobMatch.score >= settings.min_match_score, JobMatch.should_apply.is_(True))
                    .order_by(JobMatch.score.desc()).limit(settings.max_daily_applications * 3)).all()
                for app in apps:
                    app.method = choose_method(app)
                    if app.method is None:
                        continue
                    generate_email(db, app, profile)
                    generated += 1
            stats["emails_generated"] = generated
            # 9: NOTHING is sent by automation. Every email is sent only by the user's own
            #    "Send now" action for that specific, reviewed and approved application.
            step("followups", "Checking replies and drafting follow-ups (not sent)")
            stats["replies"] = check_replies(db, user)
            stats["followups_due"] = refresh_followups(db, user)
        # 10-11: dashboard is live; generate daily report
        step("report", "Generating daily report")
        build_daily_report(db, user.id, run_stats={"run_id": run.id, **{k: v for k, v in stats.items() if k not in ("discovery", "company_boards")},
                                                   "new_jobs": (stats.get("discovery") or {}).get("new_jobs", 0)
                                                   + (stats.get("company_boards") or {}).get("new_jobs", 0)})
        run.status = "completed"
        settings.last_run_at = utcnow()
        audit(db, user.id, "automation.run", "automation_run", run.id, {"trigger": trigger})
    except Exception as e:
        log.exception("pipeline failed")
        db.rollback()
        run.status, run.error = "failed", f"{type(e).__name__}: {e}"[:2000]
    finally:
        run.stats = stats
        run.finished_at = utcnow()
        run.current_step = None
        db.commit()
        _lock.release()
    return run


def run_pipeline_in_background(user_id: int, trigger: str = "manual") -> None:
    def _target():
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if user:
                run_pipeline(db, user, trigger)
        finally:
            db.close()

    threading.Thread(target=_target, name=f"pipeline-{user_id}", daemon=True).start()
