from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawJob:
    title: str
    company_name: str
    source: str  # jsearch|serpapi|greenhouse|lever|ashby|workable|careers_page
    source_url: str
    description: str | None = None
    location: str | None = None
    city: str | None = None
    company_website: str | None = None
    company_linkedin: str | None = None
    company_logo: str | None = None
    employment_type: str | None = None
    posted_at: datetime | None = None
    application_url: str | None = None
    publisher: str | None = None
    external_id: str | None = None
    salary_text: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    experience_months: int | None = None
    language: str | None = None
    raw: dict = field(default_factory=dict)
    company_id: int | None = None  # set by company-board scans: the job belongs to that exact company


@dataclass
class SearchQuery:
    title: str
    city: str
    language: str = "en"  # en|ar
    category: str = "technology"

    @property
    def text(self) -> str:
        if self.language == "ar":
            from app.services.keywords import CITY_ARABIC

            return f"{self.title} {CITY_ARABIC.get(self.city, self.city)}"
        return f"{self.title} in {self.city}, Saudi Arabia"


class SourceError(RuntimeError):
    pass


class JobSource:
    """Keyword-search source (aggregators)."""

    name = "base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    def search(self, query: SearchQuery) -> list[RawJob]:
        raise NotImplementedError
