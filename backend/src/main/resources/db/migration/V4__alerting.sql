-- V4: Alert rules + dispatch records
-- ─────────────────────────────────────────────────────────────

CREATE TABLE alert_rules (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID        REFERENCES pipelines(id),   -- NULL = global rule
    incident_type   VARCHAR(50),                              -- NULL = all types
    metric          VARCHAR(100) NOT NULL,
    operator        VARCHAR(5)  NOT NULL CHECK (operator IN ('LT', 'GT', 'EQ', 'GTE', 'LTE')),
    threshold       DECIMAL(10,4) NOT NULL,
    severity        VARCHAR(5)  NOT NULL CHECK (severity IN ('P0', 'P1', 'P2', 'P3')),
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE alert_dispatches (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id   UUID        NOT NULL REFERENCES incidents(id),
    channel       VARCHAR(30) NOT NULL CHECK (channel IN ('webhook', 'email', 'slack', 'redis')),
    destination   TEXT        NOT NULL,
    payload       JSONB       NOT NULL,
    status        VARCHAR(20) CHECK (status IN ('sent', 'failed', 'pending', 'suppressed')),
    sent_at       TIMESTAMPTZ,
    error         TEXT
);

-- Seed default alert rules (global — apply to all pipelines)
INSERT INTO alert_rules (pipeline_id, incident_type, metric, operator, threshold, severity) VALUES
  (NULL, 'PROMPT_INJECTION',       'injection_detected',    'EQ',  1,    'P0'),
  (NULL, 'HALLUCINATION',          'faithfulness_score',    'LT',  0.40, 'P0'),
  (NULL, 'HALLUCINATION',          'faithfulness_score',    'LT',  0.60, 'P1'),
  (NULL, 'HALLUCINATION',          'faithfulness_score',    'LT',  0.70, 'P2'),
  (NULL, 'COMPLIANCE_DRIFT',       'compliance_pct',        'LT',  70.0, 'P0'),
  (NULL, 'COMPLIANCE_DRIFT',       'compliance_pct',        'LT',  80.0, 'P1'),
  (NULL, 'COMPLIANCE_DRIFT',       'compliance_pct',        'LT',  90.0, 'P2'),
  (NULL, 'COST_SPIKE',             'cost_multiplier',       'GT',  10.0, 'P0'),
  (NULL, 'COST_SPIKE',             'cost_multiplier',       'GT',  5.0,  'P1'),
  (NULL, 'COST_SPIKE',             'cost_multiplier',       'GT',  3.0,  'P2'),
  (NULL, 'LATENCY_DEGRADATION',    'latency_multiplier',    'GT',  5.0,  'P0'),
  (NULL, 'LATENCY_DEGRADATION',    'latency_multiplier',    'GT',  3.0,  'P1'),
  (NULL, 'LATENCY_DEGRADATION',    'latency_multiplier',    'GT',  2.0,  'P2');

-- Indexes
CREATE INDEX idx_alert_rules_pipeline_type ON alert_rules(pipeline_id, incident_type) WHERE enabled = TRUE;
CREATE INDEX idx_alert_dispatches_incident ON alert_dispatches(incident_id, sent_at DESC);
