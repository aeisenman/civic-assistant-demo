"""SQLAlchemy 2.0 mapped classes, one per table in migrations/001_init.sql.

Used by the seed loader, the RAG store, the workflow engine and the API routers.
Depends on: pgvector.sqlalchemy for the embedding column; the schema itself is
created by the SQL migrations, not by metadata.create_all (single source of truth).
"""

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


class Document(Base):
    """An uploaded file: bytes live in SeaweedFS, extracted text lives here."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    s3_key: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    # The conversation this upload arrived in (M20). NULL on every row uploaded
    # before that, and on any caller that does not send one; the column exists so
    # an upload can claim a session id the way a chat message does.
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    """A permit / business tax / service request moving through the workflow."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tracking_number: Mapped[str] = mapped_column(Text, unique=True)
    type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="draft")
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    missing_fields: Mapped[list] = mapped_column(JSONB, default=list)
    # Non-blocking validator notes (unconfirmed address, late business start).
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resident_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    certificate_s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # M26a: the caller's Idempotency-Key, under a unique partial index
    # (009_runtime.sql). NULL on every row filed without one, which is why the
    # index is partial — NULLs would otherwise all collide under a plain UNIQUE
    # in some engines, and here they simply do not participate.
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationEvent(Base):
    """Audit row written by the workflow engine on every transition."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("applications.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrashZone(Base):
    """Collection zone. Recycling alternates on odd (A) / even (B) ISO weeks;
    `organics_week` is legacy since M6 — organics are collected weekly with trash.
    `zips` (M8) is the ZIP -> zone fallback used when an address geocodes to a real
    San Diego ZIP that no seed row covers; that mapping is fictional."""

    __tablename__ = "trash_zones"

    zone_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    trash_day: Mapped[str] = mapped_column(Text)
    recycling_week: Mapped[str | None] = mapped_column(Text, nullable=True)
    organics_week: Mapped[str | None] = mapped_column(Text, nullable=True)
    zips: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Address(Base):
    """Fake address -> trash zone + council district lookup."""

    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    address: Mapped[str] = mapped_column(Text)
    zip: Mapped[str | None] = mapped_column(Text, nullable=True)
    zone_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    council_district: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Event(Base):
    """A city event returned by the search_events tool."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)


class PermitType(Base):
    """Permit catalogue plus the inputs to the fee estimate."""

    __tablename__ = "permit_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_1000_valuation_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    typical_turnaround_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_plans_over_valuation_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ServiceCategory(Base):
    """311 category -> owning department and SLA."""

    __tablename__ = "service_categories"

    category: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Referral(Base):
    """Where to send a resident when the city is not the right agency."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    agency: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CouncilDistrict(Base):
    """District number -> councilmember and neighborhoods."""

    __tablename__ = "council_districts"

    district: Mapped[int] = mapped_column(Integer, primary_key=True)
    councilmember: Mapped[str | None] = mapped_column(Text, nullable=True)
    neighborhoods: Mapped[list] = mapped_column(JSONB, default=list)


class KbDocument(Base):
    """One markdown file from api/kb/, ingested at startup."""

    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # M19: the kb/*.md file this row came from and the sha256 of its bytes, so a
    # re-ingest can tell "already done" from "changed" per document (probe A20).
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbChunk(Base):
    """A retrievable passage: dense vector + tsvector for hybrid search."""

    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kb_documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Width follows EMBED_DIM, same value the migration substitutes.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embed_dim), nullable=True)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)


class Trace(Base):
    """One assistant turn, with everything needed to explain it."""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list)
    # M19: how many model rounds the tool loop spent. 4 (MAX_TOOL_ROUNDS) means the
    # turn ran out of budget with the model still asking for tools — the signature
    # of a loop, and the one thing tool_calls alone cannot show.
    tool_rounds: Mapped[int] = mapped_column(Integer, default=0)
    # Per-model-call breakdown from TraceCollector, and the documents the turn saw.
    calls: Mapped[list] = mapped_column(JSONB, default=list)
    document_ids: Mapped[list] = mapped_column(JSONB, default=list)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffUser(Base):
    """A back-office account (M11). One row in the demo, upserted from .env."""

    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    # "scrypt$n$r$p$salt$key" — see app/auth.py; the salt is inside the string.
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffSession(Base):
    """One signed-in browser. The primary key is the sha256 of the cookie value,
    so the table never holds anything that could be replayed as a session."""

    __tablename__ = "staff_sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff_users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """Conversation history, keyed by the browser-generated session id."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("traces.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
