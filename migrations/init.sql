-- ============================================================
-- Activity Tracker - Database Migrations
-- Run this file once against your PostgreSQL database
-- ============================================================

-- Events table with JSONB payload
CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- GIN index for fast JSONB queries
CREATE INDEX IF NOT EXISTS idx_events_payload ON events USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);

-- ============================================================
-- CDC Audit Table
-- Captures every INSERT / UPDATE / DELETE on the events table
-- ============================================================
CREATE TABLE IF NOT EXISTS events_audit (
    id          BIGSERIAL PRIMARY KEY,
    operation   TEXT NOT NULL,
    changed_at  TIMESTAMPTZ DEFAULT now(),
    changed_by  TEXT DEFAULT current_user,
    old_data    JSONB,
    new_data    JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_operation ON events_audit (operation);
CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON events_audit (changed_at);
CREATE INDEX IF NOT EXISTS idx_audit_new_data ON events_audit USING GIN (new_data);

-- ============================================================
-- CDC Trigger Function
-- Automatically fires on any change to the events table
-- ============================================================
CREATE OR REPLACE FUNCTION audit_events_fn()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO events_audit (operation, new_data)
        VALUES ('INSERT', row_to_json(NEW)::jsonb);
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO events_audit (operation, old_data, new_data)
        VALUES ('UPDATE', row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO events_audit (operation, old_data)
        VALUES ('DELETE', row_to_json(OLD)::jsonb);
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Attach the trigger to the events table
DROP TRIGGER IF EXISTS trg_audit_events ON events;
CREATE TRIGGER trg_audit_events
AFTER INSERT OR UPDATE OR DELETE ON events
FOR EACH ROW EXECUTE FUNCTION audit_events_fn();

-- ============================================================
-- Seed some sample data to test with
-- ============================================================
INSERT INTO events (user_id, event_type, payload) VALUES
(1, 'login',     '{"ip": "192.168.1.1", "country": "IN", "device": "mobile", "status": "success"}'),
(1, 'page_view', '{"ip": "192.168.1.1", "country": "IN", "page": "/dashboard", "duration_ms": 1200}'),
(2, 'login',     '{"ip": "203.0.113.5", "country": "US", "device": "desktop", "status": "failed"}'),
(2, 'purchase',  '{"ip": "203.0.113.5", "country": "US", "amount": 99.99, "item": "Pro Plan"}'),
(3, 'login',     '{"ip": "198.51.100.2","country": "UK", "device": "tablet", "status": "success"}'),
(3, 'logout',    '{"ip": "198.51.100.2","country": "UK", "session_duration_s": 3600}'),
(4, 'purchase',  '{"ip": "10.0.0.5",   "country": "IN", "amount": 49.99, "item": "Basic Plan"}'),
(4, 'login',     '{"ip": "10.0.0.5",   "country": "IN", "device": "mobile", "status": "success"}');
