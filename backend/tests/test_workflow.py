import pytest

from app.models import Application, AutomationSettings, Company, EmailHistory, User
from app.models.enums import match_category
from app.services import gmail_service
from app.services.discovery import engine as discovery_engine
from app.services.discovery.ingest import ingest_raw_job
from app.services.llm import set_llm
from app.services.pipeline import run_pipeline
from tests.conftest import FakeLLM
from tests.test_discovery import raw


@pytest.fixture
def job_app(client, auth, with_cv, db):
    user = db.query(User).first()
    s = db.query(AutomationSettings).filter_by(user_id=user.id).one()
    res = ingest_raw_job(db, raw(), user.id, s)
    company = db.query(Company).one()
    company.recruitment_email, company.email_verified = "careers@acme.example", True
    company.description = "Acme builds logistics software for Saudi retailers."
    db.commit()
    return res.job.id, db.query(Application).one().id


@pytest.fixture
def fake_gmail(monkeypatch):
    sent = []

    def _send(db, user, to, subject, body, attachment=None, thread_id=None, in_reply_to=None):
        sent.append({"to": to, "subject": subject, "attachment": attachment, "thread_id": thread_id})
        return {"id": f"msg-{len(sent)}", "threadId": "thread-1"}

    monkeypatch.setattr(gmail_service, "send_email", _send)
    return sent


def test_match_categories():
    assert match_category(85) == "Excellent Match"
    assert match_category(65) == "Good Match"
    assert match_category(50) == "Potential Match"
    assert match_category(10) == "Low Match"


def test_heuristic_analysis(client, auth, job_app):
    job_id, app_id = job_app
    m = client.post(f"/api/jobs/{job_id}/analyze", headers=auth).json()
    assert m["method"] == "heuristic"
    assert {"Python", "FastAPI", "PostgreSQL"} <= set(m["matching_skills"])
    assert m["score"] >= 65 and m["should_apply"]
    assert client.get(f"/api/applications/{app_id}", headers=auth).json()["status"] == "Analyzed"


def test_llm_analysis_guards_matching_skills(client, auth, job_app):
    job_id, _ = job_app
    set_llm(FakeLLM({"senior technical recruiter": {
        "score": 82, "required_skills": ["Python", "FastAPI", "Kubernetes"],
        "matching_skills": ["Python", "FastAPI", "Kubernetes"], "missing_skills": ["Kubernetes"],
        "transferable_skills": [], "explanation": "Strong backend fit.", "recommendation": "apply"}}))
    m = client.post(f"/api/jobs/{job_id}/analyze", headers=auth).json()
    assert m["score"] == 82 and m["category"] == "Excellent Match"
    assert "Kubernetes" not in m["matching_skills"]  # not in CV -> cannot be "matching"


def test_full_email_flow_send_once(client, auth, job_app, fake_gmail, db):
    job_id, app_id = job_app
    client.post(f"/api/jobs/{job_id}/analyze", headers=auth)
    email = client.post(f"/api/applications/{app_id}/generate-email", headers=auth, json={}).json()
    assert email["subject"] == "Application for Backend Developer – Rehab Bakheet"
    assert "Acme Tech" in email["body"] and email["generation_method"] == "template"
    detail = client.get(f"/api/applications/{app_id}", headers=auth).json()
    assert detail["status"] == "Awaiting Approval" and detail["method"] == "email"

    # cannot send before approval
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True}).status_code == 409
    # edit, approve, then send requires explicit confirm
    client.put(f"/api/emails/{email['id']}", headers=auth, json={"subject": email["subject"], "body": email["body"] + "\nThanks."})
    assert client.post(f"/api/applications/{app_id}/approve", headers=auth).json()["status"] == "Approved"
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": False}).status_code == 400
    r = client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "Applied" and d["applied_at"]
    assert fake_gmail[0]["to"] == "careers@acme.example"
    assert fake_gmail[0]["attachment"][1] == "cv.docx"
    eh = db.query(EmailHistory).one()
    assert eh.gmail_message_id == "msg-1" and eh.status == "sent"
    assert [h["to_status"] for h in d["history"]][-1] == "Applied"
    assert len(d["follow_ups"]) == 1

    # never twice
    assert client.post(f"/api/applications/{app_id}/approve", headers=auth).status_code == 409
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True}).status_code == 409
    assert len(fake_gmail) == 1

    # dashboard & reports
    k = client.get("/api/analytics/overview", headers=auth).json()
    assert k["applications_today"] == 1 and k["total_companies"] == 1
    today = client.get("/api/reports/contacted", headers=auth).json()
    assert today["count"] == 1 and today["companies"][0]["company"] == "Acme Tech"
    charts = client.get("/api/analytics/charts", headers=auth).json()
    assert charts["applications_by_city"] == [{"city": "Riyadh", "count": 1}]
    csv = client.get("/api/exports/applications.csv", headers=auth)
    assert csv.status_code == 200 and "Acme Tech" in csv.content.decode("utf-8-sig")
    xlsx = client.get("/api/exports/applications.xlsx", headers=auth)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"


def test_daily_cap(client, auth, job_app, fake_gmail):
    job_id, app_id = job_app
    client.put("/api/automation/settings", headers=auth, json={"max_daily_applications": 0})
    client.post(f"/api/applications/{app_id}/generate-email", headers=auth, json={})
    client.post(f"/api/applications/{app_id}/approve", headers=auth)
    r = client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True})
    assert r.status_code == 409 and "limit" in r.json()["detail"]
    assert fake_gmail == []


def test_online_application_flow(client, auth, job_app, db):
    job_id, app_id = job_app
    c = db.query(Company).one()
    c.recruitment_email, c.email_verified = None, False
    db.commit()
    client.post(f"/api/applications/{app_id}/generate-email", headers=auth, json={})
    d = client.post(f"/api/applications/{app_id}/approve", headers=auth).json()
    assert d["status"] == "Ready to Apply" and d["method"] == "online"
    assert client.post(f"/api/applications/{app_id}/mark-applied", headers=auth, json={"confirm": False}).status_code == 400
    d = client.post(f"/api/applications/{app_id}/mark-applied", headers=auth, json={"confirm": True}).json()
    assert d["status"] == "Applied"


def test_manual_status_and_history(client, auth, job_app):
    _, app_id = job_app
    d = client.patch(f"/api/applications/{app_id}/status", headers=auth,
                     json={"status": "Interview Scheduled", "note": "HR call", "interview_at": "2026-12-01T10:00:00"}).json()
    assert d["status"] == "Interview Scheduled" and d["interview_at"].startswith("2026-12-01")
    assert d["history"][-1]["note"] == "HR call"
    assert client.patch(f"/api/applications/{app_id}/status", headers=auth, json={"status": "Bogus"}).status_code == 422


def test_pipeline_end_to_end_with_fake_source(client, auth, with_cv, db, monkeypatch):
    class FakeSource:
        name = "jsearch"

        def is_configured(self):
            return True

        def search(self, q):
            slug = q.text.replace(" ", "-")
            return [raw(title=q.title, source_url=f"https://acme.example/jobs/{slug}", external_id=slug,
                        location=q.city)] if q.language == "en" and q.title == "Backend Developer" else []

    monkeypatch.setattr(discovery_engine, "AGGREGATORS", [FakeSource()])
    monkeypatch.setattr("app.services.pipeline.enrich_company", lambda db, c: c)
    monkeypatch.setattr("app.services.pipeline.validate_jobs", lambda db, s: {})
    user = db.query(User).first()
    s = db.query(AutomationSettings).filter_by(user_id=user.id).one()
    s.max_queries_per_run = 200
    db.commit()
    run = run_pipeline(db, user, "manual")
    assert run.status == "completed", run.error
    assert run.stats["discovery"]["new_jobs"] == 2  # Riyadh + Jeddah
    assert run.stats["analyzed"] == 2 and run.stats["emails_generated"] == 2  # method=online via apply URL
    queue = client.get("/api/applications", headers=auth, params={"status": "Awaiting Approval"}).json()
    assert queue["total"] == 2
    assert client.get("/api/reports/daily", headers=auth).json()[0]["new_jobs"] == 2
    # pause blocks everything
    client.post("/api/automation/pause", headers=auth)
    db.refresh(s)
    assert run_pipeline(db, user, "manual").status == "skipped"
