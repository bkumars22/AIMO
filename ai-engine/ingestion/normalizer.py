"""
LangSmith trace → AIMO SpanPayload normalizer.
Used by the LangSmith bridge to convert polled traces into our schema.
"""
from __future__ import annotations
from typing import Any
from ingestion.schema import SpanPayload


def langsmith_trace_to_span(trace: dict[str, Any]) -> SpanPayload | None:
    """
    Convert a LangSmith run dict to a SpanPayload.
    Returns None if the trace is missing required fields.

    Phase 1: implement full field mapping from LangSmith run format.
    """
    raise NotImplementedError("Phase 1")
