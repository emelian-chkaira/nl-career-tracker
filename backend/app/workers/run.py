"""Worker process: `python -m app.workers.run`.
 - executes queued tasks (scan, discovery, live search, embeddings…)
 - scheduler: refreshes stale companies, embeds new jobs, runs job alerts and sends the e-mail outbox.
Scale out by running more worker containers (tasks are claimed with SKIP LOCKED)."""
import logging, time, traceback, signal
from sqlalchemy import select
from app.core.db import SessionLocal
from app.core.config import settings
from app.models import Company
from app.services import task_service, alert_service, sponsor_service
from . import tasks, embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for _n in ("httpx", "httpcore", "playwright"): logging.getLogger(_n).setLevel(logging.WARNING)      # one INFO line per fetched page (incl. harmless 301/302 redirects) drowns the real worker logs
log = logging.getLogger("worker")
STOP = False
HANDLERS = {
    "scan_all": lambda t, db: tasks.scan_all(t, db), "scan_unscanned": lambda t, db: tasks.scan_all(t, db, unscanned=True), "scan_company": tasks.scan_company,
    "discover": tasks.discover, "census": tasks.census, "internships": tasks.internships, "broad_sources": tasks.broad_sources, "logos": tasks.logos, "live_search": tasks.live_search,
    "sponsors_refresh": lambda t, db: (sponsor_service.refresh(db), sponsor_service.recheck_all(db)),
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
                    if _every(last, "refresh", 30):                       # keep jobs fresh: next due companies (backs off on dead ends)
                        import datetime as dt
                        ids = list(db.scalars(select(Company.id).where((Company.website.is_not(None)) | (Company.ats_slug.is_not(None)),
                                                                         (Company.next_scan.is_(None)) | (Company.next_scan <= dt.datetime.now(dt.timezone.utc))).order_by(Company.next_scan.asc().nullsfirst()).limit(24)))
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(6) as ex: list(ex.map(lambda i: _safe(tasks._scan_one, i), ids))
            except Exception: log.error("scheduler error: %s", traceback.format_exc())
            time.sleep(3)


def _safe(fn, *a):
    try: return fn(*a)
    except Exception as e: log.warning("%s failed: %s", fn.__name__, e)


if __name__ == "__main__": main()
