import json
import logging

import click
from flask import current_app

from flask_backend.repository.cinemas import (
    get_by_slug as get_cinema_by_slug,
)
from flask_backend.scripts.dedupper import dedupper
from flask_backend.scripts.dupechecker import dupe_checker
from flask_backend.scripts.sitemap import sitemap
from flask_backend.service.runner import Runner


def register_commands(app):
    app.cli.add_command(import_json)
    app.cli.add_command(dupe_check)
    app.cli.add_command(run_dedupper)
    app.cli.add_command(generate_sitemap)
    app.cli.add_command(fetch_posters)
    app.cli.add_command(poster_review)


@click.command("import-json")
@click.argument("json_path")
def import_json(json_path):
    with open(json_path, mode="r") as json_file:
        try:
            parsed_json = json.load(json_file)
        except (json.decoder.JSONDecodeError, UnicodeDecodeError):
            click.echo("Arquivo .json inválido ou não encontrado", err=True)
            return

    runner = Runner()
    try:
        runner.parse_scrapped_json(parsed_json)
    except Exception:
        click.echo("Arquivo .json com estrutura inválida para importação", err=True)
        return

    # validate all cinemas exist in db
    for json_cinema in runner.scrapped_results.cinemas:
        cinema = get_cinema_by_slug(json_cinema.slug)
        if cinema is None:
            click.echo(f"Sala {json_cinema.slug} não encontrada.", err=True)
            return

    # all validations passed, import screenings :)
    created_features = runner.import_scrapped_results(current_app)
    click.echo(f"«{created_features}» sessões criadas com sucesso!")


@click.command("dupe-check")
def dupe_check():
    dupe_checker()


@click.command("run-dedupper")
def run_dedupper():
    dedupper()


@click.command("generate-sitemap")
def generate_sitemap():
    sitemap()


@click.command("fetch-posters")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Número máximo de sessões a processar. Sem limite por padrão.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Apenas lista o que seria feito, sem fazer requisições.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Mostra logs detalhados."
)
def fetch_posters(limit, dry_run, verbose):
    """Busca posters para sessões sem imagem.

    Tenta fontes na ordem: TMDB, IMDB.
    Registra cada tentativa para evitar repetição.
    """
    from flask_backend.service.poster_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    result = run_pipeline(current_app, limit=limit, dry_run=dry_run)

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da busca de posters:")
    click.echo(f"  Processadas:          {result.processed}")
    click.echo(f"  Posters encontrados:  {result.posters_found}")
    click.echo(f"  Posters não encontr.: {result.posters_not_found}")
    click.echo(f"  Erros:                {result.errors}")
    click.echo(f"  Fontes esgotadas:     {result.skipped_all_sources_tried}")
    click.echo(f"{'=' * 40}")

    if result.skipped_all_sources_tried > 0:
        click.echo(
            f"\n⚠ {result.skipped_all_sources_tried} sessão(ões) já tentaram todas "
            "as fontes sem sucesso. Use 'flask poster-review' para listá-las."
        )


@click.command("poster-review")
def poster_review():
    """Lista sessões que precisam de revisão manual de poster.

    São sessões sem imagem que já tentaram todas as fontes
    disponíveis (TMDB, IMDB) sem sucesso.
    """
    from flask_backend.service.poster_pipeline import get_manual_review_summary

    summary = get_manual_review_summary()

    if not summary:
        click.echo("Nenhuma sessão pendente de revisão manual de poster.")
        return

    click.echo(f"Sessões que precisam de revisão manual ({len(summary)}):\n")
    for item in summary:
        click.echo(
            f"  Screening #{item['screening_id']} – \"{item['movie_title']}\" "
            f"(fontes tentadas: {', '.join(item['sources_attempted'])})"
        )
