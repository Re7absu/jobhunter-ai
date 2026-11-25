"""AI email-writing agent: one unique, fact-grounded application email per company + position."""

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, ApplicationEmail, CandidateProfile
from app.models.enums import ApplicationStatus, EmailStatus
from app.services.applications import choose_method, revoke_approvals, set_status
from app.services.cv_parser import profile_facts
from app.services.llm import LLMError, get_llm
from app.services.skills import skill_in_text

log = logging.getLogger(__name__)

EMAIL_SYSTEM = """You write a concise, professional job application email in English on behalf of a candidate.
STRICT RULES:
- Use ONLY facts from CANDIDATE FACTS. Never invent degrees, employers, years, metrics, certifications or skills.
- Do NOT claim any skill listed under MISSING SKILLS.
- Personalize for this company and role: reference the role and something specific from the job description
  or company description (only if provided). No generic filler, no clichés like "I am writing to express".
- Structure: greeting; introduction (who the candidate is); short background; 3-5 relevant technical skills
  tied to the role; relevant experience/projects; why this company; clear application statement mentioning
  the attached CV; professional closing with the candidate's name, phone and LinkedIn if provided.
- 170-260 words. Plain text, no markdown, no placeholders like [Company].
- Subject format: "Application for {Job Title} – {Candidate Name}".
Return JSON {"subject": str, "body": str}."""


def _context(app: Application, profile: CandidateProfile, instructions: str | None) -> str:
    job, company, match = app.job, app.company, app.match
    return json.dumps({
        "CANDIDATE FACTS": profile_facts(profile),
        "CONTACT": {"name": profile.full_name, "email": profile.email, "phone": profile.phone,
                    "linkedin": profile.linkedin_url},
        "JOB": {"title": job.title, "city": job.city, "level": job.experience_level,
                "description": (job.description or "")[:5000]},
        "COMPANY": {"name": company.name, "industry": company.industry,
                    "description": (company.description or "")[:1500], "website": company.website},
        "MATCHING SKILLS": match.matching_skills if match else [],
        "MISSING SKILLS": match.missing_skills if match else [],
        "EXTRA INSTRUCTIONS FROM CANDIDATE": instructions or "",
    }, ensure_ascii=False, default=str)


def check_email(body: str, subject: str, app: Application, profile: CandidateProfile) -> list[str]:
    warnings = []
    have = {s.normalized_name for s in profile.skills}
    for miss in (app.match.missing_skills if app.match else []):
        if miss.lower() not in have and skill_in_text(miss, body):
            warnings.append(f"Mentions '{miss}', which is not evidenced in your CV — please review.")
    if app.company.name.lower() not in (body + subject).lower():
        warnings.append("Company name not mentioned — email may be too generic.")
    if "[" in body and "]" in body:
        warnings.append("Contains a bracketed placeholder.")
    return warnings


def template_email(app: Application, profile: CandidateProfile) -> tuple[str, str]:
    """Fallback when no LLM key: built only from verified facts (still specific to the job)."""
    job, company, match = app.job, app.company, app.match
    name = profile.full_name or "Candidate"
    skills = (match.matching_skills if match and match.matching_skills else [s.name for s in profile.skills])[:5]
    exp = profile.experience[0] if profile.experience else None
    edu = profile.education[0] if profile.education else None
    lines = [f"Dear {company.name} Hiring Team,", ""]
    intro = f"I would like to apply for the {job.title} position"
    intro += f" in {job.city}." if job.city else "."
    if edu and (edu.get("degree") or edu.get("field")):
        intro += f" I hold a {' in '.join(x for x in [edu.get('degree'), edu.get('field')] if x)}"
        intro += f" from {edu['institution']}." if edu.get("institution") else "."
    lines.append(intro)
    if exp and (exp.get("title") or exp.get("company")):
        lines.append("")
        lines.append(f"Most recently I worked as {exp.get('title') or 'a team member'}"
                     f"{' at ' + exp['company'] if exp.get('company') else ''}"
                     f"{': ' + exp['description'][:250] if exp.get('description') else '.'}")
    if skills:
        lines += ["", f"My skills relevant to this role include {', '.join(skills[:-1]) + ' and ' + skills[-1] if len(skills) > 1 else skills[0]}."]
    if company.description:
        lines += ["", f"I am interested in {company.name} because of its work in "
                      f"{(company.industry or company.description[:120]).rstrip('.')}."]
    lines += ["", f"Please find my CV attached. I would welcome the opportunity to discuss how I can contribute "
                  f"to {company.name} as a {job.title}.", "", "Kind regards,", name]
    lines += [x for x in [profile.phone, profile.email, profile.linkedin_url] if x]
    return f"Application for {job.title} – {name}", "\n".join(lines)


def generate_email(db: Session, app: Application, profile: CandidateProfile,
                   instructions: str | None = None) -> ApplicationEmail:
    llm = get_llm()
    method, model = "template", None
    subject = body = None
    if llm.available:
        try:
            data = llm.json_completion(EMAIL_SYSTEM, _context(app, profile, instructions), temperature=0.6,
                                       max_tokens=900)
            subject, body = str(data.get("subject") or "").strip(), str(data.get("body") or "").strip()
            method, model = "llm", llm.model
        except LLMError as e:
            log.warning("LLM email generation failed: %s", e)
    if not subject or not body:
        subject, body = template_email(app, profile)
        method, model = "template", None

    version = (db.scalar(select(func.max(ApplicationEmail.version)).where(ApplicationEmail.application_id == app.id)) or 0) + 1
    revoked = revoke_approvals(app)  # a new version always needs a fresh approval
    email = ApplicationEmail(application_id=app.id, version=version, subject=subject[:500], body=body,
                             status=EmailStatus.DRAFT, generation_method=method, model=model,
                             warnings=check_email(body, subject, app, profile))
    db.add(email)
    app.method = app.method or choose_method(app)
    if app.method == "email" and not app.recipient_email:
        app.recipient_email = app.company.recruitment_email
    if app.status in (ApplicationStatus.DISCOVERED, ApplicationStatus.ANALYZED, ApplicationStatus.APPROVED,
                      ApplicationStatus.READY_TO_APPLY):
        note = f"Email v{version} generated ({method})" + (" — previous approval revoked" if revoked else "")
        set_status(db, app, ApplicationStatus.AWAITING_APPROVAL, "system", note)
    db.commit()
    db.refresh(email)
    return email


FOLLOWUP_SYSTEM = """Write a short, polite follow-up email (60-110 words, plain text, English) for a job application
sent earlier with no reply. Use only provided facts; do not add new claims. Return JSON {"subject","body"}."""


def generate_followup(app: Application, profile: CandidateProfile) -> tuple[str, str]:
    original = next((e for e in reversed(app.emails) if e.status == EmailStatus.SENT), None)
    subject = f"Re: {original.subject}" if original else f"Following up: {app.job.title} application"
    llm = get_llm()
    if llm.available:
        try:
            data = llm.json_completion(FOLLOWUP_SYSTEM, json.dumps({
                "candidate": profile.full_name, "company": app.company.name, "role": app.job.title,
                "applied_on": str(app.applied_at.date()) if app.applied_at else None,
                "original_subject": original.subject if original else None}), max_tokens=400)
            return subject, str(data.get("body") or "").strip() or _followup_template(app, profile)
        except LLMError:
            pass
    return subject, _followup_template(app, profile)


def _followup_template(app: Application, profile: CandidateProfile) -> str:
    when = f" on {app.applied_at:%d %B %Y}" if app.applied_at else ""
    return (f"Dear {app.company.name} Hiring Team,\n\nI hope you are well. I am following up on my application for "
            f"the {app.job.title} position, which I sent{when}. I remain very interested in the role and would be glad "
            f"to provide any additional information.\n\nThank you for your time and consideration.\n\n"
            f"Kind regards,\n{profile.full_name or ''}")
