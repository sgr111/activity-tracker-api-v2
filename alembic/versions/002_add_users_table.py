"""add users table and owner_id FK on events

Revision ID: 002
Revises: 001
Create Date: 2025-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision:       str                          = "002"
down_revision:  Union[str, None]             = "001"
branch_labels:  Union[str, Sequence[str], None] = None
depends_on:     Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users table ────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",              sa.Integer(),               nullable=False),
        sa.Column("email",           sa.String(),                nullable=False),
        sa.Column("hashed_password", sa.Text(),                  nullable=False),
        sa.Column("is_active",       sa.Boolean(),               server_default="true"),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # ── add owner_id FK to events ──────────────────────────
    op.add_column(
        "events",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
    )
    op.create_index("idx_events_owner_id", "events", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_events_owner_id", table_name="events")
    op.drop_column("events", "owner_id")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
