from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.services import gmail_service
from app.services.audit import audit

router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return {"configured": settings.gmail_configured, "connected": bool(user.gmail_token_encrypted),
            "email": user.gmail_email, "scopes": gmail_service.SCOPES}


@router.get("/auth-url")
def auth_url(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return {"url": gmail_service.authorization_url(db, user)}
    except gmail_service.GmailError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/callback")
def callback(request: Request, state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    """Google redirects here after consent; we then send the browser back to the dashboard."""
    target = f"{settings.FRONTEND_URL}/settings"
    if error or not code:
        return RedirectResponse(f"{target}?gmail=error&reason={error or 'missing_code'}")
    try:
        user = gmail_service.complete_authorization(db, state, code)
    except Exception as e:  # noqa: BLE001 - report any OAuth failure back to the UI
        return RedirectResponse(f"{target}?gmail=error&reason={type(e).__name__}")
    audit(db, user.id, "gmail.connected", details={"email": user.gmail_email}, ip=client_ip(request), commit=True)
    return RedirectResponse(f"{target}?gmail=connected")


@router.post("/disconnect")
def disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    gmail_service.disconnect(db, user)
    audit(db, user.id, "gmail.disconnected", commit=True)
    return {"connected": False}
