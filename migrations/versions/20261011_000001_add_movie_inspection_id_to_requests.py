"""Adds movie_inspection_requests.movie_inspection_id: the audit row
apply_verdict recorded when it closed the request, so a retried call can
answer with it instead of writing a second one.

Revision ID: 20261011_000001
Revises: 20261011_000000
Create Date: 2026-10-11 00:00:01.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261011_000001"
down_revision: Union[str, None] = "20261011_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("movie_inspection_requests") as batch_op:
        batch_op.add_column(
            sa.Column("movie_inspection_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_movie_inspection_requests_movie_inspection_id",
            "movie_inspections",
            ["movie_inspection_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("movie_inspection_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_movie_inspection_requests_movie_inspection_id", type_="foreignkey"
        )
        batch_op.drop_column("movie_inspection_id")
