"""Backfill/refresh embeddings for jobs that do not have one yet."""
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models import Job, Company
from app.services import embedding_service as emb


def backfill(batch: int = 64, limit: int | None = None) -> int:
    if not emb.available(): return 0
    done = 0
    while True:
        with SessionLocal() as db:
            rows = db.execute(select(Job, Company.name).join(Company).where(Job.embedding.is_(None)).order_by(Job.id).limit(batch)).all()
            if not rows: break
            vecs = emb.embed([emb.job_text(j.title, cname, j.location, j.description) for j, cname in rows])
            for (j, _), v in zip(rows, vecs): j.embedding = v
            db.commit(); done += len(rows)
        if limit and done >= limit: break
    return done


if __name__ == "__main__":
    print("embedded", backfill())
