"""Relatório somente-leitura de títulos de filmes com anotações (prefixos de
mostras/sessões, sufixos de debate/conversa etc.) que poderiam ser removidas
automaticamente por flask_backend.service.title_cleaning. Não altera o
banco de dados."""

import click

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.service.title_cleaning import (
    RULE_CATEGORIES,
    clean_title,
    is_known_junk,
)


def title_cleaning_report():
    movies = db_session.query(Movie).order_by(Movie.id).all()

    category_hits: dict[str, list[tuple[str, str]]] = {}
    junk_suspects: list[tuple[int, str]] = []
    changed_count = 0

    for movie in movies:
        if is_known_junk(movie.title.strip()):
            junk_suspects.append((movie.id, movie.title))
            continue

        result = clean_title(movie.title)
        if not result.changed:
            continue

        changed_count += 1
        for rule_name in set(result.matched_rules):
            category = RULE_CATEGORIES.get(rule_name, rule_name)
            category_hits.setdefault(category, []).append(
                (result.raw_title, result.cleaned_title)
            )

    click.echo(
        "=== Relatório de limpeza de títulos (dry-run, nenhuma alteração é feita) ===\n"
    )
    click.echo(f"Total de filmes analisados: {len(movies)}")
    click.echo(f"Títulos que seriam alterados: {changed_count}")
    click.echo(
        f"Títulos suspeitos (revisão manual, não tratados): {len(junk_suspects)}\n"
    )

    click.echo("--- Por padrão detectado ---\n")
    for category, examples in sorted(category_hits.items(), key=lambda kv: -len(kv[1])):
        click.echo(f"{category:<40} {len(examples)} ocorrência(s)")
        for before, after in examples[:3]:
            click.echo(f'  "{before}" → "{after}"')
        click.echo("")

    if junk_suspects:
        click.echo("--- Títulos suspeitos / anômalos (revisão manual) ---")
        for movie_id, title in junk_suspects:
            click.echo(f'  Movie #{movie_id} – "{title}"')

    click.echo(f"\n{'=' * 60}")
