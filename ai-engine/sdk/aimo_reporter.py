"""
AIMO Sync Reporter — fire-and-forget for synchronous pipelines.

Zero external dependencies — uses stdlib urllib only.
For use in sync LangGraph pipelines (QAIP, SCIP, ARIA, ZENTRAVIX).

Credentials are read from environment variables at call time:
  AIMO_API_KEY       — Bearer token returned by /pipelines/register
  AIMO_PIPELINE_ID   — UUID returned by /pipelines/register
  AIMO_BASE_URL      — Base URL of AIMO AI engine (default: http://localhost:8001)

Usage:
    import aimo_reporter

    # After every pipeline run — returns immediately, HTTP ships in daemon thread
    aimo_reporter.report_run(
        nodes=[
            {"name": "score_risk",   "duration_ms": 120, "tokens": 0,   "cost_rupees": 0},
            {"name": "explain_risk", "duration_ms": 800, "tokens": 160, "cost_rupees": 1.2},
        ],
        faithfulness_score=0.88,
    )

    # When pipeline detects its own problem
    aimo_reporter.report_incident(
        incident_type="HALLUCINATION",
        severity="P1",
        title="Low faithfulness on Supplier X",
        evidence={"supplier": "Acme", "score": 0.62},
    )
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

RUPEES_PER_USD: float = float(os.getenv("RUPEES_PER_USD", "83.0"))


# ── Internals ─────────────────────────────────────────────────────────────────

def _normalise_nodes(nodes: list[dict]) -> list[dict]:
    result = []
    for i, n in enumerate(nodes):
        cost_usd = n.get("cost_usd") or n.get("cost_rupees", 0.0) / RUPEES_PER_USD
        result.append({
            "name":              n.get("name", f"node_{i}"),
            "model_id":          n.get("model_id") or n.get("model_used"),
            "cost_usd":          round(float(cost_usd), 6),
            "latency_ms":        int(n.get("latency_ms") or n.get("duration_ms", 0)),
            "prompt_tokens":     int(n.get("prompt_tokens") or n.get("tokens", 0)),
            "completion_tokens": int(n.get("completion_tokens", 0)),
            "input_text":        str(n.get("input_text",  "")),
            "output_text":       str(n.get("output_text", "")),
        })
    return result


def _post(url: str, payload: dict, api_key: str, timeout: float = 5.0) -> None:
    """Sync HTTP POST. Never raises — all errors are logged at DEBUG level."""
    try:
        data    = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = Request(url, data=data, headers=headers, method="POST")
        urlopen(req, timeout=timeout)
        logger.debug("AIMO reporter: POST %s ok", url)
    except Exception as exc:
        logger.debug("AIMO reporter: POST %s failed (%s) — pipeline unaffected", url, exc)


def _fire(url: str, payload: dict, api_key: str) -> None:
    """Dispatch _post in a daemon thread. Never blocks the caller."""
    t = threading.Thread(target=_post, args=(url, payload, api_key), daemon=True)
    t.start()


def _creds() -> tuple[str, str, str]:
    """Read (pipeline_id, api_key, base_url) from env."""
    return (
        os.getenv("AIMO_PIPELINE_ID", ""),
        os.getenv("AIMO_API_KEY",     ""),
        os.getenv("AIMO_BASE_URL",    "http://localhost:8001").rstrip("/"),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def report_run(
    nodes:              list[dict] | None = None,
    total_cost_rupees:  float             = 0.0,
    faithfulness_score: float | None      = None,
    outputs:            dict | None       = None,
    contexts:           list[str] | None  = None,
    run_id:             str | None        = None,
    input_text:         str               = "",
    output_text:        str               = "",
) -> None:
    """
    Fire-and-forget AIMO run report. Returns immediately.
    If AIMO is unreachable the daemon thread fails silently.

    Args:
        nodes:              Per-node metrics. Accepts aliases: duration_ms, cost_rupees,
                            tokens, model_used — automatically mapped to AIMO schema.
        total_cost_rupees:  Total run cost in INR (auto-converted to USD).
        faithfulness_score: deepeval / RAGAS faithfulness 0.0–1.0.
        outputs:            Final pipeline output dict (str-coerced).
        contexts:           RAG context chunks (attached to last node).
        run_id:             Optional custom ID (auto-generated UUID if omitted).
        input_text:         Top-level pipeline input.
        output_text:        Top-level pipeline output.
    """
    pipeline_id, api_key, base_url = _creds()
    if not pipeline_id:
        logger.debug("AIMO reporter: AIMO_PIPELINE_ID not set — skipping report_run")
        return

    norm = _normalise_nodes(nodes or [])
    if contexts and norm:
        norm[-1]["context"] = contexts  # type: ignore[assignment]

    payload = {
        "pipeline_id":        pipeline_id,
        "run_id":             run_id or str(uuid.uuid4()),
        "nodes":              norm,
        "input_text":         input_text,
        "output_text":        output_text or (str(outputs) if outputs else ""),
        "faithfulness_score": faithfulness_score,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }
    _fire(f"{base_url}/runs/ingest", payload, api_key)


def report_incident(
    incident_type: str,
    severity:      str,
    title:         str,
    description:   str       = "",
    evidence:      dict | None = None,
) -> None:
    """
    Report a pipeline-detected incident directly to AIMO. Returns immediately.

    Args:
        incident_type: HALLUCINATION | COST_SPIKE | COMPLIANCE_DRIFT |
                       LATENCY_DEGRADATION | PROMPT_INJECTION | ANOMALY
        severity:      P0 | P1 | P2 | P3
        title:         Short human-readable title.
        description:   Detailed description.
        evidence:      Supporting data dict (scores, inputs, outputs).
    """
    pipeline_id, api_key, base_url = _creds()
    if not pipeline_id:
        return

    payload = {
        "pipeline_id":   pipeline_id,
        "incident_type": incident_type,
        "severity":      severity,
        "title":         title,
        "description":   description,
        "evidence":      evidence or {},
    }
    _fire(f"{base_url}/incidents", payload, api_key)
