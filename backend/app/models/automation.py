from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, TimestampMixin, utcnow

DEFAULT_CITIES = ["Riyadh", "Jeddah"]
DEFAULT_CATEGORIES = ["technology", "product_management"]
DEFAULT_LEVELS = ["internship", "coop", "graduate", "entry", "junior", "mid"]
DEFAULT_SOURCES = ["jsearch", "serpapi", "ats", "careers_page"]


class AutomationSettings(TimestampMixin, Base):
    __tablename__ = "automation_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    paused: Mapped[bool] = mapped_column(Boolean, default=False)  # global kill-switch
    auto_discovery: Mapped[bool] = mapped_column(Boolean, default=True)
    search_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)
    run_hour: Mapped[int] = mapped_column(Integer, default=7)  # local hour for the daily run (Asia/Riyadh)
    preferred_cities: Mapped[list] = mapped_column(JSONType, default=lambda: list(DEFAULT_CITIES))
    job_categories: Mapped[list] = mapped_column(JSONType, default=lambda: list(DEFAULT_CATEGORIES))
    custom_job_titles: Mapped[list] = mapped_column(JSONType, default=list)
    experience_levels: Mapped[list] = mapped_column(JSONType, default=lambda: list(DEFAULT_LEVELS))
    include_arabic_titles: Mapped[bool] = mapped_column(Boolean, default=True)
    sources_enabled: Mapped[list] = mapped_column(JSONType, default=lambda: list(DEFAULT_SOURCES))
    max_queries_per_run: Mapped[int] = mapped_column(Integer, default=24)
    max_boards_per_run: Mapped[int] = mapped_column(Integer, default=15)  # company boards/career pages scanned
    max_jobs_to_analyze_per_run: Mapped[int] = mapped_column(Integer, default=60)
    min_match_score: Mapped[int] = mapped_column(Integer, default=65)
    max_daily_applications: Mapped[int] = mapped_column(Integer, default=10)
    # There is deliberately no auto-send option: automation only drafts. Every email is sent by the
    # user's own confirmed action on that specific, approved application.
    auto_generate_emails: Mapped[bool] = mapped_column(Boolean, default=True)
    follow_up_after_days: Mapped[int] = mapped_column(Integer, default=7)
    job_max_age_days: Mapped[int] = mapped_column(Integer, default=30)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    user = relationship("User", back_populates="settings")


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(20))  # scheduled|manual
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|completed|failed|skipped
    current_step: Mapped[str | None] = mapped_column(String(100))
    stats: Mapped[dict] = mapped_column(JSONType, default=dict)
    log: Mapped[list] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("automation_runs.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    query: Mapped[str] = mapped_column(String(500), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    new_companies_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("user_id", "report_date", name="uq_daily_report_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    new_companies: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, default=0)
    jobs_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    qualified: Mapped[int] = mapped_column(Integer, default=0)
    emails_generated: Mapped[int] = mapped_column(Integer, default=0)
    applications_sent: Mapped[int] = mapped_column(Integer, default=0)
    responses: Mapped[int] = mapped_column(Integer, default=0)
    companies_contacted: Mapped[list] = mapped_column(JSONType, default=list)
    summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
