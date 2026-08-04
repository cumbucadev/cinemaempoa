"""Adds movie_inspections: the append-only audit log for the movie
inspector agent (flask_backend/service/movie_inspector.py), which checks
whether a movie's TMDB match is consistent with what cinemas published
about it, and records what it found/fixed for /admin/movies/inspections.

Revision ID: 20260804_000000
Revises: 20260801_000000
Create Date: 2026-08-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260804_000000"
down_revision: Union[str, None] = "20260801_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie_inspections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("checked_tmdb_id", sa.Integer(), nullable=True),
        sa.Column("previous_snapshot", sa.Text(), nullable=True),
        sa.Column("new_snapshot", sa.Text(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_movie_inspections_movie_id", "movie_inspections", ["movie_id"]
    )
    op.create_index(
        "ix_movie_inspections_pipeline_run_id",
        "movie_inspections",
        ["pipeline_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_movie_inspections_pipeline_run_id", table_name="movie_inspections"
    )
    op.drop_index("ix_movie_inspections_movie_id", table_name="movie_inspections")
    op.drop_table("movie_inspections")
