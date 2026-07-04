"""
AIMO Python SDK — ai-engine/sdk/aimo_client.py

Reusable async client for the AIMO AI Incident Management & Observability
platform. Designed for drop-in use across multiple projects:

  • QAIP  — QA Intelligence Platform (LangGraph test-generation agent)
  • SCIP  — Supply Chain Intelligence Platform (IsolationForest + Claude)
  • ARIA  — AI Research Intelligence Assistant (Socratic teaching agent)
  • Any other LangGraph / AI pipeline

Usage:
    import asyncio, os
    from aimo_client import AIMOClient

    # One-time pipeline registration (run once, save the output to .env)
    async def register():
        async with AIMOClient(base_url="http://localhost:8001") as client:
            await client.register_pipeline(
                name="QAIP Test Generator",
                description="LangGraph agent that generates test cases from Jira",
                pipeline_type="LangGraph-RAG",
                owner_email="me@example.com",
            )

    # Reporting a run (call after every pipeline execution)
    async def main():
        client = AIMOClient(
            api_key=os.getenv("AIMO_API_KEY"),
            pipeline_id=os.getenv("AIMO_PIPELINE_ID"),
            base_url=os.getenv("AIMO_BASE_URL", "http://localhost:8001"),
        )
        await client.report_run(
            nodes=[
                {"name": "fetch_jira",     "duration_ms": 1200, "tokens": 450,  "cost_rupees": 0.8},
                {"name": "generate_tests", "duration_ms": 8000, "tokens": 800,  "cost_rupees": 5.2},
            ],
            total_cost_rupees=8.0,
            faithfulness_score=0.94,
            outputs={"report": "Generated 12 test cases"},
        )
        await client.close()

Design principles:
  • report_run is non-blocking — uses asyncio.create_task, returns immediately
  • Retries 3× with exponential backoff (1 s, 2 s, 4 s) before giving up
  • Silent fail — AIMO errors NEVER crash or slow down the actual pipeline
  • Rupee→USD conversion built-in (83 INR = 1 USD default, overridable via env)
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
RUPEES_PER_USD:  float = float(os.getenv("RUPEES_PER_USD", "83.0"))
_MAX_RETRIES:    int   = 3
_RETRY_BASE_SEC: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# AIMOClient
# ─────────────────────────────────────────────────────────────────────────────

class AIMOClient:
    """Async AIMO client. Thread-safe. Shareable across coroutines."""

    def __init__(
        self,
        api_key:     str   = "",
        pipeline_id: str   = "",
        base_url:    str   = "",
        timeout:     float = 5.0,
    ) -> None:
        """
        Args:
            api_key:     AIMO API key returned by register_pipeline.
                         Falls back to AIMO_API_KEY env var.
            pipeline_id: UUID returned by register_pipeline.
                         Falls back to AIMO_PIPELINE_ID env var.
            base_url:    AIMO AI-engine base URL (no trailing slash).
                         Falls back to AIMO_BASE_URL env var, then localhost:8001.
            timeout:     Per-request timeout in seconds.
        """
        self.api_key     = api_key     or os.getenv("AIMO_API_KEY",     "")
        self.pipeline_id = pipeline_id or os.getenv("AIMO_PIPELINE_ID", "")
        self.base_url    = (base_url   or os.getenv("AIMO_BASE_URL", "http://localhost:8001")).rstrip("/")
        self._client     = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        # Task set prevents background tasks from being garbage-collected mid-flight
        self._tasks: set[asyncio.Task[None]] = set()

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "AIMOClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Drain all in-flight background tasks then close the HTTP session."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._client.aclose()

    # ── Auth header ───────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    # ── Internal HTTP ─────────────────────────────────────────────────────────

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        return await self._client.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self._headers(),
        )

    async def _ship_with_retry(self, path: str, payload: dict[str, Any]) -> None:
        """POST with exponential-backoff retry. Never raises — silent fail."""
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._post(path, payload)
                resp.raise_for_status()
                logger.debug("AIMO ✓ %s (attempt %d)", path, attempt + 1)
                return
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1:
                    logger.warning(
                        "AIMO: %d retries exhausted for %s — %s. "
                        "Pipeline is unaffected.",
                        _MAX_RETRIES, path, exc,
                    )
                    return
                wait = _RETRY_BASE_SEC * (2 ** attempt)   # 1 s → 2 s → 4 s
                logger.debug(
                    "AIMO: attempt %d/%d failed (%s), retrying in %.0f s",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)

    def _fire(self, coro: Any) -> asyncio.Task[None]:
        """Schedule coroutine as a background task; prevent GC by tracking it."""
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ── Node normalisation ────────────────────────────────────────────────────

    @staticmethod
    def _normalise_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Accept flexible node dicts from any project and map to the AIMO schema.

        Supported aliases:
          duration_ms  → latency_ms
          cost_rupees  → cost_usd  (divided by RUPEES_PER_USD)
          tokens       → prompt_tokens
          model_used   → model_id
        """
        result: list[dict[str, Any]] = []
        for i, n in enumerate(nodes):
            cost_usd = (
                n.get("cost_usd")
                or n.get("cost_rupees", 0.0) / RUPEES_PER_USD
            )
            result.append({
                "name":              n.get("name", f"node_{i}"),
                "model_id":          n.get("model_id") or n.get("model_used"),
                "cost_usd":          round(float(cost_usd), 6),
                "latency_ms":        int(n.get("latency_ms") or n.get("duration_ms", 0)),
                "prompt_tokens":     int(n.get("prompt_tokens") or n.get("tokens", 0)),
                "completion_tokens": int(n.get("completion_tokens", 0)),
                "input_text":        str(n.get("input_text",  "")),
                "output_text":       str(n.get("output_text", "")),
            })
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def register_pipeline(
        self,
        name:          str,
        description:   Optional[str] = None,
        pipeline_type: Optional[str] = None,
        owner_email:   Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Register a new pipeline with AIMO. Call ONCE during project setup.

        Prints the pipeline_id and api_key to stdout — copy them to your .env.

        Args:
            name:          Human-readable pipeline name (e.g. "QAIP Test Generator").
            description:   What this pipeline does.
            pipeline_type: Tag string e.g. "LangGraph-RAG", "IsolationForest".
            owner_email:   Alert recipient for this pipeline.

        Returns:
            {"pipeline_id": "...", "api_key": "...", "name": "..."}

        Raises:
            httpx.HTTPStatusError on non-2xx response.
        """
        desc = description
        if pipeline_type:
            desc = f"[{pipeline_type}] {description}" if description else f"[{pipeline_type}]"

        payload: dict[str, Any] = {
            "name":        name,
            "description": desc,
            "owner_email": owner_email,
        }
        resp = await self._post("/pipelines/register", payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        print("=" * 60)
        print("  AIMO Pipeline Registered!")
        print(f"  AIMO_PIPELINE_ID={data['pipeline_id']}")
        print(f"  AIMO_API_KEY={data['api_key']}")
        print("  → Add both to your project .env file")
        print("=" * 60)
        return data

    async def report_run(
        self,
        nodes:              Optional[list[dict[str, Any]]] = None,
        total_cost_rupees:  float                          = 0.0,
        faithfulness_score: Optional[float]                = None,
        outputs:            Optional[dict[str, Any]]       = None,
        contexts:           Optional[list[str]]            = None,
        run_id:             Optional[str]                  = None,
        input_text:         str                            = "",
        output_text:        str                            = "",
    ) -> dict[str, Any]:
        """
        Non-blocking run report. Returns immediately; HTTP ships in background.

        The calling pipeline is NEVER blocked or slowed. If AIMO is unreachable
        the background task retries 3× then gives up silently.

        Args:
            nodes:              Per-node telemetry. Each dict may contain:
                                  name, duration_ms, tokens, cost_rupees,
                                  model_used — OR the AIMO-native field names.
            total_cost_rupees:  Total run cost in INR (auto-converted to USD).
            faithfulness_score: deepeval faithfulness 0.0–1.0.
            outputs:            Final pipeline output dict (str-coerced for AIMO).
            contexts:           RAG context chunks (attached to the last node).
            run_id:             Custom run ID; auto-generated UUID if omitted.
            input_text:         Top-level pipeline input text.
            output_text:        Top-level pipeline output text.

        Returns:
            {"accepted": True, "scheduled": True, "run_id": "..."}
            immediately — does NOT wait for the HTTP call.
        """
        if not self.pipeline_id:
            logger.debug("AIMO: pipeline_id not set — skipping report_run")
            return {"accepted": False, "reason": "no pipeline_id configured"}

        rid = run_id or str(uuid.uuid4())
        norm = self._normalise_nodes(nodes or [])

        if contexts and norm:
            norm[-1]["context"] = contexts  # type: ignore[assignment]

        out_text = output_text or (str(outputs) if outputs else "")

        payload: dict[str, Any] = {
            "pipeline_id":        self.pipeline_id,
            "run_id":             rid,
            "nodes":              norm,
            "input_text":         input_text,
            "output_text":        out_text,
            "faithfulness_score": faithfulness_score,
            "timestamp":          datetime.now(timezone.utc).isoformat(),
        }

        self._fire(self._ship_with_retry("/runs/ingest", payload))
        return {"accepted": True, "scheduled": True, "run_id": rid}

    async def report_incident(
        self,
        incident_type: str,
        severity:      str,
        title:         str,
        description:   str                        = "",
        evidence:      Optional[dict[str, Any]]   = None,
    ) -> dict[str, Any]:
        """
        Report an incident detected by the pipeline itself.

        Use when your pipeline catches a problem directly, e.g.:
          • deepeval faithfulness < threshold → HALLUCINATION
          • 3 consecutive compliance drops   → COMPLIANCE_DRIFT
          • Golden dataset CI failure        → PROMPT_INJECTION

        Args:
            incident_type: HALLUCINATION | COST_SPIKE | COMPLIANCE_DRIFT |
                           LATENCY_DEGRADATION | PROMPT_INJECTION | ANOMALY
            severity:      P0 | P1 | P2 | P3
            title:         Short human-readable title.
            description:   Detailed description of what was detected.
            evidence:      Supporting data dict (scores, inputs, outputs).

        Returns:
            The created incident dict from AIMO, or {"error": "..."} on failure.
            Never raises — failures are logged and swallowed.
        """
        payload: dict[str, Any] = {
            "pipeline_id":   self.pipeline_id,
            "incident_type": incident_type,
            "severity":      severity,
            "title":         title,
            "description":   description,
            "evidence":      evidence or {},
        }
        try:
            resp = await self._post("/incidents", payload)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("AIMO report_incident failed (%s): %s", incident_type, exc)
            return {"error": str(exc), "incident_type": incident_type, "title": title}
