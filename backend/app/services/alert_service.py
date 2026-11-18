"""Job alerts: saved searches -> in-app notification + queued e-mail digest."""
import datetime as dt, html
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import SavedSearch, Notification, EmailOutbox, User, Job
from . import search_service as ss, jobs_service

FREQ = {"instant": dt.timedelta(minutes=15), "daily": dt.timedelta(hours=23), "weekly": dt.timedelta(days=6, hours=20)}
now = lambda: dt.datetime.now(dt.timezone.utc)


def _params(s: SavedSearch) -> ss.SearchParams:
    return ss.SearchParams(**{**(s.params or {}), "page": 1, "limit": 100})


def new_matches(db: Session, s: SavedSearch, since: dt.datetime) -> list[Job]:
    ids = ss.run(db, _params(s))["ids"]
    if not ids: return []
    new_ids = db.execute(text("SELECT id FROM jobs WHERE id = ANY(:ids) AND first_seen > :since ORDER BY first_seen DESC"), {"ids": ids, "since": since}).scalars().all()
    from sqlalchemy.orm import selectinload
    return list(db.scalars(select(Job).where(Job.id.in_(new_ids[:30])).options(selectinload(Job.company)))) if new_ids else []


def _email(user: User, s: SavedSearch, jobs: list[Job]) -> tuple[str, str, str]:
    base = settings.public_url.rstrip("/")
    subject = f"{len(jobs)} new job{'s' if len(jobs) != 1 else ''} for “{s.name}”"
    lines = [f"- {j.title} — {j.company.name}{' (' + j.city + ')' if j.city else ''}\n  {base}/jobs/{j.id}" for j in jobs[:10]]
    text_body = f"Hi {user.name or 'there'},\n\nNew matches for your saved search “{s.name}”:\n\n" + "\n".join(lines) + f"\n\nManage alerts: {base}/alerts\n"
    items = "".join(f'<li><a href="{base}/jobs/{j.id}"><b>{html.escape(j.title)}</b></a> — {html.escape(j.company.name)}{" · " + html.escape(j.city) if j.city else ""}</li>' for j in jobs[:10])
    html_body = f'<p>Hi {html.escape(user.name or "there")},</p><p>New matches for <b>{html.escape(s.name)}</b>:</p><ul>{items}</ul><p><a href="{base}/alerts">Manage your alerts</a></p>'
    return subject, text_body, html_body


def run_due(db: Session) -> int:
    """Called by the worker every few minutes. Returns the number of alerts created."""
    made = 0
    for s in db.scalars(select(SavedSearch).where(SavedSearch.alert_frequency != "off")):
        gap = FREQ.get(s.alert_frequency, FREQ["daily"]); last = s.last_run_at or s.created_at
        if now() - last < gap: continue
        jobs = new_matches(db, s, last)
        s.last_run_at = now()
        if jobs:
            user = db.get(User, s.user_id)
            subject, tb, hb = _email(user, s, jobs)
            db.add(Notification(user_id=user.id, kind="alert", title=subject, body=", ".join(j.title for j in jobs[:3]), data={"saved_search_id": s.id, "job_ids": [j.id for j in jobs]}))
            if s.channel_email: db.add(EmailOutbox(to_email=user.email, subject=subject, body_text=tb, body_html=hb))
            made += 1
        db.commit()
    return made


def send_outbox(db: Session, limit: int = 50) -> int:
    import smtplib
    from email.message import EmailMessage
    sent = 0
    for m in db.scalars(select(EmailOutbox).where(EmailOutbox.status == "pending").order_by(EmailOutbox.id).limit(limit)):
        if not settings.smtp_host: m.status, m.error = "skipped", "SMTP not configured"; continue
        try:
            msg = EmailMessage(); msg["From"], msg["To"], msg["Subject"] = settings.mail_from, m.to_email, m.subject
            msg.set_content(m.body_text)
            if m.body_html: msg.add_alternative(m.body_html, subtype="html")
            sec = settings.smtp_security.lower()
            with (smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) if sec == "ssl" else smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)) as srv:
                if sec == "starttls": srv.starttls()
                if settings.smtp_user: srv.login(settings.smtp_user, settings.smtp_password or "")
                srv.send_message(msg)
            m.status, m.sent_at = "sent", now(); sent += 1
        except Exception as e: m.status, m.error = "failed", str(e)[:300]
    db.commit(); return sent
