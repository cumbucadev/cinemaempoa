"""add gemini_usage_events table

Revision ID: 78333c8ba406
Revises: 20260804_000000
Create Date: 2026-08-05 12:22:13.572558

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "78333c8ba406"
down_revision: Union[str, None] = "20260804_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gemini_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("quota_metric", sa.String(), nullable=True),
        sa.Column("unavailable_until", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gemini_usage_events_model_id", "gemini_usage_events", ["model_id"]
    )
    op.create_index(
        "ix_gemini_usage_events_occurred_at", "gemini_usage_events", ["occurred_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gemini_usage_events_occurred_at", table_name="gemini_usage_events"
    )
    op.drop_index("ix_gemini_usage_events_model_id", table_name="gemini_usage_events")
    op.drop_table("gemini_usage_events")
