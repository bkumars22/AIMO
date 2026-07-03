"""
SQLAlchemy engine + session factory for AIMO.
ORM models mirror the Flyway SQL schema exactly.

Phase 1: define all ORM models matching V1–V5 migrations.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aimo:aimo_secret@localhost:5432/aimo")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── ORM Models (Phase 1) ──────────────────────────────────────
# from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, ARRAY
# from sqlalchemy.dialects.postgresql import UUID, JSONB
# from pgvector.sqlalchemy import Vector
# import uuid, datetime
#
# class Pipeline(Base):
#     __tablename__ = "pipelines"
#     id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     name         = Column(String(100), nullable=False, unique=True)
#     ...
