"""Validate, normalize, deduplicate and persist discovered jobs and companies."""

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import Application, AutomationSettings, Company, Job, JobRequirement
from app.models.enums import ApplicationStatus
from app.services.applications import record_status
from app.services.discovery.ats_detect import detect_from_urls
from app.services.discovery.base import RawJob
from app.services.http_fetch import domain_of, is_job_board
from app.services.keywords import (
    classify_category,
    detect_city,
    detect_experience_level,
    normalize_company_name,
    normalize_title,
    parse_min_years,
    role_family,
)
from app.services.skills import extract_skills

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    job: Job | None
    new_job: bool = False
    new_company: bool = False
    new_board: bool = False
    skipped_reason: str | None = None


def _valid_url(url: str | None) -> bool:
    return bool(url) and bool(re.match(r"^https?://[^\s/$.?#].[^\s]*$", url or ""))


_TRACKING_PARAMS = re.compile(r"^(utm_.*|gh_src|lever-source|lever-origin|ref|refid|trk|trackingid|src|source|"
                              r"oga|fbclid|gclid|mc_cid|mc_eid)$", re.I)


def normalize_url(url: str) -> str:
    """Canonical form for de-duplication: drop fragments and marketing/tracking query params only."""
    p = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING_PARAMS.match(k)])
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


SEARCH_SOURCES = {"jsearch", "serpapi"}


def discovery_method_for(source: str, company: Company | None) -> str:
    if source in SEARCH_SOURCES:
        return "search_api"
    how = "auto" if company is not None and company.tracking_source == "auto" else "manual"
    return f"careers_page_{how}" if source == "careers_page" else f"ats_board_{how}"


def _raw_links(raw: RawJob) -> list[str]:
    links = [raw.application_url, raw.source_url]
    for o in (raw.raw or {}).get("apply_options") or []:
        if isinstance(o, dict):
            links.append(o.get("apply_link") or o.get("link"))
    return [u for u in links if u]


def register_board(company: Company, raw: RawJob) -> bool:
    """If a job link points into a supported ATS board, start tracking that company's board automatically."""
    if company.ats_type and company.ats_type != "careers_page":
        return False
    hit = detect_from_urls(_raw_links(raw))
    if not hit:
        return False
    company.ats_type, company.ats_slug, company.board_detected_from = hit[0], hit[1][:255], hit[2][:500]
    if not company.tracked:
        company.tracked, company.tracking_source = True, "auto"
    log.info("auto-detected %s board '%s' for %s", hit[0], hit[1], company.name)
    return True


def _note_sighting(job: Job, raw: RawJob) -> None:
    """Remember that the same job was also found on another source (original source is kept)."""
    url = raw.source_url[:1000]
    if url == job.source_url or any(s.get("url") == url for s in job.seen_sources or []):
        return
    job.seen_sources = [*(job.seen_sources or []), {"source": raw.source, "publisher": raw.publisher, "url": url,
                                                    "at": utcnow().isoformat(timespec="seconds")}][-10:]
    if raw.description and len(raw.description) > len(job.description or "") + 200:
        job.description = raw.description  # keep the most complete description
    if not job.salary_text and raw.salary_text:
        job.salary_text = raw.salary_text[:255]


def find_or_create_company(db: Session, raw: RawJob) -> tuple[Company, bool]:
    if raw.company_id:
        known = db.get(Company, raw.company_id)
        if known is not None:
            return known, False
    website_domain = domain_of(raw.company_website) if raw.company_website else None
    if website_domain and is_job_board(website_domain):
        website_domain = None
    if not website_domain and raw.application_url and not is_job_board(raw.application_url):
        website_domain = domain_of(raw.application_url)  # direct apply link on the company's own site
    norm = normalize_company_name(raw.company_name)

    company = None
    if website_domain:
        company = db.scalar(select(Company).where(Company.domain == website_domain))
    if company is None:
        company = db.scalar(select(Company).where(Company.normalized_name == norm))
    created = False
    if company is None:
        company = Company(name=raw.company_name.strip()[:255], normalized_name=norm, source=raw.source,
                          city=raw.city)
        db.add(company)
        created = True
    if website_domain and not company.domain:
        clash = db.scalar(select(Company).where(Company.domain == website_domain))
        if clash is None or clash.id == company.id:
            company.domain = website_domain
            company.website = company.website or f"https://{website_domain}"
    if raw.company_website and not company.website and not is_job_board(raw.company_website):
        company.website = raw.company_website
    if raw.company_linkedin and not company.linkedin_url:
        company.linkedin_url = raw.company_linkedin
    if raw.company_logo and not company.logo_url:
        company.logo_url = raw.company_logo[:500]
    if raw.city and not company.city:
        company.city = raw.city
    db.flush()
    return company, created


def ingest_raw_job(db: Session, raw: RawJob, user_id: int, settings: AutomationSettings) -> IngestResult:
    # ---- validation & normalization
    raw.title = re.sub(r"\s+", " ", raw.title or "").strip()
    raw.company_name = re.sub(r"\s+", " ", raw.company_name or "").strip()
    if not raw.title or not raw.company_name:
        return IngestResult(None, skipped_reason="missing title/company")
    if not _valid_url(raw.source_url):
        return IngestResult(None, skipped_reason="invalid source url")
    raw.source_url = normalize_url(raw.source_url)
    if raw.application_url and _valid_url(raw.application_url):
        raw.application_url = normalize_url(raw.application_url)
    raw.city = raw.city or detect_city(raw.location, raw.title)
    if raw.city not in (settings.preferred_cities or []):
        return IngestResult(None, skipped_reason=f"city not preferred ({raw.location})")

    # ---- company board auto-detection (even if this particular job is filtered out below:
    #      a Riyadh/Jeddah company on a public ATS usually has other relevant openings)
    new_board = new_company = False
    if raw.source in SEARCH_SOURCES and detect_from_urls(_raw_links(raw)):
        board_company, new_company = find_or_create_company(db, raw)
        new_board = register_board(board_company, raw)

    category = classify_category(raw.title, raw.description or "")
    def skip(reason: str) -> IngestResult:
        return IngestResult(None, new_company=new_company, new_board=new_board, skipped_reason=reason)

    if category is None or category not in (settings.job_categories or []):
        return skip("outside target categories")
    min_years, exp_text = parse_min_years(raw.description)
    if min_years is None and raw.experience_months:
        min_years = round(raw.experience_months / 12, 1)
    level = detect_experience_level(raw.title, raw.description or "", min_years, raw.employment_type)
    if level not in (settings.experience_levels or []):
        return skip(f"experience level {level} not selected")
    if raw.posted_at and raw.posted_at < utcnow() - timedelta(days=settings.job_max_age_days):
        return skip("posting too old")

    # ---- dedupe 1: same (normalized) URL or same source + source job id
    existing = db.scalar(select(Job).where(Job.source_url == raw.source_url[:1000]))
    if existing is None and raw.external_id:
        existing = db.scalar(select(Job).where(Job.source == raw.source, Job.external_id == raw.external_id[:255]))
    if existing is None and raw.application_url:
        # an aggregator's apply link often IS the company board URL (and vice versa)
        existing = db.scalar(select(Job).where(Job.source_url == raw.application_url[:1000]))
    if existing:
        existing.last_verified_at = utcnow()
        existing.is_active = True
        _note_sighting(existing, raw)
        return IngestResult(existing, new_company=new_company, new_board=new_board, skipped_reason="duplicate")

    company, created = find_or_create_company(db, raw)
    new_company = new_company or created
    norm_title = normalize_title(raw.title)[:255]
    # ---- dedupe 2: same company + normalized title + city within 30 days (same job on another board)
    dup = db.scalar(select(Job).where(
        Job.company_id == company.id, Job.normalized_title == norm_title, Job.city == raw.city,
        Job.discovered_at >= utcnow() - timedelta(days=30),
    ))
    if dup:
        if not dup.application_url and raw.application_url:
            dup.application_url = raw.application_url[:1000]
        dup.last_verified_at = utcnow()
        _note_sighting(dup, raw)
        return IngestResult(dup, new_company=new_company, new_board=new_board,
                            skipped_reason="duplicate (other board)")

    job = Job(
        company_id=company.id, title=raw.title[:255], normalized_title=norm_title, category=category,
        role_family=role_family(raw.title), city=raw.city, location_raw=(raw.location or "")[:255] or None,
        description=raw.description, employment_type=(raw.employment_type or "")[:50] or None,
        experience_level=level, experience_min_years=min_years, experience_text=exp_text,
        salary_text=(raw.salary_text or "")[:255] or None, salary_min=raw.salary_min, salary_max=raw.salary_max,
        salary_currency=raw.salary_currency, posted_at=raw.posted_at,
        application_url=(raw.application_url or raw.source_url)[:1000], source=raw.source,
        publisher=(raw.publisher or "")[:100] or None, source_url=raw.source_url[:1000],
        external_id=(raw.external_id or "")[:255] or None, language=raw.language, raw=raw.raw or None,
        discovery_method=discovery_method_for(raw.source, company), seen_sources=[],
        last_verified_at=utcnow(),
    )
    db.add(job)
    db.flush()
    for skill in extract_skills(f"{raw.title}\n{raw.description or ''}"):
        db.add(JobRequirement(job_id=job.id, requirement_type="skill", name=skill, normalized_name=skill.lower()))
    if exp_text:
        db.add(JobRequirement(job_id=job.id, requirement_type="experience", name=exp_text[:255],
                              normalized_name=f"{min_years or 0} years"))

    app = Application(user_id=user_id, job_id=job.id, company_id=company.id, status=ApplicationStatus.DISCOVERED)
    db.add(app)
    db.flush()
    record_status(db, app, None, ApplicationStatus.DISCOVERED, "system",
                  f"Discovered via {raw.source} ({job.discovery_method})")
    return IngestResult(job, new_job=True, new_company=new_company, new_board=new_board)
