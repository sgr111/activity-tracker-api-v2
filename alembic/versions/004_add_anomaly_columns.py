"""add anomaly_score and is_anomaly columns to events

Revision ID: 004
Revises: 003
Create Date: 2025-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision:      str                          = "004"
down_revision: Union[str, None]             = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events",
        sa.Column("anomaly_score", sa.Float(), nullable=True))
    op.add_column("events",
        sa.Column("is_anomaly", sa.Boolean(), server_default="false", nullable=False))

    op.create_index("idx_events_is_anomaly", "events", ["is_anomaly"])


def downgrade() -> None:
    op.drop_index("idx_events_is_anomaly", table_name="events")
    op.drop_column("events", "is_anomaly")
    op.drop_column("events", "anomaly_score")
