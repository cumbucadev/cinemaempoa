"""Adds movies.pipeline_run_id so a pipeline run can be credited with
creating a specific movie, the same way screenings.pipeline_run_id already
works - see docs/superpowers/specs/2026-07-27-scraper-import-counters-design.md.

Revision ID: 20260727_000000
Revises: 20260726_000000
Create Date: 2026-07-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260727_000000"
down_revision: Union[str, None] = "20260726_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("pipeline_run_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("movies") as batch_op:
        batch_op.create_foreign_key(
            "fk_movies_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index("ix_movies_pipeline_run_id", "movies", ["pipeline_run_id"])


def downgrade() -> None:
    op.drop_index("ix_movies_pipeline_run_id", table_name="movies")
    with op.batch_alter_table("movies") as batch_op:
        batch_op.drop_constraint(
            "fk_movies_pipeline_run_id_pipeline_runs", type_="foreignkey"
        )
    op.drop_column("movies", "pipeline_run_id")
