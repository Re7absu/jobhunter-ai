"""Search vocabulary: job titles (EN/AR), cities, classification helpers."""

import re

from app.models.enums import JobCategory

TECH_TITLES: list[tuple[str, str]] = [
    ("Backend Developer", "مطور باك اند"),
    ("Python Developer", "مطور بايثون"),
    ("Java Developer", "مطور جافا"),
    ("Software Engineer", "مهندس برمجيات"),
    ("AI Engineer", "مهندس ذكاء اصطناعي"),
    ("AI Developer", "مطور ذكاء اصطناعي"),
    ("Machine Learning Engineer", "مهندس تعلم الآلة"),
    ("Data Engineer", "مهندس بيانات"),
    ("Data Analyst", "محلل بيانات"),
    ("Technical Consultant", "مستشار تقني"),
    ("ERP Consultant", "مستشار ERP"),
    ("AI Consultant", "مستشار ذكاء اصطناعي"),
]

PRODUCT_TITLES: list[tuple[str, str]] = [
    ("Product Manager", "مدير منتج"),
    ("Associate Product Manager", "مدير منتج مساعد"),
    ("Junior Product Manager", "مدير منتج مبتدئ"),
    ("Product Owner", "مالك المنتج"),
    ("Product Analyst", "محلل منتجات"),
    ("Business Analyst", "محلل أعمال"),
    ("Technical Project Manager", "مدير مشاريع تقنية"),
    ("Digital Transformation Specialist", "أخصائي تحول رقمي"),
    ("IT Project Coordinator", "منسق مشاريع تقنية المعلومات"),
]

# Extra queries specifically for early-career programs
EARLY_CAREER_QUERIES: list[tuple[str, str]] = [
    ("Software Engineering Internship", "تدريب تعاوني تقنية المعلومات"),
    ("Graduate Development Program Technology", "برنامج تطوير الخريجين"),
]

CITIES: dict[str, list[str]] = {
    "Riyadh": ["riyadh", "riyad", "ar riyad", "ar-riyadh", "الرياض"],
    "Jeddah": ["jeddah", "jiddah", "jidda", "jedda", "جدة", "جده"],
}
CITY_ARABIC = {"Riyadh": "الرياض", "Jeddah": "جدة"}


def titles_for(categories: list[str]) -> list[tuple[str, str, str]]:
    """Return (english, arabic, category) tuples for the selected categories."""
    out: list[tuple[str, str, str]] = []
    if JobCategory.TECHNOLOGY in categories:
        out += [(en, ar, JobCategory.TECHNOLOGY) for en, ar in TECH_TITLES]
    if JobCategory.PRODUCT_MANAGEMENT in categories:
        out += [(en, ar, JobCategory.PRODUCT_MANAGEMENT) for en, ar in PRODUCT_TITLES]
    out += [(en, ar, JobCategory.TECHNOLOGY) for en, ar in EARLY_CAREER_QUERIES]
    return out


def detect_city(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t).lower()
    for city, aliases in CITIES.items():
        if any(a in blob for a in aliases):
            return city
    return None


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = re.sub(r"[-–—|/,:]+", " ", t)
    t = re.sub(r"\b(riyadh|jeddah|ksa|saudi arabia|remote|hybrid|onsite|on-site)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_PM_PATTERNS = [
    r"product (manager|owner|analyst|management)", r"business analyst", r"project (manager|coordinator)",
    r"digital transformation", r"scrum master", r"مدير منتج", r"مالك المنتج", r"محلل أعمال", r"مدير مشاريع",
    r"تحول رقمي", r"منسق مشاريع", r"محلل منتجات",
]
_TECH_PATTERNS = [
    r"develop", r"engineer", r"programm", r"software", r"backend", r"back-end", r"full[- ]?stack", r"data ",
    r"data$", r"analyst", r"machine learning", r"\bml\b", r"\bai\b", r"artificial intelligence", r"consultant",
    r"\berp\b", r"\bsap\b", r"odoo", r"python", r"java", r"devops", r"cloud", r"مطور", r"مهندس", r"مبرمج",
    r"بيانات", r"ذكاء اصطناعي", r"مستشار", r"تقني", r"برمجيات",
]


def classify_category(title: str, description: str = "") -> str | None:
    """Return job category or None if the job is outside the target domains."""
    t = title.lower()
    if any(re.search(p, t) for p in _PM_PATTERNS):
        return JobCategory.PRODUCT_MANAGEMENT
    if any(re.search(p, t) for p in _TECH_PATTERNS):
        return JobCategory.TECHNOLOGY
    return None


def role_family(title: str) -> str:
    t = title.lower()
    families = [
        ("AI / ML", [r"\bai\b", r"machine learning", r"\bml\b", r"llm", r"ذكاء", r"تعلم الآلة", r"artificial"]),
        ("Data", [r"data", r"بيانات", r"\bbi\b", r"analytics"]),
        ("ERP / Consulting", [r"\berp\b", r"\bsap\b", r"odoo", r"dynamics", r"consult", r"مستشار"]),
        ("Product", [r"product", r"منتج"]),
        ("Business Analysis", [r"business analyst", r"محلل أعمال"]),
        ("Project Management", [r"project", r"مشاريع", r"transformation", r"تحول"]),
        ("Backend", [r"backend", r"back-end", r"python", r"java", r"api", r"باك"]),
        ("Software Engineering", [r"software", r"developer", r"engineer", r"مطور", r"مهندس", r"full"]),
    ]
    for name, pats in families:
        if any(re.search(p, t) for p in pats):
            return name
    return "Other"


def detect_experience_level(title: str, description: str = "", min_years: float | None = None,
                            employment_type: str | None = None) -> str:
    t = f"{title} {employment_type or ''}".lower()
    d = (description or "").lower()[:4000]
    if re.search(r"co-?op|cooperative|تعاوني", t + " " + d[:600]):
        return "coop"
    if re.search(r"intern|تدريب|trainee", t):
        return "internship"
    if re.search(r"graduate|خريج|new grad|fresh", t):
        return "graduate"
    if re.search(r"\b(senior|sr\.?|lead|principal|head|director|staff|chief|manager ii|iii)\b|أول|خبير|رئيس", t):
        if "product manager" not in t or re.search(r"senior|lead|principal|head|director", t):
            return "senior"
    if re.search(r"\b(junior|jr\.?|entry|associate)\b|مبتدئ", t):
        return "junior" if "junior" in t or "jr" in t else "entry"
    if min_years is not None:
        if min_years <= 0.5:
            return "entry"
        if min_years <= 2:
            return "junior"
        if min_years <= 5:
            return "mid"
        return "senior"
    if re.search(r"fresh graduates?|no experience|0-1 years?|0 - 1 years?", d):
        return "entry"
    return "mid"


def parse_min_years(text: str | None) -> tuple[float | None, str | None]:
    if not text:
        return None, None
    m = re.search(
        r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*(?:\+)?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,4}\s+experience",
        text, re.IGNORECASE,
    )
    if m:
        return float(m.group(1)), m.group(0)[:200]
    m = re.search(r"(?:minimum|at least|min\.?)\s*(?:of\s*)?(\d{1,2})\s*(?:years?|yrs?)", text, re.IGNORECASE)
    if m:
        return float(m.group(1)), m.group(0)[:200]
    m = re.search(r"(\d{1,2})\s*(?:سنوات|سنة)", text)
    if m:
        return float(m.group(1)), m.group(0)
    return None, None


_COMPANY_SUFFIXES = r"\b(co|company|ltd|limited|llc|inc|corp|corporation|group|holding|est|establishment|plc|ksa|sa)\b\.?"


def normalize_company_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"شركة|مؤسسة|المحدودة|القابضة", " ", n)
    n = re.sub(_COMPANY_SUFFIXES, " ", n)
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()
