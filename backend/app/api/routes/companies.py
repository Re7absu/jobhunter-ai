from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Company, Job, User
from app.schemas import CompanyIn, CompanyOut, CompanyUpdate, Page
from app.services.audit import audit
from app.services.discovery.engine import scan_company_boards
from app.services.enrichment import enrich_company
from app.services.http_fetch import domain_of, is_job_board
from app.services.keywords import normalize_company_name
from app.services.pipeline import get_settings

router = APIRouter(prefix="/companies", tags=["companies"])


def _out(c: Company, job_count: int = 0) -> CompanyOut:
    o = CompanyOut.model_validate(c)
    o.job_count = job_count
    return o


@router.get("", response_model=Page)
def list_companies(q: str | None = None, city: str | None = None, has_email: bool | None = None,
                   tracked: bool | None = None, tracking_source: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                   _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jc = select(Job.company_id, func.count(Job.id).label("n")).group_by(Job.company_id).subquery()
    stmt = select(Company, func.coalesce(jc.c.n, 0)).outerjoin(jc, jc.c.company_id == Company.id)
    if q:
        stmt = stmt.where(or_(Company.name.ilike(f"%{q}%"), Company.domain.ilike(f"%{q}%"),
                              Company.industry.ilike(f"%{q}%")))
    if city:
        stmt = stmt.where(Company.city == city)
    if has_email is not None:
        stmt = stmt.where(Company.email_verified.is_(has_email))
    if tracked is not None:
        stmt = stmt.where(Company.tracked.is_(tracked))
    if tracking_source:
        stmt = stmt.where(Company.tracking_source == tracking_source)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Company.discovered_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[_out(c, n) for c, n in rows], total=total or 0, page=page, page_size=page_size)


@router.post("", response_model=CompanyOut)
def add_company(body: CompanyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Track a real company's career board (public ATS API or JSON-LD careers page)."""
    domain = domain_of(body.website) if body.website and not is_job_board(body.website) else None
    if domain and db.scalar(select(Company).where(Company.domain == domain)):
        raise HTTPException(409, "A company with this website already exists")
    if body.ats_type == "careers_page" and not body.careers_url:
        raise HTTPException(400, "careers_url is required for ats_type=careers_page")
    c = Company(name=body.name, normalized_name=normalize_company_name(body.name), domain=domain,
                website=body.website, careers_url=body.careers_url, linkedin_url=body.linkedin_url, city=body.city,
                industry=body.industry, ats_type=body.ats_type, ats_slug=body.ats_slug,
                tracked=body.tracked and bool(body.ats_type), source="manual",
                tracking_source="manual" if body.tracked and body.ats_type else None)
    db.add(c)
    audit(db, user.id, "company.create", "company", None, {"name": body.name})
    db.commit()
    return _out(c)


def _get(db: Session, cid: int) -> Company:
    c = db.get(Company, cid)
    if not c:
        raise HTTPException(404, "Company not found")
    return c


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _get(db, company_id)
    return _out(c, len(c.jobs))


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    c = _get(db, company_id)
    data = body.model_dump(exclude_unset=True)
    if "recruitment_email" in data:
        # Manually entered by the user (e.g. from the company's job ad): trusted by user confirmation.
        c.email_verified = bool(data["recruitment_email"])
        c.email_source_url = "manual entry"
    for k, v in data.items():
        setattr(c, k, v)
    if "name" in data:
        c.normalized_name = normalize_company_name(c.name)
    if {"ats_type", "ats_slug", "careers_url", "tracked"} & set(data):
        c.tracking_source = "manual"
        c.scan_error = None
    audit(db, user.id, "company.update", "company", c.id, {"fields": list(data)})
    db.commit()
    return _out(c, len(c.jobs))


@router.post("/{company_id}/enrich", response_model=CompanyOut)
def enrich(company_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _get(db, company_id)
    enrich_company(db, c)
    return _out(c, len(c.jobs))


@router.post("/{company_id}/scan-board")
def scan_board(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _get(db, company_id)
    if not c.ats_type:
        raise HTTPException(400, "This company has no job board configured")
    if not c.tracked:
        c.tracked, c.tracking_source = True, c.tracking_source or "manual"
        db.commit()
    stats = scan_company_boards(db, user.id, get_settings(db, user), company_ids=[c.id])
    db.refresh(c)
    if c.scan_error and stats.results == 0:
        raise HTTPException(400, c.scan_error)
    return {"found": stats.results, "new_jobs": stats.new_jobs, "duplicates": stats.duplicates,
            "filtered": stats.filtered, "board": c.ats_type, "slug": c.ats_slug}


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _get(db, company_id)
    db.delete(c)
    audit(db, user.id, "company.delete", "company", company_id)
    db.commit()
