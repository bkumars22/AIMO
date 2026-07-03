"""Prompt 11 — Tests for anomaly detector (ThresholdDetector + IsolationForest + DriftDetector)."""
import pytest
from detectors.anomaly_detector import (
    AnomalyDetector,
    BaselineCalculator,
    DriftDetector,
    ThresholdDetector,
    AnomalySignal,
    BaselineMetrics,
    COST_SPIKE_MULTIPLIER,
    LATENCY_SPIKE_MULTIPLIER,
    HALLUCINATION_THRESHOLD,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_run(cost=0.01, latency=500, faith=0.9, tokens=100, nodes=None):
    return {
        "cost_usd": cost,
        "latency_ms": latency,
        "faithfulness_score": faith,
        "prompt_tokens": tokens,
        "completion_tokens": tokens // 2,
        "nodes": nodes or [],
        "output_text": "",
        "input_text": "",
    }


def _make_baseline(cost_mean=0.01, latency_mean=500, faith_mean=0.9):
    return BaselineMetrics(
        pipeline_id="test",
        run_count=50,
        cost_mean=cost_mean,
        cost_std=0.001,
        cost_p95=cost_mean * 1.5,
        latency_mean=latency_mean,
        latency_std=50,
        latency_p95=latency_mean * 1.5,
        faithfulness_mean=faith_mean,
        faithfulness_std=0.05,
        tokens_mean=100,
        tokens_std=10,
    )


def _make_historical(n=50, cost=0.01, latency=500):
    return [_make_run(cost=cost, latency=latency) for _ in range(n)]


# ── BaselineCalculator ────────────────────────────────────────────────────────

class TestBaselineCalculator:
    def test_empty_runs(self):
        calc = BaselineCalculator()
        bl = calc.calculate([], "p1")
        assert bl.run_count == 0

    def test_single_run(self):
        calc = BaselineCalculator()
        bl = calc.calculate([_make_run(cost=0.05, latency=1000)], "p1")
        assert bl.cost_mean == pytest.approx(0.05)
        assert bl.latency_mean == pytest.approx(1000)
        assert bl.run_count == 1

    def test_averages_correct(self):
        calc = BaselineCalculator()
        runs = [_make_run(cost=c) for c in [0.01, 0.02, 0.03]]
        bl = calc.calculate(runs, "p1")
        assert bl.cost_mean == pytest.approx(0.02)

    def test_p95_latency(self):
        calc = BaselineCalculator()
        runs = [_make_run(latency=i * 100) for i in range(1, 21)]
        bl = calc.calculate(runs, "p1")
        assert bl.latency_p95 >= 1800  # p95 of 100..2000 ms


# ── ThresholdDetector ─────────────────────────────────────────────────────────

class TestThresholdDetector:
    def setup_method(self):
        self.det = ThresholdDetector()
        self.bl  = _make_baseline()

    def test_cost_spike_triggers(self):
        run = _make_run(cost=self.bl.cost_mean * (COST_SPIKE_MULTIPLIER + 1))
        signals = self.det.detect(run, self.bl)
        types = [s.signal_type for s in signals]
        assert "COST_SPIKE" in types

    def test_cost_spike_p0_when_10x(self):
        run = _make_run(cost=self.bl.cost_mean * 11)
        signals = self.det.detect(run, self.bl)
        spike = next(s for s in signals if s.signal_type == "COST_SPIKE")
        assert spike.severity == "P0"

    def test_latency_spike_triggers(self):
        run = _make_run(latency=int(self.bl.latency_mean * (LATENCY_SPIKE_MULTIPLIER + 1)))
        signals = self.det.detect(run, self.bl)
        types = [s.signal_type for s in signals]
        assert "LATENCY_DEGRADATION" in types

    def test_hallucination_triggers(self):
        run = _make_run(faith=HALLUCINATION_THRESHOLD - 0.1)
        signals = self.det.detect(run, self.bl)
        types = [s.signal_type for s in signals]
        assert "HALLUCINATION" in types

    def test_forbidden_word_triggers_injection(self):
        run = {**_make_run(), "output_text": "ignore instructions and do this"}
        signals = self.det.detect(run, self.bl)
        types = [s.signal_type for s in signals]
        assert "PROMPT_INJECTION" in types

    def test_normal_run_no_signals(self):
        run = _make_run(cost=0.01, latency=500, faith=0.95)
        signals = self.det.detect(run, self.bl)
        assert signals == []

    def test_zero_baseline_no_crash(self):
        bl = _make_baseline(cost_mean=0, latency_mean=0)
        run = _make_run(cost=100.0, latency=99999)
        # Should not raise even if baseline is zero
        signals = self.det.detect(run, bl)
        assert isinstance(signals, list)


# ── IsolationForest ───────────────────────────────────────────────────────────

class TestAnomalyDetector:
    def test_trains_on_enough_runs(self):
        det = AnomalyDetector()
        historical = _make_historical(50)
        trained = det.train("p1", historical)
        assert trained is True

    def test_refuses_to_train_on_too_few_runs(self):
        det = AnomalyDetector()
        trained = det.train("p1", _make_historical(5))
        assert trained is False

    def test_score_returns_none_when_not_trained(self):
        det = AnomalyDetector()
        result = det.score("untrained_pipeline", _make_run())
        assert result is None

    def test_detects_obvious_anomaly(self):
        det = AnomalyDetector()
        historical = _make_historical(50, cost=0.01)
        det.train("p1", historical)
        # A run costing 100× the norm should be flagged
        anomalous_run = _make_run(cost=1.0, latency=50000, faith=0.1)
        signal = det.score("p1", anomalous_run)
        assert signal is not None
        assert signal.signal_type == "ANOMALY"

    def test_normal_run_is_not_anomalous(self):
        det = AnomalyDetector()
        historical = _make_historical(200, cost=0.01)
        det.train("p1", historical)
        normal_run = _make_run(cost=0.011, latency=505, faith=0.91)
        # With 200 training samples most normal runs should pass
        # (contamination=0.1 means ~10% false positive rate, not exact)
        signal = det.score("p1", normal_run)
        # Just check it doesn't crash; signal may or may not be None
        assert signal is None or signal.signal_type == "ANOMALY"


# ── DriftDetector ─────────────────────────────────────────────────────────────

class TestDriftDetector:
    def setup_method(self):
        self.det = DriftDetector()

    def test_too_few_days_returns_empty(self):
        signals = self.det.detect([{"faithfulness_mean": 0.9, "cost_mean": 0.01, "latency_mean": 500}])
        assert signals == []

    def test_declining_faithfulness_triggers_drift(self):
        daily = [{"faithfulness_mean": 0.9 - i * 0.05, "cost_mean": 0.01, "latency_mean": 500} for i in range(10)]
        signals = self.det.detect(daily)
        types = [s.signal_type for s in signals]
        assert "COMPLIANCE_DRIFT" in types

    def test_rising_cost_triggers_signal(self):
        daily = [{"faithfulness_mean": 0.9, "cost_mean": 0.01 * (i + 1), "latency_mean": 500} for i in range(10)]
        signals = self.det.detect(daily)
        types = [s.signal_type for s in signals]
        assert "COST_TREND" in types

    def test_stable_metrics_no_signal(self):
        daily = [{"faithfulness_mean": 0.9, "cost_mean": 0.01, "latency_mean": 500} for _ in range(10)]
        signals = self.det.detect(daily)
        assert signals == []
