# AIMO — AI Incident Management & Observability Platform

> **PagerDuty catches when your server is down. AIMO catches when your AI is wrong.**

[![CI](https://github.com/bkumars22/AIMO/actions/workflows/ci.yml/badge.svg)](https://github.com/bkumars22/AIMO/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![Spring Boot 3.3](https://img.shields.io/badge/Spring%20Boot-3.3-green.svg)](https://spring.io/projects/spring-boot)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Live Demo:** [aimo-frontend.up.railway.app](https://aimo-frontend.up.railway.app) *(deploy in progress — see Quick Start to run locally)*

| Service | URL |
|---|---|
| Dashboard (React) | https://aimo-frontend.up.railway.app |
| AI Engine (FastAPI + Swagger) | https://aimo-ai-engine.up.railway.app/docs |
| Backend API (Spring Boot) | https://aimo-backend.up.railway.app/actuator/health |

**Guest credentials:** `demo@aimo.internal` / `aimo-demo-2026`

---

## The Ecosystem

AIMO monitors the other 4 projects in this portfolio — making it the observability layer across everything:

| Project | AIMO monitors | Repository |
|---|---|---|
| [QAIP](https://github.com/bkumars22/QA-Intelligent-Platform) | QA test pipeline cost + faithfulness | QAIP sends run data to `/runs/ingest` |
| [SCIP](https://github.com/bkumars22/scip) | Supplier analysis LLM calls | `@aimo_trace` on generate nodes |
| [ARIA](https://github.com/bkumars22/ARIA) | AI tutor compliance + injection | Injection detector already 100% passing |
| ZENTRAVIX | CEO dashboard data pipeline | Health score surfaced in ZENTRAVIX KPIs |

AIMO also monitors **itself** — meta-observability, eating its own dog food.

---

---

## The Problem

When you ship an LLM pipeline to production you get five silent failure modes that traditional APM tools miss entirely:

| Failure | Traditional APM | AIMO |
|---|---|---|
| Hallucination | ✗ invisible | ✓ deepeval faithfulness scoring |
| Cost spike | ✓ alert if billing spikes | ✓ per-run anomaly score (IsolationForest) |
| Compliance drift | ✗ invisible | ✓ embedding similarity vs. baseline |
| Latency degradation | ✓ p95 alert | ✓ z-score on rolling 7-day window |
| Prompt injection | ✗ invisible | ✓ 18-pattern regex + vector similarity |

AIMO solves all five.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Monitored Pipeline                     │
│   Node 1 → @aimo_trace → Node 2 → @aimo_trace → ...    │
└────────────────────┬────────────────────────────────────┘
                     │  fire-and-forget POST /ingest/span
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  AIMO AI Engine (FastAPI)                │
│                                                          │
│  LangGraph Monitoring Pipeline (7 nodes)                 │
│  ┌──────────────┐                                        │
│  │ ingest_telemetry → score_hallucination               │
│  │               → detect_cost_anomaly                  │
│  │               → check_compliance                     │
│  │               → detect_latency_drift                 │
│  │               → classify_injections                  │
│  │               → dispatch_incidents                   │
│  └──────────────┘                                        │
│                                                          │
│  Detectors: deepeval · IsolationForest · pgvector · regex│
│  Scheduler: compliance eval (60 min) · LangSmith (5 min) │
└──────┬───────────────────┬───────────────────────────────┘
       │ JPA/Flyway        │ Redis pub/sub
       ▼                   ▼
┌──────────────┐   ┌───────────────────────────────────┐
│  PostgreSQL  │   │  Spring Boot Backend (REST + Auth) │
│  + pgvector  │   │  WebSocket → React Dashboard       │
└──────────────┘   └───────────────────────────────────┘
```

### Five Incident Types

| Type | Trigger | Default Severity |
|---|---|---|
| `HALLUCINATION` | faithfulness < 0.40 | P1 |
| `COST_SPIKE` | cost > 3× 7-day average | P2 |
| `COMPLIANCE_DRIFT` | compliance rate < 70% | P1 |
| `LATENCY_DEGRADATION` | latency > 5× p95 baseline | P2 |
| `PROMPT_INJECTION` | regex or vector match | P0 (always critical) |

### Severity Matrix

| | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| Injection | always | | | |
| Hallucination | score < 0.25 | score < 0.40 | score < 0.60 | score ≥ 0.60 |
| Compliance | rate < 50% | rate < 70% | rate < 85% | rate ≥ 85% |
| Latency | > 10× p95 | > 5× p95 | > 3× p95 | > 2× p95 |
| Cost | > 10× avg | > 5× avg | > 3× avg | > 2× avg |

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Engine | Python 3.11 · FastAPI · LangGraph · deepeval |
| Anomaly Detection | scikit-learn IsolationForest (rolling 7-day window) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local, free) |
| Vector Store | pgvector 0.7 (384-dim) — compliance baselines + injection vectors |
| Backend | Spring Boot 3.3 · Java 17 · Spring Security · JJWT 0.12.6 |
| Database | PostgreSQL 15 + pgvector · Flyway migrations (V1–V5) |
| Cache / Pub-Sub | Redis 7 |
| Frontend | React 18 · TypeScript 5.5 · Vite 5 · Tailwind CSS 3 · Recharts 2 |
| CI | GitHub Actions — blocks merge on test failure |

---

## Project Structure

```
AIMO/
├── docker-compose.yml          # 5 services: db, redis, backend, ai-engine, frontend
├── .env.example                # all environment variables with descriptions
├── .github/
│   └── workflows/ci.yml        # Python + Java + React CI (all 3 must pass)
│
├── ai-engine/                  # FastAPI monitoring service
│   ├── main.py                 # app entrypoint + /health
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── agents/
│   │   └── monitoring_agent.py # LangGraph 7-node pipeline + MonitoringState
│   ├── detectors/
│   │   ├── hallucination.py    # deepeval faithfulness + consistency
│   │   ├── cost_anomaly.py     # IsolationForest on cost_events
│   │   ├── compliance_drift.py # pgvector embedding comparison
│   │   ├── latency_degradation.py # z-score on latency rolling window
│   │   └── injection_detector.py  # 18 regex patterns — FULLY IMPLEMENTED
│   ├── ingestion/
│   │   ├── schema.py           # Pydantic models (SpanPayload, RunPayload, …)
│   │   └── normalizer.py       # LangSmith trace → SpanPayload
│   ├── storage/
│   │   ├── database.py         # SQLAlchemy engine + SessionLocal
│   │   ├── repositories.py     # 14 DB operation stubs
│   │   └── vector_store.py     # pgvector embed + search stubs
│   ├── alerting/
│   │   ├── dispatcher.py       # webhook + email dispatch stubs
│   │   ├── redis_pubsub.py     # Redis pub/sub for WebSocket delivery
│   │   └── rules.py            # alert rule evaluation stubs
│   ├── sdk/
│   │   └── aimo_trace.py       # @aimo_trace decorator — FULLY IMPLEMENTED
│   ├── bridges/
│   │   └── langsmith_bridge.py # LangSmith polling bridge stub
│   ├── scheduler.py            # APScheduler — compliance + LangSmith jobs
│   ├── langsmith_utils.py      # @trace_node passthrough decorator
│   └── tests/
│       ├── test_health.py      # 2 passing tests
│       └── test_injection_detector.py  # 17 parametrized tests — PASSING
│
├── backend/                    # Spring Boot REST API + auth
│   ├── pom.xml                 # Spring Boot 3.3.1 · JJWT 0.12.6 · Flyway
│   ├── Dockerfile              # multi-stage maven build
│   └── src/main/
│       ├── java/com/aimo/
│       │   └── AimoApplication.java
│       └── resources/
│           ├── application.properties
│           ├── application-test.properties  # H2 in-memory for tests
│           └── db/migration/
│               ├── V1__core_schema.sql      # pipelines, runs, spans
│               ├── V2__incidents.sql        # incidents, evidence, eval runs
│               ├── V3__cost_injection.sql   # cost_events, injection_attempts
│               ├── V4__alerting.sql         # alert_rules (13 seeded defaults)
│               └── V5__pgvector.sql         # vector extension + IVFFlat indexes
│
└── frontend/                   # React dashboard
    ├── package.json            # React 18 · Recharts · Vite · Tailwind
    ├── Dockerfile              # node build → nginx serve
    ├── nginx.conf              # SPA routing + /api + /ai proxy
    ├── vite.config.ts          # path alias + dev proxy
    ├── tailwind.config.js
    └── src/
        ├── App.tsx             # BrowserRouter — /, /incidents/:id, /pipelines/:id
        ├── api/api.ts          # TypeScript interfaces + API stubs
        ├── hooks/
        │   ├── useWebSocket.ts # WebSocket hook stub
        │   └── useIncidents.ts # REST fetch hook stub
        └── pages + components/ # Dashboard, IncidentDetail, PipelineDetail
                                # IncidentFeed, PipelineHealthCard, CostTimeline,
                                # ComplianceGauge, LatencyHeatmap, InjectionLog
```

---

## Quick Start

### Prerequisites

- Docker + Docker Compose v2
- An `.env` file (copy from `.env.example` and fill in your API keys)

### 1 — Clone and configure

```bash
git clone https://github.com/bkumars22/AIMO.git
cd AIMO
cp .env.example .env
# Edit .env — set GROQ_API_KEY, ANTHROPIC_API_KEY, JWT_SECRET at minimum
```

### 2 — Start all services

```bash
docker compose up -d
```

Services start in dependency order: `db` and `redis` first, then `backend` and `ai-engine`, then `frontend`.

### 3 — Open the dashboard

```
http://localhost:3000
```

### 4 — Verify health

```bash
curl http://localhost:8001/health   # ai-engine
curl http://localhost:8080/actuator/health  # backend
```

### 5 — Instrument your pipeline

Install the SDK in your existing LLM pipeline:

```python
# 1. Copy ai-engine/sdk/aimo_trace.py into your project
# 2. Set env var: AIMO_ENDPOINT=http://localhost:8001
# 3. Decorate your nodes:

from aimo_trace import aimo_trace

@aimo_trace(node_name="generate_response", pipeline="my-rag-pipeline")
def generate_response(state: dict) -> dict:
    # your existing code — zero changes needed
    ...
    return state
```

Spans are shipped via a daemon thread — your pipeline latency is unaffected even if AIMO is unreachable.

---

## Development

### Run AI Engine locally (no Docker)

```bash
cd ai-engine
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

### Run tests

```bash
# AI Engine
cd ai-engine && pytest tests/ -v

# Backend
cd backend && mvn test -Dspring.profiles.active=test

# Frontend (type-check + lint)
cd frontend && npm install && npm run type-check && npm run lint
```

### CI

All three test jobs must pass before merging. Configure branch protection in:
`GitHub → Settings → Branches → main → Require status checks`.

Required checks: `test-ai-engine`, `test-backend`, `lint-frontend`.

---

## Roadmap

| Phase | Scope |
|---|---|
| **Scaffold** (now) | All detectors stubbed · injection detector + SDK complete · CI green |
| **Phase 1** | Implement all 5 detectors · REST API endpoints · real-time dashboard |
| **Phase 2** | Alert channels (Slack, PagerDuty, email) · incident workflows · RBAC |
| **Phase 3** | Multi-tenant SaaS · usage billing · public SDK release |

---

## Why AIMO?

Most observability tools tell you a request was slow. AIMO tells you your LLM lied, drifted off-policy, or got jailbroken — and dispatches an incident before it becomes a user complaint.

---

*Built with Spring Boot 3.3 · FastAPI · LangGraph · pgvector · React 18*
