import uuid, datetime as dt
from sqlalchemy import String, Text, Integer, Boolean, Float, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class UserAiSettings(Base):
    """Which AI (if any) a user lets analyse their job e-mails. The API key is stored encrypted and never sent back to the client."""
    __tablename__ = "user_ai_settings"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), default="rules")
    model: Mapped[str | None] = mapped_column(String(120))
    base_url: Mapped[str | None] = mapped_column(String(300))
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MailAccount(Base):
    """A Gmail account the user connected through Google OAuth (read-only). The refresh token is stored encrypted in secret_enc; host/port/folder are legacy columns."""
    __tablename__ = "mail_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(10), default="imap")     # always "gmail" now (IMAP was removed)
    label: Mapped[str] = mapped_column(String(80))
    host: Mapped[str] = mapped_column(String(200))
    port: Mapped[int] = mapped_column(Integer, default=993)
    username: Mapped[str] = mapped_column(String(200))
    secret_enc: Mapped[str | None] = mapped_column(Text)
    folder: Mapped[str] = mapped_column(String(100), default="INBOX")
    days_back: Mapped[int] = mapped_column(Integer, default=60)
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MailEvent(Base):
    """One job-related e-mail, reduced to what was extracted. The message body is NOT stored."""
    __tablename__ = "mail_events"
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_mail_user_msg"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("mail_accounts.id", ondelete="SET NULL"))
    message_id: Mapped[str] = mapped_column(String(300))
    sender: Mapped[str | None] = mapped_column(String(300))
    subject: Mapped[str | None] = mapped_column(String(400))
    received_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[str] = mapped_column(String(24), index=True)     # application_received | interview_invite | assessment | offer | rejection | recruiter_outreach
    company: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(250))
    location: Mapped[str | None] = mapped_column(String(200))
    event_date: Mapped[str | None] = mapped_column(String(80))        # interview / deadline date as written or ISO
    summary: Mapped[str | None] = mapped_column(String(400))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    classifier: Mapped[str] = mapped_column(String(60), default="rules")
    status: Mapped[str] = mapped_column(String(12), default="new", index=True)     # new | accepted | dismissed
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
