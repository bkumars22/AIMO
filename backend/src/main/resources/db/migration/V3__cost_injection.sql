-- V3: Cost events + prompt injection attempts
-- ─────────────────────────────────────────────────────────────

CREATE TABLE cost_events (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id         UUID        NOT NULL REFERENCES pipelines(id),
    run_id              UUID        REFERENCES pipeline_runs(id),
    span_id             UUID        REFERENCES pipeline_spans(id),
    model_id            VARCHAR(100) NOT NULL,
    prompt_tokens       INT         NOT NULL,
    completion_tokens   INT         NOT NULL,
    cost_usd            DECIMAL(10,6) NOT NULL,
    baseline_cost_usd   DECIMAL(10,6),
    saved_usd           DECIMAL(10,6),
    latency_ms          INT,
    source              VARCHAR(20) NOT NULL DEFAULT 'span'
                        CHECK (source IN ('span', 'langsmith_bridge')),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE injection_attempts (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id      UUID        NOT NULL REFERENCES pipelines(id),
    run_id           UUID        REFERENCES pipeline_runs(id),
    user_id          VARCHAR(200),
    input_text       TEXT        NOT NULL,
    injection_type   VARCHAR(50)
                     CHECK (injection_type IN (
                         'DIRECT_OVERRIDE',
                         'AUTHORITY_CLAIM',
                         'ROLEPLAY_FRAMING',
                         'HTML_COMMENT',
                         'CODE_BLOCK_BYPASS',
                         'URGENCY_PRESSURE',
                         'EMOTIONAL_MANIPULATION',
                         'MULTILINGUAL_VARIANT',
                         'SYSTEM_TAG',
                         'DAN_MODE'
                     )),
    matched_patterns TEXT[]      NOT NULL DEFAULT '{}',
    similarity_score DECIMAL(5,4),
    blocked          BOOLEAN     NOT NULL DEFAULT FALSE,
    incident_id      UUID        REFERENCES incidents(id),
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_cost_events_pipeline_date    ON cost_events(pipeline_id, recorded_at DESC);
CREATE INDEX idx_cost_events_model            ON cost_events(model_id, recorded_at DESC);
CREATE INDEX idx_injection_user_time          ON injection_attempts(user_id, detected_at DESC);
CREATE INDEX idx_injection_pipeline_time      ON injection_attempts(pipeline_id, detected_at DESC);
CREATE INDEX idx_injection_type               ON injection_attempts(injection_type, detected_at DESC);
