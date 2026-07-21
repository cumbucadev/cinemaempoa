"""Adds pipeline run tracking (pipeline_runs table) so the admin dashboard
can show pipeline health (did it run, when, did it succeed) and correlate
what each run touched, by tagging screenings, alerts,
movie_metadata_fetch_attempts and poster_fetch_attempts rows with the run
that created them.

Revision ID: 20260721_000000
Revises: 20260719_000001
Create Date: 2026-07-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260721_000000"
down_revision: Union[str, None] = "20260719_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pipeline_runs_pipeline_name", "pipeline_runs", ["pipeline_name"]
    )

    op.add_column(
        "screenings", sa.Column("pipeline_run_id", sa.Integer(), nullable=True)
    )
    with op.batch_alter_table("screenings") as batch_op:
        batch_op.create_foreign_key(
            "fk_screenings_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index("ix_screenings_pipeline_run_id", "screenings", ["pipeline_run_id"])

    op.add_column("alerts", sa.Column("pipeline_run_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.create_foreign_key(
            "fk_alerts_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index("ix_alerts_pipeline_run_id", "alerts", ["pipeline_run_id"])

    op.add_column(
        "movie_metadata_fetch_attempts",
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("movie_metadata_fetch_attempts") as batch_op:
        batch_op.create_foreign_key(
            "fk_movie_metadata_fetch_attempts_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index(
        "ix_movie_metadata_fetch_attempts_pipeline_run_id",
        "movie_metadata_fetch_attempts",
        ["pipeline_run_id"],
    )

    op.add_column(
        "poster_fetch_attempts",
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("poster_fetch_attempts") as batch_op:
        batch_op.create_foreign_key(
            "fk_poster_fetch_attempts_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index(
        "ix_poster_fetch_attempts_pipeline_run_id",
        "poster_fetch_attempts",
        ["pipeline_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_poster_fetch_attempts_pipeline_run_id", table_name="poster_fetch_attempts"
    )
    with op.batch_alter_table("poster_fetch_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_poster_fetch_attempts_pipeline_run_id_pipeline_runs",
            type_="foreignkey",
        )
    op.drop_column("poster_fetch_attempts", "pipeline_run_id")

    op.drop_index(
        "ix_movie_metadata_fetch_attempts_pipeline_run_id",
        table_name="movie_metadata_fetch_attempts",
    )
    with op.batch_alter_table("movie_metadata_fetch_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_movie_metadata_fetch_attempts_pipeline_run_id_pipeline_runs",
            type_="foreignkey",
        )
    op.drop_column("movie_metadata_fetch_attempts", "pipeline_run_id")

    op.drop_index("ix_alerts_pipeline_run_id", table_name="alerts")
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_constraint(
            "fk_alerts_pipeline_run_id_pipeline_runs", type_="foreignkey"
        )
    op.drop_column("alerts", "pipeline_run_id")

    op.drop_index("ix_screenings_pipeline_run_id", table_name="screenings")
    with op.batch_alter_table("screenings") as batch_op:
        batch_op.drop_constraint(
            "fk_screenings_pipeline_run_id_pipeline_runs", type_="foreignkey"
        )
    op.drop_column("screenings", "pipeline_run_id")

    op.drop_index("ix_pipeline_runs_pipeline_name", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
