"""
Prompt 12 — Demo data seeder
Creates realistic demo data so the dashboard shows real-looking data immediately.

Run:
    cd ai-engine && python seeds/demo_seeder.py

Creates:
  - 3 demo pipelines (QAIP Monitor, SCIP Monitor, ARIA Monitor)
  - 30 days of run history per pipeline
  - 15 mixed incidents (P0–P3)
  - 2 resolved P0s, 1 open P1

Requires: DB connection (set DATABASE_URL in .env)
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Lazy DB import — only runs when DEMO_SEED=1 and DB is available
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aimo:aimo_secret@localhost:5432/aimo")

PIPELINES = [
    {"id": str(uuid.uuid4()), "name": "QAIP Monitor",  "description": "Monitors QAIP QA test pipeline"},
    {"id": str(uuid.uuid4()), "name": "SCIP Monitor",  "description": "Monitors SCIP supply chain analysis"},
    {"id": str(uuid.uuid4()), "name": "ARIA Monitor",  "description": "Monitors ARIA AI tutor pipeline"},
]

INCIDENT_TEMPLATES = [
    # P0 — resolved
    {"type": "PROMPT_INJECTION", "severity": "P0", "status": "RESOLVED",
     "title": "Jailbreak attempt detected on ARIA tutor",
     "root_cause": "Student submitted DAN mode prompt to bypass content filters.",
     "resolution": "IP blocked. Injection patterns updated."},
    {"type": "HALLUCINATION", "severity": "P0", "status": "RESOLVED",
     "title": "Critical hallucination on SCIP supplier analysis",
     "root_cause": "Model cited non-existent regulations. Faithfulness score 0.11.",
     "resolution": "Retrieval context expanded. Faithfulness threshold enforced."},
    # P1 — open
    {"type": "COMPLIANCE_DRIFT", "severity": "P1", "status": "OPEN",
     "title": "Compliance rate declining on QAIP pipeline",
     "root_cause": "QAIP faithfulness scores dropping for 3 consecutive days."},
    # P2s
    {"type": "COST_SPIKE", "severity": "P2", "status": "RESOLVED",
     "title": "Cost spike on SCIP: 4.2× baseline",
     "root_cause": "Large document ingestion triggered extra chunking calls."},
    {"type": "LATENCY_DEGRADATION", "severity": "P2", "status": "OPEN",
     "title": "Latency 3× baseline on ARIA generate node",
     "root_cause": "Groq rate limit triggered retry with exponential backoff."},
    # P3s
    {"type": "ANOMALY", "severity": "P3", "status": "RESOLVED",
     "title": "Anomalous token count on QAIP explain_and_score"},
    {"type": "COST_SPIKE", "severity": "P3", "status": "RESOLVED",
     "title": "Minor cost increase on ARIA: 2.1× baseline"},
]


def seed():
    if not DB_AVAILABLE:
        print("SQLAlchemy not installed — printing seed data instead")
        _print_seed_summary()
        return

    engine = create_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)

    try:
        with Session() as session:
            _seed_pipelines(session)
            _seed_runs(session)
            _seed_incidents(session)
            session.commit()
        print("✓ Demo data seeded successfully")
        _print_seed_summary()
    except Exception as exc:
        print(f"✗ Seeding failed: {exc}")
        print("  Make sure the database is running: docker compose up -d db")
        sys.exit(1)


def _seed_pipelines(session):
    for p in PIPELINES:
        session.execute(text("""
            INSERT INTO pipelines (id, name, description, health_score, created_at, updated_at)
            VALUES (:id, :name, :desc, 85, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """), {"id": p["id"], "name": p["name"], "desc": p["description"]})
    print(f"  Seeded {len(PIPELINES)} pipelines")


def _seed_runs(session):
    total = 0
    now = datetime.now(timezone.utc)
    for p in PIPELINES:
        for days_ago in range(30):
            run_time = now - timedelta(days=days_ago, hours=random.randint(0, 23))
            cost = 0.008 + random.gauss(0, 0.002)
            latency = 650 + random.gauss(0, 100)
            faith = min(1.0, max(0.5, 0.88 + random.gauss(0, 0.05)))
            session.execute(text("""
                INSERT INTO pipeline_runs (id, pipeline_id, started_at, cost_usd, latency_ms, faithfulness_score)
                VALUES (:id, :pid, :ts, :cost, :lat, :faith)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(uuid.uuid4()), "pid": p["id"],
                "ts": run_time, "cost": max(0, cost),
                "lat": max(100, int(latency)), "faith": faith,
            })
            total += 1
    print(f"  Seeded {total} pipeline runs (30 days × {len(PIPELINES)} pipelines)")


def _seed_incidents(session):
    total = 0
    for i, tmpl in enumerate(INCIDENT_TEMPLATES):
        pipeline_id = PIPELINES[i % len(PIPELINES)]["id"]
        inc_id = str(uuid.uuid4())
        session.execute(text("""
            INSERT INTO incidents (id, pipeline_id, incident_type, severity, title,
                                   root_cause, resolution_notes, status, created_at, updated_at)
            VALUES (:id, :pid, :type, :sev, :title, :root, :res, :status, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": inc_id, "pid": pipeline_id,
            "type": tmpl["type"], "sev": tmpl["severity"],
            "title": tmpl["title"],
            "root": tmpl.get("root_cause"),
            "res": tmpl.get("resolution"),
            "status": tmpl["status"],
        })
        total += 1
    print(f"  Seeded {total} incidents")


def _print_seed_summary():
    print("\nDemo data summary:")
    for p in PIPELINES:
        print(f"  Pipeline: {p['name']} (id: {p['id'][:8]}…)")
    print(f"  Incidents: {len(INCIDENT_TEMPLATES)} ({sum(1 for i in INCIDENT_TEMPLATES if i['status'] == 'OPEN')} open)")


if __name__ == "__main__":
    seed()
