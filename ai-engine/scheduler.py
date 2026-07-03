"""
AIMO Scheduler — background jobs via APScheduler

Jobs:
  - compliance_eval_job  : every COMPLIANCE_EVAL_INTERVAL_MIN minutes
  - langsmith_bridge_job : every LANGSMITH_POLL_INTERVAL_SEC seconds

Phase 1: wire into main.py startup/shutdown events.
"""
import os
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("aimo.scheduler")

scheduler = AsyncIOScheduler()

COMPLIANCE_EVAL_INTERVAL_MIN = int(os.getenv("COMPLIANCE_EVAL_INTERVAL_MIN", "60"))
LANGSMITH_POLL_INTERVAL_SEC  = int(os.getenv("LANGSMITH_POLL_INTERVAL_SEC", "300"))


async def compliance_eval_job() -> None:
    """Run shadow compliance eval against all registered pipelines."""
    logger.info("compliance_eval_job: starting scheduled eval run")
    # TODO Phase 1: from detectors.compliance_drift import run_scheduled_eval
    #               await run_scheduled_eval()


async def langsmith_bridge_job() -> None:
    """Poll LangSmith for new traces and enrich cost_events."""
    logger.debug("langsmith_bridge_job: polling LangSmith")
    # TODO Phase 1: from bridges.langsmith_bridge import poll_and_enrich
    #               await poll_and_enrich()


def start() -> None:
    scheduler.add_job(
        compliance_eval_job,
        "interval",
        minutes=COMPLIANCE_EVAL_INTERVAL_MIN,
        id="compliance_eval",
        replace_existing=True,
    )
    scheduler.add_job(
        langsmith_bridge_job,
        "interval",
        seconds=LANGSMITH_POLL_INTERVAL_SEC,
        id="langsmith_bridge",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — compliance_eval every %dm, langsmith_bridge every %ds",
        COMPLIANCE_EVAL_INTERVAL_MIN,
        LANGSMITH_POLL_INTERVAL_SEC,
    )


def stop() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
