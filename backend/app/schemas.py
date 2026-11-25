from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import EXPERIENCE_LEVELS, ApplicationStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- auth
class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    gmail_email: str | None = None


# ---------------- CV / profile
class CVOut(ORM):
    id: int
    original_filename: str
    content_type: str
    size_bytes: int
    is_active: bool
    parse_status: str
    parse_method: str | None
    parse_error: str | None
    parsed_at: datetime | None
    created_at: datetime


class SkillOut(ORM):
    id: int
    name: str
    category: str
    source: str
    evidence: str | None


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str | None = None


class ProfileOut(ORM):
    id: int
    full_name: str | None
    headline: str | None
    email: str | None
    phone: str | None
    location: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    summary: str | None
    education: list
    experience: list
    projects: list
    certifications: list
    languages: list
    target_roles: list
    years_experience: float | None
    extraction_warnings: list
    active_cv_id: int | None
    skills: list[SkillOut]
    updated_at: datetime


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    summary: str | None = None
    target_roles: list[str] | None = None
    years_experience: float | None = None


# ---------------- companies / jobs
class CompanyOut(ORM):
    id: int
    name: str
    domain: str | None
    website: str | None
    linkedin_url: str | None
    city: str | None
    industry: str | None
    description: str | None
    careers_url: str | None
    logo_url: str | None
    recruitment_email: str | None
    email_verified: bool
    email_source_url: str | None
    ats_type: str | None
    ats_slug: str | None
    tracked: bool
    tracking_source: str | None = None
    board_detected_from: str | None = None
    last_scanned_at: datetime | None = None
    scan_error: str | None = None
    source: str | None
    discovered_at: datetime
    last_enriched_at: datetime | None
    enrichment_error: str | None
    job_count: int = 0


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    city: str | None = None
    industry: str | None = None
    ats_type: str | None = Field(default=None, pattern="^(greenhouse|lever|ashby|workable|smartrecruiters|careers_page)$")
    ats_slug: str | None = None
    tracked: bool = True


class CompanyUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    city: str | None = None
    industry: str | None = None
    description: str | None = None
    recruitment_email: EmailStr | None = None
    ats_type: str | None = Field(default=None, pattern="^(greenhouse|lever|ashby|workable|smartrecruiters|careers_page)$")
    ats_slug: str | None = None
    tracked: bool | None = None


class MatchOut(ORM):
    id: int
    job_id: int
    score: int
    category: str
    matching_skills: list
    missing_skills: list
    transferable_skills: list
    explanation: str | None
    recommendation: str
    should_apply: bool
    method: str
    model: str | None
    created_at: datetime


class RequirementOut(ORM):
    requirement_type: str
    name: str
    is_required: bool


class JobOut(ORM):
    id: int
    company_id: int
    company_name: str | None = None
    title: str
    category: str
    role_family: str | None
    city: str | None
    location_raw: str | None
    employment_type: str | None
    experience_level: str | None
    experience_min_years: float | None
    salary_text: str | None
    posted_at: datetime | None
    application_url: str | None
    source: str
    publisher: str | None
    source_url: str
    discovery_method: str = "search_api"
    seen_sources: list = []
    is_active: bool
    discovered_at: datetime
    last_verified_at: datetime | None = None
    updated_at: datetime | None = None
    match_score: int | None = None
    match_category: str | None = None
    application_id: int | None = None
    application_status: str | None = None


class JobDetail(JobOut):
    description: str | None
    experience_text: str | None
    requirements: list[RequirementOut] = []
    match: MatchOut | None = None
    company: CompanyOut | None = None


# ---------------- applications
class EmailOut(ORM):
    id: int
    version: int
    subject: str
    body: str
    status: str
    generation_method: str
    model: str | None
    warnings: list
    edited: bool
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmailUpdate(BaseModel):
    subject: str = Field(min_length=3, max_length=500)
    body: str = Field(min_length=20)


class HistoryOut(ORM):
    from_status: str | None
    to_status: str
    changed_by: str
    note: str | None
    created_at: datetime


class EmailHistoryOut(ORM):
    id: int
    application_id: int | None
    direction: str
    from_email: str | None
    to_email: str | None
    subject: str | None
    body: str | None
    attachment_name: str | None
    gmail_message_id: str | None
    gmail_thread_id: str | None
    status: str
    error: str | None
    created_at: datetime
    company_name: str | None = None
    job_title: str | None = None


class FollowUpOut(ORM):
    id: int
    application_id: int
    due_at: datetime
    status: str
    subject: str | None
    body: str | None
    sent_at: datetime | None
    company_name: str | None = None
    job_title: str | None = None
    method: str | None = None


class FollowUpUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    due_at: datetime | None = None


class ApplicationRow(BaseModel):
    id: int
    job_id: int
    company_id: int
    company_name: str
    job_title: str
    city: str | None
    category: str
    match_score: int | None
    match_category: str | None
    method: str | None
    status: str
    applied_at: datetime | None
    status_changed_at: datetime
    source_url: str
    application_url: str | None
    recipient_email: str | None
    experience_level: str | None
    created_at: datetime


class ApplicationDetail(ApplicationRow):
    notes: str | None
    interview_at: datetime | None
    response_at: datetime | None
    gmail_thread_id: str | None
    job: JobDetail
    emails: list[EmailOut]
    history: list[HistoryOut]
    email_history: list[EmailHistoryOut]
    follow_ups: list[FollowUpOut]


class StatusUpdate(BaseModel):
    status: ApplicationStatus
    note: str | None = None
    interview_at: datetime | None = None


class ApplicationUpdate(BaseModel):
    notes: str | None = None
    method: str | None = Field(default=None, pattern="^(email|online)$")
    recipient_email: EmailStr | None = None


class RegenerateIn(BaseModel):
    instructions: str | None = Field(default=None, max_length=1000)


class ConfirmIn(BaseModel):
    confirm: bool = False
    note: str | None = None


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


# ---------------- automation
class AutomationSettingsOut(ORM):
    paused: bool
    auto_discovery: bool
    search_frequency_hours: int
    run_hour: int
    preferred_cities: list
    job_categories: list
    custom_job_titles: list
    experience_levels: list
    include_arabic_titles: bool
    sources_enabled: list
    max_queries_per_run: int
    max_boards_per_run: int
    max_jobs_to_analyze_per_run: int
    min_match_score: int
    max_daily_applications: int
    auto_generate_emails: bool
    follow_up_after_days: int
    job_max_age_days: int
    last_run_at: datetime | None
    next_run_at: datetime | None = None


class AutomationSettingsIn(BaseModel):
    auto_discovery: bool | None = None
    search_frequency_hours: int | None = Field(default=None, ge=1, le=168)
    run_hour: int | None = Field(default=None, ge=0, le=23)
    preferred_cities: list[str] | None = None
    job_categories: list[str] | None = None
    custom_job_titles: list[str] | None = None
    experience_levels: list[str] | None = None
    include_arabic_titles: bool | None = None
    sources_enabled: list[str] | None = None
    max_queries_per_run: int | None = Field(default=None, ge=1, le=200)
    max_boards_per_run: int | None = Field(default=None, ge=0, le=200)
    max_jobs_to_analyze_per_run: int | None = Field(default=None, ge=1, le=500)
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    max_daily_applications: int | None = Field(default=None, ge=0, le=100)
    auto_generate_emails: bool | None = None
    follow_up_after_days: int | None = Field(default=None, ge=1, le=60)
    job_max_age_days: int | None = Field(default=None, ge=1, le=120)

    @field_validator("preferred_cities")
    @classmethod
    def _cities(cls, v):
        if v is not None and not set(v) <= {"Riyadh", "Jeddah"}:
            raise ValueError("Supported cities: Riyadh, Jeddah")
        return v

    @field_validator("job_categories")
    @classmethod
    def _cats(cls, v):
        if v is not None and not set(v) <= {"technology", "product_management"}:
            raise ValueError("Categories: technology, product_management")
        return v

    @field_validator("experience_levels")
    @classmethod
    def _levels(cls, v):
        if v is not None and not set(v) <= set(EXPERIENCE_LEVELS):
            raise ValueError(f"Levels: {EXPERIENCE_LEVELS}")
        return v


class RunOut(ORM):
    id: int
    trigger: str
    status: str
    current_step: str | None
    stats: dict
    log: list
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class DiscoveryRunIn(BaseModel):
    titles: list[str] | None = None
    cities: list[str] | None = None
    max_queries: int | None = Field(default=None, ge=1, le=100)


class SearchHistoryOut(ORM):
    id: int
    source: str
    query: str
    city: str | None
    results_count: int
    new_jobs_count: int
    new_companies_count: int
    status: str
    error: str | None
    created_at: datetime


class DailyReportOut(ORM):
    id: int
    report_date: date
    new_companies: int
    new_jobs: int
    jobs_analyzed: int
    qualified: int
    emails_generated: int
    applications_sent: int
    responses: int
    companies_contacted: list
    summary: dict
    updated_at: datetime


class AuditOut(ORM):
    id: int
    action: str
    entity_type: str | None
    entity_id: int | None
    details: dict | None
    ip_address: str | None
    created_at: datetime
