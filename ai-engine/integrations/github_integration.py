"""
Prompt 10 — GitHub MCP Integration
Auto-creates GitHub issues for P0/P1 incidents with AI-generated root cause.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "")   # e.g. "bkumars22/AIMO"
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")

SEVERITY_LABEL = {"P0": "severity:p0", "P1": "severity:p1", "P2": "severity:p2", "P3": "severity:p3"}
TYPE_LABEL     = {
    "HALLUCINATION":       "type:hallucination",
    "COST_SPIKE":          "type:cost-spike",
    "COMPLIANCE_DRIFT":    "type:compliance-drift",
    "LATENCY_DEGRADATION": "type:latency",
    "PROMPT_INJECTION":    "type:injection",
}

_HEADERS = {
    "Accept":               "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _build_body(incident: dict) -> str:
    inc_id    = incident.get("id", "")
    itype     = incident.get("incident_type", "")
    sev       = incident.get("severity", "")
    pipeline  = incident.get("pipeline_id", "")
    root      = incident.get("root_cause") or "_Root cause pending AI analysis_"
    fix       = incident.get("suggested_fix") or ""
    evidence  = incident.get("evidence") or {}

    fix_block = f"\n```python\n{fix}\n```\n" if fix else "_Suggested fix pending_"
    evidence_json = "\n".join(f"- **{k}**: {v}" for k, v in (evidence or {}).items())

    return f"""\
## AIMO Incident — {itype} [{sev}]

**Pipeline:** `{pipeline}`
**Incident ID:** `{inc_id}`
**Dashboard:** {DASHBOARD_URL}/incidents/{inc_id}

---

### Root Cause (AI Generated)

{root}

### Evidence

{evidence_json or "_No structured evidence_"}

### Suggested Fix

{fix_block}

---

_Auto-created by [AIMO](https://github.com/bkumars22/AIMO)_
"""


async def create_incident_issue(incident: dict) -> str | None:
    """
    Create a GitHub issue for a P0/P1 incident.
    Returns the issue URL on success, None on failure.
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning("GITHUB_TOKEN or GITHUB_REPO not set — GitHub issue creation skipped")
        return None

    sev   = incident.get("severity", "P3")
    itype = incident.get("incident_type", "UNKNOWN")
    title = f"[AIMO] {sev} — {itype}: {incident.get('title', '')[:80]}"

    labels = ["ai-incident", SEVERITY_LABEL.get(sev, "severity:p3")]
    if itype in TYPE_LABEL:
        labels.append(TYPE_LABEL[itype])

    payload = {
        "title":  title,
        "body":   _build_body(incident),
        "labels": labels,
    }

    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {**_HEADERS, "Authorization": f"Bearer {GITHUB_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            issue_url = resp.json().get("html_url", "")
            logger.info("GitHub issue created: %s", issue_url)
            return issue_url
    except Exception as exc:
        logger.error("GitHub issue creation failed for incident %s: %s", incident.get("id"), exc)
        return None
