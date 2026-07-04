"""
SQLAlchemy engine + session factory for AIMO.
ORM models mirror the Flyway SQL schema exactly (V1, V2, V3, V7 —
V5's pgvector tables are owned by storage/vector_store.py).
"""
import os
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY, Boolean, DateTime, DECIMAL, ForeignKey, Integer, String, Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aimo:aimo_secret@localhost:5432/aimo")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI dependency — yields a DB session and closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    pass


# ── ORM Models ────────────────────────────────────────────────────────────────

class Pipeline(Base):
    __tablename__ = "pipelines"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:          Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description:   Mapped[str | None] = mapped_column(Text)
    node_count:    Mapped[int | None] = mapped_column(Integer)
    environment:   Mapped[str] = mapped_column(String(20), nullable=False, default="production")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # V7 additions
    health_score:  Mapped[int] = mapped_column(Integer, default=100)
    api_key_hash:  Mapped[str | None] = mapped_column(String(64))
    owner_email:   Mapped[str | None] = mapped_column(String(255))
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id:              Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=False)
    external_run_id: Mapped[str | None] = mapped_column(String(200))
    status:          Mapped[str] = mapped_column(String(20), nullable=False)
    total_cost_usd:  Mapped[float | None] = mapped_column(DECIMAL(10, 6))
    total_tokens:    Mapped[int | None] = mapped_column(Integer)
    latency_ms:      Mapped[int | None] = mapped_column(Integer)
    node_count:      Mapped[int | None] = mapped_column(Integer)
    model_ids:       Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    input_hash:      Mapped[str | None] = mapped_column(String(64))
    error:           Mapped[str | None] = mapped_column(Text)
    started_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # V7 additions
    cost_usd:            Mapped[float | None] = mapped_column(DECIMAL(10, 6))
    faithfulness_score:  Mapped[float | None] = mapped_column(DECIMAL(5, 4))

    spans: Mapped[list["PipelineSpan"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class PipelineSpan(Base):
    __tablename__ = "pipeline_spans"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    node_name:         Mapped[str] = mapped_column(String(100), nullable=False)
    model_id:          Mapped[str | None] = mapped_column(String(100))
    prompt_tokens:     Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd:          Mapped[float] = mapped_column(DECIMAL(10, 6), nullable=False, default=0)
    latency_ms:        Mapped[int | None] = mapped_column(Integer)
    status:            Mapped[str | None] = mapped_column(String(20))
    error:             Mapped[str | None] = mapped_column(Text)
    input_preview:     Mapped[str | None] = mapped_column(Text)
    output_preview:    Mapped[str | None] = mapped_column(Text)
    context_used:      Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped["PipelineRun"] = relationship(back_populates="spans")


class Incident(Base):
    __tablename__ = "incidents"

    id:              Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=False)
    run_id:          Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"))
    incident_type:   Mapped[str] = mapped_column(String(50), nullable=False)
    severity:        Mapped[str] = mapped_column(String(5), nullable=False)
    status:          Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    title:           Mapped[str] = mapped_column(Text, nullable=False)
    description:     Mapped[str | None] = mapped_column(Text)
    score:           Mapped[float | None] = mapped_column(DECIMAL(8, 4))
    threshold:       Mapped[float | None] = mapped_column(DECIMAL(8, 4))
    root_cause:      Mapped[str | None] = mapped_column(Text)
    detected_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(200))

    evidence: Mapped[list["IncidentEvidence"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content:       Mapped[str | None] = mapped_column(Text)
    meta:          Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    incident: Mapped["Incident"] = relationship(back_populates="evidence")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id:              Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(20))
    total_cases:     Mapped[int] = mapped_column(Integer, nullable=False)
    auto_scored:     Mapped[int] = mapped_column(Integer, nullable=False)
    passed:          Mapped[int] = mapped_column(Integer, nullable=False)
    failed:          Mapped[int] = mapped_column(Integer, nullable=False)
    compliance_pct:  Mapped[float] = mapped_column(DECIMAL(5, 2), nullable=False)
    trigger:         Mapped[str | None] = mapped_column(String(30))
    run_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class InjectionAttempt(Base):
    __tablename__ = "injection_attempts"

    id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=False)
    run_id:           Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"))
    user_id:          Mapped[str | None] = mapped_column(String(200))
    input_text:       Mapped[str] = mapped_column(Text, nullable=False)
    injection_type:   Mapped[str | None] = mapped_column(String(50))
    matched_patterns: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    similarity_score: Mapped[float | None] = mapped_column(DECIMAL(5, 4))
    blocked:          Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    incident_id:      Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"))
    detected_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
