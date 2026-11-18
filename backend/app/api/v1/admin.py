"""Operator endpoints (admin role). They only ENQUEUE work; the worker process executes it."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.db import get_db
from app.core.deps import admin_user, current_user
from app.models import Task, Company, Job, User, Sponsor, EmailOutbox
from app.services import task_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])
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


@router.get("/users")
def users(db: Session = Depends(get_db)):
    return [{"id": str(u.id), "email": u.email, "role": u.role, "active": u.is_active, "created_at": u.created_at} for u in db.scalars(select(User).order_by(User.created_at.desc()).limit(200))]


@router.patch("/users/{uid}")
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


@router.delete("/companies/{cid}", status_code=204)
def delete_company(cid: int, db: Session = Depends(get_db)):
    c = db.get(Company, cid)
    if c: db.delete(c); db.commit()
