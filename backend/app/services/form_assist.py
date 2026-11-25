"""Online application assistant (Method B).

Reads the public application page (when permitted), detects form fields and proposes values taken
from the approved CV profile. It never submits anything: the user reviews, pastes and submits
on the official site, then confirms with "Mark as applied".
"""

import re

from bs4 import BeautifulSoup

from app.models import Application, CandidateProfile
from app.services.http_fetch import fetch_allowed, polite_get
from app.services.workflow import current_email

RULES: list[tuple[str, str]] = [
    (r"first[\s_-]?name|given|الاسم الأول", "first_name"),
    (r"last[\s_-]?name|surname|family|اسم العائلة", "last_name"),
    (r"full[\s_-]?name|^name$|your name|الاسم", "full_name"),
    (r"e-?mail|البريد", "email"),
    (r"phone|mobile|tel|الجوال|الهاتف", "phone"),
    (r"linkedin", "linkedin_url"),
    (r"github", "github_url"),
    (r"portfolio|website|personal site", "portfolio_url"),
    (r"city|location|address|المدينة", "location"),
    (r"cover|motivation|why.*(join|interested)|message|رسالة", "cover_letter"),
    (r"years.*experience|experience.*years|سنوات", "years_experience"),
    (r"university|school|institution|الجامعة", "institution"),
    (r"degree|qualification|المؤهل", "degree"),
    (r"current.*(company|employer)|employer", "current_company"),
    (r"current.*(title|position|role)|job title", "current_title"),
    (r"resume|cv|السيرة", "resume_file"),
]


def profile_values(profile: CandidateProfile, cover_letter: str | None) -> dict[str, str | None]:
    parts = (profile.full_name or "").split()
    edu = profile.education[0] if profile.education else {}
    exp = profile.experience[0] if profile.experience else {}
    return {
        "full_name": profile.full_name, "first_name": parts[0] if parts else None,
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else None, "email": profile.email,
        "phone": profile.phone, "linkedin_url": profile.linkedin_url, "github_url": profile.github_url,
        "portfolio_url": profile.portfolio_url, "location": profile.location,
        "years_experience": f"{profile.years_experience:g}" if profile.years_experience is not None else None,
        "institution": edu.get("institution"), "degree": " ".join(x for x in [edu.get("degree"), edu.get("field")] if x) or None,
        "current_company": exp.get("company"), "current_title": exp.get("title"),
        "cover_letter": cover_letter, "resume_file": "Attach your CV file (download it from the Profile page)",
    }


def detect_fields(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    labels = {lab.get("for"): lab.get_text(" ", strip=True) for lab in soup.find_all("label") if lab.get("for")}
    fields = []
    for el in soup.find_all(["input", "textarea", "select"]):
        ftype = el.get("type", el.name).lower()
        if ftype in ("hidden", "submit", "button", "image", "reset", "search"):
            continue
        name = el.get("name") or el.get("id") or ""
        label = labels.get(el.get("id")) or el.get("aria-label") or el.get("placeholder") or name
        if not label:
            continue
        fields.append({"name": name, "label": label[:200], "type": ftype,
                       "required": el.has_attr("required") or el.get("aria-required") == "true"})
    return fields[:60]


def assist(app: Application, profile: CandidateProfile) -> dict:
    email = current_email(app) or next((e for e in reversed(app.emails)), None)
    values = profile_values(profile, email.body if email else None)
    url = app.job.application_url or app.job.source_url
    result = {"application_url": url, "page_status": "not_fetched", "fields": [], "profile_values": values,
              "notes": []}
    if not fetch_allowed(url):
        result["notes"].append("This site does not permit automated access; open it and fill the form using the values below.")
        return result
    r = polite_get(url)
    if r is None:
        result["page_status"] = "unavailable"
        result["notes"].append("Page could not be read automatically (robots.txt, login or bot protection). "
                               "Open it and use the values below.")
        return result
    fields = detect_fields(r.text)
    result["page_status"] = "fetched" if fields else "no_form_found"
    if not fields:
        result["notes"].append("No form detected on this page — the form may load after login or via JavaScript.")
    for f in fields:
        key = next((k for pat, k in RULES if re.search(pat, f"{f['label']} {f['name']}", re.I)), None)
        f["profile_key"] = key
        f["suggested_value"] = values.get(key) if key else None
    result["fields"] = fields
    result["notes"].append("Review every value, submit on the official site yourself, then click 'Mark as applied'.")
    return result
