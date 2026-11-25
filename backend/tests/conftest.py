import io
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="jobhunter-test-")
# Set TEST_DATABASE_URL (e.g. a throwaway PostgreSQL database) to run the suite against Postgres.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(Path(_TMP, "storage"))
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["RAPIDAPI_KEY"] = ""
os.environ["SERPAPI_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm import set_llm  # noqa: E402

CV_PARAGRAPHS = [
    "Rehab Bakheet",
    "Computer Science Graduate | Backend & AI Engineer",
    "rehab.test@example.com | +966 50 000 0000 | linkedin.com/in/rehab-test | Riyadh",
    "Summary",
    "Computer Science graduate building backend services and AI integrations.",
    "Experience",
    "Product Engineer Intern - Sanaam (2024 - 2025)",
    "Built REST APIs with FastAPI and PostgreSQL; integrated LLMs and AI agents into product workflows.",
    "Education",
    "Bachelor of Science in Computer Science - King Abdulaziz University",
    "Projects",
    "Job tracker dashboard using React, TypeScript and Next.js",
    "Skills",
    "Python, JavaScript, TypeScript, React, Next.js, FastAPI, SQL, PostgreSQL, Data Analysis, Data Engineering",
]


def make_docx(paragraphs=CV_PARAGRAPHS) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    set_llm(None)
    from app.services.llm import LLMClient

    set_llm(LLMClient(api_key=""))  # heuristics unless a test injects a fake LLM
    yield
    set_llm(None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/register", json={"email": "owner@example.com", "full_name": "Rehab Bakheet",
                                                "password": "supersecret1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def with_cv(client, auth):
    r = client.post("/api/cv/upload", headers=auth,
                    files={"file": ("cv.docx", make_docx(),
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 200, r.text
    return r.json()


class FakeLLM:
    """Deterministic stand-in for OpenAI, keyed on the system prompt."""

    available = True
    model = "fake-llm"

    def __init__(self, responses: dict[str, dict]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def json_completion(self, system, user, **_):
        self.calls.append((system, user))
        for key, resp in self.responses.items():
            if key in system:
                return resp
        raise AssertionError(f"unexpected LLM call: {system[:60]}")
