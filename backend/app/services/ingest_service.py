"""Write path of the crawler: companies, jobs (NL-only, deduped, skills/city extracted), scan results, logos."""
import re, hashlib, datetime as dt, os
from bs4 import BeautifulSoup
from sqlalchemy import select, update, func, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from app.core.config import settings
from app.crawler import discovery, nl, scoring, dates
from app.cvtools import cv as cvmod
from app.models import Company, Job, JobSkill
from app.services import sponsor_service

NOT_JOB_URL = re.compile(r"/(news|nieuws|press|blog|articles?|media|insights|stories|events|podcast|perspectives|whitepapers?)(/|$)|#\d+$", re.I)
NOT_JOB_TITLE = re.compile(r"\b(receives|announces|announced|approval|press release|partners with|wins|launches|appoints|acquires|acquisition of)\b", re.I)
CITY_RE = sorted({c for c in nl.CITIES if c and len(c) > 3}, key=len, reverse=True)
_CITY_PAT = re.compile(r"(?<![\w])(" + "|".join(re.escape(c) for c in CITY_RE) + r")(?![\w])", re.I)
LOGO_DIR = os.path.join(settings.data_dir, "logos")
now = lambda: dt.datetime.now(dt.timezone.utc)


def looks_like_job(title, url): return not (NOT_JOB_URL.search(url or "") or NOT_JOB_TITLE.search(title or ""))
def city_of(location: str) -> str | None:
    m = _CITY_PAT.search(location or "")
    if not m: return None
    c = m.group(1).lower()
    return {"the hague": "Den Haag", "hague": "Den Haag", "haag": "Den Haag", "gravenhage": "Den Haag", "'s-gravenhage": "Den Haag", "bosch": "Den Bosch", "s-hertogenbosch": "Den Bosch", "'s-hertogenbosch": "Den Bosch"}.get(c, c.title())
def money(text):
    m = re.search(r"€\s?(\d{1,3}(?:[.,]\d{3})+|\d{4,6})(?:\s?[-–]\s?€?\s?(\d{1,3}(?:[.,]\d{3})+|\d{4,6}))?", text or "")
    if not m: return None, None, None
    f = lambda s: float(re.sub(r"[.,]", "", s)) if s else None
    lo, hi = f(m.group(1)), f(m.group(2))
    return lo, hi, ("year" if (lo or 0) > 15000 else "month")
def dedupe_key(cid, title, location):
    n = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
    return hashlib.sha1(f"{cid}|{n(title)}|{n((location or '').split(',')[0])}".encode()).hexdigest()[:16]
def skills_of(title: str, desc: str) -> list[str]:
    return list(dict.fromkeys(cvmod.find_terms((title or "") + " \n " + (desc or "")[:8000])))[:25]


def add_company(db: Session, name, website=None, careers_url=None, kvk=None, city=None, address=None, source=None) -> Company:
    import html as _h
    name = _h.unescape(name).strip()
    c = db.scalar(select(Company).where(Company.name == name))
    if not c:
        st, match = sponsor_service.check(db, name, kvk)
        c = Company(name=name, website=website, careers_url=careers_url, kvk=kvk, sponsor_status=st, sponsor_match=match, city=city, address=address, source=source)
        db.add(c); db.flush()
    else:
        c.website = c.website or website; c.city = c.city or city; c.address = c.address or address; c.source = c.source or source
    return c


def store_jobs(db: Session, company: Company, jobs: list[dict], source="company-site", expire=True) -> int:
    seen, new = set(), 0
    for j in jobs:
        url, title = j.get("url"), (j.get("title") or "").strip()
        if not url or not title or not looks_like_job(title, url): continue
        seen.add(url)
        if not nl.is_nl(j.get("location"), url, source): continue
        desc = j.get("description") or ""
        lang = scoring.language(title, desc)
        jt = "internship" if j.get("kind") == "internship" and scoring.job_type(title, j.get("location", "")) in ("job", "junior") else scoring.job_type(title, j.get("location", ""))
        lo, hi, per = money(desc)
        posted = dates.norm_date(j.get("posted_at"))
        posted = dt.date.fromisoformat(posted) if posted else None
        loc = j.get("location") or ""
        dk = dedupe_key(company.id, title, loc)
        ex = db.scalar(select(Job).where(Job.url == url))
        if ex:
            ex.last_seen = now(); ex.status = "open"; ex.posted_at = ex.posted_at or posted
            if len(desc) > len(ex.description or ""): ex.description = desc
            continue
        if db.scalar(select(Job.id).where(Job.dedupe_key == dk, Job.status == "open")):
            continue                                                        # same posting under another URL
        job = Job(company_id=company.id, title=title, location=loc, city=city_of(loc), url=url, source=source, description=desc, category=nl.category(title),
                  job_type=jt, language=lang, remote=bool(re.search(r"\bremote\b|\bhybrid\b", loc, re.I)), salary_min=lo, salary_max=hi, salary_period=per,
                  posted_at=posted, dedupe_key=dk)
        job.skills = [JobSkill(skill=s) for s in skills_of(title, desc)]
        db.add(job); new += 1
    if seen and expire:
        db.execute(update(Job).where(Job.company_id == company.id, Job.status == "open", Job.url.notin_(seen)).values(status="expired"))
    db.flush()
    return new


def ensure_logo(db: Session, c: Company):
    path = os.path.join(LOGO_DIR, os.path.basename(c.logo)) if c.logo else None
    if not c.website or (c.logo and c.description and path and os.path.exists(path)): return
    try:
        html = discovery.get(c.website, check_robots=False)
        if not html: return
        p = discovery.fetch_logo(c.website, html, c.id)
        if p: c.logo = p
        soup = BeautifulSoup(html, "lxml")
        m = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        if m and m.get("content") and not c.description: c.description = m["content"].strip()[:400]
    except Exception: pass


def scan_company(db: Session, company_id: int) -> int:
    """Crawl one company's own career site and store what it lists. Returns number of NEW jobs."""
    c = db.get(Company, company_id)
    if not c or (c.ats or "").startswith("board:"): return 0
    cd = {k: getattr(c, k) for k in ("name", "website", "careers_url", "ats", "ats_slug", "resolved_via")}
    try: r = discovery.scan_company(cd)
    except Exception as e: r = dict(jobs=[], note=f"error: {e}", website=c.website, careers_url=c.careers_url, ats=c.ats, ats_slug=c.ats_slug, resolved_via=c.resolved_via)
    c.website, c.careers_url, c.ats, c.ats_slug, c.resolved_via = r["website"], r["careers_url"], r["ats"], r["ats_slug"], r["resolved_via"]
    n = len(r["jobs"])
    c.last_scan, c.scan_note = now(), f"{r['note']} ({n} postings)"
    c.sponsor_status, c.sponsor_match = sponsor_service.check(db, c.name, c.kvk)
    failed = n == 0 and any(k in r["note"] for k in ("not found", "no careers", "error"))
    c.fail_count = 0 if n else min((c.fail_count or 0) + (1 if failed else 0), 6)
    hours = 12 if n else 168 * (1 + c.fail_count)                                  # back off on dead ends
    c.next_scan = now() + dt.timedelta(hours=hours)
    db.commit()
    ensure_logo(db, c); db.commit()
    new = store_jobs(db, c, r["jobs"]); db.commit()
    return new
