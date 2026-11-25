"""Recognise a company's public job board (ATS) from any URL that points into it.

Used on JSearch apply links and on links found on company career pages, so that companies
discovered through search get their own complete job board scanned automatically.
"""

import re
from urllib.parse import parse_qs, urlparse

# Path segments that are part of the ATS UI, never a company slug.
_RESERVED = {"embed", "api", "j", "jobs", "job", "oneclick-ui", "apply", "careers", "search", "static", "assets",
             "public", "widget", "v1", "v2", "v3", "en", "ar", "login", "signup", "auth", ""}


def _first_segment(path: str) -> str | None:
    seg = path.strip("/").split("/")[0] if path.strip("/") else ""
    seg = seg.split("?")[0]
    return None if seg.lower() in _RESERVED else seg


def detect_board(url: str | None) -> tuple[str, str] | None:
    """Return (ats_type, slug) for a URL on a supported public job board, else None."""
    if not url or not isinstance(url, str):
        return None
    try:
        p = urlparse(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if not host:
        return None
    qs = parse_qs(p.query)

    if host.endswith("greenhouse.io"):  # boards.greenhouse.io/<slug>, job-boards(.eu).greenhouse.io/<slug>
        if "for" in qs:  # boards.greenhouse.io/embed/job_board?for=<slug>
            return "greenhouse", qs["for"][0]
        if host.startswith(("boards", "job-boards")):
            slug = _first_segment(p.path)
            return ("greenhouse", slug) if slug else None
        return None
    if host in ("jobs.lever.co", "jobs.eu.lever.co"):
        slug = _first_segment(p.path)
        return ("lever", slug) if slug else None
    if host == "jobs.ashbyhq.com":
        slug = _first_segment(p.path)
        return ("ashby", slug) if slug else None
    if host == "apply.workable.com":
        slug = _first_segment(p.path)
        return ("workable", slug) if slug else None
    if host.endswith(".workable.com") and host not in ("www.workable.com", "apply.workable.com", "resources.workable.com"):
        return "workable", host.split(".")[0]
    if host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        slug = _first_segment(p.path)
        return ("smartrecruiters", slug) if slug else None
    return None


def detect_from_urls(urls) -> tuple[str, str, str] | None:
    """First (ats_type, slug, url) found among the given URLs."""
    for u in urls or []:
        hit = detect_board(u)
        if hit and re.fullmatch(r"[A-Za-z0-9_.%-]{2,120}", hit[1]):
            return hit[0], hit[1], u
    return None
