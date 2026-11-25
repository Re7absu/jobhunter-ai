"""Company-owned job boards: public ATS APIs and schema.org JobPosting JSON-LD on career pages."""

import html
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.models import Company
from app.services.discovery.aggregators import _parse_iso
from app.services.discovery.ats_detect import detect_board, detect_from_urls
from app.services.discovery.base import RawJob, SourceError
from app.services.http_fetch import domain_of, polite_get
from app.services.keywords import detect_city

log = logging.getLogger(__name__)


def html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    soup = BeautifulSoup(html.unescape(value), "lxml")
    return soup.get_text("\n", strip=True)


def _get_json(url: str, method: str = "GET", **kw):
    try:
        r = httpx.request(method, url, timeout=30, headers={"User-Agent": settings.HTTP_USER_AGENT}, **kw)
    except httpx.HTTPError as e:
        raise SourceError(f"{url}: {e}") from e
    if r.status_code >= 400:
        raise SourceError(f"{url}: HTTP {r.status_code}")
    return r.json()


def greenhouse(company: Company) -> list[RawJob]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{company.ats_slug}/jobs?content=true")
    return [RawJob(
        title=j["title"], company_name=company.name, source="greenhouse", source_url=j["absolute_url"],
        application_url=j["absolute_url"], description=html_to_text(j.get("content")),
        location=(j.get("location") or {}).get("name"), city=detect_city((j.get("location") or {}).get("name")),
        posted_at=_parse_iso(j.get("updated_at")), external_id=str(j["id"]), company_website=company.website,
    ) for j in data.get("jobs", [])]


def lever(company: Company) -> list[RawJob]:
    data = _get_json(f"https://api.lever.co/v0/postings/{company.ats_slug}?mode=json")
    out = []
    for j in data:
        cats = j.get("categories") or {}
        created = (datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).replace(tzinfo=None)
                   if j.get("createdAt") else None)
        out.append(RawJob(
            title=j["text"], company_name=company.name, source="lever", source_url=j["hostedUrl"],
            application_url=j.get("applyUrl") or j["hostedUrl"], description=j.get("descriptionPlain"),
            location=cats.get("location"), city=detect_city(cats.get("location"), *(cats.get("allLocations") or [])),
            employment_type=cats.get("commitment"), posted_at=created, external_id=j["id"],
            company_website=company.website,
        ))
    return out


def ashby(company: Company) -> list[RawJob]:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{company.ats_slug}?includeCompensation=true")
    out = []
    for j in data.get("jobs", []):
        locs = [j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]
        out.append(RawJob(
            title=j["title"], company_name=company.name, source="ashby", source_url=j["jobUrl"],
            application_url=j.get("applyUrl") or j["jobUrl"],
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            location=j.get("location"), city=detect_city(*[x for x in locs if x]),
            employment_type=j.get("employmentType"), posted_at=_parse_iso(j.get("publishedAt")),
            external_id=j.get("id"), company_website=company.website,
            salary_text=((j.get("compensation") or {}).get("compensationTierSummary")),
        ))
    return out


def workable(company: Company) -> list[RawJob]:
    data = _get_json(f"https://apply.workable.com/api/v1/widget/accounts/{company.ats_slug}?details=true")
    out = []
    for j in data.get("jobs", []):
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
        out.append(RawJob(
            title=j["title"], company_name=company.name, source="workable", source_url=j["url"],
            application_url=j.get("application_url") or j["url"], description=html_to_text(j.get("description")),
            location=loc, city=detect_city(loc), employment_type=j.get("employment_type"),
            posted_at=_parse_iso(j.get("published_on")), external_id=j.get("shortcode"),
            company_website=company.website,
        ))
    return out


# ---------------------------------------------------------------- JSON-LD career pages
def _iter_jsonld(obj):
    if isinstance(obj, list):
        for o in obj:
            yield from _iter_jsonld(o)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            yield obj
        for key in ("@graph", "itemListElement", "item"):
            if key in obj:
                yield from _iter_jsonld(obj[key])


def extract_jobpostings(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        out.extend(_iter_jsonld(data))
    return out


def _jobposting_to_raw(jp: dict, page_url: str, company: Company) -> RawJob | None:
    title = jp.get("title")
    if not title:
        return None
    locs = jp.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    loc_texts = []
    for loc in locs:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, dict):
            loc_texts.append(", ".join(str(addr.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")
                                       if addr.get(k)))
        elif isinstance(addr, str):
            loc_texts.append(addr)
    salary = jp.get("baseSalary") or {}
    val = salary.get("value") if isinstance(salary, dict) else None
    ident = jp.get("identifier")
    ext_id = (ident.get("value") if isinstance(ident, dict) else ident) or None
    url = jp.get("url") or page_url
    return RawJob(
        title=title, company_name=((jp.get("hiringOrganization") or {}).get("name") if isinstance(jp.get("hiringOrganization"), dict) else None) or company.name,
        source="careers_page", source_url=urljoin(page_url, url), application_url=urljoin(page_url, url),
        description=html_to_text(jp.get("description")), location="; ".join(loc_texts) or None,
        city=detect_city(*loc_texts), employment_type=str(jp.get("employmentType") or "") or None,
        posted_at=_parse_iso(jp.get("datePosted")), external_id=str(ext_id) if ext_id else None,
        salary_min=(val or {}).get("minValue") if isinstance(val, dict) else None,
        salary_max=(val or {}).get("maxValue") if isinstance(val, dict) else None,
        salary_currency=salary.get("currency") if isinstance(salary, dict) else None,
        company_website=company.website,
    )


JOB_LINK_HINTS = ("/job", "/jobs/", "/careers/", "/career/", "/vacanc", "/position", "/opening", "وظائف")


SR_API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
SR_MAX_DETAILS = 40  # detail calls per company per scan (only for relevant postings)


def smartrecruiters(company: Company) -> list[RawJob]:
    """SmartRecruiters public Posting API (documented, no key): list Saudi postings, then fetch details
    only for postings in Riyadh/Jeddah whose title is in the target categories."""
    from app.services.keywords import classify_category

    slug = company.ats_slug
    postings: list[dict] = []
    offset = 0
    while offset < 500:
        data = _get_json(SR_API.format(slug=slug), params={"limit": 100, "offset": offset, "country": "sa"})
        content = data.get("content") or []
        postings += content
        if len(content) < 100 or offset + 100 >= (data.get("totalFound") or 0):
            break
        offset += 100
        time.sleep(0.5)
    out: list[RawJob] = []
    details = 0
    for p in postings:
        loc = p.get("location") or {}
        city = detect_city(loc.get("city"), loc.get("region"), loc.get("fullLocation"))
        if city is None or classify_category(p.get("name") or "") is None or details >= SR_MAX_DETAILS:
            continue
        details += 1
        time.sleep(0.3)
        try:
            d = _get_json(f"{SR_API.format(slug=slug)}/{p['id']}")
        except SourceError as e:
            log.warning("SmartRecruiters detail failed for %s/%s: %s", slug, p.get("id"), e)
            continue
        sections = ((d.get("jobAd") or {}).get("sections") or {})
        desc = "\n\n".join(filter(None, (html_to_text((sections.get(k) or {}).get("text"))
                                         for k in ("jobDescription", "qualifications", "additionalInformation"))))
        url = d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{p['id']}"
        level = (p.get("experienceLevel") or {}).get("label")
        out.append(RawJob(
            title=p["name"], company_name=company.name, source="smartrecruiters", source_url=url,
            application_url=d.get("applyUrl") or url,
            description=(f"Experience level: {level}\n\n" if level else "") + (desc or ""),
            location=loc.get("fullLocation"), city=city,
            employment_type=(p.get("typeOfEmployment") or {}).get("label"),
            posted_at=_parse_iso(p.get("releasedDate")), external_id=str(p["id"]),
            company_website=company.website,
            raw={"department": (p.get("department") or {}).get("label"), "function": (p.get("function") or {}).get("label")},
        ))
    return out


def find_board_links(page_html: str, page_url: str) -> tuple[str, str, str] | None:
    """Look for links/iframes on a careers page that point to a supported ATS board."""
    soup = BeautifulSoup(page_html, "lxml")
    urls = [urljoin(page_url, t.get("href") or t.get("src") or "")
            for t in soup.find_all(["a", "iframe", "script"]) if t.get("href") or t.get("src")]
    return detect_from_urls(urls)


def careers_page(company: Company, max_links: int = 15) -> list[RawJob]:
    if not company.careers_url:
        return []
    resp = polite_get(company.careers_url)
    if resp is None or resp.status_code >= 400:
        raise SourceError(f"Careers page not accessible (blocked by robots.txt, login or HTTP error): {company.careers_url}")
    page_url = str(resp.url)
    # Many company career pages embed or link to an ATS board: use its official API instead of the HTML.
    board = detect_board(page_url) or (find_board_links(resp.text, page_url) or (None, None, None))[:2]
    if board and board[0]:
        company.ats_type, company.ats_slug = board
        company.board_detected_from = page_url[:500]
        log.info("careers page of %s uses %s board '%s'", company.name, *board)
        return ATS_FETCHERS[board[0]](company)
    found = [_jobposting_to_raw(jp, page_url, company) for jp in extract_jobpostings(resp.text)]
    # Follow same-site job detail links and read their JSON-LD
    if len(found) < 3:
        soup = BeautifulSoup(resp.text, "lxml")
        base_domain = domain_of(page_url)
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(page_url, a["href"])
            if domain_of(href) == base_domain and any(h in href.lower() for h in JOB_LINK_HINTS) and href != page_url:
                if href not in links:
                    links.append(href)
        for href in links[:max_links]:
            r = polite_get(href)
            if r is not None and r.status_code < 400:
                found += [_jobposting_to_raw(jp, str(r.url), company) for jp in extract_jobpostings(r.text)]
    return [f for f in found if f]


ATS_FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workable": workable,
                "smartrecruiters": smartrecruiters, "careers_page": careers_page}
ATS_TYPES = tuple(k for k in ATS_FETCHERS if k != "careers_page")


def fetch_company_board(company: Company) -> list[RawJob]:
    fetcher = ATS_FETCHERS.get(company.ats_type or "")
    if not fetcher:
        raise SourceError(f"Unknown ATS type: {company.ats_type}")
    if company.ats_type != "careers_page" and not company.ats_slug:
        raise SourceError("ATS slug is required")
    jobs = fetcher(company)
    for j in jobs:
        j.company_id = company.id  # never re-resolve the employer by name for its own board
    return jobs
