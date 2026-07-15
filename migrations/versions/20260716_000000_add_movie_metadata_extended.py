"""Adiciona título original, ano, idioma e países de origem

Revision ID: 20260716_000000
Revises: 20260714_000000
Create Date: 2026-07-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260716_000000"
down_revision: Union[str, None] = "20260714_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("original_title", sa.String(), nullable=True))
    op.add_column("movies", sa.Column("release_year", sa.Integer(), nullable=True))
    op.add_column("movies", sa.Column("original_language", sa.String(), nullable=True))

    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iso_3166_1", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_countries_iso_3166_1", "countries", ["iso_3166_1"], unique=True)

    op.create_table(
        "movie_countries",
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.PrimaryKeyConstraint("movie_id", "country_id"),
    )
    op.create_index("ix_movie_countries_country_id", "movie_countries", ["country_id"])


def downgrade() -> None:
    op.drop_index("ix_movie_countries_country_id", table_name="movie_countries")
    op.drop_table("movie_countries")

    op.drop_index("ix_countries_iso_3166_1", table_name="countries")
    op.drop_table("countries")

    op.drop_column("movies", "original_language")
    op.drop_column("movies", "release_year")
    op.drop_column("movies", "original_title")
