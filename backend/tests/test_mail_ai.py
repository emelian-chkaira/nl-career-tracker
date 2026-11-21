"""AI providers, mailbox sync, classification and the review inbox (no network: HTTP and IMAP are faked)."""
import json, httpx, pytest
from sqlalchemy import select, text
from app.core.config import settings
from app.models import MailEvent, UserJob, Job, Company, Task, User
from app.services import llm_service as llm, mail_service as ms, mail_classifier as mc, ingest_service as ing, task_service
from app.workers import tasks


def mail(subject, body, sender="Acme Talent <jobs@acme.com>", mid="m1"):
    return {"message_id": mid, "sender": sender, "sender_addr": sender.split("<")[-1].strip(">").lower(), "subject": subject, "date": None, "body": body}


# ---------------------------------------------------------------- rules
@pytest.mark.parametrize("subject,body,cat", [
    ("Update on your application", "Thank you for applying for the Backend Engineer position. Unfortunately we will not be moving forward.", "rejection"),
    ("Helaas", "Bedankt voor je sollicitatie. Helaas hebben we gekozen voor een andere kandidaat.", "rejection"),
    ("Interview invitation", "We would like to invite you to an interview. Pick a time on calendly.", "interview_invite"),
    ("Next steps", "Please complete the take-home assignment within 5 days.", "assessment"),
    ("Offer", "We are pleased to offer you the role of Mobile Developer.", "offer"),
    ("Your application", "Thank you for applying for the Data Engineer role. We have received your application.", "application_received"),
    ("Hello", "I came across your profile and have an exciting opportunity for you.", "recruiter_outreach"),
])
def test_rules_classify(subject, body, cat):
    m = mail(subject, body); assert mc.looks_job_related(m)
    assert mc.classify_rules(m)["category"] == cat


def test_rules_ignore_newsletters_and_extract_company_role():
    assert not mc.looks_job_related(mail("Big deals this week", "50% off everything", sender="newsletter@shop.com"))
    r = mc.classify_rules(mail("Your application to Mollie", "Thank you for applying for the Data Engineer role.", sender="no-reply@mollie.com"))
    assert r["company"] == "Mollie" and r["role"] == "Data Engineer"


# ---------------------------------------------------------------- providers
def test_provider_presets_cover_free_chinese_and_paid():
    ids = {p["id"] for p in llm.PROVIDERS.values() and [dict(id=k) for k in llm.PROVIDERS]}
    assert {"rules", "ollama", "zhipu", "qwen", "deepseek", "moonshot", "openrouter", "anthropic", "openai", "custom"} <= ids


def _fake_http(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))


def test_openai_compatible_request_and_think_stripping(monkeypatch):
    seen = {}
    def h(req):
        seen.update(url=str(req.url), auth=req.headers.get("authorization"), body=json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>hmm</think>{\"category\": \"offer\"}"}}]})
    _fake_http(monkeypatch, h)
    out = llm.complete(llm.Cfg("deepseek", "deepseek-chat", None, "sk-secret"), "sys", "user")
    assert out == '{"category": "offer"}' and seen["url"] == "https://api.deepseek.com/v1/chat/completions" and seen["auth"] == "Bearer sk-secret"
    assert seen["body"]["model"] == "deepseek-chat" and seen["body"]["messages"][0]["role"] == "system"


def test_anthropic_request_shape(monkeypatch):
    seen = {}
    def h(req):
        seen.update(url=str(req.url), key=req.headers.get("x-api-key"), body=json.loads(req.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{\"ok\": 1}"}]})
    _fake_http(monkeypatch, h)
    assert llm.complete(llm.Cfg("anthropic", "claude-haiku-5-5", None, "sk-ant-x"), "s", "u") == '{"ok": 1}'
    assert seen["url"].endswith("/v1/messages") and seen["key"] == "sk-ant-x" and seen["body"]["system"] == "s"


def test_errors_never_leak_the_key(monkeypatch):
    _fake_http(monkeypatch, lambda req: httpx.Response(401, text="invalid key sk-secret-123"))
    with pytest.raises(llm.LlmError) as e: llm.complete(llm.Cfg("openai", "gpt-4o-mini", None, "sk-secret-123"), "s", "u")
    assert "sk-secret-123" not in str(e.value)


# ---------------------------------------------------------------- settings API
def test_ai_settings_store_key_encrypted_and_never_return_it(client, make_user, db):
    h, _ = make_user()
    r = client.put("/api/v1/ai/settings", json={"provider": "qwen", "model": "qwen-plus", "api_key": "sk-qwen-secret"}, headers=h).json()
    assert r == {"provider": "qwen", "model": "qwen-plus", "base_url": None, "has_key": True}
    assert "sk-qwen-secret" not in json.dumps(client.get("/api/v1/ai/settings", headers=h).json())
    assert "sk-qwen-secret" not in (db.scalar(text("select api_key_enc from user_ai_settings")) or "")
    assert client.put("/api/v1/ai/settings", json={"provider": "qwen", "api_key": ""}, headers=h).json()["has_key"] is False       # "" removes it
    assert client.put("/api/v1/ai/settings", json={"provider": "nope"}, headers=h).status_code == 400
    assert any(p["id"] == "zhipu" for p in client.get("/api/v1/ai/providers").json())


def test_private_endpoints_blocked_when_not_allowed(client, make_user, monkeypatch):
    h, _ = make_user(); monkeypatch.setattr(settings, "allow_private_hosts", False)
    assert client.put("/api/v1/ai/settings", json={"provider": "custom", "base_url": "http://127.0.0.1:11434/v1", "model": "x"}, headers=h).status_code == 400
    assert client.post("/api/v1/mail/accounts", json={"host": "localhost", "username": "a", "password": "b"}, headers=h).status_code == 405      # IMAP was removed


# ---------------------------------------------------------------- import + classification
def test_import_with_rules_dedupes_and_needs_consent_for_external_ai(client, make_user, monkeypatch):
    h, _ = make_user()
    body = {"subject": "Update on your application", "sender": "Acme <jobs@acme.com>", "text": "Thank you for applying. Unfortunately we will not be moving forward with your application."}
    assert client.post("/api/v1/mail/import", json=body, headers=h).json()["found"] == 1
    assert client.post("/api/v1/mail/import", json=body, headers=h).json()["duplicate"] == 1
    ev = client.get("/api/v1/mail/events", headers=h).json()
    assert ev["items"][0]["category"] == "rejection" and ev["counts"]["category"] == {"rejection": 1}
    client.put("/api/v1/ai/settings", json={"provider": "anthropic", "model": "claude-haiku-5-5", "api_key": "k"}, headers=h)
    r = client.post("/api/v1/mail/import", json={**body, "text": body["text"] + " x"}, headers=h); assert r.status_code == 400 and "consent" in r.text
    monkeypatch.setattr(llm, "complete", lambda *a, **k: json.dumps({"category": "rejection", "company": "Acme", "role": "Backend Engineer", "summary": "They passed.", "confidence": 0.95}))
    r = client.post("/api/v1/mail/import", json={**body, "text": body["text"] + " y", "consent": True}, headers=h).json()
    assert r["found"] == 1
    top = client.get("/api/v1/mail/events", headers=h).json()["items"][0]
    assert top["role"] == "Backend Engineer" and top["confidence"] == 0.95 and top["classifier"] == "anthropic:claude-haiku-5-5"


def test_llm_failure_falls_back_to_rules_and_not_job_related_is_skipped(db, make_user, monkeypatch):
    cfg = llm.Cfg("deepseek", "deepseek-chat", None, "k")
    def boom(*a, **k): raise llm.LlmError("rate limited")
    monkeypatch.setattr(llm, "complete", boom)
    res, warn = mc.classify(cfg, mail("Interview", "We would like to invite you to an interview."))
    assert res["category"] == "interview_invite" and "built-in rules" in warn
    monkeypatch.setattr(llm, "complete", lambda *a, **k: json.dumps({"category": "not_job_related"}))
    assert mc.classify(cfg, mail("Interview", "invite you to an interview"))[0] is None


def test_parse_eml_and_html_body():
    raw = b"From: Jane <jane@acme.com>\nSubject: Interview at Acme\nMessage-ID: <abc@x>\nDate: Tue, 10 Nov 2026 10:00:00 +0000\nContent-Type: text/html\n\n<p>Hello <b>there</b></p><p>Interview tomorrow</p>"
    m = ms.parse_eml(raw)
    assert m["subject"] == "Interview at Acme" and m["message_id"] == "<abc@x>" and "Interview tomorrow" in m["body"] and "<p>" not in m["body"] and m["sender_addr"] == "jane@acme.com"


# ---------------------------------------------------------------- mailbox sync through the worker
# ---------------------------------------------------------------- review inbox
def _pipeline(db, user_email="user@example.com", stage="shortlisted"):
    u = db.scalar(select(User).where(User.email == user_email)); c = ing.add_company(db, "Acme")
    ing.store_jobs(db, c, [dict(title="Backend Engineer", location="Amsterdam, Netherlands", url="https://acme.nl/1", description="python", posted_at=None)]); db.commit()
    j = db.scalar(select(Job)); db.add(UserJob(user_id=u.id, job_id=j.id, stage=stage)); db.commit(); return j


def test_accept_moves_pipeline_and_never_downgrades(client, make_user, db):
    h, _ = make_user(); j = _pipeline(db)
    r = client.post("/api/v1/mail/import", json={"subject": "Your application to Acme", "sender": "Acme <jobs@acme.com>", "text": "Thank you for applying for the Backend Engineer role. We have received your application."}, headers=h).json()
    ev = client.get("/api/v1/mail/events", headers=h).json()["items"][0]
    assert ev["job_id"] == j.id and ev["suggested_stage"] == "applied" and ev["company_known"] == "Acme"
    assert client.post(f"/api/v1/mail/events/{ev['id']}/accept", headers=h).json()["stage"] == "applied"
    assert db.scalar(select(UserJob.stage)) == "applied"
    client.post("/api/v1/mail/import", json={"subject": "Interview", "sender": "Acme <jobs@acme.com>", "text": "We would like to invite you to an interview for the Backend Engineer role."}, headers=h)
    iv = [e for e in client.get("/api/v1/mail/events", headers=h).json()["items"] if e["category"] == "interview_invite"][0]
    client.post(f"/api/v1/mail/events/{iv['id']}/accept", headers=h); db.expire_all(); assert db.scalar(select(UserJob.stage)) == "interview"
    client.post("/api/v1/mail/import", json={"subject": "Application received", "sender": "Acme <jobs@acme.com>", "text": "Thank you for applying for the Backend Engineer role. We received your application again."}, headers=h)
    again = [e for e in client.get("/api/v1/mail/events", headers=h, params={"status": "new"}).json()["items"]][0]
    client.post(f"/api/v1/mail/events/{again['id']}/accept", headers=h); db.expire_all(); assert db.scalar(select(UserJob.stage)) == "interview"      # not moved back to applied


def test_edit_dismiss_bulk_and_delete(client, make_user, db):
    h, _ = make_user()
    for i, (s, b) in enumerate([("Offer", "We are pleased to offer you the role"), ("Update", "Unfortunately we will not be moving forward with your application"), ("Hi", "I came across your profile, an exciting opportunity")]):
        client.post("/api/v1/mail/import", json={"subject": s, "sender": f"Co{i} <hr@co{i}.com>", "text": b}, headers=h)
    items = client.get("/api/v1/mail/events", headers=h).json()["items"]; assert len(items) == 3
    e = items[0]
    assert client.patch(f"/api/v1/mail/events/{e['id']}", json={"category": "assessment", "company": "Fixed Co", "role": "QA"}, headers=h).status_code == 200
    assert client.patch(f"/api/v1/mail/events/{e['id']}", json={"category": "nope"}, headers=h).status_code == 400
    top = [x for x in client.get("/api/v1/mail/events", headers=h).json()["items"] if x["id"] == e["id"]][0]
    assert (top["category"], top["company"], top["role"]) == ("assessment", "Fixed Co", "QA")
    assert client.post(f"/api/v1/mail/events/{items[1]['id']}/dismiss", headers=h).status_code == 200
    assert client.post("/api/v1/mail/events/bulk", json={"ids": [items[2]["id"]], "action": "accept"}, headers=h).json()["changed"] == 1
    c = client.get("/api/v1/mail/events", headers=h).json()["counts"]["status"]; assert c == {"new": 1, "dismissed": 1, "accepted": 1}
    assert len(client.get("/api/v1/mail/events", headers=h, params={"status": "accepted"}).json()["items"]) == 1
    assert client.delete("/api/v1/mail/events", headers=h).status_code == 204
    assert client.get("/api/v1/mail/events", headers=h).json()["items"] == []


def test_mail_endpoints_require_sign_in(client):
    for path in ("/api/v1/mail/events", "/api/v1/mail/accounts", "/api/v1/ai/settings"): assert client.get(path).status_code == 401


# ---------------------------------------------------------------- Gmail OAuth
def test_gmail_oauth_flow(client, make_user, db, monkeypatch):
    from app.services import gmail_service as gm
    h, _ = make_user()
    monkeypatch.setattr(settings, "google_client_id", "cid.apps.googleusercontent.com"); monkeypatch.setattr(settings, "google_client_secret", None)
    st = client.get("/api/v1/mail/gmail/status", headers=h).json()
    assert st["configured"] is False and st["redirect_uri"].endswith("/api/v1/mail/gmail/callback")
    assert client.post("/api/v1/mail/gmail/start", headers=h).status_code == 400                      # not configured
    monkeypatch.setattr(settings, "google_client_secret", "shh")
    url = client.post("/api/v1/mail/gmail/start", headers=h).json()["url"]
    assert url.startswith("https://accounts.google.com/") and "gmail.readonly" in url and "access_type=offline" in url
    state = url.split("state=")[1].split("&")[0]
    monkeypatch.setattr(gm, "exchange", lambda code: {"refresh_token": "r-token", "access_token": "a", "email": "me@gmail.com"})
    r = client.get("/api/v1/mail/gmail/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert r.status_code in (302, 307) and "gmail=connected" in r.headers["location"]
    assert "r-token" not in (db.scalar(text("select secret_enc from mail_accounts")) or "")          # stored encrypted
    acc = client.get("/api/v1/mail/accounts", headers=h).json()
    assert len(acc) == 1 and acc[0]["provider"] == "gmail" and acc[0]["username"] == "me@gmail.com" and "r-token" not in str(acc)
    # reconnecting the same address updates instead of duplicating
    client.get("/api/v1/mail/gmail/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert len(client.get("/api/v1/mail/accounts", headers=h).json()) == 1
    # a forged state is refused
    bad = client.get("/api/v1/mail/gmail/callback", params={"code": "c", "state": "nope"}, follow_redirects=False)
    assert "gmail=error" in bad.headers["location"] and len(client.get("/api/v1/mail/accounts", headers=h).json()) == 1
    assert "gmail=denied" in client.get("/api/v1/mail/gmail/callback", params={"error": "access_denied"}, follow_redirects=False).headers["location"]
    # sync uses the Gmail API reader, not IMAP
    monkeypatch.setattr(gm, "fetch", lambda token, days=60, limit=400: [mail("Interview", "We would like to invite you to an interview.", mid="g1")] if token == "r-token" else [])
    tid = client.post("/api/v1/mail/sync", json={"account_id": acc[0]["id"]}, headers=h).json()["task_id"]
    import time
    for _ in range(100):                                               # the sync runs in a background thread of the API
        st = client.get(f"/api/v1/mail/sync/{tid}", headers=h).json()
        if st["status"] != "running": break
        time.sleep(0.1)
    assert st["status"] == "done" and st["progress"]["found"] == 1 and "unclassified" in st["progress"]
    assert client.get("/api/v1/mail/accounts", headers=h).json()[0]["last_sync_at"]
    h2, _ = make_user("other@example.com")
    assert client.get(f"/api/v1/mail/sync/{tid}", headers=h2).status_code == 404                  # someone else's task
    assert client.post(f"/api/v1/mail/accounts/{acc[0]['id']}/test", headers=h2).status_code == 404
    assert client.get("/api/v1/mail/events", headers=h2).json()["items"] == []
