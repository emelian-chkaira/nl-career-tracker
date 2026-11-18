"""Sign in with Google: verifies the ID token the client got from Google (signature via Google's public keys, audience, issuer, expiry)."""
import secrets
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import security
from app.models import User
from app.crawler.scoring import DEFAULT_PROFILE
from app.services.account_service import now

_jwks = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", cache_keys=True)


def verify_id_token(credential: str) -> dict:
    if not settings.google_ids: raise HTTPException(404, "Google sign-in is not configured")
    try:
        key = _jwks.get_signing_key_from_jwt(credential).key
        claims = jwt.decode(credential, key, algorithms=["RS256"], audience=settings.google_ids, issuer=["https://accounts.google.com", "accounts.google.com"], options={"require": ["exp", "iss", "aud", "sub"]})
    except Exception: raise HTTPException(401, "Google sign-in failed")
    if not claims.get("email") or claims.get("email_verified") is not True: raise HTTPException(401, "your Google email is not verified")
    return claims


def sign_in(db: Session, credential: str) -> User:
    c = verify_id_token(credential); email = c["email"].lower()
    u = db.scalar(select(User).where(User.email == email))
    if u:
        if not u.is_active: raise HTTPException(401, "account disabled")
        u.email_verified_at = u.email_verified_at or now()                      # Google vouches for the address
    else:
        if not settings.allow_registration: raise HTTPException(403, "registration is closed")
        u = User(email=email, name=(c.get("name") or "")[:120], password_hash=security.hash_password(secrets.token_urlsafe(32)),   # unusable random password; "forgot password" can set one
                 role="admin" if email in settings.admin_list else "user", profile=dict(DEFAULT_PROFILE), email_verified_at=now())
        db.add(u)
    u.last_login_at = now(); db.commit(); return u
