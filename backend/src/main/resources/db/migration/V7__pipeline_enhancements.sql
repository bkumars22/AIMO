-- V7: Pipeline schema enhancements for health tracking and demo seeder
ALTER TABLE pipelines
    ADD COLUMN IF NOT EXISTS health_score    INT          DEFAULT 100,
    ADD COLUMN IF NOT EXISTS api_key_hash    VARCHAR(64),
    ADD COLUMN IF NOT EXISTS owner_email     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ  DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ  DEFAULT NOW();

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS cost_usd           DECIMAL(10,6),
    ADD COLUMN IF NOT EXISTS faithfulness_score DECIMAL(5,4);

CREATE INDEX IF NOT EXISTS idx_pipelines_owner ON pipelines(owner_email);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_cost ON pipeline_runs(pipeline_id, cost_usd);
