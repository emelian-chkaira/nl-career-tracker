"""Ready-made starter data, so a fresh install has something to show before the crawler has run.

backend/seed/ holds three small gzipped CSV files made from a real crawl:
  companies.csv.gz  Dutch tech employers: name, website, careers page, ATS, city, visa-sponsor status
  jobs.csv.gz       a snapshot of open listings: title, company, city, link, domain, type, skills (NO descriptions)
  sponsors.csv.gz   the public IND register of recognised sponsors
The crawler replaces the snapshot with fresh, complete data as it visits each careers page, so nothing here goes stale for long."""
import csv, gzip, datetime as dt
from pathlib import Path
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.models import Company, Job, JobSkill, Sponsor

DIR = Path(__file__).resolve().parents[2] / "seed"
CO = ["name", "website", "careers_url", "ats", "ats_slug", "sponsor_status", "sponsor_match", "kvk", "city", "source"]
JB = ["company", "title", "location", "city", "url", "category", "domain", "job_type", "language", "remote", "posted_at", "skills"]
SP = ["name", "name_norm", "kvk", "snapshot"]


def _write(name: str, cols: list[str], rows) -> int:
    DIR.mkdir(exist_ok=True); n = 0
    with gzip.open(DIR / name, "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in rows: w.writerow(["" if v is None else v for v in r]); n += 1
    return n


def export(db: Session) -> dict:
    """Write the seed files from the current database (open jobs only, no descriptions, nothing user related)."""
    cos = db.execute(select(*[getattr(Company, c) for c in CO]).order_by(Company.name)).all()
    jobs = db.execute(select(Company.name, Job.title, Job.location, Job.city, Job.url, Job.category, Job.domain, Job.job_type, Job.language, Job.remote, Job.posted_at, func.string_agg(JobSkill.skill, "|"))
                      .join(Job, Job.company_id == Company.id).outerjoin(JobSkill, JobSkill.job_id == Job.id).where(Job.status == "open")
                      .group_by(Company.name, Job.id).order_by(Company.name, Job.id)).all()
    sps = db.execute(select(*[getattr(Sponsor, c) for c in SP]).order_by(Sponsor.id)).all()
    return {"companies": _write("companies.csv.gz", CO, cos), "jobs": _write("jobs.csv.gz", JB, jobs), "sponsors": _write("sponsors.csv.gz", SP, sps)}


def _read(name: str):
    p = DIR / name
    if not p.exists(): return []
    with gzip.open(p, "rt", newline="", encoding="utf-8") as f: return list(csv.DictReader(f))


def available() -> bool: return (DIR / "companies.csv.gz").exists()


def load(db: Session, force: bool = False) -> dict:
    """Import the seed data. Does nothing when the database already holds companies (unless force), and never overwrites existing rows."""
    if not force and db.scalar(select(func.count()).select_from(Company)): return {"skipped": "database already has data"}
    now = dt.datetime.now(dt.timezone.utc); out = {"sponsors": 0, "companies": 0, "jobs": 0}
    if not db.scalar(select(func.count()).select_from(Sponsor)):
        for r in _read("sponsors.csv.gz"): db.add(Sponsor(name=r["name"], name_norm=r["name_norm"], kvk=r["kvk"] or None, snapshot=r["snapshot"] or None)); out["sponsors"] += 1
        db.flush()
    have = {n for (n,) in db.execute(select(Company.name))}
    for r in _read("companies.csv.gz"):
        if r["name"] in have: continue
        db.add(Company(**{k: (r[k] or None) for k in CO}, next_scan=None)); out["companies"] += 1      # next_scan empty: the worker visits it soon and replaces the snapshot
    db.flush()
    ids = dict(db.execute(select(Company.name, Company.id)).all()); known = {u for (u,) in db.execute(select(Job.url))}
    for r in _read("jobs.csv.gz"):
        cid = ids.get(r["company"])
        if not cid or r["url"] in known: continue
        j = Job(company_id=cid, title=r["title"], location=r["location"] or None, city=r["city"] or None, url=r["url"], category=r["category"] or "other", domain=r["domain"] or None,
                job_type=r["job_type"] or "job", language=r["language"] or "english_ok", remote=r["remote"] in ("True", "true", "1"),
                posted_at=dt.date.fromisoformat(r["posted_at"]) if r["posted_at"] else None, first_seen=now, last_seen=now, status="open")
        db.add(j); db.flush()
        for s in filter(None, (r["skills"] or "").split("|")): db.add(JobSkill(job_id=j.id, skill=s))
        known.add(r["url"]); out["jobs"] += 1
    db.commit(); return out
