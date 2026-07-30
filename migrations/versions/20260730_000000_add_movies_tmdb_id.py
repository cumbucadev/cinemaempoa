"""Adds movies.tmdb_id so an admin can pin a Movie to a specific TMDB
entry from the web UI - see
docs/superpowers/specs/2026-07-30-movie-tmdb-metadata-edit-design.md.

Revision ID: 20260730_000000
Revises: 20260727_000001
Create Date: 2026-07-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260730_000000"
down_revision: Union[str, None] = "20260727_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("tmdb_id", sa.Integer(), nullable=True))
    op.create_index("ix_movies_tmdb_id", "movies", ["tmdb_id"])


def downgrade() -> None:
    op.drop_index("ix_movies_tmdb_id", table_name="movies")
    op.drop_column("movies", "tmdb_id")
