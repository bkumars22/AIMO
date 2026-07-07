"""
Hallucination Detector

Phase 1 stub (score_faithfulness raised NotImplementedError) replaced with
a real deepeval FaithfulnessMetric implementation, Redis-cached for an hour,
plus an AIPQ root-cause lookup once an incident fires.

Detection method:
  deepeval FaithfulnessMetric — does every claim in output come from context?
  Severity: P1 if score < 0.75, P0 if score < 0.60. Score >= 0.75 -> no incident.

Note: nothing in monitoring_agent.py calls into this module yet — the
already-wired HALLUCINATION path in classify_incidents uses
evaluators/deepeval_evaluator.py's separate score_faithfulness. This module
is a standalone, directly callable detector built to this file's spec;
score_consistency (same-input-run-N-times drift) is unrelated to this pass
and is left as the Phase 1 stub it was.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from integrations.aipq_connector import check_aipq_root_cause

logger = logging.getLogger(__name__)

FAITHFULNESS_THRESHOLD = float(os.getenv("HALLUCINATION_FAITHFULNESS_THRESHOLD", "0.70"))
CONSISTENCY_THRESHOLD  = float(os.getenv("HALLUCINATION_CONSISTENCY_THRESHOLD",  "0.85"))
SAMPLE_RATE            = float(os.getenv("HALLUCINATION_SAMPLE_RATE",            "0.20"))

P1_THRESHOLD = 0.75
P0_THRESHOLD = 0.60
CACHE_TTL_SECONDS = 3600

try:
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.test_case import LLMTestCase
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    logger.warning("deepeval not installed — hallucination scoring disabled")

try:
    import redis as redis_lib
    _redis_client = redis_lib.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
except Exception:
    _redis_client = None


@dataclass
class HallucinationIncident:
    severity: str                              # "P0" | "P1"
    score: float
    output: str
    context: list[str] = field(default_factory=list)
    root_cause: Optional[str] = None
    aipq_status: Optional[dict] = None


def _cache_key(output: str, context: list[str]) -> str:
    payload = json.dumps([output, context], sort_keys=True)
    return f"aimo:hallucination:{hashlib.sha256(payload.encode()).hexdigest()}"


def _cache_get(key: str) -> Optional[float]:
    if _redis_client is None:
        return None
    try:
        val = _redis_client.get(key)
        return float(val) if val is not None else None
    except Exception:
        return None


def _cache_set(key: str, score: float) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.setex(key, CACHE_TTL_SECONDS, str(score))
    except Exception:
        pass


def score_faithfulness(output: str, context: list[str], model_id: str = "gpt-4o-mini") -> float:
    """
    Runs deepeval's FaithfulnessMetric on (output, context chunks).
    Result is cached in Redis for 1 hour, keyed by the exact (output, context) pair.
    """
    key = _cache_key(output, context)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    if not DEEPEVAL_AVAILABLE:
        raise RuntimeError("deepeval is not installed — cannot score faithfulness")

    metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, model=model_id)
    test_case = LLMTestCase(input="", actual_output=output, retrieval_context=context)
    metric.measure(test_case)
    score = metric.score

    _cache_set(key, score)
    return score


def score_consistency(output: str, prior_outputs: list[str]) -> float:
    """Same input run N times: do outputs agree? Out of scope for this pass."""
    raise NotImplementedError("Phase 1")


async def detect_hallucination(
    output: str,
    context: list[str],
    aipq_project_id: Optional[int] = None,
    aipq_prompt_name: Optional[str] = None,
    model_id: str = "gpt-4o-mini",
) -> Optional[HallucinationIncident]:
    """
    Scores (output, context) for faithfulness. Returns a HallucinationIncident
    (P0 if score < 0.60, P1 if score < 0.75) or None if the output is
    faithful enough that no incident should fire.

    When aipq_project_id/aipq_prompt_name identify an AIPQ-tracked prompt and
    an incident does fire, queries AIPQ for whether a recent prompt change is
    the likely cause and folds that into the incident's root_cause/evidence —
    never raises on an AIPQ failure, since a down/unconfigured AIPQ must not
    prevent the underlying hallucination incident from being reported.
    """
    score = score_faithfulness(output, context, model_id=model_id)

    if score < P0_THRESHOLD:
        severity = "P0"
    elif score < P1_THRESHOLD:
        severity = "P1"
    else:
        return None

    incident = HallucinationIncident(severity=severity, score=score, output=output, context=context)

    if aipq_project_id and aipq_prompt_name:
        aipq_status = await check_aipq_root_cause(aipq_project_id, aipq_prompt_name)
        if aipq_status is not None:
            incident.aipq_status = aipq_status
            if aipq_status.get("changed_recently"):
                incident.root_cause = f"Root cause: prompt change v{aipq_status.get('current_version_number')}"
            else:
                incident.root_cause = "Root cause: model drift (prompt unchanged recently)"
        else:
            incident.root_cause = "Root cause: unknown (AIPQ unavailable)"
    else:
        incident.root_cause = "Root cause: unknown (no AIPQ prompt mapping provided)"

    logger.warning(
        "Hallucination incident [%s] faithfulness=%.3f — %s",
        severity, score, incident.root_cause,
    )
    return incident


def severity_from_score(score: float) -> str:
    if score < P0_THRESHOLD:
        return "P0"
    if score < P1_THRESHOLD:
        return "P1"
    return "OK"
