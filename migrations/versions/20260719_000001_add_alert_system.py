"""Adiciona sistema de alertas (filme novo, sessão única, sessão comentada,
mostra, diretor estreante/recorrente, nova combinação de gênero,
sequência/franquia via coleções do TMDB)

Revision ID: 20260719_000001
Revises: 20260719_000000
Create Date: 2026-07-19 16:14:31.804615

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260719_000001"
down_revision: Union[str, None] = "20260719_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collections_tmdb_id", "collections", ["tmdb_id"], unique=True)

    op.add_column("movies", sa.Column("collection_id", sa.Integer(), nullable=True))
    # SQLite can't ALTER in a constraint outside of batch mode.
    with op.batch_alter_table("movies") as batch_op:
        batch_op.create_foreign_key(
            "fk_movies_collection_id_collections",
            "collections",
            ["collection_id"],
            ["id"],
        )
    op.create_index("ix_movies_collection_id", "movies", ["collection_id"])

    # created_at: SQLite can't ADD COLUMN with a non-constant (function)
    # default in a single statement, so add it nullable, backfill via
    # UPDATE, then tighten to NOT NULL via batch mode. Matches the app's
    # convention of setting created_at explicitly in Python for all future
    # rows (see BlogPost.created_at), while still requiring a value for
    # rows that predate this migration.
    op.add_column("movies", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE movies SET created_at = CURRENT_TIMESTAMP")
    with op.batch_alter_table("movies") as batch_op:
        batch_op.alter_column("created_at", nullable=False)

    op.add_column(
        "movies",
        sa.Column("metadata_alerts_evaluated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_movies_metadata_alerts_evaluated_at",
        "movies",
        ["metadata_alerts_evaluated_at"],
    )

    op.add_column("screenings", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE screenings SET created_at = CURRENT_TIMESTAMP")
    with op.batch_alter_table("screenings") as batch_op:
        batch_op.alter_column("created_at", nullable=False)

    op.add_column("screenings", sa.Column("raw_title", sa.String(), nullable=True))
    op.add_column(
        "screenings", sa.Column("title_cleaning_rules", sa.String(), nullable=True)
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
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["screening_id"], ["screenings.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_rule_name", "alerts", ["rule_name"])
    op.create_index("ix_alerts_movie_id", "alerts", ["movie_id"])
    op.create_index("ix_alerts_screening_id", "alerts", ["screening_id"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["dedup_key"], unique=True)

    # Backfill: mark all pre-existing screenings/movies as already evaluated
    # so the alert pipeline's first run doesn't flood /admin/alerts with
    # alerts about years of past programming. Movies that exist but don't
    # yet have a director are deliberately left un-evaluated - they're
    # legitimately "new" from the alert system's point of view once the
    # metadata pipeline catches up to them.
    op.execute(
        "UPDATE screenings SET core_alerts_evaluated_at = CURRENT_TIMESTAMP "
        "WHERE core_alerts_evaluated_at IS NULL"
    )
    op.execute(
        "UPDATE movies SET metadata_alerts_evaluated_at = CURRENT_TIMESTAMP "
        "WHERE id IN (SELECT movie_id FROM movie_directors) "
        "AND metadata_alerts_evaluated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_dedup_key", table_name="alerts")
    op.drop_index("ix_alerts_screening_id", table_name="alerts")
    op.drop_index("ix_alerts_movie_id", table_name="alerts")
    op.drop_index("ix_alerts_rule_name", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_screenings_core_alerts_evaluated_at", table_name="screenings")
    op.drop_column("screenings", "core_alerts_evaluated_at")
    op.drop_column("screenings", "title_cleaning_rules")
    op.drop_column("screenings", "raw_title")
    op.drop_column("screenings", "created_at")

    op.drop_index("ix_movies_metadata_alerts_evaluated_at", table_name="movies")
    op.drop_column("movies", "metadata_alerts_evaluated_at")
    op.drop_column("movies", "created_at")

    op.drop_index("ix_movies_collection_id", table_name="movies")
    with op.batch_alter_table("movies") as batch_op:
        batch_op.drop_constraint(
            "fk_movies_collection_id_collections", type_="foreignkey"
        )
    op.drop_column("movies", "collection_id")

    op.drop_index("ix_collections_tmdb_id", table_name="collections")
    op.drop_table("collections")
