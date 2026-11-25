"""Orchestrates discovery across all enabled sources with a per-run query budget."""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import AutomationSettings, Company, Job, SearchHistory
from app.services.discovery.aggregators import AGGREGATORS
from app.services.discovery.base import SearchQuery, SourceError
from app.services.discovery.company_boards import fetch_company_board
from app.services.discovery.ingest import ingest_raw_job
from app.services.http_fetch import fetch_allowed, polite_get
from app.services.keywords import titles_for

log = logging.getLogger(__name__)


@dataclass
class DiscoveryStats:
    queries: int = 0
    results: int = 0
    new_jobs: int = 0
    new_companies: int = 0
    duplicates: int = 0
    filtered: int = 0
    boards_detected: int = 0
    boards_scanned: int = 0
    errors: list[str] = field(default_factory=list)
    new_job_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["errors"] = self.errors[:20]
        d.pop("new_job_ids")
        return d


def configured_sources() -> dict[str, bool]:
    return {s.name: s.is_configured() for s in AGGREGATORS} | {"ats": True, "careers_page": True}


def build_query_plan(db: Session, user_id: int, settings: AutomationSettings,
                     titles: list[str] | None = None, cities: list[str] | None = None) -> list[SearchQuery]:
    cities = cities or settings.preferred_cities or []
    plan: list[SearchQuery] = []
    if titles:
        for t in titles:
            plan += [SearchQuery(t, c, "en") for c in cities]
    else:
        for en, ar, cat in titles_for(settings.job_categories or []):
            for c in cities:
                plan.append(SearchQuery(en, c, "en", cat))
                if settings.include_arabic_titles:
                    plan.append(SearchQuery(ar, c, "ar", cat))
        for custom in settings.custom_job_titles or []:
            plan += [SearchQuery(custom, c, "en") for c in cities]
    # Least-recently-searched first so the budget rotates through all titles over successive runs.
    last = dict(db.execute(
        select(SearchHistory.query, func.max(SearchHistory.created_at))
        .where(SearchHistory.user_id == user_id).group_by(SearchHistory.query)
    ).all())
    plan.sort(key=lambda q: (last.get(q.text) is not None, last.get(q.text) or utcnow()))
    return plan


def run_discovery(db: Session, user_id: int, settings: AutomationSettings, run_id: int | None = None,
                  titles: list[str] | None = None, cities: list[str] | None = None,
                  max_queries: int | None = None, include_boards: bool = True) -> DiscoveryStats:
    stats = DiscoveryStats()
    enabled = set(settings.sources_enabled or [])
    sources = [s for s in AGGREGATORS if s.name in enabled and s.is_configured()]
    budget = max_queries or settings.max_queries_per_run

    if sources:
        plan = build_query_plan(db, user_id, settings, titles, cities)
        per_source = max(1, budget // len(sources))
        for source in sources:
            for q in plan[:per_source]:
                _run_query(db, user_id, settings, run_id, source.name, q.text, q.city,
                           lambda q=q, s=source: s.search(q), stats)
    else:
        if not any(s.is_configured() for s in AGGREGATORS):
            stats.errors.append("No job-search API configured (set RAPIDAPI_KEY and/or SERPAPI_KEY)")

    if include_boards:
        scan_company_boards(db, user_id, settings, run_id, stats)
    return stats


BOARD_RESCAN_HOURS = 20


def scan_company_boards(db: Session, user_id: int, settings: AutomationSettings, run_id: int | None = None,
                        stats: DiscoveryStats | None = None, company_ids: list[int] | None = None) -> DiscoveryStats:
    """Scan tracked company boards (ATS APIs + career pages): manual ones first, then auto-detected ones,
    least-recently scanned first, each at most once per BOARD_RESCAN_HOURS, capped by max_boards_per_run."""
    stats = stats or DiscoveryStats()
    enabled = set(settings.sources_enabled or [])
    if not ({"ats", "careers_page"} & enabled):
        return stats
    stmt = select(Company).where(Company.tracked.is_(True), Company.ats_type.is_not(None))
    if company_ids:
        stmt = stmt.where(Company.id.in_(company_ids))
    else:
        stmt = stmt.where((Company.last_scanned_at.is_(None))
                          | (Company.last_scanned_at < utcnow() - timedelta(hours=BOARD_RESCAN_HOURS)))
    stmt = stmt.order_by((Company.tracking_source == "auto").asc(), Company.last_scanned_at.asc().nullsfirst())
    for company in db.scalars(stmt.limit(max(1, settings.max_boards_per_run))).all():
        kind = "careers_page" if company.ats_type == "careers_page" else "ats"
        if kind not in enabled:
            continue
        before = stats.new_jobs
        err_before = len(stats.errors)
        hist = _run_query(db, user_id, settings, run_id, company.ats_type, f"board:{company.name}", None,
                          lambda c=company: fetch_company_board(c), stats)
        stats.boards_scanned += 1
        company.last_scanned_at = utcnow()
        company.scan_error = stats.errors[-1][:2000] if len(stats.errors) > err_before else None
        # An auto-detected career page without structured job data yields nothing: stop re-crawling it.
        if (company.ats_type == "careers_page" and company.tracking_source == "auto"
                and hist.status == "ok" and hist.results_count == 0):
            company.tracked = False
            company.scan_error = "No machine-readable job postings (schema.org JobPosting) found on the careers page"
        log.info("board %s (%s:%s): +%d jobs", company.name, company.ats_type, company.ats_slug,
                 stats.new_jobs - before)
        db.commit()
    return stats


def _run_query(db, user_id, settings, run_id, source_name, query_text, city, fetch,
               stats: DiscoveryStats) -> SearchHistory:
    stats.queries += 1
    hist = SearchHistory(user_id=user_id, run_id=run_id, source=source_name, query=query_text[:500], city=city,
                         results_count=0, new_jobs_count=0, new_companies_count=0, status="ok")
    try:
        raws = fetch()
        hist.results_count = len(raws)
        stats.results += len(raws)
        for raw in raws:
            res = ingest_raw_job(db, raw, user_id, settings)
            if res.new_job:
                hist.new_jobs_count += 1
                stats.new_jobs += 1
                stats.new_job_ids.append(res.job.id)
            elif res.skipped_reason and res.skipped_reason.startswith("duplicate"):
                stats.duplicates += 1
            else:
                stats.filtered += 1
            if res.new_company:
                hist.new_companies_count += 1
                stats.new_companies += 1
            if res.new_board:
                stats.boards_detected += 1
    except SourceError as e:
        hist.status, hist.error = "error", str(e)[:2000]
        stats.errors.append(f"{source_name}: {e}")
        log.warning("source %s failed for %r: %s", source_name, query_text, e)
    except Exception as e:  # keep the run going; record the failure
        db.rollback()
        hist.status, hist.error = "error", f"{type(e).__name__}: {e}"[:2000]
        stats.errors.append(f"{source_name}: {type(e).__name__}: {e}")
        log.exception("unexpected discovery error")
    db.add(hist)
    db.commit()
    return hist


def validate_jobs(db: Session, settings: AutomationSettings, limit: int = 40) -> dict:
    """Mark stale postings inactive and verify reachable ones still exist (only where fetching is permitted)."""
    expired = 0
    cutoff = utcnow() - timedelta(days=max(settings.job_max_age_days, 7) + 15)
    for job in db.scalars(select(Job).where(Job.is_active.is_(True), func.coalesce(Job.posted_at, Job.discovered_at) < cutoff)):
        job.is_active = False
        expired += 1
    checked = closed = 0
    stale_cutoff = utcnow() - timedelta(days=3)
    candidates = db.scalars(select(Job).where(
        Job.is_active.is_(True), (Job.last_verified_at.is_(None)) | (Job.last_verified_at < stale_cutoff)
    ).limit(limit)).all()
    for job in candidates:
        url = job.application_url or job.source_url
        if not fetch_allowed(url):
            continue
        r = polite_get(url, timeout=10)
        checked += 1
        if r is not None and r.status_code in (404, 410):
            job.is_active = False
            closed += 1
        elif r is not None:
            job.last_verified_at = utcnow()
    db.commit()
    return {"expired": expired, "checked": checked, "closed": closed}
