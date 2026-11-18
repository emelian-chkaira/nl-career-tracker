import time
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])
_cache: dict = {}


@router.get("/overview", summary="Market dashboard data (cached 5 minutes)")
def overview(days: int = Query(90, ge=7, le=365), category: str = "tech", kind: str | None = None, db: Session = Depends(get_db)):
    key = (days, category, kind)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 300: return hit[1]
    data = analytics_service.overview(db, days, category or None, kind)
    _cache[key] = (time.time(), data); return data
