"""
Hallucination Detector — Node 2 of the AIMO monitoring pipeline

Detection method:
  1. deepeval Faithfulness  — does every claim in output come from context?
     Threshold: HALLUCINATION_FAITHFULNESS_THRESHOLD (default 0.70)

  2. deepeval AnswerConsistency — same input_hash run N times: do outputs agree?
     Threshold: HALLUCINATION_CONSISTENCY_THRESHOLD (default 0.85)

Sample rate: HALLUCINATION_SAMPLE_RATE (default 20%)
Always runs when: same input_hash seen 3+ times in the last hour.

Severity:
  P0 — faithfulness < 0.40  (factually dangerous output)
  P1 — faithfulness 0.40–0.60
  P2 — faithfulness 0.60–0.70

Phase 1: implement score_faithfulness() and score_consistency()
"""
from __future__ import annotations
import os

FAITHFULNESS_THRESHOLD = float(os.getenv("HALLUCINATION_FAITHFULNESS_THRESHOLD", "0.70"))
CONSISTENCY_THRESHOLD  = float(os.getenv("HALLUCINATION_CONSISTENCY_THRESHOLD",  "0.85"))
SAMPLE_RATE            = float(os.getenv("HALLUCINATION_SAMPLE_RATE",            "0.20"))


def score_faithfulness(output: str, context: str, model_id: str) -> float:
    """
    Run deepeval Faithfulness metric.
    Returns score in [0, 1]; lower = more hallucination.
    """
    raise NotImplementedError("Phase 1")


def score_consistency(output: str, prior_outputs: list[str]) -> float:
    """
    Compute mean cosine similarity between output and prior outputs
    for the same input (same input_hash).
    Returns score in [0, 1]; lower = more inconsistent.
    """
    raise NotImplementedError("Phase 1")


def severity_from_score(score: float) -> str:
    if score < 0.40:
        return "P0"
    if score < 0.60:
        return "P1"
    if score < FAITHFULNESS_THRESHOLD:
        return "P2"
    return "OK"
