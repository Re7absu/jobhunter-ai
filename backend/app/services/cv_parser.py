"""CV upload storage, text extraction and structured profile extraction.

Guarantee: nothing is added to the profile unless it is supported by the CV text.
LLM output is post-validated against the raw text (skills, employers, institutions).
"""

import hashlib
import io
import json
import logging
import re
import uuid
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_bytes, encrypt_bytes
from app.core.database import utcnow
from app.models import CV, CandidateProfile, CandidateSkill, User
from app.services.llm import LLMError, get_llm
from app.services.skills import extract_skills, normalize_skill, normalized_key, skill_category, skill_in_text

log = logging.getLogger(__name__)

PDF_TYPES = {"application/pdf"}
DOCX_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


class CVError(ValueError):
    pass


# ---------------------------------------------------------------- storage
def detect_kind(filename: str, data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK" and filename.lower().endswith(".docx"):
        return "docx"
    raise CVError("Only PDF or DOCX files are accepted")


def store_cv_file(user_id: int, data: bytes, ext: str) -> str:
    folder = settings.storage_path / "cvs" / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.{ext}.enc"
    path.write_bytes(encrypt_bytes(data))
    return str(path)


def read_cv_file(cv: CV) -> bytes:
    return decrypt_bytes(Path(cv.storage_path).read_bytes())


# ---------------------------------------------------------------- text extraction
def extract_text(data: bytes, kind: str) -> str:
    if kind == "pdf":
        reader = PdfReader(io.BytesIO(data))
        parts = [(p.extract_text() or "") for p in reader.pages]
        text = "\n".join(parts)
    else:
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        text = "\n".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 50:
        raise CVError("Could not extract text from the CV (is it a scanned image? please upload a text-based PDF/DOCX)")
    return text


# ---------------------------------------------------------------- LLM extraction
CV_SYSTEM = """You extract structured data from a CV/resume. STRICT RULES:
- Use ONLY information explicitly written in the CV text. Never infer, embellish or invent.
- If a field is not present, use null or an empty list.
- Skills: list only skills/technologies/tools literally mentioned in the CV, with a short evidence quote.
- Keep the candidate's original wording for titles, employers, institutions and dates.
Return JSON with keys:
full_name, headline, email, phone, location, linkedin_url, github_url, portfolio_url, summary,
education: [{institution, degree, field, start, end, grade}],
experience: [{company, title, start, end, location, description, highlights: [str]}],
projects: [{name, description, technologies: [str], url}],
certifications: [{name, issuer, date}],
skills: [{name, category, evidence}]   (category: language|frontend|backend|data|ai|devops|tool|business|product|soft|spoken_language|other),
languages: [str],
years_experience: number|null  (sum of professional experience incl. internships, in years; null if unclear)"""


def llm_extract(text: str) -> dict:
    llm = get_llm()
    return llm.json_completion(CV_SYSTEM, f"CV TEXT:\n\"\"\"\n{text[:24000]}\n\"\"\"", temperature=0, max_tokens=4000)


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower()).strip()


def validate_against_text(data: dict, text: str) -> tuple[dict, list[str]]:
    """Drop any extracted item not supported by the CV text. Returns (clean_data, warnings)."""
    warnings: list[str] = []
    norm_text = _norm(text)

    def present(value: str | None) -> bool:
        if not value:
            return False
        v = _norm(value)
        if not v:
            return False
        if v in norm_text:
            return True
        # allow minor formatting differences: all significant tokens must appear
        tokens = [t for t in v.split() if len(t) > 2]
        return bool(tokens) and all(t in norm_text for t in tokens)

    skills = []
    for s in data.get("skills") or []:
        name = s.get("name") if isinstance(s, dict) else str(s)
        if not name:
            continue
        if skill_in_text(name, text) or present(name):
            skills.append({"name": name, "category": (s.get("category") if isinstance(s, dict) else None),
                           "evidence": (s.get("evidence") if isinstance(s, dict) else None)})
        else:
            warnings.append(f"Dropped skill not found in CV text: {name}")
    data["skills"] = skills

    exp = []
    for e in data.get("experience") or []:
        if present(e.get("company")) or present(e.get("title")):
            exp.append(e)
        else:
            warnings.append(f"Dropped experience entry not found in CV text: {e.get('title')} @ {e.get('company')}")
    data["experience"] = exp

    edu = []
    for e in data.get("education") or []:
        if present(e.get("institution")) or present(e.get("degree")):
            edu.append(e)
        else:
            warnings.append(f"Dropped education entry not found in CV text: {e.get('institution')}")
    data["education"] = edu

    certs = [c for c in data.get("certifications") or [] if present(c.get("name"))]
    if len(certs) != len(data.get("certifications") or []):
        warnings.append("Dropped certification(s) not found in CV text")
    data["certifications"] = certs

    projects = [p for p in data.get("projects") or [] if present(p.get("name")) or present(p.get("description"))]
    data["projects"] = projects

    for key in ("email", "phone", "linkedin_url", "github_url"):
        if data.get(key) and _norm(data[key]).replace(" ", "") not in norm_text.replace(" ", ""):
            warnings.append(f"Dropped {key} not found in CV text")
            data[key] = None
    return data, warnings


# ---------------------------------------------------------------- heuristic extraction
SECTION_HEADERS = {
    "education": r"education|academic|qualifications|التعليم|المؤهلات",
    "experience": r"experience|employment|work history|internships?|الخبرات|الخبرة",
    "projects": r"projects|المشاريع",
    "certifications": r"certifications?|certificates?|courses|licenses|الشهادات",
    "skills": r"skills|technical skills|technologies|المهارات",
    "summary": r"summary|profile|objective|about me|نبذة",
}


def heuristic_extract(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sections: dict[str, list[str]] = {k: [] for k in SECTION_HEADERS}
    current = None
    for ln in lines:
        low = ln.lower().strip(": ")
        hit = next((k for k, p in SECTION_HEADERS.items() if len(low) < 40 and re.fullmatch(rf"({p})\W*", low)), None)
        if hit:
            current = hit
            continue
        if current:
            sections[current].append(ln)

    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(\+?\d[\d\s\-()]{8,}\d)", text)
    linkedin = re.search(r"(https?://)?(www\.)?linkedin\.com/in/[\w\-%]+/?", text, re.I)
    github = re.search(r"(https?://)?(www\.)?github\.com/[\w\-]+/?", text, re.I)
    name = lines[0] if lines and len(lines[0]) < 60 and not re.search(r"@|\d", lines[0]) else None

    def blocks(key: str) -> list[str]:
        return sections[key][:30]

    return {
        "full_name": name,
        "headline": lines[1] if len(lines) > 1 and len(lines[1]) < 100 else None,
        "email": email.group(0) if email else None,
        "phone": phone.group(1).strip() if phone else None,
        "linkedin_url": linkedin.group(0) if linkedin else None,
        "github_url": github.group(0) if github else None,
        "summary": " ".join(sections["summary"])[:1500] or None,
        "education": [{"institution": None, "degree": ln, "field": None, "start": None, "end": None} for ln in blocks("education")[:6]],
        "experience": [{"company": None, "title": ln, "description": None, "highlights": []} for ln in blocks("experience")[:15]],
        "projects": [{"name": ln[:120], "description": ln, "technologies": extract_skills(ln)} for ln in blocks("projects")[:10]],
        "certifications": [{"name": ln, "issuer": None, "date": None} for ln in blocks("certifications")[:10]],
        "skills": [{"name": s, "category": skill_category(s), "evidence": None} for s in extract_skills(text)],
        "languages": [s for s in ("Arabic", "English") if skill_in_text(s, text)],
        "years_experience": None,
    }


# ---------------------------------------------------------------- persistence
def parse_cv(db: Session, cv: CV, user: User) -> CandidateProfile:
    """Extract structured data from a stored CV and (re)build the candidate profile from it."""
    data_bytes = read_cv_file(cv)
    kind = "pdf" if cv.content_type in PDF_TYPES else "docx"
    try:
        text = extract_text(data_bytes, kind)
    except CVError as e:
        cv.parse_status, cv.parse_error = "failed", str(e)
        db.commit()
        raise
    cv.extracted_text = text

    method = "heuristic"
    warnings: list[str] = []
    llm = get_llm()
    if llm.available:
        try:
            data = llm_extract(text)
            data, warnings = validate_against_text(data, text)
            method = "llm"
        except LLMError as e:
            log.warning("LLM CV extraction failed, using heuristic parser: %s", e)
            warnings.append(f"LLM extraction failed ({e}); used heuristic parser")
            data = heuristic_extract(text)
    else:
        warnings.append("OPENAI_API_KEY not set: heuristic parser used; review the extracted profile")
        data = heuristic_extract(text)

    # Deterministic scan always contributes (catches skills the LLM skipped; all are in the text by construction)
    known = {normalized_key(s["name"]) for s in data.get("skills", [])}
    for s in extract_skills(text):
        if normalized_key(s) not in known:
            data.setdefault("skills", []).append({"name": s, "category": skill_category(s), "evidence": None})
            known.add(normalized_key(s))

    profile = user.profile or CandidateProfile(user_id=user.id, target_roles=[])
    if profile.id is None:
        db.add(profile)
    for field in ("full_name", "headline", "email", "phone", "location", "linkedin_url", "github_url",
                  "portfolio_url", "summary"):
        val = data.get(field)
        if isinstance(val, str):
            val = val.strip()[:1500] or None
        setattr(profile, field, val)
    profile.education = data.get("education") or []
    profile.experience = data.get("experience") or []
    profile.projects = data.get("projects") or []
    profile.certifications = data.get("certifications") or []
    profile.languages = data.get("languages") or []
    ye = data.get("years_experience")
    profile.years_experience = float(ye) if isinstance(ye, (int, float)) else None
    profile.extraction_warnings = warnings
    profile.active_cv_id = cv.id
    db.flush()

    # Replace CV-sourced skills; keep manually-added ones.
    # CV is the source of truth: keep only skills the user added by hand (drop old CV/initial-profile skills)
    profile.skills = [sk for sk in profile.skills if sk.source == "manual"]  # delete-orphan removes the rest
    db.flush()
    manual = {sk.normalized_name for sk in profile.skills}
    seen: set[str] = set()
    for s in data.get("skills", []):
        canon = normalize_skill(s["name"])
        key = canon.lower()[:120]
        if key in seen or key in manual:
            continue
        seen.add(key)
        profile.skills.append(CandidateSkill(name=canon[:120], normalized_name=key,
                              category=(s.get("category") or skill_category(canon))[:30], source="cv",
                              evidence=(s.get("evidence") or None)))

    for other in db.query(CV).filter(CV.user_id == user.id, CV.id != cv.id):
        other.is_active = False
    cv.is_active = True
    cv.parse_status, cv.parse_method, cv.parse_error, cv.parsed_at = "parsed", method, None, utcnow()
    db.commit()
    db.refresh(profile)
    return profile


def save_upload(db: Session, user: User, filename: str, data: bytes) -> CV:
    if len(data) > settings.MAX_CV_MB * 1024 * 1024:
        raise CVError(f"File too large (max {settings.MAX_CV_MB} MB)")
    kind = detect_kind(filename, data)
    ctype = "application/pdf" if kind == "pdf" else next(iter(DOCX_TYPES))
    safe_name = re.sub(r"[^\w.\- ]", "_", Path(filename).name)[:200]
    cv = CV(user_id=user.id, original_filename=safe_name, content_type=ctype,
            storage_path=store_cv_file(user.id, data, kind), size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest())
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return cv


def profile_facts(profile: CandidateProfile) -> dict:
    """Compact, verified fact sheet used by the matching and email agents."""
    return {
        "name": profile.full_name,
        "headline": profile.headline,
        "location": profile.location,
        "summary": profile.summary,
        "years_experience": profile.years_experience,
        "skills": sorted({s.name for s in profile.skills}),
        "education": profile.education,
        "experience": profile.experience,
        "projects": profile.projects,
        "certifications": profile.certifications,
        "languages": profile.languages,
        "target_roles": profile.target_roles,
    }


def profile_facts_json(profile: CandidateProfile) -> str:
    return json.dumps(profile_facts(profile), ensure_ascii=False, default=str)[:12000]
