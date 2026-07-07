"""
Prompt 4 — LangGraph Monitoring Agent (6 nodes)
collect_metrics → detect_anomalies → classify_incidents →
generate_root_cause → send_alerts → store_and_update

Error isolation: one node failure must not crash the entire run.
LangSmith tracing on every node via @trace_node.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)

# ── LangGraph ─────────────────────────────────────────────────────────────────
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("langgraph not installed — monitoring graph disabled")

# ── LangSmith tracing ─────────────────────────────────────────────────────────
from langsmith_utils import trace_node

# ── Detectors ─────────────────────────────────────────────────────────────────
from detectors.anomaly_detector import (
    calculate_baseline,
    run_full_detection,
)
from detectors.injection_detector import classify as classify_injection

# ── Evaluators ────────────────────────────────────────────────────────────────
from evaluators.deepeval_evaluator import evaluate_nodes

# ── Storage / alerting stubs (implemented in Phase 1) ────────────────────────
from alerting.dispatcher import dispatch
from alerting.redis_pubsub import publish
from storage.repositories import (
    save_incident,
    update_pipeline_health,
    get_recent_runs,
    get_daily_averages,
)
from storage.vector_store import store_response_embedding

# ── AIPQ root-cause check (prompt change vs model drift) ─────────────────────
from integrations.aipq_connector import check_aipq_root_cause, format_root_cause_note

# ── Claude AI for root cause ──────────────────────────────────────────────────
try:
    from langchain_anthropic import ChatAnthropic
    _llm = ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        max_tokens=1024,
    )
    LLM_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
except Exception:
    _llm = None
    LLM_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# State schema (Prompt 4 spec)
# ─────────────────────────────────────────────────────────────────────────────

class AIMOState(TypedDict):
    pipeline_id: str
    run_id: str
    run_data: dict           # raw webhook payload
    metrics: dict            # normalised metrics after Node 1
    baseline: dict           # BaselineMetrics serialised as dict
    anomalies: list          # AnomalySignal dicts from Node 2
    incidents: list          # typed incident dicts from Node 3
    enriched_incidents: list # incidents + root cause from Node 4
    alerts_sent: list        # alert delivery receipts from Node 5
    saved_ids: list          # DB ids from Node 6
    errors: list             # per-node error records (do not stop pipeline)


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — collect_metrics
# ─────────────────────────────────────────────────────────────────────────────

@trace_node
def collect_metrics(state: AIMOState) -> AIMOState:
    """
    Extract all node traces, costs, latencies, token counts,
    model names, temperatures from raw run_data.
    """
    try:
        run   = state["run_data"]
        nodes = run.get("nodes", [])

        node_metrics = [
            {
                "name":              n.get("name", f"node_{i}"),
                "model":             n.get("model_id"),
                "temperature":       n.get("temperature"),
                "cost_usd":          n.get("cost_usd", 0.0),
                "latency_ms":        n.get("latency_ms", 0),
                "prompt_tokens":     n.get("prompt_tokens", 0),
                "completion_tokens": n.get("completion_tokens", 0),
                "input_text":        n.get("input_text", ""),
                "output_text":       n.get("output_text", ""),
                "context":           n.get("context"),
            }
            for i, n in enumerate(nodes)
        ]

        metrics = {
            "cost_usd":          sum(n.get("cost_usd", 0.0) for n in nodes),
            "latency_ms":        sum(n.get("latency_ms", 0) for n in nodes),
            "prompt_tokens":     sum(n.get("prompt_tokens", 0) for n in nodes),
            "completion_tokens": sum(n.get("completion_tokens", 0) for n in nodes),
            "faithfulness_score": run.get("faithfulness_score"),
            "output_text":       run.get("output_text", ""),
            "input_text":        run.get("input_text", ""),
            "node_metrics":      node_metrics,
            "nodes":             nodes,
            "node_count":        len(nodes),
        }
        return {**state, "metrics": metrics}
    except Exception as exc:
        logger.error("collect_metrics failed: %s", exc)
        return {**state, "metrics": {}, "errors": state["errors"] + [{"node": "collect_metrics", "error": str(exc)}]}


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — detect_anomalies
# ─────────────────────────────────────────────────────────────────────────────

@trace_node
def detect_anomalies(state: AIMOState) -> AIMOState:
    """
    IsolationForest + ThresholdDetector + DriftDetector + injection scan.
    Compares current run against DB baseline.
    """
    try:
        pipeline_id = state["pipeline_id"]
        run         = state["metrics"]

        historical = get_recent_runs(pipeline_id, limit=50)
        daily_avgs = get_daily_averages(pipeline_id, days=14)
        baseline   = calculate_baseline(historical, pipeline_id)

        signals = run_full_detection(run, baseline, historical, daily_avgs)

        # Injection scan on combined input + output
        text = f"{run.get('input_text', '')} {run.get('output_text', '')}".strip()
        if text:
            inj = classify_injection(text)
            if inj["detected"]:
                signals.append({  # type: ignore[arg-type]
                    "signal_type": "PROMPT_INJECTION",
                    "severity":    "P0",
                    "score":       inj.get("similarity") or 1.0,
                    "feature":     "input_output_text",
                    "value":       1.0,
                    "baseline_value": 0.0,
                    "explanation": f"Injection type: {inj.get('type')} | patterns: {inj.get('patterns')}",
                    "source":      "injection_detector",
                })

        serialised_signals = [vars(s) if hasattr(s, "__dict__") else s for s in signals]

        return {
            **state,
            "baseline":  vars(baseline),
            "anomalies": serialised_signals,
        }
    except Exception as exc:
        logger.error("detect_anomalies failed: %s", exc)
        return {
            **state,
            "anomalies": [],
            "baseline": {},
            "errors": state["errors"] + [{"node": "detect_anomalies", "error": str(exc)}],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — classify_incidents
# ─────────────────────────────────────────────────────────────────────────────

_SIGNAL_MAP: dict[str, tuple[str, str]] = {
    "COST_SPIKE":          ("COST_SPIKE",          "P2"),
    "LATENCY_DEGRADATION": ("LATENCY_DEGRADATION", "P2"),
    "HALLUCINATION":       ("HALLUCINATION",        "P1"),
    "PROMPT_INJECTION":    ("PROMPT_INJECTION",     "P0"),
    "COMPLIANCE_DRIFT":    ("COMPLIANCE_DRIFT",     "P1"),
    "COST_TREND":          ("COST_SPIKE",           "P3"),
    "LATENCY_TREND":       ("LATENCY_DEGRADATION",  "P3"),
    "ANOMALY":             ("ANOMALY",              "P2"),
}


@trace_node
def classify_incidents(state: AIMOState) -> AIMOState:
    """
    Rule-based classification for known signals.
    Claude AI classifies edge-case ANOMALY signals.
    deepeval batch eval adds HALLUCINATION / QUALITY_DEGRADATION incidents.
    """
    try:
        incidents: list[dict] = []

        for signal in state.get("anomalies", []):
            sig_type = signal.get("signal_type", "ANOMALY")
            rule = _SIGNAL_MAP.get(sig_type)

            if rule:
                inc_type, default_sev = rule
                severity = signal.get("severity") or default_sev
                incidents.append(_make_incident(state, inc_type, severity, signal))
            else:
                # Edge-case: ask Claude
                classified = _claude_classify(state, signal)
                incidents.append(classified)

        # deepeval node-level evaluation
        node_metrics = state.get("metrics", {}).get("node_metrics", [])
        if node_metrics:
            try:
                batch = evaluate_nodes(state["pipeline_id"], state["run_id"], node_metrics)
                for nr in batch.node_results:
                    for triggered in nr.incidents_triggered:
                        evidence = {
                            "node": nr.node_name,
                            "faithfulness": nr.faithfulness_score,
                            "relevance": nr.relevance_score,
                            "geval": nr.geval_score,
                        }
                        incidents.append(_make_incident(state, triggered, "P1", evidence))
            except Exception as eval_exc:
                logger.warning("deepeval batch evaluation failed: %s", eval_exc)

        return {**state, "incidents": incidents}
    except Exception as exc:
        logger.error("classify_incidents failed: %s", exc)
        return {
            **state,
            "incidents": [],
            "errors": state["errors"] + [{"node": "classify_incidents", "error": str(exc)}],
        }


def _make_incident(state: AIMOState, inc_type: str, severity: str, evidence: dict) -> dict:
    expl = evidence.get("explanation", "") if isinstance(evidence, dict) else str(evidence)
    return {
        "id":           str(uuid.uuid4()),
        "pipeline_id":  state["pipeline_id"],
        "run_id":       state["run_id"],
        "incident_type": inc_type,
        "severity":     severity,
        "title":        _title(inc_type, evidence),
        "evidence":     evidence,
        "status":       "OPEN",
        "root_cause":   None,
        "suggested_fix": None,
    }


def _title(inc_type: str, evidence: dict) -> str:
    if isinstance(evidence, dict) and evidence.get("explanation"):
        expl = evidence["explanation"]
        return f"{inc_type}: {expl[:120]}"
    return inc_type


def _claude_classify(state: AIMOState, signal: dict) -> dict:
    if not LLM_AVAILABLE or not _llm:
        return _make_incident(state, "ANOMALY", "P2", signal)
    try:
        prompt = (
            f"Anomaly signal:\n{signal}\n\n"
            "Classify as: COST_SPIKE | HALLUCINATION | LATENCY_DEGRADATION | "
            "COMPLIANCE_DRIFT | PROMPT_INJECTION | OTHER\n"
            "Reply format: TYPE SEVERITY (e.g., HALLUCINATION P1)"
        )
        text = _llm.invoke(prompt).content.strip()
        parts = text.split()
        inc_type = parts[0] if parts else "ANOMALY"
        severity = parts[1] if len(parts) > 1 else "P2"
        return _make_incident(state, inc_type, severity, {**signal, "classifier": "claude"})
    except Exception as exc:
        logger.warning("Claude classification failed: %s", exc)
        return _make_incident(state, "ANOMALY", "P2", signal)


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — generate_root_cause
# ─────────────────────────────────────────────────────────────────────────────

_ROOT_CAUSE_PROMPT = """\
You are an AI reliability engineer. Analyse this incident and provide:
1. WHAT specifically went wrong (1-2 sentences)
2. WHICH node caused it (node name or 'pipeline-level')
3. WHY it likely happened (root cause, 2-3 sentences)
4. SUGGESTED FIX with a concrete Python code example

Incident: {incident}
Pipeline metrics: {metrics}
Baseline: {baseline}

Be specific. Do not invent node names not present in the evidence."""


def _augment_with_aipq(incident: dict) -> dict:
    """
    For HALLUCINATION/QUALITY_DEGRADATION incidents whose evidence identifies
    an AIPQ-tracked prompt, ask AIPQ whether a recent prompt change is the
    likely cause (vs. underlying model drift) and fold that into root_cause.

    Evidence carrying aipq_project_id/aipq_prompt_name is not produced by
    anything in AIMO yet (hallucination.py is a Phase-1 stub) — this is the
    ready-to-fire other half of that loop for once it is. Runs inside a
    background-thread executor (see main.py), never inside an already-running
    event loop, so asyncio.run() here is safe.
    """
    if incident.get("incident_type") not in ("HALLUCINATION", "QUALITY_DEGRADATION"):
        return incident

    evidence = incident.get("evidence") or {}
    project_id = evidence.get("aipq_project_id")
    prompt_name = evidence.get("aipq_prompt_name")
    if not project_id or not prompt_name:
        return incident

    try:
        aipq_status = asyncio.run(check_aipq_root_cause(project_id, prompt_name))
    except Exception as exc:
        logger.warning("AIPQ augmentation failed for incident %s: %s", incident.get("id"), exc)
        return incident

    if aipq_status is None:
        return incident

    note = format_root_cause_note(aipq_status)
    return {
        **incident,
        "root_cause": f"{incident.get('root_cause', '')}\n\n{note}".strip(),
        "aipq_status": aipq_status,
    }


@trace_node
def generate_root_cause(state: AIMOState) -> AIMOState:
    """
    Claude AI generates root cause, node attribution, suggested fix.
    Falls back to structured stub if LLM unavailable.
    """
    enriched: list[dict] = []

    for inc in state.get("incidents", []):
        try:
            if not LLM_AVAILABLE or not _llm:
                entry = {
                    **inc,
                    "root_cause": "AI root cause generation disabled (ANTHROPIC_API_KEY not set).",
                }
                enriched.append(_augment_with_aipq(entry))
                continue

            prompt = _ROOT_CAUSE_PROMPT.format(
                incident=inc,
                metrics=state.get("metrics", {}),
                baseline=state.get("baseline", {}),
            )
            response = _llm.invoke(prompt).content.strip()

            suggested_fix = None
            if "```" in response:
                start = response.find("```")
                end   = response.find("```", start + 3)
                if end > start:
                    suggested_fix = response[start : end + 3]

            entry = {**inc, "root_cause": response, "suggested_fix": suggested_fix}
            entry = _augment_with_aipq(entry)
            enriched.append(entry)
        except Exception as exc:
            logger.error("root cause generation failed for %s: %s", inc.get("id"), exc)
            enriched.append({**inc, "root_cause": f"Generation error: {exc}"})

    return {**state, "enriched_incidents": enriched}


# ─────────────────────────────────────────────────────────────────────────────
# Node 5 — send_alerts
# ─────────────────────────────────────────────────────────────────────────────

@trace_node
def send_alerts(state: AIMOState) -> AIMOState:
    """
    P0/P1 → Slack immediately  |  P2 → email summary  |  P3 → log + dashboard
    """
    alerts_sent: list[dict] = []
    incidents = state.get("enriched_incidents") or state.get("incidents", [])

    for inc in incidents:
        severity = inc.get("severity", "P3")
        try:
            if severity in ("P0", "P1"):
                result = dispatch(inc, channel="slack")
                alerts_sent.append({"incident_id": inc["id"], "channel": "slack", "result": result})
            elif severity == "P2":
                result = dispatch(inc, channel="email")
                alerts_sent.append({"incident_id": inc["id"], "channel": "email", "result": result})
            else:
                logger.info("P3 incident %s — log only", inc["id"])
                alerts_sent.append({"incident_id": inc["id"], "channel": "log", "result": "logged"})
        except Exception as exc:
            logger.error("alert dispatch failed for %s: %s", inc.get("id"), exc)
            state["errors"].append({"node": "send_alerts", "incident_id": inc.get("id"), "error": str(exc)})

    return {**state, "alerts_sent": alerts_sent}


# ─────────────────────────────────────────────────────────────────────────────
# Node 6 — store_and_update
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_PENALTY = {"P0": 25, "P1": 10, "P2": 5, "P3": 1}


@trace_node
def store_and_update(state: AIMOState) -> AIMOState:
    """
    Save incidents to DB, update baseline, store embeddings in pgvector,
    update pipeline health score, push real-time update via Redis pub/sub.
    """
    saved_ids: list[str] = []
    incidents = state.get("enriched_incidents") or state.get("incidents", [])

    for inc in incidents:
        try:
            db_id = save_incident(inc)
            saved_ids.append(db_id or inc["id"])

            output = state.get("metrics", {}).get("output_text", "")
            if output:
                store_response_embedding(
                    pipeline_id=state["pipeline_id"],
                    run_id=state["run_id"],
                    text=output,
                    metadata={"incident_id": inc["id"], "incident_type": inc["incident_type"]},
                )
        except Exception as exc:
            logger.error("save_incident failed: %s", exc)
            state["errors"].append({"node": "store_and_update", "error": str(exc)})

    penalty = sum(_SEVERITY_PENALTY.get(i.get("severity", "P3"), 1) for i in incidents)
    health_score = max(0, 100 - penalty)

    try:
        update_pipeline_health(state["pipeline_id"], health_score)
    except Exception as exc:
        logger.error("update_pipeline_health failed: %s", exc)

    # Best-effort real-time push (WebSocket)
    try:
        import asyncio
        payload = {
            "pipeline_id":  state["pipeline_id"],
            "run_id":       state["run_id"],
            "health_score": health_score,
            "incidents": [
                {"id": i["id"], "type": i["incident_type"], "severity": i["severity"]}
                for i in incidents
            ],
        }
        asyncio.create_task(publish("aimo:incidents", payload))
    except Exception:
        pass

    return {**state, "saved_ids": saved_ids}


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph StateGraph
# ─────────────────────────────────────────────────────────────────────────────

def _build_graph():
    if not LANGGRAPH_AVAILABLE:
        return None
    g = StateGraph(AIMOState)
    g.add_node("collect_metrics",     collect_metrics)
    g.add_node("detect_anomalies",    detect_anomalies)
    g.add_node("classify_incidents",  classify_incidents)
    g.add_node("generate_root_cause", generate_root_cause)
    g.add_node("send_alerts",         send_alerts)
    g.add_node("store_and_update",    store_and_update)
    g.set_entry_point("collect_metrics")
    g.add_edge("collect_metrics",     "detect_anomalies")
    g.add_edge("detect_anomalies",    "classify_incidents")
    g.add_edge("classify_incidents",  "generate_root_cause")
    g.add_edge("generate_root_cause", "send_alerts")
    g.add_edge("send_alerts",         "store_and_update")
    g.add_edge("store_and_update",    END)
    return g.compile()


monitoring_graph = _build_graph()


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_monitoring(pipeline_id: str, run_data: dict) -> AIMOState:
    """Invoke the 6-node monitoring pipeline. Safe even if graph is None."""
    initial: AIMOState = {
        "pipeline_id":        pipeline_id,
        "run_id":             run_data.get("run_id") or str(uuid.uuid4()),
        "run_data":           run_data,
        "metrics":            {},
        "baseline":           {},
        "anomalies":          [],
        "incidents":          [],
        "enriched_incidents": [],
        "alerts_sent":        [],
        "saved_ids":          [],
        "errors":             [],
    }
    if monitoring_graph is None:
        return {**initial, "errors": [{"node": "run_monitoring", "error": "LangGraph not installed"}]}
    try:
        return monitoring_graph.invoke(initial)
    except Exception as exc:
        logger.error("monitoring_graph.invoke failed: %s", exc)
        return {**initial, "errors": [{"node": "run_monitoring", "error": str(exc)}]}
