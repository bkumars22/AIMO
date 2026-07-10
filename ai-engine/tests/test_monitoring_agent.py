"""Prompt 11 — Tests for monitoring agent nodes (with DB + Claude mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

# ── Stub external dependencies before importing agent ────────────────────────
import sys
import types

# Stub LangGraph
lg_mod = types.ModuleType("langgraph")
lg_mod.graph = types.ModuleType("langgraph.graph")  # type: ignore
lg_mod.graph.StateGraph = MagicMock()  # type: ignore
lg_mod.graph.END = object()            # type: ignore
sys.modules.setdefault("langgraph", lg_mod)
sys.modules.setdefault("langgraph.graph", lg_mod.graph)  # type: ignore

# Stub langchain_anthropic
lca_mod = types.ModuleType("langchain_anthropic")
lca_mod.ChatAnthropic = MagicMock()  # type: ignore
sys.modules.setdefault("langchain_anthropic", lca_mod)

from agents.monitoring_agent import (
    collect_metrics,
    detect_anomalies,
    classify_incidents,
    generate_root_cause,
    send_alerts,
    store_and_update,
    AIMOState,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _initial_state(**kwargs) -> AIMOState:
    base: AIMOState = {
        "pipeline_id":        "test-pipeline",
        "run_id":             "run-123",
        "run_data":           {},
        "metrics":            {},
        "baseline":           {},
        "anomalies":          [],
        "incidents":          [],
        "enriched_incidents": [],
        "alerts_sent":        [],
        "saved_ids":          [],
        "errors":             [],
    }
    return {**base, **kwargs}


def _run_data(cost=0.01, latency=500, faith=0.9):
    return {
        "run_id": "run-123",
        "input_text":  "What is photosynthesis?",
        "output_text": "Photosynthesis converts CO2 and water into glucose.",
        "faithfulness_score": faith,
        "nodes": [
            {"name": "retrieve",  "cost_usd": cost * 0.2, "latency_ms": latency // 5,
             "prompt_tokens": 50, "completion_tokens": 10, "input_text": "Q", "output_text": "ctx"},
            {"name": "generate",  "cost_usd": cost * 0.8, "latency_ms": latency * 4 // 5,
             "prompt_tokens": 150, "completion_tokens": 80, "input_text": "Q+ctx",
             "output_text": "Photosynthesis converts CO2 and water into glucose."},
        ],
    }


# ── collect_metrics ───────────────────────────────────────────────────────────

class TestCollectMetrics:
    def test_extracts_total_cost(self):
        state = _initial_state(run_data=_run_data(cost=0.10))
        result = collect_metrics(state)
        assert result["metrics"]["cost_usd"] == pytest.approx(0.10)

    def test_extracts_node_count(self):
        state = _initial_state(run_data=_run_data())
        result = collect_metrics(state)
        assert result["metrics"]["node_count"] == 2

    def test_crash_does_not_propagate(self):
        state = _initial_state(run_data=None)  # will cause AttributeError
        result = collect_metrics(state)
        assert isinstance(result["errors"], list)
        assert any("collect_metrics" in str(e) for e in result["errors"])

    def test_node_metrics_contains_names(self):
        state = _initial_state(run_data=_run_data())
        result = collect_metrics(state)
        names = [n["name"] for n in result["metrics"]["node_metrics"]]
        assert "retrieve" in names
        assert "generate" in names


# ── detect_anomalies ──────────────────────────────────────────────────────────

class TestDetectAnomalies:
    @patch("agents.monitoring_agent.get_recent_runs", return_value=[])
    @patch("agents.monitoring_agent.get_daily_averages", return_value=[])
    def test_returns_anomalies_list(self, mock_avgs, mock_runs):
        state = _initial_state(
            metrics={
                "cost_usd": 0.01, "latency_ms": 500,
                "faithfulness_score": 0.9, "input_text": "", "output_text": "",
                "prompt_tokens": 100, "completion_tokens": 50,
                "nodes": [], "node_metrics": [], "node_count": 0,
            }
        )
        result = detect_anomalies(state)
        assert isinstance(result["anomalies"], list)

    @patch("agents.monitoring_agent.get_recent_runs", return_value=[])
    @patch("agents.monitoring_agent.get_daily_averages", return_value=[])
    def test_db_error_does_not_crash(self, mock_avgs, mock_runs):
        mock_runs.side_effect = Exception("DB down")
        state = _initial_state(metrics={"cost_usd": 0.01, "latency_ms": 500,
                                         "faithfulness_score": 0.9, "input_text": "",
                                         "output_text": "", "nodes": [], "node_metrics": [],
                                         "prompt_tokens": 0, "completion_tokens": 0, "node_count": 0})
        result = detect_anomalies(state)
        assert isinstance(result, dict)  # must not raise


# ── classify_incidents ────────────────────────────────────────────────────────

class TestClassifyIncidents:
    def test_cost_spike_signal_creates_incident(self):
        signal = {
            "signal_type": "COST_SPIKE", "severity": "P2",
            "score": 4.5, "feature": "cost_usd",
            "value": 0.09, "baseline_value": 0.01,
            "explanation": "Cost 9× baseline", "source": "threshold",
        }
        state = _initial_state(anomalies=[signal], metrics={}, run_data=_run_data())
        with patch("agents.monitoring_agent.evaluate_nodes") as mock_eval:
            mock_eval.return_value = MagicMock(node_results=[])
            result = classify_incidents(state)
        assert len(result["incidents"]) >= 1
        inc = result["incidents"][0]
        assert inc["incident_type"] == "COST_SPIKE"
        assert inc["severity"] == "P2"

    def test_injection_signal_is_p0(self):
        signal = {
            "signal_type": "PROMPT_INJECTION", "severity": "P0",
            "score": 1.0, "feature": "input_text", "value": 1.0,
            "baseline_value": 0.0, "explanation": "DAN mode detected", "source": "injection_detector",
        }
        state = _initial_state(anomalies=[signal], metrics={}, run_data=_run_data())
        with patch("agents.monitoring_agent.evaluate_nodes") as mock_eval:
            mock_eval.return_value = MagicMock(node_results=[])
            result = classify_incidents(state)
        assert any(i["severity"] == "P0" for i in result["incidents"])

    def test_empty_anomalies_produces_no_incidents(self):
        state = _initial_state(anomalies=[], metrics={}, run_data=_run_data())
        with patch("agents.monitoring_agent.evaluate_nodes") as mock_eval:
            mock_eval.return_value = MagicMock(node_results=[])
            result = classify_incidents(state)
        assert result["incidents"] == []

    def test_hallucination_gets_aipq_ids_when_mapped(self):
        state = _initial_state(anomalies=[], metrics={"node_metrics": [{"name": "teach_socratically"}]},
                                run_data=_run_data(), pipeline_id="aria-prod")
        node_result = MagicMock(
            node_name="teach_socratically", incidents_triggered=["HALLUCINATION"],
            faithfulness_score=0.5, relevance_score=0.6, geval_score=0.4,
        )
        with patch("agents.monitoring_agent.evaluate_nodes") as mock_eval, \
             patch("agents.monitoring_agent.get_aipq_mapping",
                   return_value={"project_id": 1, "prompt_name": "aria_socratic_system"}) as mock_map:
            mock_eval.return_value = MagicMock(node_results=[node_result])
            result = classify_incidents(state)
        mock_map.assert_called_once_with("aria-prod", "teach_socratically")
        inc = result["incidents"][0]
        assert inc["evidence"]["aipq_project_id"] == 1
        assert inc["evidence"]["aipq_prompt_name"] == "aria_socratic_system"

    def test_hallucination_without_mapping_has_no_aipq_ids(self):
        state = _initial_state(anomalies=[], metrics={"node_metrics": [{"name": "generate"}]},
                                run_data=_run_data(), pipeline_id="unmapped-pipeline")
        node_result = MagicMock(
            node_name="generate", incidents_triggered=["HALLUCINATION"],
            faithfulness_score=0.5, relevance_score=0.6, geval_score=0.4,
        )
        with patch("agents.monitoring_agent.evaluate_nodes") as mock_eval, \
             patch("agents.monitoring_agent.get_aipq_mapping", return_value=None):
            mock_eval.return_value = MagicMock(node_results=[node_result])
            result = classify_incidents(state)
        inc = result["incidents"][0]
        assert "aipq_project_id" not in inc["evidence"]
        assert "aipq_prompt_name" not in inc["evidence"]

    def test_cost_spike_node_result_does_not_get_aipq_ids(self):
        state = _initial_state(anomalies=[], metrics={"node_metrics": [{"name": "teach_socratically"}]},
                                run_data=_run_data(), pipeline_id="aria-prod")
        node_result = MagicMock(
            node_name="teach_socratically", incidents_triggered=["COST_SPIKE"],
            faithfulness_score=0.9, relevance_score=0.9, geval_score=0.9,
        )
        with patch("agents.monitoring_agent.evaluate_nodes") as mock_eval, \
             patch("agents.monitoring_agent.get_aipq_mapping") as mock_map:
            mock_map.return_value = {"project_id": 1, "prompt_name": "aria_socratic_system"}
            mock_eval.return_value = MagicMock(node_results=[node_result])
            result = classify_incidents(state)
        mock_map.assert_not_called()
        inc = result["incidents"][0]
        assert "aipq_project_id" not in inc["evidence"]


# ── generate_root_cause ───────────────────────────────────────────────────────

class TestGenerateRootCause:
    def test_stub_root_cause_when_llm_disabled(self):
        inc = {
            "id": "i1", "pipeline_id": "p1", "run_id": "r1",
            "incident_type": "HALLUCINATION", "severity": "P1",
            "title": "Test", "evidence": {}, "status": "OPEN",
        }
        state = _initial_state(incidents=[inc])
        with patch("agents.monitoring_agent.LLM_AVAILABLE", False):
            result = generate_root_cause(state)
        assert len(result["enriched_incidents"]) == 1
        assert result["enriched_incidents"][0]["root_cause"] is not None

    def test_llm_error_does_not_crash(self):
        inc = {
            "id": "i1", "pipeline_id": "p1", "run_id": "r1",
            "incident_type": "COST_SPIKE", "severity": "P2",
            "title": "Test", "evidence": {}, "status": "OPEN",
        }
        state = _initial_state(incidents=[inc])
        with patch("agents.monitoring_agent.LLM_AVAILABLE", True), \
             patch("agents.monitoring_agent._llm") as mock_llm:
            mock_llm.invoke.side_effect = Exception("API error")
            result = generate_root_cause(state)
        assert len(result["enriched_incidents"]) == 1  # must not lose incident


# ── send_alerts ───────────────────────────────────────────────────────────────

class TestSendAlerts:
    @patch("agents.monitoring_agent.dispatch", return_value={"ok": True})
    def test_p0_goes_to_slack(self, mock_dispatch):
        inc = {
            "id": "i1", "pipeline_id": "p1", "run_id": "r1",
            "incident_type": "PROMPT_INJECTION", "severity": "P0",
            "title": "Injection", "evidence": {}, "status": "OPEN",
            "root_cause": "Jailbreak attempt",
        }
        state = _initial_state(enriched_incidents=[inc])
        result = send_alerts(state)
        assert any(a["channel"] == "slack" for a in result["alerts_sent"])

    @patch("agents.monitoring_agent.dispatch", return_value={"ok": True})
    def test_p2_goes_to_email(self, mock_dispatch):
        inc = {
            "id": "i2", "pipeline_id": "p1", "run_id": "r1",
            "incident_type": "COST_SPIKE", "severity": "P2",
            "title": "Cost spike", "evidence": {}, "status": "OPEN",
        }
        state = _initial_state(enriched_incidents=[inc])
        result = send_alerts(state)
        assert any(a["channel"] == "email" for a in result["alerts_sent"])

    @patch("agents.monitoring_agent.dispatch", side_effect=Exception("Slack down"))
    def test_alert_failure_does_not_stop_pipeline(self, mock_dispatch):
        inc = {
            "id": "i3", "pipeline_id": "p1", "run_id": "r1",
            "incident_type": "HALLUCINATION", "severity": "P1",
            "title": "Hallucination", "evidence": {}, "status": "OPEN",
        }
        state = _initial_state(enriched_incidents=[inc])
        result = send_alerts(state)
        # Pipeline must continue — errors go into state["errors"]
        assert isinstance(result, dict)


# ── State passes between nodes ────────────────────────────────────────────────

class TestStatePassthrough:
    @patch("agents.monitoring_agent.get_recent_runs", return_value=[])
    @patch("agents.monitoring_agent.get_daily_averages", return_value=[])
    @patch("agents.monitoring_agent.evaluate_nodes")
    def test_pipeline_id_preserved_through_nodes(self, mock_eval, mock_avgs, mock_runs):
        mock_eval.return_value = MagicMock(node_results=[])
        state = _initial_state(run_data=_run_data())
        state = collect_metrics(state)
        state = detect_anomalies(state)
        assert state["pipeline_id"] == "test-pipeline"
