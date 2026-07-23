"""initial tables - events, events_audit, CDC trigger

Revision ID: 001
Revises:
Create Date: 2025-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision:       str                     = "001"
down_revision:  Union[str, None]        = None
branch_labels:  Union[str, Sequence[str], None] = None
depends_on:     Union[str, Sequence[str], None] = None

#alembic revision --autogenerate -m "initial tables - events, events_audit, CDC trigger"
def upgrade() -> None:
    # ── events table ───────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id",         sa.Integer(),                    nullable=False),
        sa.Column("user_id",    sa.Integer(),                    nullable=False),
        sa.Column("event_type", sa.String(),                     nullable=False),
        sa.Column("payload",    JSONB(),                         nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),      server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),      server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_events_user_id", "events", ["user_id"])
    op.create_index("idx_events_type",    "events", ["event_type"])
    op.create_index(
        "idx_events_payload", "events", ["payload"],
        postgresql_using="gin"
    )

    # ── events_audit table ─────────────────────────────────
    # The events_audit table is used for Change Data Capture (CDC) 
    # to track changes in the events table.
    op.create_table(
        "events_audit",
        sa.Column("id",         sa.Integer(),               nullable=False),
        sa.Column("operation",  sa.String(),                nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("changed_by", sa.Text(),                  nullable=True),
        sa.Column("old_data",   JSONB(),                    nullable=True),
        sa.Column("new_data",   JSONB(),                    nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_operation",  "events_audit", ["operation"])
    op.create_index("idx_audit_changed_at", "events_audit", ["changed_at"])
    op.create_index(
        "idx_audit_new_data", "events_audit", ["new_data"],
        postgresql_using="gin"
    )

    # ── CDC trigger function + trigger ─────────────────────
    # The audit_events_fn() function is a PostgreSQL trigger function 
    # that captures changes in the events table and 
    # logs them into the events_audit table.
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

    op.execute("""
        DROP TRIGGER IF EXISTS trg_audit_events ON events;
        CREATE TRIGGER trg_audit_events
        AFTER INSERT OR UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION audit_events_fn();
    """)

#  this is the downgrade function to reverse the changes
#  made in the upgrade function
def downgrade() -> None: 
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events ON events;")
    op.execute("DROP FUNCTION IF EXISTS audit_events_fn;")
    op.drop_table("events_audit")
    op.drop_table("events")
