"""
AIPQ Root-Cause Connector

When AIMO flags a HALLUCINATION or QUALITY_DEGRADATION incident, this asks
AIPQ whether the underlying prompt changed recently — turning "something
got worse" into "prompt vN, deployed 2 days ago, dropped compliance from
0.94 to 0.71 — rollback recommended" (or, if the prompt hasn't changed,
"this is model drift, not a prompt regression").

Now wired automatically: classify_incidents (monitoring_agent.py) looks up
each (pipeline_id, node_name) pair in AIPQ_PIPELINE_MAP and, when a match
exists, stamps aipq_project_id/aipq_prompt_name onto the incident's
evidence at creation time — so generate_root_cause's existing
_augment_with_aipq call fires for real instead of only when a caller
manually supplies that evidence.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

AIPQ_BASE_URL = os.getenv("AIPQ_BASE_URL", "http://localhost:8001")
AIPQ_API_KEY = os.getenv("AIPQ_API_KEY", "")

# JSON env var mapping AIMO pipeline_id -> node_name -> AIPQ (project_id, prompt_name):
#   AIPQ_PIPELINE_MAP={"aria-prod": {"teach_socratically": {"project_id": 1, "prompt_name": "aria_socratic_system"}}}
# A pipeline can have multiple nodes, each independently tracked by AIPQ as its
# own prompt, hence the two-level lookup rather than one mapping per pipeline.
_PIPELINE_MAP: dict = {}
try:
    _PIPELINE_MAP = json.loads(os.getenv("AIPQ_PIPELINE_MAP", "{}"))
except json.JSONDecodeError:
    logger.warning("AIPQ_PIPELINE_MAP is not valid JSON — no AIMO incidents will auto-map to AIPQ prompts")


def get_aipq_mapping(pipeline_id: str, node_name: str) -> Optional[dict]:
    """Returns {"project_id": int, "prompt_name": str} if this pipeline/node is AIPQ-tracked, else None."""
    return _PIPELINE_MAP.get(pipeline_id, {}).get(node_name)


async def check_aipq_root_cause(project_id: int, prompt_name: str) -> Optional[dict]:
    """
    Queries AIPQ's cross-system drift-status endpoint for one prompt.

    Returns None if AIPQ is unreachable or not configured — never raises,
    so a down/unconfigured AIPQ can't break AIMO's own incident pipeline.
    """
    if not AIPQ_API_KEY:
        logger.debug("AIPQ_API_KEY not set — skipping AIPQ root-cause check")
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{AIPQ_BASE_URL}/drift/status",
                params={"project_id": project_id, "prompt_name": prompt_name},
                headers={"Authorization": f"Bearer {AIPQ_API_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.debug("AIPQ has no record of prompt '%s' for project %d", prompt_name, project_id)
        else:
            logger.warning("AIPQ root-cause query failed (%d): %s", exc.response.status_code, exc)
        return None
    except Exception as exc:
        logger.warning("AIPQ unreachable during root-cause check for '%s': %s", prompt_name, exc)
        return None


def format_root_cause_note(aipq_status: dict) -> str:
    """Turns AIPQ's /drift/status payload into a one-line note for an incident's root_cause field."""
    return f"[AIPQ] {aipq_status.get('root_cause_hint', 'No AIPQ assessment available.')}"
