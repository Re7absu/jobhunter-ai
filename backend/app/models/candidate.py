from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, TimestampMixin, utcnow


class CV(Base):
    __tablename__ = "cvs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(String(500))  # encrypted file on disk
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|parsed|failed
    parse_method: Mapped[str | None] = mapped_column(String(20))  # llm|heuristic
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    active_cv_id: Mapped[int | None] = mapped_column(ForeignKey("cvs.id", ondelete="SET NULL"))

    full_name: Mapped[str | None] = mapped_column(String(255))
    headline: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)

    education: Mapped[list] = mapped_column(JSONType, default=list)
    experience: Mapped[list] = mapped_column(JSONType, default=list)
    projects: Mapped[list] = mapped_column(JSONType, default=list)
    certifications: Mapped[list] = mapped_column(JSONType, default=list)
    languages: Mapped[list] = mapped_column(JSONType, default=list)
    target_roles: Mapped[list] = mapped_column(JSONType, default=list)
    years_experience: Mapped[float | None] = mapped_column(Float)
    extraction_warnings: Mapped[list] = mapped_column(JSONType, default=list)

    user = relationship("User", back_populates="profile")
    skills = relationship("CandidateSkill", back_populates="profile", cascade="all, delete-orphan")


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("profile_id", "normalized_name", name="uq_skill_profile_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(30), default="technical")
    source: Mapped[str] = mapped_column(String(20), default="cv")  # cv|manual|profile
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile = relationship("CandidateProfile", back_populates="skills")
