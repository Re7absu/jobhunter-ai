from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, TimestampMixin, utcnow
from app.models.enums import ApplicationStatus


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    # Never apply twice to the same position.
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("job_matches.id", ondelete="SET NULL"))
    method: Mapped[str | None] = mapped_column(String(20))  # email|online
    status: Mapped[str] = mapped_column(String(30), default=ApplicationStatus.DISCOVERED, index=True)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    response_at: Mapped[datetime | None] = mapped_column(DateTime)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    job = relationship("Job")
    company = relationship("Company")
    match = relationship("JobMatch")
    emails = relationship(
        "ApplicationEmail", back_populates="application", cascade="all, delete-orphan",
        order_by="ApplicationEmail.version",
    )
    history = relationship(
        "ApplicationStatusHistory", back_populates="application", cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.created_at",
    )
    follow_ups = relationship("FollowUp", back_populates="application", cascade="all, delete-orphan")


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[str] = mapped_column(String(20), default="system")  # user|system
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    application = relationship("Application", back_populates="history")


class ApplicationEmail(TimestampMixin, Base):
    __tablename__ = "application_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    generation_method: Mapped[str] = mapped_column(String(20))  # llm|template|manual
    model: Mapped[str | None] = mapped_column(String(100))
    warnings: Mapped[list] = mapped_column(JSONType, default=list)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)

    application = relationship("Application", back_populates="emails")


class EmailHistory(Base):
    __tablename__ = "email_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), index=True)
    application_email_id: Mapped[int | None] = mapped_column(ForeignKey("application_emails.id", ondelete="SET NULL"))
    follow_up_id: Mapped[int | None] = mapped_column(ForeignKey("follow_ups.id", ondelete="SET NULL"))
    direction: Mapped[str] = mapped_column(String(10))  # outbound|inbound
    from_email: Mapped[str | None] = mapped_column(String(255))
    to_email: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    attachment_name: Mapped[str | None] = mapped_column(String(255))
    gmail_message_id: Mapped[str | None] = mapped_column(String(100), index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20))  # sent|failed|received
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FollowUp(TimestampMixin, Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    gmail_message_id: Mapped[str | None] = mapped_column(String(100))

    application = relationship("Application", back_populates="follow_ups")
