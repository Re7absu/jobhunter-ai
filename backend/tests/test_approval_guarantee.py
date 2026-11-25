"""The owner's requirement: nothing is ever sent or submitted without explicit approval of that specific
application, and every email is reviewed (approved in its final form) and confirmed before sending."""

import pytest

from app.models import Application, AutomationSettings, User
from app.services import workflow
from app.services.applications import ApplicationError
from app.services.pipeline import run_pipeline
from tests.test_workflow import fake_gmail, job_app  # noqa: F401  (fixtures)


def _approved(client, auth, app_id):
    email = client.post(f"/api/applications/{app_id}/generate-email", headers=auth, json={}).json()
    d = client.post(f"/api/applications/{app_id}/approve", headers=auth).json()
    assert d["status"] == "Approved"
    return email


def test_regenerate_after_approval_revokes_it(client, auth, job_app, fake_gmail):
    _, app_id = job_app
    v1 = _approved(client, auth, app_id)
    v2 = client.post(f"/api/applications/{app_id}/generate-email", headers=auth,
                     json={"instructions": "shorter"}).json()
    d = client.get(f"/api/applications/{app_id}", headers=auth).json()
    assert d["status"] == "Awaiting Approval"
    statuses = {e["id"]: e["status"] for e in d["emails"]}
    assert statuses[v1["id"]] == "rejected" and statuses[v2["id"]] == "draft"
    assert not any(e["status"] == "approved" for e in d["emails"])
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True}).status_code == 409
    assert fake_gmail == []
    # approving again approves exactly the newest version, and that is what gets sent
    client.post(f"/api/applications/{app_id}/approve", headers=auth)
    r = client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True})
    assert r.status_code == 200, r.text
    assert len(fake_gmail) == 1 and fake_gmail[0]["subject"] == v2["subject"]


def test_edit_after_approval_requires_new_approval(client, auth, job_app, fake_gmail):
    _, app_id = job_app
    email = _approved(client, auth, app_id)
    r = client.put(f"/api/emails/{email['id']}", headers=auth,
                   json={"subject": email["subject"], "body": email["body"] + "\nEdited."})
    assert r.json()["status"] == "draft"
    assert client.get(f"/api/applications/{app_id}", headers=auth).json()["status"] == "Awaiting Approval"
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True}).status_code == 409
    assert fake_gmail == []


@pytest.mark.parametrize("status", ["Approved", "Ready to Apply", "Applied"])
def test_guarded_statuses_cannot_be_set_manually(client, auth, job_app, status):
    _, app_id = job_app
    client.post(f"/api/applications/{app_id}/generate-email", headers=auth, json={})
    r = client.patch(f"/api/applications/{app_id}/status", headers=auth, json={"status": status})
    assert r.status_code == 409
    assert client.get(f"/api/applications/{app_id}", headers=auth).json()["status"] == "Awaiting Approval"


def test_recipient_change_after_approval_requires_new_approval(client, auth, job_app, fake_gmail):
    _, app_id = job_app
    _approved(client, auth, app_id)
    d = client.patch(f"/api/applications/{app_id}", headers=auth, json={"recipient_email": "jobs@verify.example.com"}).json()
    assert d["status"] == "Awaiting Approval"
    assert not any(e["status"] == "approved" for e in d["emails"])
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True}).status_code == 409
    assert fake_gmail == []


def test_send_requires_explicit_confirmation(client, auth, job_app, fake_gmail, db):
    _, app_id = job_app
    _approved(client, auth, app_id)
    assert client.post(f"/api/applications/{app_id}/send", headers=auth, json={}).status_code == 400
    user = db.query(User).first()
    app = db.get(Application, app_id)
    s = db.query(AutomationSettings).filter_by(user_id=user.id).one()
    with pytest.raises(ApplicationError, match="explicit confirmation"):
        workflow.send_application(db, user, app, s, user_confirmed=False)
    assert fake_gmail == []


def test_daily_run_never_sends_even_approved_emails(client, auth, job_app, fake_gmail, db, monkeypatch):
    _, app_id = job_app
    _approved(client, auth, app_id)
    user = db.query(User).first()
    user.gmail_token_encrypted = "connected"  # pretend Gmail is connected
    db.commit()
    monkeypatch.setattr("app.services.pipeline.run_discovery", lambda *a, **k: type("S", (), {"as_dict": lambda self: {}})())
    monkeypatch.setattr("app.services.pipeline.enrich_company", lambda db, c: c)
    monkeypatch.setattr("app.services.pipeline.validate_jobs", lambda db, s: {})
    monkeypatch.setattr("app.services.pipeline.check_replies", lambda db, u: 0)
    run = run_pipeline(db, user, "scheduled")
    assert run.status == "completed", run.error
    assert fake_gmail == []
    assert client.get(f"/api/applications/{app_id}", headers=auth).json()["status"] == "Approved"


def test_auto_send_setting_no_longer_exists(client, auth):
    s = client.get("/api/automation/settings", headers=auth).json()
    assert "auto_send_approved" not in s
    r = client.put("/api/automation/settings", headers=auth, json={"auto_send_approved": True})
    assert r.status_code == 200 and "auto_send_approved" not in r.json()


def test_followup_send_requires_confirmation(client, auth, job_app, fake_gmail, db):
    _, app_id = job_app
    _approved(client, auth, app_id)
    client.post(f"/api/applications/{app_id}/send", headers=auth, json={"confirm": True})
    fu_id = client.get("/api/followups", headers=auth).json()[0]["id"]
    client.post(f"/api/followups/{fu_id}/draft", headers=auth)
    assert client.post(f"/api/followups/{fu_id}/send", headers=auth, json={}).status_code == 400
    assert len(fake_gmail) == 1  # only the original application
