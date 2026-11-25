from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, TimestampMixin, utcnow


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_job_source_external"),
        Index("ix_jobs_company_title_city", "company_id", "normalized_title", "city"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    normalized_title: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)  # technology|product_management
    role_family: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    location_raw: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(50))
    experience_level: Mapped[str | None] = mapped_column(String(20), index=True)
    experience_min_years: Mapped[float | None] = mapped_column(Float)
    experience_text: Mapped[str | None] = mapped_column(String(255))
    salary_text: Mapped[str | None] = mapped_column(String(255))
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    application_url: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(50), index=True)
    publisher: Mapped[str | None] = mapped_column(String(100))  # e.g. LinkedIn, Bayt (via aggregator)
    # search_api | ats_board_auto | ats_board_manual | careers_page_auto | careers_page_manual
    discovery_method: Mapped[str] = mapped_column(String(30), default="search_api", index=True)
    # Other places the same job was seen later: [{source, publisher, url, at}]
    seen_sources: Mapped[list] = mapped_column(JSONType, default=list)
    source_url: Mapped[str] = mapped_column(String(1000), unique=True)
    external_id: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(5))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    raw: Mapped[dict | None] = mapped_column(JSONType)

    company = relationship("Company", back_populates="jobs")
    requirements = relationship("JobRequirement", back_populates="job", cascade="all, delete-orphan")
    matches = relationship("JobMatch", back_populates="job", cascade="all, delete-orphan")


class JobRequirement(Base):
    __tablename__ = "job_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    requirement_type: Mapped[str] = mapped_column(String(30))  # skill|experience|education|language|certification
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    job = relationship("Job", back_populates="requirements")


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("job_id", "profile_id", name="uq_match_job_profile"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    matching_skills: Mapped[list] = mapped_column(JSONType, default=list)
    missing_skills: Mapped[list] = mapped_column(JSONType, default=list)
    transferable_skills: Mapped[list] = mapped_column(JSONType, default=list)
    explanation: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(20))  # apply|consider|skip
    should_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    method: Mapped[str] = mapped_column(String(20))  # llm|heuristic
    model: Mapped[str | None] = mapped_column(String(100))
    cv_id: Mapped[int | None] = mapped_column(ForeignKey("cvs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    job = relationship("Job", back_populates="matches")
