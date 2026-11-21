"""Crawler / operator endpoints (open to any signed-in user unless CAREERS_OPEN_CRAWLER=false; user management and deletes stay admin-only). They only ENQUEUE work; the worker process executes it."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db
from app.core.deps import admin_user, current_user, operator_user
from app.models import Task, Company, Job, User, Sponsor, EmailOutbox
from app.services import task_service, maintenance_service, policy_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(operator_user)])
KINDS = {"scan_all", "scan_unscanned", "scan_company", "discover", "census", "internships", "broad_sources", "logos", "sponsors_refresh", "embed", "live_search"}


class TaskIn(BaseModel):
    kind: str
    payload: dict = {}


@router.post("/tasks", status_code=202)
def create_task(body: TaskIn, db: Session = Depends(get_db)):
    if body.kind not in KINDS: raise HTTPException(400, f"kind must be one of {sorted(KINDS)}")
    t = task_service.enqueue(db, body.kind, body.payload); return {"id": t.id, "status": t.status}


@router.get("/tasks")
def tasks(db: Session = Depends(get_db)):
    return [{"id": t.id, "kind": t.kind, "status": t.status, "progress": t.progress, "error": t.error, "created_at": t.created_at, "finished_at": t.finished_at}
            for t in db.scalars(select(Task).order_by(Task.id.desc()).limit(30))]


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    one = lambda sql: db.execute(text(sql)).scalar()
    return {"users": one("SELECT count(*) FROM users"), "companies": one("SELECT count(*) FROM companies"), "companies_scanned": one("SELECT count(*) FROM companies WHERE last_scan IS NOT NULL"),
            "companies_with_jobs": one("SELECT count(DISTINCT company_id) FROM jobs WHERE status='open'"), "open_jobs": one("SELECT count(*) FROM jobs WHERE status='open'"),
            "embedded_jobs": one("SELECT count(*) FROM jobs WHERE embedding IS NOT NULL"), "sponsors": one("SELECT count(*) FROM sponsors"),
            "saved_searches": one("SELECT count(*) FROM saved_searches"), "emails_pending": one("SELECT count(*) FROM email_outbox WHERE status='pending'"),
            "scan_outcomes": [dict(note=r[0], n=r[1]) for r in db.execute(text("SELECT split_part(scan_note,' (',1) n, count(*) FROM companies WHERE last_scan IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 12"))]}


@router.get("/worker", summary="Live view of the crawler worker: throughput, backlog and the latest scans")
def worker(db: Session = Depends(get_db)):
    one = lambda sql: db.execute(text(sql)).scalar()
    per_min = [{"t": r[0].isoformat(), "n": r[1]} for r in db.execute(text(
        "SELECT date_trunc('minute', last_scan) m, count(*) FROM companies WHERE last_scan > now() - interval '30 minutes' GROUP BY 1 ORDER BY 1"))]
    recent = [{"name": r[0], "ats": r[1], "note": r[2], "at": r[3].isoformat()} for r in db.execute(text(
        "SELECT name, ats, scan_note, last_scan FROM companies WHERE last_scan IS NOT NULL ORDER BY last_scan DESC LIMIT 15"))]
    idle = one("SELECT extract(epoch FROM now() - max(last_scan)) FROM companies")
    total = one("SELECT count(*) FROM companies WHERE (website IS NOT NULL OR ats_slug IS NOT NULL) AND coalesce(ats,'') NOT LIKE 'board:%'")
    due = one("SELECT count(*) FROM companies WHERE (website IS NOT NULL OR ats_slug IS NOT NULL) AND coalesce(ats,'') NOT LIKE 'board:%' AND (next_scan IS NULL OR next_scan <= now())")
    last10 = one("SELECT count(*) FROM companies WHERE last_scan > now() - interval '10 minutes'")
    return {"running": idle is not None and idle < 300, "idle_seconds": int(idle) if idle is not None else None,
            "total": total, "due": due, "per_min": per_min, "recent": recent,
            "rate_per_min": round(last10 / 10, 1), "eta_minutes": round(due / (last10 / 10)) if last10 else None,
            "open_jobs": one("SELECT count(*) FROM jobs WHERE status='open'"),
            "new_jobs_hour": one("SELECT count(*) FROM jobs WHERE first_seen > now() - interval '1 hour'"),
            "saved_careers_pages": one("SELECT count(*) FROM companies WHERE careers_url IS NOT NULL")}


@router.get("/policy", summary="The storage policy in effect (env defaults + overrides saved from the Crawler page)")
def policy(db: Session = Depends(get_db)):
    return {**policy_service.current(), "defaults": policy_service.defaults(), "by_domain": {(r[0] or "unclassified"): r[1] for r in db.execute(text("SELECT domain, count(*) FROM jobs WHERE status='open' GROUP BY 1 ORDER BY 2 DESC"))}}


class PolicyIn(BaseModel):
    keep_domains: list[str] = []
    max_job_age_days: int = 0
    delete_expired_after_days: int = 0


@router.put("/policy", dependencies=[Depends(admin_user)], summary="Save the storage policy (takes effect for the API and the worker within seconds)")
def set_policy(body: PolicyIn, db: Session = Depends(get_db)):
    try: policy_service.save(db, body.keep_domains, body.max_job_age_days, body.delete_expired_after_days)
    except ValueError as e: raise HTTPException(400, str(e))
    return policy(db)


@router.delete("/policy", dependencies=[Depends(admin_user)], summary="Drop the saved overrides and go back to the environment defaults")
def reset_policy(db: Session = Depends(get_db)):
    policy_service.reset(db); return policy(db)


@router.get("/maintenance/{action}/preview", summary="How many rows an action would affect right now (changes nothing)")
def maintenance_preview(action: str, db: Session = Depends(get_db)):
    if action not in maintenance_service.ACTIONS: raise HTTPException(404, f"action must be one of {sorted(maintenance_service.ACTIONS)}")
    return maintenance_service.preview(db, action)


@router.post("/maintenance/{action}", dependencies=[Depends(admin_user)], summary="Housekeeping: backfill_domains | purge | prune | clear_jobs | clear_all (destructive ones need confirm=true)")
def maintenance(action: str, body: dict | None = None, db: Session = Depends(get_db)):
    if action not in maintenance_service.ACTIONS: raise HTTPException(404, f"action must be one of {sorted(maintenance_service.ACTIONS)}")
    if action in maintenance_service.DESTRUCTIVE and not (body or {}).get("confirm"): raise HTTPException(400, "this deletes data and cannot be undone: send {\"confirm\": true}")
    return maintenance_service.ACTIONS[action](db)


@router.get("/users", dependencies=[Depends(admin_user)])
def users(db: Session = Depends(get_db)):
    return [{"id": str(u.id), "email": u.email, "role": u.role, "active": u.is_active, "created_at": u.created_at} for u in db.scalars(select(User).order_by(User.created_at.desc()).limit(200))]


@router.patch("/users/{uid}", dependencies=[Depends(admin_user)])
def update_user(uid: str, body: dict, db: Session = Depends(get_db)):
    import uuid
    u = db.get(User, uuid.UUID(uid))
    if not u: raise HTTPException(404)
    if "role" in body and body["role"] in ("user", "admin"): u.role = body["role"]
    if "is_active" in body: u.is_active = bool(body["is_active"])
    db.commit(); return {"ok": True}


@router.post("/companies", status_code=201)
def add_company(body: dict, db: Session = Depends(get_db)):
    from app.services import ingest_service as ing
    c = ing.add_company(db, body["name"], body.get("website"), body.get("careers_url"), body.get("kvk")); db.commit()
    return {"id": c.id, "name": c.name}


@router.delete("/companies/{cid}", status_code=204, dependencies=[Depends(admin_user)])
def delete_company(cid: int, db: Session = Depends(get_db)):
    c = db.get(Company, cid)
    if c: db.delete(c); db.commit()


# ------------------------------------------------------------------ companies: list / add / edit / rescan / delete / export
import csv, io, re as _re
from fastapi.responses import StreamingResponse
from app.models import UserJob

CO_FILTERS = {
    "has_jobs": "EXISTS (SELECT 1 FROM jobs j WHERE j.company_id = c.id AND j.status = 'open')",
    "no_jobs": "c.last_scan IS NOT NULL AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.company_id = c.id AND j.status = 'open')",
    "failing": "c.fail_count > 0",
    "never": "c.last_scan IS NULL",
    "due": "(c.website IS NOT NULL OR c.ats_slug IS NOT NULL) AND (c.next_scan IS NULL OR c.next_scan <= now())",
    "no_site": "c.website IS NULL AND c.ats_slug IS NULL",
}
CO_SORT = {"name": "name ASC", "last_scan": "last_scan DESC NULLS LAST", "jobs": "open_jobs DESC, name ASC", "failing": "fail_count DESC, name ASC", "newest": "id DESC"}


def _co_where(q: str | None, status: str | None) -> tuple[str, dict]:
    w, a = ["TRUE"], {}
    if q: w.append("(c.name ILIKE :q OR c.website ILIKE :q OR c.careers_url ILIKE :q)"); a["q"] = f"%{q}%"
    if status and status != "all":
        if status not in CO_FILTERS: raise HTTPException(400, f"status must be one of {['all', *CO_FILTERS]}")
        w.append(CO_FILTERS[status])
    return " AND ".join(w), a


@router.get("/companies", summary="Browse the companies the crawler knows")
def list_companies(q: str | None = None, status: str | None = None, sort: str = "name", page: int = 1, limit: int = 25, db: Session = Depends(get_db)):
    if sort not in CO_SORT: raise HTTPException(400, f"sort must be one of {sorted(CO_SORT)}")
    limit = max(1, min(limit, 100)); where, a = _co_where(q, status)
    total = db.execute(text(f"SELECT count(*) FROM companies c WHERE {where}"), a).scalar()
    rows = db.execute(text(f"""SELECT * FROM (SELECT c.id, c.name, c.website, c.careers_url, c.ats, c.city, c.source, c.last_scan, c.next_scan, c.scan_note, c.fail_count, c.notes,
        (SELECT count(*) FROM jobs j WHERE j.company_id = c.id AND j.status = 'open') open_jobs FROM companies c WHERE {where}) t ORDER BY {CO_SORT[sort]} LIMIT :l OFFSET :o"""),
        {**a, "l": limit, "o": (max(page, 1) - 1) * limit}).mappings().all()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "limit": limit}


class CompanyPatch(BaseModel):
    name: str | None = None
    website: str | None = None
    careers_url: str | None = None
    notes: str | None = None


def _url(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v: return None
    if not _re.match(r"https?://", v): v = "https://" + v
    return v


@router.patch("/companies/{cid}", summary="Edit a company. Changing the careers URL clears the saved ATS and schedules a re-scan.")
def patch_company(cid: int, body: CompanyPatch, db: Session = Depends(get_db)):
    c = db.get(Company, cid)
    if not c: raise HTTPException(404)
    if body.name is not None:
        n = body.name.strip()
        if not n: raise HTTPException(400, "name cannot be empty")
        if n != c.name and db.scalar(select(Company.id).where(Company.name == n)): raise HTTPException(409, "a company with that name already exists")
        c.name = n
    if body.website is not None: c.website = _url(body.website)
    if body.notes is not None: c.notes = body.notes.strip() or None
    if body.careers_url is not None and _url(body.careers_url) != c.careers_url:
        c.careers_url = _url(body.careers_url); c.ats = c.ats_slug = c.resolved_via = None; c.next_scan = None; c.fail_count = 0
    db.commit(); return {"ok": True}


@router.post("/companies/{cid}/scan", status_code=202, summary="Queue a re-scan of one company now")
def scan_one(cid: int, db: Session = Depends(get_db)):
    c = db.get(Company, cid)
    if not c: raise HTTPException(404)
    c.next_scan = None; db.commit()
    t = task_service.enqueue(db, "scan_company", {"id": cid}); return {"task_id": t.id}


class BulkCompanies(BaseModel):
    text: str
    scan: bool = True


@router.post("/companies/bulk", status_code=201, summary="Add many companies at once: one per line as 'Name', 'Name, website' or 'Name | website' (or just a website)")
def bulk_companies(body: BulkCompanies, db: Session = Depends(get_db)):
    from urllib.parse import urlparse
    from app.services import ingest_service as ing
    added, existing, bad = 0, 0, []
    for raw in body.text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"): continue
        parts = [x.strip() for x in _re.split(r"\s*[|,;\t]\s*", line, maxsplit=1)]
        name, site = (parts[0], parts[1] if len(parts) > 1 else None)
        if _re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/.*)?$", name) and not site:                     # just a website: derive the name from the domain
            site, host = name, urlparse(_url(name)).netloc.lower().removeprefix("www.")
            name = host.split(".")[-2].capitalize() if host.count(".") else host
        if not name or len(name) > 200: bad.append(line[:60]); continue
        before = db.scalar(select(Company.id).where(Company.name == name))
        ing.add_company(db, name, website=_url(site), source="manual")
        existing += bool(before); added += not before
    db.commit()
    task = task_service.enqueue(db, "scan_unscanned").id if body.scan and added else None
    return {"added": added, "already_known": existing, "ignored": bad, "scan_task_id": task}


# ------------------------------------------------------------------ jobs: browse / bulk change / export
JOB_SORT = {"newest": "j.first_seen DESC, j.id DESC", "oldest": "j.first_seen ASC, j.id ASC", "company": "c.name ASC, j.title ASC", "title": "j.title ASC"}


def _job_where(q, status, domain, company_id, older_than_days, no_domain=False) -> tuple[str, dict]:
    w, a = ["TRUE"], {}
    if q: w.append("(j.title ILIKE :q OR c.name ILIKE :q)"); a["q"] = f"%{q}%"
    if status and status != "all": w.append("j.status = :st"); a["st"] = status
    if domain: w.append("j.domain = :dm"); a["dm"] = domain
    if company_id: w.append("j.company_id = :cid"); a["cid"] = company_id
    if older_than_days: w.append("COALESCE(j.posted_at, j.first_seen::date) < current_date - :od"); a["od"] = older_than_days
    return " AND ".join(w), a


@router.get("/jobs", summary="Browse stored jobs")
def list_jobs(q: str | None = None, status: str | None = "open", domain: str | None = None, company_id: int | None = None, older_than_days: int | None = None,
              sort: str = "newest", page: int = 1, limit: int = 25, db: Session = Depends(get_db)):
    if sort not in JOB_SORT: raise HTTPException(400, f"sort must be one of {sorted(JOB_SORT)}")
    limit = max(1, min(limit, 100)); where, a = _job_where(q, status, domain, company_id, older_than_days)
    base = f"FROM jobs j JOIN companies c ON c.id = j.company_id WHERE {where}"
    total = db.execute(text(f"SELECT count(*) {base}"), a).scalar()
    rows = db.execute(text(f"""SELECT j.id, j.title, j.url, j.location, j.city, j.status, j.domain, j.job_type, j.posted_at, j.first_seen, j.last_seen, c.id company_id, c.name company,
        (SELECT count(*) FROM user_jobs u WHERE u.job_id = j.id) saved_by {base} ORDER BY {JOB_SORT[sort]} LIMIT :l OFFSET :o"""), {**a, "l": limit, "o": (max(page, 1) - 1) * limit}).mappings().all()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "limit": limit}


class JobBulk(BaseModel):
    action: str                                   # delete | expire | reopen
    ids: list[int] = []                           # explicit selection ...
    all_matching: bool = False                    # ... or everything the filters below match
    q: str | None = None
    status: str | None = None
    domain: str | None = None
    company_id: int | None = None
    older_than_days: int | None = None
    confirm: bool = False


@router.post("/jobs/bulk", summary="Delete / expire / reopen the selected jobs (or all jobs matching the filters). Deleting is admin-only.")
def jobs_bulk(body: JobBulk, user: User = Depends(operator_user), db: Session = Depends(get_db)):
    if body.action not in ("delete", "expire", "reopen"): raise HTTPException(400, "action must be delete, expire or reopen")
    if body.action == "delete" and user.role != "admin": raise HTTPException(403, "only an admin can delete jobs")
    if body.all_matching:
        if not body.confirm: raise HTTPException(400, "this changes every matching job: send confirm=true")
        where, a = _job_where(body.q, body.status, body.domain, body.company_id, body.older_than_days)
        ids = [r[0] for r in db.execute(text(f"SELECT j.id FROM jobs j JOIN companies c ON c.id = j.company_id WHERE {where}"), a)]
    else: ids = body.ids[:5000]
    if not ids: return {"changed": 0}
    if body.action == "delete": n = db.execute(text("DELETE FROM jobs WHERE id = ANY(:i)"), {"i": ids}).rowcount
    else: n = db.execute(text("UPDATE jobs SET status = :s WHERE id = ANY(:i)"), {"s": "expired" if body.action == "expire" else "open", "i": ids}).rowcount
    db.commit(); return {"changed": n}


@router.get("/export/{what}.csv", summary="Download jobs or companies as CSV")
def export(what: str, db: Session = Depends(get_db)):
    if what == "jobs":
        sql = "SELECT j.id, c.name company, j.title, j.domain, j.job_type, j.location, j.city, j.status, j.posted_at, j.first_seen, j.last_seen, j.url FROM jobs j JOIN companies c ON c.id = j.company_id ORDER BY j.id"
    elif what == "companies":
        sql = "SELECT id, name, website, careers_url, ats, ats_slug, city, source, sponsor_status, last_scan, next_scan, fail_count, scan_note FROM companies ORDER BY id"
    else: raise HTTPException(404, "export jobs or companies")
    def rows():
        res = db.execute(text(sql)); buf = io.StringIO(); w = csv.writer(buf); w.writerow(res.keys()); yield buf.getvalue()
        for r in res:
            buf.seek(0); buf.truncate(); w.writerow(["" if v is None else str(v) for v in r]); yield buf.getvalue()
    return StreamingResponse(rows(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={what}.csv"})


# ------------------------------------------------------------------ task queue controls
@router.post("/tasks/{tid}/cancel", summary="Cancel a queued task, or mark a stuck 'running' task as stopped")
def cancel_task(tid: int, db: Session = Depends(get_db)):
    import datetime as dt
    t = db.get(Task, tid)
    if not t: raise HTTPException(404)
    if t.status in ("queued", "running"):
        t.status, t.error, t.finished_at = "failed", "cancelled by operator", dt.datetime.now(dt.timezone.utc); db.commit()
    return {"ok": True}


@router.delete("/tasks", summary="Remove finished and failed tasks from the history")
def clear_tasks(db: Session = Depends(get_db)):
    n = db.execute(text("DELETE FROM tasks WHERE status IN ('done', 'failed')")).rowcount; db.commit(); return {"removed": n}
