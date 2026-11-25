from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_automation_settings, get_current_user, get_profile
from app.api.routes.jobs import job_detail
from app.core.database import get_db, utcnow
from app.models import (
    Application,
    ApplicationEmail,
    AutomationSettings,
    CandidateProfile,
    Company,
    EmailHistory,
    FollowUp,
    Job,
    JobMatch,
    User,
)
from app.models.enums import ApplicationStatus, EmailStatus, FollowUpStatus
from app.schemas import (
    ApplicationDetail,
    ApplicationRow,
    ApplicationUpdate,
    ConfirmIn,
    EmailHistoryOut,
    EmailOut,
    EmailUpdate,
    FollowUpOut,
    FollowUpUpdate,
    HistoryOut,
    Page,
    RegenerateIn,
    StatusUpdate,
)
from app.services import form_assist, workflow
from app.services.applications import ApplicationError, choose_method, latest_email, revoke_approvals, set_status

# Reachable only through the explicit review actions, never through a manual status change.
GUARDED_STATUSES = {ApplicationStatus.APPROVED, ApplicationStatus.READY_TO_APPLY, ApplicationStatus.APPLIED}
from app.services.audit import audit
from app.services.email_writer import check_email, generate_email, generate_followup

router = APIRouter(tags=["applications"])


def application_query(user_id: int, *, city=None, category=None, status=None, statuses=None, min_score=None,
                      company=None, method=None, date_from=None, date_to=None, applied_only=False):
    stmt = (select(Application, Job, Company, JobMatch)
            .join(Job, Job.id == Application.job_id).join(Company, Company.id == Application.company_id)
            .outerjoin(JobMatch, JobMatch.id == Application.match_id)
            .where(Application.user_id == user_id))
    if city:
        stmt = stmt.where(Job.city == city)
    if category:
        stmt = stmt.where(Job.category == category)
    if status:
        stmt = stmt.where(Application.status == status)
    if statuses:
        stmt = stmt.where(Application.status.in_(statuses))
    if min_score is not None:
        stmt = stmt.where(JobMatch.score >= min_score)
    if company:
        stmt = stmt.where(or_(Company.name.ilike(f"%{company}%"), Job.title.ilike(f"%{company}%")))
    if method:
        stmt = stmt.where(Application.method == method)
    date_col = Application.applied_at if applied_only else Application.created_at
    if applied_only:
        stmt = stmt.where(Application.applied_at.is_not(None))
    if date_from:
        stmt = stmt.where(date_col >= date_from)
    if date_to:
        stmt = stmt.where(date_col <= date_to)
    return stmt


def _row(a: Application, j: Job, c: Company, m: JobMatch | None) -> ApplicationRow:
    return ApplicationRow(
        id=a.id, job_id=j.id, company_id=c.id, company_name=c.name, job_title=j.title, city=j.city,
        category=j.category, match_score=m.score if m else None, match_category=m.category if m else None,
        method=a.method, status=a.status, applied_at=a.applied_at, status_changed_at=a.status_changed_at,
        source_url=j.source_url, application_url=j.application_url, recipient_email=a.recipient_email,
        experience_level=j.experience_level, created_at=a.created_at)


SORTS = {"score": JobMatch.score.desc().nullslast(), "applied": Application.applied_at.desc().nullslast(),
         "updated": Application.status_changed_at.desc(), "created": Application.created_at.desc()}


@router.get("/applications", response_model=Page)
def list_applications(city: str | None = None, category: str | None = None, status: str | None = None,
                      statuses: list[str] | None = Query(None), min_score: int | None = None,
                      company: str | None = None, method: str | None = None, date_from: datetime | None = None,
                      date_to: datetime | None = None, applied_only: bool = False, sort: str = "updated",
                      page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = application_query(user.id, city=city, category=category, status=status, statuses=statuses,
                             min_score=min_score, company=company, method=method, date_from=date_from,
                             date_to=date_to, applied_only=applied_only)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(SORTS.get(sort, SORTS["updated"]), Application.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[_row(*r) for r in rows], total=total, page=page, page_size=page_size)


def _own(db: Session, user: User, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "Application not found")
    return app


def _eh_out(h: EmailHistory, app: Application | None) -> EmailHistoryOut:
    o = EmailHistoryOut.model_validate(h)
    if app:
        o.company_name, o.job_title = app.company.name, app.job.title
    return o


def _fu_out(f: FollowUp) -> FollowUpOut:
    o = FollowUpOut.model_validate(f)
    o.company_name, o.job_title, o.method = f.application.company.name, f.application.job.title, f.application.method
    return o


def detail(db: Session, user: User, app: Application) -> ApplicationDetail:
    row = _row(app, app.job, app.company, app.match)
    eh = db.scalars(select(EmailHistory).where(EmailHistory.application_id == app.id).order_by(EmailHistory.created_at)).all()
    return ApplicationDetail(
        **row.model_dump(), notes=app.notes, interview_at=app.interview_at, response_at=app.response_at,
        gmail_thread_id=app.gmail_thread_id, job=job_detail(db, app.job, user),
        emails=[EmailOut.model_validate(e) for e in app.emails],
        history=[HistoryOut.model_validate(h) for h in app.history],
        email_history=[_eh_out(h, app) for h in eh], follow_ups=[_fu_out(f) for f in app.follow_ups])


@router.get("/applications/{app_id}", response_model=ApplicationDetail)
def get_application(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return detail(db, user, _own(db, user, app_id))


@router.patch("/applications/{app_id}/status", response_model=ApplicationDetail)
def update_status(app_id: int, body: StatusUpdate, request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    app = _own(db, user, app_id)
    if body.status in GUARDED_STATUSES and body.status != app.status:
        # These statuses can only be reached through the review buttons (Approve / Send / Mark as applied),
        # so an approval always corresponds to an email version the user actually reviewed.
        raise HTTPException(409, f"'{body.status.value}' can only be set with the Approve, Send or "
                                 "Mark as applied buttons after reviewing the application.")
    if body.interview_at:
        app.interview_at = body.interview_at
    old = app.status
    set_status(db, app, body.status, "user", body.note)
    audit(db, user.id, "application.status", "application", app.id, {"from": old, "to": body.status.value},
          client_ip(request))
    db.commit()
    return detail(db, user, app)


@router.patch("/applications/{app_id}", response_model=ApplicationDetail)
def update_application(app_id: int, body: ApplicationUpdate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    app = _own(db, user, app_id)
    data = body.model_dump(exclude_unset=True)
    if app.applied_at and ({"method", "recipient_email"} & set(data)):
        raise HTTPException(409, "Already applied — method and recipient can no longer change")
    changed = {k for k, v in data.items() if getattr(app, k) != v}
    for k, v in data.items():
        setattr(app, k, v)
    if changed & {"method", "recipient_email"} and app.status in (ApplicationStatus.APPROVED,
                                                                  ApplicationStatus.READY_TO_APPLY):
        # The approval covered a specific recipient/method; a change needs a fresh review.
        live = latest_email(app)
        revoke_approvals(app, keep=live)
        if live and live.status == EmailStatus.APPROVED:
            live.status, live.approved_at = EmailStatus.DRAFT, None  # keep the text, require re-approval
        set_status(db, app, ApplicationStatus.AWAITING_APPROVAL, "user",
                   "Recipient/method changed — re-approval required")
    audit(db, user.id, "application.update", "application", app.id, {"fields": list(data)})
    db.commit()
    return detail(db, user, app)


@router.post("/applications/{app_id}/generate-email", response_model=EmailOut)
def regenerate_email(app_id: int, body: RegenerateIn | None = None, user: User = Depends(get_current_user),
                     profile: CandidateProfile = Depends(get_profile), db: Session = Depends(get_db)):
    app = _own(db, user, app_id)
    if app.applied_at:
        raise HTTPException(409, "Already applied")
    if app.method is None:
        app.method = choose_method(app)
    email = generate_email(db, app, profile, body.instructions if body else None)
    audit(db, user.id, "email.generate", "application_email", email.id, commit=True)
    return email


@router.put("/emails/{email_id}", response_model=EmailOut)
def edit_email(email_id: int, body: EmailUpdate, user: User = Depends(get_current_user),
               profile: CandidateProfile = Depends(get_profile), db: Session = Depends(get_db)):
    email = db.get(ApplicationEmail, email_id)
    if not email or email.application.user_id != user.id:
        raise HTTPException(404, "Email not found")
    if email.status not in (EmailStatus.DRAFT, EmailStatus.APPROVED):
        raise HTTPException(409, f"Cannot edit an email with status '{email.status}'")
    app = email.application
    if app.applied_at:
        raise HTTPException(409, "Already applied — the sent email can no longer be edited")
    latest = latest_email(app)
    if latest is not email:
        raise HTTPException(409, "Only the latest version of the email can be edited")
    email.subject, email.body, email.edited = body.subject, body.body, True
    email.warnings = check_email(body.body, body.subject, app, profile)
    # Any edit cancels approval of every version: the edited text must be reviewed and approved again.
    revoke_approvals(app, keep=email)
    email.status, email.approved_at = EmailStatus.DRAFT, None
    if app.status in (ApplicationStatus.APPROVED, ApplicationStatus.READY_TO_APPLY):
        set_status(db, app, ApplicationStatus.AWAITING_APPROVAL, "user", "Email edited — re-approval required")
    audit(db, user.id, "email.edit", "application_email", email.id)
    db.commit()
    return email


@router.post("/applications/{app_id}/approve", response_model=ApplicationDetail)
def approve(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = _own(db, user, app_id)
    try:
        workflow.approve(db, user, app)
    except ApplicationError as e:
        raise HTTPException(409, str(e)) from e
    return detail(db, user, app)


@router.post("/applications/{app_id}/reject", response_model=ApplicationDetail)
def reject(app_id: int, body: ConfirmIn | None = None, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    app = _own(db, user, app_id)
    workflow.reject(db, user, app, body.note if body else None)
    return detail(db, user, app)


@router.post("/applications/{app_id}/send", response_model=ApplicationDetail)
def send(app_id: int, body: ConfirmIn, user: User = Depends(get_current_user),
         settings: AutomationSettings = Depends(get_automation_settings), db: Session = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(400, "Explicit confirmation required (confirm=true)")
    app = _own(db, user, app_id)
    try:
        workflow.send_application(db, user, app, settings, user_confirmed=body.confirm)
    except ApplicationError as e:
        raise HTTPException(409, str(e)) from e
    return detail(db, user, app)


@router.get("/applications/{app_id}/form-assist")
def assist(app_id: int, user: User = Depends(get_current_user), profile: CandidateProfile = Depends(get_profile),
           db: Session = Depends(get_db)):
    return form_assist.assist(_own(db, user, app_id), profile)


@router.post("/applications/{app_id}/mark-applied", response_model=ApplicationDetail)
def mark_applied(app_id: int, body: ConfirmIn, user: User = Depends(get_current_user),
                 settings: AutomationSettings = Depends(get_automation_settings), db: Session = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(400, "Confirm that you submitted the application (confirm=true)")
    app = _own(db, user, app_id)
    try:
        workflow.mark_applied_online(db, user, app, settings, body.note)
    except ApplicationError as e:
        raise HTTPException(409, str(e)) from e
    return detail(db, user, app)


# ---------------------------------------------------------------- email history
@router.get("/email-history", response_model=Page)
def email_history(direction: str | None = None, q: str | None = None, page: int = Query(1, ge=1),
                  page_size: int = Query(25, le=200), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    stmt = select(EmailHistory).where(EmailHistory.user_id == user.id)
    if direction:
        stmt = stmt.where(EmailHistory.direction == direction)
    if q:
        stmt = stmt.where(or_(EmailHistory.subject.ilike(f"%{q}%"), EmailHistory.to_email.ilike(f"%{q}%"),
                              EmailHistory.from_email.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(EmailHistory.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = [_eh_out(h, db.get(Application, h.application_id) if h.application_id else None) for h in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------- follow-ups
@router.get("/followups", response_model=list[FollowUpOut])
def list_followups(status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(FollowUp).join(Application).where(Application.user_id == user.id)
    if status:
        stmt = stmt.where(FollowUp.status == status)
    return [_fu_out(f) for f in db.scalars(stmt.order_by(FollowUp.due_at)).all()]


def _own_fu(db: Session, user: User, fu_id: int) -> FollowUp:
    fu = db.get(FollowUp, fu_id)
    if not fu or fu.application.user_id != user.id:
        raise HTTPException(404, "Follow-up not found")
    return fu


@router.post("/followups/refresh")
def refresh_followups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    replies = workflow.check_replies(db, user)
    due = workflow.refresh_followups(db, user)
    return {"replies_detected": replies, "followups_due": due}


@router.put("/followups/{fu_id}", response_model=FollowUpOut)
def edit_followup(fu_id: int, body: FollowUpUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    fu = _own_fu(db, user, fu_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(fu, k, v)
    db.commit()
    return _fu_out(fu)


@router.post("/followups/{fu_id}/draft", response_model=FollowUpOut)
def draft_followup(fu_id: int, user: User = Depends(get_current_user), profile: CandidateProfile = Depends(get_profile),
                   db: Session = Depends(get_db)):
    fu = _own_fu(db, user, fu_id)
    fu.subject, fu.body = generate_followup(fu.application, profile)
    db.commit()
    return _fu_out(fu)


@router.post("/followups/{fu_id}/send", response_model=FollowUpOut)
def send_followup(fu_id: int, body: ConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(400, "Explicit confirmation required (confirm=true)")
    fu = _own_fu(db, user, fu_id)
    try:
        workflow.send_followup(db, user, fu, user_confirmed=body.confirm)
    except ApplicationError as e:
        raise HTTPException(409, str(e)) from e
    return _fu_out(fu)


@router.post("/followups/{fu_id}/dismiss", response_model=FollowUpOut)
def dismiss_followup(fu_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fu = _own_fu(db, user, fu_id)
    fu.status = FollowUpStatus.DISMISSED
    fu.updated_at = utcnow()
    app = fu.application
    if app.status == ApplicationStatus.FOLLOW_UP_REQUIRED:
        set_status(db, app, ApplicationStatus.APPLIED, "user", "Follow-up dismissed")
    db.commit()
    return _fu_out(fu)
