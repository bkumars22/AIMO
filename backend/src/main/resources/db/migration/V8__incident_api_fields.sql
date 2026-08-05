-- V8: Reconcile `incidents` table with the Java entity (com.aimo.entity.Incident).
--
-- The Python ai-engine (storage/database.py) and the Java backend
-- (entity/Incident.java) evolved independently against the same table:
-- ai-engine writes description/score/threshold/detected_at/acknowledged_*,
-- while the JPA entity expects created_at/updated_at/suggested_fix/
-- resolution_notes/resolved_by/false_positive/evidence. Hibernate's
-- ddl-auto=validate failed startup entirely on the missing columns below.
-- Adding them (nullable, additive) unblocks the backend without touching
-- the columns the detector pipeline already depends on.

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS suggested_fix   TEXT,
    ADD COLUMN IF NOT EXISTS resolution_notes TEXT,
    ADD COLUMN IF NOT EXISTS resolved_by     VARCHAR(200),
    ADD COLUMN IF NOT EXISTS false_positive  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS evidence        JSONB;

-- Backfill created_at from the existing detected_at so pre-V8 rows (if any)
-- don't all collapse to the same migration timestamp.
UPDATE incidents SET created_at = detected_at, updated_at = detected_at
WHERE created_at = updated_at;
