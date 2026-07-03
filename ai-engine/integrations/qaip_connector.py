"""
Prompt 10 — QAIP Webhook Integration
QAIP sends run data to AIMO after every pipeline run.
AIMO monitors QAIP's own pipeline → meta-observability.
"""
from __future__ import annotations

import logging
import os
import uuid

import httpx

logger = logging.getLogger(__name__)

AIMO_ENDPOINT = os.getenv("AIMO_ENDPOINT", "http://localhost:8001")
AIMO_API_KEY  = os.getenv("AIMO_API_KEY", "")
QAIP_PIPELINE_ID = os.getenv("QAIP_PIPELINE_ID", "")  # registered pipeline ID for QAIP itself


async def report_qaip_run(
    run_id: str | None,
    nodes: list[dict],
    total_cost_usd: float,
    input_text: str,
    output_text: str,
    faithfulness_score: float | None = None,
) -> bool:
    """
    QAIP calls this after each test run to send telemetry to AIMO.
    Returns True if AIMO accepted the run, False otherwise.
    """
    if not QAIP_PIPELINE_ID:
        logger.debug("QAIP_PIPELINE_ID not set — AIMO reporting disabled")
        return False

    payload = {
        "pipeline_id":       QAIP_PIPELINE_ID,
        "run_id":            run_id or str(uuid.uuid4()),
        "nodes":             nodes,
        "input_text":        input_text,
        "output_text":       output_text,
        "faithfulness_score": faithfulness_score,
    }

    headers = {"Authorization": f"Bearer {AIMO_API_KEY}"} if AIMO_API_KEY else {}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{AIMO_ENDPOINT}/runs/ingest", json=payload, headers=headers)
            resp.raise_for_status()
            logger.info("QAIP run %s reported to AIMO", payload["run_id"])
            return True
    except Exception as exc:
        logger.warning("AIMO report failed for QAIP run %s: %s", payload.get("run_id"), exc)
        return False
