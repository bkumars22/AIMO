"""
Latency Degradation Detector — Node 5 of the AIMO monitoring pipeline

Detection method:
  1. IsolationForest on 7-day per-node latency window
  2. z-score: (current - mean) / std > LATENCY_ZSCORE_THRESHOLD
  3. Hard check: latency_ms > LATENCY_SPIKE_MULTIPLIER × p95_baseline
  4. Distinguishes Groq rate-limit retry (simultaneous cost + latency spike)

Severity:
  P0 — > 5× P95 baseline OR timeout (latency > 30_000ms)
  P1 — 3–5× P95 baseline
  P2 — 2–3× P95 baseline

Phase 1: implement detect() using PostgreSQL span history + sklearn
"""
from __future__ import annotations
import os

LATENCY_SPIKE_MULTIPLIER = float(os.getenv("LATENCY_SPIKE_MULTIPLIER", "2.0"))
LATENCY_ZSCORE_THRESHOLD = float(os.getenv("LATENCY_ZSCORE_THRESHOLD", "2.5"))
TIMEOUT_THRESHOLD_MS     = 30_000


def detect(
    pipeline_id: str,
    node_name: str,
    latency_ms: int,
    history_ms: list[int],
) -> dict:
    """
    Analyze latency against rolling window history.

    Returns:
      {
        anomaly_score:    float,
        p50:              float,
        p95:              float,
        p99:              float,
        z_score:          float,
        is_anomaly:       bool,
        severity:         str,
        is_rate_limit:    bool,   # True if cost spike also detected in same run
      }
    """
    raise NotImplementedError("Phase 1")


def severity_from_multiplier(multiplier: float, is_timeout: bool) -> str:
    if is_timeout or multiplier > 5:
        return "P0"
    if multiplier > 3:
        return "P1"
    if multiplier > LATENCY_SPIKE_MULTIPLIER:
        return "P2"
    return "OK"
