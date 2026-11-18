def test_register_login_me_profile(client, make_user):
    h, tok = make_user()
    assert tok["user"]["email"] == "user@example.com" and tok["user"]["role"] == "user"
    assert client.get("/api/v1/auth/me", headers=h).json()["name"] == "Test User"
    r = client.put("/api/v1/auth/profile", headers=h, json={"skills": ["flutter"], "cities": ["Eindhoven"]})
    assert r.status_code == 200 and r.json()["profile"]["skills"] == ["flutter"]
    assert client.post("/api/v1/auth/login", json={"email": "USER@example.com", "password": "correct-horse-1"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong-password"}).status_code == 401


def test_duplicate_and_weak_password(client, make_user):
    make_user()
    assert client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "another-pass-1"}).status_code == 409
    assert client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_admin_email_gets_admin_role(client, make_user):
    h, tok = make_user("admin@example.com")
    assert tok["user"]["role"] == "admin"
    assert client.get("/api/v1/admin/stats", headers=h).status_code == 200


def test_admin_endpoints_forbidden_for_users_and_anonymous(client, make_user):
    h, _ = make_user()
    assert client.get("/api/v1/admin/stats", headers=h).status_code == 403
    assert client.get("/api/v1/admin/stats").status_code == 401
    assert client.post("/api/v1/admin/tasks", json={"kind": "scan_all"}, headers=h).status_code == 403


def test_refresh_rotation_and_reuse_detection(client, make_user):
    _, tok = make_user()
    old = tok["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": old}); assert r.status_code == 200
    new = r.json()["refresh_token"]; assert new != old
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old}).status_code == 401      # re-use -> whole family revoked
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new}).status_code == 401


def test_refresh_via_cookie_and_logout(client, make_user):
    make_user()
    assert client.post("/api/v1/auth/refresh").status_code == 200                                   # cookie set by register
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_bad_token_rejected(client):
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_change_password(client, make_user):
    h, _ = make_user()
    assert client.post("/api/v1/auth/password", headers=h, json={"current_password": "bad", "new_password": "brand-new-pass-1"}).status_code == 400
    assert client.post("/api/v1/auth/password", headers=h, json={"current_password": "correct-horse-1", "new_password": "brand-new-pass-1"}).status_code == 204
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "brand-new-pass-1"}).status_code == 200


def _link_token(db, subject_part):
    import re
    from sqlalchemy import select
    from app.models import EmailOutbox
    m = [x for x in db.scalars(select(EmailOutbox).order_by(EmailOutbox.id)) if subject_part in x.subject][-1]
    return re.search(r"token=([\w-]+)", m.body_text).group(1)


def test_email_verification_flow(client, make_user, db):
    h, tok = make_user()
    assert tok["user"]["email_verified"] is False
    t = _link_token(db, "Confirm")
    assert client.post("/api/v1/auth/verify", json={"token": t}).json()["email_verified"] is True
    assert client.post("/api/v1/auth/verify", json={"token": t}).status_code == 400          # single use
    assert client.get("/api/v1/auth/me", headers=h).json()["email_verified"] is True
    assert client.post("/api/v1/auth/verify", json={"token": "x" * 30}).status_code == 400


def test_password_reset_flow(client, make_user, db):
    h, tok = make_user()
    assert client.post("/api/v1/auth/forgot", json={"email": "nobody@example.com"}).status_code == 202     # no enumeration
    assert client.post("/api/v1/auth/forgot", json={"email": "user@example.com"}).status_code == 202
    t = _link_token(db, "Reset")
    assert client.post("/api/v1/auth/reset", json={"token": t, "new_password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/reset", json={"token": t, "new_password": "brand-new-pass-9"}).status_code == 204
    assert client.post("/api/v1/auth/reset", json={"token": t, "new_password": "brand-new-pass-9"}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "correct-horse-1"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "brand-new-pass-9"}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401   # old sessions signed out


def test_require_verified_blocks_login(client, make_user, monkeypatch):
    from app.core.config import settings
    make_user(); monkeypatch.setattr(settings, "require_verified_email", True)
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "correct-horse-1"}).status_code == 403


def test_smtp_modes(db, monkeypatch):
    import smtplib
    from app.core.config import settings
    from app.models import EmailOutbox
    from app.services import alert_service
    calls = []
    class Fake:
        def __init__(self, host, port, timeout=0): calls.append((type(self).__name__, host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): calls.append("starttls")
        def login(self, u, p): calls.append(("login", u))
        def send_message(self, m): calls.append(("sent", m["To"]))
    class FakeSSL(Fake): pass
    monkeypatch.setattr(smtplib, "SMTP", Fake); monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSL)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test"); monkeypatch.setattr(settings, "smtp_user", "u")
    for sec, port in (("starttls", 587), ("ssl", 465), ("none", 1025)):
        calls.clear(); monkeypatch.setattr(settings, "smtp_security", sec); monkeypatch.setattr(settings, "smtp_port", port)
        db.add(EmailOutbox(to_email="a@example.com", subject="s", body_text="b")); db.commit()
        assert alert_service.send_outbox(db) == 1
        assert ("starttls" in calls) == (sec == "starttls") and calls[0][0] == ("FakeSSL" if sec == "ssl" else "Fake")


def test_google_sign_in(client, monkeypatch):
    from app.core.config import settings
    from app.services import google_service
    assert client.post("/api/v1/auth/google", json={"credential": "x" * 30}).status_code == 404          # not configured
    monkeypatch.setattr(settings, "google_client_id", "cid.apps.googleusercontent.com")
    assert client.post("/api/v1/auth/google", json={"credential": "x" * 30}).status_code == 401          # garbage token
    assert client.get("/api/v1/auth/config").json()["google_client_id"] == "cid.apps.googleusercontent.com"
    claims = {"email": "G.User@Example.com", "email_verified": True, "name": "G User", "sub": "1"}
    monkeypatch.setattr(google_service, "verify_id_token", lambda c: claims)
    r = client.post("/api/v1/auth/google", json={"credential": "x" * 30}); assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "g.user@example.com" and r.json()["user"]["email_verified"] is True
    assert client.post("/api/v1/auth/google", json={"credential": "x" * 30}).json()["user"]["id"] == r.json()["user"]["id"]   # same account on 2nd login
    # an existing password account is linked by its (Google-verified) email
    client.post("/api/v1/auth/register", json={"email": "p@example.com", "password": "correct-horse-1"})
    claims["email"] = "p@example.com"
    u = client.post("/api/v1/auth/google", json={"credential": "x" * 30}).json()["user"]
    assert u["email"] == "p@example.com" and u["email_verified"] is True
