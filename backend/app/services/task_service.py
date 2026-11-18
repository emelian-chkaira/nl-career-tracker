import datetime as dt
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import Task


def enqueue(db: Session, kind: str, payload: dict | None = None, dedupe: bool = True) -> Task:
    """Queue a task; if the same kind is already queued/running, return that one instead (idempotent triggers)."""
    if dedupe:
        t = db.scalar(select(Task).where(Task.kind == kind, Task.status.in_(("queued", "running"))).order_by(Task.id.desc()))
        if t and (payload or {}) == (t.payload or {}): return t
    t = Task(kind=kind, payload=payload or {}); db.add(t); db.commit(); return t


def claim(db: Session) -> Task | None:
    """Atomically take the oldest queued task (SKIP LOCKED: safe with several workers)."""
    row = db.execute(text("""UPDATE tasks SET status='running', started_at=now() WHERE id = (
        SELECT id FROM tasks WHERE status='queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id""")).first()
    db.commit()
    return db.get(Task, row[0]) if row else None


def progress(db: Session, t: Task, **kw):
    t.progress = {**(t.progress or {}), **kw}; db.commit()


def finish(db: Session, t: Task, error: str | None = None):
    t.status = "failed" if error else "done"; t.error = error; t.finished_at = dt.datetime.now(dt.timezone.utc); db.commit()
