"""AI job-matching agent (LLM) with a deterministic fallback."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import Application, CandidateProfile, Job, JobMatch, JobRequirement
from app.models.enums import ApplicationStatus, match_category
from app.services.applications import set_status
from app.services.cv_parser import profile_facts_json
from app.services.keywords import role_family
from app.services.llm import LLMError, get_llm
from app.services.skills import RELATED, extract_skills, normalize_skill

log = logging.getLogger(__name__)

MATCH_SYSTEM = """You are a senior technical recruiter evaluating fit between a candidate and a job in Saudi Arabia.
Rules:
- Use ONLY the candidate facts provided (extracted from their CV). Never assume skills they did not list.
- Consider transferable skills and relevant experience; do NOT reject only because the job title differs.
- Junior/graduate/intern candidates can be suitable for entry-level and junior roles even with gaps.
- Be calibrated: 80-100 excellent, 65-79 good, 50-64 potential, <50 low.
Return JSON:
{"score": int 0-100,
 "required_skills": [str]  (technical & professional skills the job asks for),
 "matching_skills": [str]  (required skills the candidate demonstrably has),
 "missing_skills": [str]   (required skills not evidenced in the CV),
 "transferable_skills": [str] (candidate skills that partially cover missing ones, e.g. "PostgreSQL -> MySQL"),
 "experience_fit": "below"|"meets"|"above",
 "explanation": "3-5 sentences: why suitable or unsuitable, citing concrete CV facts",
 "recommendation": "apply"|"consider"|"skip"}"""


def _job_payload(job: Job) -> str:
    return (
        f"TITLE: {job.title}\nCOMPANY: {job.company.name if job.company else ''}\nCITY: {job.city}\n"
        f"LEVEL: {job.experience_level} (min years: {job.experience_min_years})\n"
        f"EMPLOYMENT: {job.employment_type}\nDESCRIPTION:\n{(job.description or '')[:7000]}"
    )


def llm_match(profile: CandidateProfile, job: Job) -> dict:
    llm = get_llm()
    data = llm.json_completion(
        MATCH_SYSTEM, f"CANDIDATE FACTS (JSON):\n{profile_facts_json(profile)}\n\nJOB:\n{_job_payload(job)}",
        temperature=0.1, max_tokens=1200,
    )
    score = max(0, min(100, int(round(float(data.get("score", 0))))))
    have = {s.normalized_name for s in profile.skills}
    # Guard: a "matching" skill must actually exist in the candidate profile.
    matching = [s for s in data.get("matching_skills") or [] if normalize_skill(s).lower() in have
                or any(normalize_skill(s).lower() in h or h in normalize_skill(s).lower() for h in have)]
    return {
        "score": score,
        "required_skills": [str(s) for s in data.get("required_skills") or []][:40],
        "matching_skills": matching[:40],
        "missing_skills": [str(s) for s in data.get("missing_skills") or []][:40],
        "transferable_skills": [str(s) for s in data.get("transferable_skills") or []][:20],
        "explanation": str(data.get("explanation") or "")[:3000],
        "recommendation": data.get("recommendation") if data.get("recommendation") in ("apply", "consider", "skip") else None,
        "method": "llm", "model": llm.model,
    }


LEVEL_FIT = {"internship": 1.0, "coop": 1.0, "graduate": 1.0, "entry": 1.0, "junior": 0.9, "mid": 0.55, "senior": 0.15}


def heuristic_match(profile: CandidateProfile, job: Job) -> dict:
    have = {normalize_skill(s.name) for s in profile.skills}
    required = [r.name for r in job.requirements if r.requirement_type == "skill"] or \
        extract_skills(f"{job.title}\n{job.description or ''}")
    required = list(dict.fromkeys(normalize_skill(r) for r in required))
    matching = [r for r in required if r in have]
    missing = [r for r in required if r not in have]
    transferable = []
    for m in missing:
        rel = RELATED.get(m, set()) & have
        if rel:
            transferable.append(f"{', '.join(sorted(rel))} -> {m}")
    if required:
        skill_ratio = (len(matching) + 0.5 * len(transferable)) / len(required)
    else:
        skill_ratio = 0.5
    targets = " ".join(profile.target_roles or []).lower() + " " + (profile.headline or "").lower()
    fam = role_family(job.title)
    title_fit = 1.0 if fam.split(" ")[0].lower() in targets else 0.6
    years = profile.years_experience or 0
    level_fit = LEVEL_FIT.get(job.experience_level or "mid", 0.5)
    if job.experience_min_years and years >= job.experience_min_years:
        level_fit = max(level_fit, 0.9)
    score = round(100 * (0.6 * min(skill_ratio, 1.0) + 0.15 * title_fit + 0.25 * level_fit))
    explanation = (
        f"Heuristic analysis (no LLM): {len(matching)} of {len(required)} detected required skills found in your CV"
        f"{' (' + ', '.join(matching[:8]) + ')' if matching else ''}. "
        f"{'Missing: ' + ', '.join(missing[:8]) + '. ' if missing else ''}"
        f"{'Transferable: ' + '; '.join(transferable[:5]) + '. ' if transferable else ''}"
        f"Role level '{job.experience_level}' vs your ~{years:g} years of experience."
    )
    return {"score": max(0, min(100, score)), "required_skills": required, "matching_skills": matching,
            "missing_skills": missing, "transferable_skills": transferable, "explanation": explanation,
            "recommendation": None, "method": "heuristic", "model": None}


def analyze_job(db: Session, profile: CandidateProfile, job: Job, min_score: int = 65,
                force: bool = False) -> JobMatch:
    existing = db.scalar(select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.profile_id == profile.id))
    if existing and not force:
        return existing
    llm = get_llm()
    result = None
    if llm.available:
        try:
            result = llm_match(profile, job)
        except (LLMError, ValueError, TypeError) as e:
            log.warning("LLM matching failed for job %s: %s", job.id, e)
    if result is None:
        result = heuristic_match(profile, job)

    score = result["score"]
    rec = result["recommendation"] or ("apply" if score >= min_score else "consider" if score >= 50 else "skip")
    match = existing or JobMatch(job_id=job.id, profile_id=profile.id)
    match.score = score
    match.category = match_category(score)
    match.matching_skills = result["matching_skills"]
    match.missing_skills = result["missing_skills"]
    match.transferable_skills = result["transferable_skills"]
    match.explanation = result["explanation"]
    match.recommendation = rec
    match.should_apply = score >= min_score and rec != "skip"
    match.method, match.model = result["method"], result["model"]
    match.cv_id = profile.active_cv_id
    match.created_at = utcnow()
    if existing is None:
        db.add(match)
    db.flush()

    # Store the LLM's view of requirements (replacing heuristic skill rows)
    if result["method"] == "llm" and result["required_skills"]:
        for r in [r for r in job.requirements if r.requirement_type == "skill"]:
            db.delete(r)
        for s in dict.fromkeys(normalize_skill(x) for x in result["required_skills"]):
            db.add(JobRequirement(job_id=job.id, requirement_type="skill", name=s[:255], normalized_name=s.lower()[:255]))

    app = db.scalar(select(Application).where(Application.job_id == job.id, Application.user_id == profile.user_id))
    if app:
        app.match_id = match.id
        if app.status == ApplicationStatus.DISCOVERED:
            set_status(db, app, ApplicationStatus.ANALYZED, "system", f"Match score {score} ({match.category})")
    db.commit()
    return match


def analyze_pending(db: Session, profile: CandidateProfile, min_score: int, limit: int = 50) -> list[JobMatch]:
    done = select(JobMatch.job_id).where(JobMatch.profile_id == profile.id)
    jobs = db.scalars(select(Job).where(Job.is_active.is_(True), Job.id.not_in(done))
                      .order_by(Job.discovered_at.desc()).limit(limit)).all()
    return [analyze_job(db, profile, j, min_score) for j in jobs]
