"""Job search on Postgres.

 keyword   : weighted full-text (title A > location C > description D) with ontology synonyms ("flutter" -> dart, mobile, ios, android…),
             phrase / exclusion / field operators, and trigram typo tolerance.
 semantic  : pgvector cosine similarity between the query embedding and each posting's embedding (local ONNX model).
 hybrid    : both, fused with Reciprocal Rank Fusion (default).

Query language (all optional, combinable with the structured filters):
    flutter developer          words are OR-ed with coverage scoring; generic words (developer, engineer…) count less
    "machine learning"         exact phrase (required)
    -java  or  -"sales"        exclude
    title:react company:adyen location:utrecht skill:docker      field operators
"""
import re, time, math
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.crawler import search as onto
from . import embedding_service

Sort = Literal["relevance", "newest", "oldest", "salary", "fit"]
Mode = Literal["hybrid", "keyword", "semantic"]


class SearchParams(BaseModel):
    q: str = ""
    mode: Mode = "hybrid"
    sort: Sort | None = None                       # default: relevance when q is given, else newest
    category: str | None = "tech"                   # tech | other | None(all)
    kind: Literal["job", "internship"] | None = None
    job_type: list[str] = []                        # internship | traineeship | junior | job | senior
    domain: list[str] = []                          # mobile | backend | frontend | fullstack | software | data | devops | security | qa | embedded | design | product | other
    language: list[str] = []                        # english_ok | dutch_plus | dutch_required
    city: list[str] = []
    location: str | None = None
    remote: bool | None = None
    sponsor: bool | None = None                     # only companies on the IND recognised-sponsor register (flag, not a default filter)
    skills: list[str] = []
    skills_mode: Literal["any", "all"] = "any"
    company_id: int | None = None
    min_salary: float | None = None                 # monthly gross EUR (yearly values are divided by 12)
    days: int | None = Field(None, ge=1, le=365)    # posted within the last N days
    status: str = "open"
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


FIELD_RE = re.compile(r'\b(title|company|location|skill):("[^"]+"|\S+)', re.I)
PHRASE_RE = re.compile(r'"([^"]+)"')
EXCL_RE = re.compile(r'(?:^|\s)-("[^"]+"|[\w][\w.+#-]*)')


def parse_query(q: str) -> dict:
    q = q or ""
    fields = [(m.group(1).lower(), m.group(2).strip('"')) for m in FIELD_RE.finditer(q)]
    q = FIELD_RE.sub(" ", q)
    excl = [e.strip('"') for e in EXCL_RE.findall(q)]
    q = EXCL_RE.sub(" ", q)
    phrases = PHRASE_RE.findall(q)
    q = PHRASE_RE.sub(" ", q)
    return {"text": re.sub(r"\s+", " ", q).strip(), "phrases": phrases, "excl": excl, "fields": fields}


def _filters(p: SearchParams) -> tuple[str, dict]:
    w, a = ["j.status = :status"], {"status": p.status}
    if p.category: w.append("j.category = :category"); a["category"] = p.category
    if p.kind == "internship": w.append("j.job_type IN ('internship','traineeship')")
    elif p.kind == "job": w.append("j.job_type NOT IN ('internship','traineeship')")
    if p.job_type: w.append("j.job_type = ANY(:job_types)"); a["job_types"] = p.job_type
    if p.domain: w.append("j.domain = ANY(:domains)"); a["domains"] = p.domain
    if p.language: w.append("j.language = ANY(:langs)"); a["langs"] = p.language
    if p.city: w.append("lower(j.city) = ANY(:cities)"); a["cities"] = [c.lower() for c in p.city]
    if p.location: w.append("j.location ILIKE :loc"); a["loc"] = f"%{p.location}%"
    if p.remote is not None: w.append("j.remote = :remote"); a["remote"] = p.remote
    if p.sponsor: w.append("c.sponsor_status IN ('recognised','possible')")
    if p.company_id: w.append("j.company_id = :cid"); a["cid"] = p.company_id
    if p.days: w.append("COALESCE(j.posted_at, j.first_seen::date) >= current_date - make_interval(days => :days)"); a["days"] = p.days
    if p.min_salary:
        w.append("(CASE WHEN j.salary_period='year' THEN j.salary_min/12 ELSE j.salary_min END) >= :minsal"); a["minsal"] = p.min_salary
    if p.skills:
        agg = "ALL" if p.skills_mode == "all" else "ANY"
        if p.skills_mode == "all":
            w.append("(SELECT count(*) FROM job_skills s WHERE s.job_id=j.id AND s.skill = ANY(:skills)) = :nskills"); a["nskills"] = len(set(s.lower() for s in p.skills))
        else:
            w.append("EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id=j.id AND s.skill = ANY(:skills))")
        a["skills"] = [s.lower() for s in p.skills]
    return " AND ".join(w), a


def _operator_sql(pq: dict) -> tuple[list[str], dict]:
    w, a = [], {}
    for i, ph in enumerate(pq["phrases"]): w.append(f"j.search_vector @@ phraseto_tsquery('english', :ph{i})"); a[f"ph{i}"] = ph
    for i, ex in enumerate(pq["excl"]): w.append(f"NOT (j.search_vector @@ phraseto_tsquery('english', :ex{i}))"); a[f"ex{i}"] = ex
    for i, (f, v) in enumerate(pq["fields"]):
        a[f"f{i}"] = f"%{v}%"
        if f == "title": w.append(f"j.title ILIKE :f{i}")
        elif f == "company": w.append(f"c.name ILIKE :f{i}")
        elif f == "location": w.append(f"(j.location ILIKE :f{i} OR j.city ILIKE :f{i})")
        elif f == "skill": w.append(f"EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id=j.id AND s.skill = lower(:fs{i}))"); a[f"fs{i}"] = v
    return w, a


def _or_tsq(terms: list[str], prefix: str, a: dict) -> str | None:
    parts = []
    for i, t in enumerate(dict.fromkeys(x for x in terms if x and len(x) > 1)):
        k = f"{prefix}{i}"; a[k] = t; parts.append(f"phraseto_tsquery('english', :{k})")
    return " || ".join(parts) if parts else None


BASE = "FROM jobs j JOIN companies c ON c.id = j.company_id"


def _keyword_candidates(db: Session, p: SearchParams, pq: dict, groups: list[dict], limit=800):
    where, args = _filters(p)
    ow, oa = _operator_sql(pq); args.update(oa)
    conds = list(ow)
    rank_expr, match = "0", None
    specific = [g for g in groups if not g["generic"]] or groups
    strong = [t for g in specific for t in g["strong"]]
    related = [t for g in specific for t in g["related"]]
    tsq_s = _or_tsq(strong, "s", args); tsq_r = _or_tsq(related, "r", args)
    if tsq_s or tsq_r:
        full = " || ".join(x for x in (tsq_s, tsq_r) if x)
        typo = []
        for i, g in enumerate(specific):
            if len(g["label"]) >= 5: args[f"ty{i}"] = g["label"]; typo.append(f":ty{i} <% j.title")
        conds.append("(j.search_vector @@ (" + full + ")" + ("".join(" OR " + t for t in typo)) + ")")
        rank_expr = f"ts_rank_cd(j.search_vector, {tsq_s}, 32) * 2" + (f" + ts_rank_cd(j.search_vector, {tsq_r}, 32) * 0.5" if tsq_r else "") if tsq_s else f"ts_rank_cd(j.search_vector, {tsq_r}, 32) * 0.5"
    if conds: where += " AND " + " AND ".join(conds)
    sql = f"SELECT j.id, j.title, c.name AS company, j.location, left(j.description, 4000) AS description, ({rank_expr}) AS kw {BASE} WHERE {where} ORDER BY kw DESC, j.posted_at DESC NULLS LAST LIMIT {limit}"
    return db.execute(text(sql), args).mappings().all()


def _semantic_candidates(db: Session, p: SearchParams, pq: dict, qtext: str, limit=150, min_sim=0.6):
    if not embedding_service.available() or not qtext.strip(): return []
    where, args = _filters(p)
    ow, oa = _operator_sql(pq); args.update(oa)
    if ow: where += " AND " + " AND ".join(ow)
    args["qv"] = str(embedding_service.embed_query(qtext))
    sql = f"SELECT j.id, 1 - (j.embedding <=> CAST(:qv AS vector)) AS sim {BASE} WHERE {where} AND j.embedding IS NOT NULL ORDER BY j.embedding <=> CAST(:qv AS vector) LIMIT {limit}"
    return [r for r in db.execute(text(sql), args).mappings().all() if r["sim"] >= min_sim]


def _browse_ids(db: Session, p: SearchParams, pq: dict, order: str, limit=5000):
    where, args = _filters(p)
    ow, oa = _operator_sql(pq); args.update(oa)
    if ow: where += " AND " + " AND ".join(ow)
    return db.execute(text(f"SELECT j.id {BASE} WHERE {where} ORDER BY {order} LIMIT {limit}"), args).scalars().all()


ORDERS = {"newest": "COALESCE(j.posted_at, j.first_seen::date) DESC, j.first_seen DESC, j.id DESC", "oldest": "COALESCE(j.posted_at, j.first_seen::date) ASC, j.id ASC",
          "salary": "(CASE WHEN j.salary_period='year' THEN j.salary_min/12 ELSE j.salary_min END) DESC NULLS LAST, j.id DESC"}


def run(db: Session, p: SearchParams) -> dict:
    """-> {ids (ordered, capped), relevance{id: 0-100}, matched{id: [why]}, info{...}}. Pagination/serialisation happen in jobs_service."""
    t0 = time.time()
    pq = parse_query(p.q)
    sort = p.sort or ("relevance" if p.q.strip() else "newest")
    qtext = pq["text"] or " ".join(pq["phrases"])
    groups = onto.parse(qtext) if qtext else []
    has_terms = bool(groups)
    info = {"groups": [g["label"] for g in groups], "mode": p.mode, "semantic": False, "operators": {"phrases": pq["phrases"], "exclude": pq["excl"], "fields": pq["fields"]}}
    relevance, matched = {}, {}
    if not has_terms:                                    # browse / operator-only
        order = ORDERS.get(sort if sort in ORDERS else "newest")
        ids = _browse_ids(db, p, pq, order)
        info["took_ms"] = round((time.time() - t0) * 1000)
        return {"ids": list(ids), "relevance": relevance, "matched": matched, "info": info, "sort": sort}

    kw_scores: dict[int, float] = {}
    if p.mode in ("hybrid", "keyword"):
        for r in _keyword_candidates(db, p, pq, groups):
            s, why = onto.score(groups, r["title"] or "", r["company"] or "", r["location"] or "", r["description"] or "")
            if s >= 25: kw_scores[r["id"]] = s + float(r["kw"] or 0); relevance[r["id"]] = s; matched[r["id"]] = why
    sem_sim: dict[int, float] = {}
    if p.mode in ("hybrid", "semantic"):
        sem = _semantic_candidates(db, p, pq, qtext)
        info["semantic"] = bool(sem) or embedding_service.available()
        sem_sim = {r["id"]: float(r["sim"]) for r in sem}
        for i, sim in sem_sim.items():
            if i not in relevance:                       # found only by meaning, not by words
                relevance[i] = round(min(100, max(0, (sim - 0.5) / 0.4 * 100))); matched[i] = ["similar meaning"]
            elif relevance[i] < 100: relevance[i] = min(100, relevance[i] + 8)
    k = 60
    kw_rank = {i: n for n, i in enumerate(sorted(kw_scores, key=lambda x: -kw_scores[x]))}
    sem_rank = {i: n for n, i in enumerate(sorted(sem_sim, key=lambda x: -sem_sim[x]))}
    fused = {i: (1 / (k + kw_rank[i]) if i in kw_rank else 0) + (1 / (k + sem_rank[i]) if i in sem_rank else 0) for i in set(kw_rank) | set(sem_rank)}
    ids = sorted(fused, key=lambda i: -fused[i])
    if sort in ORDERS and ids:                           # explicit date/salary order among the matches
        ordered = db.execute(text(f"SELECT j.id FROM jobs j WHERE j.id = ANY(:ids) ORDER BY {ORDERS[sort]}"), {"ids": ids}).scalars().all()
        ids = list(ordered)
    info["took_ms"] = round((time.time() - t0) * 1000)
    return {"ids": ids, "relevance": relevance, "matched": matched, "info": info, "sort": sort}


def facets(db: Session, ids: list[int]) -> dict:
    if not ids: return {k: [] for k in ("category", "job_type", "domain", "city", "language", "skills", "companies", "sponsor", "remote")}
    a = {"ids": ids[:5000]}
    g = lambda col: [dict(value=r[0], count=r[1]) for r in db.execute(text(f"SELECT {col}, count(*) n FROM jobs j WHERE j.id = ANY(:ids) AND {col} IS NOT NULL GROUP BY {col} ORDER BY n DESC LIMIT 15"), a).all()]
    return {
        "category": g("j.category"), "job_type": g("j.job_type"), "domain": g("j.domain"), "city": g("j.city"), "language": g("j.language"),
        "skills": [dict(value=r[0], count=r[1]) for r in db.execute(text("SELECT s.skill, count(*) n FROM job_skills s WHERE s.job_id = ANY(:ids) GROUP BY s.skill ORDER BY n DESC LIMIT 20"), a).all()],
        "companies": [dict(id=r[0], value=r[1], count=r[2]) for r in db.execute(text("SELECT c.id, c.name, count(*) n FROM jobs j JOIN companies c ON c.id=j.company_id WHERE j.id = ANY(:ids) GROUP BY c.id, c.name ORDER BY n DESC LIMIT 10"), a).all()],
        "sponsor": db.execute(text("SELECT count(*) FROM jobs j JOIN companies c ON c.id=j.company_id WHERE j.id = ANY(:ids) AND c.sponsor_status IN ('recognised','possible')"), a).scalar(),
        "remote": db.execute(text("SELECT count(*) FROM jobs j WHERE j.id = ANY(:ids) AND j.remote"), a).scalar(),
    }
