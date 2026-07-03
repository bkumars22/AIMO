"""
Alert rule evaluation — loads thresholds from DB (alert_rules table),
cached in Redis for 5 minutes.

Phase 1: implement load_rules() and evaluate().
"""
from __future__ import annotations


def load_rules(pipeline_id: str | None = None) -> list[dict]:
    """
    Load alert rules from DB, filtered by pipeline_id.
    Results cached in Redis for 5 minutes.
    """
    raise NotImplementedError("Phase 1")


def evaluate(scores: dict, pipeline_id: str) -> list[dict]:
    """
    Evaluate all detector scores against alert rules.
    Returns list of triggered rule dicts with severity.

    scores = {
      'faithfulness_score':    float | None,
      'cost_anomaly_score':    float | None,
      'compliance_score':      float | None,
      'latency_anomaly_score': float | None,
      'injection_detected':    bool,
    }
    """
    raise NotImplementedError("Phase 1")
