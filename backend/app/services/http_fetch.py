"""Polite HTTP fetching for company websites: robots.txt respected, no anti-bot evasion."""

import logging
import threading
import time
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

# Sites whose terms forbid automated access: we only use them through licensed aggregator APIs.
NO_FETCH_DOMAINS = (
    "linkedin.com", "indeed.com", "bayt.com", "glassdoor.com", "naukrigulf.com", "gulftalent.com",
    "google.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
)

# Job boards / ATS hosts: never treat these as a company's own domain.
JOB_BOARD_DOMAINS = NO_FETCH_DOMAINS + (
    "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com", "myworkdayjobs.com",
    "workday.com", "bamboohr.com", "zohorecruit.com", "jobs.sa", "tanqeeb.com", "wuzzuf.net", "jooble.org",
    "ziprecruiter.com", "monster.com", "talent.com", "jobrapido.com", "careerjet.com", "mihnati.com",
    "taqat.sa", "recruitee.com", "teamtailor.com", "breezy.hr", "jazzhr.com", "icims.com", "taleo.net",
    "successfactors.com", "oraclecloud.com", "eightfold.ai", "pinpointhq.com", "manatal.com", "akhtaboot.com",
)


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def is_job_board(url_or_domain: str | None) -> bool:
    d = domain_of(url_or_domain) if url_or_domain and "/" in url_or_domain else (url_or_domain or "")
    d = (d or "").lower()
    return any(d == b or d.endswith("." + b) for b in JOB_BOARD_DOMAINS)


def fetch_allowed(url: str) -> bool:
    d = domain_of(url) or ""
    return not any(d == b or d.endswith("." + b) for b in NO_FETCH_DOMAINS)


@lru_cache(maxsize=512)
def _robots(origin: str) -> RobotFileParser | None:
    rp = RobotFileParser()
    try:
        r = httpx.get(f"{origin}/robots.txt", timeout=10, follow_redirects=True,
                      headers={"User-Agent": settings.HTTP_USER_AGENT})
        if r.status_code >= 400:
            return None  # no robots.txt -> allowed
        rp.parse(r.text.splitlines())
        return rp
    except httpx.HTTPError:
        return None


def robots_allows(url: str) -> bool:
    p = urlparse(url)
    rp = _robots(f"{p.scheme}://{p.netloc}")
    return True if rp is None else rp.can_fetch(settings.HTTP_USER_AGENT, url)


_last_hit: dict[str, float] = {}
_throttle_lock = threading.Lock()


def throttle(url: str) -> None:
    """Wait so that requests to one host are spaced by max(CRAWL_MIN_DELAY_SECONDS, robots.txt Crawl-delay)."""
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    delay = settings.CRAWL_MIN_DELAY_SECONDS
    rp = _robots(origin) if p.scheme in ("http", "https") else None
    if rp is not None:
        try:
            cd = rp.crawl_delay(settings.HTTP_USER_AGENT)
            if cd:
                delay = max(delay, min(float(cd), 30.0))
        except (TypeError, ValueError):
            pass
    with _throttle_lock:
        wait = _last_hit.get(origin, 0.0) + delay - time.monotonic()
        _last_hit[origin] = time.monotonic() + max(wait, 0.0)
    if wait > 0:
        time.sleep(wait)


def polite_get(url: str, timeout: float = 15) -> httpx.Response | None:
    """GET a public page if allowed by our policy and robots.txt. Returns None when not permitted/failed."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not fetch_allowed(url):
        log.debug("skip (policy) %s", url)
        return None
    if not robots_allows(url):
        log.info("skip (robots.txt) %s", url)
        return None
    throttle(url)
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": settings.HTTP_USER_AGENT, "Accept-Language": "en,ar;q=0.8"})
        if r.status_code in (401, 403, 429) or "captcha" in r.text[:5000].lower():
            log.info("skip (access restricted) %s -> %s", url, r.status_code)
            return None
        return r
    except httpx.HTTPError as e:
        log.debug("fetch failed %s: %s", url, e)
        return None
