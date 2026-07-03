"""
LangSmith Bridge — polls LangSmith API every LANGSMITH_POLL_INTERVAL_SEC
seconds, converts traces to AIMO SpanPayloads, and enriches cost_events.

Why this exists: @aimo_trace ships data in real-time but some pipelines
may not yet have the SDK installed. The bridge provides zero-code-change
observability by reading directly from LangSmith.

Phase 1: implement poll_and_enrich() using LangSmith Python client.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger("aimo.bridges.langsmith")

LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "AIMO-Production")


async def poll_and_enrich() -> int:
    """
    Fetch runs from LangSmith since last poll timestamp.
    Convert each run to SpanPayload and pass through the monitoring pipeline.

    Returns: number of runs processed.
    """
    if not LANGCHAIN_API_KEY:
        logger.debug("LangSmith bridge disabled — LANGCHAIN_API_KEY not set")
        return 0
    raise NotImplementedError("Phase 1")
