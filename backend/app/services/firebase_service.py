"""Firebase Authentication as the identity provider, through its REST API (Identity Toolkit), so web and mobile need no Firebase SDK.

Firebase stores the credentials and sends the verification / reset e-mails; this server only exchanges the result for its own
access + refresh tokens and keeps a local user row (profile, saved jobs) linked by firebase_uid. Accounts that existed before
Firebase was switched on are migrated lazily on their next successful sign-in."""
import logging, secrets
import httpx
from app.services import auth_service
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import security
from app.models import User, RefreshToken
from app.crawler.scoring import DEFAULT_PROFILE
from app.services.account_service import now

log = logging.getLogger("firebase")
BASE = "https://identitytoolkit.googleapis.com/v1/accounts:"
TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
BAD_LINK = HTTPException(400, "this link is invalid or has expired")
ERRORS = {
    "EMAIL_EXISTS": (409, "an account with this email already exists"),
    "EMAIL_NOT_FOUND": (401, "invalid email or password"), "INVALID_PASSWORD": (401, "invalid email or password"), "INVALID_LOGIN_CREDENTIALS": (401, "invalid email or password"),
    "USER_DISABLED": (401, "account disabled"), "TOO_MANY_ATTEMPTS_TRY_LATER": (429, "too many attempts, try again later"),
    "WEAK_PASSWORD": (422, "password is too weak (min 8 characters)"), "INVALID_EMAIL": (422, "invalid email address"),
    "OPERATION_NOT_ALLOWED": (503, "this sign-in method is not enabled in Firebase"),
    "EXPIRED_OOB_CODE": (400, BAD_LINK.detail), "INVALID_OOB_CODE": (400, BAD_LINK.detail),
    "INVALID_IDP_RESPONSE": (401, "Google sign-in failed"), "INVALID_REFRESH_TOKEN": (401, "please sign in again"), "TOKEN_EXPIRED": (401, "please sign in again"),
}


def _call(op: str, payload: dict) -> dict:
    try: r = httpx.post(BASE + op, params={"key": settings.firebase_api_key}, json=payload, timeout=15)
    except httpx.HTTPError: raise HTTPException(502, "identity provider unreachable")
    if r.status_code >= 400:
        try: code = ((r.json().get("error") or {}).get("message") or "").split(" ")[0]
        except ValueError: code = ""
        status, msg = ERRORS.get(code, (502, "identity provider error")); log.warning("firebase %s -> %s", op, code or r.status_code)
        raise HTTPException(status, msg)
    return r.json()


def _link(db: Session, email: str, uid: str, name: str = "", verified: bool = False, refresh: str | None = None) -> User:
    """The local user for a Firebase account: by uid, else by e-mail (adopts accounts that pre-date Firebase), else a new one."""
    email = email.strip().lower()
    u = db.scalar(select(User).where(User.firebase_uid == uid)) or db.scalar(select(User).where(User.email == email))
    if not u:
        if not settings.allow_registration: raise HTTPException(403, "registration is closed")
        u = User(email=email, name=name.strip()[:120], password_hash=security.hash_password(secrets.token_urlsafe(32)),    # real credentials live in Firebase
                 role=auth_service.role_for(db, email), profile=dict(DEFAULT_PROFILE), is_active=True); db.add(u)
    if not u.is_active: raise HTTPException(401, "account disabled")
    u.firebase_uid = uid
    if verified: u.email_verified_at = u.email_verified_at or now(); u.firebase_refresh = None
    elif not u.email_verified: u.firebase_refresh = refresh
    db.commit(); return u


def _send_verification(id_token: str):
    try: _call("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": id_token})
    except HTTPException: log.warning("could not send the verification e-mail")


def register(db: Session, email: str, password: str, name: str = "") -> User:
    if not settings.allow_registration: raise HTTPException(403, "registration is closed")
    r = _call("signUp", {"email": email.strip().lower(), "password": password, "returnSecureToken": True})
    _send_verification(r["idToken"])
    return _link(db, email, r["localId"], name, verified=False, refresh=r.get("refreshToken"))


def login(db: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    try: r = _call("signInWithPassword", {"email": email, "password": password, "returnSecureToken": True})
    except HTTPException as e:
        legacy = db.scalar(select(User).where(User.email == email))
        if e.status_code != 401 or not legacy or legacy.firebase_uid or not security.verify_password(password, legacy.password_hash): raise
        r = _call("signUp", {"email": email, "password": password, "returnSecureToken": True})              # lazy migration of a pre-Firebase account
        if legacy.email_verified: u = _link(db, email, r["localId"], legacy.name, verified=True)
        else: _send_verification(r["idToken"]); u = _link(db, email, r["localId"], legacy.name, verified=False, refresh=r.get("refreshToken"))
        return _finish(db, u)
    info = _call("lookup", {"idToken": r["idToken"]})["users"][0]
    verified = bool(info.get("emailVerified"))
    u = _link(db, email, r["localId"], info.get("displayName") or "", verified=verified, refresh=r.get("refreshToken"))
    if settings.require_verified_email and not u.email_verified: raise HTTPException(403, "please confirm your email first (check your inbox)")
    return _finish(db, u)


def _finish(db: Session, u: User) -> User:
    u.last_login_at = now(); db.commit(); return u


def google(db: Session, credential: str) -> User:
    r = _call("signInWithIdp", {"postBody": f"id_token={credential}&providerId=google.com", "requestUri": settings.public_url, "returnSecureToken": True, "returnIdpCredential": True})
    if not r.get("email"): raise HTTPException(401, "Google sign-in failed")
    return _finish(db, _link(db, r["email"], r["localId"], r.get("displayName") or "", verified=bool(r.get("emailVerified", True))))


def forgot(email: str):
    try: _call("sendOobCode", {"requestType": "PASSWORD_RESET", "email": email.strip().lower()})
    except HTTPException: pass                                              # same answer whether or not the account exists


def reset(db: Session, oob_code: str, new_password: str):
    r = _call("resetPassword", {"oobCode": oob_code, "newPassword": new_password})
    u = db.scalar(select(User).where(User.email == (r.get("email") or "").lower()))
    if u:
        u.email_verified_at = u.email_verified_at or now(); u.firebase_refresh = None
        db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id).values(revoked=True))   # sign out everywhere
        db.commit()


def verify(db: Session, oob_code: str) -> User:
    r = _call("update", {"oobCode": oob_code})
    u = db.scalar(select(User).where(User.email == (r.get("email") or "").lower()))
    if not u: raise BAD_LINK
    u.email_verified_at = u.email_verified_at or now(); u.firebase_refresh = None; db.commit(); return u


def resend_verification(db: Session, user: User):
    if user.email_verified: return
    if not user.firebase_refresh: raise HTTPException(400, "please sign out and sign in again, then retry")
    try: r = httpx.post(TOKEN_URL, params={"key": settings.firebase_api_key}, data={"grant_type": "refresh_token", "refresh_token": user.firebase_refresh}, timeout=15)
    except httpx.HTTPError: raise HTTPException(502, "identity provider unreachable")
    if r.status_code >= 400: raise HTTPException(400, "please sign out and sign in again, then retry")
    _call("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": r.json()["id_token"]})


def change_password(user: User, current: str, new: str):
    try: r = _call("signInWithPassword", {"email": user.email, "password": current, "returnSecureToken": True})
    except HTTPException as e:
        if e.status_code == 401: raise HTTPException(400, "current password is wrong")
        raise
    _call("update", {"idToken": r["idToken"], "password": new, "returnSecureToken": False})
