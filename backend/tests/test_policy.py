"""Storage policy (domains, max age), retention purge, clearing data, and the domain filter."""
import datetime as dt
from sqlalchemy import select, text
from app.core.config import settings
from app.crawler.domains import classify, parse
from app.models import Job, UserJob
from app.services import ingest_service as ing, maintenance_service as maint


def J(title, desc="", days_ago=None, n=[0]):
    n[0] += 1
    posted = (dt.date.today() - dt.timedelta(days=days_ago)).isoformat() if days_ago is not None else None
    return dict(title=title, location="Amsterdam, Netherlands", url=f"https://x.nl/{n[0]}", description=desc, posted_at=posted)


def test_classify_titles_and_descriptions():
    assert classify("Senior iOS Developer") == "mobile"
    assert classify("Flutter Engineer") == "mobile"
    assert classify("Backend Engineer (Python)") == "backend"
    assert classify("Full-Stack Developer") == "fullstack"
    assert classify("Data Engineer") == "data"
    assert classify("Software Engineer") == "software"                                   # generic title, no stack hint
    assert classify("Software Engineer", "spring microservices postgres rest api") == "backend"
    assert classify("Account Manager") == "other"
    assert parse("Mobile, backend, nonsense") == {"mobile", "backend"} and parse("") == set()


def test_only_configured_domains_are_stored(db, monkeypatch):
    c = ing.add_company(db, "Acme"); monkeypatch.setattr(settings, "keep_domains", "mobile")
    n = ing.store_jobs(db, c, [J("Flutter Developer"), J("Backend Engineer"), J("Data Engineer"), J("iOS Developer")]); db.commit()
    assert n == 2
    assert {j.domain for j in db.scalars(select(Job))} == {"mobile"}


def test_everything_stored_when_no_domain_filter(db, monkeypatch):
    c = ing.add_company(db, "Acme"); monkeypatch.setattr(settings, "keep_domains", "")
    assert ing.store_jobs(db, c, [J("Flutter Developer"), J("Backend Engineer")]) == 2


def test_old_postings_are_skipped(db, monkeypatch):
    c = ing.add_company(db, "Acme"); monkeypatch.setattr(settings, "max_job_age_days", 30)
    n = ing.store_jobs(db, c, [J("Backend Engineer", days_ago=5), J("Backend Developer", days_ago=90), J("Python Developer")]); db.commit()      # no date -> kept
    assert n == 2


def test_purge_deletes_old_and_long_expired_but_never_saved(db, make_user, monkeypatch):
    c = ing.add_company(db, "Acme"); ing.store_jobs(db, c, [J("Backend Engineer A", days_ago=2), J("Backend Engineer B", days_ago=2), J("Backend Engineer C", days_ago=2)]); db.commit()
    a, b, cc = db.scalars(select(Job).order_by(Job.id)).all()
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100)
    a.status, a.last_seen = "expired", old                                              # expired long ago -> deleted
    b.status, b.last_seen = "expired", old                                              # expired long ago but saved -> kept
    from app.models import User
    u = User(email="s@example.com", password_hash="x", name="s", is_active=True); db.add(u); db.flush(); db.add(UserJob(user_id=u.id, job_id=b.id)); db.commit()
    monkeypatch.setattr(settings, "delete_expired_after_days", 60)
    r = maint.purge_old(db)
    assert r["expired_deleted"] == 1
    assert {j.id for j in db.scalars(select(Job))} == {b.id, cc.id}


def test_prune_applies_current_policy_to_stored_jobs(db, monkeypatch):
    c = ing.add_company(db, "Acme"); monkeypatch.setattr(settings, "keep_domains", ""); ing.store_jobs(db, c, [J("Flutter Developer"), J("Backend Engineer"), J("Data Engineer")]); db.commit()
    monkeypatch.setattr(settings, "keep_domains", "mobile,backend")
    assert maint.prune_to_policy(db)["other_domains_deleted"] == 1
    assert sorted(j.domain for j in db.scalars(select(Job))) == ["backend", "mobile"]


def test_clear_jobs_and_all(db):
    c = ing.add_company(db, "Acme"); ing.store_jobs(db, c, [J("Backend Engineer")]); db.commit()
    assert maint.clear_jobs(db) == {"jobs_deleted": 1}
    assert db.scalar(text("select count(*) from companies")) == 1
    assert maint.clear_all(db)["companies_deleted"] == 1


def test_maintenance_endpoints_are_admin_only_and_need_confirmation(client, make_user):
    h, _ = make_user()
    assert client.post("/api/v1/admin/maintenance/purge", headers=h).status_code == 403          # operator but not admin
    ha, _ = make_user("admin@example.com")
    assert client.post("/api/v1/admin/maintenance/purge", headers=ha).status_code == 200
    assert client.post("/api/v1/admin/maintenance/clear_jobs", headers=ha).status_code == 400    # needs confirm
    assert client.post("/api/v1/admin/maintenance/clear_jobs", json={"confirm": True}, headers=ha).status_code == 200
    assert client.post("/api/v1/admin/maintenance/nope", headers=ha).status_code == 404


def test_search_filters_by_domain_and_returns_facet(db, client, monkeypatch):
    c = ing.add_company(db, "Acme"); monkeypatch.setattr(settings, "keep_domains", ""); ing.store_jobs(db, c, [J("Flutter Developer"), J("Backend Engineer")]); db.commit()
    r = client.get("/api/v1/jobs", params={"domain": "mobile"}).json()
    assert [j["title"] for j in r["items"]] == ["Flutter Developer"] and r["items"][0]["domain"] == "mobile"
    assert {f["value"] for f in r["facets"]["domain"]} == {"mobile"} or "mobile" in {f["value"] for f in r["facets"]["domain"]}
