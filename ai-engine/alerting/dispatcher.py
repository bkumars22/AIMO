"""
Alert Dispatcher — sends incidents to Slack (webhook) or email (SMTP).

Synchronous by design: monitoring_agent's send_alerts node is a plain sync
LangGraph node that calls dispatch(inc, channel=...) directly without
awaiting it (see that node and its existing test suite, which already
mocks dispatch as a plain callable) — making this module async would
require threading asyncio.run() through send_alerts and rewriting tests
that have nothing to do with this module's own implementation.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger("aimo.alerting.dispatcher")

WEBHOOK_URL = os.getenv("AIMO_ALERT_WEBHOOK", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

_SEVERITY_COLOR = {"P0": "#dc2626", "P1": "#ea580c", "P2": "#d97706", "P3": "#65a30d"}


def _slack_payload(incident: dict) -> dict:
    severity = incident.get("severity", "P3")
    return {
        "attachments": [{
            "color": _SEVERITY_COLOR.get(severity, "#64748b"),
            "title": f"[{severity}] {incident.get('title') or incident.get('incident_type', 'AIMO incident')}",
            "text": incident.get("root_cause") or "No root cause yet.",
            "fields": [
                {"title": "Type", "value": incident.get("incident_type", "UNKNOWN"), "short": True},
                {"title": "Pipeline", "value": str(incident.get("pipeline_id", "—")), "short": True},
                {"title": "Incident ID", "value": str(incident.get("id", "—")), "short": True},
            ],
        }],
    }


def send_webhook(incident: dict) -> bool:
    """POST incident payload to AIMO_ALERT_WEBHOOK (Slack incoming-webhook format)."""
    if not WEBHOOK_URL:
        logger.warning("AIMO_ALERT_WEBHOOK not set — skipping Slack alert for incident %s", incident.get("id"))
        return False
    try:
        resp = httpx.post(WEBHOOK_URL, json=_slack_payload(incident), timeout=5.0)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Slack webhook delivery failed for incident %s: %s", incident.get("id"), exc)
        return False


def send_email(incident: dict) -> bool:
    """Send incident email via SMTP (STARTTLS)."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and ALERT_EMAIL_TO):
        logger.warning("SMTP not fully configured — skipping email alert for incident %s", incident.get("id"))
        return False
    try:
        severity = incident.get("severity", "P3")
        title = incident.get("title") or incident.get("incident_type", "AIMO incident")
        body = (
            f"Severity: {severity}\n"
            f"Type: {incident.get('incident_type', 'UNKNOWN')}\n"
            f"Pipeline: {incident.get('pipeline_id', '—')}\n"
            f"Incident ID: {incident.get('id', '—')}\n\n"
            f"Root cause: {incident.get('root_cause') or 'Not yet determined.'}"
        )
        msg = MIMEText(body)
        msg["Subject"] = f"[AIMO {severity}] {title}"
        msg["From"] = ALERT_EMAIL_FROM or SMTP_USER
        msg["To"] = ALERT_EMAIL_TO

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Email delivery failed for incident %s: %s", incident.get("id"), exc)
        return False


def dispatch(incident: dict, channel: str) -> dict:
    """
    Dispatch one incident to a single channel ("slack" or "email").

    Never raises — an unreachable Slack/SMTP endpoint must never break
    incident creation, so failures are reported via the return value, not
    an exception (send_alerts also wraps its own call in try/except, but
    that's for genuinely unexpected errors, not routine delivery failures).
    """
    if channel == "slack":
        ok = send_webhook(incident)
    elif channel == "email":
        ok = send_email(incident)
    else:
        logger.warning("dispatch: unknown channel '%s' for incident %s", channel, incident.get("id"))
        ok = False
    return {"ok": ok, "channel": channel}
