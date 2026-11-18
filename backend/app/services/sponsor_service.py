"""IND recognised-sponsor register: refresh from ind.nl and match company names (flag only, never a filter)."""
import re, datetime, httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.crawler.text import norm
from app.models import Sponsor, KV, Company

URL = "https://ind.nl/en/public-register-recognised-sponsors/public-register-work"


def refresh(db: Session, html: str | None = None) -> int:
    if html is None:
        html = httpx.get(URL, headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=60).text
    soup = BeautifulSoup(html, "lxml"); rows = []
    snap = datetime.date.today().isoformat()
    for tr in soup.select("table tr")[1:]:
        tds = [t.get_text(" ", strip=True) for t in tr.find_all(["th", "td"])]
        if tds and tds[0]: rows.append(Sponsor(name=tds[0], name_norm=norm(tds[0]), kvk=(tds[1] if len(tds) > 1 else None), snapshot=snap))
    if rows:
        db.execute(delete(Sponsor)); db.add_all(rows)
        kv = db.get(KV, "sponsor_snapshot") or KV(k="sponsor_snapshot"); kv.v = snap; db.add(kv)
        db.commit()
    return len(rows)


def check(db: Session, name: str, kvk: str | None = None) -> tuple[str, str | None]:
    """-> (status, matched register name). recognised = KvK or exact normalised name, possible = register name starts with the brand."""
    if db.scalar(select(Sponsor.id).limit(1)) is None: return "unchecked", None
    if kvk:
        r = db.scalar(select(Sponsor).where(Sponsor.kvk == kvk).limit(1))
        if r: return "recognised", r.name
    n = norm(name)
    if not n: return "not_listed", None
    r = db.scalar(select(Sponsor).where(Sponsor.name_norm == n).limit(1))
    if r: return "recognised", r.name
    if len(n) >= 4:
        r = db.scalar(select(Sponsor).where(Sponsor.name_norm.like(f"{n} %")).limit(1))      # brand vs legal entity: "adyen" -> "adyen n.v."
        if r: return "possible", r.name
    return "not_listed", None


def recheck_all(db: Session):
    for c in db.scalars(select(Company)):
        c.sponsor_status, c.sponsor_match = check(db, c.name, c.kvk)
    db.commit()
