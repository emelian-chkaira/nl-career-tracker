from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.jobs_service import logo_url
from app.models import Company, Job

router = APIRouter(prefix="/companies", tags=["companies"])


def _out(c: Company, open_jobs: int = 0) -> dict:
    return {"id": c.id, "name": c.name, "website": c.website, "careers_url": c.careers_url, "logo": logo_url(c.logo), "city": c.city, "description": c.description,
            "sponsor_status": c.sponsor_status, "sponsor_match": c.sponsor_match, "ats": c.ats, "last_scan": c.last_scan, "open_jobs": open_jobs}


@router.get("")
def list_companies(q: str = "", city: str = "", hiring: bool = False, page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    cnt = select(Job.company_id.label("cid"), func.count().label("n")).where(Job.status == "open").group_by(Job.company_id).subquery()
    stmt = select(Company, func.coalesce(cnt.c.n, 0)).outerjoin(cnt, cnt.c.cid == Company.id)
    if q: stmt = stmt.where(or_(Company.name.ilike(f"%{q}%"), Company.description.ilike(f"%{q}%")))
    if city: stmt = stmt.where(Company.city.ilike(f"%{city}%"))
    if hiring: stmt = stmt.where(func.coalesce(cnt.c.n, 0) > 0)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(func.coalesce(cnt.c.n, 0).desc(), Company.name).offset((page - 1) * limit).limit(limit)).all()
    return {"items": [_out(c, n) for c, n in rows], "total": total, "page": page, "limit": limit}


@router.get("/{cid}")
def company(cid: int, db: Session = Depends(get_db)):
    c = db.get(Company, cid)
    if not c: raise HTTPException(404, "company not found")
    n = db.scalar(select(func.count()).select_from(Job).where(Job.company_id == cid, Job.status == "open"))
    return _out(c, n)
