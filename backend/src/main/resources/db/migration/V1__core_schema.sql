-- V1: Core pipeline registry + telemetry tables
-- ─────────────────────────────────────────────────────────────

CREATE TABLE pipelines (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    node_count      INT,
    environment     VARCHAR(20) NOT NULL DEFAULT 'production'
                    CHECK (environment IN ('production', 'staging', 'dev')),
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE pipeline_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID        NOT NULL REFERENCES pipelines(id),
    external_run_id VARCHAR(200),
    status          VARCHAR(20) NOT NULL
                    CHECK (status IN ('running', 'completed', 'failed', 'timeout')),
    total_cost_usd  DECIMAL(10,6),
    total_tokens    INT,
    latency_ms      INT,
    node_count      INT,
    model_ids       TEXT[],
    input_hash      VARCHAR(64),
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ
);

CREATE TABLE pipeline_spans (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID        NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    node_name         VARCHAR(100) NOT NULL,
    model_id          VARCHAR(100),
    prompt_tokens     INT         NOT NULL DEFAULT 0,
    completion_tokens INT         NOT NULL DEFAULT 0,
    cost_usd          DECIMAL(10,6) NOT NULL DEFAULT 0,
    latency_ms        INT,
    status            VARCHAR(20) CHECK (status IN ('ok', 'error', 'timeout')),
    error             TEXT,
    input_preview     TEXT,
    output_preview    TEXT,
    context_used      BOOLEAN     NOT NULL DEFAULT FALSE,
    started_at        TIMESTAMPTZ NOT NULL
);

-- Indexes for common query patterns
CREATE INDEX idx_pipeline_runs_pipeline_time ON pipeline_runs(pipeline_id, started_at DESC);
CREATE INDEX idx_pipeline_spans_run          ON pipeline_spans(run_id, node_name);
CREATE INDEX idx_pipeline_spans_node_time    ON pipeline_spans(node_name, started_at DESC);
