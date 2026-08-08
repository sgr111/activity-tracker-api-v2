"""create llm_calls table for llm-observability logging

Revision ID: 007
Revises: 006
Create Date: 2026-08-07

Adds the llm_calls table that llm_observability.track_llm_call() writes to
via ObservabilityCallback (services/observability.py), now that db_session
is wired in (routers/events.py passes get_logging_session() into
natural_language_to_sql/summarise_events/rag_answer). Until this migration
runs, those calls fail-open to console/JSON logging instead — this table
existing is what switches that over to real persisted rows.

Schema matches llm_observability's own LLMCallLog model
(llm_observability/models.py) / migrations/001_create_llm_calls_table.sql
in the sgr111/llm-observability repo.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision:      str                             = "007"
down_revision: Union[str, None]                = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("feature", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_name", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("guardrail_flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("extra_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_llm_calls_project_feature", "llm_calls", ["project", "feature"]
    )
    op.create_index("idx_llm_calls_created_at", "llm_calls", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_llm_calls_created_at", table_name="llm_calls")
    op.drop_index("idx_llm_calls_project_feature", table_name="llm_calls")
    op.drop_table("llm_calls")
