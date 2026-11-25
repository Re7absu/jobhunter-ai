from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import AutomationSettings, CandidateProfile, User
from app.services.pipeline import get_settings

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    sub = decode_access_token(creds.credentials)
    user = db.get(User, int(sub)) if sub and sub.isdigit() else None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CandidateProfile:
    if user.profile is None:
        p = CandidateProfile(user_id=user.id, full_name=user.full_name, target_roles=[])
        db.add(p)
        db.commit()
        db.refresh(user)
    return user.profile


def get_automation_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AutomationSettings:
    return get_settings(db, user)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
