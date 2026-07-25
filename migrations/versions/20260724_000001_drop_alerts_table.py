"""Removes the old alerts table and its generation-pipeline bookkeeping
columns (issue #258). The Alert model/pipeline is fully replaced by
alert_actions (added in 20260724_000000) plus the live-computed Pendentes
view - see docs/superpowers/specs/2026-07-24-admin-alerts-usability-design.md.

Revision ID: 20260724_000001
Revises: 20260724_000000
Create Date: 2026-07-24 00:00:01.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260724_000001"
down_revision: Union[str, None] = "20260724_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_alerts_pipeline_run_id", table_name="alerts")
    op.drop_index("ix_alerts_dedup_key", table_name="alerts")
    op.drop_index("ix_alerts_screening_id", table_name="alerts")
    op.drop_index("ix_alerts_movie_id", table_name="alerts")
    op.drop_index("ix_alerts_rule_name", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_screenings_core_alerts_evaluated_at", table_name="screenings")
    op.drop_column("screenings", "core_alerts_evaluated_at")

    op.drop_index("ix_movies_metadata_alerts_evaluated_at", table_name="movies")
    op.drop_column("movies", "metadata_alerts_evaluated_at")


def downgrade() -> None:
    op.add_column(
        "movies",
        sa.Column("metadata_alerts_evaluated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_movies_metadata_alerts_evaluated_at",
        "movies",
        ["metadata_alerts_evaluated_at"],
    )

    op.add_column(
        "screenings",
        sa.Column("core_alerts_evaluated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_screenings_core_alerts_evaluated_at",
        "screenings",
        ["core_alerts_evaluated_at"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_name", sa.String(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("screening_id", sa.Integer(), nullable=True),
        sa.Column("dedup_key", sa.String(), nullable=False),
        sa.Column("drafted_text", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["screening_id"], ["screenings.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_rule_name", "alerts", ["rule_name"])
    op.create_index("ix_alerts_movie_id", "alerts", ["movie_id"])
    op.create_index("ix_alerts_screening_id", "alerts", ["screening_id"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["dedup_key"], unique=True)
    op.create_index("ix_alerts_pipeline_run_id", "alerts", ["pipeline_run_id"])
