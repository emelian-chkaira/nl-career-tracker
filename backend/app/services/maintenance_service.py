"""Database housekeeping: retention purge, applying the storage policy to existing rows, domain backfill, and clearing data.

Every action has a PREVIEW (how many rows it would touch) and returns counts. Jobs that someone saved to a pipeline (user_jobs) are never removed by purge/prune."""
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.crawler import domains
from . import policy_service

SAVED = "NOT EXISTS (SELECT 1 FROM user_jobs u WHERE u.job_id = jobs.id)"


def _count(db: Session, sql: str, **a) -> int: return db.execute(text(f"SELECT count(*) FROM jobs WHERE {sql}"), a).scalar() or 0
def _del(db: Session, sql: str, **a) -> int: return db.execute(text(f"DELETE FROM jobs WHERE {sql}"), a).rowcount


def _purge_clauses(p: dict) -> dict[str, tuple[str, dict]]:
    out = {}
    if p["delete_expired_after_days"]: out["expired_deleted"] = (f"status = 'expired' AND last_seen < now() - make_interval(days => :d) AND {SAVED}", {"d": p["delete_expired_after_days"]})
    if p["max_job_age_days"]: out["too_old_deleted"] = (f"COALESCE(posted_at, first_seen::date) < current_date - :d AND {SAVED}", {"d": p["max_job_age_days"]})
    return out


def _prune_clause(p: dict) -> tuple[str, dict] | None:
    if not p["keep_domains"]: return None
    return (f"domain IS NOT NULL AND domain <> ALL(:k) AND {SAVED}", {"k": p["keep_domains"]})


def backfill_domains(db: Session, only_missing: bool = True) -> int:
    """Classify jobs that have no domain yet (or all of them) with the current rules."""
    q = "SELECT j.id, j.title, left(j.description, 3000), coalesce(string_agg(s.skill, ','), '') FROM jobs j LEFT JOIN job_skills s ON s.job_id = j.id " \
        + ("WHERE j.domain IS NULL " if only_missing else "") + "GROUP BY j.id"
    done = 0
    for jid, title, desc, sk in db.execute(text(q)).all():
        db.execute(text("UPDATE jobs SET domain = :d WHERE id = :i"), {"d": domains.classify(title, desc or "", sk.split(",") if sk else []), "i": jid}); done += 1
    db.commit(); return done


def purge_old(db: Session) -> dict:
    """Retention: delete long-expired jobs and jobs older than the age limit (never saved/pipeline jobs)."""
    out = {"expired_deleted": 0, "too_old_deleted": 0}
    for k, (sql, a) in _purge_clauses(policy_service.current()).items(): out[k] = _del(db, sql, **a)
    db.commit(); return out


def prune_to_policy(db: Session) -> dict:
    """Apply the CURRENT storage policy to jobs already stored: drop domains you no longer keep, plus everything purge_old removes."""
    backfill_domains(db)
    out = {"other_domains_deleted": 0}
    c = _prune_clause(policy_service.current())
    if c: out["other_domains_deleted"] = _del(db, c[0], **c[1])
    db.commit(); out.update(purge_old(db)); return out


def clear_jobs(db: Session) -> dict:
    """Delete ALL jobs (also removes users' pipeline entries for them). Companies, users and settings stay."""
    n = _del(db, "TRUE"); db.commit(); return {"jobs_deleted": n}


def clear_all(db: Session) -> dict:
    """Delete all jobs AND all companies. Users, accounts, saved searches and alerts stay."""
    j = _del(db, "TRUE"); c = db.execute(text("DELETE FROM companies")).rowcount; db.commit(); return {"jobs_deleted": j, "companies_deleted": c}


def preview(db: Session, action: str) -> dict:
    """What the action WOULD do right now, without changing anything."""
    p = policy_service.current()
    if action == "backfill_domains": return {"jobs_to_classify": _count(db, "domain IS NULL")}
    if action == "purge": return {k.replace("_deleted", "_to_delete"): _count(db, sql, **a) for k, (sql, a) in _purge_clauses(p).items()} or {"nothing_to_do": 0}
    if action == "prune":
        out = {}
        c = _prune_clause(p)
        if c: out["other_domains_to_delete"] = _count(db, c[0], **c[1])
        out.update({k.replace("_deleted", "_to_delete"): _count(db, sql, **a) for k, (sql, a) in _purge_clauses(p).items()})
        return out or {"nothing_to_do": 0}
    if action == "clear_jobs": return {"jobs_to_delete": _count(db, "TRUE"), "pipeline_entries_lost": db.execute(text("SELECT count(*) FROM user_jobs")).scalar() or 0}
    if action == "clear_all": return {"jobs_to_delete": _count(db, "TRUE"), "companies_to_delete": db.execute(text("SELECT count(*) FROM companies")).scalar() or 0,
                                      "pipeline_entries_lost": db.execute(text("SELECT count(*) FROM user_jobs")).scalar() or 0}
    raise KeyError(action)


ACTIONS = {"backfill_domains": lambda db: {"classified": backfill_domains(db)}, "purge": purge_old, "prune": prune_to_policy, "clear_jobs": clear_jobs, "clear_all": clear_all}
DESTRUCTIVE = {"clear_jobs", "clear_all"}
