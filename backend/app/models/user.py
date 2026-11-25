from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, TimestampMixin, utcnow


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Gmail OAuth (token JSON is Fernet-encrypted)
    gmail_email: Mapped[str | None] = mapped_column(String(255))
    gmail_token_encrypted: Mapped[str | None] = mapped_column(Text)
    gmail_oauth_state: Mapped[str | None] = mapped_column(String(255), index=True)
    gmail_code_verifier: Mapped[str | None] = mapped_column(String(255))

    profile = relationship("CandidateProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings = relationship("AutomationSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict | None] = mapped_column(JSONType)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
