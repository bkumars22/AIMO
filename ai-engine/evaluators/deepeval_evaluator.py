"""
Prompt 8 — deepeval Integration
Faithfulness, Relevance, Consistency, GEval + batch + trend detection.
Redis caching: same input → skip re-evaluation for 1 hour.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from statistics import mean, variance

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
FAITHFULNESS_THRESHOLD  = float(os.getenv("FAITHFULNESS_THRESHOLD", "0.85"))
RELEVANCE_THRESHOLD     = float(os.getenv("RELEVANCE_THRESHOLD", "0.80"))
CONSISTENCY_VAR_MAX     = float(os.getenv("CONSISTENCY_VAR_MAX", "0.05"))
GEVAL_THRESHOLD         = float(os.getenv("GEVAL_THRESHOLD", "0.90"))
EVAL_SAMPLE_RATE        = float(os.getenv("EVAL_SAMPLE_RATE", "0.20"))   # 20% of runs
DRIFT_WINDOW            = int(os.getenv("DRIFT_WINDOW", "10"))           # last N runs
EVAL_CACHE_TTL_SEC      = int(os.getenv("EVAL_CACHE_TTL_SEC", "3600"))   # 1 hour

# ── Lazy deepeval import (tests can mock it) ──────────────────────────────────
try:
    from deepeval import evaluate
    from deepeval.metrics import (
        FaithfulnessMetric,
        AnswerRelevancyMetric,
        GEval,
    )
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    logger.warning("deepeval not installed — eval scores will be None")

# ── Lazy Redis import ─────────────────────────────────────────────────────────
try:
    import redis as redis_lib
    _redis_client = redis_lib.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    REDIS_AVAILABLE = True
except Exception:
    _redis_client = None
    REDIS_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NodeEvalResult:
    node_name: str
    faithfulness_score: float | None = None
    relevance_score: float | None    = None
    consistency_score: float | None  = None
    geval_score: float | None        = None
    incidents_triggered: list[str]   = field(default_factory=list)
    cached: bool = False


@dataclass
class BatchEvalResult:
    pipeline_id: str
    run_id: str
    node_results: list[NodeEvalResult]
    drift_signals: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Redis cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(input_text: str, context: str | None, output_text: str, metric: str) -> str:
    payload = json.dumps([input_text, context, output_text, metric], sort_keys=True)
    return f"aimo:eval:{hashlib.sha256(payload.encode()).hexdigest()}"


def _cache_get(key: str) -> float | None:
    if not REDIS_AVAILABLE or not _redis_client:
        return None
    try:
        val = _redis_client.get(key)
        return float(val) if val is not None else None
    except Exception:
        return None


def _cache_set(key: str, score: float) -> None:
    if not REDIS_AVAILABLE or not _redis_client:
        return
    try:
        _redis_client.setex(key, EVAL_CACHE_TTL_SEC, str(score))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Core evaluation functions
# ─────────────────────────────────────────────────────────────────────────────

def score_faithfulness(
    input_text: str,
    output_text: str,
    context: list[str] | None = None,
) -> tuple[float | None, bool]:
    """Returns (score, was_cached). Score None if deepeval unavailable."""
    ctx_str = json.dumps(context) if context else ""
    key = _cache_key(input_text, ctx_str, output_text, "faithfulness")
    cached = _cache_get(key)
    if cached is not None:
        return cached, True

    if not DEEPEVAL_AVAILABLE:
        return None, False

    try:
        metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, model="gpt-4o-mini")
        test_case = LLMTestCase(
            input=input_text,
            actual_output=output_text,
            retrieval_context=context or [],
        )
        metric.measure(test_case)
        score = metric.score
        _cache_set(key, score)
        return score, False
    except Exception as exc:
        logger.error("faithfulness eval failed: %s", exc)
        return None, False


def score_relevance(
    input_text: str,
    output_text: str,
) -> tuple[float | None, bool]:
    key = _cache_key(input_text, None, output_text, "relevance")
    cached = _cache_get(key)
    if cached is not None:
        return cached, True

    if not DEEPEVAL_AVAILABLE:
        return None, False

    try:
        metric = AnswerRelevancyMetric(threshold=RELEVANCE_THRESHOLD, model="gpt-4o-mini")
        test_case = LLMTestCase(input=input_text, actual_output=output_text)
        metric.measure(test_case)
        score = metric.score
        _cache_set(key, score)
        return score, False
    except Exception as exc:
        logger.error("relevance eval failed: %s", exc)
        return None, False


def score_consistency(
    input_text: str,
    outputs: list[str],
) -> float | None:
    """Run same prompt N times, measure variance. High variance → drift."""
    if len(outputs) < 2:
        return None
    scores = []
    for out in outputs:
        score, _ = score_faithfulness(input_text, out)
        if score is not None:
            scores.append(score)
    if len(scores) < 2:
        return None
    var = variance(scores)
    # Return 1 - normalised variance (higher = more consistent)
    return max(0.0, 1.0 - min(var / CONSISTENCY_VAR_MAX, 1.0))


def score_behavioral_compliance(
    input_text: str,
    output_text: str,
    stated_rules: str,
) -> tuple[float | None, bool]:
    """GEval: 'Does the AI response follow its stated rules?'"""
    key = _cache_key(input_text, stated_rules, output_text, "geval_compliance")
    cached = _cache_get(key)
    if cached is not None:
        return cached, True

    if not DEEPEVAL_AVAILABLE:
        return None, False

    try:
        metric = GEval(
            name="BehavioralCompliance",
            criteria=(
                f"The AI has the following stated rules:\n{stated_rules}\n\n"
                "Does the actual output strictly follow all stated rules? "
                "Score 1.0 if perfectly compliant, 0.0 if any rule is violated."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=GEVAL_THRESHOLD,
            model="gpt-4o-mini",
        )
        test_case = LLMTestCase(input=input_text, actual_output=output_text)
        metric.measure(test_case)
        score = metric.score
        _cache_set(key, score)
        return score, False
    except Exception as exc:
        logger.error("geval compliance eval failed: %s", exc)
        return None, False


# ─────────────────────────────────────────────────────────────────────────────
# Batch evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_nodes(
    pipeline_id: str,
    run_id: str,
    nodes: list[dict],
    stated_rules: str | None = None,
) -> BatchEvalResult:
    """
    nodes: list of {name, input_text, output_text, context (optional)}
    Evaluates each node and flags which metrics failed.
    """
    node_results: list[NodeEvalResult] = []

    for node in nodes:
        name       = node.get("name", "unknown")
        input_text = node.get("input_text", "")
        output_text = node.get("output_text", "")
        context    = node.get("context")

        result = NodeEvalResult(node_name=name)
        triggered: list[str] = []

        # Faithfulness
        faith_score, faith_cached = score_faithfulness(input_text, output_text, context)
        result.faithfulness_score = faith_score
        result.cached = faith_cached
        if faith_score is not None and faith_score < FAITHFULNESS_THRESHOLD:
            triggered.append("HALLUCINATION")

        # Relevance
        rel_score, _ = score_relevance(input_text, output_text)
        result.relevance_score = rel_score
        if rel_score is not None and rel_score < RELEVANCE_THRESHOLD:
            triggered.append("QUALITY_DEGRADATION")

        # GEval behavioral compliance (if rules provided)
        if stated_rules:
            geval_score, _ = score_behavioral_compliance(input_text, output_text, stated_rules)
            result.geval_score = geval_score
            if geval_score is not None and geval_score < GEVAL_THRESHOLD:
                triggered.append("COMPLIANCE_DRIFT")

        result.incidents_triggered = triggered
        node_results.append(result)

    return BatchEvalResult(
        pipeline_id=pipeline_id,
        run_id=run_id,
        node_results=node_results,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Trend detection (last DRIFT_WINDOW runs)
# ─────────────────────────────────────────────────────────────────────────────

def detect_score_drift(recent_scores: list[float]) -> list[str]:
    """
    recent_scores: faithfulness scores for last N runs, oldest first.
    Returns list of signal strings if declining trend detected.
    """
    if len(recent_scores) < 3:
        return []

    window = recent_scores[-DRIFT_WINDOW:]
    signals: list[str] = []

    # 3+ consecutive drops
    consecutive_drops = 0
    for i in range(1, len(window)):
        if window[i] < window[i - 1]:
            consecutive_drops += 1
        else:
            consecutive_drops = 0

    if consecutive_drops >= 3:
        delta = window[-1] - window[0]
        signals.append(
            f"COMPLIANCE_DRIFT: faithfulness dropped {delta:.3f} over {len(window)} runs "
            f"({consecutive_drops} consecutive drops)"
        )

    # Overall mean of last half vs first half
    mid = len(window) // 2
    first_half_mean = mean(window[:mid]) if mid else window[0]
    second_half_mean = mean(window[mid:]) if mid else window[-1]
    if second_half_mean < first_half_mean - 0.10:
        signals.append(
            f"COMPLIANCE_DRIFT: mean faithfulness fell from {first_half_mean:.2f} "
            f"to {second_half_mean:.2f} over last {len(window)} runs"
        )

    return signals
