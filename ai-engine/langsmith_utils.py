"""
LangSmith tracing utilities for AIMO's own monitoring pipeline.
Zero-overhead passthrough when LANGCHAIN_API_KEY is not set.
"""
import os
import time
import logging
import functools
from typing import Callable

logger = logging.getLogger("aimo.langsmith")

_TRACING_ENABLED = bool(os.getenv("LANGCHAIN_API_KEY"))

try:
    if _TRACING_ENABLED:
        from langsmith import Client as _LSClient
        _ls_client = _LSClient()
    else:
        _ls_client = None
except ImportError:
    _ls_client = None
    _TRACING_ENABLED = False


def trace_node(node_name_or_fn: Callable | str | None = None) -> Callable:
    """
    Wrap a LangGraph node with a LangSmith span. No-op when key not set.

    Usable both bare (@trace_node — name inferred from the function) and as
    a factory (@trace_node("custom_name")).
    """
    def wrap(fn: Callable, name: str) -> Callable:
        if not _TRACING_ENABLED:
            return fn

        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            started = time.time()
            status = "ok"
            try:
                return fn(state)
            except Exception:
                status = "error"
                raise
            finally:
                elapsed_ms = int((time.time() - started) * 1000)
                logger.debug("[%s] status=%s elapsed=%dms", name, status, elapsed_ms)
        return wrapper

    if callable(node_name_or_fn):
        fn = node_name_or_fn
        return wrap(fn, fn.__name__)

    def decorator(fn: Callable) -> Callable:
        return wrap(fn, node_name_or_fn or fn.__name__)
    return decorator


def trace_run(run_id: str, project_id: str, node_count: int,
              cost_usd: float, deepeval_score: float = 0.0) -> None:
    """Log a complete pipeline run cost to LangSmith dataset."""
    if not _TRACING_ENABLED or _ls_client is None:
        return
    try:
        _ls_client.create_example(
            inputs={"run_id": run_id, "project_id": project_id},
            outputs={
                "node_count": node_count,
                "cost_usd": round(cost_usd, 6),
                "deepeval_score": round(deepeval_score, 4),
            },
            dataset_name="AIMO-RunMetrics",
        )
    except Exception as exc:
        logger.debug("trace_run: LangSmith logging failed — %s", exc)
