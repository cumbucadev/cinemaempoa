import json

import click
from flask import current_app

from flask_backend.repository.cinemas import (
    get_by_slug as get_cinema_by_slug,
)
from flask_backend.scripts.dedupper import dedupper
from flask_backend.scripts.dupechecker import dupe_checker
from flask_backend.service.runner import Runner


def register_commands(app):
    app.cli.add_command(import_json)
    app.cli.add_command(dupe_check)
    app.cli.add_command(run_dedupper)


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
