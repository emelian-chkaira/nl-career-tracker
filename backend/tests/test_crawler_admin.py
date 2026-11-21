"""Crawler page API: editable policy, previews, companies / jobs CRUD, export, task controls, first-user-admin."""
import datetime as dt
from sqlalchemy import select, text
from app.core.config import settings
from app.models import Job, Company, Task, UserJob, User
from app.services import ingest_service as ing, policy_service

A = "/api/v1/admin"


def J(title, n=[0], **kw):
    n[0] += 1; return dict(title=title, location="Amsterdam, Netherlands", url=f"https://x.nl/{n[0]}", description=kw.get("desc", ""), posted_at=kw.get("posted"))


def admin(make_user): return make_user("admin@example.com")[0]


def test_policy_is_editable_saved_and_used_by_ingest(client, make_user, db, monkeypatch):
    ha, h = admin(make_user), make_user()[0]
    assert client.get(f"{A}/policy", headers=ha).json()["keep_domains"] == []
    assert client.put(f"{A}/policy", json={"keep_domains": ["mobile"], "max_job_age_days": 0, "delete_expired_after_days": 30}, headers=h).status_code == 403
    r = client.put(f"{A}/policy", json={"keep_domains": ["mobile"], "max_job_age_days": 0, "delete_expired_after_days": 30}, headers=ha).json()
    assert r["keep_domains"] == ["mobile"] and r["delete_expired_after_days"] == 30 and r["defaults"]["keep_domains"] == []
    c = ing.add_company(db, "Acme"); assert ing.store_jobs(db, c, [J("Flutter Developer"), J("Backend Engineer")]) == 1
    assert client.put(f"{A}/policy", json={"keep_domains": ["nonsense"]}, headers=ha).status_code == 400
    assert client.delete(f"{A}/policy", headers=ha).json()["keep_domains"] == []                       # back to env defaults
    assert ing.store_jobs(db, c, [J("Backend Engineer 2")]) == 1


def test_previews_change_nothing(client, make_user, db):
    ha = admin(make_user); c = ing.add_company(db, "Acme"); ing.store_jobs(db, c, [J("Backend Engineer"), J("Flutter Developer")]); db.commit()
    p = client.get(f"{A}/maintenance/clear_jobs/preview", headers=ha).json(); assert p["jobs_to_delete"] == 2
    assert client.get(f"{A}/maintenance/clear_all/preview", headers=ha).json()["companies_to_delete"] == 1
    assert client.get(f"{A}/maintenance/purge/preview", headers=ha).json() == {"nothing_to_do": 0} or "expired_to_delete" in client.get(f"{A}/maintenance/purge/preview", headers=ha).json()
    assert db.scalar(text("select count(*) from jobs")) == 2
    assert client.get(f"{A}/maintenance/nope/preview", headers=ha).status_code == 404


def test_companies_list_filter_edit_scan_bulk_delete(client, make_user, db):
    ha = admin(make_user)
    r = client.post(f"{A}/companies/bulk", json={"text": "Acme | https://acme.nl\nBeta, beta.io\nhttps://www.gamma.com\n# comment\n\nAcme", "scan": True}, headers=ha).json()
    assert r["added"] == 3 and r["already_known"] == 1 and r["scan_task_id"]
    names = {c["name"] for c in client.get(f"{A}/companies", headers=ha).json()["items"]}; assert names == {"Acme", "Beta", "Gamma"}
    cid = client.get(f"{A}/companies", params={"q": "acme"}, headers=ha).json()["items"][0]["id"]
    assert client.get(f"{A}/companies", params={"status": "never"}, headers=ha).json()["total"] == 3
    assert client.get(f"{A}/companies", params={"status": "bad"}, headers=ha).status_code == 400
    assert client.patch(f"{A}/companies/{cid}", json={"careers_url": "acme.nl/jobs", "notes": "check monthly"}, headers=ha).status_code == 200
    row = client.get(f"{A}/companies", params={"q": "acme"}, headers=ha).json()["items"][0]
    assert row["careers_url"] == "https://acme.nl/jobs" and row["notes"] == "check monthly"
    assert client.patch(f"{A}/companies/{cid}", json={"name": "Beta"}, headers=ha).status_code == 409
    t = client.post(f"{A}/companies/{cid}/scan", headers=ha).json()["task_id"]; assert db.get(Task, t).kind == "scan_company"
    assert client.delete(f"{A}/companies/{cid}", headers=ha).status_code == 204
    assert client.get(f"{A}/companies", headers=ha).json()["total"] == 2


def test_jobs_browse_bulk_and_permissions(client, make_user, db):
    ha, h = admin(make_user), make_user()[0]
    c = ing.add_company(db, "Acme"); ing.store_jobs(db, c, [J("Backend Engineer"), J("Flutter Developer"), J("iOS Developer")]); db.commit()
    jobs = client.get(f"{A}/jobs", params={"domain": "mobile"}, headers=h).json(); assert jobs["total"] == 2                       # operators can browse
    ids = [j["id"] for j in jobs["items"]]
    assert client.post(f"{A}/jobs/bulk", json={"action": "expire", "ids": ids[:1]}, headers=h).json()["changed"] == 1
    assert client.get(f"{A}/jobs", params={"status": "expired"}, headers=h).json()["total"] == 1
    assert client.post(f"{A}/jobs/bulk", json={"action": "reopen", "ids": ids[:1]}, headers=h).json()["changed"] == 1
    assert client.post(f"{A}/jobs/bulk", json={"action": "delete", "ids": ids}, headers=h).status_code == 403                       # deleting is admin-only
    assert client.post(f"{A}/jobs/bulk", json={"action": "delete", "domain": "mobile", "all_matching": True}, headers=ha).status_code == 400   # needs confirm
    assert client.post(f"{A}/jobs/bulk", json={"action": "delete", "domain": "mobile", "all_matching": True, "confirm": True}, headers=ha).json()["changed"] == 2
    assert client.get(f"{A}/jobs", params={"status": "all"}, headers=ha).json()["total"] == 1


def test_export_csv(client, make_user, db):
    ha = admin(make_user); c = ing.add_company(db, "Acme", website="https://acme.nl"); ing.store_jobs(db, c, [J("Backend Engineer, Senior")]); db.commit()
    r = client.get(f"{A}/export/jobs.csv", headers=ha); lines = r.text.strip().splitlines()
    assert r.headers["content-type"].startswith("text/csv") and lines[0].startswith("id,company,title") and '"Backend Engineer, Senior"' in lines[1]
    assert "Acme" in client.get(f"{A}/export/companies.csv", headers=ha).text and client.get(f"{A}/export/other.csv", headers=ha).status_code == 404


def test_task_cancel_and_clear(client, make_user, db):
    ha = admin(make_user); q = Task(kind="scan_all", status="queued"); r = Task(kind="scan_all", status="running"); d = Task(kind="embed", status="done"); db.add_all([q, r, d]); db.commit()
    assert client.post(f"{A}/tasks/{q.id}/cancel", headers=ha).status_code == 200 and client.post(f"{A}/tasks/{r.id}/cancel", headers=ha).status_code == 200
    db.expire_all(); assert db.get(Task, q.id).status == "failed" and db.get(Task, r.id).error == "cancelled by operator"
    assert client.delete(f"{A}/tasks", headers=ha).json()["removed"] == 3


def test_first_user_becomes_admin_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "first_user_admin", True)
    r1 = client.post("/api/v1/auth/register", json={"email": "first@example.com", "password": "correct-horse-1", "name": "A"}).json()
    r2 = client.post("/api/v1/auth/register", json={"email": "second@example.com", "password": "correct-horse-1", "name": "B"}).json()
    assert r1["user"]["role"] == "admin" and r2["user"]["role"] == "user"
