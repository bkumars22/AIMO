"""
Prompt 10 — Slack MCP Integration
Formatted alerts with severity-based routing:
  P0 → immediate @channel mention
  P1 → alert within 5 minutes
  P2 → daily digest
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
DASHBOARD_URL     = os.getenv("DASHBOARD_URL", "http://localhost:3000")

SEVERITY_EMOJI = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "⚪"}
TYPE_EMOJI = {
    "HALLUCINATION":       "🧠",
    "COST_SPIKE":          "💰",
    "COMPLIANCE_DRIFT":    "📋",
    "LATENCY_DEGRADATION": "⏱",
    "PROMPT_INJECTION":    "🛡",
}


def _build_blocks(incident: dict) -> list[dict]:
    sev   = incident.get("severity", "P3")
    itype = incident.get("incident_type", "UNKNOWN")
    title = incident.get("title", "Untitled incident")
    pipeline = incident.get("pipeline_id", "unknown")
    root_cause = incident.get("root_cause", "")
    inc_id = incident.get("id", "")

    mention = "<!channel> " if sev == "P0" else ""
    header  = f"{mention}{SEVERITY_EMOJI.get(sev, '⚪')} {sev} — {TYPE_EMOJI.get(itype, '⚠️')} {itype}"

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\nPipeline: `{pipeline}`"}},
    ]

    if root_cause:
        snippet = root_cause[:300] + ("…" if len(root_cause) > 300 else "")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Root cause:*\n{snippet}"},
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View in AIMO"},
                "url": f"{DASHBOARD_URL}/incidents/{inc_id}",
                "style": "primary" if sev in ("P0", "P1") else "default",
            }
        ],
    })
    return blocks


async def send_incident_alert(incident: dict, timeout: float = 5.0) -> bool:
    """Send a formatted Slack alert. Returns True on success."""
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — alert skipped for incident %s", incident.get("id"))
        return False

    sev = incident.get("severity", "P3")
    payload = {
        "blocks":    _build_blocks(incident),
        "text":      f"AIMO {sev} incident: {incident.get('title', '')}",  # fallback for notifications
        "username":  "AIMO",
        "icon_emoji": ":robot_face:",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            logger.info("Slack alert sent for incident %s (status %d)", incident.get("id"), resp.status_code)
            return True
    except Exception as exc:
        logger.error("Slack alert failed for incident %s: %s", incident.get("id"), exc)
        return False


async def send_daily_digest(incidents: list[dict]) -> bool:
    """P2 daily digest — bundle multiple P2 incidents into one message."""
    if not SLACK_WEBHOOK_URL or not incidents:
        return False

    lines = [f"• {i.get('incident_type')} — {i.get('title', '')[:80]}" for i in incidents[:20]]
    payload = {
        "text": f"AIMO daily digest: {len(incidents)} P2 incidents",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "🟡 AIMO Daily P2 Digest"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"<{DASHBOARD_URL}/incidents?severity=P2|View all in AIMO>"}},
        ],
        "username": "AIMO",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("Slack digest failed: %s", exc)
        return False
