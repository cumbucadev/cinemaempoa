import json
import logging
import os

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
from flask_backend.scripts.tmdb_id_backfill import (
    tmdb_id_backfill as run_tmdb_id_backfill,
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
    app.cli.add_command(inspect_movies)
    app.cli.add_command(title_cleaning_report_command)
    app.cli.add_command(title_cleaning_backfill_command)
    app.cli.add_command(tmdb_id_backfill_command)
    app.cli.add_command(delete_movie_command)
    app.cli.add_command(sync_graph_command)
    app.cli.add_command(graph_query_command)
    app.cli.add_command(detect_motifs_command)


def _run_import_json(run, json_path):
    from flask_backend.repository import pipeline_runs

    with open(json_path) as json_file:
        try:
            parsed_json = json.load(json_file)
        except (json.decoder.JSONDecodeError, UnicodeDecodeError):
            message = "Arquivo .json inválido ou não encontrado"
            pipeline_runs.finish(run.id, status="error", error_message=message)
            click.echo(message, err=True)
            return

    runner = Runner()
    try:
        runner.parse_scrapped_json(parsed_json)
    except Exception:
        message = "Arquivo .json com estrutura inválida para importação"
        pipeline_runs.finish(run.id, status="error", error_message=message)
        click.echo(message, err=True)
        return

    slugs = sorted({c.slug for c in runner.scrapped_results.cinemas})
    pipeline_runs.set_source(run.id, ",".join(slugs))

    # validate all cinemas exist in db
    for json_cinema in runner.scrapped_results.cinemas:
        cinema = get_cinema_by_slug(json_cinema.slug)
        if cinema is None:
            message = f"Sala {json_cinema.slug} não encontrada."
            pipeline_runs.finish(run.id, status="error", error_message=message)
            click.echo(message, err=True)
            return

    # all validations passed, import screenings :)
    features_processed = sum(
        len(cinema.features) for cinema in runner.scrapped_results.cinemas
    )
    summary = runner.import_scrapped_results(current_app, pipeline_run_id=run.id)
    status = "warning" if features_processed == 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "movies_created": summary.movies_created,
                "screenings_created": summary.screenings_created,
                "dates_registered": summary.dates_registered,
            }
        ),
    )
    click.echo(
        f"«{summary.movies_created}» filmes, «{summary.screenings_created}» sessões "
        f"e «{summary.dates_registered}» novos horários registrados!"
    )


@click.command("import-json")
@click.argument("json_path")
def import_json(json_path):
    from flask_backend.repository import pipeline_runs

    run = pipeline_runs.start("import-json")
    try:
        _run_import_json(run, json_path)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise


@click.command("dupe-check")
def dupe_check():
    dupe_checker()


@click.command("sync-graph")
def sync_graph_command():
    """Reconstrói o grafo de conhecimento (movies, cinemas, sessões, gêneros,
    diretores, países) a partir do SQLite.

    Apaga e recria o grafo inteiro a cada execução - comando manual, não
    faz parte de nenhum pipeline automatizado.
    """
    from flask_backend.service.graph_sync import sync_graph

    result = sync_graph()
    click.echo(
        f"Grafo sincronizado: {result.nodes_created} nós, "
        f"{result.edges_created} arestas."
    )


GRAPH_QUERY_NAMES = [
    "movies-by-director",
    "directors-currently-showing",
    "countries-this-month",
    "genres-at-cinema",
    "screenings-since-release",
]


@click.command("graph-query")
@click.argument("query_name")
@click.option("--director", default=None, help="Nome do diretor.")
@click.option("--cinema", default=None, help="Slug da sala.")
@click.option("--year", type=int, default=None, help="Ano.")
@click.option("--movie", default=None, help="Slug do filme.")
def graph_query_command(query_name, director, cinema, year, movie):
    """Executa uma consulta pré-definida no grafo de conhecimento e imprime
    os resultados em formato de tabela simples.

    QUERY_NAME: movies-by-director | directors-currently-showing |
    countries-this-month | genres-at-cinema | screenings-since-release
    """
    from flask_backend.service import graph_queries

    if query_name not in GRAPH_QUERY_NAMES:
        raise click.UsageError(
            f"Consulta desconhecida: '{query_name}'. Opções: "
            f"{', '.join(GRAPH_QUERY_NAMES)}"
        )

    if query_name == "movies-by-director" and not director:
        raise click.UsageError("--director é obrigatório para movies-by-director")
    if query_name == "genres-at-cinema" and (not cinema or year is None):
        raise click.UsageError(
            "--cinema e --year são obrigatórios para genres-at-cinema"
        )
    if query_name == "screenings-since-release" and not movie:
        raise click.UsageError("--movie é obrigatório para screenings-since-release")

    # Read GRAPH_DB_PATH off the module at call time (not import time) so
    # tests that monkeypatch it still take effect. Without this check, a
    # missing graph file silently opens as a fresh empty graph and every
    # query below just returns [] - "Nenhum resultado." with no hint that
    # `sync-graph` was never run.
    if not os.path.exists(graph_queries.GRAPH_DB_PATH):
        raise click.UsageError(
            f"Grafo não encontrado em {graph_queries.GRAPH_DB_PATH}. "
            "Rode `flask --app flask_backend sync-graph` primeiro."
        )

    if query_name == "movies-by-director":
        rows = graph_queries.movies_by_director(director)
    elif query_name == "directors-currently-showing":
        rows = graph_queries.directors_currently_showing()
    elif query_name == "countries-this-month":
        rows = graph_queries.countries_this_month()
    elif query_name == "genres-at-cinema":
        rows = graph_queries.genres_at_cinema(cinema, year)
    else:
        rows = graph_queries.screenings_since_release(movie)

    if not rows:
        click.echo("Nenhum resultado.")
        return

    headers = list(rows[0].keys())
    click.echo(" | ".join(headers))
    for row in rows:
        click.echo(" | ".join(str(row[h]) for h in headers))


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
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.poster_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    run = pipeline_runs.start("fetch-posters")
    try:
        result = run_pipeline(
            current_app, limit=limit, dry_run=dry_run, pipeline_run_id=run.id
        )
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    status = "warning" if result.errors > 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "processed": result.processed,
                "posters_found": result.posters_found,
                "posters_not_found": result.posters_not_found,
                "errors": result.errors,
                "skipped_all_sources_tried": result.skipped_all_sources_tried,
            }
        ),
    )

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
    """Busca diretor(es) e gêneros no TMDB para filmes ainda não vinculados.

    Registra cada tentativa para evitar repetição.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.movie_metadata_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    run = pipeline_runs.start("fetch-movie-metadata")
    try:
        result = run_pipeline(limit=limit, dry_run=dry_run, pipeline_run_id=run.id)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    status = "warning" if result.errors > 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "processed": result.processed,
                "metadata_found": result.metadata_found,
                "metadata_not_found": result.metadata_not_found,
                "errors": result.errors,
                "skipped_all_sources_tried": result.skipped_all_sources_tried,
            }
        ),
    )

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

    São filmes ainda não vinculados ao TMDB cuja última tentativa de busca
    não teve sucesso.
    """
    from flask_backend.service.movie_metadata_pipeline import get_manual_review_summary

    summary = get_manual_review_summary()

    if not summary:
        click.echo("Nenhum filme pendente de revisão manual de metadados.")
        return

    click.echo(f"Filmes que precisam de revisão manual ({len(summary)}):\n")
    for item in summary:
        detail = item["status"]
        if item["error_message"]:
            detail = f"{detail}: {item['error_message']}"
        click.echo(f'  Movie #{item["movie_id"]} – "{item["movie_title"]}" ({detail})')


@click.command("inspect-movies")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Número máximo de filmes a inspecionar. Sem limite por padrão.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Mostra logs detalhados."
)
def inspect_movies(limit, verbose):
    """Verifica se o filme vinculado no TMDB é consistente com o que os
    cinemas publicaram sobre ele, corrigindo vínculos incorretos quando
    identifica um substituto com confiança e sinalizando os demais para
    revisão manual em /admin/movies/inspections.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.movie_inspector import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    run = pipeline_runs.start("inspect-movies")
    try:
        result = run_pipeline(limit=limit, pipeline_run_id=run.id)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    status = "warning" if result.errors > 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "processed": result.processed,
                "consistent": result.consistent,
                "fixed": result.fixed,
                "needs_review": result.needs_review,
                "errors": result.errors,
            }
        ),
    )

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da inspeção de filmes:")
    click.echo(f"  Processados:          {result.processed}")
    click.echo(f"  Consistentes:         {result.consistent}")
    click.echo(f"  Corrigidos:           {result.fixed}")
    click.echo(f"  Aguardando revisão:   {result.needs_review}")
    click.echo(f"  Erros:                {result.errors}")
    click.echo(f"{'=' * 40}")

    if result.needs_review > 0:
        click.echo(
            f"\n⚠ {result.needs_review} filme(s) aguardam revisão manual em "
            "/admin/movies/inspections."
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


@click.command("tmdb-id-backfill")
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    default=False,
    help="Aplica as alterações. Sem esta flag, apenas mostra o que seria feito.",
)
def tmdb_id_backfill_command(apply_):
    """Remove o histórico de tentativas de filmes que já têm metadados TMDB
    (diretor/gênero/título original) mas nunca tiveram tmdb_id gravado -
    relíquia do pipeline anterior ao #295. Por padrão roda em modo dry-run.

    Depois de aplicar, rode 'flask fetch-movie-metadata' para que esses
    filmes sejam buscados novamente no TMDB, desta vez gravando o tmdb_id.
    """
    run_tmdb_id_backfill(apply=apply_)


@click.command("delete-movie")
@click.argument("identifier")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Pula a confirmação e apaga direto.",
)
def delete_movie_command(identifier, yes):
    """Apaga um filme e todos os registros relacionados (sessões, datas,
    tentativas de busca de poster/metadados, associações de gênero/diretor/país).

    IDENTIFIER pode ser o id numérico ou o slug do filme.
    """
    run_delete_movie(identifier, skip_confirmation=yes)


@click.command("detect-motifs")
@click.option(
    "--limit", type=int, default=10, help="Número máximo de observações a exibir."
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Imprime as observações completas (com evidências) em JSON.",
)
def detect_motifs_command(limit, as_json):
    """Executa o motor de detecção de motivos editoriais sobre o grafo de
    conhecimento e imprime as observações de maior pontuação.
    """
    import dataclasses

    from flask_backend.service import motif_ranking

    if not os.path.exists(motif_ranking.GRAPH_DB_PATH):
        raise click.UsageError(
            f"Grafo não encontrado em {motif_ranking.GRAPH_DB_PATH}. "
            "Rode `flask --app flask_backend sync-graph` primeiro."
        )

    observations = motif_ranking.run_motifs()[:limit]

    if as_json:
        click.echo(
            json.dumps(
                [dataclasses.asdict(o) for o in observations],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not observations:
        click.echo("Nenhuma observação.")
        return

    for observation in observations:
        click.echo(
            f"{observation.score:.2f} | {observation.motif_name} | "
            f"{observation.headline}"
        )
