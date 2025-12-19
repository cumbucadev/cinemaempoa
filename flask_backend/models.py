from typing import List

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, relationship

from flask_backend.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(20), unique=True, nullable=False)
    password = Column(String, nullable=False)


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=True, index=True)

    screenings: Mapped[List["Screening"]] = relationship(back_populates="movie")
    directors: Mapped[List["Director"]] = relationship(secondary="movie_directors")


class Cinema(Base):
    __tablename__ = "cinemas"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)


class Screening(Base):
    __tablename__ = "screenings"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    cinema_id = Column(Integer, ForeignKey("cinemas.id"), nullable=False)
    url = Column(String, nullable=True)
    # TODO: should image and description belong to the movie?
    image = Column(String, nullable=True)
    image_alt = Column(String, nullable=True)
    description = Column(String, nullable=False)
    # TODO: maybe change this to a _status_ enum?
    draft = Column(Boolean, nullable=False, default=False)

    # TODO: maybe keep image related properties in a separate "medias" table?
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    movie: Mapped["Movie"] = relationship(back_populates="screenings")
    cinema: Mapped["Cinema"] = relationship()
    dates: Mapped[List["ScreeningDate"]] = relationship(back_populates="screening")


class ScreeningDate(Base):
    __tablename__ = "screening_dates"

    id = Column(Integer, primary_key=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(String, nullable=True)

    screening: Mapped["Screening"] = relationship(back_populates="dates")


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=True, index=True)
    content = Column(Text, nullable=False)
    excerpt = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    published = Column(Boolean, nullable=False, default=False)
    featured_image = Column(String, nullable=True)
    featured_image_alt = Column(String, nullable=True)

    author: Mapped["User"] = relationship()


class Director(Base):
    __tablename__ = "directors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=True, index=True)

    movies: Mapped[List[Movie]] = relationship(secondary="movie_directors")


class MovieDirectors(Base):
    __tablename__ = "movie_directors"

    movie_id = Column(
        Integer, ForeignKey("movies.id"), primary_key=True, nullable=False
    )
    director_id = Column(
        Integer, ForeignKey("directors.id"), primary_key=True, nullable=False
    )
