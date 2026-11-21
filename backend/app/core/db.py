from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings

engine = create_engine(settings.database_url, pool_size=settings.db_pool_size, max_overflow=20, pool_pre_ping=True, future=True)


@event.listens_for(engine, "connect")
def _tune(dbapi_conn, _):
    with dbapi_conn.cursor() as cur: cur.execute("SET pg_trgm.word_similarity_threshold = 0.6")   # typo tolerance for the `<%` operator
    dbapi_conn.commit()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase): pass


def get_db():
    """FastAPI dependency: one session per request."""
    with SessionLocal() as s:
        yield s


@contextmanager
def session_scope():
    """For workers / scripts: commit on success, roll back on error."""
    with SessionLocal() as s:
        try:
            yield s; s.commit()
        except Exception:
            s.rollback(); raise
