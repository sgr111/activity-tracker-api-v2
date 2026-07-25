"""fix audit trigger - exclude updated_at from the no-op comparison

Revision ID: 006
Revises: 005
Create Date: 2026-07-26

updated_at has onupdate=func.now() in the SQLAlchemy model, so it changes
on EVERY UPDATE statement regardless of whether any real data changed.
Migration 005's `OLD IS DISTINCT FROM NEW` check compares the whole row,
including updated_at — which meant it was always true, defeating the
optimization entirely. This migration excludes updated_at (and created_at,
which should never change anyway) from the comparison using jsonb subtraction.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision:      str                          = "006"
down_revision: Union[str, None]             = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_events_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                INSERT INTO events_audit (operation, new_data)
                VALUES ('INSERT', row_to_json(NEW)::jsonb);
                RETURN NEW;
            ELSIF TG_OP = 'UPDATE' THEN
                IF (to_jsonb(OLD) - 'updated_at' - 'created_at')
                   IS DISTINCT FROM
                   (to_jsonb(NEW) - 'updated_at' - 'created_at') THEN
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
    # Restore migration 005's version (compares whole row, including updated_at)
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
