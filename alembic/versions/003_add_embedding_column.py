"""add embedding vector column to events

Revision ID: 003
Revises: 002
Create Date: 2025-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision:      str                          = "003"
down_revision: Union[str, None]             = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 3072 dims (gemini-embedding-001)
    # No ANN index — pgvector HNSW/IVFFlat both cap at 2000 dims
    # Exact cosine search is fine for small-medium datasets
    op.execute("""
        ALTER TABLE events
        ADD COLUMN IF NOT EXISTS embedding vector(3072);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS embedding;")