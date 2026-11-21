"""Task implementations executed by the worker process."""
import re, time, logging
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from sqlalchemy import select, func
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Company, Job, Task
from app.services import ingest_service as ing, sponsor_service, task_service
from app.crawler import free_discovery, wikidata, seed, clusters, nl, discovery, search as onto
import threading

log = logging.getLogger("worker")
PW_SLOTS = threading.Semaphore(settings.browser_slots)


def _scan_one(cid: int) -> int:
    with SessionLocal() as db:
        return ing.scan_company(db, cid)     # headless-browser concurrency is already capped inside discovery.render_scan


def scan_ids(t: Task, db, ids: list[int]):
    state = {"done": 0, "new_jobs": 0}
    task_service.progress(db, t, total=len(ids), done=0, new_jobs=0)
    def one(cid):
        try: state["new_jobs"] += _scan_one(cid)
        except Exception as e: log.warning("scan %s failed: %s", cid, e)
        state["done"] += 1
        if state["done"] % 10 == 0:
            with SessionLocal() as d2:
                tt = d2.get(Task, t.id); task_service.progress(d2, tt, **state)
    with ThreadPoolExecutor(settings.scan_threads) as ex: list(ex.map(one, ids))
    task_service.progress(db, t, **state)


def scan_all(t, db, unscanned=False):
    q = select(Company.id).where((Company.website.is_not(None)) | (Company.ats_slug.is_not(None)))
    if unscanned: q = q.where(Company.last_scan.is_(None))
    scan_ids(t, db, list(db.scalars(q)))


def scan_company(t, db):
    scan_ids(t, db, [int(t.payload["id"])])


def discover(t, db):
    logs = []
    def add(src, items):
        n = 0
        for name, site in items:
            if not name or re.fullmatch(r"Q\d+", name): continue
            if not db.scalar(select(Company.id).where(Company.name == name)): n += 1
            ing.add_company(db, name, website=site)
        db.commit(); logs.append(f"{src}: {len(items)} found, {n} new"); task_service.progress(db, t, log=logs)
    for n in seed.SEED + nl.TECH_COMPANIES: ing.add_company(db, n)
    for n, w, _k in clusters.all_companies(): ing.add_company(db, n, website=w)
    db.commit()
    for src, fn in (("European Tech Map", lambda: free_discovery.europeantechmap(lambda m: None)), ("OpenStreetMap (NL offices)", free_discovery.overpass_companies),
                    ("Wikipedia categories", free_discovery.wikipedia_categories), ("Wikidata", wikidata.fetch)):
        try: add(src, fn())
        except Exception as e: logs.append(f"{src}: failed ({e})"); task_service.progress(db, t, log=logs)
    try:
        items = free_discovery.overpass_cities(lambda m: task_service.progress(db, t, log=logs + [m]))
        for name, site, city, addr, kind in items: ing.add_company(db, name, website=site, city=city, address=addr, source="openstreetmap")
        db.commit(); logs.append(f"OpenStreetMap by city: {len(items)} found")
    except Exception as e: logs.append(f"OpenStreetMap by city failed ({e})")
    task_service.progress(db, t, log=logs)


def logos(t, db):
    ids = list(db.scalars(select(Company.id).where(Company.website.is_not(None), (Company.logo.is_(None)) | (Company.description.is_(None)))))
    task_service.progress(db, t, total=len(ids), done=0)
    def one(i):
        with SessionLocal() as d: ing.ensure_logo(d, d.get(Company, i)); d.commit()
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, ids))
    task_service.progress(db, t, done=len(ids))


def live_search(t, db, budget=90):
    """Real-time search: related companies first (sector lists, sponsor register, Wikipedia), then read their own career pages right now."""
    q = t.payload["q"]; t0 = time.time()
    task_service.progress(db, t, stage="finding companies", done=0, total=0, new_jobs=0)
    pri: list[int] = []
    cl = clusters.clusters_for(q)
    for k in cl[:4]:
        for e in clusters.C[k][1]:
            n, w = clusters.parse(e); pri.append(ing.add_company(db, n, website=w).id)
    from app.models import Sponsor
    words = [w for w in re.findall(r"[a-z0-9]{4,}", q.lower()) if w not in ("developer", "engineer", "senior", "junior", "intern", "internship", "software")]
    from app.crawler.text import norm
    for w in words[:3]:
        pri += list(db.scalars(select(Company.id).where(Company.name.ilike(f"%{w}%"))))
        for s in db.scalars(select(Sponsor).where(Sponsor.name_norm.like(f"%{norm(w)}%")).limit(25)): pri.append(ing.add_company(db, s.name, kvk=s.kvk).id)
    try:
        for name, site in free_discovery.wikipedia_search(q): pri.append(ing.add_company(db, name, website=site).id)
    except Exception: pass
    db.commit()
    import datetime as dt
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)
    rest = list(db.scalars(select(Company.id).order_by(Company.last_scan.asc().nullsfirst()).limit(2000)))
    order = list(dict.fromkeys(pri + rest))
    fresh = {i for i, ls in db.execute(select(Company.id, Company.last_scan)) if ls and ls > cut}
    todo = [i for i in order if i not in fresh][:400]
    task_service.progress(db, t, stage="reading company career sites", total=len(todo))
    state = {"done": 0, "new_jobs": 0}
    def one(cid):
        if time.time() - t0 > budget: return
        try: state["new_jobs"] += _scan_one(cid)
        except Exception: pass
        state["done"] += 1
    with ThreadPoolExecutor(8) as ex: list(ex.map(one, todo))
    task_service.progress(db, t, stage="done", **state)


def census(t, db, ats_list=None):
    """Discover companies through the ATS platforms they use (crt.sh hostnames -> public ATS API -> keep NL tech employers)."""
    from app.crawler import ats_census
    ats_list = ats_list or list(ats_census.DOMAINS)
    known = {(c.ats, c.ats_slug) for c in db.scalars(select(Company).where(Company.ats_slug.is_not(None)))}
    names = {n.lower() for n in db.scalars(select(Company.name))}
    work = []
    for ats in ats_list:
        slugs = set()
        for dom in ats_census.DOMAINS[ats]: slugs |= ats_census.crt_slugs(dom)
        fresh = [(ats, s) for s in sorted(slugs) if (ats, s) not in known and ats_census.pretty(s).lower() not in names]
        work += fresh
        task_service.progress(db, t, log=(t.progress or {}).get("log", []) + [f"{ats}: {len(slugs)} hostnames, {len(fresh)} unknown"])
    state = {"total": len(work), "done": 0, "kept": 0, "new_jobs": 0}
    task_service.progress(db, t, **state)
    def one(item):
        ats, slug = item
        try:
            jobs = discovery.ADAPTERS[ats](slug)
            if jobs:
                with SessionLocal() as d2:
                    name = ats_census.pretty(slug)
                    if ats == "recruitee":
                        d = discovery.get(f"https://{slug}.recruitee.com/api/offers/", True, False) or {}
                        cn = next((o.get("company_name") for o in d.get("offers", []) if o.get("company_name")), None)
                        if cn: name = cn.strip()
                    c = ing.add_company(d2, name, source=f"census:{ats}")
                    c.ats, c.ats_slug, c.resolved_via = ats, slug, "census"
                    n = ing.store_jobs(d2, c, jobs)
                    tech = d2.scalar(select(func.count()).select_from(Job).where(Job.company_id == c.id, Job.category == "tech"))
                    if not tech: d2.delete(c); d2.commit()
                    else:
                        c.last_scan = ing.now(); c.scan_note = f"census {ats} ({n} postings)"; c.next_scan = ing.now() + dt.timedelta(hours=12); d2.commit()
                        state["kept"] += 1; state["new_jobs"] += n
        except Exception as e: log.warning("census %s/%s: %s", ats, slug, e)
        state["done"] += 1
        if state["done"] % 25 == 0:
            with SessionLocal() as d3: task_service.progress(d3, d3.get(Task, t.id), **state)
    with ThreadPoolExecutor(12) as ex: list(ex.map(one, work))
    task_service.progress(db, t, **state)


def broad_sources(t, db):
    """Wider open-data sweep: Wikidata by IT-industry subtree, OSM by tech-sounding names nationwide."""
    from app.crawler import deep_discovery
    logs = []
    for src, fn in (("Wikidata IT-industry subtree", deep_discovery.wikidata_industry), ("OpenStreetMap tech names", deep_discovery.osm_names), ("Wikidata NL HQ by city", deep_discovery.wikidata_by_region), ("Wikipedia deep categories", deep_discovery.wikipedia_deep)):
        try:
            items = fn(); n = 0
            for name, site in items:
                if not name or re.fullmatch(r"Q\d+", name): continue
                if not db.scalar(select(Company.id).where(Company.name == name)): n += 1
                ing.add_company(db, name, website=site, source=src[:60])
            db.commit(); logs.append(f"{src}: {len(items)} found, {n} new")
        except Exception as e: logs.append(f"{src}: failed ({e})")
        task_service.progress(db, t, log=logs)


def internships(t, db):
    """Internship-focused sweep: read every company's student/stage/graduate pages (wide path list + werkenbij/careers/jobs subdomains)."""
    ids = list(db.execute(select(Company.id).where(Company.website.is_not(None), ~Company.ats.like("board:%") | Company.ats.is_(None))
                          .order_by(Company.id.in_(select(Job.company_id).where(Job.status == "open")).desc(), Company.id)).scalars())
    state = {"total": len(ids), "done": 0, "new_jobs": 0, "companies_with_new": 0}
    task_service.progress(db, t, **state)
    def one(cid):
        try:
            with SessionLocal() as d2:
                c = d2.get(Company, cid)
                have = set(d2.scalars(select(Job.url).where(Job.company_id == cid)))
                found = discovery.scan_student_pages(c.website, "", "", have)
                if found:
                    n = ing.store_jobs(d2, c, found, expire=False); d2.commit()
                    if n: state["new_jobs"] += n; state["companies_with_new"] += 1
        except Exception as e: log.warning("internships %s: %s", cid, e)
        state["done"] += 1
        if state["done"] % 20 == 0:
            with SessionLocal() as d3: task_service.progress(d3, d3.get(Task, t.id), **state)
    with ThreadPoolExecutor(10) as ex: list(ex.map(one, ids))
    task_service.progress(db, t, **state)


def mail_sync(t: Task, db):
    """Read one connected mailbox (read-only), classify the job e-mails and store the extracted facts. Runs with the owner's AI settings."""
    import uuid
    from app.core.secretbox import unseal
    from app.models import MailAccount, User, UserAiSettings
    from app.services import llm_service, mail_classifier
    p = t.payload or {}; uid = uuid.UUID(p["user_id"]); acc = db.get(MailAccount, p["account_id"])
    if not acc or acc.user_id != uid: raise RuntimeError("mailbox not found")
    s = db.get(UserAiSettings, uid); cfg = llm_service.Cfg(s.provider, s.model, s.base_url, unseal(s.api_key_enc)) if s else llm_service.Cfg()
    try:
        task_service.progress(db, t, phase="reading mailbox")
        days = int(p.get("days") or acc.days_back)
        from app.services import gmail_service
        mails = gmail_service.fetch(unseal(acc.secret_enc) or "", days=days)
        task_service.progress(db, t, phase="analysing", total=len(mails))
        stats = mail_classifier.process(db, uid, cfg, mails, account_id=acc.id, progress=lambda **k: task_service.progress(db, t, **k))
        import datetime as _dt
        acc.last_sync_at, acc.last_error = _dt.datetime.now(_dt.timezone.utc), None; db.commit()
        task_service.progress(db, t, phase="done", **stats)
    except Exception as e:
        db.rollback(); acc = db.get(MailAccount, p["account_id"])
        if acc: acc.last_error = str(e)[:300]; db.commit()
        raise
