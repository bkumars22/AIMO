"""
Query layer for AIMO storage. All DB access goes through here — no raw SQL
in business logic (agents/monitoring_agent.py, main.py).

`pipeline_id` accepted by these functions is whatever the caller has on hand —
either the DB UUID (returned by create_pipeline / /pipelines/register) or the
pipeline's friendly name (e.g. "ARIA", "QAIP" — what the SDK ships in spans/
runs before a pipeline has ever been explicitly registered). Ingestion paths
(save_span, save_run, save_incident, update_pipeline_health) auto-create the
pipeline row on first sight; read paths (get_pipeline, list_incidents, ...)
only resolve existing pipelines and return None/[] when there's no match.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from storage.database import (
    Incident,
    IncidentEvidence,
    InjectionAttempt,
    Pipeline,
    PipelineRun,
    PipelineSpan,
    EvalRun,
    SessionLocal,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _find_pipeline(session, pipeline_id: str) -> Pipeline | None:
    """Look up a pipeline by DB UUID or by name. Never creates one."""
    as_uuid = _as_uuid(pipeline_id)
    if as_uuid is not None:
        pipeline = session.get(Pipeline, as_uuid)
        if pipeline is not None:
            return pipeline
    return session.scalar(select(Pipeline).where(Pipeline.name == str(pipeline_id)))


def _get_or_create_pipeline(session, pipeline_id: str) -> Pipeline:
    """Look up a pipeline by DB UUID or name; auto-create by name if absent."""
    pipeline = _find_pipeline(session, pipeline_id)
    if pipeline is not None:
        return pipeline
    pipeline = Pipeline(name=str(pipeline_id))
    session.add(pipeline)
    session.flush()
    return pipeline


def _find_run(session, pipeline: Pipeline, external_run_id: str | None) -> PipelineRun | None:
    if not external_run_id:
        return None
    return session.scalar(
        select(PipelineRun)
        .where(PipelineRun.pipeline_id == pipeline.id)
        .where(PipelineRun.external_run_id == str(external_run_id))
        .order_by(PipelineRun.started_at.desc())
    )


def _pipeline_to_dict(p: Pipeline) -> dict:
    return {
        "id":            str(p.id),
        "name":          p.name,
        "description":   p.description,
        "node_count":    p.node_count,
        "environment":   p.environment,
        "is_active":     p.is_active,
        "health_score":  p.health_score,
        "owner_email":   p.owner_email,
        "registered_at": p.registered_at.isoformat() if p.registered_at else None,
        "last_seen_at":  p.last_seen_at.isoformat() if p.last_seen_at else None,
    }


def _incident_to_dict(inc: Incident, include_evidence: bool = True) -> dict:
    data = {
        "id":              str(inc.id),
        "pipeline_id":     str(inc.pipeline_id),
        "run_id":          str(inc.run_id) if inc.run_id else None,
        "incident_type":   inc.incident_type,
        "severity":        inc.severity,
        "status":          inc.status,
        "title":           inc.title,
        "description":     inc.description,
        "score":           float(inc.score) if inc.score is not None else None,
        "threshold":       float(inc.threshold) if inc.threshold is not None else None,
        "root_cause":      inc.root_cause,
        "detected_at":     inc.detected_at.isoformat() if inc.detected_at else None,
        "acknowledged_at": inc.acknowledged_at.isoformat() if inc.acknowledged_at else None,
        "resolved_at":     inc.resolved_at.isoformat() if inc.resolved_at else None,
        "acknowledged_by": inc.acknowledged_by,
    }
    if include_evidence:
        data["evidence"] = [
            {"type": e.evidence_type, "content": e.content, "metadata": e.meta}
            for e in inc.evidence
        ]
    return data


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Pipelines ─────────────────────────────────────────────────────────────────

def create_pipeline(
    name: str,
    description: str | None = None,
    owner_email: str | None = None,
    api_key_hash: str | None = None,
) -> str:
    """Insert a pipelines row. Idempotent by name — returns the existing
    pipeline's id if one is already registered under this name."""
    with SessionLocal() as session:
        existing = session.scalar(select(Pipeline).where(Pipeline.name == name))
        if existing is not None:
            return str(existing.id)

        pipeline = Pipeline(
            name=name,
            description=description,
            owner_email=owner_email,
            api_key_hash=api_key_hash,
        )
        session.add(pipeline)
        session.commit()
        return str(pipeline.id)


def get_pipeline(pipeline_id: str) -> dict | None:
    """Read-only lookup by DB UUID or name."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        return _pipeline_to_dict(pipeline) if pipeline is not None else None


def get_pipeline_health_score(pipeline_id: str) -> int:
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        return pipeline.health_score if pipeline is not None else 100


def update_pipeline_health(pipeline_id: str, health_score: int) -> None:
    with SessionLocal() as session:
        pipeline = _get_or_create_pipeline(session, pipeline_id)
        pipeline.health_score = max(0, min(100, int(health_score)))
        pipeline.last_seen_at = _utcnow()
        pipeline.updated_at = _utcnow()
        session.commit()


# ── Spans / Runs ──────────────────────────────────────────────────────────────

def save_span(span_data: dict) -> str:
    """Insert a pipeline_spans row. Auto-creates the pipeline and/or the
    parent run if this is the first span seen for either. Returns the new
    span's db id (UUID string)."""
    with SessionLocal() as session:
        pipeline = _get_or_create_pipeline(session, span_data["pipeline_id"])
        pipeline.last_seen_at = _utcnow()

        run = _find_run(session, pipeline, span_data.get("run_id"))
        if run is None:
            run = PipelineRun(
                pipeline_id=pipeline.id,
                external_run_id=span_data.get("run_id"),
                status="running",
                started_at=span_data.get("timestamp") or _utcnow(),
            )
            session.add(run)
            session.flush()

        input_text = span_data.get("input_text") or ""
        output_text = span_data.get("output_text") or ""

        span = PipelineSpan(
            run_id=run.id,
            node_name=span_data["node_name"],
            model_id=span_data.get("model_id"),
            prompt_tokens=span_data.get("prompt_tokens", 0),
            completion_tokens=span_data.get("completion_tokens", 0),
            cost_usd=span_data.get("cost_usd", 0.0),
            latency_ms=span_data.get("latency_ms"),
            status="error" if span_data.get("error") else "ok",
            error=span_data.get("error"),
            input_preview=input_text[:500],
            output_preview=output_text[:500],
            context_used=bool(span_data.get("context")),
            started_at=span_data.get("timestamp") or _utcnow(),
        )
        session.add(span)
        session.commit()
        return str(span.id)


def save_run(run_data: dict) -> str:
    """Upsert a pipeline_runs row keyed by (pipeline, external_run_id).
    Returns the db run id (UUID string)."""
    with SessionLocal() as session:
        pipeline = _get_or_create_pipeline(session, run_data["pipeline_id"])
        pipeline.last_seen_at = _utcnow()

        run = _find_run(session, pipeline, run_data.get("run_id"))
        if run is None:
            run = PipelineRun(pipeline_id=pipeline.id, external_run_id=run_data.get("run_id"))
            session.add(run)

        run.status         = run_data.get("status", run.status or "completed")
        run.total_cost_usd = run_data.get("total_cost_usd")
        run.cost_usd       = run_data.get("total_cost_usd")
        run.total_tokens   = run_data.get("total_tokens")
        run.latency_ms     = run_data.get("latency_ms")
        run.node_count     = run_data.get("node_count")
        run.model_ids      = run_data.get("model_ids") or []
        run.error          = run_data.get("error")
        run.started_at     = run_data.get("started_at") or run.started_at or _utcnow()
        run.completed_at   = run_data.get("completed_at")
        if run_data.get("faithfulness_score") is not None:
            run.faithfulness_score = run_data["faithfulness_score"]

        session.commit()
        return str(run.id)


def _run_window(session, pipeline: Pipeline, days: int) -> list[PipelineRun]:
    since = _utcnow() - timedelta(days=days)
    return list(
        session.scalars(
            select(PipelineRun)
            .where(PipelineRun.pipeline_id == pipeline.id)
            .where(PipelineRun.started_at >= since)
            .order_by(PipelineRun.started_at.asc())
        )
    )


def get_cost_history(pipeline_id: str, node_name: str, days: int = 7) -> list[float]:
    """cost_usd values for (pipeline_id, node_name) over the last N days,
    oldest first."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return []
        since = _utcnow() - timedelta(days=days)
        rows = session.scalars(
            select(PipelineSpan.cost_usd)
            .join(PipelineRun, PipelineSpan.run_id == PipelineRun.id)
            .where(PipelineRun.pipeline_id == pipeline.id)
            .where(PipelineSpan.node_name == node_name)
            .where(PipelineSpan.started_at >= since)
            .order_by(PipelineSpan.started_at.asc())
        )
        return [float(v) for v in rows]


def get_latency_history(pipeline_id: str, node_name: str, days: int = 7) -> list[int]:
    """latency_ms values for (pipeline_id, node_name) over the last N days,
    oldest first."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return []
        since = _utcnow() - timedelta(days=days)
        rows = session.scalars(
            select(PipelineSpan.latency_ms)
            .join(PipelineRun, PipelineSpan.run_id == PipelineRun.id)
            .where(PipelineRun.pipeline_id == pipeline.id)
            .where(PipelineSpan.node_name == node_name)
            .where(PipelineSpan.started_at >= since)
            .where(PipelineSpan.latency_ms.is_not(None))
            .order_by(PipelineSpan.started_at.asc())
        )
        return [int(v) for v in rows]


def get_recent_compliance_scores(pipeline_id: str, limit: int = 20) -> list[float]:
    """Last N compliance_pct values for a pipeline (from eval_runs), oldest
    first."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return []
        rows = session.scalars(
            select(EvalRun.compliance_pct)
            .where(EvalRun.pipeline_id == pipeline.id)
            .order_by(EvalRun.run_at.desc())
            .limit(limit)
        )
        return [float(v) for v in rows][::-1]


def get_recent_runs(pipeline_id: str, limit: int = 50) -> list[dict]:
    """Runs shaped for detectors.anomaly_detector (BaselineCalculator etc):
    cost_usd, latency_ms, prompt_tokens, completion_tokens,
    faithfulness_score, nodes[]. Oldest first."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return []
        runs = list(
            session.scalars(
                select(PipelineRun)
                .where(PipelineRun.pipeline_id == pipeline.id)
                .order_by(PipelineRun.started_at.desc())
                .limit(limit)
            )
        )
        runs.reverse()

        out: list[dict] = []
        for run in runs:
            nodes = [
                {
                    "name":              s.node_name,
                    "cost_usd":          float(s.cost_usd or 0.0),
                    "latency_ms":        s.latency_ms or 0,
                    "prompt_tokens":     s.prompt_tokens,
                    "completion_tokens": s.completion_tokens,
                }
                for s in run.spans
            ]
            cost = run.cost_usd if run.cost_usd is not None else run.total_cost_usd
            out.append({
                "run_id":            str(run.id),
                "cost_usd":          float(cost) if cost is not None else sum(n["cost_usd"] for n in nodes),
                "latency_ms":        run.latency_ms or sum(n["latency_ms"] for n in nodes),
                "prompt_tokens":     sum(n["prompt_tokens"] for n in nodes),
                "completion_tokens": sum(n["completion_tokens"] for n in nodes),
                "faithfulness_score": float(run.faithfulness_score) if run.faithfulness_score is not None else None,
                "nodes":             nodes,
            })
        return out


def get_daily_averages(pipeline_id: str, days: int = 14) -> list[dict]:
    """Daily {date, faithfulness_mean, cost_mean, latency_mean} for the last
    N days, sorted oldest → newest (feeds detectors.anomaly_detector.DriftDetector)."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return []
        runs = _run_window(session, pipeline, days)

        buckets: dict[str, list[PipelineRun]] = defaultdict(list)
        for run in runs:
            buckets[run.started_at.date().isoformat()].append(run)

        out = []
        for day in sorted(buckets):
            day_runs = buckets[day]
            costs = [float(r.cost_usd if r.cost_usd is not None else (r.total_cost_usd or 0.0)) for r in day_runs]
            latencies = [r.latency_ms or 0 for r in day_runs]
            faiths = [float(r.faithfulness_score) for r in day_runs if r.faithfulness_score is not None]
            out.append({
                "date":              day,
                "cost_mean":         sum(costs) / len(costs) if costs else 0.0,
                "latency_mean":      sum(latencies) / len(latencies) if latencies else 0.0,
                "faithfulness_mean": sum(faiths) / len(faiths) if faiths else 1.0,
            })
        return out


def get_pipeline_metrics(
    pipeline_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    granularity: str = "day",
) -> list[dict]:
    """Historical cost / latency / faithfulness, bucketed by hour/day/week."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return []

        to_dt = datetime.fromisoformat(to_date) if to_date else _utcnow()
        default_span = {"hour": 2, "day": 30, "week": 90}.get(granularity, 30)
        from_dt = datetime.fromisoformat(from_date) if from_date else to_dt - timedelta(days=default_span)

        runs = session.scalars(
            select(PipelineRun)
            .where(PipelineRun.pipeline_id == pipeline.id)
            .where(PipelineRun.started_at >= from_dt)
            .where(PipelineRun.started_at <= to_dt)
            .order_by(PipelineRun.started_at.asc())
        )

        def _bucket_key(dt: datetime) -> str:
            if granularity == "hour":
                return dt.strftime("%Y-%m-%dT%H:00:00")
            if granularity == "week":
                start_of_week = dt - timedelta(days=dt.weekday())
                return start_of_week.date().isoformat()
            return dt.date().isoformat()

        buckets: dict[str, list[PipelineRun]] = defaultdict(list)
        for run in runs:
            buckets[_bucket_key(run.started_at)].append(run)

        out = []
        for key in sorted(buckets):
            bucket_runs = buckets[key]
            costs = [float(r.cost_usd if r.cost_usd is not None else (r.total_cost_usd or 0.0)) for r in bucket_runs]
            latencies = [r.latency_ms or 0 for r in bucket_runs]
            faiths = [float(r.faithfulness_score) for r in bucket_runs if r.faithfulness_score is not None]
            out.append({
                "bucket":            key,
                "cost_usd":          sum(costs) / len(costs) if costs else 0.0,
                "latency_ms":        sum(latencies) / len(latencies) if latencies else 0.0,
                "faithfulness_score": sum(faiths) / len(faiths) if faiths else None,
                "run_count":         len(bucket_runs),
            })
        return out


def recalculate_baseline_in_db(pipeline_id: str, runs: list[dict]) -> dict:
    """Recompute BaselineMetrics from the given runs (Phase 1: not persisted —
    detect_anomalies recomputes it fresh on every monitoring pass anyway)."""
    from detectors.anomaly_detector import calculate_baseline
    baseline = calculate_baseline(runs, pipeline_id)
    return vars(baseline)


# ── Incidents ─────────────────────────────────────────────────────────────────

def save_incident(incident_data: dict) -> str:
    """Insert an incidents row (+ one evidence row if evidence is present).
    Returns the new incident's db id (UUID string)."""
    with SessionLocal() as session:
        pipeline = _get_or_create_pipeline(session, incident_data["pipeline_id"])
        run = _find_run(session, pipeline, incident_data.get("run_id"))

        incident = Incident(
            pipeline_id=pipeline.id,
            run_id=run.id if run else None,
            incident_type=incident_data["incident_type"],
            severity=incident_data["severity"],
            status=incident_data.get("status", "OPEN"),
            title=incident_data.get("title", incident_data["incident_type"]),
            description=incident_data.get("suggested_fix"),
            root_cause=incident_data.get("root_cause"),
        )
        session.add(incident)
        session.flush()

        evidence = incident_data.get("evidence")
        if evidence:
            meta = evidence if isinstance(evidence, dict) else {}
            session.add(IncidentEvidence(
                incident_id=incident.id,
                evidence_type="METRIC",
                content=str(evidence),
                meta=meta,
            ))

        session.commit()
        return str(incident.id)


def list_incidents(
    pipeline_id: str | None = None,
    incident_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List incidents with optional filters, most recent first."""
    with SessionLocal() as session:
        query = select(Incident)

        if pipeline_id is not None:
            pipeline = _find_pipeline(session, pipeline_id)
            if pipeline is None:
                return []
            query = query.where(Incident.pipeline_id == pipeline.id)
        if incident_type is not None:
            query = query.where(Incident.incident_type == incident_type)
        if severity is not None:
            query = query.where(Incident.severity == severity)
        if status is not None:
            query = query.where(Incident.status == status)

        query = query.order_by(Incident.detected_at.desc()).limit(limit).offset(offset)
        incidents = session.scalars(query)
        return [_incident_to_dict(inc, include_evidence=False) for inc in incidents]


def get_incident(incident_id: str) -> dict | None:
    """Single incident with its evidence."""
    as_uuid = _as_uuid(incident_id)
    if as_uuid is None:
        return None
    with SessionLocal() as session:
        incident = session.get(Incident, as_uuid)
        return _incident_to_dict(incident) if incident is not None else None


def acknowledge_incident(incident_id: str, acknowledged_by: str) -> None:
    as_uuid = _as_uuid(incident_id)
    if as_uuid is None:
        return
    with SessionLocal() as session:
        incident = session.get(Incident, as_uuid)
        if incident is None:
            return
        incident.status = "ACKNOWLEDGED"
        incident.acknowledged_at = _utcnow()
        incident.acknowledged_by = acknowledged_by
        session.commit()


def resolve_incident_in_db(
    incident_id: str,
    resolution_notes: str | None,
    false_positive: bool,
    resolved_by: str,
) -> dict:
    """Mark an incident resolved (or suppressed, if flagged a false positive).
    There's no dedicated resolved_by column in the schema, so the resolving
    actor is recorded via acknowledged_by when that field is still empty."""
    as_uuid = _as_uuid(incident_id)
    if as_uuid is None:
        return {}
    with SessionLocal() as session:
        incident = session.get(Incident, as_uuid)
        if incident is None:
            return {}

        incident.status = "SUPPRESSED" if false_positive else "RESOLVED"
        incident.resolved_at = _utcnow()
        if resolution_notes:
            incident.description = (
                f"{incident.description}\n\nResolution: {resolution_notes}"
                if incident.description else resolution_notes
            )
        if not incident.acknowledged_by:
            incident.acknowledged_by = resolved_by

        session.commit()
        return _incident_to_dict(incident)


# ── Injection attempts ────────────────────────────────────────────────────────

def save_injection_attempt(attempt_data: dict) -> str:
    """Insert an injection_attempts row. Returns the new attempt's db id
    (UUID string)."""
    with SessionLocal() as session:
        pipeline = _get_or_create_pipeline(session, attempt_data["pipeline_id"])
        run = _find_run(session, pipeline, attempt_data.get("run_id"))

        attempt = InjectionAttempt(
            pipeline_id=pipeline.id,
            run_id=run.id if run else None,
            user_id=attempt_data.get("user_id"),
            input_text=attempt_data["input_text"],
            injection_type=attempt_data.get("injection_type"),
            matched_patterns=attempt_data.get("matched_patterns") or [],
            similarity_score=attempt_data.get("similarity_score"),
            blocked=attempt_data.get("blocked", False),
            incident_id=_as_uuid(attempt_data["incident_id"]) if attempt_data.get("incident_id") else None,
        )
        session.add(attempt)
        session.commit()
        return str(attempt.id)


def get_injection_count(user_id: str, pipeline_id: str, window_minutes: int = 60) -> int:
    """Count injection attempts from user_id in the last N minutes."""
    with SessionLocal() as session:
        pipeline = _find_pipeline(session, pipeline_id)
        if pipeline is None:
            return 0
        since = _utcnow() - timedelta(minutes=window_minutes)
        return session.scalar(
            select(func.count())
            .select_from(InjectionAttempt)
            .where(InjectionAttempt.pipeline_id == pipeline.id)
            .where(InjectionAttempt.user_id == user_id)
            .where(InjectionAttempt.detected_at >= since)
        ) or 0
