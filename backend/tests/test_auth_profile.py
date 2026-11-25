from app.services.cv_parser import validate_against_text
from app.services.llm import set_llm
from tests.conftest import CV_PARAGRAPHS, FakeLLM, make_docx


def test_register_login_me(client, auth):
    me = client.get("/api/auth/me", headers=auth).json()
    assert me["email"] == "owner@example.com"
    r = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "supersecret1"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong-pass"}).status_code == 401
    # registration closes after the first account
    r = client.post("/api/auth/register", json={"email": "x@example.com", "full_name": "X", "password": "supersecret1"})
    assert r.status_code == 403


def test_requires_auth(client):
    assert client.get("/api/applications").status_code == 401


def test_cv_upload_heuristic_extracts_only_real_skills(client, auth, with_cv):
    skills = {s["name"] for s in with_cv["skills"]}
    assert {"Python", "FastAPI", "PostgreSQL", "React", "Next.js", "TypeScript"} <= skills
    assert "Kubernetes" not in skills and "Java" not in skills
    assert with_cv["email"] == "rehab.test@example.com"
    assert with_cv["active_cv_id"] is not None
    cvs = client.get("/api/cv", headers=auth).json()
    assert cvs[0]["parse_status"] == "parsed" and cvs[0]["parse_method"] == "heuristic"
    # encrypted at rest but downloadable by the owner
    r = client.get(f"/api/cv/{cvs[0]['id']}/download", headers=auth)
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_rejects_non_cv_files(client, auth):
    r = client.post("/api/cv/upload", headers=auth, files={"file": ("x.txt", b"hello world" * 20, "text/plain")})
    assert r.status_code == 400


def test_llm_extraction_hallucinations_are_dropped(client, auth):
    fake = FakeLLM({"extract structured data from a CV": {
        "full_name": "Rehab Bakheet", "email": "rehab.test@example.com",
        "skills": [{"name": "FastAPI"}, {"name": "Kubernetes"}, {"name": "PostgreSQL"}],
        "experience": [{"company": "Sanaam", "title": "Product Engineer Intern"},
                       {"company": "Google", "title": "Staff Engineer"}],
        "education": [{"institution": "King Abdulaziz University", "degree": "Bachelor of Science"}],
        "certifications": [{"name": "AWS Solutions Architect"}],
        "projects": [], "languages": [], "years_experience": 1,
    }})
    set_llm(fake)
    r = client.post("/api/cv/upload", headers=auth, files={"file": ("cv.docx", make_docx(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    p = r.json()
    names = {s["name"] for s in p["skills"]}
    assert "Kubernetes" not in names and "FastAPI" in names
    assert [e["company"] for e in p["experience"]] == ["Sanaam"]
    assert p["certifications"] == []
    assert any("Kubernetes" in w for w in p["extraction_warnings"])


def test_validate_against_text_unit():
    text = "\n".join(CV_PARAGRAPHS)
    data, warnings = validate_against_text({"skills": [{"name": "Rust"}, {"name": "python"}]}, text)
    assert [s["name"] for s in data["skills"]] == ["python"]
    assert warnings


def test_manual_skill_and_profile_update(client, auth, with_cv):
    r = client.post("/api/profile/skills", headers=auth, json={"name": "docker"})
    assert r.status_code == 200 and r.json()["name"] == "Docker"
    r = client.put("/api/profile", headers=auth, json={"target_roles": ["Backend Developer"], "location": "Riyadh"})
    assert r.json()["target_roles"] == ["Backend Developer"]
