"""Licensed job-search APIs that aggregate Google for Jobs (LinkedIn, Indeed, Bayt, GulfTalent, Naukrigulf, ...)."""

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.database import utcnow
from app.services.discovery.base import JobSource, RawJob, SearchQuery, SourceError
from app.services.keywords import detect_city

log = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_relative_date(text: str | None) -> datetime | None:
    """'3 days ago', 'منذ يومين', '1 hour ago' -> datetime."""
    if not text:
        return None
    t = text.lower()
    m = re.search(r"(\d+)\+?\s*(minute|hour|day|week|month)", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n), "day": timedelta(days=n),
                 "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
        return utcnow() - delta
    if "today" in t or "just" in t or "اليوم" in t:
        return utcnow()
    if "yesterday" in t or "أمس" in t:
        return utcnow() - timedelta(days=1)
    return None


def _jsearch_posted(j: dict) -> datetime | None:
    """JSearch gives an ISO date, a unix timestamp and/or a relative string ('3 days ago')."""
    if j.get("job_posted_at_datetime_utc"):
        return _parse_iso(j["job_posted_at_datetime_utc"])
    ts = j.get("job_posted_at_timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
    return parse_relative_date(j.get("job_posted_at"))


def _jsearch_salary(j: dict) -> str | None:
    for key in ("job_salary_string", "job_salary"):
        if isinstance(j.get(key), str) and j[key].strip():
            return j[key].strip()[:255]
    if j.get("job_min_salary"):
        return (f"{j['job_min_salary']}–{j.get('job_max_salary') or ''} {j.get('job_salary_currency') or ''} "
                f"/{j.get('job_salary_period') or ''}").strip()
    return None


class JSearchSource(JobSource):
    """https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"""

    name = "jsearch"

    def is_configured(self) -> bool:
        return bool(settings.RAPIDAPI_KEY)

    def search(self, query: SearchQuery) -> list[RawJob]:
        params = {"query": query.text, "page": "1", "num_pages": "1", "country": "sa", "date_posted": "week"}
        if query.language == "ar":
            params["language"] = "ar"
        try:
            r = httpx.get(f"https://{settings.JSEARCH_HOST}{settings.JSEARCH_PATH}", params=params, timeout=40,
                          headers={"X-RapidAPI-Key": settings.RAPIDAPI_KEY, "X-RapidAPI-Host": settings.JSEARCH_HOST})
        except httpx.HTTPError as e:
            raise SourceError(f"JSearch request failed: {e}") from e
        if r.status_code >= 400:
            raise SourceError(f"JSearch HTTP {r.status_code}: {r.text[:300]}")
        out: list[RawJob] = []
        data = r.json().get("data") or []
        jobs = data.get("jobs") or [] if isinstance(data, dict) else data  # /search-v2 nests jobs under data.jobs
        for j in jobs:
            if (j.get("job_country") or "SA").upper() not in ("SA", "SAUDI ARABIA"):
                continue
            apply_options = j.get("apply_options") or []
            direct = next((o.get("apply_link") for o in apply_options if o.get("is_direct")), None)
            apply_link = direct or j.get("job_apply_link")
            exp = j.get("job_required_experience") or {}
            out.append(RawJob(
                title=j.get("job_title") or "",
                company_name=j.get("employer_name") or "",
                company_website=j.get("employer_website"),
                company_logo=j.get("employer_logo"),
                source=self.name,
                source_url=j.get("job_apply_link") or j.get("job_google_link") or "",
                application_url=apply_link,
                publisher=j.get("job_publisher"),
                description=j.get("job_description"),
                location=", ".join(x for x in [j.get("job_city"), j.get("job_state"), j.get("job_country")] if x),
                city=detect_city(j.get("job_city"), j.get("job_state"), j.get("job_location")),
                employment_type=j.get("job_employment_type"),
                posted_at=_jsearch_posted(j),
                external_id=j.get("job_id"),
                salary_min=j.get("job_min_salary"),
                salary_max=j.get("job_max_salary"),
                salary_currency=j.get("job_salary_currency"),
                salary_text=_jsearch_salary(j),
                experience_months=exp.get("required_experience_in_months"),
                language=query.language,
                raw={"apply_options": apply_options[:5], "highlights": j.get("job_highlights")},
            ))
        return out


class SerpApiGoogleJobsSource(JobSource):
    """https://serpapi.com/google-jobs-api"""

    name = "serpapi"

    def is_configured(self) -> bool:
        return bool(settings.SERPAPI_KEY)

    def search(self, query: SearchQuery) -> list[RawJob]:
        params = {
            "engine": "google_jobs", "q": query.title, "location": f"{query.city}, Saudi Arabia",
            "hl": "ar" if query.language == "ar" else "en", "gl": "sa", "api_key": settings.SERPAPI_KEY,
        }
        try:
            r = httpx.get("https://serpapi.com/search.json", params=params, timeout=60)
        except httpx.HTTPError as e:
            raise SourceError(f"SerpAPI request failed: {e}") from e
        if r.status_code >= 400:
            raise SourceError(f"SerpAPI HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("error") and "hasn't returned any results" not in data["error"]:
            raise SourceError(f"SerpAPI: {data['error']}")
        out: list[RawJob] = []
        for j in data.get("jobs_results") or []:
            ext = j.get("detected_extensions") or {}
            apply_options = j.get("apply_options") or []
            link = apply_options[0]["link"] if apply_options else j.get("share_link")
            if not link:
                continue
            out.append(RawJob(
                title=j.get("title") or "",
                company_name=j.get("company_name") or "",
                company_logo=j.get("thumbnail"),
                source=self.name,
                source_url=link,
                application_url=link,
                publisher=(j.get("via") or "").replace("via ", "") or None,
                description=j.get("description"),
                location=j.get("location"),
                city=detect_city(j.get("location")) or query.city,
                employment_type=ext.get("schedule_type"),
                posted_at=parse_relative_date(ext.get("posted_at")),
                external_id=(j.get("job_id") or "")[:255] or None,
                salary_text=ext.get("salary"),
                language=query.language,
                raw={"apply_options": apply_options[:5], "highlights": j.get("job_highlights")},
            ))
        return out


AGGREGATORS: list[JobSource] = [JSearchSource(), SerpApiGoogleJobsSource()]
