import click
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from flask_backend.env_config import ADMIN_PROD_PWD, ADMIN_PROD_USERNAME, DATABASE_URL

engine = create_engine(DATABASE_URL)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    import flask_backend.models

    Base.metadata.create_all(bind=engine)


def seed_db_prod():
    from flask_backend.seeds import cinema_seeds, user_seeds

    print("Setting up admin user")
    try:
        user_seeds.create_user_from_data(db_session, ADMIN_PROD_USERNAME, ADMIN_PROD_PWD)
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

    cinema_seeds.create_cinemas(db_session)
    movie_seeds.create_movies(db_session)
    screening_seeds.create_screenings(db_session)
    user_seeds.create_user(db_session)


def init_app(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)
    app.cli.add_command(init_db_prod_command)


@click.command("init-db")
def init_db_command():
    """Create tables based on models.py - idempotent operation."""
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
