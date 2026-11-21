import re
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload
from app.crawler import scoring, thresholds, search as onto
from app.models import Job, User, UserJob
from app.schemas.job import JobOut, CompanyMini, SearchOut
from . import search_service as ss


def _salary(j: Job, profile: dict | None):
    if j.salary_min is None and j.salary_max is None: return None
    cat = (profile or {}).get("salary_category", "hsm_under30")
    return {"min": j.salary_min, "max": j.salary_max, "period": j.salary_period, "verdict": thresholds.verdict(j.salary_min, j.salary_max, j.salary_period, cat)}


def logo_url(v: str | None) -> str | None:
    """Stored as a bare filename or 'logos/x.png'; always expose an absolute path the API serves."""
    if not v: return None
    if v.startswith(('http://', 'https://', '/')): return v
    return '/logos/' + v.removeprefix('logos/')


def to_out(j: Job, user: User | None = None, stages: dict | None = None, relevance=None, matched=None, snippet=None, full=False) -> JobOut:
    p = user.profile if user else None
    fit = why = None
    if user and p and (p.get("skills") or p.get("titles") or p.get("cities")):
        fit, why = scoring.fit(j.title, j.description or "", j.location or "", j.job_type, j.language, p)
    c = j.company
    return JobOut(id=j.id, title=j.title, company=CompanyMini(id=c.id, name=c.name, logo=logo_url(c.logo), website=c.website, sponsor_status=c.sponsor_status, sponsor_match=c.sponsor_match),
                  location=j.location, city=j.city, url=j.url, job_type=j.job_type, category=j.category, domain=j.domain, language=j.language, remote=j.remote, salary=_salary(j, p),
                  posted_at=j.posted_at, first_seen=j.first_seen, status=j.status, skills=[s.skill for s in j.skills][:8], snippet=snippet if snippet is not None else (j.description or "")[:240],
                  relevance=relevance, matched=matched or [], fit=fit, fit_reason=why, stage=(stages or {}).get(j.id), description=(j.description if full else None))


def _snippets(db: Session, ids: list[int], q: str) -> dict[int, str]:
    pq = ss.parse_query(q); words = [w for g in onto.parse(pq["text"]) for w in g["strong"][:3]] + pq["phrases"]
    if not words or not ids: return {}
    tsq = " OR ".join(f'"{w}"' for w in dict.fromkeys(words) if w.strip())[:300]
    rows = db.execute(text("SELECT id, ts_headline('english', left(coalesce(description,''), 4000), websearch_to_tsquery('english', :q), 'MaxWords=32,MinWords=14,StartSel=<mark>,StopSel=</mark>,ShortWord=2') FROM jobs WHERE id = ANY(:ids)"), {"q": tsq, "ids": ids}).all()
    return {r[0]: r[1] for r in rows}


def search(db: Session, p: ss.SearchParams, user: User | None = None) -> SearchOut:
    res = ss.run(db, p)
    ids = res["ids"]
    if res["sort"] == "fit" and user:                    # personalised order: needs the candidate rows
        cand = db.scalars(select(Job).where(Job.id.in_(ids[:1500])).options(selectinload(Job.company))).all()
        fits = {j.id: scoring.fit(j.title, j.description or "", j.location or "", j.job_type, j.language, user.profile)[0] for j in cand}
        ids = sorted(ids[:1500], key=lambda i: -fits.get(i, 0)) + ids[1500:]
    total = len(ids)
    page_ids = ids[(p.page - 1) * p.limit: p.page * p.limit]
    jobs = {j.id: j for j in db.scalars(select(Job).where(Job.id.in_(page_ids)).options(selectinload(Job.company), selectinload(Job.skills)))}
    stages = {}
    if user and page_ids: stages = {r.job_id: r.stage for r in db.scalars(select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id.in_(page_ids)))}
    snips = _snippets(db, page_ids, p.q) if p.q.strip() and res["info"]["groups"] else {}
    items = [to_out(jobs[i], user, stages, res["relevance"].get(i), res["matched"].get(i), snips.get(i) or None) for i in page_ids if i in jobs]
    return SearchOut(items=items, total=total, page=p.page, limit=p.limit, facets=ss.facets(db, ids), query=res["info"], sort=res["sort"])
