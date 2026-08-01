"""Adds movies.tmdb_excluded so an admin can mark a movie as confirmed
absent from TMDB when removing an incorrect link - the metadata pipeline
must not try to re-attach TMDB data to it afterwards.

Revision ID: 20260801_000000
Revises: 20260730_000000
Create Date: 2026-08-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260801_000000"
down_revision: Union[str, None] = "20260730_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "movies",
        sa.Column(
            "tmdb_excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("movies", "tmdb_excluded")
