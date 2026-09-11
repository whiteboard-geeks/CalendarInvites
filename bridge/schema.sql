-- Additive v1; run explicitly before starting API/worker. No historical adoption.
CREATE TABLE IF NOT EXISTS bridge_schema (version integer PRIMARY KEY);
INSERT INTO bridge_schema VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS bridge_rotation (
 consultant text PRIMARY KEY, cursor bigint NOT NULL DEFAULT 0,
 mailbox_cursors jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS bridge_senders (
 id text PRIMARY KEY, account jsonb NOT NULL, disabled boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS bridge_caps (
 sender text NOT NULL REFERENCES bridge_senders(id), day date NOT NULL,
 used integer NOT NULL CHECK (used >= 0), PRIMARY KEY(sender, day)
);
CREATE TABLE IF NOT EXISTS bridge_meetings (
 operation text PRIMARY KEY, consultant text NOT NULL, task_id text NOT NULL,
 sender text NOT NULL REFERENCES bridge_senders(id), group_name text NOT NULL,
 start_at timestamptz NOT NULL, end_at timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'reserved', data jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(consultant, task_id), CHECK(end_at > start_at)
);
CREATE TABLE IF NOT EXISTS bridge_jobs (
 operation text PRIMARY KEY REFERENCES bridge_meetings(operation),
 due_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz,
 lease_token text, attempts integer NOT NULL DEFAULT 0, last_error text
);
CREATE INDEX IF NOT EXISTS bridge_jobs_due ON bridge_jobs(due_at);
CREATE TABLE IF NOT EXISTS bridge_audit (
 id bigserial PRIMARY KEY, operation text, action text NOT NULL,
 detail jsonb NOT NULL DEFAULT '{}', at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bridge_worker_health (
 name text PRIMARY KEY, seen_at timestamptz NOT NULL DEFAULT now()
);
