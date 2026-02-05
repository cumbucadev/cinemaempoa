"""Adiciona tabela poster_fetch_attempts

Revision ID: 20260205_000000
Revises: 20251124_201556
Create Date: 2026-02-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260205_000000"
down_revision: Union[str, None] = "20251124_201556"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "poster_fetch_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screening_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["screening_id"],
            ["screenings.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_poster_fetch_attempts_screening_id",
        "poster_fetch_attempts",
        ["screening_id"],
    )
    op.create_index(
        "ix_poster_fetch_attempts_source",
        "poster_fetch_attempts",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("ix_poster_fetch_attempts_source", table_name="poster_fetch_attempts")
    op.drop_index(
        "ix_poster_fetch_attempts_screening_id", table_name="poster_fetch_attempts"
    )
    op.drop_table("poster_fetch_attempts")
