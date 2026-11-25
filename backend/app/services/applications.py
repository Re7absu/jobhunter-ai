"""Application status machine, history and duplicate-application guard."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import Application, ApplicationStatusHistory, EmailHistory, Job
from app.models.enums import SUBMITTED_STATUSES, ApplicationMethod, ApplicationStatus


class ApplicationError(ValueError):
    pass


def record_status(db: Session, app: Application, from_status: str | None, to_status: str,
                  changed_by: str = "system", note: str | None = None) -> None:
    db.add(ApplicationStatusHistory(application_id=app.id, from_status=from_status, to_status=to_status,
                                    changed_by=changed_by, note=note))


def set_status(db: Session, app: Application, status: ApplicationStatus | str, changed_by: str = "system",
               note: str | None = None) -> Application:
    status = ApplicationStatus(status)
    if app.status == status:
        return app
    old = app.status
    app.status = status
    app.status_changed_at = utcnow()
    if status == ApplicationStatus.APPLIED and not app.applied_at:
        app.applied_at = utcnow()
    if status == ApplicationStatus.RESPONSE_RECEIVED and not app.response_at:
        app.response_at = utcnow()
    record_status(db, app, old, status, changed_by, note)
    return app


def revoke_approvals(app: Application, keep=None) -> int:
    """Cancel every draft/approved email of this application except `keep`.

    Called whenever the email content changes (regenerate / edit) so that an approval always refers to
    exactly the text the user reviewed. Returns how many approvals were revoked.
    """
    from app.models.enums import EmailStatus

    revoked = 0
    for e in app.emails:
        if e is keep:
            continue
        if e.status == EmailStatus.APPROVED:
            revoked += 1
        if e.status in (EmailStatus.DRAFT, EmailStatus.APPROVED):
            e.status = EmailStatus.REJECTED  # superseded
            e.approved_at = None
    return revoked


def latest_email(app: Application):
    return max(app.emails, key=lambda e: e.version) if app.emails else None


def already_applied_elsewhere(db: Session, app: Application) -> Application | None:
    """Same company + same normalized title already submitted (e.g. found on two boards)."""
    job = app.job
    return db.scalar(
        select(Application).join(Job, Job.id == Application.job_id).where(
            Application.user_id == app.user_id,
            Application.id != app.id,
            Application.company_id == app.company_id,
            Job.normalized_title == job.normalized_title,
            Application.status.in_([s.value for s in SUBMITTED_STATUSES]),
        )
    )


def assert_can_submit(db: Session, app: Application) -> None:
    if app.applied_at or app.status in {s.value for s in SUBMITTED_STATUSES}:
        raise ApplicationError("This position has already been applied to.")
    sent = db.scalar(select(func.count(EmailHistory.id)).where(
        EmailHistory.application_id == app.id, EmailHistory.direction == "outbound", EmailHistory.status == "sent",
        EmailHistory.follow_up_id.is_(None)))
    if sent:
        raise ApplicationError("An application email was already sent for this position.")
    other = already_applied_elsewhere(db, app)
    if other:
        raise ApplicationError(f"You already applied to this role at this company (application #{other.id}).")


def choose_method(app: Application) -> str | None:
    company = app.company
    if company and company.recruitment_email and company.email_verified:
        return ApplicationMethod.EMAIL
    if app.job and app.job.application_url:
        return ApplicationMethod.ONLINE
    return None


LOCAL_OFFSET = timedelta(hours=3)  # Asia/Riyadh (UTC+3, no DST)


def local_now() -> datetime:
    return utcnow() + LOCAL_OFFSET


def day_bounds(day: datetime | None = None) -> tuple[datetime, datetime]:
    """UTC start/end of the local (Riyadh) calendar day containing `day` (a local datetime)."""
    local = (day or local_now()).replace(hour=0, minute=0, second=0, microsecond=0)
    start = local - LOCAL_OFFSET
    return start, start + timedelta(days=1)


def applications_sent_today(db: Session, user_id: int) -> int:
    start, end = day_bounds()
    return db.scalar(select(func.count(Application.id)).where(
        Application.user_id == user_id, Application.applied_at >= start, Application.applied_at < end)) or 0
