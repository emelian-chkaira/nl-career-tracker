"""Worker process: `python -m app.workers.run`.
 - executes queued tasks (scan, discovery, live search, embeddings…)
 - scheduler: refreshes stale companies, embeds new jobs, runs job alerts and sends the e-mail outbox.
Scale out by running more worker containers (tasks are claimed with SKIP LOCKED)."""
import logging, time, traceback, signal
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, exists
from app.core.db import SessionLocal
from app.core.config import settings
from app.models import Company, Job
from app.services import task_service, alert_service, sponsor_service, maintenance_service
from . import tasks, embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for _n in ("httpx", "httpcore", "playwright"): logging.getLogger(_n).setLevel(logging.WARNING)      # one INFO line per fetched page (incl. harmless 301/302 redirects) drowns the real worker logs
log = logging.getLogger("worker")
STOP = False
HANDLERS = {
    "scan_all": lambda t, db: tasks.scan_all(t, db), "scan_unscanned": lambda t, db: tasks.scan_all(t, db, unscanned=True), "scan_company": tasks.scan_company,
    "discover": tasks.discover, "census": tasks.census, "internships": tasks.internships, "broad_sources": tasks.broad_sources, "logos": tasks.logos, "live_search": tasks.live_search,
    "sponsors_refresh": lambda t, db: (sponsor_service.refresh(db), sponsor_service.recheck_all(db)),
    "mail_sync": tasks.mail_sync,
    "embed": lambda t, db: task_service.progress(db, t, embedded=embeddings.backfill()),
}


def _every(last: dict, key: str, seconds: float) -> bool:
    if time.time() - last.get(key, 0) >= seconds: last[key] = time.time(); return True
    return False


def main():
    global STOP
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("STOP", True)); signal.signal(signal.SIGINT, lambda *_: globals().__setitem__("STOP", True))
    last: dict = {}
    log.info("worker started")
    while not STOP:
        did = False
        with SessionLocal() as db:
            t = task_service.claim(db)
            if t:
                did = True; log.info("task %s #%s %s", t.kind, t.id, t.payload)
                try:
                    HANDLERS[t.kind](t, db); task_service.finish(db, t)
                except Exception as e:
                    db.rollback(); log.error("task failed: %s", traceback.format_exc()); task_service.finish(db, db.get(type(t), t.id), str(e)[:300])
        if not did:
            try:
                with SessionLocal() as db:
                    if _every(last, "alerts", 300): n = alert_service.run_due(db); alert_service.send_outbox(db); n and log.info("alerts created: %s", n)
                    if _every(last, "embed", 120): embeddings.backfill(limit=500)
                    if _every(last, "purge", 86400): r = maintenance_service.purge_old(db); any(r.values()) and log.info("retention purge: %s", r)      # daily retention
                    if _every(last, "refresh", 5): _refresh(db)       # keep jobs fresh: top up the scan pool with the next due companies
            except Exception: log.error("scheduler error: %s", traceback.format_exc())
            time.sleep(3)


POOL_SIZE = 20; STUCK_AFTER = 900                      # scans in flight at once; a scan older than 15 min is treated as hung and its slot is reused
_pool = ThreadPoolExecutor(POOL_SIZE + 8); _inflight: dict[int, float] = {}


def _refresh(db):
    """Continuously keep POOL_SIZE company scans running. One hung scan can no longer stall the others (no batch barrier)."""
    import datetime as dt
    now = time.time()
    for cid, t0 in list(_inflight.items()):
        if now - t0 > STUCK_AFTER: log.warning("scan of company %s looks hung (>%ss); freeing its slot", cid, STUCK_AFTER); _inflight.pop(cid, None)
    free = POOL_SIZE - len(_inflight)
    if free <= 0: return
    has_open = exists().where(Job.company_id == Company.id, Job.status == "open")      # companies that actually have live postings are refreshed first
    q = select(Company.id).where((Company.website.is_not(None)) | (Company.ats_slug.is_not(None)),
                                 Company.ats.is_(None) | ~Company.ats.like("board:%"),      # board-level sources are scanned per board, never per company (they would return instantly and clog the queue)
                                 (Company.next_scan.is_(None)) | (Company.next_scan <= dt.datetime.now(dt.timezone.utc)))
    if _inflight: q = q.where(Company.id.not_in(list(_inflight)))
    for cid in db.scalars(q.order_by(has_open.desc(), Company.next_scan.asc().nullsfirst()).limit(free)):
        _inflight[cid] = time.time()
        _pool.submit(_run_scan, cid)


def _run_scan(cid: int):
    try: _safe(tasks._scan_one, cid)
    finally: _inflight.pop(cid, None)


def _safe(fn, *a):
    try: return fn(*a)
    except Exception as e: log.warning("%s failed: %s", fn.__name__, e)


if __name__ == "__main__": main()
