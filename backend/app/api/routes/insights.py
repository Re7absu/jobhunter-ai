from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.applications import application_query
from app.core.database import get_db
from app.models import Application, AuditLog, DailyReport, User
from app.schemas import AuditOut, DailyReportOut
from app.services import analytics, exports
from app.services.applications import local_now

router = APIRouter(tags=["analytics, reports & exports"])


@router.get("/analytics/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return analytics.kpis(db, user.id)


@router.get("/analytics/charts")
def charts(days: int = Query(30, ge=7, le=365), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return analytics.charts(db, user.id, days)


@router.get("/reports/daily", response_model=list[DailyReportOut])
def reports(limit: int = Query(30, le=365), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(DailyReport).where(DailyReport.user_id == user.id)
                      .order_by(DailyReport.report_date.desc()).limit(limit)).all()


@router.post("/reports/daily/today", response_model=DailyReportOut)
def report_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return analytics.build_daily_report(db, user.id)


@router.get("/reports/daily/{day}", response_model=DailyReportOut)
def report_for(day: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rep = db.scalar(select(DailyReport).where(DailyReport.user_id == user.id, DailyReport.report_date == day))
    if rep is None:
        if day > local_now().date():
            raise HTTPException(404, "No report for a future date")
        rep = analytics.build_daily_report(db, user.id, day)
    return rep


@router.get("/reports/contacted")
def contacted(day: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = day or local_now().date()
    items = analytics.contacted_on(db, user.id, d)
    return {"date": d.isoformat(), "count": len(items), "companies": items}


def _apps(db: Session, user: User, **filters):
    rows = db.execute(application_query(user.id, **filters).order_by(Application.applied_at.desc().nullslast(),
                                                                       Application.id.desc())).all()
    return [r[0] for r in rows]


def _filters(city, category, status, min_score, company, date_from, date_to, applied_only):
    return dict(city=city, category=category, status=status, min_score=min_score, company=company,
                date_from=date_from, date_to=date_to, applied_only=applied_only)


@router.get("/exports/applications.csv")
def export_csv(city: str | None = None, category: str | None = None, status: str | None = None,
               min_score: int | None = None, company: str | None = None, date_from: datetime | None = None,
               date_to: datetime | None = None, applied_only: bool = True,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apps = _apps(db, user, **_filters(city, category, status, min_score, company, date_from, date_to, applied_only))
    fname = f"applications_{local_now():%Y%m%d}.csv"
    return Response(exports.to_csv(apps), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/exports/applications.xlsx")
def export_xlsx(city: str | None = None, category: str | None = None, status: str | None = None,
                min_score: int | None = None, company: str | None = None, date_from: datetime | None = None,
                date_to: datetime | None = None, applied_only: bool = True,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apps = _apps(db, user, **_filters(city, category, status, min_score, company, date_from, date_to, applied_only))
    daily = analytics.contacted_on(db, user.id, local_now().date())
    fname = f"applications_{local_now():%Y%m%d}.xlsx"
    return Response(exports.to_xlsx(apps, daily),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(limit: int = Query(100, le=1000), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(AuditLog).where(AuditLog.user_id == user.id)
                      .order_by(AuditLog.created_at.desc()).limit(limit)).all()
