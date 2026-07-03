"""
Alert Dispatcher — sends incidents to webhook / Slack / email.

Phase 1: implement send_webhook() and send_slack().
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger("aimo.alerting.dispatcher")

WEBHOOK_URL = os.getenv("AIMO_ALERT_WEBHOOK", "")


async def send_webhook(incident: dict) -> bool:
    """POST incident payload to AIMO_ALERT_WEBHOOK (Slack-compatible)."""
    raise NotImplementedError("Phase 1")


async def send_email(incident: dict) -> bool:
    """Send incident email via SMTP."""
    raise NotImplementedError("Phase 1")


async def dispatch(incident: dict) -> list[str]:
    """
    Dispatch an incident to all configured channels.
    Returns list of channel names that were notified.
    Swallows errors per channel — never blocks incident creation.
    """
    raise NotImplementedError("Phase 1")
