from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_automation_settings, get_current_user
from app.core.config import settings as app_settings
from app.core.database import get_db
from app.models import AutomationRun, AutomationSettings, User
from app.schemas import AutomationSettingsIn, AutomationSettingsOut, RunOut
from app.services import scheduler
from app.services.audit import audit
from app.services.discovery.engine import configured_sources
from app.services.llm import get_llm
from app.services.pipeline import is_running, run_pipeline_in_background

router = APIRouter(prefix="/automation", tags=["automation"])


def _out(s: AutomationSettings) -> AutomationSettingsOut:
    o = AutomationSettingsOut.model_validate(s)
    o.next_run_at = scheduler.next_run_time(s.user_id)
    return o


@router.get("/settings", response_model=AutomationSettingsOut)
def get_settings(s: AutomationSettings = Depends(get_automation_settings)):
    return _out(s)


@router.put("/settings", response_model=AutomationSettingsOut)
def update_settings(body: AutomationSettingsIn, user: User = Depends(get_current_user),
                    s: AutomationSettings = Depends(get_automation_settings), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    audit(db, user.id, "automation.settings", details=data)
    db.commit()
    if scheduler.scheduler.running:
        scheduler.schedule_user(s)
    return _out(s)


@router.post("/pause", response_model=AutomationSettingsOut)
def pause(user: User = Depends(get_current_user), s: AutomationSettings = Depends(get_automation_settings),
          db: Session = Depends(get_db)):
    s.paused = True
    audit(db, user.id, "automation.pause")
    db.commit()
    if scheduler.scheduler.running:
        scheduler.schedule_user(s)
    return _out(s)


@router.post("/resume", response_model=AutomationSettingsOut)
def resume(user: User = Depends(get_current_user), s: AutomationSettings = Depends(get_automation_settings),
           db: Session = Depends(get_db)):
    s.paused = False
    audit(db, user.id, "automation.resume")
    db.commit()
    if scheduler.scheduler.running:
        scheduler.schedule_user(s)
    return _out(s)


@router.post("/run")
def run_now(user: User = Depends(get_current_user), s: AutomationSettings = Depends(get_automation_settings)):
    if s.paused:
        raise HTTPException(409, "Automation is paused — resume it first")
    if is_running():
        raise HTTPException(409, "A run is already in progress")
    run_pipeline_in_background(user.id, "manual")
    return {"started": True}


@router.get("/runs", response_model=list[RunOut])
def runs(limit: int = Query(20, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(AutomationRun).where(AutomationRun.user_id == user.id)
                      .order_by(AutomationRun.started_at.desc()).limit(limit)).all()


@router.post("/check-openai")
def check_openai(_: User = Depends(get_current_user)):
    """Make a tiny real request to OpenAI and report the exact problem, if any."""
    return get_llm().check()


@router.get("/status")
def status(user: User = Depends(get_current_user), s: AutomationSettings = Depends(get_automation_settings)):
    return {
        "running": is_running(),
        "paused": s.paused,
        "next_run_at": scheduler.next_run_time(user.id),
        "openai_error": get_llm().last_error,
        "integrations": {
            "openai": get_llm().available,
            "gmail_configured": app_settings.gmail_configured,
            "gmail_connected": bool(user.gmail_token_encrypted),
            **{f"source_{k}": v for k, v in configured_sources().items()},
        },
    }
