-- V6: users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          VARCHAR(32)  NOT NULL DEFAULT 'PIPELINE_OWNER'
                  CHECK (role IN ('ADMIN', 'PIPELINE_OWNER', 'VIEWER')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default admin (password set via AIMO_ADMIN_PASSWORD env at first startup)
-- Password must be BCrypt-hashed at deploy time
-- Example seed (password = 'changeme123' — MUST be changed in production):
-- INSERT INTO users (email, password_hash, role)
-- VALUES ('admin@aimo.internal', '$2a$10$...', 'ADMIN')
-- ON CONFLICT DO NOTHING;
