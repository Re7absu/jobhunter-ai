from datetime import timedelta

from app.core.database import utcnow
from app.models import Application, AutomationSettings, Company, Job, User
from app.services.discovery.base import RawJob, SearchQuery
from app.services.discovery.company_boards import extract_jobpostings
from app.services.discovery.engine import build_query_plan
from app.services.discovery.ingest import ingest_raw_job
from app.services.enrichment import email_matches_domain, extract_emails, rank_email
from app.services.keywords import classify_category, detect_city, detect_experience_level, parse_min_years


def _settings(db, client, auth):
    user = db.query(User).first()
    return user, db.query(AutomationSettings).filter_by(user_id=user.id).one()


def raw(**kw) -> RawJob:
    base = dict(title="Backend Developer", company_name="Acme Tech", source="jsearch",
                source_url="https://acme.example/careers/backend-1", location="Riyadh, Saudi Arabia",
                description="We need Python, FastAPI and PostgreSQL. 1-2 years of experience.",
                company_website="https://www.acme.example", external_id="j1", posted_at=utcnow())
    base.update(kw)
    return RawJob(**base)


def test_ingest_creates_company_job_application_and_dedupes(client, auth, db):
    user, s = _settings(db, client, auth)
    r1 = ingest_raw_job(db, raw(), user.id, s)
    db.commit()
    assert r1.new_job and r1.new_company
    job = db.get(Job, r1.job.id)
    assert job.city == "Riyadh" and job.category == "technology" and job.experience_level == "junior"
    assert {r.name for r in job.requirements if r.requirement_type == "skill"} >= {"Python", "FastAPI", "PostgreSQL"}
    company = db.query(Company).one()
    assert company.domain == "acme.example"
    app = db.query(Application).one()
    assert app.status == "Discovered"

    # same URL -> duplicate
    assert ingest_raw_job(db, raw(), user.id, s).skipped_reason == "duplicate"
    # same job on another board (different URL/id) -> cross-board duplicate
    r3 = ingest_raw_job(db, raw(source="serpapi", source_url="https://bayt.example/job/99", external_id="x9",
                                company_website=None, company_name="Acme Tech Co."), user.id, s)
    assert r3.skipped_reason == "duplicate (other board)"
    assert db.query(Job).count() == 1 and db.query(Company).count() == 1


def test_ingest_filters(client, auth, db):
    user, s = _settings(db, client, auth)
    assert ingest_raw_job(db, raw(location="Dammam", source_url="https://a.example/1", external_id="1"),
                          user.id, s).skipped_reason.startswith("city")
    assert ingest_raw_job(db, raw(title="Senior Staff Backend Engineer", source_url="https://a.example/2",
                                  external_id="2"), user.id, s).skipped_reason.startswith("experience level")
    assert ingest_raw_job(db, raw(title="Sales Executive", source_url="https://a.example/3", external_id="3"),
                          user.id, s).skipped_reason == "outside target categories"
    assert ingest_raw_job(db, raw(source_url="not-a-url", external_id="4"), user.id, s).skipped_reason == "invalid source url"
    old = raw(source_url="https://a.example/5", external_id="5", posted_at=utcnow() - timedelta(days=90))
    assert ingest_raw_job(db, old, user.id, s).skipped_reason == "posting too old"
    # Arabic posting in Jeddah is accepted
    ar = raw(title="مطور باك اند", location="جدة", source_url="https://a.example/6", external_id="6")
    assert ingest_raw_job(db, ar, user.id, s).new_job


def test_keyword_helpers():
    assert detect_city("Jiddah, Makkah") == "Jeddah"
    assert detect_city("الرياض") == "Riyadh"
    assert classify_category("Associate Product Manager") == "product_management"
    assert classify_category("مهندس بيانات") == "technology"
    assert classify_category("Accountant") is None
    assert detect_experience_level("Software Engineering Intern") == "internship"
    assert detect_experience_level("Cooperative Training - IT") == "coop"
    assert detect_experience_level("Graduate Development Program") == "graduate"
    assert detect_experience_level("Senior Data Engineer") == "senior"
    assert parse_min_years("Minimum 3 years of experience in Java")[0] == 3


def test_query_plan_covers_titles_both_languages(client, auth, db):
    user, s = _settings(db, client, auth)
    plan = build_query_plan(db, user.id, s)
    texts = {q.text for q in plan}
    assert "Backend Developer in Riyadh, Saudi Arabia" in texts
    assert "Product Owner in Jeddah, Saudi Arabia" in texts
    assert any("الرياض" in t for t in texts)
    assert SearchQuery("Data Engineer", "Jeddah", "ar").text.endswith("جدة")


def test_jsonld_extraction():
    html = """<html><script type="application/ld+json">{"@context":"https://schema.org","@graph":[
      {"@type":"JobPosting","title":"Data Engineer","datePosted":"2026-11-01",
       "jobLocation":{"@type":"Place","address":{"addressLocality":"Riyadh","addressCountry":"SA"}},
       "description":"<p>Airflow, SQL</p>","url":"/jobs/1"}]}</script></html>"""
    jps = extract_jobpostings(html)
    assert len(jps) == 1 and jps[0]["title"] == "Data Engineer"


def test_email_extraction_rules():
    html = '<a href="mailto:careers@acme.example">Jobs</a> contact info@acme.example or john@gmail.com'
    emails = extract_emails(html)
    assert {"careers@acme.example", "info@acme.example", "john@gmail.com"} <= emails
    valid = sorted((e for e in emails if email_matches_domain(e, "acme.example")), key=rank_email)
    assert valid[0] == "careers@acme.example"
    assert not email_matches_domain("john@gmail.com", "acme.example")
