-- V5: pgvector extension + embedding tables + IVFFlat indexes
-- ─────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS vector;

-- Response embeddings — for compliance drift detection
-- Label 'compliant' = known-good responses (seeded from golden_dataset PASSes)
-- Label 'baseline'  = running average of production responses
CREATE TABLE response_embeddings (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id   UUID        NOT NULL REFERENCES pipelines(id),
    run_id        UUID        REFERENCES pipeline_runs(id),
    node_name     VARCHAR(100),
    embedding     vector(384) NOT NULL,   -- all-MiniLM-L6-v2
    input_hash    VARCHAR(64),
    label         VARCHAR(30)
                  CHECK (label IN ('compliant', 'non_compliant', 'baseline', 'injection')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Known injection input vectors — seeded from ARIA golden_dataset adversarial cases
CREATE TABLE injection_vectors (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding      vector(384) NOT NULL,
    injection_type VARCHAR(50) NOT NULL,
    source_text    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- IVFFlat indexes for fast approximate nearest-neighbour search
-- lists=100 is recommended for tables up to ~1M rows
CREATE INDEX idx_response_embeddings_cosine
    ON response_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX idx_injection_vectors_cosine
    ON injection_vectors USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- Supporting indexes
CREATE INDEX idx_response_embeddings_pipeline_label
    ON response_embeddings(pipeline_id, label, created_at DESC);
