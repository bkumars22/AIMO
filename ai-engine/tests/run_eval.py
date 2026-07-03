"""
Prompt 11 — Golden dataset evaluation runner.
python ai-engine/tests/run_eval.py

Outputs: detection rate, per-case results, exits non-zero if < 95%.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add ai-engine to path when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from detectors.anomaly_detector import (
    BaselineMetrics,
    ThresholdDetector,
    calculate_baseline,
)
from detectors.injection_detector import classify as classify_injection

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
TARGET_RATE  = 0.95


def detect(case: dict) -> str | None:
    """Return detected incident type or None."""
    run      = case["run"]
    baseline = case.get("baseline", {})

    bl = BaselineMetrics(
        pipeline_id="eval",
        run_count=50,
        cost_mean=baseline.get("cost_mean", 0.01),
        cost_std=0.001,
        cost_p95=baseline.get("cost_mean", 0.01) * 2,
        latency_mean=baseline.get("latency_mean", 500),
        latency_std=50,
        latency_p95=baseline.get("latency_mean", 500) * 1.5,
        faithfulness_mean=0.90,
        faithfulness_std=0.05,
        tokens_mean=100,
        tokens_std=10,
    )

    det = ThresholdDetector()
    signals = det.detect(run, bl)

    # Also run injection detector
    text = f"{run.get('input_text', '')} {run.get('output_text', '')}".strip()
    inj = classify_injection(text)
    if inj["detected"]:
        signals.append(type("S", (), {"signal_type": "PROMPT_INJECTION"})())

    if not signals:
        return None

    # Map to incident type
    type_map = {
        "COST_SPIKE": "COST_SPIKE",
        "LATENCY_DEGRADATION": "LATENCY_DEGRADATION",
        "HALLUCINATION": "HALLUCINATION",
        "PROMPT_INJECTION": "PROMPT_INJECTION",
        "COMPLIANCE_DRIFT": "COMPLIANCE_DRIFT",
    }
    for s in signals:
        t = getattr(s, "signal_type", s.get("signal_type", "") if isinstance(s, dict) else "")
        if t in type_map:
            return type_map[t]
    return "ANOMALY"


def main():
    data   = json.loads(DATASET_PATH.read_text())
    cases  = data["cases"]
    passed = 0
    failed = []

    for case in cases:
        expected = case["expected_incident_type"]
        detected = detect(case)
        label    = case["label"]

        if label == "POSITIVE":
            ok = detected == expected
        else:
            ok = detected is None

        if ok:
            passed += 1
        else:
            failed.append({
                "id": case["id"],
                "description": case["description"],
                "expected": expected,
                "detected": detected,
                "label": label,
            })

    rate = passed / len(cases)
    print(f"\n{'=' * 60}")
    print(f"AIMO Golden Dataset Evaluation")
    print(f"{'=' * 60}")
    print(f"Passed: {passed}/{len(cases)} ({rate * 100:.1f}%)")
    print(f"Target: {TARGET_RATE * 100:.0f}%")

    if failed:
        print(f"\nFailed cases ({len(failed)}):")
        for f in failed:
            print(f"  {f['id']} [{f['label']}] expected={f['expected']} detected={f['detected']}")
            print(f"         {f['description']}")

    if rate >= TARGET_RATE:
        print(f"\n✓ PASS — {rate * 100:.1f}% ≥ {TARGET_RATE * 100:.0f}% target")
        sys.exit(0)
    else:
        print(f"\n✗ FAIL — {rate * 100:.1f}% < {TARGET_RATE * 100:.0f}% target")
        sys.exit(1)


if __name__ == "__main__":
    main()
