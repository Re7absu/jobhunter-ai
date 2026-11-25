from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_automation_settings, get_current_user, get_profile
from app.core.database import SessionLocal, get_db
from app.models import Application, AutomationSettings, CandidateProfile, Company, Job, JobMatch, SearchHistory, User
from app.schemas import (
    CompanyOut,
    DiscoveryRunIn,
    JobDetail,
    JobOut,
    MatchOut,
    Page,
    RequirementOut,
    SearchHistoryOut,
)
from app.services.discovery.engine import configured_sources, run_discovery
from app.services.matching import analyze_job, analyze_pending

router = APIRouter(tags=["jobs & matching"])


def _job_out(job: Job, company: Company, match: JobMatch | None, app: Application | None) -> JobOut:
    o = JobOut.model_validate(job)
    o.company_name = company.name
    o.match_score = match.score if match else None
    o.match_category = match.category if match else None
    o.application_id = app.id if app else None
    o.application_status = app.status if app else None
    return o


def job_detail(db: Session, job: Job, user: User) -> JobDetail:
    match = db.scalar(select(JobMatch).where(JobMatch.job_id == job.id).order_by(JobMatch.created_at.desc()))
    app = db.scalar(select(Application).where(Application.job_id == job.id, Application.user_id == user.id))
    base = _job_out(job, job.company, match, app).model_dump()
    return JobDetail(**base, description=job.description, experience_text=job.experience_text,
                     requirements=[RequirementOut.model_validate(r) for r in job.requirements],
                     match=MatchOut.model_validate(match) if match else None,
                     company=CompanyOut.model_validate(job.company))


@router.get("/jobs", response_model=Page)
def list_jobs(q: str | None = None, city: str | None = None, category: str | None = None,
              level: str | None = None, min_score: int | None = None, match_category: str | None = None,
              active: bool | None = True, analyzed: bool | None = None, date_from: datetime | None = None,
              company_id: int | None = None, source: str | None = None, discovery_method: str | None = None,
              sort: str = "discovered",
              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (select(Job, Company, JobMatch, Application)
            .join(Company, Company.id == Job.company_id)
            .outerjoin(JobMatch, JobMatch.job_id == Job.id)
            .outerjoin(Application, (Application.job_id == Job.id) & (Application.user_id == user.id)))
    if q:
        stmt = stmt.where(or_(Job.title.ilike(f"%{q}%"), Company.name.ilike(f"%{q}%")))
    if city:
        stmt = stmt.where(Job.city == city)
    if category:
        stmt = stmt.where(Job.category == category)
    if level:
        stmt = stmt.where(Job.experience_level == level)
    if min_score is not None:
        stmt = stmt.where(JobMatch.score >= min_score)
    if match_category:
        stmt = stmt.where(JobMatch.category == match_category)
    if active is not None:
        stmt = stmt.where(Job.is_active.is_(active))
    if analyzed is not None:
        stmt = stmt.where(JobMatch.id.is_not(None) if analyzed else JobMatch.id.is_(None))
    if date_from:
        stmt = stmt.where(Job.discovered_at >= date_from)
    if company_id:
        stmt = stmt.where(Job.company_id == company_id)
    if source:
        stmt = stmt.where(Job.source == source)
    if discovery_method:
        # "ats_board" / "careers_page" match both the _auto and _manual variants
        stmt = stmt.where(Job.discovery_method.like(f"{discovery_method}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"score": JobMatch.score.desc().nullslast(), "posted": Job.posted_at.desc().nullslast()}.get(
        sort, Job.discovered_at.desc())
    rows = db.execute(stmt.order_by(order, Job.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[_job_out(j, c, m, a) for j, c, m, a in rows], total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job_detail(db, job, user)


@router.post("/jobs/{job_id}/analyze", response_model=MatchOut)
def analyze(job_id: int, profile: CandidateProfile = Depends(get_profile),
            settings: AutomationSettings = Depends(get_automation_settings), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if profile.active_cv_id is None:
        raise HTTPException(400, "Upload your CV first")
    return analyze_job(db, profile, job, settings.min_match_score, force=True)


@router.post("/matches/analyze-pending")
def analyze_all(limit: int = Query(30, ge=1, le=200), profile: CandidateProfile = Depends(get_profile),
                settings: AutomationSettings = Depends(get_automation_settings), db: Session = Depends(get_db)):
    if profile.active_cv_id is None:
        raise HTTPException(400, "Upload your CV first")
    matches = analyze_pending(db, profile, settings.min_match_score, limit)
    return {"analyzed": len(matches), "qualified": sum(1 for m in matches if m.should_apply)}


@router.get("/discovery/sources")
def sources(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    boards = db.execute(select(Company.ats_type, Company.tracking_source, func.count(Company.id))
                        .where(Company.tracked.is_(True)).group_by(Company.ats_type, Company.tracking_source)).all()
    jobs_by_source = dict(db.execute(select(Job.source, func.count(Job.id)).group_by(Job.source)).all())
    return {"configured": configured_sources(),
            "tracked_boards": [{"type": t, "tracking": tr, "count": n} for t, tr, n in boards],
            "jobs_by_source": jobs_by_source,
            "notes": {"jsearch": "RAPIDAPI_KEY - Google for Jobs aggregate (LinkedIn, GulfTalent, Jooble, Tanqeeb, ...)",
                      "serpapi": "SERPAPI_KEY - Google Jobs engine",
                      "ats": "Company boards on Greenhouse / Lever / Ashby / Workable / SmartRecruiters "
                             "(public APIs, no key; detected automatically from job links or added manually)",
                      "careers_page": "Company career pages (found during company research) with schema.org "
                                      "JobPosting data; robots.txt and crawl delays respected"}}


@router.post("/discovery/run")
def discovery_run(body: DiscoveryRunIn, background: BackgroundTasks, user: User = Depends(get_current_user),
                  settings: AutomationSettings = Depends(get_automation_settings)):
    if settings.paused:
        raise HTTPException(409, "Automation is paused")
    user_id = user.id

    def _bg():
        db = SessionLocal()
        try:
            s = db.scalar(select(AutomationSettings).where(AutomationSettings.user_id == user_id))
            run_discovery(db, user_id, s, titles=body.titles, cities=body.cities, max_queries=body.max_queries)
        finally:
            db.close()

    background.add_task(_bg)
    return {"started": True}


@router.get("/discovery/history", response_model=list[SearchHistoryOut])
def discovery_history(limit: int = Query(100, le=500), user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return db.scalars(select(SearchHistory).where(SearchHistory.user_id == user.id)
                      .order_by(SearchHistory.created_at.desc()).limit(limit)).all()
