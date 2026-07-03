-- V2: Incidents + evidence + compliance eval tables
-- ─────────────────────────────────────────────────────────────

CREATE TABLE incidents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID        NOT NULL REFERENCES pipelines(id),
    run_id          UUID        REFERENCES pipeline_runs(id),
    incident_type   VARCHAR(50) NOT NULL
                    CHECK (incident_type IN (
                        'HALLUCINATION',
                        'COST_SPIKE',
                        'COMPLIANCE_DRIFT',
                        'LATENCY_DEGRADATION',
                        'PROMPT_INJECTION'
                    )),
    severity        VARCHAR(5)  NOT NULL CHECK (severity IN ('P0', 'P1', 'P2', 'P3')),
    status          VARCHAR(20) NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'SUPPRESSED')),
    title           TEXT        NOT NULL,
    description     TEXT,
    score           DECIMAL(8,4),
    threshold       DECIMAL(8,4),
    root_cause      TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    acknowledged_by VARCHAR(200)
);

CREATE TABLE incident_evidence (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id   UUID        NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    evidence_type VARCHAR(50) NOT NULL
                  CHECK (evidence_type IN ('INPUT', 'OUTPUT', 'CONTEXT', 'METRIC', 'TRACE', 'PATTERN')),
    content       TEXT,
    metadata      JSONB       NOT NULL DEFAULT '{}'
);

CREATE TABLE eval_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID        NOT NULL REFERENCES pipelines(id),
    dataset_version VARCHAR(20),
    total_cases     INT         NOT NULL,
    auto_scored     INT         NOT NULL,
    passed          INT         NOT NULL,
    failed          INT         NOT NULL,
    compliance_pct  DECIMAL(5,2) NOT NULL,
    trigger         VARCHAR(30)
                    CHECK (trigger IN ('scheduled', 'manual', 'incident_triggered', 'sampling')),
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE eval_case_results (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id   UUID        NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    case_id       VARCHAR(50) NOT NULL,
    category      VARCHAR(50),
    status        VARCHAR(20) CHECK (status IN ('PASS', 'FAIL', 'MANUAL_REVIEW', 'ERROR')),
    violations    TEXT[],
    response      TEXT,
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_incidents_pipeline_type ON incidents(pipeline_id, incident_type, detected_at DESC);
CREATE INDEX idx_incidents_open          ON incidents(status, detected_at DESC) WHERE status = 'OPEN';
CREATE INDEX idx_incidents_severity      ON incidents(severity, detected_at DESC);
CREATE INDEX idx_eval_runs_pipeline      ON eval_runs(pipeline_id, run_at DESC);
