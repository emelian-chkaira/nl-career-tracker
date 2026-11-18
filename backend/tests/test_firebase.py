"""Firebase Authentication flow against an in-memory fake of the Identity Toolkit REST API."""
import itertools
import httpx
import pytest


class FakeResp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


class FakeFirebase:
    def __init__(self):
        self.users, self.sent, self.oob, self.n = {}, [], {}, itertools.count(1)

    def err(self, m): return FakeResp(400, {"error": {"message": m}})

    def post(self, url, params=None, json=None, data=None, timeout=0):
        if "securetoken" in url:
            u = next((x for x in self.users.values() if x["refresh"] == data["refresh_token"]), None)
            return FakeResp(200, {"id_token": "id-" + u["uid"]}) if u else self.err("INVALID_REFRESH_TOKEN")
        op = url.rsplit(":", 1)[1]; return getattr(self, op)(json)

    def _tokens(self, u): return {"idToken": "id-" + u["uid"], "localId": u["uid"], "refreshToken": u["refresh"], "email": u["email"]}
    def _by_id(self, t): return next((x for x in self.users.values() if "id-" + x["uid"] == t), None)

    def signUp(self, j):
        if j["email"] in self.users: return self.err("EMAIL_EXISTS")
        if len(j["password"]) < 6: return self.err("WEAK_PASSWORD : Password should be at least 6 characters")
        n = next(self.n); u = self.users[j["email"]] = {"uid": f"uid{n}", "email": j["email"], "pw": j["password"], "verified": False, "refresh": f"rt{n}", "name": ""}
        return FakeResp(200, self._tokens(u))

    def signInWithPassword(self, j):
        u = self.users.get(j["email"])
        return FakeResp(200, self._tokens(u)) if u and u["pw"] == j["password"] else self.err("INVALID_LOGIN_CREDENTIALS")

    def lookup(self, j):
        u = self._by_id(j["idToken"]); return FakeResp(200, {"users": [{"emailVerified": u["verified"], "displayName": u["name"]}]})

    def sendOobCode(self, j):
        email = j.get("email") or self._by_id(j["idToken"])["email"]
        if email not in self.users: return self.err("EMAIL_NOT_FOUND")
        code = f"oob-{j['requestType']}-{len(self.sent)}-padding-padding"; self.oob[code] = (j["requestType"], email); self.sent.append((j["requestType"], email, code)); return FakeResp(200, {"email": email})

    def resetPassword(self, j):
        if j["oobCode"] not in self.oob: return self.err("INVALID_OOB_CODE")
        _, email = self.oob.pop(j["oobCode"]); self.users[email]["pw"] = j["newPassword"]; return FakeResp(200, {"email": email})

    def update(self, j):
        if "oobCode" in j:
            if j["oobCode"] not in self.oob: return self.err("INVALID_OOB_CODE")
            _, email = self.oob.pop(j["oobCode"]); self.users[email]["verified"] = True; return FakeResp(200, {"email": email, "emailVerified": True})
        u = self._by_id(j["idToken"]); u["pw"] = j["password"]; return FakeResp(200, {"email": u["email"]})

    def signInWithIdp(self, j):
        email = "guser@example.com"
        u = self.users.get(email) or self.users.setdefault(email, {"uid": f"uid{next(self.n)}", "email": email, "pw": "", "verified": True, "refresh": "rtg", "name": "G User"})
        return FakeResp(200, {**self._tokens(u), "emailVerified": True, "displayName": u["name"]})


@pytest.fixture()
def fb(monkeypatch):
    from app.core.config import settings
    f = FakeFirebase(); monkeypatch.setattr(httpx, "post", f.post)
    monkeypatch.setattr(settings, "firebase_api_key", "test-key")
    return f


def _body(email="u@example.com", pw="correct-horse-1"): return {"email": email, "password": pw, "name": "U"}


def test_register_login_verify(client, fb):
    r = client.post("/api/v1/auth/register", json=_body()); assert r.status_code == 201, r.text
    assert r.json()["user"]["email_verified"] is False and fb.sent[0][:2] == ("VERIFY_EMAIL", "u@example.com")
    assert client.post("/api/v1/auth/register", json=_body()).status_code == 409
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.post("/api/v1/auth/login", json=_body(pw="wrong-password")).status_code == 401
    assert client.post("/api/v1/auth/verify/send", headers=h).status_code == 202 and fb.sent[-1][0] == "VERIFY_EMAIL" and len(fb.sent) == 2    # resend via stored refresh token
    assert client.post("/api/v1/auth/verify", json={"token": fb.sent[-1][2]}).json()["email_verified"] is True
    assert client.post("/api/v1/auth/verify", json={"token": fb.sent[-1][2]}).status_code == 400                       # single use
    assert client.post("/api/v1/auth/login", json=_body()).json()["user"]["email_verified"] is True


def test_forgot_reset_signs_out_everywhere(client, fb):
    tok = client.post("/api/v1/auth/register", json=_body()).json()
    assert client.post("/api/v1/auth/forgot", json={"email": "nobody@example.com"}).status_code == 202
    assert client.post("/api/v1/auth/forgot", json={"email": "u@example.com"}).status_code == 202
    code = [s for s in fb.sent if s[0] == "PASSWORD_RESET"][0][2]
    assert client.post("/api/v1/auth/reset", json={"token": code, "new_password": "brand-new-pass-9"}).status_code == 204
    assert client.post("/api/v1/auth/reset", json={"token": code, "new_password": "brand-new-pass-9"}).status_code == 400
    assert client.post("/api/v1/auth/login", json=_body()).status_code == 401
    assert client.post("/api/v1/auth/login", json=_body(pw="brand-new-pass-9")).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_legacy_account_migrates_on_login(client, make_user, monkeypatch):
    from app.core.config import settings
    h, tok = make_user("old@example.com", "correct-horse-1")                  # created before Firebase was enabled
    f = FakeFirebase(); monkeypatch.setattr(httpx, "post", f.post); monkeypatch.setattr(settings, "firebase_api_key", "test-key")
    r = client.post("/api/v1/auth/login", json=_body("old@example.com")); assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == tok["user"]["id"] and "old@example.com" in f.users                                 # same local account, now in Firebase
    assert client.post("/api/v1/auth/login", json=_body("old@example.com", "wrong-password")).status_code == 401


def test_google_and_change_password(client, fb):
    r = client.post("/api/v1/auth/google", json={"credential": "x" * 30}); assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "guser@example.com" and r.json()["user"]["email_verified"] is True
    tok = client.post("/api/v1/auth/register", json=_body()).json(); h = {"Authorization": "Bearer " + tok["access_token"]}
    assert client.post("/api/v1/auth/password", headers=h, json={"current_password": "nope-nope-1", "new_password": "another-pass-22"}).status_code == 400
    assert client.post("/api/v1/auth/password", headers=h, json={"current_password": "correct-horse-1", "new_password": "another-pass-22"}).status_code == 204
    assert client.post("/api/v1/auth/login", json=_body(pw="another-pass-22")).status_code == 200


def test_require_verified_blocks_login(client, fb, monkeypatch):
    from app.core.config import settings
    client.post("/api/v1/auth/register", json=_body()); monkeypatch.setattr(settings, "require_verified_email", True)
    assert client.post("/api/v1/auth/login", json=_body()).status_code == 403
