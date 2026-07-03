"""
Compliance Drift Detector — Node 4 of the AIMO monitoring pipeline

Detection method:
  1. Embedding drift — embed output_text (all-MiniLM-L6-v2, 384-dim),
     cosine-compare to pgvector store of known-compliant responses.
     Mean similarity < 0.82 on 3 consecutive outputs = drift.

  2. Shadow eval — COMPLIANCE_SHADOW_EVAL_RATE fraction of live traffic
     is checked against the pipeline's golden dataset
     (forbidden + required patterns, same logic as run_eval.py).

Severity:
  P0 — compliance_rate < 70%
  P1 — 70–80%
  P2 — 80–90%

Phase 1: implement embed_and_compare() and shadow_eval_case()
"""
from __future__ import annotations
import os

COMPLIANCE_MIN_RATE         = float(os.getenv("COMPLIANCE_MIN_RATE", "0.90"))
SHADOW_EVAL_RATE            = float(os.getenv("COMPLIANCE_SHADOW_EVAL_RATE", "0.10"))
EMBEDDING_DRIFT_THRESHOLD   = 0.82


def embed_and_compare(output_text: str, pipeline_id: str) -> float:
    """
    Embed output_text and cosine-compare to compliant baseline vectors.
    Returns mean similarity in [0, 1].
    """
    raise NotImplementedError("Phase 1")


def shadow_eval_case(input_text: str, output_text: str, pipeline_id: str) -> dict:
    """
    Run forbidden/required pattern check against pipeline's golden dataset.
    Returns { passed: bool, violations: list[str] }
    """
    raise NotImplementedError("Phase 1")


def severity_from_rate(compliance_pct: float) -> str:
    if compliance_pct < 70:
        return "P0"
    if compliance_pct < 80:
        return "P1"
    if compliance_pct < 90:
        return "P2"
    return "OK"
