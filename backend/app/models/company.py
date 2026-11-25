from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, utcnow


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    domain: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    industry: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(String(500))
    logo_url: Mapped[str | None] = mapped_column(String(500))

    recruitment_email: Mapped[str | None] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_source_url: Mapped[str | None] = mapped_column(String(500))

    # Tracked company career boards (public ATS APIs or JSON-LD career pages)
    # greenhouse|lever|ashby|workable|smartrecruiters|careers_page
    ats_type: Mapped[str | None] = mapped_column(String(30))
    ats_slug: Mapped[str | None] = mapped_column(String(255))
    tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    tracking_source: Mapped[str | None] = mapped_column(String(10))  # manual|auto (auto = detected from job links)
    board_detected_from: Mapped[str | None] = mapped_column(String(500))  # URL that revealed the board
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    scan_error: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str | None] = mapped_column(String(50))
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime)
    enrichment_error: Mapped[str | None] = mapped_column(Text)

    jobs = relationship("Job", back_populates="company", cascade="all, delete-orphan")
