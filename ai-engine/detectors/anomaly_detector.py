"""
Prompt 9 — IsolationForest Baseline Engine
ThresholdDetector → AnomalyDetector → SHAP chain
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# ── Thresholds (overridden by .env) ──────────────────────────────────────────
import os
COST_SPIKE_MULTIPLIER   = float(os.getenv("COST_SPIKE_MULTIPLIER", "3.0"))
LATENCY_SPIKE_MULTIPLIER = float(os.getenv("LATENCY_SPIKE_MULTIPLIER", "5.0"))
HALLUCINATION_THRESHOLD  = float(os.getenv("HALLUCINATION_THRESHOLD", "0.70"))
FORBIDDEN_WORDS          = ["ignore instructions", "jailbreak", "DAN mode", "god mode"]
ISOLATION_CONTAMINATION  = float(os.getenv("ISOLATION_CONTAMINATION", "0.10"))
MIN_RUNS_FOR_BASELINE    = 10  # need at least this many runs before IsolationForest


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BaselineMetrics:
    pipeline_id: str
    run_count: int
    cost_mean: float = 0.0
    cost_std: float  = 0.0
    cost_p95: float  = 0.0
    latency_mean: float = 0.0
    latency_std: float  = 0.0
    latency_p95: float  = 0.0
    faithfulness_mean: float = 1.0
    faithfulness_std: float  = 0.0
    tokens_mean: float = 0.0
    tokens_std: float  = 0.0
    node_baselines: dict = field(default_factory=dict)


@dataclass
class AnomalySignal:
    signal_type: str           # COST_SPIKE | LATENCY | HALLUCINATION | INJECTION | DRIFT
    severity: str              # P0 | P1 | P2 | P3
    score: float               # isolation score or threshold ratio
    feature: str               # which metric triggered
    value: float               # actual value
    baseline_value: float      # expected value
    explanation: str           # human-readable SHAP-style explanation
    source: str                # threshold | isolation_forest | drift


# ─────────────────────────────────────────────────────────────────────────────
# 1. BaselineCalculator
# ─────────────────────────────────────────────────────────────────────────────

class BaselineCalculator:
    """Computes baseline stats from last N runs for a pipeline."""

    def calculate(self, runs: list[dict], pipeline_id: str) -> BaselineMetrics:
        """
        runs: list of dicts with keys:
          cost_usd, latency_ms, prompt_tokens, completion_tokens,
          faithfulness_score (optional), nodes (list of node dicts)
        """
        if not runs:
            return BaselineMetrics(pipeline_id=pipeline_id, run_count=0)

        costs       = [r.get("cost_usd", 0.0) for r in runs]
        latencies   = [r.get("latency_ms", 0) for r in runs]
        tokens      = [r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in runs]
        faithfulness = [r["faithfulness_score"] for r in runs if r.get("faithfulness_score") is not None]

        def _p95(vals: list) -> float:
            if not vals:
                return 0.0
            idx = int(len(vals) * 0.95)
            return sorted(vals)[min(idx, len(vals) - 1)]

        def _safe_std(vals: list) -> float:
            return stdev(vals) if len(vals) > 1 else 0.0

        node_baselines: dict = {}
        all_nodes: dict[str, list] = {}
        for run in runs:
            for node in run.get("nodes", []):
                name = node.get("name", "unknown")
                all_nodes.setdefault(name, []).append(node)
        for name, node_runs in all_nodes.items():
            node_costs     = [n.get("cost_usd", 0.0) for n in node_runs]
            node_latencies = [n.get("latency_ms", 0) for n in node_runs]
            node_baselines[name] = {
                "cost_mean": mean(node_costs),
                "latency_mean": mean(node_latencies),
            }

        return BaselineMetrics(
            pipeline_id=pipeline_id,
            run_count=len(runs),
            cost_mean=mean(costs),
            cost_std=_safe_std(costs),
            cost_p95=_p95(costs),
            latency_mean=mean(latencies),
            latency_std=_safe_std(latencies),
            latency_p95=_p95(latencies),
            faithfulness_mean=mean(faithfulness) if faithfulness else 1.0,
            faithfulness_std=_safe_std(faithfulness) if faithfulness else 0.0,
            tokens_mean=mean(tokens),
            tokens_std=_safe_std(tokens),
            node_baselines=node_baselines,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. ThresholdDetector  (runs first — catches obvious P0s instantly)
# ─────────────────────────────────────────────────────────────────────────────

class ThresholdDetector:
    """Rule-based fast detection for obvious incidents."""

    def detect(self, run: dict, baseline: BaselineMetrics) -> list[AnomalySignal]:
        signals: list[AnomalySignal] = []

        cost     = run.get("cost_usd", 0.0)
        latency  = run.get("latency_ms", 0)
        faith    = run.get("faithfulness_score")
        output   = run.get("output_text", "")

        # Cost spike
        if baseline.cost_mean > 0 and cost > COST_SPIKE_MULTIPLIER * baseline.cost_mean:
            ratio = cost / baseline.cost_mean
            signals.append(AnomalySignal(
                signal_type="COST_SPIKE",
                severity="P0" if ratio > 10 else "P1" if ratio > 5 else "P2",
                score=ratio,
                feature="cost_usd",
                value=cost,
                baseline_value=baseline.cost_mean,
                explanation=f"Cost ${cost:.4f} is {ratio:.1f}× the {baseline.run_count}-run baseline of ${baseline.cost_mean:.4f}",
                source="threshold",
            ))

        # Latency spike
        if baseline.latency_mean > 0 and latency > LATENCY_SPIKE_MULTIPLIER * baseline.latency_mean:
            ratio = latency / baseline.latency_mean
            signals.append(AnomalySignal(
                signal_type="LATENCY_DEGRADATION",
                severity="P0" if ratio > 10 else "P1" if ratio > 5 else "P2",
                score=ratio,
                feature="latency_ms",
                value=latency,
                baseline_value=baseline.latency_mean,
                explanation=f"Latency {latency}ms is {ratio:.1f}× the baseline of {baseline.latency_mean:.0f}ms",
                source="threshold",
            ))

        # Hallucination
        if faith is not None and faith < HALLUCINATION_THRESHOLD:
            signals.append(AnomalySignal(
                signal_type="HALLUCINATION",
                severity="P0" if faith < 0.25 else "P1" if faith < 0.40 else "P2",
                score=1.0 - faith,
                feature="faithfulness_score",
                value=faith,
                baseline_value=baseline.faithfulness_mean,
                explanation=f"Faithfulness {faith:.2f} is below threshold {HALLUCINATION_THRESHOLD}",
                source="threshold",
            ))

        # Forbidden pattern in output
        output_lower = output.lower()
        for word in FORBIDDEN_WORDS:
            if word in output_lower:
                signals.append(AnomalySignal(
                    signal_type="PROMPT_INJECTION",
                    severity="P0",
                    score=1.0,
                    feature="output_text",
                    value=1.0,
                    baseline_value=0.0,
                    explanation=f"Forbidden pattern detected in output: '{word}'",
                    source="threshold",
                ))
                break

        return signals


# ─────────────────────────────────────────────────────────────────────────────
# 3. AnomalyDetector  (IsolationForest — catches subtle patterns)
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyDetector:
    """IsolationForest anomaly detection trained on historical runs."""

    def __init__(self):
        self._models: dict[str, IsolationForest] = {}

    def _feature_vector(self, run: dict) -> list[float]:
        return [
            run.get("cost_usd", 0.0),
            run.get("latency_ms", 0) / 1000.0,       # normalise to seconds
            (run.get("prompt_tokens", 0) + run.get("completion_tokens", 0)) / 1000.0,
            run.get("faithfulness_score") or 1.0,
            float(len(run.get("nodes", []))),
        ]

    def train(self, pipeline_id: str, historical_runs: list[dict]) -> bool:
        """Train or retrain the model for a pipeline. Returns False if too few runs."""
        if len(historical_runs) < MIN_RUNS_FOR_BASELINE:
            logger.warning(
                "pipeline %s has only %d runs — need %d for IsolationForest",
                pipeline_id, len(historical_runs), MIN_RUNS_FOR_BASELINE,
            )
            return False

        X = np.array([self._feature_vector(r) for r in historical_runs])
        model = IsolationForest(contamination=ISOLATION_CONTAMINATION, random_state=42)
        model.fit(X)
        self._models[pipeline_id] = model
        logger.info("IsolationForest trained for pipeline %s on %d runs", pipeline_id, len(historical_runs))
        return True

    def score(self, pipeline_id: str, run: dict) -> Optional[AnomalySignal]:
        """Returns an AnomalySignal if the run is anomalous, else None."""
        model = self._models.get(pipeline_id)
        if model is None:
            return None

        x = np.array([self._feature_vector(run)])
        prediction = model.predict(x)[0]      # 1 = normal, -1 = anomaly
        raw_score  = model.score_samples(x)[0] # lower = more anomalous

        if prediction == -1:
            explanation = _shap_explain(run, raw_score)
            return AnomalySignal(
                signal_type="ANOMALY",
                severity="P2",
                score=abs(raw_score),
                feature="composite",
                value=raw_score,
                baseline_value=0.0,
                explanation=explanation,
                source="isolation_forest",
            )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. SHAP Explainer  (feature attribution without full SHAP library)
# ─────────────────────────────────────────────────────────────────────────────

def _shap_explain(run: dict, iso_score: float) -> str:
    """
    Lightweight SHAP-style explanation by comparing feature z-scores.
    Full SHAP integration is a Phase 2 enhancement.
    """
    features = {
        "cost_usd":   run.get("cost_usd", 0.0),
        "latency_ms": run.get("latency_ms", 0) / 1000.0,
        "tokens":     (run.get("prompt_tokens", 0) + run.get("completion_tokens", 0)) / 1000.0,
        "faithfulness": run.get("faithfulness_score") or 1.0,
    }
    # Rank features by how far from "normal" they look (heuristic)
    sorted_feats = sorted(features.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top = sorted_feats[:2]
    parts = [f"{feat}={val:.3f}" for feat, val in top]
    return (
        f"IsolationForest anomaly score {iso_score:.3f} "
        f"(most anomalous features: {', '.join(parts)})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. DriftDetector  (linear regression on 14-day metric trends)
# ─────────────────────────────────────────────────────────────────────────────

class DriftDetector:
    """Detects slow-burn metric drift over 14 days using linear regression."""

    def detect(self, daily_averages: list[dict]) -> list[AnomalySignal]:
        """
        daily_averages: list of {date, faithfulness_mean, cost_mean, latency_mean}
        sorted oldest → newest
        """
        if len(daily_averages) < 3:
            return []

        signals: list[AnomalySignal] = []
        n = len(daily_averages)
        x = np.arange(n, dtype=float)

        for metric, signal_type in [
            ("faithfulness_mean", "COMPLIANCE_DRIFT"),
            ("cost_mean", "COST_TREND"),
            ("latency_mean", "LATENCY_TREND"),
        ]:
            y = np.array([d.get(metric, 0.0) for d in daily_averages], dtype=float)
            slope = float(np.polyfit(x, y, 1)[0])

            # Faithfulness declining or cost/latency rising are bad
            is_bad = (
                (metric == "faithfulness_mean" and slope < -0.01) or
                (metric != "faithfulness_mean" and slope > 0.05)
            )
            if is_bad:
                direction = "declining" if slope < 0 else "rising"
                signals.append(AnomalySignal(
                    signal_type=signal_type,
                    severity="P2",
                    score=abs(slope),
                    feature=metric,
                    value=y[-1],
                    baseline_value=y[0],
                    explanation=f"{metric} is {direction} at {slope:+.4f}/day over {n} days",
                    source="drift_detector",
                ))

        return signals


# ─────────────────────────────────────────────────────────────────────────────
# Public orchestration helper
# ─────────────────────────────────────────────────────────────────────────────

_baseline_calc  = BaselineCalculator()
_threshold_det  = ThresholdDetector()
_anomaly_det    = AnomalyDetector()
_drift_det      = DriftDetector()


def run_full_detection(
    run: dict,
    baseline: BaselineMetrics,
    historical_runs: list[dict],
    daily_averages: list[dict],
) -> list[AnomalySignal]:
    """
    Full detection chain: ThresholdDetector → AnomalyDetector → DriftDetector.
    Returns deduplicated list of AnomalySignals.
    """
    signals: list[AnomalySignal] = []

    # Fast rule-based check
    signals.extend(_threshold_det.detect(run, baseline))

    # IsolationForest (train if not already trained)
    if baseline.pipeline_id not in _anomaly_det._models:
        _anomaly_det.train(baseline.pipeline_id, historical_runs)
    iso_signal = _anomaly_det.score(baseline.pipeline_id, run)
    if iso_signal:
        signals.append(iso_signal)

    # Drift
    signals.extend(_drift_det.detect(daily_averages))

    return signals


def calculate_baseline(runs: list[dict], pipeline_id: str) -> BaselineMetrics:
    return _baseline_calc.calculate(runs, pipeline_id)
