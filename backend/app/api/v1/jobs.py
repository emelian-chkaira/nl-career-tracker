from typing import Annotated
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload
from app.core import ratelimit
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import optional_user, client_ip
from app.models import Job, User, UserJob
from app.schemas.job import JobOut, SearchOut
from app.services import jobs_service, search_service as ss, task_service
from app.crawler import dates

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=SearchOut, summary="Search jobs (full-text + semantic + filters)")
def list_jobs(p: Annotated[ss.SearchParams, Query()], db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    return jobs_service.search(db, p, user)


@router.post("/search", response_model=SearchOut, summary="Same as GET /jobs, parameters in the JSON body (used by saved searches)")
def search_post(p: ss.SearchParams, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    return jobs_service.search(db, p, user)


@router.get("/suggest", summary="Autocomplete: skills, companies, job titles, concepts")
def suggest(q: str = Query("", max_length=60), db: Session = Depends(get_db)):
    q = q.strip().lower()
    if len(q) < 2: return {"skills": [], "companies": [], "titles": [], "concepts": []}
    from app.crawler.search import ONTOLOGY
    like = q + "%"
    return {
        "skills": db.execute(text("SELECT skill FROM job_skills WHERE skill LIKE :l GROUP BY skill ORDER BY count(*) DESC LIMIT 6"), {"l": like}).scalars().all(),
        "companies": db.execute(text("SELECT name FROM companies WHERE lower(name) LIKE :l OR lower(name) LIKE :l2 ORDER BY name LIMIT 6"), {"l": like, "l2": "% " + like}).scalars().all(),
        "titles": db.execute(text("SELECT title FROM jobs WHERE status='open' AND lower(title) LIKE :l2 GROUP BY title ORDER BY count(*) DESC LIMIT 6"), {"l2": "%" + like}).scalars().all(),
        "concepts": [k for k in ONTOLOGY if k.startswith(q)][:5],
    }


@router.post("/live-search", summary="Ask the worker to re-read the most relevant companies' career pages right now")
def live_search(request: Request, q: str = Query(..., min_length=2, max_length=120), db: Session = Depends(get_db)):
    if not ratelimit.allow("live:" + client_ip(request), 6, 120): raise HTTPException(429, "live search is rate limited")
    t = task_service.enqueue(db, "live_search", {"q": q.strip()})
    return {"task_id": t.id, "status": t.status}


@router.get("/{job_id}", response_model=JobOut)
def job_detail(job_id: int, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    j = db.scalar(select(Job).where(Job.id == job_id).options(selectinload(Job.company), selectinload(Job.skills)))
    if not j: raise HTTPException(404, "job not found")
    if len(j.description or "") < 200 and j.source == "company-site":          # lazily read the full posting from the employer's own page
        from app.crawler import discovery
        try:
            d = discovery.fetch_detail(j.url)
            if d.get("description"): j.description = d["description"]
            pd = dates.norm_date(d.get("posted_at"))
            if pd and not j.posted_at:
                import datetime as dt; j.posted_at = dt.date.fromisoformat(pd)
            db.commit()
        except Exception: db.rollback()
    stage = db.get(UserJob, (user.id, j.id)) if user else None
    return jobs_service.to_out(j, user, {j.id: stage.stage} if stage else {}, full=True)
