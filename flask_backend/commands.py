import json
import logging

import click
from flask import current_app

from flask_backend.repository.cinemas import (
    get_by_slug as get_cinema_by_slug,
)
from flask_backend.scripts.dedupper import dedupper
from flask_backend.scripts.delete_movie import delete_movie as run_delete_movie
from flask_backend.scripts.dupechecker import dupe_checker
from flask_backend.scripts.sitemap import sitemap
from flask_backend.scripts.title_cleaning_backfill import (
    title_cleaning_backfill as run_title_cleaning_backfill,
)
from flask_backend.scripts.title_cleaning_report import (
    title_cleaning_report as run_title_cleaning_report,
)
from flask_backend.service.runner import Runner


def register_commands(app):
    app.cli.add_command(import_json)
    app.cli.add_command(dupe_check)
    app.cli.add_command(run_dedupper)
    app.cli.add_command(generate_sitemap)
    app.cli.add_command(fetch_posters)
    app.cli.add_command(poster_review)
    app.cli.add_command(fetch_movie_metadata)
    app.cli.add_command(movie_metadata_review)
    app.cli.add_command(title_cleaning_report_command)
    app.cli.add_command(title_cleaning_backfill_command)
    app.cli.add_command(delete_movie_command)
    app.cli.add_command(generate_alerts)


@click.command("import-json")
@click.argument("json_path")
def import_json(json_path):
    with open(json_path) as json_file:
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
            f'  Screening #{item["screening_id"]} – "{item["movie_title"]}" '
            f"(fontes tentadas: {', '.join(item['sources_attempted'])})"
        )


@click.command("fetch-movie-metadata")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Número máximo de filmes a processar. Sem limite por padrão.",
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
def fetch_movie_metadata(limit, dry_run, verbose):
    """Busca diretor(es) e gêneros para filmes sem esses dados.

    Tenta fontes na ordem: TMDB.
    Registra cada tentativa para evitar repetição.
    """
    from flask_backend.service.movie_metadata_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    result = run_pipeline(limit=limit, dry_run=dry_run)

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da busca de metadados de filmes:")
    click.echo(f"  Processados:          {result.processed}")
    click.echo(f"  Metadados encontrados:  {result.metadata_found}")
    click.echo(f"  Não encontrados:      {result.metadata_not_found}")
    click.echo(f"  Erros:                {result.errors}")
    click.echo(f"  Fontes esgotadas:     {result.skipped_all_sources_tried}")
    click.echo(f"{'=' * 40}")

    if result.skipped_all_sources_tried > 0:
        click.echo(
            f"\n⚠ {result.skipped_all_sources_tried} filme(s) já tentaram todas "
            "as fontes sem sucesso. Use 'flask movie-metadata-review' para listá-los."
        )


@click.command("movie-metadata-review")
def movie_metadata_review():
    """Lista filmes que precisam de revisão manual de metadados.

    São filmes sem diretor que já tentaram todas as fontes
    disponíveis (TMDB) sem sucesso.
    """
    from flask_backend.service.movie_metadata_pipeline import get_manual_review_summary

    summary = get_manual_review_summary()

    if not summary:
        click.echo("Nenhum filme pendente de revisão manual de metadados.")
        return

    click.echo(f"Filmes que precisam de revisão manual ({len(summary)}):\n")
    for item in summary:
        click.echo(
            f'  Movie #{item["movie_id"]} – "{item["movie_title"]}" '
            f"(fontes tentadas: {', '.join(item['sources_attempted'])})"
        )


@click.command("title-cleaning-report")
def title_cleaning_report_command():
    """Relatório somente-leitura de títulos com anotações detectáveis
    (prefixos de mostras/sessões, sufixos de debate/conversa etc.).
    """
    run_title_cleaning_report()


@click.command("title-cleaning-backfill")
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    default=False,
    help="Aplica as alterações. Sem esta flag, apenas mostra o que seria feito.",
)
def title_cleaning_backfill_command(apply_):
    """Limpa os títulos existentes e funde filmes cuja limpeza resulte no
    mesmo slug. Por padrão roda em modo dry-run (nenhuma alteração é feita).

    ATENÇÃO: --apply grava no banco e funde/apaga registros duplicados de
    forma irreversível. Faça backup do arquivo do banco antes de usar.
    """
    run_title_cleaning_backfill(apply=apply_)


@click.command("generate-alerts")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Número máximo de sessões/filmes a avaliar. Sem limite por padrão.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Apenas lista o que seria criado, sem gravar alertas.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Mostra logs detalhados."
)
def generate_alerts(limit, dry_run, verbose):
    """Avalia as regras de alerta (filme novo, sessão única, sessão
    comentada, mostra, estreia/retorno de diretor, nova combinação de
    gênero, sequência/franquia) e grava os alertas pendentes.

    Revise-os em /admin/alerts.
    """
    from flask_backend.service.alert_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhum alerta será gravado ===\n")

    result = run_pipeline(limit=limit, dry_run=dry_run)

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da geração de alertas:")
    click.echo(f"  Sessões avaliadas:    {result.screenings_evaluated}")
    click.echo(f"  Filmes avaliados:     {result.movies_evaluated}")
    click.echo(f"  Alertas gerados:      {result.alerts_created}")
    if result.alerts_by_rule:
        click.echo("  Por regra:")
        for rule_name, count in sorted(result.alerts_by_rule.items()):
            click.echo(f"    {rule_name}: {count}")
    click.echo(f"{'=' * 40}")


@click.command("delete-movie")
@click.argument("movie_id", type=int)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Pula a confirmação e apaga direto.",
)
def delete_movie_command(movie_id, yes):
    """Apaga um filme e todos os registros relacionados (sessões, datas,
    tentativas de busca de poster/metadados, associações de gênero/diretor/país).
    """
    run_delete_movie(movie_id, skip_confirmation=yes)
