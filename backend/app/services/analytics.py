"""KPIs, charts and daily reports."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import Application, Company, DailyReport, Job, JobMatch
from app.models.enums import PENDING_STATUSES, SUBMITTED_STATUSES, ApplicationStatus
from app.services.applications import LOCAL_OFFSET, day_bounds, local_now

SUBMITTED = [s.value for s in SUBMITTED_STATUSES]
RESPONDED = [ApplicationStatus.RESPONSE_RECEIVED.value, ApplicationStatus.INTERVIEW_SCHEDULED.value,
             ApplicationStatus.REJECTED.value]


def kpis(db: Session, user_id: int) -> dict:
    start, end = day_bounds()
    week_start = start - timedelta(days=(local_now().weekday() + 1) % 7)  # week starts Sunday (KSA)
    cnt = lambda *conds: db.scalar(select(func.count(Application.id)).where(Application.user_id == user_id, *conds)) or 0  # noqa: E731
    qualified = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.should_apply.is_(True))) or 0
    return {
        "total_companies": db.scalar(select(func.count(Company.id))) or 0,
        "total_jobs": db.scalar(select(func.count(Job.id))) or 0,
        "active_jobs": db.scalar(select(func.count(Job.id)).where(Job.is_active.is_(True))) or 0,
        "qualified_opportunities": qualified,
        "applications_today": cnt(Application.applied_at >= start, Application.applied_at < end),
        "applications_this_week": cnt(Application.applied_at >= week_start),
        "pending_applications": cnt(Application.status.in_([s.value for s in PENDING_STATUSES])),
        "awaiting_approval": cnt(Application.status == ApplicationStatus.AWAITING_APPROVAL),
        "responses_received": cnt(Application.response_at.is_not(None)),
        "interviews_scheduled": cnt(Application.status == ApplicationStatus.INTERVIEW_SCHEDULED),
        "total_applied": cnt(Application.applied_at.is_not(None)),
    }


def charts(db: Session, user_id: int, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(Application.applied_at, Job.city, Job.category, Application.status, Application.response_at,
               Application.company_id)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user_id, Application.applied_at.is_not(None))
    ).all()
    per_day: Counter = Counter()
    per_week: Counter = Counter()
    by_city: Counter = Counter()
    by_cat: Counter = Counter()
    companies = set()
    responded = interviews = 0
    for applied_at, city, cat, status, response_at, company_id in rows:
        local = applied_at + LOCAL_OFFSET
        if applied_at >= since:
            per_day[local.date().isoformat()] += 1
        iso = local.isocalendar()
        per_week[f"{iso.year}-W{iso.week:02d}"] += 1
        by_city[city or "Unknown"] += 1
        by_cat[cat or "other"] += 1
        companies.add(company_id)
        if response_at or status in RESPONDED:
            responded += 1
        if status == ApplicationStatus.INTERVIEW_SCHEDULED:
            interviews += 1
    total = len(rows)
    today = local_now().date()
    day_series = [{"date": (today - timedelta(days=i)).isoformat(),
                   "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)]
    avg = db.scalar(select(func.avg(JobMatch.score)))
    score_dist = defaultdict(int)
    for (score,) in db.execute(select(JobMatch.score)).all():
        bucket = "80-100" if score >= 80 else "65-79" if score >= 65 else "50-64" if score >= 50 else "0-49"
        score_dist[bucket] += 1
    status_counts = dict(db.execute(select(Application.status, func.count(Application.id))
                                    .where(Application.user_id == user_id).group_by(Application.status)).all())
    return {
        "applications_per_day": day_series,
        "applications_per_week": [{"week": k, "count": v} for k, v in sorted(per_week.items())][-12:],
        "applications_by_city": [{"city": k, "count": v} for k, v in by_city.most_common()],
        "applications_by_category": [{"category": k, "count": v} for k, v in by_cat.most_common()],
        "companies_contacted": len(companies),
        "response_rate": round(100 * responded / total, 1) if total else 0.0,
        "interview_rate": round(100 * interviews / total, 1) if total else 0.0,
        "average_match_score": round(float(avg), 1) if avg is not None else None,
        "match_score_distribution": [{"bucket": b, "count": score_dist.get(b, 0)} for b in ("0-49", "50-64", "65-79", "80-100")],
        "status_breakdown": [{"status": s.value, "count": status_counts.get(s.value, 0)} for s in ApplicationStatus],
    }


def contacted_on(db: Session, user_id: int, day: date) -> list[dict]:
    start, end = day_bounds(datetime.combine(day, datetime.min.time()))
    rows = db.execute(
        select(Application, Job, Company).join(Job, Job.id == Application.job_id)
        .join(Company, Company.id == Application.company_id)
        .where(Application.user_id == user_id, Application.applied_at >= start, Application.applied_at < end)
        .order_by(Application.applied_at)
    ).all()
    return [{"application_id": a.id, "company": c.name, "job_title": j.title, "city": j.city, "method": a.method,
             "recipient": a.recipient_email, "applied_at": (a.applied_at + LOCAL_OFFSET).isoformat(timespec="minutes"),
             "source_url": j.source_url} for a, j, c in rows]


def build_daily_report(db: Session, user_id: int, day: date | None = None, run_stats: dict | None = None) -> DailyReport:
    day = day or local_now().date()
    start, end = day_bounds(datetime.combine(day, datetime.min.time()))
    contacted = contacted_on(db, user_id, day)
    rep = db.scalar(select(DailyReport).where(DailyReport.user_id == user_id, DailyReport.report_date == day))
    if rep is None:
        rep = DailyReport(user_id=user_id, report_date=day)
        db.add(rep)
    rep.new_companies = db.scalar(select(func.count(Company.id)).where(Company.discovered_at >= start, Company.discovered_at < end)) or 0
    rep.new_jobs = db.scalar(select(func.count(Job.id)).where(Job.discovered_at >= start, Job.discovered_at < end)) or 0
    rep.jobs_analyzed = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.created_at >= start, JobMatch.created_at < end)) or 0
    rep.qualified = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.created_at >= start, JobMatch.created_at < end,
                                                                     JobMatch.should_apply.is_(True))) or 0
    from app.models import ApplicationEmail  # local import avoids cycles

    rep.emails_generated = db.scalar(select(func.count(ApplicationEmail.id)).join(Application).where(
        Application.user_id == user_id, ApplicationEmail.created_at >= start, ApplicationEmail.created_at < end)) or 0
    rep.applications_sent = len(contacted)
    rep.responses = db.scalar(select(func.count(Application.id)).where(
        Application.user_id == user_id, Application.response_at >= start, Application.response_at < end)) or 0
    rep.companies_contacted = contacted
    summary = dict(rep.summary or {})
    if run_stats:
        summary.setdefault("runs", []).append(run_stats)
        summary["runs"] = summary["runs"][-5:]
    rep.summary = summary
    rep.updated_at = utcnow()
    db.commit()
    db.refresh(rep)
    return rep
