from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{tid}", summary="Progress of a queued task (e.g. a live search)")
def task(tid: int, db: Session = Depends(get_db)):
    t = db.get(Task, tid)
    if not t or t.kind != "live_search": raise HTTPException(404)          # only live-search progress is public
    return {"id": t.id, "status": t.status, "progress": t.progress}
