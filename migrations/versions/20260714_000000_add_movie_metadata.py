"""Adiciona metadados de filme (diretores, gêneros)

Revision ID: 20260714_000000
Revises: 20260205_000000
Create Date: 2026-07-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260714_000000"
down_revision: Union[str, None] = "20260205_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "genres",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_genres_tmdb_id", "genres", ["tmdb_id"], unique=True
    )

    op.create_table(
        "directors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_directors_tmdb_id", "directors", ["tmdb_id"], unique=True
    )

    op.create_table(
        "movie_genres",
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("genre_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["genre_id"], ["genres.id"]),
        sa.PrimaryKeyConstraint("movie_id", "genre_id"),
    )
    op.create_index(
        "ix_movie_genres_genre_id", "movie_genres", ["genre_id"]
    )

    op.create_table(
        "movie_directors",
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("director_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["director_id"], ["directors.id"]),
        sa.PrimaryKeyConstraint("movie_id", "director_id"),
    )
    op.create_index(
        "ix_movie_directors_director_id", "movie_directors", ["director_id"]
    )

    op.create_table(
        "movie_metadata_fetch_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_movie_metadata_fetch_attempts_movie_id",
        "movie_metadata_fetch_attempts",
        ["movie_id"],
    )
    op.create_index(
        "ix_movie_metadata_fetch_attempts_source",
        "movie_metadata_fetch_attempts",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_movie_metadata_fetch_attempts_source",
        table_name="movie_metadata_fetch_attempts",
    )
    op.drop_index(
        "ix_movie_metadata_fetch_attempts_movie_id",
        table_name="movie_metadata_fetch_attempts",
    )
    op.drop_table("movie_metadata_fetch_attempts")

    op.drop_index("ix_movie_directors_director_id", table_name="movie_directors")
    op.drop_table("movie_directors")

    op.drop_index("ix_movie_genres_genre_id", table_name="movie_genres")
    op.drop_table("movie_genres")

    op.drop_index("ix_directors_tmdb_id", table_name="directors")
    op.drop_table("directors")

    op.drop_index("ix_genres_tmdb_id", table_name="genres")
    op.drop_table("genres")
