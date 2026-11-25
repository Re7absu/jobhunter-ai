"""Company board auto-discovery, SmartRecruiters, cross-source de-duplication, politeness."""

import httpx
import pytest

from app.core.database import utcnow
from app.models import AutomationSettings, Company, Job, SearchHistory, User
from app.services import http_fetch
from app.services.discovery import company_boards, engine
from app.services.discovery.ats_detect import detect_board
from app.services.discovery.base import RawJob
from app.services.discovery.ingest import ingest_raw_job, normalize_url
from app.services.enrichment import track_careers_page
from app.services.pipeline import run_pipeline


def _ctx(db):
    user = db.query(User).first()
    return user, db.query(AutomationSettings).filter_by(user_id=user.id).one()


def jraw(**kw) -> RawJob:
    base = dict(title="Backend Developer", company_name="Acme Tech", source="jsearch", publisher="LinkedIn",
                source_url="https://www.linkedin.com/jobs/view/123?utm_source=google", location="Riyadh, Saudi Arabia",
                description="Python, FastAPI, PostgreSQL. 1-2 years of experience.", external_id="js-1",
                posted_at=utcnow())
    base.update(kw)
    return RawJob(**base)


# ---------------------------------------------------------------- detection & normalization
@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
    ("https://job-boards.eu.greenhouse.io/acme/jobs/9", ("greenhouse", "acme")),
    ("https://boards.greenhouse.io/embed/job_app?for=acme&token=5", ("greenhouse", "acme")),
    ("https://jobs.lever.co/acme/1a2b-3c", ("lever", "acme")),
    ("https://jobs.ashbyhq.com/acme/0f9e", ("ashby", "acme")),
    ("https://apply.workable.com/salla/j/C4BF5/", ("workable", "salla")),
    ("https://salla.workable.com/jobs/123", ("workable", "salla")),
    ("https://jobs.smartrecruiters.com/AcmeSA/7440001-backend-developer", ("smartrecruiters", "AcmeSA")),
    ("https://careers.smartrecruiters.com/AcmeSA", ("smartrecruiters", "AcmeSA")),
    ("https://www.linkedin.com/jobs/view/1", None),
    ("https://boards.greenhouse.io/embed/job_board", None),
    ("https://jobs.lever.co/", None),
])
def test_detect_board(url, expected):
    assert detect_board(url) == expected


def test_normalize_url_strips_only_tracking_params():
    assert normalize_url("HTTPS://Acme.com/jobs/1/?utm_source=x&gh_src=y&jobId=5#apply") == "https://acme.com/jobs/1?jobId=5"


# ---------------------------------------------------------------- auto-detection from search results
def test_board_auto_detected_from_apply_link_even_if_job_filtered(client, auth, db):
    user, s = _ctx(db)
    raw = jraw(title="Senior Staff Engineer", application_url="https://boards.greenhouse.io/acmetech/jobs/77?gh_src=li")
    res = ingest_raw_job(db, raw, user.id, s)
    db.commit()
    assert res.new_job is False and res.new_board is True  # senior role filtered, board still registered
    c = db.query(Company).one()
    assert (c.ats_type, c.ats_slug, c.tracked, c.tracking_source) == ("greenhouse", "acmetech", True, "auto")


def test_job_from_search_records_source_and_method(client, auth, db):
    user, s = _ctx(db)
    res = ingest_raw_job(db, jraw(), user.id, s)
    db.commit()
    job = db.get(Job, res.job.id)
    assert job.source == "jsearch" and job.publisher == "LinkedIn" and job.discovery_method == "search_api"
    assert job.source_url == "https://www.linkedin.com/jobs/view/123"  # tracking param removed
    assert job.discovered_at and job.updated_at and job.last_verified_at


# ---------------------------------------------------------------- cross-source de-duplication
def test_same_job_from_company_board_is_deduplicated(client, auth, db):
    user, s = _ctx(db)
    first = ingest_raw_job(db, jraw(), user.id, s)
    db.commit()
    board_raw = RawJob(title="Backend Developer - Riyadh", company_name="Acme Tech", source="smartrecruiters",
                       source_url="https://jobs.smartrecruiters.com/AcmeTech/744-backend-developer?oga=true",
                       location="Riyadh, Saudi Arabia", city="Riyadh", external_id="744",
                       description="Full description " * 40)
    second = ingest_raw_job(db, board_raw, user.id, s)
    db.commit()
    assert second.skipped_reason == "duplicate (other board)" and second.job.id == first.job.id
    job = db.get(Job, first.job.id)
    assert db.query(Job).count() == 1
    assert job.source == "jsearch"  # original source kept
    assert job.seen_sources[0]["source"] == "smartrecruiters"
    assert job.description.startswith("Full description")  # more complete description kept
    # seeing it again does not add a second sighting
    ingest_raw_job(db, board_raw, user.id, s)
    assert len(db.get(Job, first.job.id).seen_sources) == 1


def test_apply_link_matching_existing_board_url_is_duplicate(client, auth, db):
    user, s = _ctx(db)
    board = RawJob(title="Data Engineer", company_name="Beta", source="lever", source_url="https://jobs.lever.co/beta/1",
                   location="Jeddah", city="Jeddah", external_id="1", description="SQL, Airflow, 1 year of experience")
    ingest_raw_job(db, board, user.id, s)
    via_search = jraw(title="Data Engineer", company_name="Beta Company Ltd", location="Jeddah",
                      source_url="https://www.bayt.com/en/job/99", external_id="js-99",
                      application_url="https://jobs.lever.co/beta/1?lever-source=bayt")
    res = ingest_raw_job(db, via_search, user.id, s)
    assert res.skipped_reason == "duplicate" and db.query(Job).count() == 1


# ---------------------------------------------------------------- SmartRecruiters
def test_smartrecruiters_fetcher(monkeypatch):
    calls = []

    def fake_get_json(url, method="GET", **kw):
        calls.append((url, kw.get("params")))
        if url.endswith("/postings"):
            return {"totalFound": 3, "content": [
                {"id": "1", "name": "Backend Engineer", "releasedDate": "2026-11-20T10:00:00.000Z",
                 "location": {"city": "Riyadh", "country": "sa", "fullLocation": "Riyadh, Saudi Arabia"},
                 "typeOfEmployment": {"label": "Full-time"}, "experienceLevel": {"label": "Entry Level"}},
                {"id": "2", "name": "Backend Engineer", "location": {"city": "Dammam", "country": "sa"}},
                {"id": "3", "name": "Accountant", "location": {"city": "Riyadh", "country": "sa"}},
            ]}
        return {"postingUrl": "https://jobs.smartrecruiters.com/AcmeSA/1-backend-engineer",
                "applyUrl": "https://jobs.smartrecruiters.com/AcmeSA/1-backend-engineer?oga=true",
                "jobAd": {"sections": {"jobDescription": {"text": "<p>Build APIs in <b>Python</b></p>"},
                                       "qualifications": {"text": "<ul><li>FastAPI</li></ul>"}}}}

    monkeypatch.setattr(company_boards, "_get_json", fake_get_json)
    monkeypatch.setattr(company_boards.time, "sleep", lambda s: None)
    jobs = company_boards.smartrecruiters(Company(name="Acme SA", ats_type="smartrecruiters", ats_slug="AcmeSA"))
    assert [j.external_id for j in jobs] == ["1"]  # Dammam & non-target roles skipped without detail calls
    j = jobs[0]
    assert j.source == "smartrecruiters" and j.city == "Riyadh" and "FastAPI" in j.description
    assert "Entry Level" in j.description and j.posted_at.year == 2026
    assert calls[0][1]["country"] == "sa" and len(calls) == 2  # 1 list + 1 detail call


# ---------------------------------------------------------------- board scanning
def test_scan_boards_once_per_window_and_logs_errors(client, auth, db, monkeypatch):
    user, s = _ctx(db)
    ok = Company(name="Acme SA", normalized_name="acme sa", ats_type="smartrecruiters", ats_slug="AcmeSA",
                 tracked=True, tracking_source="auto")
    bad = Company(name="Broken Co", normalized_name="broken co", ats_type="lever", ats_slug="broken",
                  tracked=True, tracking_source="manual")
    db.add_all([ok, bad])
    db.commit()
    monkeypatch.setitem(company_boards.ATS_FETCHERS, "smartrecruiters", lambda c: [RawJob(
        title="AI Engineer", company_name=c.name, source="smartrecruiters", city="Riyadh", location="Riyadh",
        source_url="https://jobs.smartrecruiters.com/AcmeSA/9-ai-engineer", external_id="9",
        description="LLMs, Python. 0-2 years of experience.")])

    def broken(c):
        raise company_boards.SourceError("https://api.lever.co/v0/postings/broken: HTTP 404")

    monkeypatch.setitem(company_boards.ATS_FETCHERS, "lever", broken)
    stats = engine.scan_company_boards(db, user.id, s)
    assert stats.boards_scanned == 2 and stats.new_jobs == 1
    job = db.query(Job).one()
    assert job.discovery_method == "ats_board_auto" and job.source == "smartrecruiters"
    db.refresh(bad)
    assert "HTTP 404" in bad.scan_error and bad.last_scanned_at
    assert db.query(SearchHistory).filter_by(source="lever", status="error").count() == 1
    # within the re-scan window nothing is requested again
    assert engine.scan_company_boards(db, user.id, s).boards_scanned == 0


def test_careers_page_switches_to_linked_ats_or_stops_when_empty(client, auth, db, monkeypatch):
    user, s = _ctx(db)
    linked = Company(name="Gamma", normalized_name="gamma", careers_url="https://gamma.sa/careers",
                     ats_type="careers_page", tracked=True, tracking_source="auto", domain="gamma.sa")
    empty = Company(name="Delta", normalized_name="delta", careers_url="https://delta.sa/careers",
                    ats_type="careers_page", tracked=True, tracking_source="auto", domain="delta.sa")
    db.add_all([linked, empty])
    db.commit()
    pages = {"https://gamma.sa/careers": '<a href="https://jobs.lever.co/gamma">Open roles</a>',
             "https://delta.sa/careers": "<h1>Join us</h1><p>Send your CV</p>"}

    def fake_get(url, timeout=15):
        return httpx.Response(200, text=pages[url], request=httpx.Request("GET", url))

    monkeypatch.setattr(company_boards, "polite_get", fake_get)
    monkeypatch.setitem(company_boards.ATS_FETCHERS, "lever", lambda c: [RawJob(
        title="Product Analyst", company_name=c.name, source="lever", city="Jeddah", location="Jeddah",
        source_url="https://jobs.lever.co/gamma/abc", external_id="abc", description="SQL, product analytics")])
    stats = engine.scan_company_boards(db, user.id, s)
    db.refresh(linked)
    db.refresh(empty)
    assert (linked.ats_type, linked.ats_slug) == ("lever", "gamma") and stats.new_jobs == 1
    assert empty.tracked is False and "JobPosting" in empty.scan_error


def test_enrichment_tracks_careers_pages_safely():
    same_site = Company(name="A", domain="acme.sa", careers_url="https://careers.acme.sa/jobs")
    ats = Company(name="B", domain="b.sa", careers_url="https://apply.workable.com/bco/")
    off_site = Company(name="C", domain="c.sa", careers_url="https://c.taleo.net/careersection/jobs")
    assert track_careers_page(same_site) and same_site.ats_type == "careers_page" and same_site.tracking_source == "auto"
    assert track_careers_page(ats) and (ats.ats_type, ats.ats_slug) == ("workable", "bco")
    assert not track_careers_page(off_site) and not off_site.tracked


# ---------------------------------------------------------------- politeness
def test_throttle_spaces_requests_per_host(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http_fetch.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(http_fetch, "_robots", lambda origin: None)
    monkeypatch.setattr(http_fetch.settings, "CRAWL_MIN_DELAY_SECONDS", 2.0)
    http_fetch._last_hit.clear()
    http_fetch.throttle("https://slow.example/a")
    http_fetch.throttle("https://slow.example/b")
    http_fetch.throttle("https://other.example/a")
    assert len(sleeps) == 1 and 1.5 < sleeps[0] <= 2.0


def test_robots_disallow_blocks_fetch(monkeypatch):
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /careers"])
    monkeypatch.setattr(http_fetch, "_robots", lambda origin: rp)
    monkeypatch.setattr(http_fetch.httpx, "get", lambda *a, **k: pytest.fail("must not fetch"))
    assert http_fetch.polite_get("https://blocked.example/careers") is None


# ---------------------------------------------------------------- end-to-end: search -> board -> matching, no sending
def test_pipeline_discovers_board_jobs_and_matches_them(client, auth, with_cv, db, monkeypatch):
    class FakeSearch:
        name = "jsearch"

        def is_configured(self):
            return True

        def search(self, q):
            if q.language != "en" or q.title != "Backend Developer" or q.city != "Riyadh":
                return []
            return [jraw(application_url="https://jobs.smartrecruiters.com/AcmeTech/1-backend-developer")]

    sent = []
    monkeypatch.setattr(engine, "AGGREGATORS", [FakeSearch()])
    monkeypatch.setattr("app.services.pipeline.enrich_company", lambda db, c: c)
    monkeypatch.setattr("app.services.pipeline.validate_jobs", lambda db, s: {})
    monkeypatch.setattr("app.services.gmail_service.send_email", lambda *a, **k: sent.append(a))
    monkeypatch.setitem(company_boards.ATS_FETCHERS, "smartrecruiters", lambda c: [
        RawJob(title="Backend Developer", company_name=c.name, source="smartrecruiters", city="Riyadh",
               location="Riyadh", source_url="https://jobs.smartrecruiters.com/AcmeTech/1-backend-developer",
               external_id="1", description="Python FastAPI PostgreSQL, 1 year of experience"),
        RawJob(title="Data Engineer", company_name=c.name, source="smartrecruiters", city="Jeddah",
               location="Jeddah", source_url="https://jobs.smartrecruiters.com/AcmeTech/2-data-engineer",
               external_id="2", description="SQL, Python, ETL. 0-2 years of experience"),
    ])
    user, s = _ctx(db)
    s.max_queries_per_run = 200
    db.commit()
    run = run_pipeline(db, user, "manual")
    assert run.status == "completed", run.error
    assert run.stats["discovery"]["boards_detected"] == 1
    boards = run.stats["company_boards"]
    assert boards["boards_scanned"] == 1 and boards["new_jobs"] == 1 and boards["duplicates"] == 1
    assert db.query(Job).count() == 2 and run.stats["analyzed"] == 2  # CV matching applied to board jobs too
    r = client.get("/api/jobs", headers=auth, params={"discovery_method": "ats_board"}).json()
    assert r["total"] == 1 and r["items"][0]["discovery_method"] == "ats_board_auto"
    assert r["items"][0]["title"] == "Data Engineer"
    dup = client.get("/api/jobs", headers=auth, params={"source": "jsearch"}).json()["items"][0]
    assert dup["seen_sources"][0]["source"] == "smartrecruiters"
    assert sent == []  # discovery never sends anything
