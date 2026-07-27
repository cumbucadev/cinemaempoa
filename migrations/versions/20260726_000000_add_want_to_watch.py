"""Adds want_to_watch: the anonymous per-visitor "want to watch" mark on
the reels homepage star button - see
docs/superpowers/specs/2026-07-26-want-to-watch-design.md.

Revision ID: 20260726_000000
Revises: 20260724_000001
Create Date: 2026-07-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260726_000000"
down_revision: Union[str, None] = "20260724_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "want_to_watch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("visitor_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("movie_id", "visitor_id"),
    )
    op.create_index("ix_want_to_watch_movie_id", "want_to_watch", ["movie_id"])
    op.create_index("ix_want_to_watch_visitor_id", "want_to_watch", ["visitor_id"])


def downgrade() -> None:
    op.drop_index("ix_want_to_watch_visitor_id", table_name="want_to_watch")
    op.drop_index("ix_want_to_watch_movie_id", table_name="want_to_watch")
    op.drop_table("want_to_watch")
