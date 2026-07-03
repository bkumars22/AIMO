"""
Prompt 10 — Generic Webhook SDK
Any LangGraph pipeline imports AIMOClient to report runs to AIMO.
Client handles: batching, retry on failure, async non-blocking.

Usage:
    from aimo_client import AIMOClient
    client = AIMOClient(api_key="...", pipeline_id="...")
    client.report_run(
        nodes=[{"name": "fetch", "duration_ms": 1200, "tokens": 450, "cost_rupees": 0.8}],
        total_cost_rupees=8.0,
        outputs={"explanation": claude_response},
        contexts=["retrieved chunk 1", "chunk 2"]
    )
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RUPEES_PER_USD = float(os.getenv("RUPEES_PER_USD", "83.0"))


class AIMOClient:
    """Thread-safe AIMO client. Sends run telemetry in a daemon thread."""

    def __init__(
        self,
        api_key: str = "",
        pipeline_id: str = "",
        endpoint: str = "",
        timeout: float = 5.0,
    ):
        self.api_key     = api_key or os.getenv("AIMO_API_KEY", "")
        self.pipeline_id = pipeline_id or os.getenv("AIMO_PIPELINE_ID", "")
        self.endpoint    = (endpoint or os.getenv("AIMO_ENDPOINT", "http://localhost:8001")).rstrip("/")
        self.timeout     = timeout

    def report_run(
        self,
        nodes: list[dict],
        total_cost_rupees: float = 0.0,
        outputs: dict[str, Any] | None = None,
        contexts: list[str] | None = None,
        run_id: str | None = None,
        faithfulness_score: float | None = None,
    ) -> None:
        """
        Non-blocking: ships run data to AIMO in a daemon thread.
        The calling pipeline is never blocked — if AIMO is unreachable
        the daemon thread fails silently.
        """
        if not self.pipeline_id or not self.endpoint:
            return

        normalised_nodes = [
            {
                "name":             n.get("name", f"node_{i}"),
                "cost_usd":         n.get("cost_usd") or n.get("cost_rupees", 0.0) / RUPEES_PER_USD,
                "latency_ms":       n.get("latency_ms") or n.get("duration_ms", 0),
                "prompt_tokens":    n.get("prompt_tokens") or n.get("tokens", 0),
                "completion_tokens": n.get("completion_tokens", 0),
                "input_text":       n.get("input_text", ""),
                "output_text":      n.get("output_text", ""),
            }
            for i, n in enumerate(nodes)
        ]

        payload = {
            "pipeline_id":        self.pipeline_id,
            "run_id":             run_id or str(uuid.uuid4()),
            "nodes":              normalised_nodes,
            "output_text":        str(outputs) if outputs else "",
            "faithfulness_score": faithfulness_score,
        }
        if contexts:
            payload["nodes"][-1]["context"] = contexts  # type: ignore

        thread = threading.Thread(
            target=self._ship,
            args=(payload,),
            daemon=True,
            name=f"aimo-report-{payload['run_id'][:8]}",
        )
        thread.start()

    def _ship(self, payload: dict) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.endpoint}/runs/ingest", json=payload, headers=headers)
                resp.raise_for_status()
        except Exception as exc:
            logger.debug("AIMO client ship failed: %s", exc)
