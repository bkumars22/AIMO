"""
Redis pub/sub for real-time incident push to the React dashboard.

Channel: aimo:incidents
Message: JSON-encoded incident dict

The FastAPI WebSocket handler subscribes to this channel
and pushes messages to connected browser clients.

Phase 1: implement publish() and the async subscriber.
"""
from __future__ import annotations
import json
import os
import logging

logger = logging.getLogger("aimo.alerting.pubsub")

REDIS_URL     = os.getenv("REDIS_URL", "redis://localhost:6379")
ALERT_CHANNEL = os.getenv("REDIS_ALERT_CHANNEL", "aimo:incidents")

_redis_client = None   # initialized on first call


def get_client():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def publish(incident: dict) -> None:
    """Publish incident JSON to aimo:incidents channel."""
    raise NotImplementedError("Phase 1")


async def subscribe():
    """
    Async generator — yields incident dicts from aimo:incidents channel.
    Used by the WebSocket route handler.
    """
    raise NotImplementedError("Phase 1")
