import os

import click
from flask.cli import with_appcontext
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from flask_backend.env_config import ADMIN_PROD_PWD, ADMIN_PROD_USERNAME, DATABASE_URL

# TODO: This is a hack to get the database to work with pytest
# see https://github.com/pytest-dev/pytest/issues/9502#issuecomment-2063572916
# we should be able to change this in conftest.py app fixture
if os.environ.get("PYTEST_VERSION"):
    engine = create_engine("sqlite:///:memory:")
else:
    engine = create_engine(DATABASE_URL)

db_session = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    """Initialize the database using Alembic migrations.
    This function executes all pending migrations to update the database.
    For new databases, it will create all tables.
    """
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


def seed_db_prod():
    from flask_backend.seeds import cinema_seeds, user_seeds

    print("Setting up admin user")
    try:
        user_seeds.create_user_from_data(
            db_session, ADMIN_PROD_USERNAME, ADMIN_PROD_PWD
        )
    except IntegrityError:
        db_session.rollback()
        print("Admin user already exists. Skipping...")
    print("Setting up default cinemas")
    try:
        cinema_seeds.create_cinemas(db_session)
    except IntegrityError:
        db_session.rollback()
        print("Cinemas already registered. Skipping...")


def seed_db():
    from flask_backend.seeds import (
        cinema_seeds,
        movie_seeds,
        screening_seeds,
        user_seeds,
    )

    try:
        screening_seeds.create_screenings(db_session)
    except IntegrityError:
        db_session.rollback()
        print("Screenings already registered. Skipping...")

    try:
        cinema_seeds.create_cinemas(db_session)
    except IntegrityError:
        db_session.rollback()
        print("Cinemas already registered. Skipping...")

    try:
        movie_seeds.create_movies(db_session)
    except IntegrityError:
        db_session.rollback()
        print("Movies already registered. Skipping...")

    try:
        user_seeds.create_user(db_session)
    except IntegrityError:
        db_session.rollback()
        print("Users already registered. Skipping...")


def init_app(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)
    app.cli.add_command(init_db_prod_command)
    app.cli.add_command(db_upgrade_command)
    app.cli.add_command(db_downgrade_command)
    app.cli.add_command(db_revision_command)
    app.cli.add_command(db_current_command)
    app.cli.add_command(db_history_command)


@click.command("init-db")
def init_db_command():
    """Create tables based on models.py using Alembic migrations.

    This command applies all pending migrations to initialize or update
    the database schema. It is idempotent and safe to run multiple times.
    """
    init_db()
    click.echo("Initialized the database.")


@click.command("init-db-prod")
def init_db_prod_command():
    """Creates all tables, populates the movies table and creates the admin user"""
    init_db()
    seed_db_prod()
    click.echo("Seeded the database - production.")


@click.command("seed-db")
def seed_db_command():
    """Populates database tables."""
    seed_db()
    click.echo("Seeded the database.")


@click.command("db-upgrade")
@click.argument("revision", default="head")
@with_appcontext
def db_upgrade_command(revision):
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, revision)
    click.echo(f"Database upgraded to revision: {revision}")


@click.command("db-downgrade")
@click.argument("revision", default="-1")
@with_appcontext
def db_downgrade_command(revision):
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, revision)
    click.echo(f"Database downgraded to revision: {revision}")


@click.command("db-revision")
@click.option(
    "--autogenerate",
    is_flag=True,
    help="Gera automaticamente migração a partir dos modelos",
)
@click.option("-m", "--message", help="Mensagem da migração")
@with_appcontext
def db_revision_command(autogenerate, message):
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    if autogenerate:
        command.revision(
            alembic_cfg, autogenerate=True, message=message or "Migração automática"
        )
        click.echo("Migração auto-gerada criada.")
    else:
        command.revision(alembic_cfg, message=message or "Nova migração")
        click.echo("Migração vazia criada.")


@click.command("db-current")
@with_appcontext
def db_current_command():
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.current(alembic_cfg)


@click.command("db-history")
@click.option("--verbose", "-v", is_flag=True, help="Mostra saída detalhada")
@with_appcontext
def db_history_command(verbose):
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.history(alembic_cfg, verbose=verbose)
