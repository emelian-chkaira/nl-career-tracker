"""Housekeeping from the command line:  python -m app.cli <command> [--yes]

  seed               load the ready-made starter data (only into an empty database; --force to add anyway)
  export-seed        rewrite backend/seed/ from the current database (maintainers)
  stats              how much is stored
  backfill-domains   classify jobs that have no domain yet (--all: re-classify every job with the current rules)
  purge              delete long-expired / too-old jobs (see CAREERS_MAX_JOB_AGE_DAYS, CAREERS_DELETE_EXPIRED_AFTER_DAYS)
  prune              apply the storage policy (CAREERS_KEEP_DOMAINS, max age) to jobs already stored
  clear-jobs         delete ALL jobs                     (asks for confirmation, or pass --yes)
  clear-all          delete ALL jobs and companies       (asks for confirmation, or pass --yes)"""
import sys, json
from sqlalchemy import text
from app.core.db import SessionLocal
from app.services import maintenance_service as m


def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "").replace("-", "_")
    if cmd == "stats":
        with SessionLocal() as db:
            q = lambda s: db.execute(text(s)).scalar()
            print(json.dumps({"companies": q("select count(*) from companies"), "jobs_open": q("select count(*) from jobs where status='open'"), "jobs_expired": q("select count(*) from jobs where status='expired'"),
                              "by_domain": {r[0] or "unclassified": r[1] for r in db.execute(text("select domain, count(*) from jobs where status='open' group by 1 order by 2 desc"))}}, indent=2)); return 0
    if cmd in ("seed", "export_seed"):
        from app.services import seed_service as sd
        with SessionLocal() as db: print(json.dumps(sd.export(db) if cmd == "export_seed" else sd.load(db, force="--force" in argv)))
        return 0
    if cmd not in m.ACTIONS: print(__doc__); return 2
    if cmd in m.DESTRUCTIVE and "--yes" not in argv:
        if input(f"This runs '{cmd}' and cannot be undone. Type 'yes' to continue: ").strip().lower() != "yes": print("aborted"); return 1
    with SessionLocal() as db:
        if cmd == "backfill_domains" and "--all" in argv: print(json.dumps({"classified": m.backfill_domains(db, only_missing=False)}))
        else: print(json.dumps(m.ACTIONS[cmd](db)))
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
