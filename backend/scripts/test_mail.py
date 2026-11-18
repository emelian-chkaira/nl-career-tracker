"""Send one test e-mail with the configured SMTP settings:  .venv/bin/python -m scripts.test_mail you@example.com"""
import sys
from app.core.db import SessionLocal
from app.core.config import settings
from app.models import EmailOutbox
from app.services import alert_service

if len(sys.argv) != 2: sys.exit("usage: python -m scripts.test_mail <recipient>")
if not settings.smtp_host: sys.exit("CAREERS_SMTP_HOST is not set (put it in .env or backend/.env.local)")
with SessionLocal() as db:
    m = EmailOutbox(to_email=sys.argv[1], subject="CareerNL test email", body_text="SMTP is configured correctly.")
    db.add(m); db.commit(); alert_service.send_outbox(db); db.refresh(m)
    print(f"{settings.smtp_host}:{settings.smtp_port} ({settings.smtp_security}) -> {m.status}" + (f": {m.error}" if m.error else ""))
    sys.exit(0 if m.status == "sent" else 1)
