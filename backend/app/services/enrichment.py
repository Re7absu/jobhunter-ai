"""Company research from the company's own public website.

Recruitment emails are only accepted when they are (1) published on the company's own site,
(2) on the company's own domain, and (3) the domain has MX records. Nothing is guessed.
"""

import logging
import re
from urllib.parse import urljoin

import dns.exception
import dns.resolver
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import Company
from app.services.discovery.ats_detect import detect_board
from app.services.http_fetch import domain_of, is_job_board, polite_get
from app.services.keywords import detect_city
from app.services.llm import LLMError, get_llm

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RECRUIT_LOCALPARTS = ("careers", "career", "jobs", "job", "hr", "recruit", "recruitment", "recruiting", "talent",
                      "hiring", "people", "cv", "resume", "join", "joinus", "employment", "vacancies", "tawzeef")
CAREER_LINK_RE = re.compile(r"career|jobs|join[- ]?us|work[- ]with[- ]us|vacanc|وظائف|التوظيف|انضم", re.I)
CONTACT_PATHS = ["", "/careers", "/jobs", "/contact", "/contact-us", "/en/careers", "/en/contact-us", "/about"]


def has_mx(domain: str) -> bool:
    try:
        return bool(dns.resolver.resolve(domain, "MX", lifetime=6))
    except (dns.exception.DNSException, OSError):
        return False


def email_matches_domain(email: str, domain: str) -> bool:
    ed = email.split("@")[-1].lower()
    return ed == domain or ed.endswith("." + domain) or domain.endswith("." + ed)


def rank_email(email: str) -> int:
    local = email.split("@")[0].lower()
    if any(local == p or local.startswith(p) for p in RECRUIT_LOCALPARTS):
        return 0
    if local in ("info", "contact", "hello"):
        return 2
    return 1


def extract_emails(html_text: str) -> set[str]:
    soup = BeautifulSoup(html_text, "lxml")
    emails = set()
    for a in soup.select('a[href^="mailto:"]'):
        addr = a["href"][7:].split("?")[0].strip()
        if EMAIL_RE.fullmatch(addr):
            emails.add(addr.lower())
    for m in EMAIL_RE.findall(soup.get_text(" ")):
        if not m.lower().endswith((".png", ".jpg", ".svg", ".webp", ".gif")):
            emails.add(m.lower())
    return emails


def track_careers_page(company: Company) -> bool:
    """Start scanning a careers page found on the company's own site (auto-tracking).

    ATS links are tracked as that ATS; same-site pages as 'careers_page' (read via schema.org JobPosting).
    Off-site pages on unsupported systems are left alone.
    """
    if company.tracked or company.ats_type or not company.careers_url:
        return False
    hit = detect_board(company.careers_url)
    if hit:
        company.ats_type, company.ats_slug = hit
    else:
        site, page = (company.domain or "").lower(), (domain_of(company.careers_url) or "").lower()
        if not site or not (page == site or page.endswith("." + site)):
            return False
        company.ats_type = "careers_page"
    company.tracked, company.tracking_source = True, "auto"
    company.board_detected_from = company.careers_url[:500]
    log.info("auto-tracking %s careers board for %s", company.ats_type, company.name)
    return True


def enrich_company(db: Session, company: Company, use_llm: bool = True) -> Company:
    company.last_enriched_at = utcnow()
    company.enrichment_error = None
    if not company.website and company.domain:
        company.website = f"https://{company.domain}"
    if not company.website or is_job_board(company.website):
        company.enrichment_error = "No official website known"
        db.commit()
        return company

    domain = company.domain or domain_of(company.website)
    pages_text: list[str] = []
    candidates: dict[str, str] = {}  # email -> page url
    home = polite_get(company.website)
    if home is None or home.status_code >= 400:
        company.enrichment_error = "Website not reachable or crawling not permitted"
        db.commit()
        return company

    base = str(home.url)
    final_domain = domain_of(base)
    if final_domain and not company.domain and not is_job_board(final_domain):
        company.domain = final_domain
        domain = final_domain
    soup = BeautifulSoup(home.text, "lxml")

    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta and meta.get("content") and not company.description:
        company.description = meta["content"].strip()[:2000]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "linkedin.com/company/" in href and not company.linkedin_url:
            company.linkedin_url = href.split("?")[0][:500]
        if not company.careers_url and (CAREER_LINK_RE.search(a.get_text(" ", strip=True) or "")
                                        or CAREER_LINK_RE.search(href)):
            full = urljoin(base, href)
            if full.startswith("http"):
                company.careers_url = full[:500]
    pages_text.append(soup.get_text(" ", strip=True)[:4000])
    for e in extract_emails(home.text):
        candidates.setdefault(e, base)

    extra = [urljoin(base, p) for p in CONTACT_PATHS[1:]]
    if company.careers_url and domain_of(company.careers_url) == domain_of(base):
        extra.insert(0, company.careers_url)
    for url in dict.fromkeys(extra):
        r = polite_get(url, timeout=10)
        if r is None or r.status_code >= 400:
            continue
        for e in extract_emails(r.text):
            candidates.setdefault(e, str(r.url))
        if len(pages_text) < 3:
            pages_text.append(BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)[:3000])

    valid = sorted((e for e in candidates if domain and email_matches_domain(e, domain)), key=rank_email)
    valid = [e for e in valid if rank_email(e) < 2] or valid  # prefer recruitment/personal over generic info@
    if valid and (not company.recruitment_email or not company.email_verified):
        email = valid[0]
        if has_mx(email.split("@")[1]):
            company.recruitment_email = email
            company.email_verified = True
            company.email_source_url = candidates[email][:500]

    if not company.city:
        company.city = detect_city(" ".join(pages_text))
    track_careers_page(company)

    llm = get_llm()
    if use_llm and llm.available and not company.industry and pages_text:
        try:
            data = llm.json_completion(
                "You summarize a company from text scraped from its own website. Use ONLY the provided text. "
                "Return JSON {industry: short string or null, description: 2-3 sentence factual summary or null}.",
                f"Company: {company.name}\nWEBSITE TEXT:\n{' '.join(pages_text)[:6000]}",
                max_tokens=400,
            )
            company.industry = (data.get("industry") or None) and str(data["industry"])[:255]
            if data.get("description") and (not company.description or len(company.description) < 80):
                company.description = str(data["description"])[:2000]
        except LLMError as e:
            log.info("company research LLM failed: %s", e)
    db.commit()
    return company
