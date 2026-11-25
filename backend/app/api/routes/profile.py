from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_profile
from app.core.database import get_db
from app.models import CV, CandidateProfile, CandidateSkill, User
from app.schemas import CVOut, ProfileOut, ProfileUpdate, SkillIn, SkillOut
from app.services.audit import audit
from app.services.cv_parser import CVError, parse_cv, read_cv_file, save_upload
from app.services.skills import normalize_skill, skill_category

router = APIRouter(tags=["cv & profile"])


@router.post("/cv/upload", response_model=ProfileOut)
async def upload_cv(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    data = await file.read()
    try:
        cv = save_upload(db, user, file.filename or "cv", data)
        audit(db, user.id, "cv.upload", "cv", cv.id, {"filename": cv.original_filename}, client_ip(request), commit=True)
        profile = parse_cv(db, cv, user)
    except CVError as e:
        raise HTTPException(400, str(e)) from e
    return profile


@router.get("/cv", response_model=list[CVOut])
def list_cvs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(CV).where(CV.user_id == user.id).order_by(CV.created_at.desc())).all()


def _own_cv(db: Session, user: User, cv_id: int) -> CV:
    cv = db.get(CV, cv_id)
    if not cv or cv.user_id != user.id:
        raise HTTPException(404, "CV not found")
    return cv


@router.get("/cv/{cv_id}/download")
def download_cv(cv_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cv = _own_cv(db, user, cv_id)
    audit(db, user.id, "cv.download", "cv", cv.id, ip=client_ip(request), commit=True)
    return Response(read_cv_file(cv), media_type=cv.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{cv.original_filename}"'})


@router.post("/cv/{cv_id}/reparse", response_model=ProfileOut)
def reparse_cv(cv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cv = _own_cv(db, user, cv_id)
    try:
        return parse_cv(db, cv, user)
    except CVError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/cv/{cv_id}", status_code=204)
def delete_cv(cv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from pathlib import Path

    cv = _own_cv(db, user, cv_id)
    if cv.is_active:
        raise HTTPException(400, "Cannot delete the active CV; upload a new one first")
    Path(cv.storage_path).unlink(missing_ok=True)
    db.delete(cv)
    audit(db, user.id, "cv.delete", "cv", cv_id)
    db.commit()


@router.get("/profile", response_model=ProfileOut)
def get_my_profile(profile: CandidateProfile = Depends(get_profile)):
    return profile


@router.put("/profile", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, profile: CandidateProfile = Depends(get_profile),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)
    audit(db, user.id, "profile.update", "profile", profile.id, {"fields": list(body.model_dump(exclude_unset=True))})
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profile/skills", response_model=SkillOut)
def add_skill(body: SkillIn, profile: CandidateProfile = Depends(get_profile), db: Session = Depends(get_db)):
    canon = normalize_skill(body.name)
    if any(s.normalized_name == canon.lower() for s in profile.skills):
        raise HTTPException(409, "Skill already in profile")
    skill = CandidateSkill(profile_id=profile.id, name=canon, normalized_name=canon.lower(),
                           category=body.category or skill_category(canon), source="manual")
    db.add(skill)
    db.commit()
    return skill


@router.delete("/profile/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: int, profile: CandidateProfile = Depends(get_profile), db: Session = Depends(get_db)):
    skill = db.get(CandidateSkill, skill_id)
    if not skill or skill.profile_id != profile.id:
        raise HTTPException(404, "Skill not found")
    db.delete(skill)
    db.commit()
