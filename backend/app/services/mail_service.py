"""E-mail parsing (.eml files and Gmail API messages). Mailbox access itself lives in gmail_service (Google OAuth, read-only)."""
import email, re, datetime as dt
from email import policy
from email.utils import parsedate_to_datetime, parseaddr
from bs4 import BeautifulSoup

MAX_BODY = 6000


class MailError(Exception): pass


def html_to_text(html: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", BeautifulSoup(html or "", "lxml").get_text("\n")).strip()


def parse_message(msg: email.message.EmailMessage, fallback_id: str = "") -> dict:
    body = ""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        try: raw = part.get_content()
        except Exception: raw = ""
        body = html_to_text(raw) if part.get_content_type() == "text/html" else raw
    try: when = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
    except Exception: when = None
    if when and when.tzinfo is None: when = when.replace(tzinfo=dt.timezone.utc)
    name, addr = parseaddr(str(msg.get("From", "")))
    return {"message_id": (str(msg.get("Message-ID") or "").strip() or fallback_id)[:300], "sender": f"{name} <{addr}>".strip()[:300] if name else addr[:300],
            "sender_addr": addr.lower(), "subject": str(msg.get("Subject", ""))[:400], "date": when, "body": (body or "").strip()[:MAX_BODY]}


def parse_eml(data: bytes) -> dict:
    return parse_message(email.message_from_bytes(data, policy=policy.default), fallback_id=f"eml-{abs(hash(data))}")
