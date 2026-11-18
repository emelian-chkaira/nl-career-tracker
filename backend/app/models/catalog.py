import datetime as dt
from sqlalchemy import String, Text, Integer, Float, Boolean, Date, DateTime, ForeignKey, Index, Computed, func, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.core.db import Base
from app.core.config import settings

_VEC = (
    "setweight(to_tsvector('english', coalesce(title,'')), 'A') || "
    "setweight(to_tsvector('english', coalesce(location,'')), 'C') || "
    "setweight(to_tsvector('english', left(coalesce(description,''), 20000)), 'D')"
)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text)
    ats: Mapped[str | None] = mapped_column(String(40))
    ats_slug: Mapped[str | None] = mapped_column(String(200))
    resolved_via: Mapped[str | None] = mapped_column(String(40))
    sponsor_status: Mapped[str] = mapped_column(String(16), default="unchecked")   # recognised | possible | not_listed | unchecked
    sponsor_match: Mapped[str | None] = mapped_column(String(255))
    kvk: Mapped[str | None] = mapped_column(String(16))
    logo: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(60))
    last_scan: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    next_scan: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    scan_note: Mapped[str | None] = mapped_column(Text)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    jobs: Mapped[list["Job"]] = relationship(back_populates="company", cascade="all, delete-orphan", passive_deletes=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80), index=True)         # normalised city (market dashboard)
    url: Mapped[str] = mapped_column(Text, unique=True)
    source: Mapped[str | None] = mapped_column(String(40), default="company-site")
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(16), default="other", index=True)   # tech | other
    job_type: Mapped[str] = mapped_column(String(16), default="job", index=True)     # internship | traineeship | junior | job | senior
    language: Mapped[str] = mapped_column(String(20), default="english_ok")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_period: Mapped[str | None] = mapped_column(String(10))
    posted_at: Mapped[dt.date | None] = mapped_column(Date)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)      # open | expired
    dedupe_key: Mapped[str | None] = mapped_column(String(32), index=True)
    search_vector = mapped_column(TSVECTOR, Computed(_VEC, persisted=True))
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    company: Mapped[Company] = relationship(back_populates="jobs")
    skills: Mapped[list["JobSkill"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_jobs_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_jobs_embedding", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_jobs_open_posted", "status", "posted_at"),
    )


class JobSkill(Base):
    """Skills detected in a posting (powers the 'skills in demand' dashboard and skill filters)."""
    __tablename__ = "job_skills"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    skill: Mapped[str] = mapped_column(String(60), primary_key=True, index=True)


class Sponsor(Base):
    """IND register of recognised sponsors."""
    __tablename__ = "sponsors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    name_norm: Mapped[str] = mapped_column(String(255), index=True)
    kvk: Mapped[str | None] = mapped_column(String(16), index=True)
    snapshot: Mapped[str | None] = mapped_column(String(20))


class KV(Base):
    __tablename__ = "kv"
    k: Mapped[str] = mapped_column(String(80), primary_key=True)
    v: Mapped[str | None] = mapped_column(Text)
