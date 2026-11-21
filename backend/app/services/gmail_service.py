"""Gmail through Google OAuth 2.0 (read-only scope). The user signs in on Google's own page; we only keep a revocable refresh token (encrypted).
Messages are read with the Gmail API (messages.list / messages.get) - nothing is changed, deleted or marked as read."""
import base64, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from email.utils import parseaddr
from urllib.parse import urlencode
import httpx, jwt
from app.core.config import settings
from app.services.mail_service import MailError, MAX_BODY, html_to_text

SCOPES = "https://www.googleapis.com/auth/gmail.readonly openid email"
AUTH_URL, TOKEN_URL, API = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://gmail.googleapis.com/gmail/v1/users/me"


def client_id() -> str | None: return settings.gmail_client_id or (settings.google_ids[0] if settings.google_ids else None)
def configured() -> bool: return bool(client_id() and settings.google_client_secret)
def redirect_uri() -> str: return settings.api_url.rstrip("/") + "/api/v1/mail/gmail/callback"


def make_state(user_id: str) -> str: return jwt.encode({"sub": user_id, "typ": "gmail", "exp": int(time.time()) + 600}, settings.jwt_secret, algorithm="HS256")
def read_state(state: str) -> str:
    try:
        d = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if d.get("typ") != "gmail": raise ValueError
        return d["sub"]
    except Exception: raise MailError("the sign-in link expired, please try again")


def auth_url(user_id: str) -> str:
    if not configured(): raise MailError("Gmail sign-in is not configured on this server (see docs/GMAIL_OAUTH.md)")
    return AUTH_URL + "?" + urlencode({"client_id": client_id(), "redirect_uri": redirect_uri(), "response_type": "code", "scope": SCOPES,
                                       "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": make_state(user_id)})


def _token(data: dict) -> dict:
    try: r = httpx.post(TOKEN_URL, data={"client_id": client_id(), "client_secret": settings.google_client_secret, **data}, timeout=20)
    except httpx.HTTPError as e: raise MailError(f"cannot reach Google ({str(e)[:60]})")
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200: raise MailError(f"Google refused: {j.get('error_description') or j.get('error') or r.status_code}")
    return j


def exchange(code: str) -> dict:
    """-> {refresh_token, access_token, email}"""
    j = _token({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})
    if not j.get("refresh_token"): raise MailError("Google did not return offline access. Remove the app at myaccount.google.com/permissions and connect again.")
    p = _get("/profile", j["access_token"])
    return {"refresh_token": j["refresh_token"], "access_token": j["access_token"], "email": p.get("emailAddress", "")}


def access_token(refresh_token: str) -> str:
    try: return _token({"refresh_token": refresh_token, "grant_type": "refresh_token"})["access_token"]
    except MailError as e: raise MailError(f"{e}. Reconnect Gmail (Google testing mode expires the login after 7 days).")


def _get(path: str, token: str, **params) -> dict:
    for attempt in range(9):          # Gmail rate-limits bursts (403 "quota exceeded" / 429): wait and retry with growing delays
        try: r = httpx.get(API + path, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        except httpx.HTTPError as e: raise MailError(f"cannot reach Gmail ({str(e)[:60]})")
        if r.status_code in (429, 500, 503) or (r.status_code == 403 and ("uota" in r.text or "ate limit" in r.text or "rateLimit" in r.text)):
            time.sleep(min(30, float(r.headers.get("Retry-After") or 0) or 2 ** attempt)); continue
        break
    if r.status_code == 403 and "has not been used" in r.text: raise MailError("The Gmail API is not enabled for this Google Cloud project.")
    if r.status_code != 200: raise MailError(f"Gmail error {r.status_code}: {r.text[:120]}")
    return r.json()


def test(refresh_token: str) -> dict:
    p = _get("/profile", access_token(refresh_token)); return {"ok": True, "messages": p.get("messagesTotal", 0)}


def _b64(data: str) -> str: return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _walk(part: dict, out: dict):
    mt, body = part.get("mimeType", ""), part.get("body", {})
    if mt in ("text/plain", "text/html") and body.get("data") and not part.get("filename"): out.setdefault(mt, _b64(body["data"]))
    for sub in part.get("parts", []) or []: _walk(sub, out)


def _from_api(m: dict) -> dict:
    """Gmail API message (format=full) -> the same dict shape the .eml parser produces. Text parts only; attachments are ignored."""
    hdr = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
    parts: dict = {}; _walk(m.get("payload", {}), parts)
    body = parts.get("text/plain") or html_to_text(parts.get("text/html", ""))
    name, addr = parseaddr(hdr.get("from", ""))
    try: when = dt.datetime.fromtimestamp(int(m["internalDate"]) / 1000, dt.timezone.utc)
    except Exception: when = None
    return {"message_id": (hdr.get("message-id") or f"gmail-{m['id']}").strip()[:300], "sender": (f"{name} <{addr}>" if name else addr)[:300], "sender_addr": addr.lower(),
            "subject": hdr.get("subject", "")[:400], "date": when, "body": (body or "").strip()[:MAX_BODY]}


def fetch(refresh_token: str, days: int = 60, limit: int = 400) -> list[dict]:
    """Newest first. Skips promotions/social/spam/trash to keep it fast; job mail lives in the primary inbox."""
    tok = access_token(refresh_token); ids, page = [], None
    while len(ids) < limit:
        j = _get("/messages", tok, q=f"newer_than:{days}d -category:promotions -category:social -in:spam -in:trash", maxResults=min(100, limit - len(ids)), **({"pageToken": page} if page else {}))
        ids += [m["id"] for m in j.get("messages", [])]; page = j.get("nextPageToken")
        if not page: break
    def meta(i: str) -> dict:                       # cheap: headers + snippet only
        m = _get(f"/messages/{i}", tok, format="metadata", metadataHeaders=["From", "Subject", "Message-ID"])
        d = _from_api(m); d["body"] = m.get("snippet", ""); d["_id"] = i; return d
    from app.services.mail_classifier import looks_job_related
    with ThreadPoolExecutor(4) as ex: light = list(ex.map(meta, ids))
    out = []
    for d in light:                                 # download the full text only for mail that looks job related (full = much higher quota cost)
        if looks_job_related(d):
            try: d["body"] = _from_api(_get(f"/messages/{d['_id']}", tok, format="full"))["body"] or d["body"]
            except MailError: pass                  # keep the snippet if Gmail throttles this one
            time.sleep(0.2)
        out.append(d)
    return out
