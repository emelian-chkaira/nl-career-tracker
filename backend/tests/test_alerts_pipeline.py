import datetime as dt
from app.models import SavedSearch, Notification, EmailOutbox, Job
from app.services import ingest_service as ing, alert_service


def _job(db, title, loc="Eindhoven, Netherlands"):
    c = ing.add_company(db, "Alert Co"); db.flush()
    ing.store_jobs(db, c, [dict(title=title, location=loc, url=f"https://a.nl/{title.replace(' ', '-')}", description="flutter dart", posted_at=None)]); db.commit()


def test_alert_creates_notification_and_email(client, make_user, db):
    h, _ = make_user()
    r = client.post("/api/v1/me/searches", headers=h, json={"name": "Flutter NL", "params": {"q": "flutter", "mode": "keyword"}, "alert_frequency": "daily"}); assert r.status_code == 201
    sid = r.json()["id"]
    s = db.get(SavedSearch, sid); s.last_run_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2); db.commit()
    _job(db, "Flutter Developer")
    assert alert_service.run_due(db) == 1
    n = client.get("/api/v1/me/notifications", headers=h).json()
    assert n["unread"] == 1 and "Flutter NL" in n["items"][0]["title"] and n["items"][0]["data"]["job_ids"]
    assert db.query(EmailOutbox).filter(EmailOutbox.subject.like('%Flutter%')).count() == 1
    assert alert_service.run_due(db) == 0                                           # not due again yet, and nothing new
    client.post(f"/api/v1/me/notifications/{n['items'][0]['id']}/read", headers=h)
    assert client.get("/api/v1/me/notifications", headers=h).json()["unread"] == 0
    assert alert_service.send_outbox(db) == 0 and db.query(EmailOutbox).first().status == "skipped"   # no SMTP configured


def test_alert_off_and_ownership(client, make_user, db):
    h1, _ = make_user("a@example.com"); h2, _ = make_user("b@example.com")
    sid = client.post("/api/v1/me/searches", headers=h1, json={"name": "x", "params": {"q": "flutter"}, "alert_frequency": "off"}).json()["id"]
    assert client.patch(f"/api/v1/me/searches/{sid}", headers=h2, json={"name": "hack"}).status_code == 404
    assert client.delete(f"/api/v1/me/searches/{sid}", headers=h2).status_code == 404
    assert client.post("/api/v1/me/searches", headers=h1, json={"name": "bad", "params": {"limit": 999}}).status_code == 422
    assert client.get("/api/v1/me/searches").status_code == 401


def test_pipeline_is_per_user(client, make_user, db):
    _job(db, "Flutter Developer"); jid = db.query(Job).first().id
    h1, _ = make_user("a@example.com"); h2, _ = make_user("b@example.com")
    assert client.put(f"/api/v1/me/jobs/{jid}", headers=h1, json={"stage": "applied", "notes": "sent CV"}).status_code == 200
    assert client.get("/api/v1/me/pipeline", headers=h1).json()["items"][0]["stage"] == "applied"
    assert client.get("/api/v1/me/pipeline", headers=h2).json()["items"] == []
    assert client.get(f"/api/v1/jobs/{jid}", headers=h1).json()["stage"] == "applied"
    assert client.put(f"/api/v1/me/jobs/{jid}", headers=h1, json={"stage": "nonsense"}).status_code == 400


def test_dashboard_overview(client, db):
    c = ing.add_company(db, "Dash Co"); db.flush()
    ing.store_jobs(db, c, [dict(title="Flutter Developer", location="Eindhoven, Netherlands", url="https://d.nl/1", description="flutter dart", posted_at=None),
                           dict(title="Data Engineer", location="Amsterdam, Netherlands", url="https://d.nl/2", description="python", posted_at=None)]); db.commit()
    d = client.get("/api/v1/analytics/overview", params={"days": 31}).json()
    assert d["kpi"]["open_jobs"] == 2 and any(c["name"] == "Amsterdam" for c in d["cities"]) and any(s["name"] == "flutter" for s in d["skills"]) and len(d["daily"]) >= 30


def test_cv_endpoints_anonymous(client, db):
    _job(db, "Flutter Developer"); jid = db.query(Job).first().id
    txt = "Jane Doe\njane@example.com\n\nSkills\nFlutter, Dart\n\nExperience\nMobile Intern - Acme  2025 - 2026\n- Built a Flutter app\n"
    ex = client.post("/api/v1/cv/extract?filename=cv.txt", content=txt.encode()); assert ex.status_code == 200 and ex.json()["latex"]
    t = client.post("/api/v1/cv/tailor", json={"cv": ex.json()["cv"], "latex": ex.json()["latex"], "job_id": jid})
    assert t.status_code == 200 and "flutter" in t.json()["matched"] and t.json()["latex"]
    assert client.post("/api/v1/cv/cover-letter", json={"cv": ex.json()["cv"], "job_id": jid}).status_code == 200
    assert client.post("/api/v1/cv/tailor", json={"cv": {}, "job_id": jid, "ai": True}).status_code == 400
