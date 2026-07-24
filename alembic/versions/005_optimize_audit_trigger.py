"""optimize audit trigger - skip no-op UPDATE logging

Revision ID: 005
Revises: 004
Create Date: 2026-07-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision:      str                          = "005"
down_revision: Union[str, None]             = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Overwrites the existing audit_events_fn() from migration 001.
    # Only change: the UPDATE branch now skips logging when nothing
    # actually changed (IS DISTINCT FROM is NULL-safe, unlike !=).
    # INSERT and DELETE branches are unchanged.
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_events_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                INSERT INTO events_audit (operation, new_data)
                VALUES ('INSERT', row_to_json(NEW)::jsonb);
                RETURN NEW;
            ELSIF TG_OP = 'UPDATE' THEN
                IF OLD IS DISTINCT FROM NEW THEN
                    INSERT INTO events_audit (operation, old_data, new_data)
                    VALUES ('UPDATE', row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                INSERT INTO events_audit (operation, old_data)
                VALUES ('DELETE', row_to_json(OLD)::jsonb);
                RETURN OLD;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Restores the original unconditional-logging version from migration 001.
    op.execute("""
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
    """)
