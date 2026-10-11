"""Adds movie_inspection_requests: one row per movie inspection run from
outside the Flask process (the Orbit agent, through the MCP server), holding
the tmdb_id being checked and the tmdb ids the agent observed between tool
calls.

Revision ID: 20261011_000000
Revises: 20260805_000000
Create Date: 2026-10-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261011_000000"
down_revision: Union[str, None] = "20260805_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie_inspection_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("checked_tmdb_id", sa.Integer(), nullable=True),
        sa.Column("observed_tmdb_ids", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_movie_inspection_requests_movie_id",
        "movie_inspection_requests",
        ["movie_id"],
    )
    op.create_index(
        "ix_movie_inspection_requests_pipeline_run_id",
        "movie_inspection_requests",
        ["pipeline_run_id"],
    )
    op.create_index(
        "ix_movie_inspection_requests_status",
        "movie_inspection_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_movie_inspection_requests_status", table_name="movie_inspection_requests"
    )
    op.drop_index(
        "ix_movie_inspection_requests_pipeline_run_id",
        table_name="movie_inspection_requests",
    )
    op.drop_index(
        "ix_movie_inspection_requests_movie_id", table_name="movie_inspection_requests"
    )
    op.drop_table("movie_inspection_requests")
