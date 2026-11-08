-- Durable orchestration queue for the single-process Docker service.
-- Existing public service tables are unchanged.
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    stage text NOT NULL CHECK (stage IN ('collect', 'process', 'serve')),
    batch_key text NOT NULL,
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'running', 'succeeded', 'failed')),
    attempts integer NOT NULL DEFAULT 0,
    run_after timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, stage, batch_key)
);
CREATE INDEX IF NOT EXISTS pipeline_jobs_ready_idx
    ON pipeline_jobs (state, run_after, id);
