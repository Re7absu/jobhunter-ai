from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AutomationSettings, CandidateProfile, CandidateSkill, User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.services import scheduler
from app.services.audit import audit
from app.services.skills import normalize_skill, skill_category

router = APIRouter(prefix="/auth", tags=["auth"])

# Initial profile supplied by the owner (replaced by CV-extracted data once a CV is parsed).
INITIAL_TARGET_ROLES = ["Backend Developer", "Data Engineer", "AI Engineer", "Technical Consultant",
                        "ERP Consultant", "Product Manager"]
INITIAL_SKILLS = ["Python", "JavaScript", "React", "TypeScript", "Next.js", "Backend Development", "FastAPI",
                  "REST APIs", "SQL", "PostgreSQL", "Data Engineering", "Data Analysis", "Artificial Intelligence",
                  "LLMs", "AI Agents", "AI Integration"]


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(User.id))) or 0
    if count > 0 and not settings.ALLOW_REGISTRATION:
        raise HTTPException(403, "Registration is closed")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    user = User(email=body.email.lower(), full_name=body.full_name, hashed_password=hash_password(body.password))
    db.add(user)
    db.flush()
    profile = CandidateProfile(user_id=user.id, full_name=body.full_name, target_roles=INITIAL_TARGET_ROLES,
                               headline="Computer Science graduate · Product Engineer Intern experience")
    db.add(profile)
    db.flush()
    for s in INITIAL_SKILLS:
        db.add(CandidateSkill(profile_id=profile.id, name=normalize_skill(s), normalized_name=normalize_skill(s).lower(),
                              category=skill_category(s), source="profile", evidence="Initial profile (replace by uploading CV)"))
    auto = AutomationSettings(user_id=user.id)
    db.add(auto)
    audit(db, user.id, "auth.register", "user", user.id, ip=client_ip(request))
    db.commit()
    if scheduler.scheduler.running:
        db.refresh(auto)
        scheduler.schedule_user(auto)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.hashed_password):
        audit(db, user.id if user else None, "auth.login_failed", details={"email": body.email}, ip=client_ip(request),
              commit=True)
        raise HTTPException(401, "Incorrect email or password")
    audit(db, user.id, "auth.login", ip=client_ip(request), commit=True)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """Lets the login page know whether the first account still needs to be created."""
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    return {"has_users": has_users, "registration_open": (not has_users) or settings.ALLOW_REGISTRATION}
