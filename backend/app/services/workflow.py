"""Approval → send → track workflow. Every outgoing action requires an explicitly approved email."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import CV, Application, ApplicationEmail, AutomationSettings, EmailHistory, FollowUp, User
from app.models.enums import ApplicationMethod, ApplicationStatus, EmailStatus, FollowUpStatus
from app.services import gmail_service
from app.services.applications import (
    ApplicationError,
    applications_sent_today,
    assert_can_submit,
    latest_email,
    revoke_approvals,
    set_status,
)
from app.services.audit import audit
from app.services.cv_parser import read_cv_file
from app.services.email_writer import generate_followup

log = logging.getLogger(__name__)


def current_email(app: Application) -> ApplicationEmail | None:
    live = [e for e in app.emails if e.status in (EmailStatus.DRAFT, EmailStatus.APPROVED)]
    return live[-1] if live else None


def approve(db: Session, user: User, app: Application) -> Application:
    if app.status not in (ApplicationStatus.AWAITING_APPROVAL, ApplicationStatus.ANALYZED,
                          ApplicationStatus.DISCOVERED):
        raise ApplicationError(f"Cannot approve an application in status '{app.status}'")
    assert_can_submit(db, app)
    latest = latest_email(app)
    email = latest if latest and latest.status in (EmailStatus.DRAFT, EmailStatus.APPROVED) else None
    if email:
        # Approval applies to exactly this version; anything older is cancelled.
        revoke_approvals(app, keep=email)
        email.status = EmailStatus.APPROVED
        email.approved_at = utcnow()
    if app.method == ApplicationMethod.EMAIL:
        if not email:
            raise ApplicationError("Generate an email before approving an email application")
        if not app.recipient_email:
            raise ApplicationError("No verified recruitment email for this company")
        set_status(db, app, ApplicationStatus.APPROVED, "user", "Approved by user")
    else:
        app.method = app.method or ApplicationMethod.ONLINE
        set_status(db, app, ApplicationStatus.READY_TO_APPLY, "user", "Approved for online application")
    audit(db, user.id, "application.approve", "application", app.id,
          {"email_id": email.id if email else None, "email_version": email.version if email else None})
    db.commit()
    return app


def reject(db: Session, user: User, app: Application, note: str | None = None) -> Application:
    email = current_email(app)
    if email:
        email.status = EmailStatus.REJECTED
        email.rejected_at = utcnow()
    set_status(db, app, ApplicationStatus.CLOSED, "user", note or "Rejected in approval queue")
    audit(db, user.id, "application.reject", "application", app.id, {"note": note})
    db.commit()
    return app


def _active_cv(db: Session, user: User) -> CV:
    cv = db.scalar(select(CV).where(CV.user_id == user.id, CV.is_active.is_(True)))
    if not cv:
        raise ApplicationError("Upload a CV before sending applications")
    return cv


def send_application(db: Session, user: User, app: Application, settings: AutomationSettings,
                     *, user_confirmed: bool) -> EmailHistory:
    """Send an APPROVED email application through Gmail with the CV attached.

    Only ever called from the user's own "Send now" action: the daily automation never sends.
    """
    if not user_confirmed:
        raise ApplicationError("Sending requires your explicit confirmation for this specific application")
    if app.status != ApplicationStatus.APPROVED:
        raise ApplicationError("Only approved email applications can be sent")
    email = latest_email(app)
    if not email or email.status != EmailStatus.APPROVED or not email.approved_at:
        raise ApplicationError("The latest version of this email has not been approved — review and approve it first")
    actor = "user"
    if not app.recipient_email:
        raise ApplicationError("Missing recipient email")
    assert_can_submit(db, app)
    if applications_sent_today(db, user.id) >= settings.max_daily_applications:
        raise ApplicationError(f"Daily application limit reached ({settings.max_daily_applications})")
    cv = _active_cv(db, user)

    attachment = (read_cv_file(cv), cv.original_filename, cv.content_type)
    hist = EmailHistory(user_id=user.id, application_id=app.id, application_email_id=email.id, direction="outbound",
                        from_email=user.gmail_email, to_email=app.recipient_email, subject=email.subject,
                        body=email.body, attachment_name=cv.original_filename, status="failed")
    try:
        res = gmail_service.send_email(db, user, app.recipient_email, email.subject, email.body, attachment)
    except gmail_service.GmailError as e:
        hist.error = str(e)[:2000]
        email.status = EmailStatus.APPROVED  # still approved; can retry
        db.add(hist)
        audit(db, user.id, "application.send_failed", "application", app.id, {"error": str(e)[:300]})
        db.commit()
        raise ApplicationError(str(e)) from e
    hist.status = "sent"
    hist.gmail_message_id, hist.gmail_thread_id = res["id"], res["threadId"]
    db.add(hist)
    email.status = EmailStatus.SENT
    app.gmail_thread_id = res["threadId"]
    set_status(db, app, ApplicationStatus.APPLIED, actor, f"Email sent to {app.recipient_email}")
    db.add(FollowUp(application_id=app.id, due_at=utcnow() + timedelta(days=settings.follow_up_after_days)))
    audit(db, user.id, "application.sent", "application", app.id,
          {"to": app.recipient_email, "gmail_message_id": res["id"], "by": actor})
    db.commit()
    return hist


def mark_applied_online(db: Session, user: User, app: Application, settings: AutomationSettings,
                        note: str | None = None) -> Application:
    if app.status != ApplicationStatus.READY_TO_APPLY:
        raise ApplicationError("Approve the application first (status must be 'Ready to Apply')")
    assert_can_submit(db, app)
    app.method = ApplicationMethod.ONLINE
    set_status(db, app, ApplicationStatus.APPLIED, "user", note or "Submitted online by user")
    db.add(FollowUp(application_id=app.id, due_at=utcnow() + timedelta(days=settings.follow_up_after_days)))
    audit(db, user.id, "application.applied_online", "application", app.id)
    db.commit()
    return app


# ---------------------------------------------------------------- follow-ups & replies
def refresh_followups(db: Session, user: User) -> int:
    """Mark due follow-ups and draft their text. Returns number newly due."""
    due = db.scalars(select(FollowUp).join(Application).where(
        Application.user_id == user.id, FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_at <= utcnow(),
        FollowUp.body.is_(None))).all()
    n = 0
    for fu in due:
        app = fu.application
        if app.status != ApplicationStatus.APPLIED:
            fu.status = FollowUpStatus.DISMISSED
            continue
        fu.subject, fu.body = generate_followup(app, user.profile)
        set_status(db, app, ApplicationStatus.FOLLOW_UP_REQUIRED, "system", "No response yet")
        n += 1
    db.commit()
    return n


def send_followup(db: Session, user: User, fu: FollowUp, *, user_confirmed: bool) -> EmailHistory:
    if not user_confirmed:
        raise ApplicationError("Sending a follow-up requires your explicit confirmation")
    app = fu.application
    if fu.status != FollowUpStatus.PENDING or not fu.body:
        raise ApplicationError("Follow-up is not ready to send")
    if app.method != ApplicationMethod.EMAIL or not app.recipient_email:
        raise ApplicationError("Follow-up emails are only possible for email applications")
    hist =EmailHistory(user_id=user.id, application_id=app.id, follow_up_id=fu.id, direction="outbound",
                        from_email=user.gmail_email, to_email=app.recipient_email, subject=fu.subject, body=fu.body,
                        status="failed")
    try:
        res = gmail_service.send_email(db, user, app.recipient_email, fu.subject or "", fu.body,
                                       thread_id=app.gmail_thread_id)
    except gmail_service.GmailError as e:
        hist.error = str(e)
        db.add(hist)
        db.commit()
        raise ApplicationError(str(e)) from e
    hist.status, hist.gmail_message_id, hist.gmail_thread_id = "sent", res["id"], res["threadId"]
    db.add(hist)
    fu.status, fu.sent_at, fu.gmail_message_id = FollowUpStatus.SENT, utcnow(), res["id"]
    if app.status == ApplicationStatus.FOLLOW_UP_REQUIRED:
        set_status(db, app, ApplicationStatus.APPLIED, "user", "Follow-up sent")
    audit(db, user.id, "followup.sent", "application", app.id, {"thread": app.gmail_thread_id})
    db.commit()
    return hist


def check_replies(db: Session, user: User) -> int:
    """Detect replies on Gmail threads of sent applications."""
    if not user.gmail_token_encrypted:
        return 0
    apps = db.scalars(select(Application).where(
        Application.user_id == user.id, Application.gmail_thread_id.is_not(None),
        Application.status.in_([ApplicationStatus.APPLIED, ApplicationStatus.FOLLOW_UP_REQUIRED]))).all()
    found = 0
    for app in apps:
        try:
            replies = gmail_service.thread_replies(db, user, app.gmail_thread_id)
        except gmail_service.GmailError as e:
            log.warning("reply check failed: %s", e)
            break
        known = {h.gmail_message_id for h in db.scalars(select(EmailHistory).where(
            EmailHistory.application_id == app.id, EmailHistory.direction == "inbound"))}
        new = [r for r in replies if r["id"] not in known]
        for r in new:
            received = datetime.fromtimestamp(int(r["internalDate"]) / 1000, timezone.utc).replace(tzinfo=None) \
                if r.get("internalDate") else utcnow()
            db.add(EmailHistory(user_id=user.id, application_id=app.id, direction="inbound", from_email=r["from"],
                                to_email=user.gmail_email, subject=r.get("subject"), body=r.get("snippet"),
                                gmail_message_id=r["id"], gmail_thread_id=app.gmail_thread_id, status="received",
                                created_at=received))
        if new:
            found += 1
            set_status(db, app, ApplicationStatus.RESPONSE_RECEIVED, "system", f"Reply from {new[0]['from']}")
            for fu in app.follow_ups:
                if fu.status == FollowUpStatus.PENDING:
                    fu.status = FollowUpStatus.DISMISSED
    db.commit()
    return found
