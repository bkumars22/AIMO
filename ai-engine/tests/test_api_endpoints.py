"""Prompt 11 — FastAPI endpoint tests."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("main.JWT_AVAILABLE", False), \
         patch("main.create_pipeline", return_value="pipe-123"), \
         patch("main.get_pipeline", return_value={"id": "p1", "name": "Test"}), \
         patch("main.list_incidents", return_value=[]), \
         patch("main.get_incident", return_value=None), \
         patch("main.get_pipeline_health_score", return_value=85), \
         patch("main.get_recent_runs", return_value=[]), \
         patch("main.get_pipeline_metrics", return_value=[]), \
         patch("main.recalculate_baseline_in_db", return_value={}), \
         patch("main.resolve_incident_in_db", return_value={}):
        from main import app
        yield TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_payload(self, client: TestClient):
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert data["service"] == "aimo-ai-engine"


class TestPipelineRegister:
    def test_register_returns_pipeline_id(self, client: TestClient):
        resp = client.post("/pipelines/register", json={"name": "MyPipeline"})
        assert resp.status_code == 200
        data = resp.json()
        assert "pipeline_id" in data
        assert "api_key" in data

    def test_register_requires_name(self, client: TestClient):
        resp = client.post("/pipelines/register", json={})
        assert resp.status_code == 422


class TestRunsIngest:
    def test_ingest_returns_202(self, client: TestClient):
        payload = {
            "pipeline_id": "pipe-123",
            "nodes": [
                {"name": "retrieve", "cost_usd": 0.001, "latency_ms": 200,
                 "prompt_tokens": 50, "completion_tokens": 20,
                 "input_text": "q", "output_text": "ctx"},
            ],
            "input_text": "What is AI?",
            "output_text": "AI is artificial intelligence.",
        }
        resp = client.post("/runs/ingest", json=payload)
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True

    def test_ingest_requires_pipeline_id(self, client: TestClient):
        resp = client.post("/runs/ingest", json={"nodes": []})
        assert resp.status_code == 422


class TestIncidentsEndpoint:
    def test_incidents_returns_list(self, client: TestClient):
        resp = client.get("/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_incidents_404_for_unknown(self, client: TestClient):
        resp = client.get("/incidents/nonexistent-id")
        assert resp.status_code == 404


class TestPipelineHealth:
    def test_health_returns_score(self, client: TestClient):
        resp = client.get("/pipelines/p1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data
        assert 0 <= data["health_score"] <= 100

    def test_unknown_pipeline_404(self, client: TestClient):
        with patch("main.get_pipeline", return_value=None):
            resp = client.get("/pipelines/unknown/health")
        assert resp.status_code == 404


class TestAuthentication:
    def test_auth_required_on_incidents_when_jwt_enabled(self):
        with patch("main.JWT_AVAILABLE", True):
            from main import app
            c = TestClient(app)
            resp = c.get("/incidents")
            assert resp.status_code == 401
