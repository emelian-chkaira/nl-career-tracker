"""E-mail verification and password reset: single-use hashed tokens, mails queued in the outbox and sent right away."""
import hashlib, secrets, datetime as dt
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import security
from app.models import User, AuthToken, EmailOutbox, RefreshToken

now = lambda: dt.datetime.now(dt.timezone.utc)
_h = lambda t: hashlib.sha256(t.encode()).hexdigest()


def _issue(db: Session, user: User, kind: str, ttl: dt.timedelta) -> str:
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == kind, AuthToken.used_at.is_(None)).values(used_at=now()))   # only the newest link works
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user.id, kind=kind, token_hash=_h(raw), expires_at=now() + ttl)); db.flush()
    return raw


def _mail(db: Session, to: str, subject: str, text: str, button: str, url: str):
    html = (f"<div style='font-family:system-ui,sans-serif;max-width:480px;margin:auto'><h2 style='margin:0 0 12px'>{subject}</h2><p>{text}</p>"
            f"<p><a href='{url}' style='display:inline-block;background:#2457f5;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600'>{button}</a></p>"
            f"<p style='color:#667;font-size:12px'>Or paste this link into your browser:<br>{url}</p></div>")
    db.add(EmailOutbox(to_email=to, subject=subject, body_text=f"{text}\n\n{url}\n", body_html=html))


def send_verification(db: Session, user: User):
    if user.email_verified: return
    raw = _issue(db, user, "verify", dt.timedelta(hours=settings.verify_ttl_hours))
    _mail(db, user.email, "Confirm your CareerNL email", "Confirm your email address to finish setting up your account.", "Confirm email", f"{settings.public_url}/verify?token={raw}")
    db.commit()


def send_reset(db: Session, email: str):
    """Always silent about whether the account exists (no user enumeration)."""
    u = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not u or not u.is_active: return
    raw = _issue(db, u, "reset", dt.timedelta(minutes=settings.reset_ttl_min))
    _mail(db, u.email, "Reset your CareerNL password", f"Use this link within {settings.reset_ttl_min} minutes to choose a new password. If you did not ask for it, ignore this email.", "Choose a new password", f"{settings.public_url}/reset?token={raw}")
    db.commit()


def _consume(db: Session, raw: str, kind: str) -> User:
    t = db.scalar(select(AuthToken).where(AuthToken.token_hash == _h(raw), AuthToken.kind == kind))
    if not t or t.used_at or t.expires_at < now(): raise HTTPException(400, "this link is invalid or has expired")
    t.used_at = now(); u = db.get(User, t.user_id)
    if not u or not u.is_active: raise HTTPException(400, "this link is invalid or has expired")
    return u


def verify(db: Session, raw: str) -> User:
    u = _consume(db, raw, "verify"); u.email_verified_at = u.email_verified_at or now(); db.commit(); return u


def reset(db: Session, raw: str, new_password: str):
    u = _consume(db, raw, "reset")
    u.password_hash = security.hash_password(new_password)
    if not u.email_verified_at: u.email_verified_at = now()                      # proves control of the mailbox
    db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id).values(revoked=True))   # sign out everywhere
    db.commit()
