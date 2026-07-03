"""
Query layer for AIMO storage.
All DB access goes through here — no raw SQL in business logic.

Phase 1: implement each method using SQLAlchemy ORM + SessionLocal.
"""
from __future__ import annotations
from typing import Any


def save_span(span_data: dict) -> str:
    """Insert pipeline_spans row. Returns db_span_id (UUID)."""
    raise NotImplementedError("Phase 1")


def save_run(run_data: dict) -> str:
    """Upsert pipeline_runs row. Returns db_run_id (UUID)."""
    raise NotImplementedError("Phase 1")


def get_cost_history(pipeline_id: str, node_name: str, days: int = 7) -> list[float]:
    """Return cost_usd values for (pipeline_id, node_name) over last N days."""
    raise NotImplementedError("Phase 1")


def get_latency_history(pipeline_id: str, node_name: str, days: int = 7) -> list[int]:
    """Return latency_ms values for (pipeline_id, node_name) over last N days."""
    raise NotImplementedError("Phase 1")


def get_recent_compliance_scores(pipeline_id: str, limit: int = 20) -> list[float]:
    """Return last N compliance_pct values for a pipeline (from eval_runs)."""
    raise NotImplementedError("Phase 1")


def save_incident(incident_data: dict) -> str:
    """Insert incidents row. Returns incident_id (UUID)."""
    raise NotImplementedError("Phase 1")


def save_injection_attempt(attempt_data: dict) -> str:
    """Insert injection_attempts row. Returns attempt_id (UUID)."""
    raise NotImplementedError("Phase 1")


def get_injection_count(user_id: str, pipeline_id: str, window_minutes: int = 60) -> int:
    """Count injection attempts from user_id in last N minutes."""
    raise NotImplementedError("Phase 1")


def list_incidents(
    pipeline_id: str | None = None,
    incident_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List incidents with optional filters."""
    raise NotImplementedError("Phase 1")


def get_incident(incident_id: str) -> dict | None:
    """Get single incident with evidence."""
    raise NotImplementedError("Phase 1")


def acknowledge_incident(incident_id: str, acknowledged_by: str) -> None:
    raise NotImplementedError("Phase 1")


def resolve_incident(incident_id: str, resolved_by: str, root_cause: str | None) -> None:
    raise NotImplementedError("Phase 1")
