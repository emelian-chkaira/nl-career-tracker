import uuid, datetime as dt
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import security
from app.models import User, RefreshToken
from app.crawler.scoring import DEFAULT_PROFILE


def register(db: Session, email: str, password: str, name: str = "") -> User:
    if not settings.allow_registration: raise HTTPException(403, "registration is closed")
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(409, "an account with this email already exists")
    role = "admin" if email in settings.admin_list else "user"
    u = User(email=email, password_hash=security.hash_password(password), name=name.strip(), role=role, profile=dict(DEFAULT_PROFILE))
    db.add(u); db.commit(); return u


def authenticate(db: Session, email: str, password: str) -> User:
    u = db.scalar(select(User).where(User.email == email.strip().lower()))
    ok = security.verify_password(password, u.password_hash) if u else security.verify_password(password, security.hash_password("x"))   # constant-ish time
    if not u or not ok or not u.is_active: raise HTTPException(401, "invalid email or password")
    if settings.require_verified_email and not u.email_verified: raise HTTPException(403, "please confirm your email first (check your inbox)")
    u.last_login_at = dt.datetime.now(dt.timezone.utc); db.commit(); return u


def issue_tokens(db: Session, user: User, family: uuid.UUID | None = None) -> tuple[str, str]:
    raw, h = security.new_refresh_token()
    db.add(RefreshToken(user_id=user.id, family=family or uuid.uuid4(), token_hash=h, expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.refresh_ttl_days)))
    db.commit()
    return security.create_access_token(user.id, user.role), raw


def rotate(db: Session, raw: str) -> tuple[User, str, str]:
    """Exchange a refresh token for a new pair. Re-use of an already-rotated token revokes the entire family (theft detection)."""
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh(raw)))
    now = dt.datetime.now(dt.timezone.utc)
    if not rt or rt.expires_at < now: raise HTTPException(401, "invalid refresh token")
    if rt.revoked:
        db.execute(update(RefreshToken).where(RefreshToken.family == rt.family).values(revoked=True)); db.commit()
        raise HTTPException(401, "refresh token re-use detected; please sign in again")
    user = db.get(User, rt.user_id)
    if not user or not user.is_active: raise HTTPException(401, "account disabled")
    rt.revoked = True; db.commit()
    access, new_raw = issue_tokens(db, user, family=rt.family)
    return user, access, new_raw


def revoke(db: Session, raw: str | None):
    if not raw: return
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh(raw)))
    if rt: db.execute(update(RefreshToken).where(RefreshToken.family == rt.family).values(revoked=True)); db.commit()
