"""Applies title_cleaning.clean_title to all existing movies and merges any
rows that collapse onto the same slug as a result.

Usage (via CLI):
    flask title-cleaning-backfill          # dry-run, prints the plan only
    flask title-cleaning-backfill --apply  # performs the writes, single transaction

Back up the database file before the first --apply run - this command
deletes rows (merged duplicates) and is not reversible.
"""

from collections import defaultdict
from typing import Dict, List, Tuple

import click
from slugify import slugify

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.service.movie_merge import (
    merge_movies,
    pick_survivor,
    reset_fetch_attempts,
)
from flask_backend.service.title_cleaning import (
    CleanTitleResult,
    clean_title,
    is_known_junk,
)

Entry = Tuple[Movie, CleanTitleResult]


def _describe_movie(movie: Movie) -> str:
    bits = [f"{len(movie.screenings)} sessões"]
    if movie.directors:
        bits.append("diretor: " + ", ".join(d.name for d in movie.directors))
    if movie.genres:
        bits.append("gêneros: " + ", ".join(g.name for g in movie.genres))
    if movie.original_title:
        bits.append(f"título original: {movie.original_title}")
    if not movie.directors and not movie.genres and not movie.original_title:
        bits.append("sem metadados")
    return ", ".join(bits)


def _group_by_cleaned_slug(movies: List[Movie]) -> Dict[str, List[Entry]]:
    groups: Dict[str, List[Entry]] = defaultdict(list)
    for movie in movies:
        if is_known_junk(movie.title.strip()):
            continue
        result = clean_title(movie.title)
        groups[slugify(result.cleaned_title)].append((movie, result))
    return groups


def _print_plan(
    renames: List[Entry], merge_groups: List[Tuple[str, List[Entry]]]
) -> None:
    click.echo("=== Backfill de limpeza de títulos ===\n")
    click.echo(f"Renomeações simples (sem colisão de slug): {len(renames)}")
    click.echo(f"Grupos de fusão (colisão de slug após limpeza): {len(merge_groups)}\n")

    if renames:
        click.echo("--- Exemplos de renomeação ---")
        for movie, result in renames[:5]:
            click.echo(
                f'  Movie #{movie.id} "{result.raw_title}" → "{result.cleaned_title}"'
            )
        if len(renames) > 5:
            click.echo(f"  ... e mais {len(renames) - 5}")
        click.echo("")

    if merge_groups:
        click.echo("--- Fusões detectadas ---")
        for slug, entries in merge_groups:
            movies = [movie for movie, _ in entries]
            survivor = pick_survivor(movies)
            click.echo(f'  slug: "{slug}"')
            for movie, result in entries:
                marker = "sobrevivente" if movie.id == survivor.id else "fundido"
                click.echo(
                    f'    Movie #{movie.id} "{result.raw_title}" → '
                    f'"{result.cleaned_title}" [{marker}] ({_describe_movie(movie)})'
                )
        click.echo("")

    click.echo(f"{'=' * 60}")


def title_cleaning_backfill(apply: bool = False) -> None:
    movies = db_session.query(Movie).order_by(Movie.id).all()
    groups = _group_by_cleaned_slug(movies)

    renames: List[Entry] = []
    merge_groups: List[Tuple[str, List[Entry]]] = []
    for slug, entries in groups.items():
        if len(entries) == 1:
            if entries[0][1].changed:
                renames.append(entries[0])
        else:
            merge_groups.append((slug, entries))

    _print_plan(renames, merge_groups)

    if not apply:
        click.echo(
            "\nModo dry-run: nenhuma alteração foi feita. Use --apply para aplicar."
        )
        return

    try:
        for movie, result in renames:
            old_title = movie.title
            movie.title = result.cleaned_title
            movie.slug = slugify(result.cleaned_title)
            if movie.title != old_title:
                reset_fetch_attempts(movie)

        for _slug, entries in merge_groups:
            group_movies = [movie for movie, _ in entries]
            for movie, result in entries:
                movie.title = result.cleaned_title
                movie.slug = slugify(result.cleaned_title)
            survivor = pick_survivor(group_movies)
            duplicates = [movie for movie in group_movies if movie.id != survivor.id]
            merge_movies(survivor, duplicates)
            reset_fetch_attempts(survivor)

        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    click.echo(
        f"\nAplicado: {len(renames)} título(s) renomeado(s), "
        f"{len(merge_groups)} grupo(s) de filmes fundidos."
    )
