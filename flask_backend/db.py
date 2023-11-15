import click

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

from flask_backend.env_config import DATABASE_URL

engine = create_engine(DATABASE_URL)
db_session = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    import flask_backend.models

    Base.metadata.create_all(bind=engine)


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


@click.command("init-db")
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")


@click.command("seed-db")
def seed_db_command():
    """Populates database tables."""
    seed_db()
    click.echo("Seeded the database.")
