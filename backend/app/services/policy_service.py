"""The storage policy (which job domains to keep, how old jobs may be, when expired jobs are deleted).

Defaults come from the environment (CAREERS_KEEP_DOMAINS ...). An operator can override them in the Crawler page; overrides are saved in the database (kv table),
so they survive restarts and are shared by the API and the worker (which re-reads them every few seconds)."""
import json, time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import SessionLocal
from app.crawler.domains import DOMAINS, parse
from app.models import KV

KEY = "policy"
_cache: dict = {"at": 0.0, "v": None}


def defaults() -> dict:
    return {"keep_domains": sorted(parse(settings.keep_domains)), "max_job_age_days": int(settings.max_job_age_days or 0), "delete_expired_after_days": int(settings.delete_expired_after_days or 0)}


def current() -> dict:
    """Effective policy (env defaults + saved overrides). Cheap: cached for 5 seconds."""
    if time.time() - _cache["at"] < 5 and _cache["v"] is not None and _cache["env"] == (settings.keep_domains, settings.max_job_age_days, settings.delete_expired_after_days): return _cache["v"]
    p = defaults()
    try:
        with SessionLocal() as db:
            raw = db.scalar(select(KV.v).where(KV.k == KEY))
        if raw: p.update({k: v for k, v in json.loads(raw).items() if k in p})
    except Exception: pass
    _cache.update(at=time.time(), v=p, env=(settings.keep_domains, settings.max_job_age_days, settings.delete_expired_after_days)); return p


def save(db: Session, keep_domains: list[str], max_job_age_days: int, delete_expired_after_days: int) -> dict:
    bad = [d for d in keep_domains if d not in DOMAINS]
    if bad: raise ValueError(f"unknown domain(s): {', '.join(bad)}")
    if max_job_age_days < 0 or delete_expired_after_days < 0: raise ValueError("days cannot be negative")
    p = {"keep_domains": sorted(set(keep_domains)), "max_job_age_days": int(max_job_age_days), "delete_expired_after_days": int(delete_expired_after_days)}
    row = db.get(KV, KEY) or KV(k=KEY); row.v = json.dumps(p); db.add(row); db.commit()
    _cache["v"] = None; return p


def reset(db: Session) -> dict:
    row = db.get(KV, KEY)
    if row: db.delete(row); db.commit()
    _cache["v"] = None; return current()
