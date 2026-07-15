"""Deletes a single movie and every row that depends on it (screenings,
screening dates, poster/metadata fetch attempts). Genre/director/country
association rows are dropped automatically by SQLAlchemy when the movie is
deleted - the Genre/Director/Country rows themselves are never touched, since
they're shared across movies.

Usage (via CLI):
    flask delete-movie <id>          # prints the movie, asks for confirmation
    flask delete-movie <id> --yes    # skips the confirmation prompt
"""

import click

from flask_backend.models import Movie
from flask_backend.repository.movies import delete as delete_movie_row
from flask_backend.repository.movies import get_by_id


def _print_movie(movie: Movie) -> None:
    click.echo(f'Movie #{movie.id} - "{movie.title}"')
    if movie.slug:
        click.echo(f"  slug: {movie.slug}")
    if movie.original_title:
        click.echo(f"  título original: {movie.original_title}")
    if movie.release_year:
        click.echo(f"  ano: {movie.release_year}")
    if movie.original_language:
        click.echo(f"  idioma original: {movie.original_language}")
    if movie.directors:
        click.echo(f"  diretor(es): {', '.join(d.name for d in movie.directors)}")
    if movie.genres:
        click.echo(f"  gênero(s): {', '.join(g.name for g in movie.genres)}")
    if movie.countries:
        click.echo(f"  país(es): {', '.join(c.name for c in movie.countries)}")

    if not movie.screenings:
        click.echo("  sessões: nenhuma")
        return

    click.echo(f"  sessões ({len(movie.screenings)}):")
    for screening in movie.screenings:
        dates = ", ".join(
            f"{d.date}{' ' + d.time if d.time else ''}" for d in screening.dates
        )
        status = "rascunho" if screening.draft else "publicada"
        click.echo(
            f"    Screening #{screening.id} - cinema: {screening.cinema.name} "
            f"[{status}] - datas: {dates or 'nenhuma'}"
        )


def delete_movie(movie_id: int, skip_confirmation: bool = False) -> bool:
    movie = get_by_id(movie_id)
    if movie is None:
        click.echo(f"Filme #{movie_id} não encontrado.", err=True)
        return False

    _print_movie(movie)

    if not skip_confirmation:
        confirmed = click.confirm(
            "\nTem certeza que deseja apagar este filme e todos os registros "
            "relacionados? Esta ação não pode ser desfeita.",
            default=False,
        )
        if not confirmed:
            click.echo("Operação cancelada.")
            return False

    delete_movie_row(movie)
    click.echo(f"\nFilme #{movie_id} apagado com sucesso.")
    return True
