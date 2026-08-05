"""One-off backfill: clears stale metadata fetch-attempt history for movies
that already have TMDB-derived metadata (directors/genres/original_title)
but no tmdb_id.

These rows are relics of the pre-#295 metadata pipeline, which upserted
directors/genres on a successful TMDB match without ever recording the
match's tmdb_id. The current pipeline (flask_backend.service.
movie_metadata_pipeline) skips any movie with an existing fetch attempt,
so these movies are stuck forever with metadata but no tmdb_id - and
never become eligible for `flask inspect-movies`, which requires tmdb_id.

Deleting their attempt log lets `flask fetch-movie-metadata` pick them
back up and search TMDB again, this time persisting tmdb_id.

Usage (via CLI):
    flask tmdb-id-backfill          # dry-run, prints the plan only
    flask tmdb-id-backfill --apply  # deletes the stale attempt rows
"""

import click

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieMetadataFetchAttempt


def _movies_with_stale_metadata() -> list[Movie]:
    return (
        db_session.query(Movie)
        .filter(
            Movie.tmdb_id.is_(None),
            (Movie.directors.any())
            | (Movie.genres.any())
            | (Movie.original_title.isnot(None)),
        )
        .order_by(Movie.id)
        .all()
    )


def tmdb_id_backfill(apply: bool = False) -> None:
    movies = _movies_with_stale_metadata()

    click.echo("=== Backfill de tmdb_id ===\n")
    click.echo(f"Filmes com metadados TMDB mas sem tmdb_id: {len(movies)}\n")

    if movies:
        click.echo("--- Exemplos ---")
        for movie in movies[:10]:
            directors = ", ".join(d.name for d in movie.directors)
            click.echo(f'  Movie #{movie.id} "{movie.title}" (diretor: {directors})')
        if len(movies) > 10:
            click.echo(f"  ... e mais {len(movies) - 10}")
        click.echo("")

    click.echo(f"{'=' * 60}")

    if not apply:
        click.echo(
            "\nModo dry-run: nenhuma alteração foi feita. Use --apply para aplicar."
        )
        return

    if not movies:
        click.echo("\nNada para aplicar.")
        return

    movie_ids = [movie.id for movie in movies]
    deleted = (
        db_session.query(MovieMetadataFetchAttempt)
        .filter(MovieMetadataFetchAttempt.movie_id.in_(movie_ids))
        .delete(synchronize_session=False)
    )
    db_session.commit()

    click.echo(
        f"\nAplicado: {deleted} tentativa(s) removida(s) para {len(movies)} filme(s). "
        "Rode 'flask fetch-movie-metadata' para tentar novamente."
    )
