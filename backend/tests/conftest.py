"""Tests run against a throwaway Postgres database (needs the dev container: `docker compose up -d db`)."""
import os, sys, uuid
import psycopg

ADMIN = os.environ.get("TEST_ADMIN_DSN", "postgresql://careers:careers@localhost:5433/postgres")
DB = "careers_test"
with psycopg.connect(ADMIN, autocommit=True) as c:
    c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)"); c.execute(f"CREATE DATABASE {DB}")
os.environ["DATABASE_URL"] = f"postgresql+psycopg://careers:careers@localhost:5433/{DB}"
os.environ.update(CAREERS_DATA_DIR=os.path.join(os.path.dirname(__file__), ".tmp-data"), CAREERS_ADMIN_EMAILS="admin@example.com", CAREERS_RATE_LIMIT_PER_MIN="0", CAREERS_AUTH_RATE_LIMIT_PER_MIN="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import text
from app.core.db import engine, Base
import app.models  # noqa

with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector")); conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
Base.metadata.create_all(engine)


@pytest.fixture()
def db():
    from app.core.db import SessionLocal
    with SessionLocal() as s:
        yield s


@pytest.fixture(autouse=True)
def clean(request):
    yield
    if "keep_data" in request.keywords: return
    with engine.begin() as c:
        c.execute(text("TRUNCATE auth_tokens, notifications, email_outbox, saved_searches, user_jobs, refresh_tokens, users, job_skills, jobs, companies, tasks RESTART IDENTITY CASCADE"))
    from app.core import ratelimit; ratelimit.reset()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def make_user(client):
    def _make(email="user@example.com", password="correct-horse-1", name="Test User"):
        r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name}); assert r.status_code == 201, r.text
        return {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()
    return _make
