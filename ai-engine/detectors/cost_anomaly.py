"""
Cost Anomaly Detector — Node 3 of the AIMO monitoring pipeline

Detection method:
  1. IsolationForest trained on 7-day rolling cost_usd window
     per (pipeline_id, node_name).
     anomaly_score > 0 = anomaly (sklearn convention: -1/+1 → mapped to 0–1)

  2. Hard check: cost_usd > COST_SPIKE_MULTIPLIER × rolling_7d_avg

  3. Absolute ceiling: cost_usd > COST_SPIKE_ABSOLUTE_CEILING_USD

Also projects Groq daily token quota usage.

Severity:
  P0 — > 10× rolling avg
  P1 — 5–10× rolling avg
  P2 — 3–5× rolling avg

Phase 1: implement detect() using PostgreSQL cost history + sklearn
"""
from __future__ import annotations
import os

COST_SPIKE_MULTIPLIER      = float(os.getenv("COST_SPIKE_MULTIPLIER", "3.0"))
COST_CEILING_USD           = float(os.getenv("COST_SPIKE_ABSOLUTE_CEILING_USD", "0.50"))
GROQ_DAILY_TOKEN_LIMIT     = int(os.getenv("GROQ_DAILY_TOKEN_LIMIT", "100000"))


def detect(
    pipeline_id: str,
    node_name: str,
    cost_usd: float,
    tokens_used: int,
    history: list[float],
) -> dict:
    """
    Analyze cost against rolling window history.

    Returns:
      {
        anomaly_score:   float,   # 0–1, higher = more anomalous
        baseline_avg:    float,   # 7-day rolling average
        is_anomaly:      bool,
        severity:        str,     # 'P0' | 'P1' | 'P2' | 'OK'
        quota_pct:       float,   # Groq daily quota % used today
      }
    """
    raise NotImplementedError("Phase 1")


def severity_from_multiplier(multiplier: float) -> str:
    if multiplier > 10:
        return "P0"
    if multiplier > 5:
        return "P1"
    if multiplier > COST_SPIKE_MULTIPLIER:
        return "P2"
    return "OK"
