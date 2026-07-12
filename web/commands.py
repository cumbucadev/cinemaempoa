import click

from web.scripts.dedupper import dedupper
from web.scripts.dupechecker import dupe_checker
from web.scripts.sitemap import sitemap


def register_commands(app):
    app.cli.add_command(dupe_check)
    app.cli.add_command(run_dedupper)
    app.cli.add_command(generate_sitemap)


@click.command("dupe-check")
def dupe_check():
    dupe_checker()


@click.command("run-dedupper")
def run_dedupper():
    dedupper()


@click.command("generate-sitemap")
def generate_sitemap():
    sitemap()
