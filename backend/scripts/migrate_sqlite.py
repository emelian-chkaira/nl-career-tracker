"""One-off: copy the legacy SQLite database (careers.db) into Postgres, keeping ids. Usage: python -m scripts.migrate_sqlite path/to/careers.db [--truncate]"""
import sys, sqlite3, datetime as dt
from sqlalchemy import text
from app.core.db import SessionLocal
from app.models import Company, Job, JobSkill, Sponsor, KV
from app.services import ingest_service as ing
from app.crawler import dates, nl


def ts(v):
    if not v: return None
    try: return dt.datetime.fromisoformat(v).replace(tzinfo=dt.timezone.utc)
    except Exception: return None


def main(path, truncate=False):
    src = sqlite3.connect(path); src.row_factory = sqlite3.Row
    with SessionLocal() as db:
        if truncate:
            db.execute(text("TRUNCATE job_skills, user_jobs, jobs, companies, sponsors RESTART IDENTITY CASCADE")); db.commit()
        rows = src.execute("SELECT * FROM sponsor").fetchall()
        db.bulk_save_objects([Sponsor(name=r["name"], name_norm=r["name_norm"], kvk=r["kvk"], snapshot=r["snapshot"]) for r in rows]); db.commit()
        snap = src.execute("SELECT v FROM kv WHERE k='sponsor_snapshot'").fetchone()
        if snap: db.merge(KV(k="sponsor_snapshot", v=snap["v"])); db.commit()
        print("sponsors", len(rows))
        cols = {r[1] for r in src.execute("PRAGMA table_info(company)")}
        for r in src.execute("SELECT * FROM company").fetchall():
            g = lambda k: r[k] if k in cols else None
            db.add(Company(id=r["id"], name=r["name"], website=g("website"), careers_url=g("careers_url"), ats=g("ats"), ats_slug=g("ats_slug"), resolved_via=g("resolved_via"),
                           sponsor_status=g("sponsor_status") or "unchecked", sponsor_match=g("sponsor_match"), kvk=g("kvk"), logo=g("logo"), city=g("city"), address=g("address"),
                           description=g("description"), source=g("source"), last_scan=ts(g("last_scan")), next_scan=ts(g("next_scan")), scan_note=g("scan_note"), fail_count=g("fail_count") or 0, notes=g("notes")))
        db.commit(); print("companies", db.execute(text("SELECT count(*) FROM companies")).scalar())
        n = 0
        for r in src.execute("SELECT * FROM job").fetchall():
            if not ing.looks_like_job(r["title"], r["url"]) or not nl.is_nl(r["location"], r["url"], r["source"]): continue
            posted = dates.norm_date(r["posted_at"]); posted = dt.date.fromisoformat(posted) if posted else None
            j = Job(id=r["id"], company_id=r["company_id"], title=r["title"], location=r["location"], city=ing.city_of(r["location"] or ""), url=r["url"], source=r["source"] or "company-site",
                    description=r["description"], category=nl.category(r["title"]), job_type=r["job_type"] or "job", language=r["language"] or "english_ok",
                    remote=bool(r["location"] and "remote" in r["location"].lower()), salary_min=r["salary_min"], salary_max=r["salary_max"], salary_period=r["salary_period"],
                    posted_at=posted, first_seen=ts(r["first_seen"]) or dt.datetime.now(dt.timezone.utc), last_seen=ts(r["last_seen"]) or dt.datetime.now(dt.timezone.utc),
                    status=r["status"] or "open", dedupe_key=ing.dedupe_key(r["company_id"], r["title"], r["location"]))
            j.skills = [JobSkill(skill=s) for s in ing.skills_of(r["title"], r["description"] or "")]
            db.add(j); n += 1
            if n % 500 == 0: db.commit()
        db.commit()
        db.execute(text("SELECT setval(pg_get_serial_sequence('companies','id'), (SELECT coalesce(max(id),1) FROM companies))"))
        db.execute(text("SELECT setval(pg_get_serial_sequence('jobs','id'), (SELECT coalesce(max(id),1) FROM jobs))")); db.commit()
        print("jobs", n)


if __name__ == "__main__":
    main(sys.argv[1], "--truncate" in sys.argv)
